# -*- coding: utf-8 -*-
"""tests.test_debug.test_system_diagnoser —— 系统诊断框架测试。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.debug.system_diagnoser import (
    SystemDiagnoser,
    Severity,
)


@pytest.fixture
def sample_data():
    """生成示例数据。"""
    np.random.seed(42)
    n = 200
    prices = 2000 + np.cumsum(np.random.randn(n) * 2)
    return pd.DataFrame({
        "open": prices + np.random.randn(n) * 0.5,
        "high": prices + np.abs(np.random.randn(n) * 1.0),
        "low": prices - np.abs(np.random.randn(n) * 1.0),
        "close": prices,
    })


class TestDataLayerCheck:
    def test_good_data_passes_check(self, sample_data):
        """好的数据应该通过检查。"""
        diagnoser = SystemDiagnoser()
        report = diagnoser.check_data_layer(sample_data)

        # 不应该有critical错误
        assert not any(c.severity == Severity.CRITICAL for c in report.checks)

    def test_missing_column_detected(self, sample_data):
        """缺少列应该被检测到。"""
        bad_data = sample_data.drop(columns=["close"])
        diagnoser = SystemDiagnoser()
        report = diagnoser.check_data_layer(bad_data)

        errors = [c for c in report.checks if c.severity == Severity.ERROR]
        assert len(errors) > 0  # 应该有错误

    def test_bad_ohlc_detected(self, sample_data):
        """OHLC关系错误应该被检测到。"""
        bad_data = sample_data.copy()
        bad_data.loc[0, "high"] = 1990  # high < low
        bad_data.loc[0, "low"] = 2010

        diagnoser = SystemDiagnoser()
        report = diagnoser.check_data_layer(bad_data)

        ohlc_checks = [c for c in report.checks if c.name == "OHLC关系"]
        assert ohlc_checks[0].severity == Severity.ERROR


class TestSignalLayerCheck:
    def test_normal_signal_rate(self):
        """正常信号频率应该通过。"""
        signals = [0] * 95 + [1] * 5  # 5%信号率
        diagnoser = SystemDiagnoser()
        report = diagnoser.check_signal_layer(signals)

        rate_checks = [c for c in report.checks if c.name == "信号频率"]
        assert rate_checks[0].severity == Severity.OK

    def test_too_few_signals(self):
        """信号太少应该警告。"""
        signals = [0] * 199 + [1] * 1  # 0.5%信号率
        diagnoser = SystemDiagnoser()
        report = diagnoser.check_signal_layer(signals)

        rate_checks = [c for c in report.checks if c.name == "信号频率"]
        assert rate_checks[0].severity == Severity.WARNING


class TestRiskLayerCheck:
    def test_normal_stop_rate(self):
        """正常止损率应该通过。"""
        trades = [{"exit_reason": "stop_loss"}] * 3 + [{"exit_reason": "take_profit"}] * 7
        diagnoser = SystemDiagnoser()
        report = diagnoser.check_risk_layer(trades)

        stop_checks = [c for c in report.checks if c.name == "止损频率"]
        assert stop_checks[0].severity == Severity.OK

    def test_too_many_stops(self):
        """止损太多应该警告。"""
        trades = [{"exit_reason": "stop_loss"}] * 8 + [{"exit_reason": "take_profit"}] * 2
        diagnoser = SystemDiagnoser()
        report = diagnoser.check_risk_layer(trades)

        stop_checks = [c for c in report.checks if c.name == "止损频率"]
        assert stop_checks[0].severity == Severity.WARNING
