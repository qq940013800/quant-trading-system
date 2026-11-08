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


class TestPortfolioRiskBoundary:
    def setup_method(self):
        self.config = PortfolioRiskConfig(
            max_total_exposure=0.05,
            max_exposure_per_cluster=0.03,
            daily_loss_limit=0.03,
            max_strategies=3,
        )

    def test_empty_manager_aggregates_zero(self):
        mgr = PortfolioRiskManager(self.config)
        assert mgr.total_exposure() == 0.0
        assert mgr.cluster_exposure(0) == 0.0
        assert mgr.total_daily_pnl() == 0.0

    def test_empty_manager_allows_open(self):
        mgr = PortfolioRiskManager(self.config)
        allowed, reason = mgr.can_open_new_position("ghost", 0.01)
        assert allowed is True
        assert "允许" in reason

    def test_remove_missing_strategy_does_not_raise(self):
        mgr = PortfolioRiskManager(self.config)
        mgr.remove_strategy("not_registered")  # pop 默认 None，不抛异常

    def test_total_exposure_exact_limit_allowed(self):
        """current + planned == max_total 走严格 > 口径，恰好等于允许。"""
        cfg = PortfolioRiskConfig(max_total_exposure=0.05,
                                  max_exposure_per_cluster=0.10,
                                  daily_loss_limit=0.03, max_strategies=3)
        mgr = PortfolioRiskManager(cfg)
        mgr.add_strategy(StrategyRisk("s1", current_exposure=0.04,
                                      correlation_cluster=0))
        allowed, _ = mgr.can_open_new_position("s1", planned_risk=0.01)
        assert allowed is True

    def test_total_exposure_over_limit_denied(self):
        cfg = PortfolioRiskConfig(max_total_exposure=0.05,
                                  max_exposure_per_cluster=0.10,
                                  daily_loss_limit=0.03, max_strategies=3)
        mgr = PortfolioRiskManager(cfg)
        mgr.add_strategy(StrategyRisk("s1", current_exposure=0.04,
                                      correlation_cluster=0))
        allowed, reason = mgr.can_open_new_position("s1", planned_risk=0.011)
        assert allowed is False
        assert "总敞口" in reason

    def test_daily_pnl_exact_limit_triggers(self):
        """当日亏损恰好等于 -limit（<= 口径）即熔断。"""
        mgr = PortfolioRiskManager()
        mgr.add_strategy(StrategyRisk("a", daily_pnl=-0.03))
        allowed, reason = mgr.can_open_new_position("a", planned_risk=0.01)
        assert allowed is False
        assert "熔断" in reason

    def test_unknown_strategy_skips_cluster_check(self):
        """未注册策略不做聚类敞口检查（无聚类归属）。"""
        cfg = PortfolioRiskConfig(max_exposure_per_cluster=0.01)
        mgr = PortfolioRiskManager(cfg)
        mgr.add_strategy(StrategyRisk("known", current_exposure=0.009,
                                      correlation_cluster=7))
        allowed, _ = mgr.can_open_new_position("ghost", planned_risk=0.02)
        assert allowed is True

    def test_report_structure(self):
        mgr = PortfolioRiskManager(self.config)
        mgr.set_equity(50_000)
        report = mgr.risk_report()
        assert report["equity"] == 50_000
        assert report["strategy_count"] == 0
        assert report["total_exposure"] == 0.0
        assert report["total_daily_pnl"] == 0.0
        assert set(report["config"].keys()) == {
            "max_total_exposure", "max_exposure_per_cluster",
            "daily_loss_limit", "max_strategies",
        }


class TestPortfolioRiskGuard:
    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), -0.01])
    def test_rejects_bad_planned_risk(self, bad):
        mgr = PortfolioRiskManager()
        with pytest.raises(ValueError):
            mgr.can_open_new_position("ghost", planned_risk=bad)

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), -0.01])
    def test_rejects_nonfinite_config_threshold(self, bad):
        with pytest.raises(ValueError):
            PortfolioRiskConfig(max_total_exposure=bad)

    @pytest.mark.parametrize("bad", [True, 1.5, -1, "3"])
    def test_rejects_invalid_max_strategies(self, bad):
        with pytest.raises(ValueError):
            PortfolioRiskConfig(max_strategies=bad)
