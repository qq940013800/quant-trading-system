"""Deterministic synthetic bars for unit tests and the pipeline no-leakage
self-check: if a research pipeline is profitable on a pure martingale walk,
it contains look-ahead leakage (DATA_INGESTION.md §5).

Frozen signature (AI_ML_SYSTEM_DESIGN.md §3.2):
    make_synthetic_bars(seed, n, kind="martingale") -> list[Bar]
Determinism: np.random.default_rng(seed) only — same seed reproduces bytes.
Never calibrate thresholds on synthetic data; it exists to be wrong about.
"""
from __future__ import annotations

import logging
from typing import List

import numpy as np
import pandas as pd

from .bar import Bar

log = logging.getLogger("core.data.synthetic")

ORIGIN = pd.Timestamp("2024-01-01T00:00:00Z")  # fixed synthetic clock anchor
BAR_MINUTES = 5
START_PRICE = 2600.0      # XAUUSD-like level (test fixture only, not a market constant)
MART_SIGMA = 0.0008       # per-bar log-return vol, ~ target ATR scale for tests


def _bars_from_returns(symbol: str, rets: np.ndarray, rng: np.random.Generator) -> List[Bar]:
    closes = START_PRICE * np.exp(np.cumsum(rets))
    bars: List[Bar] = []
    prev_close = START_PRICE
    n = len(rets)
    for i in range(n):
        ts_utc = ORIGIN + pd.Timedelta(minutes=BAR_MINUTES * i)
        o = prev_close
        c = float(closes[i])
        # intrabar excursion: deterministic per-bar draws from the SAME rng
        up = abs(rng.normal(0.0, MART_SIGMA)) * c
        dn = abs(rng.normal(0.0, MART_SIGMA)) * c
        h = max(o, c) + up
        l = min(o, c) - dn
        tv = float(rng.integers(50, 500))
        bars.append(Bar(
            symbol=symbol,
            ts_utc=ts_utc,
            ts_server=ts_utc.tz_localize(None),   # offset 0: server == UTC here
            server_offset_hours=0.0,
            open_=o, high=h, low=l, close=c,
            tick_volume=tv, spread_points=None,
        ))
        prev_close = c
    return bars


def make_synthetic_bars(seed: int, n: int, kind: str = "martingale") -> List[Bar]:
    """Generate n deterministic bars.

    kind="martingale": zero-drift random walk, constant per-bar vol — any
        strategy that "profits" here is leaking future information.
    kind="trend_regime": low-vol upward-trend first segment, high-vol chop
        second segment; the breakpoint (n//2) is known to tests.
    """
    if n <= 0:
        raise ValueError("n must be positive")
    rng = np.random.default_rng(seed)

    if kind == "martingale":
        rets = rng.normal(0.0, MART_SIGMA, size=n)
    elif kind == "trend_regime":
        half = n // 2
        first = rng.normal(0.0006, 0.0004, size=half)     # low-vol trend up
        rest = rng.normal(0.0, 0.0025, size=n - half)     # high-vol chop
        rets = np.concatenate([first, rest])
    else:
        raise ValueError(f"unknown synthetic kind {kind!r}; "
                         f"expected 'martingale' or 'trend_regime'")

    bars = _bars_from_returns("XAUUSD_SYN", rets, rng)
    log.info("synthetic bars: seed=%d n=%d kind=%s", seed, n, kind)
    return bars
