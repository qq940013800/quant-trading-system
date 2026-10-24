# -*- coding: utf-8 -*-
"""test_backtest_metrics.py —— 绩效指标在已知权益曲线上的正确性。"""
from __future__ import annotations

import _bt_helpers as H  # noqa: F401
import numpy as np
import pandas as pd

from core.backtest.metrics import compute_metrics


def test_metrics_on_known_curve():
    # 100 -> 110 上涨 -> 回撤到 105
    idx = pd.date_range("2021-01-04", periods=5, freq="5min", tz="UTC")
    eq = pd.Series([100.0, 105.0, 110.0, 108.0, 105.0], index=idx)
    trades = [{"pnl_usd": 10.0}, {"pnl_usd": -3.0}, {"pnl_usd": 5.0}]
    m = compute_metrics(eq, trades, bars_per_year=100)
    assert m["n_trades"] == 3
    assert m["win_rate"] == (2 / 3)
    assert m["profit_factor"] == pytest_approx(15.0 / 3.0)
    assert m["max_drawdown"] < 0          # 存在回撤
    assert m["expectancy_usd"] == pytest_approx(4.0)


def pytest_approx(x):
    import pytest
    return pytest.approx(x)


def test_empty_trades_no_crash():
    idx = pd.date_range("2021-01-04", periods=2, freq="5min", tz="UTC")
    eq = pd.Series([100.0, 101.0], index=idx)
    m = compute_metrics(eq, [], bars_per_year=100)
    assert m["n_trades"] == 0
    assert m["sharpe"] == 0.0
