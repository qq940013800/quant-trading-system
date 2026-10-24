# -*- coding: utf-8 -*-
"""测试验证层中间件。"""
import pytest
from core.integration.verification_middleware import (
    VerificationMiddleware,
    GateDecision,
    GateFinding,
    GateReport,
)


class TestVerificationMiddleware:
    """验证层中间件测试。"""

    def setup_method(self):
        """每个测试前初始化中间件。"""
        self.mw = VerificationMiddleware(
            overfitting_threshold=0.3,
            drift_warn_threshold=0.7,
            drift_reject_threshold=0.4,
            stress_min_survival=0.5,
        )

    def test_gate_pass(self):
        """测试全部通过的情况。"""
        report = self.mw.gate_before_deploy(
            strategy_id="s001",
            strategy_name="ML趋势",
            backtest_results={"pbo": 0.1, "deflated_sharpe": 1.5},
            recent_returns=[0.01, 0.02, -0.01, 0.03, 0.015],
            benchmark_returns=[0.005, 0.01, -0.005, 0.015, 0.01],
        )

        assert report.strategy_id == "s001"
        assert report.overall_decision in [GateDecision.PASS, GateDecision.WARN]
        assert len(report.findings) > 0

    def test_gate_reject_overfitting(self):
        """测试过拟合风险过高被拒绝。"""
        report = self.mw.gate_before_deploy(
            strategy_id="s002",
            strategy_name="过拟合策略",
            backtest_results={"pbo": 0.6, "deflated_sharpe": 0.5},
        )

        assert report.overall_decision == GateDecision.REJECT
        overfitting_finding = next(f for f in report.findings if f.check_name == "过拟合检测")
        assert overfitting_finding.decision == GateDecision.REJECT

    def test_gate_warn_overfitting(self):
        """测试过拟合风险偏高警告。"""
        report = self.mw.gate_before_deploy(
            strategy_id="s003",
            strategy_name="中等风险策略",
            backtest_results={"pbo": 0.25, "deflated_sharpe": 1.0},
        )

        overfitting_finding = next(f for f in report.findings if f.check_name == "过拟合检测")
        assert overfitting_finding.decision in [GateDecision.PASS, GateDecision.WARN]

    def test_gate_drift_health(self):
        """测试漂移健康度检查。"""
        # 构造收益很差的情况
        recent_returns = [-0.02, -0.015, -0.03, -0.025, -0.02]
        benchmark_returns = [0.005, 0.01, -0.005, 0.015, 0.01]

        report = self.mw.gate_before_deploy(
            strategy_id="s004",
            strategy_name="漂移策略",
            recent_returns=recent_returns,
            benchmark_returns=benchmark_returns,
        )

        drift_finding = next(f for f in report.findings if f.check_name == "漂移监控")
        # 收益很差，应该是警告或拒绝
        assert drift_finding.decision in [GateDecision.WARN, GateDecision.DOWNGRADE, GateDecision.REJECT]

    def test_gate_before_trade(self):
        """测试交易前的组合风控检查。"""
        # 正常情况
        report = self.mw.gate_before_trade(
            strategy_id="s005",
            current_exposure=0.02,
            new_position_size=0.01,
            cluster_exposure=0.015,
        )

        assert report.overall_decision in [GateDecision.PASS, GateDecision.WARN]
        risk_finding = next(f for f in report.findings if f.check_name == "组合风控")
        assert risk_finding.decision in [GateDecision.PASS, GateDecision.WARN]

    def test_gate_before_trade_reject(self):
        """测试交易前组合风险超标被拒绝。"""
        report = self.mw.gate_before_trade(
            strategy_id="s006",
            current_exposure=0.06,  # 已经超过默认的5%上限
            new_position_size=0.02,
            cluster_exposure=0.04,  # 超过默认的3%上限
        )

        assert report.overall_decision == GateDecision.REJECT
        risk_finding = next(f for f in report.findings if f.check_name == "组合风控")
        assert risk_finding.decision == GateDecision.REJECT

    def test_gate_report_stats(self):
        """测试报告统计属性。"""
        report = self.mw.gate_before_deploy(
            strategy_id="s007",
            strategy_name="统计测试",
            backtest_results={"pbo": 0.1, "deflated_sharpe": 1.5},
        )

        assert report.pass_count + report.warn_count + report.reject_count + report.downgrade_count == len(report.findings)
        assert report.strategy_name == "统计测试"

    def test_gate_empty_findings(self):
        """测试没有检查项的情况。"""
        # 不传任何数据，应该没有findings
        report = self.mw.gate_before_deploy(
            strategy_id="s008",
            strategy_name="空数据",
        )

        # 没有检查项，默认通过
        assert report.overall_decision == GateDecision.PASS
        assert len(report.findings) == 0

    def test_gate_exception_handling(self):
        """测试检查出错时的容错处理。"""
        # 传入错误的数据类型，应该不会崩溃
        report = self.mw.gate_before_deploy(
            strategy_id="s009",
            strategy_name="异常测试",
            price_data="not_a_dataframe",  # 错误的数据类型
        )

        # 应该返回警告而不是崩溃
        assert report.overall_decision in [GateDecision.PASS, GateDecision.WARN]


class TestGateDecision:
    """GateDecision枚举测试。"""

    def test_decision_values(self):
        """测试决策枚举值。"""
        assert GateDecision.PASS == "pass"
        assert GateDecision.WARN == "warn"
        assert GateDecision.REJECT == "reject"
        assert GateDecision.DOWNGRADE == "downgrade"


class TestGateFinding:
    """GateFinding数据类测试。"""

    def test_finding_creation(self):
        """测试创建检查项发现。"""
        finding = GateFinding(
            check_name="测试检查",
            decision=GateDecision.WARN,
            score=50.0,
            message="这是一个警告",
            details={"key": "value"},
        )

        assert finding.check_name == "测试检查"
        assert finding.decision == GateDecision.WARN
        assert finding.score == 50.0
        assert finding.message == "这是一个警告"
        assert finding.details["key"] == "value"
