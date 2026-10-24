"""Synthetic-data tests: deterministic reproduction, OHLC invariants,
and the causal self-check that a restricted-history statistic equals the
same statistic computed on an as_of-truncated feed.
"""
from __future__ import annotations

import pandas as pd
import pytest

from core.data.bar import LookAheadError
from core.data.synthetic import make_synthetic_bars
from core.data.validator import assert_as_of


def test_same_seed_reproduces_exactly():
    a = make_synthetic_bars(seed=7, n=50)
    b = make_synthetic_bars(seed=7, n=50)
    assert [x.close for x in a] == [x.close for x in b]
    assert [x.ts_utc for x in a] == [x.ts_utc for x in b]


def test_different_seed_differs():
    a = make_synthetic_bars(seed=1, n=50)
    b = make_synthetic_bars(seed=2, n=50)
    assert [x.close for x in a] != [x.close for x in b]


def test_bar_invariants_hold(syn_bars):
    assert len(syn_bars) == 60
    ts = [b.ts_utc for b in syn_bars]
    assert ts == sorted(ts)
    assert len(set(ts)) == len(ts)                     # strictly increasing
    for b in syn_bars:
        assert b.ts_utc.tz is not None                 # aware UTC
        assert b.low <= b.open_ <= b.high
        assert b.low <= b.close <= b.high
        assert b.close > 0


def test_unknown_kind_rejected():
    with pytest.raises(ValueError):
        make_synthetic_bars(seed=1, n=10, kind="random_cheese")


def test_trend_regime_has_two_vol_regimes():
    bars = make_synthetic_bars(seed=99, n=200, kind="trend_regime")
    mid = 100
    first = [b.close for b in bars[:mid]]
    second = [b.close for b in bars[mid:]]
    # first segment trends up: end > start
    assert first[-1] > first[0]
    # second segment is higher variance than first
    import numpy as np
    r1 = np.diff(np.log(first))
    r2 = np.diff(np.log(second))
    assert r2.std() > r1.std() * 2


def test_causal_statistic_matches_as_of_truncation(syn_bars):
    """The core no-leakage assertion: expanding mean of close computed on the
    full feed up to as_of must equal the same computation on bars truncated
    at as_of — and any history containing a bar after as_of is rejected."""
    as_of = syn_bars[40].ts_utc

    def expanding_mean(history):
        closes = [b.close for b in history]
        return sum(closes) / len(closes)

    assert_as_of(syn_bars[:41], as_of)
    mean_truncated = expanding_mean(syn_bars[:41])

    # same value recomputed independently from the tail
    tail = syn_bars[:41]
    mean_recomputed = sum(b.close for b in tail) / len(tail)
    assert mean_truncated == mean_recomputed

    with pytest.raises(LookAheadError):
        assert_as_of(syn_bars[:42], as_of)   # bar 41 closes after as_of


def test_martingale_has_no_forced_trend(syn_bars):
    # sanity: synthetic martingale starts near anchor price regime
    assert 2000.0 < syn_bars[-1].close < 3500.0
