# -*- coding: utf-8 -*-
"""tests.test_registry.test_strategy_matcher —— 策略自动匹配测试。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.registry.strategy_matcher import (
    StrategyProfile,
    MarketRegime,
    StrategyMatcher,
    match_strategies,
)
# ------------------------------------------------------------------
# 策略档案
# ------------------------------------------------------------------
class TestStrategyProfile:
    def test_profile_creation(self):
        """创建策略档案。"""
        profile = StrategyProfile(
            name="trend_following",
            best_regimes=["trending"],
            worst_regimes=["ranging"],
            expected_sharpe=1.5,
            max_drawdown=0.15,
        )
        assert profile.name == "trend_following"
        assert "trending" in profile.best_regimes


# ------------------------------------------------------------------
# 市场状态
# ------------------------------------------------------------------
class TestMarketRegime:
    def test_regime_creation(self):
        """创建市场状态。"""
        regime = MarketRegime(
            regime_type="trending",
            strength=0.8,
            volatility="medium",
        )
        assert regime.regime_type == "trending"
        assert regime.strength == 0.8


# ------------------------------------------------------------------
# 策略匹配器
# ------------------------------------------------------------------
class TestStrategyMatcher:
    def test_match_trend_strategy_in_trending_market(self):
        """趋势策略在趋势市场应该排名靠前。"""
        strategies = [
            StrategyProfile("trend_following", ["trending"], ["ranging"], 1.5, 0.15),
            StrategyProfile("mean_reversion", ["ranging"], ["trending"], 1.2, 0.10),
            StrategyProfile("breakout", ["trending", "volatile"], ["low_vol"], 1.3, 0.20),
        ]
        
        market = MarketRegime("trending", strength=0.8, volatility="medium")
        
        matcher = StrategyMatcher(strategies)
        rankings = matcher.rank(market)
        
        # 趋势策略应该排第一
        assert rankings[0].profile.name == "trend_following"

    def test_match_mean_reversion_in_ranging_market(self):
        """均值回归策略在震荡市场应该排名靠前。"""
        strategies = [
            StrategyProfile("trend_following", ["trending"], ["ranging"], 1.5, 0.15),
            StrategyProfile("mean_reversion", ["ranging"], ["trending"], 1.2, 0.10),
        ]
        
        market = MarketRegime("ranging", strength=0.6, volatility="low")
        
        matcher = StrategyMatcher(strategies)
        rankings = matcher.rank(market)
        
        # 均值回归应该排第一
        assert rankings[0].profile.name == "mean_reversion"

    def test_dynamic_weight_adjustment(self):
        """动态权重调整：市场强度越高，越偏好高 Sharpe 策略。"""
        strategies = [
            StrategyProfile("conservative", ["ranging"], ["volatile"], 1.0, 0.05),
            StrategyProfile("aggressive", ["volatile", "trending"], ["ranging"], 2.0, 0.30),
        ]
        
        # 低强度震荡市场：保守策略更受青睐
        market_low = MarketRegime("ranging", strength=0.3, volatility="low")
        matcher = StrategyMatcher(strategies)
        rankings_low = matcher.rank(market_low)
        
        # 高强度趋势市场：激进策略更受青睐
        market_high = MarketRegime("trending", strength=0.9, volatility="high")
        rankings_high = matcher.rank(market_high)
        
        # 低强度震荡时保守策略排名更高
        assert rankings_low[0].profile.name == "conservative"
        # 高强度趋势时激进策略排名更高
        assert rankings_high[0].profile.name == "aggressive"


# ------------------------------------------------------------------
# 防抖动机制
# ------------------------------------------------------------------
class TestAntiFlipFlop:
    def test_sticky_switching(self):
        """防抖动：市场状态变化不大时，不轻易切换策略。"""
        strategies = [
            StrategyProfile("trend_following", ["trending"], ["ranging"], 1.5, 0.15),
            StrategyProfile("balanced", ["trending", "ranging"], ["volatile"], 1.3, 0.10),
        ]
        
        matcher = StrategyMatcher(strategies, switch_threshold=0.2)
        
        # 当前持有趋势策略
        current = "trend_following"
        
        # 市场状态轻微变化（从弱趋势到中性）
        market1 = MarketRegime("trending", strength=0.55, volatility="medium")
        market2 = MarketRegime("trending", strength=0.50, volatility="medium")
        
        rank1 = matcher.rank(market1, current_strategy=current)
        rank2 = matcher.rank(market2, current_strategy=current)
        
        # 轻微变化不应该触发切换（防抖动 bias 起作用）
        # 当前策略应该还排第一
        assert rank1[0].profile.name == current
        assert rank2[0].profile.name == current


# ------------------------------------------------------------------
# 波动率匹配
# ------------------------------------------------------------------
class TestVolatilityMatching:
    def test_volatility_preference_affects_score(self):
        """波动率偏好应该影响匹配得分。"""
        strategies = [
            StrategyProfile("low_vol_strat", ["trending"], ["ranging"],
                           1.5, 0.10, preferred_volatility="low"),
            StrategyProfile("high_vol_strat", ["trending"], ["ranging"],
                           1.5, 0.10, preferred_volatility="high"),
        ]

        # 低波动市场：低波动策略应该得分更高
        market_low_vol = MarketRegime("trending", strength=0.7, volatility="low")
        matcher = StrategyMatcher(strategies)
        rankings = matcher.rank(market_low_vol)

        assert rankings[0].profile.name == "low_vol_strat"

    def test_high_vol_market_prefers_high_vol_strategy(self):
        """高波动市场应该偏好高波动策略。"""
        strategies = [
            StrategyProfile("low_vol_strat", ["trending"], ["ranging"],
                           1.5, 0.10, preferred_volatility="low"),
            StrategyProfile("high_vol_strat", ["trending"], ["ranging"],
                           1.5, 0.10, preferred_volatility="high"),
        ]

        market_high_vol = MarketRegime("trending", strength=0.7, volatility="high")
        matcher = StrategyMatcher(strategies)
        rankings = matcher.rank(market_high_vol)

        assert rankings[0].profile.name == "high_vol_strat"


# ------------------------------------------------------------------
# 组合分散化选择
# ------------------------------------------------------------------
class TestPortfolioSelection:
    def test_select_portfolio_basic(self):
        """基本组合选择：选 top N 策略。"""
        strategies = [
            StrategyProfile("strat_a", ["trending"], ["ranging"], 1.5, 0.15,
                           correlation_cluster=0),
            StrategyProfile("strat_b", ["trending"], ["ranging"], 1.4, 0.12,
                           correlation_cluster=1),
            StrategyProfile("strat_c", ["trending"], ["ranging"], 1.3, 0.10,
                           correlation_cluster=2),
        ]

        market = MarketRegime("trending", strength=0.8)
        matcher = StrategyMatcher(strategies)
        portfolio = matcher.select_portfolio(market, top_n=2)

        assert len(portfolio) == 2
        assert portfolio[0].name == "strat_a"
        assert portfolio[1].name == "strat_b"

    def test_portfolio_diversification_across_clusters(self):
        """组合分散化：不同聚类的策略应该被优先选中。"""
        strategies = [
            # 聚类 0：趋势类策略
            StrategyProfile("trend_a", ["trending"], ["ranging"], 1.5, 0.15,
                           correlation_cluster=0),
            StrategyProfile("trend_b", ["trending"], ["ranging"], 1.4, 0.12,
                           correlation_cluster=0),
            # 聚类 1：均值回归类策略
            StrategyProfile("meanrev_a", ["ranging"], ["trending"], 1.3, 0.10,
                           correlation_cluster=1),
        ]

        market = MarketRegime("trending", strength=0.8)
        matcher = StrategyMatcher(strategies)

        # 选 2 个策略，每个聚类最多 1 个
        portfolio = matcher.select_portfolio(market, top_n=2, max_per_cluster=1)

        assert len(portfolio) == 2
        # 应该选了 trend_a（聚类0）和 meanrev_a（聚类1）
        # 而不是 trend_a 和 trend_b（同聚类）
        clusters = [s.correlation_cluster for s in portfolio]
        assert len(set(clusters)) == 2

    def test_portfolio_respects_max_per_cluster(self):
        """组合选择应该尊重每个聚类的最大数量限制。"""
        strategies = [
            StrategyProfile("s1", ["trending"], [], 1.5, 0.1, correlation_cluster=0),
            StrategyProfile("s2", ["trending"], [], 1.4, 0.1, correlation_cluster=0),
            StrategyProfile("s3", ["trending"], [], 1.3, 0.1, correlation_cluster=0),
            StrategyProfile("s4", ["trending"], [], 1.2, 0.1, correlation_cluster=1),
        ]

        market = MarketRegime("trending", strength=0.8)
        matcher = StrategyMatcher(strategies)

        # 每个聚类最多 1 个，选 2 个
        portfolio = matcher.select_portfolio(market, top_n=2, max_per_cluster=1)

        assert len(portfolio) == 2
        clusters = [s.correlation_cluster for s in portfolio]
        assert len(set(clusters)) == 2  # 两个不同的聚类

    def test_portfolio_returns_all_if_not_enough(self):
        """策略数量不够时返回全部，不报错。"""
        strategies = [
            StrategyProfile("only_one", ["trending"], [], 1.5, 0.1),
        ]

        market = MarketRegime("trending", strength=0.8)
        matcher = StrategyMatcher(strategies)
        portfolio = matcher.select_portfolio(market, top_n=5)

        assert len(portfolio) == 1


# ------------------------------------------------------------------
# 边界情况
# ------------------------------------------------------------------
class TestEdgeCases:
    def test_empty_strategy_list(self):
        """空策略列表应该返回空排名。"""
        matcher = StrategyMatcher([])
        market = MarketRegime("trending")
        rankings = matcher.rank(market)
        assert rankings == []

    def test_select_portfolio_empty_strategies(self):
        """空策略列表的组合选择应该返回空。"""
        matcher = StrategyMatcher([])
        market = MarketRegime("trending")
        portfolio = matcher.select_portfolio(market, top_n=3)
        assert portfolio == []

    def test_match_strategies_convenience_function(self):
        """便捷函数应该正常工作。"""
        strategies = [
            StrategyProfile("trend", ["trending"], ["ranging"], 1.5, 0.15),
        ]
        market = MarketRegime("trending")
        rankings = match_strategies(strategies, market)
        assert len(rankings) == 1
        assert rankings[0].profile.name == "trend"
