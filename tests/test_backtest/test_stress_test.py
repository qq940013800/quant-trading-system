# -*- coding: utf-8 -*-
"""tests.test_backtest.test_stress_test —— 压力测试模块测试。"""
from __future__ import annotations

import pytest

from core.backtest.stress_test import (
    StressScenario,
    StressTester,
    PRESET_SCENARIOS,
)


class TestStressScenario:
    def test_scenario_creation(self):
        s = StressScenario(
            name="test_crash",
            description="测试暴跌",
            price_shock=-0.15,
            volatility_multiplier=3.0,
        )
        assert s.name == "test_crash"
        assert s.price_shock == -0.15


class TestPresetScenarios:
    def test_presets_exist(self):
        """预设情景应该存在。"""
        assert "2008_financial_crisis" in PRESET_SCENARIOS
        assert "2020_covid_crash" in PRESET_SCENARIOS

    def test_preset_values_reasonable(self):
        """预设情景的参数应该合理。"""
        crisis = PRESET_SCENARIOS["2008_financial_crisis"]
        assert crisis.price_shock < -0.15  # 至少跌15%
        assert crisis.volatility_multiplier > 2.0  # 波动率至少翻倍


class TestStressTester:
    def setup_method(self):
        self.tester = StressTester(initial_equity=100000)

    def test_run_single_scenario(self):
        """运行单个情景应该返回结果。"""
        scenario = PRESET_SCENARIOS["2008_financial_crisis"]
        # 用5%的敞口来测试，应该能触发熔断
        result = self.tester.run_scenario(scenario, current_exposure=0.05)

        assert result.scenario_name == "2008金融危机"
        assert result.total_loss > 0  # 应该有亏损
        assert result.circuit_breaker_triggered is True  # 应该触发熔断

    def test_run_all_presets(self):
        """运行所有预设情景。"""
        results = self.tester.run_all_presets(current_exposure=0.02)
        assert len(results) == len(PRESET_SCENARIOS)

    def test_low_exposure_survives(self):
        """低敞口应该能存活。"""
        scenario = PRESET_SCENARIOS["2008_financial_crisis"]
        result = self.tester.run_scenario(scenario, current_exposure=0.005)
        assert result.survived is True

    def test_high_exposure_may_fail(self):
        """高敞口可能爆仓。"""
        # 极端高敞口测试
        scenario = StressScenario(
            name="extreme",
            description="极端测试",
            price_shock=-0.50,
            volatility_multiplier=10.0,
            gap_days=10,
            liquidity_crisis=True,
        )
        result = self.tester.run_scenario(scenario, current_exposure=0.5)
        # 极端情况下应该爆仓
        assert result.margin_call is True

    def test_stress_report(self):
        """压力测试报告应该包含关键信息。"""
        report = self.tester.stress_report(current_exposure=0.02)

        assert "scenarios_tested" in report
        assert "survival_rate" in report
        assert "worst_case" in report
        assert "all_results" in report
        assert report["scenarios_tested"] == len(PRESET_SCENARIOS)
        # 正常敞口下应该全部存活
        assert report["survival_rate"] == 1.0

    def test_worst_case_identified(self):
        """应该能找出最差的情景。"""
        report = self.tester.stress_report(current_exposure=0.02)
        worst = report["worst_case"]

        assert "name" in worst
        assert "total_loss" in worst
        assert worst["total_loss"] > 0
