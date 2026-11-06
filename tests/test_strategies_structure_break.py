# -*- coding: utf-8 -*-
"""tests/test_strategies_structure_break.py —— BOS/CHoCH 结构突破策略单测。

覆盖：上行噪声趋势 → 多头结构突破信号；下行 → 空头；横盘无突破 → 无信号；
同 history 重放可重放；混入未来 bar 显式报错。
"""
from __future__ import annotations

import numpy as np
import pytest

import _bt_helpers as H
from core.strategies.structure_break import StructureBreakStrategy


def _zigzag(n_cycles: int = 15, leg: int = 4, up: float = 2.2, down: float = 1.8,
            start: float = 1800.0):
    """确定性 zigzag：up 根上行 + down 根下行交替（内部高点/低点即 swing）。

    up/down 不等 → 有净漂移，每个新峰值超越前一个 swing 峰值（BOS 成立）。
    """
    prices = [start]
    for _ in range(n_cycles):
        for _ in range(leg):
            prices.append(prices[-1] + up)
        for _ in range(leg):
            prices.append(prices[-1] - down)
    return H.make_bars(prices, spread=0.5)


def _run(strat, bars):
    out = []
    for i, bar in enumerate(bars):
        sig = strat.on_bar_close(bars[:i + 1], bar)
        out.append((bar, sig))
    return out


def test_uptrend_emits_long_structure_signal():
    bars = _zigzag()
    strat = StructureBreakStrategy()
    results = _run(strat, bars)
    longs = [sig for _, sig in results if sig is not None and sig.direction == 1]
    assert longs, "zigzag 上行 leg 应产生多头结构突破信号"
    sig = longs[0]
    assert sig.expert == "structure_break"
    assert sig.l1_in_zone is True
    assert abs(sig.entry_dist - 2.0 * sig.atr0) < 1e-9
    assert sig.strategy_version == "structure_break-v1"
    assert sig.regime_weights == {"trend": 1.0, "mr": 0.0, "range": 0.0}


def test_downtrend_emits_short_structure_signal():
    """镜像 zigzag（下行漂移）：下行 leg 跌破前 swing low → 空头 BOS。"""
    bars = _zigzag(up=1.8, down=2.2)
    strat = StructureBreakStrategy()
    results = _run(strat, bars)
    shorts = [sig for _, sig in results if sig is not None and sig.direction == -1]
    assert shorts, "下行 leg 应产生空头结构突破信号"


def test_sideways_no_signal():
    bars = H.make_bars([1800.0] * 80, spread=0.5)
    strat = StructureBreakStrategy(k=2)
    results = _run(strat, bars)
    assert all(sig is None for _, sig in results), \
        "无结构突破的横盘行情不应出信号"


def test_future_bar_guard():
    bars = H.make_trend_bars(n=60, seed=7)
    strat = StructureBreakStrategy()
    future = H.make_bar(500, open_=2000, high=2001, low=1999, close=2000)
    with pytest.raises(ValueError):
        strat.on_bar_close(list(bars) + [future], bars[-1])


def test_replay_determinism():
    bars = _zigzag()
    s1 = StructureBreakStrategy()
    s2 = StructureBreakStrategy()
    a = s1.on_bar_close(bars, bars[-1])
    b = s2.on_bar_close(list(bars), bars[-1])
    assert (a is None and b is None) or (
        a.signal_id == b.signal_id and a.direction == b.direction
        and a.atr0 == b.atr0)
