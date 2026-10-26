"""
Unified auto-stop for live strategies after fatal exchange/auth/connectivity errors.

Position sync and order workers call `auto_stop_live_strategy` so DB status, executor
threads, and runtime logs stay consistent (avoids endless retry spam after restart).
"""

from __future__ import annotations

import threading
from typing import Set

from app.utils.db import get_db_connection
from app.utils.logger import get_logger
from app.utils.strategy_runtime_logs import append_strategy_log

logger = get_logger(__name__)

_quiet_lock = threading.Lock()
_quiet_sids: Set[int] = set()


def is_fatal_exchange_error(msg: str) -> bool:
    """Return True when the strategy should not keep retrying exchange/private APIs."""
    m = (msg or "").lower()
    if not m:
        return False
    if "unsupported market type" in m or "unsupported market" in m:
        return True
    tokens = (
        "binance http 401",
        '"code":-2015',
        "-2015",
        "okx http 401",
        '"code":"50111"',
        "50111",
        "invalid api-key",
        "invalid api key",
        "invalid ok-access-key",
        "invalid ip",
        "invalid_ip",
        "40018",
        "permissions for action",
        "unauthorized",
        "forbidden",
        " http 401",
        "authentication",
        "signature mismatch",
        "invalid_signature",
        "permission denied",
        "connection refused",
        "connect call failed",
        "errno 111",
        "make sure api port on tws",
        "failed to connect to ibkr",
        "ibkr connection failed",
        "live trading error",
        "single-asset collateral mode is temporarily unavailable",
        "disabled ibkr",
        "已关闭 ibkr",
        "missing okx",
        "api_key/secret_key",
        "secret_key/passphrase",
        "missing api_key",
        "missing secret",
        "missing passphrase",
        "missing credential",
        "no credential",
        "exchange credential",
        "unsupported client for grid",
    )
    return any(t in m for t in tokens)


def maybe_auto_stop_on_exchange_error(
    strategy_id: int,
    msg: str,
    *,
    source: str = "exchange",
    consecutive_failures: int = 0,
    consecutive_threshold: int = 5,
) -> bool:
    """
    Stop a live strategy after a fatal exchange/auth error or repeated failures.
    Returns True if auto-stop was triggered (or already quieted for this run).
    """
    sid = int(strategy_id or 0)
    if sid <= 0:
        return False
    reason = (msg or "").strip()
    if not reason:
        return False
    if is_fatal_exchange_error(reason):
        auto_stop_live_strategy(sid, reason, source=source)
        return True
    if consecutive_failures >= max(1, int(consecutive_threshold or 5)):
        auto_stop_live_strategy(
            sid,
            f"Repeated exchange errors ({consecutive_failures}): {reason}",
            source=source,
        )
        return True
    return False


def should_skip_position_sync(strategy_id: int) -> bool:
    """In-process guard: skip sync for strategies already auto-stopped this run."""
    with _quiet_lock:
        return int(strategy_id) in _quiet_sids


def auto_stop_live_strategy(
    strategy_id: int,
    reason: str,
    *,
    source: str = "position_sync",
) -> bool:
    """
    Mark strategy stopped in DB, stop executor thread if running, append runtime log.
    Safe to call multiple times for the same strategy_id.
    """
    sid = int(strategy_id)
    if sid <= 0:
        return False

    reason = (reason or "").strip() or "fatal exchange error"
    with _quiet_lock:
        already = sid in _quiet_sids
        _quiet_sids.add(sid)
    if already:
        return True

    log_msg = f"Auto-stopped ({source}): {reason}"
    logger.error("[Strategy %s] %s", sid, log_msg)
    try:
        append_strategy_log(sid, "error", log_msg)
    except Exception:
        pass

    try:
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute(
                "UPDATE qd_strategies_trading SET status = 'stopped' WHERE id = %s",
                (sid,),
            )
            db.commit()
            cur.close()
    except Exception as e:
        logger.warning("auto_stop: DB update failed for strategy %s: %s", sid, e)

    try:
        from app import get_trading_executor

        get_trading_executor().stop_strategy(sid)
    except Exception as e:
        logger.debug("auto_stop: executor stop_strategy(%s): %s", sid, e)

    return True


# ============================================================
# 绩效衰减健康度评估（策略生命周期管理）
# 基于第一性原理：Alpha会衰减，必须自动发现、自动预警、自动减仓
# ============================================================

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Dict
from datetime import datetime


