# -*- coding: utf-8 -*-
"""core.risk.portfolio_risk —— 组合层面风控系统。

第一性原理：
- 单个策略的止损控制的是单笔交易的最大损失
- 但组合层面的风险是叠加的——如果多个策略同时亏钱，总回撤会超预期
- 风险不是简单相加，要考虑策略之间的相关性

核心能力：
1. 总风险敞口限制（所有策略的总风险预算）
2. 风险预算分配（每个策略最多承担多少风险）
3. 相关性调整（高相关策略要降权）
4. 组合回撤监控（组合层面的熔断）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StrategyRisk:
    """单个策略的风险参数。

    Attributes:
        strategy_id: 策略ID
        risk_per_trade: 单笔交易风险（占权益比例，如 0.01 = 1%）
        current_exposure: 当前持仓风险敞口（占权益比例）
        correlation_cluster: 相关性聚类编号
        daily_pnl: 当日盈亏（占权益比例）
    """
    strategy_id: str
    risk_per_trade: float = 0.01
    current_exposure: float = 0.0
    correlation_cluster: int = 0
    daily_pnl: float = 0.0


@dataclass
class PortfolioRiskConfig:
    """组合风控配置。所有阈值来自配置，不硬编码。

    Attributes:
        max_total_exposure: 最大总风险敞口（如 0.05 = 5%权益）
        max_exposure_per_cluster: 每个相关性聚类的最大敞口
        daily_loss_limit: 组合当日最大亏损（如 0.03 = 3%）
        max_strategies: 最大同时运行的策略数量
    """
    max_total_exposure: float = 0.05
    max_exposure_per_cluster: float = 0.03
    daily_loss_limit: float = 0.03
    max_strategies: int = 5


class PortfolioRiskManager:
    """组合层面风控管理器。

    设计原则：
    - 先检查总风险，再分配单个策略的额度
    - 高相关策略不能同时满仓
    - 组合级别的熔断优先级高于单个策略
    """

    def __init__(self, config: Optional[PortfolioRiskConfig] = None):
        self.config = config or PortfolioRiskConfig()
        self.strategies: dict[str, StrategyRisk] = {}
        self._equity: float = 100000.0  # 默认初始权益

    @property
    def equity(self) -> float:
        return self._equity

    def set_equity(self, equity: float) -> None:
        """设置当前权益。"""
        self._equity = float(equity)

    def add_strategy(self, risk: StrategyRisk) -> None:
        """注册一个策略到组合。"""
        self.strategies[risk.strategy_id] = risk

    def remove_strategy(self, strategy_id: str) -> None:
        """从组合移除一个策略。"""
        self.strategies.pop(strategy_id, None)

    def total_exposure(self) -> float:
        """计算总风险敞口（所有策略当前敞口之和）。"""
        return sum(s.current_exposure for s in self.strategies.values())

    def cluster_exposure(self, cluster: int) -> float:
        """计算某个相关性聚类的总敞口。"""
        return sum(
            s.current_exposure
            for s in self.strategies.values()
            if s.correlation_cluster == cluster
        )

    def total_daily_pnl(self) -> float:
        """计算组合当日总盈亏。"""
        return sum(s.daily_pnl for s in self.strategies.values())

    def can_open_new_position(self, strategy_id: str,
                              planned_risk: float) -> tuple[bool, str]:
        """判断某个策略能不能开新仓。

        从第一性原理出发：
        1. 先检查总敞口有没有超
        2. 再检查这个策略所在聚类的敞口有没有超
        3. 最后检查组合当日亏损有没有到熔断线

        Args:
            strategy_id: 要开仓的策略ID
            planned_risk: 计划承担的风险（占权益比例）

        Returns:
            (是否允许, 原因说明)
        """
        # 1. 检查组合当日熔断
        daily_pnl = self.total_daily_pnl()
        if daily_pnl <= -self.config.daily_loss_limit:
            return False, f"组合当日亏损 {daily_pnl:.2%} 已达熔断线 {self.config.daily_loss_limit:.2%}"

        # 2. 检查策略数量
        if len(self.strategies) >= self.config.max_strategies:
            return False, f"策略数量 {len(self.strategies)} 已达上限 {self.config.max_strategies}"

        # 3. 检查总敞口
        current_total = self.total_exposure()
        if current_total + planned_risk > self.config.max_total_exposure:
            return False, (
                f"总敞口 {current_total:.2%} + 新增 {planned_risk:.2%} "
                f"将超过上限 {self.config.max_total_exposure:.2%}"
            )

        # 4. 检查聚类敞口
        strategy = self.strategies.get(strategy_id)
        if strategy:
            cluster = strategy.correlation_cluster
            cluster_exp = self.cluster_exposure(cluster)
            if cluster_exp + planned_risk > self.config.max_exposure_per_cluster:
                return False, (
                    f"聚类 {cluster} 敞口 {cluster_exp:.2%} + 新增 {planned_risk:.2%} "
                    f"将超过上限 {self.config.max_exposure_per_cluster:.2%}"
                )

        return True, "允许开仓"

    def risk_report(self) -> dict:
        """生成组合风险报告。"""
        return {
            "equity": self._equity,
            "total_exposure": self.total_exposure(),
            "total_daily_pnl": self.total_daily_pnl(),
            "strategy_count": len(self.strategies),
            "config": {
                "max_total_exposure": self.config.max_total_exposure,
                "max_exposure_per_cluster": self.config.max_exposure_per_cluster,
                "daily_loss_limit": self.config.daily_loss_limit,
                "max_strategies": self.config.max_strategies,
            },
            "strategies": [
                {
                    "id": s.strategy_id,
                    "exposure": s.current_exposure,
                    "cluster": s.correlation_cluster,
                    "daily_pnl": s.daily_pnl,
                }
                for s in self.strategies.values()
            ],
        }
