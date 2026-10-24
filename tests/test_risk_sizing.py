# -*- coding: utf-8 -*-
"""test_risk_sizing.py —— 固定分数 + Kelly cap + lot_step 取整 + vol-target。"""
from __future__ import annotations

import _bt_helpers as H  # noqa: F401
import math

import pytest

from core.risk.sizing import quantile_threshold, target_lots, vol_target_scale


def test_lots_floors_to_lot_step():
    # equity=10000, risk=1%, atr0(stop dist)=2, point_value=100
    # risk_budget=100; per_unit_risk=200; raw=0.5 手；lot_step=0.01 -> 0.50
    lots = target_lots(equity=10_000, risk_pct=0.01, atr0=2.0,
                      point_value=100, min_lot=0.01, lot_step=0.01, kelly_cap=1.0)
    assert abs(lots - 0.50) < 1e-9
    # 必须对齐到 lot_step
    assert abs(lots / 0.01 - round(lots / 0.01)) < 1e-9


def test_kelly_cap_truncates_risk():
    # risk_pct=0.05 但 kelly_cap=0.01 -> 实际按 1% 风险
    a = target_lots(10_000, 0.05, 2.0, 100, 0.01, 0.01, kelly_cap=0.01)
    b = target_lots(10_000, 0.01, 2.0, 100, 0.01, 0.01, kelly_cap=1.0)
    assert abs(a - b) < 1e-9


def test_below_min_lot_returns_zero():
    # 风险预算极小 -> 计算手数 < min_lot -> 0
    lots = target_lots(equity=100.0, risk_pct=0.01, atr0=50.0,
                       point_value=100, min_lot=0.10, lot_step=0.01, kelly_cap=1.0)
    assert lots == 0.0


def test_vol_target_scale_shrinks_only():
    assert vol_target_scale(realized_vol=0.20, target_vol=0.10) == pytest.approx(0.5)
    assert vol_target_scale(realized_vol=0.05, target_vol=0.10) == 1.0  # 不放大


def test_quantile_threshold_from_distribution():
    # 阈值来自分布：CLEAN 样本 90 分位
    vals = list(range(100))
    q90 = quantile_threshold(vals, 0.90)
    assert q90 == pytest.approx(89.1)


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        target_lots(0, 0.01, 2.0, 100, 0.01, 0.01, 1.0)
    with pytest.raises(ValueError):
        quantile_threshold([], 0.5)