class HealthStatus(Enum):
    """三级健康度状态"""
    GREEN = "green"    # 健康运行
    YELLOW = "yellow"  # 预警，减仓
    RED = "red"        # 失效，退役


@dataclass
class StrategyPerformance:
    """策略绩效数据快照"""
    strategy_id: int
    strategy_name: str
    total_return: float          # 总收益率
    sharpe_ratio: float          # 夏普比率
    max_drawdown: float           # 历史最大回撤
    win_rate: float               # 胜率
    profit_factor: float          # 盈亏比
    trades_count: int             # 交易次数
    current_drawdown: float       # 当前回撤
    loss_streak: int              # 连续亏损次数


@dataclass
class HealthDecision:
    """健康度评估结果"""
    strategy_id: int
    strategy_name: str
    status: HealthStatus
    confidence: float             # 置信度 0-1
    reasons: List[str]            # 触发原因列表
    suggested_action: str         # 建议动作
    position_adjustment: float    # 仓位调整系数（1=满仓，0=清仓）
    timestamp: datetime


# 阈值配置（提前冻结，不允许根据结果调整）
HEALTH_THRESHOLDS = {
    'drawdown_yellow': 0.10,           # 回撤10%预警
    'drawdown_red': 0.20,              # 回撤20%退役
    'loss_streak_yellow': 5,           # 连续亏损5次预警
    'loss_streak_red': 10,             # 连续亏损10次退役
    'sharpe_decay_yellow': 0.4,        # 夏普衰减40%预警
    'min_trades_significant': 20,      # 统计显著性最小样本数
}


def evaluate_strategy_health(
    perf: StrategyPerformance,
    baseline_perf: Optional[StrategyPerformance] = None,
) -> HealthDecision:
    """
    评估策略健康状态
    多重指标交叉验证，每个指标独立判断，最后综合评分
    """
    reasons = []
    yellow_score = 0
    red_score = 0

    # 1. 回撤检查（最硬的指标）
    if perf.current_drawdown >= HEALTH_THRESHOLDS['drawdown_red']:
        red_score += 3
        reasons.append(f"当前回撤{perf.current_drawdown:.1%}超过20%红线")
    elif perf.current_drawdown >= HEALTH_THRESHOLDS['drawdown_yellow']:
        yellow_score += 2
        reasons.append(f"当前回撤{perf.current_drawdown:.1%}超过10%预警线")

    # 2. 连续亏损检查
    if perf.loss_streak >= HEALTH_THRESHOLDS['loss_streak_red']:
        red_score += 2
        reasons.append(f"连续亏损{perf.loss_streak}次，超过10次红线")
    elif perf.loss_streak >= HEALTH_THRESHOLDS['loss_streak_yellow']:
        yellow_score += 1
        reasons.append(f"连续亏损{perf.loss_streak}次，超过5次预警线")

    # 3. 夏普衰减检查（对比上线基线）
    if baseline_perf and baseline_perf.sharpe_ratio > 0:
        sharpe_drop = 1 - (perf.sharpe_ratio / baseline_perf.sharpe_ratio)
        if sharpe_drop >= HEALTH_THRESHOLDS['sharpe_decay_yellow']:
            yellow_score += 2
            reasons.append(
                f"夏普比率衰减{sharpe_drop:.1%}，"
                f"从{baseline_perf.sharpe_ratio:.2f}降到{perf.sharpe_ratio:.2f}"
            )

    # 4. 样本量检查（统计显著性）
    if perf.trades_count < HEALTH_THRESHOLDS['min_trades_significant']:
        yellow_score += 1
        reasons.append(f"交易样本只有{perf.trades_count}次，统计显著性不足")

    # 综合判断状态
    if red_score >= 3:
        status = HealthStatus.RED
        suggested_action = "立即清仓，停止开新仓，启动复盘"
        position_adjustment = 0.0
        confidence = min(red_score / 5, 1.0)
    elif red_score >= 1 or yellow_score >= 3:
        status = HealthStatus.YELLOW
        suggested_action = "减仓50%，加强监控，准备备选策略"
        position_adjustment = 0.5
        confidence = min((red_score + yellow_score) / 6, 1.0)
    else:
        status = HealthStatus.GREEN
        suggested_action = "正常运行"
        position_adjustment = 1.0
        confidence = 0.8

    return HealthDecision(
        strategy_id=perf.strategy_id,
        strategy_name=perf.strategy_name,
        status=status,
        confidence=confidence,
        reasons=reasons,
        suggested_action=suggested_action,
        position_adjustment=position_adjustment,
        timestamp=datetime.now(),
    )
