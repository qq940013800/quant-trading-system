# -*- coding: utf-8 -*-
"""
策略生命周期自动退役监控（Strategy Health Monitor）

职责（仅接线，不改既有阈值）：
  1. 周期性为运行中的实盘策略构建绩效快照（复用 dashboard._compute_performance_stats
     与 trade_net_pnl 的同一净盈亏口径，保证与前端绩效卡一致）。
  2. 调用 strategy_lifecycle.evaluate_strategy_health 评估健康状态。
  3. RED  → 真实退役：平仓（trading_executor.stop_strategy_with_policy(close_positions=True)）
            + DB 状态置 stopped + 审计日志（幂等，失败不阻塞状态收口）。
     YELLOW → 仅记录预警（减仓 50% 需要改 registry/config 仓位，属 AGENTS.md 人工确认范围，
            本轮只落日志与建议，不自动改仓位）。
     GREEN → 不动作。

口径说明（诚实标注）：
  - total_return / sharpe：以 qd_strategies_trading.initial_capital 锚定逐笔收益；
    initial_capital <= 0 时 total_return 记为 0 且标注不可锚定（不参与决策）。
  - sharpe 为每笔收益的 mean/std（不年化；样本 < 20 时统计意义不足，由评估函数扣样本分）。
  - max_drawdown / current_drawdown 均为小数（0.20 = 20%），与 HEALTH_THRESHOLDS 一致。
  - baseline（上线基线绩效）当前无持久化来源，sharpe_decay 维度在 baseline=None 时跳过。
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.services.strategy_lifecycle import (
    HealthStatus,
    HealthDecision,
    StrategyPerformance,
    evaluate_strategy_health,
)
from app.utils.db import get_db_connection
from app.utils.logger import get_logger
from app.utils.strategy_runtime_logs import append_strategy_log

logger = get_logger(__name__)

_retired_lock = threading.Lock()
_retired_sids: set = set()          # 进程级幂等：本运行周期已退役的策略不再重复触发
_retired_cooldown_s = 1800          # 冷却后允许重新评估（人工恢复后重跑）


def _net_profit(t: Dict[str, Any]) -> float:
    """与 dashboard 同一净盈亏口径（profit - 开平仓手续费）。"""
    from app.utils.trade_net_pnl import net_pnl_for_equity_step

    return float(net_pnl_for_equity_step(t) or 0.0)


def build_strategy_performance_from_rows(
    strategy: Dict[str, Any],
    trades: List[Dict[str, Any]],
) -> StrategyPerformance:
    """
    由策略行 + 交易事件行构造绩效快照（纯函数，可单测）。

    strategy 至少含: id, strategy_name, initial_capital
    trades: qd_strategy_trades 行（open/add 事件 profit 为 NULL，自动剔除）。
    """
    from app.routes.dashboard import _compute_performance_stats

    sid = int(strategy.get("id") or 0)
    name = str(strategy.get("strategy_name") or f"strategy-{sid}")
    initial = float(strategy.get("initial_capital") or 0.0)

    stats = _compute_performance_stats(trades or [], initial_capital=initial)
    closing = [t for t in (trades or []) if t.get("profit") is not None]
    profits = [_net_profit(t) for t in closing]

    total_return = 0.0
    sharpe = 0.0
    if initial > 0 and profits:
        returns = [p / initial for p in profits]
        total_return = sum(returns)
        n = len(returns)
        mean = sum(returns) / n
        var = sum((r - mean) ** 2 for r in returns) / n if n > 1 else 0.0
        sharpe = (mean / (var ** 0.5)) if var > 0 else 0.0

    # 当前回撤（小数）：当前累计净收益相对历史峰值
    current_drawdown = 0.0
    if profits:
        cum = 0.0
        peak = 0.0
        for p in profits:
            cum += p
            if cum > peak:
                peak = cum
        if peak > 0:
            current_drawdown = max(0.0, (peak - cum) / peak)

    # 连续亏损（小数口径与 evaluate 一致，threshold 为次数）
    loss_streak = 0
    for p in reversed(profits):
        if p < 0:
            loss_streak += 1
        else:
            break

    return StrategyPerformance(
        strategy_id=sid,
        strategy_name=name,
        total_return=total_return,
        sharpe_ratio=sharpe,
        max_drawdown=float(stats.get("max_drawdown_pct") or 0.0) / 100.0,
        win_rate=float(stats.get("win_rate") or 0.0) / 100.0,
        profit_factor=float(stats.get("profit_factor") or 0.0),
        trades_count=int(stats.get("total_trades") or 0),
        current_drawdown=current_drawdown,
        loss_streak=loss_streak,
    )


def fetch_live_strategies() -> List[Dict[str, Any]]:
    """运行中的实盘策略（仅 execution_mode='live' AND status='running'）。"""
    with get_db_connection() as db:
        cur = db.cursor()
        cur.execute(
            """
            SELECT id, strategy_name, user_id, initial_capital, status
            FROM qd_strategies_trading
            WHERE status = 'running'
              AND execution_mode = 'live'
            ORDER BY id
            """
        )
        rows = [dict(r) for r in (cur.fetchall() or [])]
        cur.close()
    return rows


def fetch_strategy_trades(strategy_id: int) -> List[Dict[str, Any]]:
    """策略全部交易事件（按 id 即事件时序排序，保持权益曲线顺序）。"""
    with get_db_connection() as db:
        cur = db.cursor()
        cur.execute(
            "SELECT * FROM qd_strategy_trades WHERE strategy_id = %s ORDER BY id",
            (int(strategy_id),),
        )
        rows = [dict(r) for r in (cur.fetchall() or [])]
        cur.close()
    return rows


def retire_strategy(
    strategy_id: int,
    decision: HealthDecision,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    执行 RED 退役（幂等）：
      stop_strategy_with_policy(close_positions=True) → DB stopped → 审计日志。
    平仓异常不阻塞状态收口（防止死循环重试），但会如实记录 close 结果。
    """
    sid = int(strategy_id)
    with _retired_lock:
        if sid in _retired_sids:
            return {"strategy_id": sid, "status": "already_retired", "success": True}
        _retired_sids.add(sid)

    result: Dict[str, Any] = {
        "strategy_id": sid,
        "status": "retired",
        "close_requested": True,
        "close_ok": False,
        "close_detail": "",
    }
    log_reason = "; ".join(decision.reasons) or decision.suggested_action

    # 1) 停止 + 真实平仓（reduce-only 队列）
    try:
        from app import get_trading_executor

        r = get_trading_executor().stop_strategy_with_policy(sid, close_positions=True)
        result["close_ok"] = bool(r.get("success"))
        result["close_detail"] = str(r.get("close_errors") or r.get("status") or "")
    except Exception as e:  # noqa: BLE001
        result["close_detail"] = f"close failed: {e}"
        logger.warning("retire: close strategy %s failed: %s", sid, e)

    # 2) DB 状态置 stopped（失败也要继续记录日志，避免阻塞审计）
    try:
        from app.services.strategy import StrategyService

        kw = {}
        if user_id is not None:
            kw["user_id"] = int(user_id)
        StrategyService().update_strategy_status(sid, "stopped", **kw)
    except Exception as e:  # noqa: BLE001
        logger.warning("retire: db stop strategy %s failed: %s", sid, e)
        result["close_detail"] = (result["close_detail"] + f"; db_stop failed: {e}").strip()

    # 3) 审计日志（无论 1/2 是否失败都记录决策）
    try:
        append_strategy_log(
            sid,
            "error",
            f"[auto-retire RED] {decision.suggested_action} | reasons: {log_reason} | close_ok={result['close_ok']}",
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("retire: append log strategy %s: %s", sid, e)

    return result


def run_strategy_health_check_once() -> Dict[str, Any]:
    """
    单轮健康检查：遍历 live 策略 → 构建绩效 → 评估 → RED 退役 / YELLOW 日志。
    返回本轮统计（供 worker 日志与测试断言）。
    """
    summary = {"checked": 0, "green": 0, "yellow": 0, "red": 0, "errors": [], "retired": []}
    try:
        strategies = fetch_live_strategies()
    except Exception as e:  # noqa: BLE001
        logger.warning("health check: fetch live strategies failed: %s", e)
        summary["errors"].append(f"fetch_strategies: {e}")
        return summary

    for st in strategies or []:
        sid = int(st.get("id") or 0)
        if sid <= 0:
            continue
        summary["checked"] += 1
        try:
            trades = fetch_strategy_trades(sid)
            perf = build_strategy_performance_from_rows(st, trades)
            decision = evaluate_strategy_health(perf, baseline_perf=None)
        except Exception as e:  # noqa: BLE001
            logger.warning("health check: eval strategy %s failed: %s", sid, e)
            summary["errors"].append(f"strategy_{sid}: {e}")
            continue

        if decision.status == HealthStatus.RED:
            summary["red"] += 1
            r = retire_strategy(sid, decision, user_id=st.get("user_id"))
            summary["retired"].append({"strategy_id": sid, **r})
        elif decision.status == HealthStatus.YELLOW:
            summary["yellow"] += 1
            try:
                append_strategy_log(
                    sid,
                    "warning",
                    f"[auto-retire YELLOW] {decision.suggested_action} | reasons: "
                    + "; ".join(decision.reasons),
                )
            except Exception as e:  # noqa: BLE001
                logger.debug("health check: append yellow log %s: %s", sid, e)
        else:
            summary["green"] += 1

    return summary


class StrategyHealthWorker(threading.Thread):
    """
    周期调度载体（独立线程，故障隔离：健康检查异常不影响下单/持仓 worker）。
    退避：连续失败时间隔指数增长（上限 300s）；成功恢复基准间隔。
    部署：由容器/compose 启动独立 worker（接线步骤见交付说明，未在本轮自动部署）。
    """

    def __init__(self, interval: float = 60.0, stop_event: Optional[threading.Event] = None):
        super().__init__(name="strategy-health-worker", daemon=True)
        self.interval = max(5.0, float(interval))
        self._stop = stop_event or threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        logger.info("strategy health worker started (interval=%.0fs)", self.interval)
        backoff = self.interval
        while not self._stop.wait(backoff):
            try:
                summary = run_strategy_health_check_once()
                if summary.get("errors"):
                    logger.warning("health check round errors: %s", summary["errors"])
                if summary.get("red"):
                    logger.warning("health check round: %s", summary)
                backoff = self.interval  # 成功恢复基准间隔
            except Exception as e:  # noqa: BLE001
                logger.error("health check round crashed: %s", e)
                backoff = min(300.0, backoff * 2)
        logger.info("strategy health worker stopped")
