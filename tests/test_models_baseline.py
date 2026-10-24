# -*- coding: utf-8 -*-
"""tests/test_models_baseline.py —— 线性基线接口与可学习性（纯 numpy，无 sklearn 依赖）。"""
from __future__ import annotations

import numpy as np
import pytest

from _tp_bootstrap import ROOT  # noqa: F401
from core.models.baseline import LogisticBaseline, RidgeBaseline, permutation_importance


def _separable(n=400, seed=0):
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, 3))
    y = (X[:, 0] > 0.0).astype(float)  # 只由第 0 维决定
    return X, y


def test_logistic_fit_separable():
    X, y = _separable()
    m = LogisticBaseline(C=1.0).fit(X, y)
    pred = (m.predict_proba(X)[:, 1] >= 0.5).astype(float)
    assert (pred == y).mean() > 0.95
    assert m.version.startswith("baseline-logistic")


def test_predict_proba_bounded_and_normalized():
    X, y = _separable(n=100)
    m = LogisticBaseline().fit(X, y)
    p = m.predict_proba(X)
    assert p.shape == (100, 2)
    assert np.all(p >= 0) and np.all(p <= 1)
    assert np.allclose(p.sum(axis=1), 1.0)


def test_ridge_learns_simple_relation():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(300, 2))
    y = 2.0 * X[:, 0] - X[:, 1] + rng.normal(scale=0.01, size=300)
    m = RidgeBaseline(alpha=0.1).fit(X, y)
    pred = m.predict(X)
    assert np.abs(pred - y).mean() < 0.05


def test_permutation_importance_ranks_true_feature():
    X, y = _separable()
    m = LogisticBaseline().fit(X, y)
    imp = permutation_importance(m, X, y, seed=0, n_repeats=3)
    assert imp[0] > imp[1]  # 真特征列 > 噪声列


def test_unfitted_raises():
    m = LogisticBaseline()
    with pytest.raises(RuntimeError):
        m.predict_proba(np.zeros((1, 3)))
