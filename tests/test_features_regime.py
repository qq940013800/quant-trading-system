# -*- coding: utf-8 -*-
"""tests/test_features_regime.py —— L2 regime 特征：取值域、分布归一化、单调性。"""
from __future__ import annotations

import numpy as np
import pytest

from _tp_bootstrap import make_synthetic_bars

from core.features.base import LookAheadError
from core.features.atr import wilder_atr
from core.features.volatility import realized_vol, atr_percentile_rank
from core.features.regime import adx, hurst_exponent, regime_weights
from core.features.structure import donchian_position, nearest_confirmed_swing
from core.features.patterns import bull_fvg, bull_engulfing


@pytest.fixture(scope="module")
def bars():
    return make_synthetic_bars(seed=23, n=400, kind="trend_regime")


def test_adx_hurst_domains(bars):
    as_of = bars[300].ts_utc
    a = adx(bars[:301], as_of, period=14)
    h = hurst_exponent(bars[:301], as_of, window=256, min_window=64)
    assert np.isfinite(a) and 0.0 <= a <= 100.0
    assert np.isfinite(h) and 0.0 <= h <= 1.0


def test_realized_vol_positive(bars):
    as_of = bars[200].ts_utc
    v = realized_vol(bars[:201], as_of, window=48)
    assert np.isfinite(v) and v > 0.0


def test_atr_percentile_rank_in_unit_interval(bars):
    as_of = bars[250].ts_utc
    atr_arr = np.array([wilder_atr(bars[: i + 1], bars[i].ts_utc, period=14)
                        for i in range(251)])
    pct = atr_percentile_rank(bars[:251], as_of, atr_arr, period=14, min_history=96)
    assert 0.0 <= pct <= 1.0


def test_donchian_position_unit_interval(bars):
    as_of = bars[200].ts_utc
    d = donchian_position(bars[:201], as_of, window=20)
    assert np.isfinite(d) and 0.0 <= d <= 1.0


def test_regime_weights_sum_to_one_and_bounded():
    w = regime_weights(adx_val=40.0, hurst_val=0.6, atr_pct=0.3,
                        adx_q_lo=15.0, adx_q_hi=35.0)
    assert set(w) == {"w_trend", "w_mr", "w_range"}
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert all(0.0 <= v <= 1.0 for v in w.values())
    # NaN 输入 → 均匀分布（防御）
    w_nan = regime_weights(np.nan, np.nan, np.nan, adx_q_lo=15.0, adx_q_hi=35.0)
    assert all(abs(v - 1.0 / 3) < 1e-9 for v in w_nan.values())


def test_regime_weights_distribution_thresholds_not_arbitrary():
    # adx 高于高分位 → w_trend=1（纯趋势）
    w = regime_weights(adx_val=100.0, hurst_val=0.5, atr_pct=0.5,
                       adx_q_lo=15.0, adx_q_hi=35.0)
    assert w["w_trend"] == pytest.approx(1.0)
    # adx 低于低分位 + hurst<0.5 → MR 权重 > 0
    w2 = regime_weights(adx_val=5.0, hurst_val=0.2, atr_pct=0.9,
                         adx_q_lo=15.0, adx_q_hi=35.0)
    assert w2["w_mr"] > 0.0


def test_patterns_boolean_domain(bars):
    as_of = bars[100].ts_utc
    f = bull_fvg(bars[:101], as_of)
    e = bull_engulfing(bars[:101], as_of)
    assert f in (0.0, 1.0)
    assert e in (0.0, 1.0)


def test_swing_no_lookahead(bars):
    """swing 计算只用 <= as_of 的 bar；喂未来 bar 必被 decorator 拒绝。"""
    t = 200
    as_of = bars[t].ts_utc
    s = nearest_confirmed_swing(bars[: t + 1], as_of, k=3)
    assert set(s) == {"dist_high", "dist_low"}
    with pytest.raises(LookAheadError):
        nearest_confirmed_swing(bars, as_of, k=3)
