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
from typing import Optional


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
