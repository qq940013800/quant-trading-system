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
