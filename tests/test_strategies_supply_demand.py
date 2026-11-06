# -*- coding: utf-8 -*-
"""tests/test_strategies_supply_demand.py —— 供需区策略单测。

覆盖（AGENTS.md 硬规则 2「供需区只用 KNOWN 集构建」）：
1. 盘整→impulse 当根构建 demand zone；
2. 价格回访 zone → 做多信号（range 权重 / l1_in_zone / entry_dist 冻结）；
3. KNOWN 边界之后的 impulse bar 不构建新 zone，但仍使用既有 zone 回访出信号；
4. zone 有效期过期后自动失效；
5. 因果守卫（混入未来 bar 显式报错）。
"""
from __future__ import annotations

import numpy as np
import pytest

import _bt_helpers as H
from core.strategies.supply_demand import SupplyDemandStrategy


def _synthetic() -> list:
    """20 根平盘(1800) → impulse(1806) → 上行 → 回落回访盘整 zone。"""
    prices = [1800.0] * 20 + [1806.0, 1808.0, 1809.0, 1810.0,
                              1807.0, 1804.0, 1801.5, 1800.2, 1799.9]
    return H.make_bars(prices, spread=0.5)


def _run(strat, bars):
    """引擎式逐根回放，返回 (bar, signal) 列表。"""
    out = []
    for i, bar in enumerate(bars):
        sig = strat.on_bar_close(bars[:i + 1], bar)
        out.append((bar, sig))
    return out


def test_impulse_builds_demand_zone():
    bars = _synthetic()
    strat = SupplyDemandStrategy()
    _run(strat, bars[:22])  # 跑到 impulse+1 根
    assert len(strat.zones) >= 1
    zone = strat.zones[0]
    assert zone["side"] == "demand"
    assert zone["build_ts"] == bars[20].ts_utc
    # zone = 盘整段 [low, high] ≈ [1799.75, 1800.25]
    assert zone["bottom"] < 1800.0 < zone["top"]


def test_retest_emits_long_signal():
    bars = _synthetic()
    strat = SupplyDemandStrategy()
    results = _run(strat, bars)
    longs = [sig for _, sig in results if sig is not None and sig.direction == 1]
    assert longs, "回访盘整 zone 应出做多信号"
    sig = longs[0]
    assert sig.l1_in_zone is True
    assert sig.regime_weights == {"trend": 0.0, "mr": 0.0, "range": 1.0}
    assert abs(sig.entry_dist - 2.0 * sig.atr0) < 1e-9
    assert sig.strategy_version == "supply_demand-v1"


def test_known_end_ts_blocks_post_known_zone_building():
    """KNOWN 纪律：边界之后的 impulse bar 只使用、不构建。"""
    bars = _synthetic()
    known_end = str(bars[20].ts_utc)  # impulse 当根仍属 KNOWN 集
    strat = SupplyDemandStrategy(known_end_ts=known_end)
    _run(strat, bars[:21])  # 跑到 impulse 当根：zone 已建
    n_zones_after_known = len(strat.zones)
    assert n_zones_after_known >= 1

    # 交易段再来一根大 impulse（跳空 +10），禁止构建新 zone
    last_bar = bars[-1]
    jump = H.make_bar(len(bars), open_=1799.9, high=1810.5, low=1799.0,
                      close=1810.0)
    history = list(bars[:21]) + [jump]
    strat.on_bar_close(history, jump)
    assert len(strat.zones) == n_zones_after_known, \
        "交易段（KNOWN 集外）的 impulse 不得构建新供需区"


def test_trade_segment_retest_still_uses_known_zones():
    bars = _synthetic()
    known_end = str(bars[20].ts_utc)
    strat = SupplyDemandStrategy(known_end_ts=known_end)
    results = _run(strat, bars)  # 全程回放：后半段（交易段）回访既有 zone
    longs = [sig for _, sig in results if sig is not None and sig.direction == 1]
    assert longs, "KNOWN 集内构建的 zone 在交易段回访时仍可出信号"


def test_zone_expiry():
    bars = _synthetic()
    strat = SupplyDemandStrategy(zone_valid_bars=2)  # 2 根后过期
    results = _run(strat, bars)
    # 回访 bar（index 27-28）距 impulse（index 20）已远超 2 根 → zone 已失效
    assert all(sig is None for _, sig in results)
    assert strat.zones == []


def test_future_bar_guard():
    bars = _synthetic()
    strat = SupplyDemandStrategy()
    future = H.make_bar(500, open_=1900, high=1901, low=1899, close=1900)
    with pytest.raises(ValueError) as exc:
        strat.on_bar_close(list(bars) + [future], bars[-1])
    assert "no future bars" in exc.value.args[0]["detail"]


def test_known_end_ts_must_be_tz_aware():
    with pytest.raises(ValueError):
        SupplyDemandStrategy(known_end_ts="2021-01-04 00:30")  # naive
