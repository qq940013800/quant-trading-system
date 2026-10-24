# -*- coding: utf-8 -*-
"""tests/test_models_labels.py —— triple-barrier 标签：已知路径 + atr0 冻结。

用手工构造的 OHLC 路径精确断言标签方向（IMPLEMENTATION_SPEC §4.2）。
"""
from __future__ import annotations

import pandas as pd
import pytest

from _tp_bootstrap import ROOT  # noqa: F401  (sys.path 引导)
from core.data.bar import Bar
from core.models.labels import triple_barrier_labels

TS0 = pd.Timestamp("2024-01-01T00:00:00Z")


def _bar(i: int, o: float, h: float, l: float, c: float) -> Bar:
    return Bar(symbol="XAUUSD", ts_utc=TS0 + pd.Timedelta(minutes=5 * i),
               ts_server=TS0 + pd.Timedelta(hours=2) + pd.Timedelta(minutes=5 * i),
               server_offset_hours=2.0, open_=o, high=h, low=l, close=c,
               tick_volume=100.0)


def _make_bars(close_path: list[float], half_gap: float = 0.1) -> list[Bar]:
    bars = []
    for i, c in enumerate(close_path):
        o = close_path[i - 1] if i > 0 else c
        bars.append(_bar(i, o, c + half_gap, c - half_gap, c))
    return bars


def _atr_const(n: int, v: float = 1.0) -> pd.Series:
    return pd.Series([v] * n, dtype=float)


def test_up_path_hits_tp():
    bars = _make_bars([100.0 + 0.5 * i for i in range(20)])
    lab = triple_barrier_labels(bars, _atr_const(20), tp_mult=1.0, sl_mult=1.0,
                                max_holding_bars=10)
    # 入场 i=0：p0=100，上屏障=101；第 2 根 high=101.1 触上屏障 → +1
    assert lab.iloc[0] == 1


def test_down_path_hits_sl():
    bars = _make_bars([100.0 - 0.5 * i for i in range(20)])
    lab = triple_barrier_labels(bars, _atr_const(20), tp_mult=1.0, sl_mult=1.0,
                                max_holding_bars=10)
    # p0=100，下屏障=99；第 2 根 low=98.9 → -1
    assert lab.iloc[0] == -1


def test_flat_path_time_barrier_is_zero():
    bars = _make_bars([100.5] * 20)
    lab = triple_barrier_labels(bars, _atr_const(20), tp_mult=1.0, sl_mult=1.0,
                                max_holding_bars=10)
    assert lab.iloc[0] == 0


def test_same_bar_double_touch_conservative():
    # j=1：high=102（触上屏障101）且 low=98（触下屏障99）→ 保守判 -1
    bars = [_bar(0, 100.0, 100.1, 99.9, 100.0),
            _bar(1, 100.0, 102.0, 98.0, 101.5)]
    lab = triple_barrier_labels(bars, _atr_const(2), tp_mult=1.0, sl_mult=1.0,
                                max_holding_bars=10)
    assert lab.iloc[0] == -1


def test_atr0_frozen_not_recomputed():
    """入场 bar 的 atr0 被冻结；即使后续 atr 变大，标签仍用 atr[0]。"""
    # close 缓慢上行 0.3/bar：若用未来 atr[10]=10，屏障=110 永不触 → 0；
    # 用 atr[0]=1：上屏障=101，第 4 根 high≈101.45 → +1。
    close_path = [100.0 + 0.3 * i for i in range(20)]
    bars = _make_bars(close_path)
    atr = _atr_const(20, v=1.0)
    atr.iloc[10:] = 10.0  # 未来 ATR 放大（模拟重算泄漏的错误对照）
    lab = triple_barrier_labels(bars, atr, tp_mult=1.0, sl_mult=1.0,
                                max_holding_bars=10)
    assert lab.iloc[0] == 1


def test_bad_mult_raises():
    bars = _make_bars([100.0] * 5)
    with pytest.raises(ValueError):
        triple_barrier_labels(bars, _atr_const(5), tp_mult=0.0, sl_mult=1.0,
                              max_holding_bars=5)
