# -*- coding: utf-8 -*-
"""tests/test_models_gbm.py —— LightGBM 封装（importorskip 隔离）。

无 lightgbm 环境本文件 skip 不失败（设计文档⑤⑦A.3）。
"""
from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("lightgbm")

from _tp_bootstrap import ROOT  # noqa: E402
from core.models.gbm import LightGBMWrapper, has_lightgbm  # noqa: E402


def _data(n=400, seed=0):
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, 4))
    y = (X[:, 0] + 0.5 * X[:, 1] > 0).astype(float)
    return X, y


def test_gbm_interface():
    assert has_lightgbm()
    X, y = _data()
    X_tr, y_tr = X[:300], y[:300]
    X_va, y_va = X[300:], y[300:]
    m = LightGBMWrapper(max_depth=4, n_estimators=50, early_stopping_rounds=5)
    m.fit(X_tr, y_tr, X_eval=X_va, y_eval=y_va)
    p = m.predict_proba(X_va)
    assert p.shape == (100, 2)
    assert np.all(p >= 0) and np.allclose(p.sum(axis=1), 1.0)
    assert m.version.startswith("gbm-lgbm")


def test_gbm_depth_bounds_enforced():
    with pytest.raises(ValueError):
        LightGBMWrapper(max_depth=2)  # 设计约束 3-6


@pytest.mark.parametrize("bad", [True, 1.5, "4", 2, 7])
def test_gbm_max_depth_must_be_int_in_3_6(bad):
    with pytest.raises(ValueError, match="max_depth"):
        LightGBMWrapper(max_depth=bad)


@pytest.mark.parametrize("bad", [True, "0.05", None, 0.0, 1.5,
                                  float("nan"), float("inf")])
def test_gbm_learning_rate_must_be_ratio(bad):
    with pytest.raises(ValueError, match="learning_rate"):
        LightGBMWrapper(learning_rate=bad)


@pytest.mark.parametrize("bad", [True, 0.0, 1.5, None])
def test_gbm_subsample_must_be_ratio(bad):
    with pytest.raises(ValueError, match="subsample"):
        LightGBMWrapper(subsample=bad)


@pytest.mark.parametrize("bad", [True, 1.5, 0, "300"])
def test_gbm_n_estimators_must_be_pos_int(bad):
    with pytest.raises(ValueError, match="n_estimators"):
        LightGBMWrapper(n_estimators=bad)


@pytest.mark.parametrize("bad", [True, 2.0, -1, "30"])
def test_gbm_early_stopping_must_be_nonneg_int(bad):
    with pytest.raises(ValueError, match="early_stopping_rounds"):
        LightGBMWrapper(early_stopping_rounds=bad)


@pytest.mark.parametrize("bad", [True, 1.5, -1, "7"])
def test_gbm_random_state_must_be_nonneg_int(bad):
    with pytest.raises(ValueError, match="random_state"):
        LightGBMWrapper(random_state=bad)


def test_gbm_valid_params_accepted():
    m = LightGBMWrapper(max_depth=4, learning_rate=0.05, n_estimators=100,
                        subsample=0.8, early_stopping_rounds=10, random_state=0)
    assert m.max_depth == 4
    assert m.n_estimators == 100
    assert m.params["learning_rate"] == pytest.approx(0.05)
