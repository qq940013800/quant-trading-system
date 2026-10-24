# -*- coding: utf-8 -*-
"""测试支撑：最小 Bar/Schema 与确定性合成 bar 序列（解耦未就绪的 core/data）。

schema 字段与 docs/trading/AI_ML_SYSTEM_DESIGN.md 3.1 对齐。
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# 保证 D:\Trader 在 sys.path，使 `import core.*` 在任意 cwd 下可用
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass(frozen=True)
class Bar:
    symbol: str
    ts_utc: pd.Timestamp
    ts_server: pd.Timestamp
    server_offset_hours: float
    open_: float
    high: float
    low: float
    close: float
    tick_volume: float = 1000.0
    spread_points: Optional[float] = None


def _ts(i: int, freq: str = "5min") -> pd.Timestamp:
    base = pd.Timestamp("2021-01-04 00:00", tz="UTC")
    return base + pd.Timedelta(i, unit="m" if freq == "5min" else "m") * 1


def make_bar(i: int, open_: float, high: float, low: float, close: float,
             symbol: str = "XAUUSD", tick_volume: float = 1000.0) -> Bar:
    ts = pd.Timestamp("2021-01-04 00:00", tz="UTC") + pd.Timedelta(minutes=5 * i)
    return Bar(symbol=symbol, ts_utc=ts, ts_server=ts, server_offset_hours=2.0,
               open_=float(open_), high=float(high), low=float(low),
               close=float(close), tick_volume=float(tick_volume))


def make_bars(prices: list[float], spread: float = 0.2, vol: float = 1000.0) -> list[Bar]:
    """由收盘价序列构造 OHLC 持平的合成 bar（open=close=prices[k]，high/low 包络）。"""
    bars = []
    for k, c in enumerate(prices):
        o = prices[k - 1] if k > 0 else c
        h = max(o, c) + spread / 2
        lo = min(o, c) - spread / 2
        bars.append(make_bar(k, open_=o, high=h, low=lo, close=c, tick_volume=vol))
    return bars


def make_trend_bars(n: int = 200, seed: int = 7, start: float = 1800.0,
                    step: float = 0.5) -> list[Bar]:
    """确定性带噪趋势序列（可复现），用于突破策略触发。"""
    rng = np.random.default_rng(seed)
    prices = [start]
    for _ in range(n - 1):
        prices.append(prices[-1] + step + rng.normal(0, 0.3))
    return make_bars(prices)


@dataclass(frozen=True)
class Signal:
    signal_id: str
    bar_ts_utc: pd.Timestamp
    expert: str
    direction: int
    price_ref: float
    atr0: float
    entry_dist: float
    l1_in_zone: bool = True
    regime_weights: dict = field(default_factory=dict)
    meta_p: Optional[float] = None
