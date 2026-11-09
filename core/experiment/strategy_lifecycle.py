# -*- coding: utf-8 -*-
"""core/experiment/strategy_lifecycle.py —— 策略生命周期管理。

基于第一性原理：
    策略不是回测好就直接上实盘的。它有完整的生命周期：
    研究 → 回测 → AB测试 → 小资金灰度 → 全量上线 → 监控 → 退役

    每一步都有明确的进入和退出标准，不能跳步。

核心状态机：
    DRAFT → BACKTESTING → AB_TESTING → PAPER_TRADING → LIVE_SMALL → LIVE_FULL → MONITORING → RETIRED
              ↓           ↓             ↓              ↓             ↓
            REJECTED    REJECTED      REJECTED       REJECTED     REJECTED
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Sequence
import math


def _finite(name: str, val: float) -> float:
    if not isinstance(val, (int, float)) or isinstance(val, bool) \
            or not math.isfinite(val):
        raise ValueError(f"{name} 必须为有限数值，收到 {val!r}")
    return float(val)


def _as_int(name: str, val: int) -> int:
    if isinstance(val, bool) or not isinstance(val, int):
        raise ValueError(f"{name} 必须为整数，收到 {val!r}")
    return val


def _positive_finite(name: str, val: float) -> float:
    val = _finite(name, val)
    if val <= 0:
        raise ValueError(f"{name} 必须 > 0，收到 {val!r}")
    return val


def _nonneg_finite(name: str, val: float) -> float:
    val = _finite(name, val)
    if val < 0:
        raise ValueError(f"{name} 必须 >= 0，收到 {val!r}")
    return val


def _ratio(name: str, val: float, *, lo: float, hi: float,
           closed_lo: bool = True, closed_hi: bool = True) -> float:
    val = _finite(name, val)
    if ((closed_lo and val < lo) or (not closed_lo and val <= lo)
            or (closed_hi and val > hi) or (not closed_hi and val >= hi)):
        raise ValueError(f"{name} 必须位于 [{lo}, {hi}] 区间，收到 {val!r}")
    return val


# ------------------------------------------------------------------
# 状态枚举
# ------------------------------------------------------------------
class StrategyState(Enum):
    """策略生命周期状态。"""
    DRAFT = "draft"                    # 草稿阶段
    BACKTESTING = "backtesting"        # 回测中
    AB_TESTING = "ab_testing"          # AB测试中
    PAPER_TRADING = "paper_trading"    # 模拟交易
    LIVE_SMALL = "live_small"          # 小资金实盘
    LIVE_FULL = "live_full"            # 全量实盘
    MONITORING = "monitoring"          # 监控中
    RETIRED = "retired"                # 已退役
    REJECTED = "rejected"              # 已否决


# 合法的状态转移
VALID_TRANSITIONS: dict[StrategyState, list[StrategyState]] = {
    StrategyState.DRAFT: [StrategyState.BACKTESTING, StrategyState.REJECTED],
    StrategyState.BACKTESTING: [StrategyState.AB_TESTING, StrategyState.REJECTED],
    StrategyState.AB_TESTING: [StrategyState.PAPER_TRADING, StrategyState.REJECTED],
    StrategyState.PAPER_TRADING: [StrategyState.LIVE_SMALL, StrategyState.REJECTED],
    StrategyState.LIVE_SMALL: [StrategyState.LIVE_FULL, StrategyState.REJECTED, StrategyState.MONITORING],
    StrategyState.LIVE_FULL: [StrategyState.MONITORING, StrategyState.RETIRED],
    StrategyState.MONITORING: [StrategyState.LIVE_FULL, StrategyState.RETIRED],
    StrategyState.RETIRED: [],
    StrategyState.REJECTED: [],
}


# ------------------------------------------------------------------
# 数据类
# ------------------------------------------------------------------
@dataclass
class LifecycleEvent:
    """生命周期事件记录（审计用）。"""
    timestamp: datetime
    from_state: StrategyState
    to_state: StrategyState
    reason: str
    metrics: dict = field(default_factory=dict)


@dataclass
class StrategyLifecycle:
    """策略生命周期管理器。

    用法：
        lifecycle = StrategyLifecycle("trend_v2")
        lifecycle.transition_to(StrategyState.BACKTESTING, "完成研究")
        lifecycle.transition_to(StrategyState.AB_TESTING, "回测Sharpe=1.5")
    """
    strategy_name: str
    current_state: StrategyState = StrategyState.DRAFT
    events: list[LifecycleEvent] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        # 记录初始事件
        self.events.append(LifecycleEvent(
            timestamp=datetime.now(),
            from_state=None,
            to_state=self.current_state,
            reason="策略创建",
        ))

    def can_transition_to(self, target: StrategyState) -> bool:
        """检查是否可以转移到目标状态。"""
        allowed = VALID_TRANSITIONS.get(self.current_state, [])
        return target in allowed

    def transition_to(self, target: StrategyState, reason: str,
                       metrics: Optional[dict] = None) -> bool:
        """转移到新状态。

        Args:
            target: 目标状态
            reason: 转移原因（审计用）
            metrics: 相关指标

        Returns:
            是否成功转移
        """
        if not self.can_transition_to(target):
            raise ValueError(
                f"非法状态转移：{self.current_state.value} → {target.value}。"
                f"允许的转移：{[s.value for s in VALID_TRANSITIONS.get(self.current_state, [])]}"
            )

        old_state = self.current_state
        self.current_state = target

        self.events.append(LifecycleEvent(
            timestamp=datetime.now(),
            from_state=old_state,
            to_state=target,
            reason=reason,
            metrics=metrics or {},
        ))

        return True

    def get_audit_trail(self) -> list[dict]:
        """获取完整审计轨迹。"""
        return [
            {
                "timestamp": e.timestamp.isoformat(),
                "from": e.from_state.value if e.from_state else "none",
                "to": e.to_state.value,
                "reason": e.reason,
                "metrics": e.metrics,
            }
            for e in self.events
        ]

    def is_live(self) -> bool:
        """是否在实盘交易中。"""
        return self.current_state in [StrategyState.LIVE_SMALL, StrategyState.LIVE_FULL]

    def is_active(self) -> bool:
        """是否活跃（非退役/否决）。"""
        return self.current_state not in [StrategyState.RETIRED, StrategyState.REJECTED]


# ------------------------------------------------------------------
# 上线标准检查器
# ------------------------------------------------------------------
@dataclass
class LaunchCriteria:
    """上线标准（实验前冻结，不可更改）。"""
    min_sharpe: float = 1.0              # 最低Sharpe
    max_drawdown: float = 0.20           # 最大回撤上限
    min_trades: int = 30                 # 最少交易笔数
    ab_test_significance: float = 0.05  # AB测试显著性
    max_overfitting_score: float = 0.3   # 过拟合评分上限
    min_live_days: int = 7               # 最少模拟交易日

    def __post_init__(self) -> None:
        self.min_sharpe = _positive_finite("min_sharpe", self.min_sharpe)
        self.max_drawdown = _positive_finite("max_drawdown", self.max_drawdown)
        self.min_trades = _as_int("min_trades", self.min_trades)
        if self.min_trades < 1:
            raise ValueError(f"min_trades 必须 >= 1，收到 {self.min_trades}")
        self.ab_test_significance = _ratio(
            "ab_test_significance", self.ab_test_significance,
            lo=0.0, hi=1.0, closed_lo=False, closed_hi=False)
        self.max_overfitting_score = _ratio(
            "max_overfitting_score", self.max_overfitting_score,
            lo=0.0, hi=1.0)
        self.min_live_days = _as_int("min_live_days", self.min_live_days)
        if self.min_live_days < 1:
            raise ValueError(f"min_live_days 必须 >= 1，收到 {self.min_live_days}")


class LaunchGate:
    """上线闸门——检查策略是否满足上线标准。

    基于第一性原理：每一步都有明确的门槛，
    不达标就不能进入下一步，不能"差不多就上"。
    """

    def __init__(self, criteria: Optional[LaunchCriteria] = None):
        self.criteria = criteria or LaunchCriteria()

    def check_backtest_ready(self, sharpe: float, max_dd: float,
                              n_trades: int) -> tuple[bool, list[str]]:
        """检查是否可以进入AB测试。"""
        issues = []

        if sharpe < self.criteria.min_sharpe:
            issues.append(f"Sharpe={sharpe:.2f} < {self.criteria.min_sharpe}")

        if max_dd > self.criteria.max_drawdown:
            issues.append(f"最大回撤={max_dd:.2%} > {self.criteria.max_drawdown:.0%}")

        if n_trades < self.criteria.min_trades:
            issues.append(f"交易笔数={n_trades} < {self.criteria.min_trades}")

        return len(issues) == 0, issues

    def check_ab_test_passed(self, ab_conclusion: str,
                               overfitting_score: float) -> tuple[bool, list[str]]:
        """检查AB测试是否通过。"""
        issues = []

        if ab_conclusion != "launch":
            issues.append(f"AB测试结论={ab_conclusion}，不是launch")

        if overfitting_score > self.criteria.max_overfitting_score:
            issues.append(f"过拟合评分={overfitting_score:.2f} > {self.criteria.max_overfitting_score}")

        return len(issues) == 0, issues

    def check_paper_trading_ready(self, paper_days: int,
                                     paper_sharpe: float) -> tuple[bool, list[str]]:
        """检查模拟交易是否达标。"""
        issues = []

        if paper_days < self.criteria.min_live_days:
            issues.append(f"模拟天数={paper_days} < {self.criteria.min_live_days}")

        if paper_sharpe < self.criteria.min_sharpe * 0.8:  # 实盘可以打8折
            issues.append(f"模拟Sharpe={paper_sharpe:.2f} < 回测的80%")

        return len(issues) == 0, issues


# ------------------------------------------------------------------
# 八阶段映射（发现→验证→小资金→规模化→拥挤→衰减→退役→复盘）
#
# 前七个阶段由状态机承载；"拥挤/衰减"是监控期内的判定结论（见下方纯判定
# 函数），"复盘"是退役后的 post-mortem 动作，不落状态机。
# ------------------------------------------------------------------
LIFECYCLE_STAGES: tuple[str, ...] = (
    "discovery", "validation", "small_capital", "scale",
    "crowding", "decay", "retired", "post_mortem",
)

STATE_TO_STAGE: dict[StrategyState, str] = {
    StrategyState.DRAFT: "discovery",
    StrategyState.BACKTESTING: "validation",
    StrategyState.AB_TESTING: "validation",
    StrategyState.PAPER_TRADING: "small_capital",
    StrategyState.LIVE_SMALL: "small_capital",
    StrategyState.LIVE_FULL: "scale",
    StrategyState.MONITORING: "decay",
    StrategyState.RETIRED: "retired",
    StrategyState.REJECTED: "validation",
}


def stage_of_state(state: StrategyState) -> str:
    """状态机状态 → 八阶段标签；未映射时抛 KeyError（显式而非兜底静默）。"""
    return STATE_TO_STAGE[state]


# ------------------------------------------------------------------
# 原因码（纯枚举，供审计轨迹与退役建议引用）
# ------------------------------------------------------------------
class CrowdReason(str, Enum):
    """拥挤判定原因码。"""
    CAPACITY_LIMIT = "crowd_capacity_limit"        # 容量利用率触顶
    FILL_RATE_DROP = "crowd_fill_rate_drop"       # 成交率下滑
    SLIPPAGE_RISE = "crowd_slippage_rise"         # 滑点上升
    PEER_CORR_HIGH = "crowd_peer_corr_high"       # 与同类策略相关性过高


class DecayReason(str, Enum):
    """衰减判定原因码。"""
    SHARPE_DOWN = "decay_sharpe_down"             # Sharpe 相对基准下滑
    WINRATE_DOWN = "decay_winrate_down"           # 胜率相对基准下滑
    EXPECTANCY_DOWN = "decay_expectancy_down"     # 期望值转负/过低
    DRAWDOWN_EXCESS = "decay_drawdown_excess"     # 回撤突破上限


class RetireReason(str, Enum):
    """退役建议原因码。"""
    BREACH_RISK_LIMIT = "retire_breach_risk_limit"   # 突破风控上限
    STRUCTURAL_BREAK = "retire_structural_break"     # 市场结构突变
    CAPACITY_EXHAUSTED = "retire_capacity_exhausted" # 容量耗尽
    PROLONGED_DECAY = "retire_prolonged_decay"       # 持续衰减且样本充分
    PERSISTENT_RED = "retire_persistent_red"         # 连续 N 期红灯持续性触发
    VOLUNTARY = "retire_voluntary"                    # 主动退役


@dataclass(frozen=True)
class WatchThresholds:
    """监控期阈值（调用方在实验前冻结传入；函数内不做绩效网格搜索）。"""
    # 拥挤口径
    min_fill_rate: float = 0.90
    max_slippage_bps: float = 5.0
    max_capacity_util: float = 0.80
    max_peer_corr: float = 0.70
    # 衰减口径
    min_sharpe_ratio: float = 0.60      # current / baseline 下限
    min_winrate_ratio: float = 0.85    # current / baseline 下限
    min_expectancy: float = 0.0
    max_drawdown: float = 0.25
    min_trades_for_decay: int = 20      # 判定持续衰减所需最少样本

    def __post_init__(self) -> None:
        _ratio("min_fill_rate", self.min_fill_rate, lo=0.0, hi=1.0)
        _nonneg_finite("max_slippage_bps", self.max_slippage_bps)
        _ratio("max_capacity_util", self.max_capacity_util, lo=0.0, hi=1.0)
        _ratio("max_peer_corr", self.max_peer_corr, lo=0.0, hi=1.0)
        _ratio("min_sharpe_ratio", self.min_sharpe_ratio, lo=0.0, hi=1.0)
        _ratio("min_winrate_ratio", self.min_winrate_ratio, lo=0.0, hi=1.0)
        _finite("min_expectancy", self.min_expectancy)
        _positive_finite("max_drawdown", self.max_drawdown)
        n = _as_int("min_trades_for_decay", self.min_trades_for_decay)
        if n < 1:
            raise ValueError(f"min_trades_for_decay 必须 >= 1，收到 {n}")


@dataclass(frozen=True)
class CrowdingReport:
    """拥挤判定报告（纯数据）。"""
    crowded: bool
    reasons: list[str]
    flags: dict[str, float]

    def to_dict(self) -> dict:
        return {"crowded": self.crowded, "reasons": list(self.reasons),
                "flags": dict(self.flags)}


@dataclass(frozen=True)
class DecayReport:
    """衰减判定报告（纯数据）。"""
    decayed: bool
    reasons: list[str]
    flags: dict[str, float]

    def to_dict(self) -> dict:
        return {"decayed": self.decayed, "reasons": list(self.reasons),
                "flags": dict(self.flags)}


@dataclass(frozen=True)
class PersistenceReport:
    """信号持续性报告（纯数据）：尾部连续红灯期数是否达到阈值 N。"""
    persistent: bool
    consecutive_count: int
    min_consecutive: int
    flags: dict[str, float]

    def to_dict(self) -> dict:
        return {"persistent": self.persistent,
                "consecutive_count": self.consecutive_count,
                "min_consecutive": self.min_consecutive,
                "flags": dict(self.flags)}


@dataclass(frozen=True)
class RetirementRecommendation:
    """退役建议：retire / watch / keep + 原因码 + 观测快照。"""
    recommendation: str
    reasons: list[str]
    flags: dict[str, float]

    def to_dict(self) -> dict:
        return {"recommendation": self.recommendation,
                "reasons": list(self.reasons), "flags": dict(self.flags)}


def _metric(metrics: dict, key: str) -> Optional[float]:
    value = metrics.get(key)
    return None if value is None else float(value)


def assess_crowding(metrics: dict,
                    thresholds: WatchThresholds) -> CrowdingReport:
    """纯判定：当前容量/成交/滑点/同业相关性是否进入拥挤区间。

    Args:
        metrics: fill_rate / slippage_bps / capacity_util / peer_corr，
            缺键则该维度跳过判定。
        thresholds: 冻结阈值。
    """
    reasons: list[str] = []
    flags: dict[str, float] = {}

    fill_rate = _metric(metrics, "fill_rate")
    if fill_rate is not None:
        flags["fill_rate"] = fill_rate
        if fill_rate < thresholds.min_fill_rate:
            reasons.append(CrowdReason.FILL_RATE_DROP.value)

    slippage = _metric(metrics, "slippage_bps")
    if slippage is not None:
        flags["slippage_bps"] = slippage
        if slippage > thresholds.max_slippage_bps:
            reasons.append(CrowdReason.SLIPPAGE_RISE.value)

    capacity = _metric(metrics, "capacity_util")
    if capacity is not None:
        flags["capacity_util"] = capacity
        if capacity > thresholds.max_capacity_util:
            reasons.append(CrowdReason.CAPACITY_LIMIT.value)

    peer_corr = _metric(metrics, "peer_corr")
    if peer_corr is not None:
        flags["peer_corr"] = peer_corr
        if peer_corr > thresholds.max_peer_corr:
            reasons.append(CrowdReason.PEER_CORR_HIGH.value)

    return CrowdingReport(crowded=bool(reasons), reasons=reasons, flags=flags)


def assess_decay(metrics: dict,
                 thresholds: WatchThresholds) -> DecayReport:
    """纯判定：当前绩效相对基准是否出现衰减信号。

    Args:
        metrics: current_sharpe / baseline_sharpe / current_win_rate /
            baseline_win_rate / current_expectancy / current_max_drawdown /
            n_trades；缺键则该维度跳过判定。
        thresholds: 冻结阈值。
    """
    reasons: list[str] = []
    flags: dict[str, float] = {}

    cur_sharpe = _metric(metrics, "current_sharpe")
    base_sharpe = _metric(metrics, "baseline_sharpe")
    if cur_sharpe is not None and base_sharpe and base_sharpe > 0:
        ratio = cur_sharpe / base_sharpe
        flags["sharpe_ratio"] = ratio
        if ratio < thresholds.min_sharpe_ratio:
            reasons.append(DecayReason.SHARPE_DOWN.value)

    cur_wr = _metric(metrics, "current_win_rate")
    base_wr = _metric(metrics, "baseline_win_rate")
    if cur_wr is not None and base_wr and base_wr > 0:
        wr_ratio = cur_wr / base_wr
        flags["winrate_ratio"] = wr_ratio
        if wr_ratio < thresholds.min_winrate_ratio:
            reasons.append(DecayReason.WINRATE_DOWN.value)

    expectancy = _metric(metrics, "current_expectancy")
    n_trades = metrics.get("n_trades")
    n_trades = int(n_trades) if n_trades is not None else 0
    if expectancy is not None:
        flags["current_expectancy"] = expectancy
        if expectancy < thresholds.min_expectancy:
            reasons.append(DecayReason.EXPECTANCY_DOWN.value)

    max_dd = _metric(metrics, "current_max_drawdown")
    if max_dd is not None:
        flags["current_max_drawdown"] = max_dd
        if max_dd > thresholds.max_drawdown:
            reasons.append(DecayReason.DRAWDOWN_EXCESS.value)

    flags["n_trades"] = float(n_trades)
    return DecayReport(decayed=bool(reasons), reasons=reasons, flags=flags)


def assess_persistence(red_flags: Sequence[bool],
                        min_consecutive: int) -> PersistenceReport:
    """纯判定：尾部连续红灯期数是否达到阈值 N（蓝图 G9 持续性）。

    单期红灯只是波动信号；连续 N 期红灯才构成持续性衰减/拥挤依据。
    ``red_flags`` 按时间从旧到新排列，计数取尾部（最近一期向前回溯）连续 True。

    Args:
        red_flags: 各期红灯标志（True=当期触发衰减/拥挤信号）。
        min_consecutive: 触发持续性所需最少连续期数（正整数，调用方冻结传入）。
    """
    n = _as_int("min_consecutive", min_consecutive)
    if n < 1:
        raise ValueError(f"min_consecutive 必须 >= 1，收到 {n}")
    if not isinstance(red_flags, Sequence):
        raise ValueError("red_flags 必须为序列")
    flags = [bool(x) for x in red_flags]
    count = 0
    for f in reversed(flags):
        if f:
            count += 1
        else:
            break
    persistent = count >= n
    return PersistenceReport(
        persistent=persistent,
        consecutive_count=count,
        min_consecutive=n,
        flags={"consecutive_count": float(count),
               "min_consecutive": float(n)},
    )


def recommend_retirement(decay: DecayReport, crowd: CrowdingReport,
                         metrics: dict,
                         thresholds: WatchThresholds,
                         persistence: Optional[PersistenceReport] = None
                         ) -> RetirementRecommendation:
    """纯判定：综合衰减/拥挤/风控信号给出 keep / watch / retire 建议。

    - retire：硬 breaches（风控上限、结构突变、容量耗尽、持续衰减且样本充分、
      连续 N 期红灯持续性触发）。
    - watch：出现软信号但未触发硬 breach。
    - keep：无显著信号。

    阈值全部由 ``thresholds`` 传入；本函数不读取 DB、不做参数寻优。
    """
    reasons: list[str] = []
    hard_breach = False

    # 风控上限突破（硬）
    if DecayReason.DRAWDOWN_EXCESS.value in decay.reasons:
        reasons.append(RetireReason.BREACH_RISK_LIMIT.value)
        hard_breach = True

    # 市场结构突变（硬，调用方显式标记）
    if bool(metrics.get("structural_break", False)):
        reasons.append(RetireReason.STRUCTURAL_BREAK.value)
        hard_breach = True

    # 容量耗尽（硬）
    if CrowdReason.CAPACITY_LIMIT.value in crowd.reasons:
        reasons.append(RetireReason.CAPACITY_EXHAUSTED.value)
        hard_breach = True

    # 持续衰减且样本充分（硬）
    n_trades = int(metrics.get("n_trades", 0) or 0)
    expectancy = _metric(metrics, "current_expectancy")
    if (decay.decayed and n_trades >= thresholds.min_trades_for_decay
            and expectancy is not None and expectancy < thresholds.min_expectancy):
        reasons.append(RetireReason.PROLONGED_DECAY.value)
        hard_breach = True

    # 主动退役（硬，调用方显式标记）
    if bool(metrics.get("voluntary_retire", False)):
        reasons.append(RetireReason.VOLUNTARY.value)
        hard_breach = True

    # 连续 N 期红灯持续性触发（硬，可选接入；当期仍处衰减态才成立）
    if persistence is not None and persistence.persistent and decay.decayed:
        reasons.append(RetireReason.PERSISTENT_RED.value)
        hard_breach = True

    if hard_breach:
        recommendation = "retire"
    elif decay.decayed or crowd.crowded or reasons:
        recommendation = "watch"
    else:
        recommendation = "keep"

    flags = {**decay.flags, **crowd.flags,
             "n_trades": float(n_trades),
             "hard_breach": 1.0 if hard_breach else 0.0}
    if persistence is not None:
        flags["persistent_red"] = 1.0 if persistence.persistent else 0.0
        flags["consecutive_red"] = float(persistence.consecutive_count)

    return RetirementRecommendation(
        recommendation=recommendation, reasons=reasons, flags=flags)

