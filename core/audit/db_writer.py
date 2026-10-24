# -*- coding: utf-8 -*-
"""core.audit.db_writer —— 决策审计写入 PostgreSQL。

基于第一性原理：
    决策记录只写文件 = 审计是死的，无法查询、无法统计、无法复用。
    写入数据库 = 决策是活的，可以聚合分析、可以驱动复盘、可以沉淀为知识。

设计原则：
1. 失败不影响主交易流程（写库失败只记日志，不抛异常）
2. 异步写入更好，但第一版用同步简单实现
3. 字段映射清晰，可追溯
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

from .record import Decision

log = logging.getLogger("core.audit.db")


# ------------------------------------------------------------------
# 数据库连接（懒加载）
# ------------------------------------------------------------------
_pg_conn = None


def _get_pg_conn():
    """懒加载PostgreSQL连接。从环境变量读取配置。"""
    global _pg_conn
    if _pg_conn is not None:
        return _pg_conn

    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor

        dsn = os.environ.get(
            "QUANTDINGER_PG_DSN",
            "postgresql://quantdinger:f0305a79f750eb324df59b8d2c483e55@localhost:5432/quantdinger"
        )
        _pg_conn = psycopg2.connect(dsn)
        _pg_conn.autocommit = True
        log.info("PostgreSQL audit connection established")
        return _pg_conn
    except ImportError:
        log.warning("psycopg2 not installed, DB audit disabled")
        return None
    except Exception as e:
        log.warning("Failed to connect to PostgreSQL for audit: %s", e)
        return None


# ------------------------------------------------------------------
# Decision -> qd_ai_decisions 字段映射
# ------------------------------------------------------------------
def decision_to_db_row(decision: Decision) -> dict:
    """把 Decision 对象映射为 qd_ai_decisions 表字段。"""
    signal = decision.signal
    signal_dict = {}
    if hasattr(signal, "__dict__"):
        signal_dict = vars(signal)

    risk_state = decision.risk_state
    risk_dict = {}
    if hasattr(risk_state, "__dict__"):
        risk_dict = vars(risk_state)

    return {
        "decision_uid": decision.decision_id,
        "source_type": "strategy",
        "symbol": getattr(signal, "symbol", "unknown"),
        "action": "open_long" if decision.final_signed_lots > 0 else
                  "open_short" if decision.final_signed_lots < 0 else "reject",
        "market_type": "crypto",
        "model": decision.model_version,
        "decision": "accept" if decision.accepted else "reject",
        "allowed": decision.accepted,
        "confidence": getattr(risk_state, "confidence", 0.5),
        "reason": decision.reject_reason or "accepted by rules",
        "fallback_reason": decision.reject_reason or "",
        "probabilities_json": json.dumps(decision.feature_snapshot),
        "checks_json": json.dumps({
            "threshold_dataset": decision.threshold_dataset,
            "decision_rule_version": decision.decision_rule_version,
            "final_signed_lots": decision.final_signed_lots,
        }),
        "request_snapshot": json.dumps({
            "signal": signal_dict,
            "risk_state": risk_dict,
        }),
        "billing_json": "{}",
        "latency_ms": 0,
    }


# ------------------------------------------------------------------
# 写入函数
# ------------------------------------------------------------------
def write_decision_to_db(decision: Decision) -> bool:
    """把 Decision 写入 qd_ai_decisions 表。

    Returns:
        True if written successfully, False otherwise.
        失败不抛异常，只记日志（不影响主交易流程）。
    """
    conn = _get_pg_conn()
    if conn is None:
        return False

    row = decision_to_db_row(decision)

    sql = """
        INSERT INTO qd_ai_decisions (
            decision_uid, source_type, symbol, action, market_type,
            model, decision, allowed, confidence, reason, fallback_reason,
            probabilities_json, checks_json, request_snapshot, billing_json, latency_ms
        ) VALUES (
            %(decision_uid)s, %(source_type)s, %(symbol)s, %(action)s, %(market_type)s,
            %(model)s, %(decision)s, %(allowed)s, %(confidence)s, %(reason)s, %(fallback_reason)s,
            %(probabilities_json)s::jsonb, %(checks_json)s::jsonb, %(request_snapshot)s::jsonb,
            %(billing_json)s::jsonb, %(latency_ms)s
        )
        ON CONFLICT (decision_uid) DO NOTHING
    """

    try:
        with conn.cursor() as cur:
            cur.execute(sql, row)
        log.debug("decision written to DB: %s accepted=%s",
                  decision.decision_id, decision.accepted)
        return True
    except Exception as e:
        log.warning("Failed to write decision to DB: %s", e)
        # 连接可能坏了，重置
        global _pg_conn
        _pg_conn = None
        return False


# ------------------------------------------------------------------
# 写入复盘记录
# ------------------------------------------------------------------
def write_post_mortem_to_db(
    title: str,
    post_mortem_type: str,
    severity: str,
    what_happened: str,
    why_it_happened: str,
    what_we_learned: str,
    how_to_improve: str,
    root_cause_category: str = "system",
) -> Optional[int]:
    """写一条复盘记录到 qd_post_mortems 表。

    Returns:
        插入的记录ID，失败返回 None。
    """
    conn = _get_pg_conn()
    if conn is None:
        return None

    import uuid
    pm_uid = f"pm-{uuid.uuid4().hex[:12]}"

    sql = """
        INSERT INTO qd_post_mortems (
            post_mortem_uid, title, post_mortem_type, severity,
            root_cause_category, what_happened, why_it_happened,
            what_we_learned, how_to_improve, status, occurred_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, 'open', NOW()
        )
        RETURNING id
    """

    try:
        with conn.cursor() as cur:
            cur.execute(sql, (
                pm_uid, title, post_mortem_type, severity,
                root_cause_category, what_happened, why_it_happened,
                what_we_learned, how_to_improve,
            ))
            result = cur.fetchone()
            record_id = result[0] if result else None
        log.info("post-mortem written to DB: id=%s title=%s", record_id, title)
        return record_id
    except Exception as e:
        log.warning("Failed to write post-mortem to DB: %s", e)
        global _pg_conn
        _pg_conn = None
        return None


# ------------------------------------------------------------------
# 写入故障知识
# ------------------------------------------------------------------
def write_fault_knowledge_to_db(
    title: str,
    symptom: str,
    root_cause: str,
    solution: str,
    category: str = "system",
    severity: str = "P2",
) -> Optional[int]:
    """写一条故障知识到 qd_fault_knowledge 表。"""
    conn = _get_pg_conn()
    if conn is None:
        return None

    import uuid
    fault_uid = f"fault-{uuid.uuid4().hex[:12]}"

    sql = """
        INSERT INTO qd_fault_knowledge (
            fault_uid, title, symptom, root_cause, solution,
            category, severity, verified, confidence_score
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, false, 0.5
        )
        RETURNING id
    """

    try:
        with conn.cursor() as cur:
            cur.execute(sql, (
                fault_uid, title, symptom, root_cause, solution,
                category, severity,
            ))
            result = cur.fetchone()
            record_id = result[0] if result else None
        log.info("fault knowledge written to DB: id=%s title=%s", record_id, title)
        return record_id
    except Exception as e:
        log.warning("Failed to write fault knowledge to DB: %s", e)
        global _pg_conn
        _pg_conn = None
        return None


# ------------------------------------------------------------------
# 写入交易日志
# ------------------------------------------------------------------
def write_trade_to_db(
    trade_uid: str,
    symbol: str,
    side: str,
    entry_time,
    entry_price: float,
    quantity: float,
    stop_loss: float = None,
    take_profit: float = None,
    exit_time=None,
    exit_price: float = None,
    gross_pnl: float = None,
    commission: float = 0,
    slippage_cost: float = 0,
    net_pnl: float = None,
    r_multiple: float = None,
    strategy_id: int = None,
    decision_id: str = None,
    market_regime: str = None,
    entry_reason: str = None,
    exit_reason: str = None,
    confidence: float = None,
    status: str = "open",
) -> Optional[int]:
    """写一条交易日志到 qd_trade_journal 表。

    用于记录完整的交易生命周期：
    - 开仓时：status='open'，只有入场信息
    - 平仓时：status='closed'，补充出场信息和盈亏
    """
    conn = _get_pg_conn()
    if conn is None:
        return None

    # 计算持仓时长
    holding_hours = None
    if entry_time and exit_time:
        from datetime import datetime
        if isinstance(entry_time, str):
            entry_time = datetime.fromisoformat(entry_time)
        if isinstance(exit_time, str):
            exit_time = datetime.fromisoformat(exit_time)
        holding_hours = round((exit_time - entry_time).total_seconds() / 3600, 2)

    # 计算净盈亏
    if net_pnl is None and gross_pnl is not None:
        net_pnl = gross_pnl - commission - slippage_cost

    sql = """
        INSERT INTO qd_trade_journal (
            trade_uid, symbol, side, entry_time, exit_time, holding_hours,
            entry_price, exit_price, quantity, stop_loss, take_profit,
            gross_pnl, commission, slippage_cost, net_pnl, r_multiple,
            strategy_id, decision_id, market_regime, entry_reason, exit_reason,
            confidence, status
        ) VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s
        )
        ON CONFLICT (trade_uid) DO UPDATE SET
            exit_time = EXCLUDED.exit_time,
            exit_price = EXCLUDED.exit_price,
            holding_hours = EXCLUDED.holding_hours,
            gross_pnl = EXCLUDED.gross_pnl,
            net_pnl = EXCLUDED.net_pnl,
            r_multiple = EXCLUDED.r_multiple,
            exit_reason = EXCLUDED.exit_reason,
            status = EXCLUDED.status,
            updated_at = NOW()
        RETURNING id
    """

    try:
        with conn.cursor() as cur:
            cur.execute(sql, (
                trade_uid, symbol, side, entry_time, exit_time, holding_hours,
                entry_price, exit_price, quantity, stop_loss, take_profit,
                gross_pnl, commission, slippage_cost, net_pnl, r_multiple,
                strategy_id, decision_id, market_regime, entry_reason, exit_reason,
                confidence, status,
            ))
            result = cur.fetchone()
            record_id = result[0] if result else None
        log.info("trade journal written: id=%s uid=%s status=%s", record_id, trade_uid, status)
        return record_id
    except Exception as e:
        log.warning("Failed to write trade journal: %s", e)
        global _pg_conn
        _pg_conn = None
        return None
