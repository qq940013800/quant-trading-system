# -*- coding: utf-8 -*-
"""tests/test_regime_classifier.py —— RegimeClassifier 端到端：因果守卫、
CLEAN 集纪律、概率归一、合成数据状态可解释性、GMM 不可用降级。"""
from __future__ import annotations

import numpy as np
import pytest

from _tp_bootstrap import make_synthetic_bars  # 测试引导：项目根入 sys.path
from _bt_helpers import make_trend_bars

from core.features.base import LookAheadError
from core.features.atr import wilder_atr
from core.features.regime import adx, hurst_exponent
from core.regime import (
    RegimeClassifier,
    STATE_MEAN_REVERSION,
    STATE_RANGING,
    STATE_TREND,
)
import core.regime.gmm as gmm_mod


@pytest.fixture(scope="module")
def clean_bars():
    """CLEAN 训练段：trend_regime = 前半低波上行、后半高波震荡（断点在 n//2）。"""
    return make_synthetic_bars(seed=5, n=800, kind="trend_regime")


@pytest.fixture(scope="module")
def clf(clean_bars):
    return RegimeClassifier().fit(clean_bars)


# ------------------------------------------------------------- 因果守卫
def test_predict_with_future_bars_raises_lookahead(clf, clean_bars):
    t = 300
    as_of = clean_bars[t].ts_utc
    out = clf.predict(clean_bars[: t + 1], as_of)  # 截断历史：必须成功
    assert out.state in (STATE_TREND, STATE_MEAN_REVERSION, STATE_RANGING)
    with pytest.raises(LookAheadError):
        clf.predict(clean_bars, as_of)  # 全量含未来 bar：守卫必须拒绝


def test_predict_snapshot_deterministic_under_future_append(clf, clean_bars):
    """同一 (history[:t+1], as_of) 重算结果不变（黄金因果不变量）。"""
    t = 300
    as_of = clean_bars[t].ts_utc
    r1 = clf.predict(clean_bars[: t + 1], as_of)
    r2 = clf.predict(clean_bars[: t + 1], as_of)
    assert r1.state == r2.state
    assert r1.probs == pytest.approx(r2.probs)


# ------------------------------------------------------------- CLEAN 纪律
def test_fit_uses_only_cLEAN_segment_not_full_sample(clean_bars):
    half = 400
    train_only = RegimeClassifier().fit(clean_bars[:half])
    thr_train = train_only._thr
    # 全样本（后半段是高波震荡）atr_q_hi 必然 > 仅训练段派生值
    atr_rows = []
    for i in range(len(clean_bars)):
        h, a = hurst_exponent(clean_bars[: i + 1], clean_bars[i].ts_utc,
                              window=256, min_window=64), \
               wilder_atr(clean_bars[: i + 1], clean_bars[i].ts_utc, period=14)
        close = clean_bars[i].close
        atr_rows.append(float(a) / close if np.isfinite(a) else np.nan)
    atr_all = np.array(atr_rows, dtype=float)
    atr_all = atr_all[np.isfinite(atr_all)]
    assert thr_train.atr_q_hi < np.quantile(atr_all, 0.70)


def test_fit_with_as_of_end_matches_explicit_slice(clean_bars):
    half = 400
    clipped = RegimeClassifier().fit(
        clean_bars, as_of_end=clean_bars[half - 1].ts_utc)
    direct = RegimeClassifier().fit(clean_bars[:half])
    assert clipped._thr == direct._thr


def test_predict_does_not_refit(clf, clean_bars):
    thr_before = clf._thr
    gmm_before = clf._gmm
    for t in (300, 310, 320):
        clf.predict(clean_bars[: t + 1], clean_bars[t].ts_utc)
    assert clf._thr is thr_before
    assert clf._gmm is gmm_before


# ------------------------------------------------------------- 输出契约
def test_output_contract_fields(clf, clean_bars):
    out = clf.predict(clean_bars[: 301], clean_bars[300].ts_utc)
    assert out.threshold_dataset == "CLEAN"
    assert out.version.startswith("regime-rules-gmm-v1")
    assert set(out.probs) == {STATE_TREND, STATE_MEAN_REVERSION, STATE_RANGING}
    assert sum(out.probs.values()) == pytest.approx(1.0)


def test_predict_before_fit_raises_contextual_runtimeerror(clean_bars):
    bare = RegimeClassifier()
    with pytest.raises(RuntimeError, match="not fitted"):
        bare.predict(clean_bars[:10], clean_bars[9].ts_utc)


# ------------------------------------------------- 合成数据状态可解释性
def test_strong_trend_feed_classified_trend(clf):
    feed = make_trend_bars(n=500, seed=7, start=1800.0, step=1.0)
    t = 460
    out = clf.predict(feed[: t + 1], feed[t].ts_utc)
    assert out.state == STATE_TREND
    assert out.probs[STATE_TREND] >= 1.0 / 3


def test_pure_martingale_chop_not_classified_trend(clf):
    chop = make_synthetic_bars(seed=9, n=600, kind="martingale")
    t = 400
    out = clf.predict(chop[: t + 1], chop[t].ts_utc)
    # 纯随机游走无趋势：硬状态不得为 trend（whipsaw 区不硬切）
    assert out.state in (STATE_MEAN_REVERSION, STATE_RANGING)


# ------------------------------------------------- GMM 不可用降级
def test_gmm_unavailable_degrades_to_rule_only(monkeypatch, clean_bars):
    monkeypatch.setattr(gmm_mod, "_HAS_GMM", False)
    degraded_clf = RegimeClassifier(use_gmm=True).fit(clean_bars)
    assert degraded_clf._gmm_active is False
    t = 300
    out = degraded_clf.predict(clean_bars[: t + 1], clean_bars[t].ts_utc)
    assert out.version.endswith("/rules-only")
    assert out.degraded is True  # 显式标注：软概率层降级为规则映射
    assert sum(out.probs.values()) == pytest.approx(1.0)


def test_rule_only_mode_by_config(clean_bars):
    cfg_clf = RegimeClassifier(use_gmm=False).fit(clean_bars)
    assert cfg_clf._gmm is None
    out = cfg_clf.predict(clean_bars[: 301], clean_bars[300].ts_utc)
    assert out.version.endswith("/rules-only")
