# -*- coding: utf-8 -*-
"""core.registry —— 策略注册表（Strategy Registry）。

基于第一性原理设计：
1. 每个策略版本都有完整快照（参数、性能、状态）
2. 上线前参数必须冻结，不允许热更新
3. 所有版本可追溯、可回滚
4. 决策可审计：每笔交易都能还原是哪个策略版本产生的

设计原则：
- 纯数据类，不依赖外部存储（文件/数据库由上层负责）
- 版本号语义化（MAJOR.MINOR.PATCH）
- 状态机严格：draft → backtest → paper → live → retired
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class StrategyStatus(Enum):
    """策略状态枚举（严格状态机）。"""
    DRAFT = "draft"            # 草稿：开发中，未测试
    BACKTEST = "backtest"      # 回测中：历史数据验证
    PAPER = "paper"            # 模拟盘：小资金模拟运行
    LIVE = "live"              # 实盘：真实资金运行
    PAUSED = "paused"          # 暂停：临时停止
    RETIRED = "retired"        # 退役：永久下线

    @classmethod
    def can_transition(cls, from_status: "StrategyStatus",
                       to_status: "StrategyStatus") -> bool:
        """状态转换是否合法。"""
        valid_transitions = {
            cls.DRAFT: {cls.BACKTEST},
            cls.BACKTEST: {cls.PAPER, cls.DRAFT, cls.RETIRED},
            cls.PAPER: {cls.LIVE, cls.BACKTEST, cls.RETIRED, cls.PAUSED},
            cls.PAUSED: {cls.PAPER, cls.LIVE, cls.RETIRED},
            cls.LIVE: {cls.PAUSED, cls.RETIRED},
            cls.RETIRED: set(),  # 退役是终态
        }
        return to_status in valid_transitions.get(from_status, set())


@dataclass
class PerformanceSnapshot:
    """策略性能快照（回测或实盘指标）。"""
    sharpe: float = 0.0              # 夏普比率
    sortino: float = 0.0             # 索提诺比率
    calmar: float = 0.0              # 卡玛比率
    max_drawdown: float = 0.0        # 最大回撤
    win_rate: float = 0.0            # 胜率
    profit_factor: float = 0.0       # 盈亏比
    total_trades: int = 0             # 总交易次数
    avg_r_multiple: float = 0.0       # 平均R倍数
    deflated_sharpe: float = 0.0     # 校正后夏普（考虑试验次数）
    pbo: float = 1.0                 # 过拟合概率（越低越好）
    evaluated_at: datetime = field(default_factory=datetime.now)


@dataclass
class StrategyVersion:
    """策略版本完整快照。

    不可协商的不变量：
    1. 参数一旦冻结（进入backtest及以后），不可修改
    2. 状态转换必须符合状态机规则
    3. 所有字段都必须可序列化（用于审计日志）
    """
    strategy_id: str                  # 策略唯一ID（如 "trend_breakout"）
    version: str                     # 版本号（如 "v1.2.0"）
    created_at: datetime             # 创建时间
    parameters: dict[str, Any]       # 完整参数快照
    status: StrategyStatus = StrategyStatus.DRAFT
    parent_version: str | None = None  # 基于哪个版本改的
    changelog: str = ""               # 改了什么
    performance: PerformanceSnapshot | None = None  # 性能指标
    description: str = ""             # 策略描述

    # 内部状态
    _frozen: bool = field(default=False, init=False, repr=False)

    def freeze_parameters(self) -> None:
        """冻结参数，进入不可修改状态。

        规则：只有 draft 状态可以冻结，冻结后参数不可修改。
        """
        if self.status != StrategyStatus.DRAFT:
            raise ValueError(f"只有 DRAFT 状态可以冻结参数，当前状态: {self.status.value}")
        self._frozen = True

    def update_status(self, new_status: StrategyStatus) -> None:
        """更新策略状态（严格状态机）。

        规则：
        - 只有合法的状态转换才允许
        - 进入 backtest 时自动冻结参数
        - 退役后不可恢复
        """
        if not StrategyStatus.can_transition(self.status, new_status):
            raise ValueError(
                f"非法状态转换: {self.status.value} → {new_status.value}\n"
                f"合法转换: {self._valid_next_statuses()}"
            )

        # 进入回测时自动冻结参数
        if new_status == StrategyStatus.BACKTEST and not self._frozen:
            self.freeze_parameters()

        self.status = new_status

    def _valid_next_statuses(self) -> list[str]:
        """返回当前状态的合法后续状态列表。"""
        valid = {
            StrategyStatus.DRAFT: ["backtest"],
            StrategyStatus.BACKTEST: ["paper", "draft", "retired"],
            StrategyStatus.PAPER: ["live", "backtest", "retired", "paused"],
            StrategyStatus.PAUSED: ["paper", "live", "retired"],
            StrategyStatus.LIVE: ["paused", "retired"],
            StrategyStatus.RETIRED: [],
        }
        return valid.get(self.status, [])

    def update_performance(self, perf: PerformanceSnapshot) -> None:
        """更新性能快照。

        规则：只有 backtest / paper / live 状态可以更新性能
        """
        if self.status not in (StrategyStatus.BACKTEST, StrategyStatus.PAPER, StrategyStatus.LIVE):
            raise ValueError(f"当前状态 {self.status.value} 不能更新性能")
        self.performance = perf

    def is_live(self) -> bool:
        """是否正在实盘运行。"""
        return self.status == StrategyStatus.LIVE

    def is_frozen(self) -> bool:
        """参数是否已冻结。"""
        return self._frozen

    def summary(self) -> dict[str, Any]:
        """返回摘要（用于日志和UI展示）。"""
        return {
            "strategy_id": self.strategy_id,
            "version": self.version,
            "status": self.status.value,
            "parameters_frozen": self._frozen,
            "created_at": self.created_at.isoformat(),
            "performance": self.performance.__dict__ if self.performance else None,
        }


class StrategyRegistry:
    """策略注册表（管理所有策略版本）。

    职责：
    1. 注册新策略版本
    2. 查询策略版本
    3. 版本对比
    4. 列出所有策略
    """

    def __init__(self):
        self._strategies: dict[str, StrategyVersion] = {}

    def register(self, strategy: StrategyVersion) -> None:
        """注册一个新策略版本。

        规则：strategy_id + version 必须唯一
        """
        key = f"{strategy.strategy_id}:{strategy.version}"
        if key in self._strategies:
            raise ValueError(f"策略版本已存在: {key}")
        self._strategies[key] = strategy

    def get(self, strategy_id: str, version: str) -> StrategyVersion | None:
        """获取指定策略版本。"""
        key = f"{strategy_id}:{version}"
        return self._strategies.get(key)

    def get_latest(self, strategy_id: str) -> StrategyVersion | None:
        """获取指定策略的最新版本。"""
        versions = [
            s for k, s in self._strategies.items()
            if s.strategy_id == strategy_id
        ]
        if not versions:
            return None
        # 按创建时间排序，取最新
        return max(versions, key=lambda s: s.created_at)

    def get_live(self) -> list[StrategyVersion]:
        """获取所有正在实盘运行的策略。"""
        return [s for s in self._strategies.values() if s.is_live()]

    def list_all(self) -> list[StrategyVersion]:
        """列出所有策略版本。"""
        return list(self._strategies.values())

    def list_by_status(self, status: StrategyStatus) -> list[StrategyVersion]:
        """按状态筛选策略。"""
        return [s for s in self._strategies.values() if s.status == status]

    def compare_versions(self, id1: str, v1: str, id2: str, v2: str) -> dict:
        """对比两个策略版本。

        Returns:
            对比结果：参数差异、性能差异、状态差异
        """
        s1 = self.get(id1, v1)
        s2 = self.get(id2, v2)
        if not s1 or not s2:
            raise ValueError("找不到指定的策略版本")

        # 参数差异
        param_diff = {}
        all_keys = set(s1.parameters.keys()) | set(s2.parameters.keys())
        for key in all_keys:
            v1_val = s1.parameters.get(key)
            v2_val = s2.parameters.get(key)
            if v1_val != v2_val:
                param_diff[key] = {"v1": v1_val, "v2": v2_val}

        # 性能差异
        perf_diff = {}
        if s1.performance and s2.performance:
            metrics = ["sharpe", "max_drawdown", "win_rate", "profit_factor"]
            for m in metrics:
                p1 = getattr(s1.performance, m, 0)
                p2 = getattr(s2.performance, m, 0)
                perf_diff[m] = {"v1": p1, "v2": p2, "delta": p2 - p1}

        return {
            "version1": s1.summary(),
            "version2": s2.summary(),
            "parameter_diff": param_diff,
            "performance_diff": perf_diff,
        }
