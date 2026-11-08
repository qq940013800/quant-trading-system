# -*- coding: utf-8 -*-
"""tests.test_risk.test_return_profile —— 收益分布形态画像纯函数单测。"""
from __future__ import annotations

import math

import pytest

from core.risk.return_profile import describe_returns


def test_empty_returns_neutral():
    out = describe_returns([])
    assert out["n"] == 0
    assert out["mean"] == 0.0
    assert out["std"] == 0.0
    assert out["skewness"] == 0.0
    assert out["downside_upside_ratio"] is None


def test_single_value_neutral():
    out = describe_returns([0.01])
    assert out["n"] == 1
    assert out["std"] == 0.0
    assert out["skewness"] == 0.0
    assert out["worst_return"] == pytest.approx(0.01)
    assert out["best_return"] == pytest.approx(0.01)
    assert out["downside_upside_ratio"] is None


def test_symmetric_returns_zero_skew_equal_dev():
    out = describe_returns([2.0, -1.0, 1.0, -2.0])
    assert out["skewness"] == pytest.approx(0.0, abs=1e-9)
    assert out["downside_deviation"] == pytest.approx(out["upside_deviation"])
    assert out["downside_upside_ratio"] == pytest.approx(1.0, abs=1e-9)
    assert out["loss_share"] == pytest.approx(0.5)


def test_left_skew_is_negative():
    # 多数小赚、少数大亏 → 左偏，样本偏度为负
    out = describe_returns([0.01, 0.01, 0.01, 0.01, -0.20])
    assert out["skewness"] < 0.0
    assert out["worst_return"] == pytest.approx(-0.20)


def test_right_skew_is_positive():
    # 多数小亏、少数大赚 → 右偏，样本偏度为正
    out = describe_returns([-0.01, -0.01, -0.01, -0.01, 0.20])
    assert out["skewness"] > 0.0
    assert out["best_return"] == pytest.approx(0.20)


def test_loss_share_and_extremes():
    out = describe_returns([0.02, -0.03, 0.01, -0.01])
    assert out["loss_share"] == pytest.approx(0.5)
    assert out["worst_return"] == pytest.approx(-0.03)
    assert out["best_return"] == pytest.approx(0.02)


@pytest.mark.parametrize("bad", [[1.0, math.inf], [1.0, math.nan], [1.0, -math.inf]])
def test_non_finite_raises(bad):
    with pytest.raises(ValueError):
        describe_returns(bad)


@pytest.mark.parametrize("bad", ["0.01", b"1.0", {"a": 1.0}])
def test_non_sequence_rejected(bad):
    with pytest.raises(ValueError):
        describe_returns(bad)


def test_constant_series_zero_dispersion():
    out = describe_returns([0.02] * 10)
    assert out["std"] == 0.0
    assert out["skewness"] == 0.0
    assert out["downside_deviation"] == 0.0
    assert out["upside_deviation"] == 0.0
    assert out["loss_share"] == 0.0
    assert out["downside_upside_ratio"] is None
