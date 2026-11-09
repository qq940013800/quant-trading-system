# -*- coding: utf-8 -*-
"""test_backtest.test_broker —— 撮合成交纯函数成交价/成本与边界值守卫。"""
from __future__ import annotations

import pytest

from core.backtest.broker import simulate_fill


def test_long_fill_price_and_cost():
    fill = simulate_fill(+1, ref_price=2000.0, spread=2.0, slippage=0.5,
                         commission_per_lot=0.0, lots=0.5, point_value=100.0)
    # 买：ref + spread/2 + slip = 2000 + 1.0 + 0.5 = 2001.5
    assert fill.fill_price == pytest.approx(2001.5)
    # 不利偏移 1.5 × 0.5 手 × 100 = 75.0 USD
    assert fill.cost == pytest.approx(75.0)


def test_short_fill_price_and_cost():
    fill = simulate_fill(-1, ref_price=2000.0, spread=2.0, slippage=0.5,
                         commission_per_lot=1.0, lots=0.5, point_value=100.0)
    # 卖：ref - spread/2 - slip = 1998.5
    assert fill.fill_price == pytest.approx(1998.5)
    # 成本 = 偏移 1.5×0.5×100 + 佣金 1.0×0.5 = 75.5
    assert fill.cost == pytest.approx(75.5)


def test_rejects_bad_direction():
    with pytest.raises(ValueError):
        simulate_fill(0, 2000.0, 2.0, 0.5, 0.0, 0.5, 100.0)


def test_rejects_nonpositive_lots():
    with pytest.raises(ValueError):
        simulate_fill(+1, 2000.0, 2.0, 0.5, 0.0, 0.0, 100.0)


def test_rejects_nonpositive_ref_price():
    with pytest.raises(ValueError):
        simulate_fill(+1, 0.0, 2.0, 0.5, 0.0, 0.5, 100.0)


def test_rejects_negative_spread_or_slippage():
    with pytest.raises(ValueError):
        simulate_fill(+1, 2000.0, -1.0, 0.5, 0.0, 0.5, 100.0)
    with pytest.raises(ValueError):
        simulate_fill(+1, 2000.0, 2.0, -0.5, 0.0, 0.5, 100.0)


def test_rejects_nonfinite_inputs():
    for bad in (float("nan"), float("inf")):
        with pytest.raises(ValueError):
            simulate_fill(+1, bad, 2.0, 0.5, 0.0, 0.5, 100.0)
        with pytest.raises(ValueError):
            simulate_fill(+1, 2000.0, bad, 0.5, 0.0, 0.5, 100.0)


def test_rejects_nonpositive_point_value():
    with pytest.raises(ValueError):
        simulate_fill(+1, 2000.0, 2.0, 0.5, 0.0, 0.5, 0.0)


def _fill(**kw):
    base = dict(direction=+1, ref_price=2000.0, spread=2.0, slippage=0.5,
                commission_per_lot=0.0, lots=0.5, point_value=100.0)
    base.update(kw)
    return simulate_fill(**base)


@pytest.mark.parametrize("field", ["ref_price", "spread", "slippage",
                                   "commission_per_lot", "lots", "point_value"])
@pytest.mark.parametrize("bad", [True, "2000", None])
def test_rejects_non_numeric_inputs(field, bad):
    with pytest.raises(ValueError):
        _fill(**{field: bad})
