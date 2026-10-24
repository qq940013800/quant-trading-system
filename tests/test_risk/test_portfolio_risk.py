# -*- coding: utf-8 -*-
"""tests.test_risk.test_portfolio_risk —— 组合层面风控测试。"""
from __future__ import annotations

import pytest

from core.risk.portfolio_risk import (
    StrategyRisk,
    PortfolioRiskConfig,
    PortfolioRiskManager,
)


class TestPortfolioRiskConfig:
    def test_default_config(self):
        config = PortfolioRiskConfig()
        assert config.max_total_exposure == 0.05
        assert config.max_exposure_per_cluster == 0.03
        assert config.daily_loss_limit == 0.03
        assert config.max_strategies == 5


class TestStrategyRisk:
    def test_strategy_risk_creation(self):
        s = StrategyRisk(strategy_id="trend_001", risk_per_trade=0.01)
        assert s.strategy_id == "trend_001"
        assert s.risk_per_trade == 0.01
        assert s.current_exposure == 0.0


class TestPortfolioRiskManager:
    def setup_method(self):
        self.config = PortfolioRiskConfig(
            max_total_exposure=0.05,
            max_exposure_per_cluster=0.03,
            daily_loss_limit=0.03,
            max_strategies=3,
        )
        self.manager = PortfolioRiskManager(self.config)
        self.manager.set_equity(100000)

    def test_add_remove_strategy(self):
        s = StrategyRisk(strategy_id="s1")
        self.manager.add_strategy(s)
        assert "s1" in self.manager.strategies

        self.manager.remove_strategy("s1")
        assert "s1" not in self.manager.strategies

    def test_total_exposure(self):
        self.manager.add_strategy(StrategyRisk("s1", current_exposure=0.01))
        self.manager.add_strategy(StrategyRisk("s2", current_exposure=0.02))
        assert self.manager.total_exposure() == pytest.approx(0.03)

    def test_cluster_exposure(self):
        self.manager.add_strategy(StrategyRisk("s1", current_exposure=0.01, correlation_cluster=0))
        self.manager.add_strategy(StrategyRisk("s2", current_exposure=0.02, correlation_cluster=0))
        self.manager.add_strategy(StrategyRisk("s3", current_exposure=0.015, correlation_cluster=1))

        assert self.manager.cluster_exposure(0) == pytest.approx(0.03)
        assert self.manager.cluster_exposure(1) == pytest.approx(0.015)

    def test_can_open_position_normal(self):
        """正常情况允许开仓。"""
        self.manager.add_strategy(StrategyRisk("s1", current_exposure=0.01))
        allowed, reason = self.manager.can_open_new_position("s1", planned_risk=0.01)
        assert allowed is True
        assert "允许" in reason

    def test_total_exposure_limit(self):
        """总敞口超限应该禁止。"""
        self.manager.add_strategy(StrategyRisk("s1", current_exposure=0.04))
        allowed, reason = self.manager.can_open_new_position("s1", planned_risk=0.02)
        assert allowed is False
        assert "总敞口" in reason

    def test_cluster_exposure_limit(self):
        """聚类敞口超限应该禁止。"""
        self.manager.add_strategy(StrategyRisk("s1", current_exposure=0.025, correlation_cluster=0))
        allowed, reason = self.manager.can_open_new_position("s1", planned_risk=0.01)
        assert allowed is False
        assert "聚类" in reason

    def test_daily_loss_limit(self):
        """当日亏损超限应该禁止开仓。"""
        self.manager.add_strategy(StrategyRisk("s1", daily_pnl=-0.02))
        self.manager.add_strategy(StrategyRisk("s2", daily_pnl=-0.015))
        # 总亏损 -3.5% 超过 3% 限制
        allowed, reason = self.manager.can_open_new_position("s1", planned_risk=0.01)
        assert allowed is False
        assert "熔断" in reason

    def test_max_strategies_limit(self):
        """策略数量超限应该禁止。"""
        self.manager.add_strategy(StrategyRisk("s1"))
        self.manager.add_strategy(StrategyRisk("s2"))
        self.manager.add_strategy(StrategyRisk("s3"))
        # 已经3个了，再加新的应该不行
        allowed, reason = self.manager.can_open_new_position("new_s", planned_risk=0.01)
        assert allowed is False
        assert "策略数量" in reason

    def test_risk_report(self):
        """风险报告应该包含关键信息。"""
        self.manager.add_strategy(StrategyRisk("s1", current_exposure=0.01, daily_pnl=0.005))
        report = self.manager.risk_report()

        assert "equity" in report
        assert "total_exposure" in report
        assert "strategies" in report
        assert len(report["strategies"]) == 1
        assert report["strategies"][0]["id"] == "s1"
