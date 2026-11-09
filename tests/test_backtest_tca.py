# -*- coding: utf-8 -*-
"""test_backtest_tca.py —— G7 TCA 成本分解与偏差告警纯判定测试。"""
from __future__ import annotations

import math
import pytest

from core.backtest.tca import (
    CostBreakdown,
    assess_cost_deviation,
    decompose_costs,
)


def test_decompose_total_and_shares():
    bd = decompose_costs(spread=0.20, slippage=0.10, impact=0.05, commission=0.15)
    assert bd.total == pytest.approx(0.50)
    shares = bd.shares()
    assert sum(shares.values()) == pytest.approx(1.0)
    assert all(v >= 0 for v in shares.values())
    assert shares["commission"] == pytest.approx(0.15 / 0.50)
    assert bd.components()["impact"] == 0.05


def test_zero_cost_shares_are_zero():
    bd = decompose_costs(spread=0.0, slippage=0.0, impact=0.0, commission=0.0)
    assert bd.total == 0.0
    assert bd.shares() == {k: 0.0 for k in ("spread", "slippage", "impact", "commission")}


def test_deviation_within_threshold_not_breached():
    actual = decompose_costs(spread=0.2, slippage=0.1, impact=0.1, commission=0.1)  # 0.5
    expected = decompose_costs(spread=0.2, slippage=0.1, impact=0.05, commission=0.05)  # 0.4
    res = assess_cost_deviation(actual, expected, deviation_threshold=0.30)
    assert res.expected_total == pytest.approx(0.4)
    assert res.actual_total == pytest.approx(0.5)
    assert res.deviation == pytest.approx(0.1)
    assert res.deviation_ratio == pytest.approx(0.25)
    assert res.breached is False


def test_deviation_over_threshold_breached():
    actual = decompose_costs(spread=0.2, slippage=0.2, impact=0.1, commission=0.1)  # 0.6
    expected = decompose_costs(spread=0.2, slippage=0.1, impact=0.05, commission=0.05)  # 0.4
    res = assess_cost_deviation(actual, expected, deviation_threshold=0.25)
    assert res.deviation_ratio == pytest.approx(0.5)
    assert res.breached is True


def test_actual_below_expected_not_breached():
    actual = decompose_costs(spread=0.15, slippage=0.10, impact=0.0, commission=0.10)  # 0.35
    expected = decompose_costs(spread=0.2, slippage=0.1, impact=0.05, commission=0.05)  # 0.4
    res = assess_cost_deviation(actual, expected, deviation_threshold=0.25)
    assert res.deviation < 0
    assert res.deviation_ratio == pytest.approx(-0.125)
    assert res.breached is False


def test_expected_zero_actual_positive_breached_no_ratio():
    actual = decompose_costs(spread=0.1, slippage=0.1, impact=0.0, commission=0.0)
    expected = decompose_costs(spread=0.0, slippage=0.0, impact=0.0, commission=0.0)
    res = assess_cost_deviation(actual, expected, deviation_threshold=0.25)
    assert res.deviation_ratio is None
    assert res.breached is True


def test_expected_zero_actual_zero_not_breached():
    zero = decompose_costs(spread=0.0, slippage=0.0, impact=0.0, commission=0.0)
    res = assess_cost_deviation(zero, zero, deviation_threshold=0.25)
    assert res.deviation_ratio is None
    assert res.breached is False


@pytest.mark.parametrize("kw", [
    {"spread": -0.1, "slippage": 0.0, "impact": 0.0, "commission": 0.0},
    {"spread": 0.0, "slippage": -0.1, "impact": 0.0, "commission": 0.0},
    {"spread": 0.0, "slippage": 0.0, "impact": -0.1, "commission": 0.0},
    {"spread": 0.0, "slippage": 0.0, "impact": 0.0, "commission": -0.1},
])
def test_negative_component_rejected(kw):
    with pytest.raises(ValueError):
        decompose_costs(**kw)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, True, "0.1"])
def test_non_finite_component_rejected(bad):
    with pytest.raises(ValueError):
        decompose_costs(spread=bad, slippage=0.0, impact=0.0, commission=0.0)


def test_negative_threshold_rejected():
    actual = decompose_costs(spread=0.1, slippage=0.0, impact=0.0, commission=0.0)
    expected = decompose_costs(spread=0.1, slippage=0.0, impact=0.0, commission=0.0)
    with pytest.raises(ValueError):
        assess_cost_deviation(actual, expected, deviation_threshold=-0.1)


def test_to_dict_roundtrip():
    actual = decompose_costs(spread=0.2, slippage=0.1, impact=0.1, commission=0.1)
    expected = decompose_costs(spread=0.2, slippage=0.1, impact=0.05, commission=0.05)
    res = assess_cost_deviation(actual, expected, deviation_threshold=0.30)
    d = res.to_dict()
    assert d["breached"] is False
    assert d["flags"]["deviation_ratio"] == pytest.approx(d["deviation_ratio"])
    assert set(d.keys()) == {"actual_total", "expected_total", "deviation",
                             "deviation_ratio", "breached", "threshold", "flags"}
