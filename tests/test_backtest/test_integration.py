# -*- coding: utf-8 -*-
"""tests.test_backtest.test_integration —— 压力测试与回测集成测试。"""
from __future__ import annotations

import pytest

from core.backtest.integration import (
    BacktestStressIntegration,
    IntegratedReport,
)


class TestBacktestStressIntegration:
    def setup_method(self):
        self.integration = BacktestStressIntegration(initial_equity=100000)

    def test_analyze_returns_report(self):
        """分析应该返回集成报告。"""
        metrics = {"sharpe": 1.5, "max_drawdown": 0.10}
        report = self.integration.analyze(metrics, current_exposure=0.02)

        assert isinstance(report, IntegratedReport)
        assert report.risk_score >= 0
        assert report.risk_level in ("low", "medium", "high", "critical")

    def test_report_contains_stress_results(self):
        """报告应该包含所有压力测试结果。"""
        metrics = {"sharpe": 1.0, "max_drawdown": 0.15}
        report = self.integration.analyze(metrics, current_exposure=0.02)

        assert len(report.stress_results) == 5  # 5个预设情景

    def test_worst_case_loss_identified(self):
        """应该能找出最差情景的损失。"""
        metrics = {"sharpe": 1.0, "max_drawdown": 0.15}
        report = self.integration.analyze(metrics, current_exposure=0.02)

        assert report.worst_case_loss > 0

    def test_risk_score_range(self):
        """风险评分应该在0-100之间。"""
        metrics = {"sharpe": 1.0, "max_drawdown": 0.15}
        report = self.integration.analyze(metrics, current_exposure=0.02)

        assert 0 <= report.risk_score <= 100

    def test_safe_strategy_high_score(self):
        """安全的策略应该有较高的风险评分。"""
        metrics = {"sharpe": 2.0, "max_drawdown": 0.05}
        report = self.integration.analyze(metrics, current_exposure=0.01)

        assert report.risk_score >= 60

    def test_risky_strategy_low_score(self):
        """高风险策略应该有较低的风险评分。"""
        metrics = {"sharpe": 0.5, "max_drawdown": 0.30}
        report = self.integration.analyze(metrics, current_exposure=0.05)

        assert report.risk_score < 60

    def test_quick_analyze(self):
        """快速分析应该返回字典。"""
        result = self.integration.quick_analyze(
            sharpe=1.5,
            max_drawdown=0.10,
            current_exposure=0.02,
        )

        assert "risk_score" in result
        assert "risk_level" in result
        assert "worst_case_loss" in result
        assert "survival_rate" in result

    def test_risk_level_classification(self):
        """风险等级分类应该正确。"""
        # 安全策略
        assert self.integration._risk_level(90) == "low"
        assert self.integration._risk_level(70) == "medium"
        assert self.integration._risk_level(50) == "high"
        assert self.integration._risk_level(30) == "critical"
