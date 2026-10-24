# -*- coding: utf-8 -*-
"""测试守门员整合模块。"""
import pytest
from core.integration.gatekeeper import Gatekeeper, GatekeeperSummary, StrategyGateResult
from core.integration.verification_middleware import GateDecision


class TestGatekeeper:
    """守门员整合模块测试。"""

    def setup_method(self):
        """每个测试前初始化守门员。"""
        self.gate = Gatekeeper()

    def test_run_full_gate(self):
        """测试完整守门员流程。"""
        summary = self.gate.run_full_gate()

        assert isinstance(summary, GatekeeperSummary)
        assert summary.total_strategies > 0
        assert summary.pass_count + summary.warn_count + summary.downgrade_count + summary.reject_count == summary.total_strategies
        assert len(summary.results) == summary.total_strategies

    def test_summary_stats(self):
        """测试总结统计属性。"""
        summary = self.gate.run_full_gate()

        assert 0 <= summary.pass_rate <= 1
        assert summary.pass_count >= 0
        assert summary.reject_count >= 0

    def test_strategy_result(self):
        """测试单个策略结果。"""
        summary = self.gate.run_full_gate()

        for result in summary.results:
            assert isinstance(result, StrategyGateResult)
            assert result.strategy_id
            assert result.strategy_name
            assert result.can_deploy in [True, False]
            assert result.recommended_action

    def test_generate_report_text(self):
        """测试生成人类可读报告。"""
        summary = self.gate.run_full_gate()
        report_text = self.gate.generate_report_text(summary)

        assert "守门员报告" in report_text
        assert "策略总数" in report_text
        assert "通过率" in report_text

    def test_bridge_health_included(self):
        """测试桥接健康状态包含在报告中。"""
        summary = self.gate.run_full_gate()

        assert summary.bridge_health is not None
        # 桥接可能可达也可能不可达，取决于环境

    def test_gate_one_strategy(self):
        """测试单个策略守门员检查。"""
        strategy = {"id": "test001", "name": "测试策略", "type": "test", "symbol": "TESTUSD"}
        result = self.gate._gate_one_strategy(strategy)

        assert result.strategy_id == "test001"
        assert result.strategy_name == "测试策略"
        assert result.gate_report.overall_decision in list(GateDecision)

    def test_fetch_strategies_fallback(self):
        """测试桥接不可用时的降级策略列表。"""
        strategies = self.gate._fetch_strategies()

        # 应该至少返回一些策略（即使是模拟的）
        assert len(strategies) > 0
        for s in strategies:
            assert "id" in s
            assert "name" in s


class TestStrategyGateResult:
    """单个策略结果测试。"""

    def test_result_creation(self):
        """测试创建策略结果。"""
        from core.integration.verification_middleware import GateReport, GateFinding
        from datetime import datetime

        report = GateReport(
            strategy_id="s001",
            strategy_name="测试",
            overall_decision=GateDecision.PASS,
            findings=[],
            timestamp=datetime.now().isoformat(),
        )

        result = StrategyGateResult(
            strategy_id="s001",
            strategy_name="测试",
            gate_report=report,
            can_deploy=True,
            recommended_action="允许上线",
        )

        assert result.strategy_id == "s001"
        assert result.can_deploy is True
