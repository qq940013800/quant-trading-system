# -*- coding: utf-8 -*-
"""test_backtest_costs.py —— 三档点差 / 滑点 / 零成本开关（设计⑦.C / c06 关联）。"""
from __future__ import annotations

import _bt_helpers as H  # noqa: F401
import pandas as pd
import pytest

from core.backtest.costs import CostModel, is_news_time, slippage_points, spread_at

NEWS = [pd.Timestamp("2021-01-04 10:00", tz="UTC")]


def model() -> CostModel:
    return CostModel(base_spread=0.20, news_spread=0.60, gap_spread=1.00,
                     gap_threshold=1.0, base_slippage=0.05,
                     slippage_per_volume_frac=0.10, commission_per_lot=0.0,
                     news_minutes=15.0)


def test_news_spread_gt_base():
    bar = H.make_bar(120, 1800, 1800.5, 1799.5, 1800.1)  # 10:00
    s = spread_at(bar, NEWS, prev_close=1800.0, cost_model=model())
    assert s > model().base_spread          # 不等式断言，防成本被旁路成常数
    assert s == model().news_spread


def test_calm_spread_is_base():
    bar = H.make_bar(0, 1800, 1800.5, 1799.5, 1800.1)     # 00:00，远离新闻
    s = spread_at(bar, NEWS, prev_close=1800.0, cost_model=model())
    assert s == model().base_spread


def test_gap_spread_largest():
    # open 相对 prev_close 跳空 2.0 > gap_threshold 1.0
    bar = H.make_bar(0, open_=1802.0, high=1802.5, low=1801.5, close=1802.0)
    s = spread_at(bar, NEWS, prev_close=1800.0, cost_model=model())
    assert s == model().gap_spread


def test_is_news_window_15min():
    assert is_news_time(pd.Timestamp("2021-01-04 10:14", tz="UTC"), NEWS, 15)
    assert not is_news_time(pd.Timestamp("2021-01-04 10:30", tz="UTC"), NEWS, 15)


def test_slippage_scales_with_volume_frac():
    bar = H.make_bar(0, 1800, 1801, 1799, 1800)
    low = slippage_points(bar, 0.0, model())
    high = slippage_points(bar, 1.0, model())
    assert high > low


def test_zero_cost_model_returns_zero():
    bar = H.make_bar(0, 1800, 1801, 1799, 1800)
    assert spread_at(bar, NEWS, 1800.0, None) == 0.0
    assert slippage_points(bar, 0.5, None) == 0.0


def test_tiers_monotonic_config():
    assert model().tiers_valid()
