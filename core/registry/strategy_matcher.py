# -*- coding: utf-8 -*-
"""core.registry.strategy_matcher —— 策略自动匹配系统。

基于第一性原理：没有万能策略——不同市场状态适合不同策略。
本模块根据市场状态自动选择最合适的策略组合，并带防抖动机制。

核心逻辑：
1. 每个策略有适用市场状态画像（best/worst regimes）
2. 匹配得分 = 适配度 × 风险调整后收益 × 市场强度因子
3. 防抖动：切换阈值，避免频繁切换策略
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ------------------------------------------------------------------
# 数据类
# ------------------------------------------------------------------
@dataclass
class StrategyProfile:
    """策略档案：描述一个策略的特性。

    Attributes:
        name: 策略名称
        best_regimes: 最适合的市场状态列表（trending/ranging/volatile/quiet）
        worst_regimes: 最不适合的市场状态列表
        preferred_volatility: 偏好的波动率环境（low/medium/high）
        expected_sharpe: 预期 Sharpe（历史回测或实盘）
        max_drawdown: 最大回撤（历史）
        risk_level: 风险等级（1-5）
        correlation_cluster: 相关性聚类编号（用于组合分散化）
    """
    name: str
    best_regimes: list[str]
    worst_regimes: list[str]
    expected_sharpe: float
    max_drawdown: float
    risk_level: int = 3
    preferred_volatility: str = "medium"
    correlation_cluster: int = 0

    def __repr__(self):
        return f"StrategyProfile({self.name}, SR={self.expected_sharpe:.2f})"


@dataclass
class MarketRegime:
    """当前市场状态。

    Attributes:
        regime_type: 市场状态类型（trending/ranging/volatile/quiet）
        strength: 状态强度（0-1）
        volatility: 波动率水平（low/medium/high）
        trend_direction: 趋势方向（up/down/flat）
    """
    regime_type: str
    strength: float = 0.5
    volatility: str = "medium"
    trend_direction: str = "flat"

    def __repr__(self):
        return f"MarketRegime({self.regime_type}, strength={self.strength:.2f})"


@dataclass
class StrategyScore:
    """策略匹配得分。"""
    profile: StrategyProfile
    score: float
    rank: int = 0

    def __repr__(self):
        return f"StrategyScore({self.profile.name}, score={self.score:.3f})"


# ------------------------------------------------------------------
# 策略匹配器
# ------------------------------------------------------------------
class StrategyMatcher:
    """策略自动匹配器。

    根据市场状态，给所有策略打分排序，选出最合适的策略。

    Attributes:
        strategies: 策略列表
        switch_threshold: 切换阈值（防抖动）
            新策略得分必须比当前策略高 threshold 才切换
    """

    def __init__(self, strategies: list[StrategyProfile],
                 switch_threshold: float = 0.15):
        self.strategies = strategies
        self.switch_threshold = switch_threshold

    def _calc_fit_score(self, strategy: StrategyProfile,
                        market: MarketRegime) -> float:
        """计算策略与市场状态的适配度（0-1）。

        从第一性原理出发：适配度 = 状态类型匹配 × 波动率匹配
        - 状态类型：趋势/震荡/波动/平静，权重 0.7
        - 波动率匹配：策略偏好的波动率和市场实际波动率，权重 0.3
        """
        regime = market.regime_type

        # 状态类型适配度（0-1）
        if regime in strategy.best_regimes:
            regime_fit = 0.8 + 0.2 * market.strength
        elif regime in strategy.worst_regimes:
            regime_fit = 0.1
        else:
            regime_fit = 0.4

        # 波动率适配度（0-1）
        vol_map = {"low": 0.0, "medium": 0.5, "high": 1.0}
        strategy_vol = vol_map.get(strategy.preferred_volatility, 0.5)
        market_vol = vol_map.get(market.volatility, 0.5)
        vol_distance = abs(strategy_vol - market_vol)
        vol_fit = 1.0 - vol_distance  # 距离越近，匹配越好

        # 综合：状态类型权重 0.7，波动率权重 0.3
        total_fit = 0.7 * regime_fit + 0.3 * vol_fit

        return total_fit

    def _calc_risk_adjusted_return(self, strategy: StrategyProfile,
                                    market: MarketRegime) -> float:
        """计算风险调整后收益。

        市场强度越高，越偏好高 Sharpe 策略；
        市场越不稳定，越偏好低回撤策略。
        """
        # Sharpe 因子：归一化到 0-1
        sharpe_factor = min(strategy.expected_sharpe / 2.0, 1.0)

        # 回撤因子：回撤越小越好
        dd_factor = 1.0 - min(strategy.max_drawdown / 0.3, 1.0)

        # 市场强度调节：高强度市场偏好高 Sharpe，低强度偏好低回撤
        strength = market.strength
        risk_adjusted = (
            strength * sharpe_factor +
            (1 - strength) * dd_factor
        )

        return risk_adjusted

    def rank(self, market: MarketRegime,
             current_strategy: Optional[str] = None) -> list[StrategyScore]:
        """根据市场状态给所有策略排名。

        Args:
            market: 当前市场状态
            current_strategy: 当前持有的策略名称（用于防抖动）

        Returns:
            策略得分列表（按得分降序）
        """
        scores = []

        for strategy in self.strategies:
            # 适配度
            fit = self._calc_fit_score(strategy, market)

            # 风险调整后收益
            rar = self._calc_risk_adjusted_return(strategy, market)

            # 综合得分 = 0.6 × 适配度 + 0.4 × 风险调整收益
            total_score = 0.6 * fit + 0.4 * rar

            # 防抖动：当前持有策略加 bias
            if current_strategy and strategy.name == current_strategy:
                total_score += self.switch_threshold

            scores.append(StrategyScore(profile=strategy, score=total_score))

        # 按得分降序排序
        scores.sort(key=lambda s: s.score, reverse=True)

        # 排名
        for i, s in enumerate(scores):
            s.rank = i + 1

        return scores

    def select(self, market: MarketRegime,
               current_strategy: Optional[str] = None) -> StrategyProfile:
        """选择最合适的策略。

        带防抖动机制：新策略必须比当前策略好 threshold 才切换。
        """
        rankings = self.rank(market, current_strategy)
        best = rankings[0]

        # 如果有当前策略，检查是否需要切换
        if current_strategy:
            current_rank = next(
                (s for s in rankings if s.profile.name == current_strategy),
                None
            )
            if current_rank:
                # 只有当新策略明显更好时才切换
                if best.score - current_rank.score < self.switch_threshold:
                    return current_rank.profile

        return best.profile

    def select_portfolio(self, market: MarketRegime,
                         top_n: int = 3,
                         max_per_cluster: int = 1) -> list[StrategyProfile]:
        """选择策略组合（带分散化）。

        从第一性原理出发：分散化是唯一的免费午餐。
        选 top N 策略，但每个相关性聚类最多选 max_per_cluster 个，
        避免伪分散（一堆策略其实是同一个风险因子）。

        Args:
            market: 当前市场状态
            top_n: 选几个策略
            max_per_cluster: 每个聚类最多选几个

        Returns:
            选出的策略列表（按得分降序）
        """
        rankings = self.rank(market)
        selected = []
        cluster_counts: dict[int, int] = {}

        for score in rankings:
            cluster = score.profile.correlation_cluster
            # 这个聚类还没选满
            if cluster_counts.get(cluster, 0) < max_per_cluster:
                selected.append(score.profile)
                cluster_counts[cluster] = cluster_counts.get(cluster, 0) + 1
                # 选够了就停
                if len(selected) >= top_n:
                    break

        return selected


# ------------------------------------------------------------------
# 便捷函数
# ------------------------------------------------------------------
def match_strategies(strategies: list[StrategyProfile],
                     market: MarketRegime,
                     current: Optional[str] = None) -> list[StrategyScore]:
    """便捷函数：一行调用策略匹配。"""
    matcher = StrategyMatcher(strategies)
    return matcher.rank(market, current_strategy=current)
