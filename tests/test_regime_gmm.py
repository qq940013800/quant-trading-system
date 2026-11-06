# -*- coding: utf-8 -*-
"""tests/test_regime_gmm.py —— GMM 软概率层：拟合、分量→状态对齐、降级隔离。"""
from __future__ import annotations

import numpy as np
import pytest

import core.regime.gmm as gmm_mod
from core.regime.gmm import GMMRegimeModel, has_gmm
from core.regime.rules import STATE_MEAN_REVERSION, STATE_RANGING, STATE_TREND


@pytest.fixture(scope="module")
def three_clusters():
    """三个在 (adx, hurst, atr_pct) 上可分的确定性高斯簇。"""
    rng = np.random.default_rng(11)
    trend = rng.normal([60.0, 0.75, 3e-4], [2.0, 0.03, 2e-5], size=(80, 3))
    mr = rng.normal([10.0, 0.25, 1.5e-4], [2.0, 0.03, 2e-5], size=(80, 3))
    ranging = rng.normal([22.0, 0.5, 1.0e-4], [2.0, 0.03, 2e-5], size=(80, 3))
    return np.vstack([trend, mr, ranging])


def test_gmm_fit_and_posterior_sum_to_one(three_clusters):
    if not has_gmm():
        pytest.importorskip("sklearn.mixture")
    model = GMMRegimeModel(random_state=7).fit(three_clusters)
    p = model.predict_probs(three_clusters[0])
    assert p is not None
    assert set(p) == {STATE_TREND, STATE_MEAN_REVERSION, STATE_RANGING}
    assert sum(p.values()) == pytest.approx(1.0)
    assert all(0.0 <= v <= 1.0 for v in p.values())


def test_gmm_component_alignment_sends_trend_cluster_to_trend(three_clusters):
    if not has_gmm():
        pytest.importorskip("sklearn.mixture")
    model = GMMRegimeModel(random_state=7).fit(three_clusters)
    # 趋势质心（高 adx）→ trend 后验占优
    p = model.predict_probs([60.0, 0.75, 3e-4])
    assert p[STATE_TREND] > p[STATE_MEAN_REVERSION]
    assert p[STATE_TREND] > p[STATE_RANGING]
    # 反持续质心（低 hurst、低 adx）→ mean_reversion 占优
    p_mr = model.predict_probs([10.0, 0.25, 1.5e-4])
    assert p_mr[STATE_MEAN_REVERSION] > p_mr[STATE_TREND]


def test_gmm_nan_row_returns_none(three_clusters):
    if not has_gmm():
        pytest.importorskip("sklearn.mixture")
    model = GMMRegimeModel(random_state=7).fit(three_clusters)
    assert model.predict_probs([np.nan, 0.5, 2e-4]) is None
    assert model.predict_probs([60.0, np.nan, 2e-4]) is None


def test_gmm_rejects_bad_shape_and_short_data(three_clusters):
    if not has_gmm():
        pytest.importorskip("sklearn.mixture")
    model = GMMRegimeModel(random_state=7)
    with pytest.raises(ValueError, match="shape"):
        model.fit(three_clusters[:, :2])  # 缺一列
    with pytest.raises(ValueError, match="needs"):
        model.fit(three_clusters[:10])  # 不足 MIN_FIT_ROWS


def test_gmm_unavailable_raises_contextual_runtimeerror(monkeypatch):
    """import 隔离：模拟 sklearn 缺失，构造时抛带上下文 RuntimeError（非裸 except）。"""
    monkeypatch.setattr(gmm_mod, "_HAS_GMM", False)
    with pytest.raises(RuntimeError, match="unavailable"):
        GMMRegimeModel()
