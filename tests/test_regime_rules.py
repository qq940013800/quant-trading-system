# -*- coding: utf-8 -*-
"""tests/test_regime_rules.py —— 规则层：状态可解释性、分布派生阈值、归一化。"""
from __future__ import annotations

import numpy as np
import pytest

from core.regime.rules import (
    MR_HURST_THRESHOLD,
    STATE_MEAN_REVERSION,
    STATE_RANGING,
    STATE_TREND,
    RuleThresholds,
    derive_thresholds,
    rule_state_and_soft_probs,
)


@pytest.fixture
def thr() -> RuleThresholds:
    # 直接给出一条 deadband（测试阈值派生用夹具），q 级别仅审计标签
    return RuleThresholds(adx_q_lo=15.0, adx_q_hi=35.0,
                          atr_q_lo=1e-4, atr_q_hi=3e-4, q_lo=0.30, q_hi=0.70)


def test_derive_thresholds_matches_numpy_quantile():
    # 偏态双峰分布：50 个低值 + 50 个高值
    adx = np.concatenate([np.full(50, 5.0), np.full(50, 60.0)])
    atr = np.concatenate([np.full(50, 1e-4), np.full(50, 9e-4)])
    out = derive_thresholds(adx, atr, q_lo=0.30, q_hi=0.70)
    assert out.adx_q_lo == pytest.approx(np.quantile(adx, 0.30))
    assert out.adx_q_hi == pytest.approx(np.quantile(adx, 0.70))
    assert out.atr_q_lo == pytest.approx(np.quantile(atr, 0.30))
    assert out.atr_q_hi == pytest.approx(np.quantile(atr, 0.70))


def test_derive_thresholds_rejects_degenerate_distribution():
    adx = np.full(20, 20.0)  # 全相同 → 分位退化 q_hi <= q_lo
    atr = np.linspace(1e-4, 3e-4, 20)
    with pytest.raises(ValueError, match="degenerate"):
        derive_thresholds(adx, atr)


def test_derive_thresholds_rejects_bad_quantile_levels():
    with pytest.raises(ValueError, match="quantile levels"):
        derive_thresholds(np.full(20, 1.0), np.full(20, 1e-4), q_lo=0.8, q_hi=0.2)


def test_rule_state_trend_when_adx_above_hi(thr):
    feat = {"adx": 60.0, "hurst": 0.5, "atr_pct": 2e-4}
    state, probs, degraded = rule_state_and_soft_probs(feat, thr)
    assert state == STATE_TREND
    assert not degraded
    assert probs[STATE_TREND] == pytest.approx(1.0)


def test_rule_state_mean_reversion_when_anti_persistent_low_adx(thr):
    feat = {"adx": 5.0, "hurst": 0.2, "atr_pct": 1.5e-4}
    state, probs, degraded = rule_state_and_soft_probs(feat, thr)
    assert state == STATE_MEAN_REVERSION
    assert not degraded
    assert probs[STATE_MEAN_REVERSION] > probs[STATE_TREND]


def test_rule_state_ranging_in_deadband(thr):
    # adx 在 deadband 内、hurst≈0.5（随机游走）→ ranging，非硬切
    feat = {"adx": 25.0, "hurst": 0.5, "atr_pct": 2e-4}
    state, probs, degraded = rule_state_and_soft_probs(feat, thr)
    assert state == STATE_RANGING
    assert not degraded


def test_rule_probs_sum_to_one_and_bounded(thr):
    for feat in ({"adx": 60.0, "hurst": 0.5, "atr_pct": 2e-4},
                 {"adx": 5.0, "hurst": 0.2, "atr_pct": 1.5e-4},
                 {"adx": 25.0, "hurst": 0.5, "atr_pct": 2e-4}):
        _, probs, _ = rule_state_and_soft_probs(feat, thr)
        assert set(probs) == {STATE_TREND, STATE_MEAN_REVERSION, STATE_RANGING}
        assert sum(probs.values()) == pytest.approx(1.0)
        assert all(0.0 <= v <= 1.0 for v in probs.values())


def test_rule_nan_features_fallback_uniform_with_degraded_flag(thr):
    feat = {"adx": np.nan, "hurst": np.nan, "atr_pct": np.nan}
    state, probs, degraded = rule_state_and_soft_probs(feat, thr)
    assert state == STATE_RANGING
    assert degraded
    assert all(v == pytest.approx(1.0 / 3) for v in probs.values())


def test_hurst_theory_constant_is_documented_random_walk_boundary():
    # 理论常量：R/S Hurst=0.5 随机游走分界（非绩效参数）
    assert MR_HURST_THRESHOLD == 0.5


class TestRuleThresholdsGuards:
    @staticmethod
    def _make(**kw):
        base = dict(adx_q_lo=15.0, adx_q_hi=35.0,
                    atr_q_lo=1e-4, atr_q_hi=3e-4, q_lo=0.30, q_hi=0.70)
        base.update(kw)
        return RuleThresholds(**base)

    @pytest.mark.parametrize("kwargs", [
        {"adx_q_lo": np.nan}, {"adx_q_hi": np.inf},
        {"atr_q_lo": True}, {"atr_q_hi": np.nan},
        {"q_lo": np.nan},
    ])
    def test_non_finite_rejected(self, kwargs):
        with pytest.raises(ValueError):
            self._make(**kwargs)

    @pytest.mark.parametrize("kwargs", [
        {"adx_q_lo": 35.0, "adx_q_hi": 15.0},
        {"atr_q_lo": 3e-4, "atr_q_hi": 1e-4},
        {"adx_q_lo": 20.0, "adx_q_hi": 20.0},
    ])
    def test_degenerate_band_rejected(self, kwargs):
        with pytest.raises(ValueError):
            self._make(**kwargs)

    @pytest.mark.parametrize("kwargs", [
        {"q_lo": 0.8, "q_hi": 0.2}, {"q_lo": 0.0, "q_hi": 0.7},
        {"q_lo": 0.3, "q_hi": 1.0}, {"q_lo": 0.5, "q_hi": 0.5},
    ])
    def test_quantile_levels_rejected(self, kwargs):
        with pytest.raises(ValueError):
            self._make(**kwargs)

    def test_valid_thresholds_accepted(self):
        t = self._make()
        assert t.adx_q_lo == 15.0 and t.q_hi == 0.70
