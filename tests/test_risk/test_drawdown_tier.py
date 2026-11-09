# -*- coding: utf-8 -*-
"""tests.test_risk.test_drawdown_tier —— 回撤分级降档纯函数单测。"""
from __future__ import annotations

import math

import pytest

from core.risk.drawdown_tier import drawdown_tier_factor


def test_no_drawdown_returns_base():
    assert drawdown_tier_factor(100.0, 100.0) == pytest.approx(1.0)


def test_drawdown_below_one_step_keeps_base():
    # -5% 不足一档（步长 10%）
    assert drawdown_tier_factor(95.0, 100.0) == pytest.approx(1.0)


def test_one_step_past_boundary():
    # -11% 越过一档（步长 10%）→ 0.8；浮点边界 90/100 与旧引擎同口径记未达一档
    assert drawdown_tier_factor(89.0, 100.0) == pytest.approx(0.8)


def test_two_steps_deeper():
    # -25% → 两步 0.8^2 = 0.64
    assert drawdown_tier_factor(75.0, 100.0) == pytest.approx(0.64)


def test_non_positive_peak_degrades_to_base():
    assert drawdown_tier_factor(50.0, 0.0) == pytest.approx(1.0)
    assert drawdown_tier_factor(-10.0, -5.0) == pytest.approx(1.0)


def test_custom_base_factor():
    assert drawdown_tier_factor(100.0, 100.0, base_factor=0.5) == pytest.approx(0.5)


def test_max_steps_caps_tier():
    # -30% 本应三步，封顶一档 → 0.8
    assert drawdown_tier_factor(70.0, 100.0, max_steps=1) == pytest.approx(0.8)


@pytest.mark.parametrize("bad_equity", [math.nan, math.inf, -math.inf])
def test_non_finite_equity_raises(bad_equity):
    with pytest.raises(ValueError):
        drawdown_tier_factor(bad_equity, 100.0)


@pytest.mark.parametrize("bad_step", [0.0, -0.1])
def test_non_positive_step_raises(bad_step):
    with pytest.raises(ValueError):
        drawdown_tier_factor(90.0, 100.0, dd_step=bad_step)


@pytest.mark.parametrize("bad_mult", [1.5, 0.0, -0.5])
def test_invalid_tier_mult_raises(bad_mult):
    with pytest.raises(ValueError):
        drawdown_tier_factor(90.0, 100.0, tier_mult=bad_mult)


@pytest.mark.parametrize("bad_max", [-1, 1.5, True])
def test_invalid_max_steps_raises(bad_max):
    with pytest.raises(ValueError):
        drawdown_tier_factor(90.0, 100.0, max_steps=bad_max)
