# -*- coding: utf-8 -*-
"""tests/test_models_meta_label.py —— MetaLabeler 分位参数守卫与分布敏感性。"""
from __future__ import annotations

import numpy as np
import pytest

from core.models.meta_label import MetaLabeler


class _Stub:
    version = "stub"


class _ProbStub:
    """按注入概率返回 predict_proba 的桩模型（不引入真实依赖）。"""

    version = "stub"

    def __init__(self, probs):
        self._probs = np.asarray(probs, dtype=float)

    def fit(self, X, y):
        return self

    def predict_proba(self, X):
        n = len(X)
        p = self._probs[:n] if n <= len(self._probs) else np.full(n, self._probs[0])
        return np.column_stack([1.0 - p, p])


def _labeler(**kw):
    base = dict(base_model=_Stub(), q_lo=0.30, q_hi=0.70)
    base.update(kw)
    return MetaLabeler(**base)


@pytest.mark.parametrize("bad", [True, "0.3", None, float("nan"),
                                 float("inf"), 0.70, 1.0])
def test_rejects_bad_q_lo(bad):
    with pytest.raises(ValueError):
        _labeler(q_lo=bad)


@pytest.mark.parametrize("bad", [True, "0.7", None, float("nan"),
                                 float("inf"), 0.20, 1.5])
def test_rejects_bad_q_hi(bad):
    with pytest.raises(ValueError):
        _labeler(q_hi=bad)


def test_valid_quantiles_accepted():
    m = _labeler(q_lo=0.25, q_hi=0.75)
    assert m.q_lo == pytest.approx(0.25)
    assert m.q_hi == pytest.approx(0.75)


def test_quantile_thresholds_follow_training_distribution():
    """G4 验收：分位阈值随训练分布移动，而非固定 0.55/0.45。"""
    high = MetaLabeler(
        _ProbStub([0.70, 0.80, 0.85, 0.90, 0.95]), 0.30, 0.70
    ).fit(np.zeros((5, 2)), np.ones(5))
    low = MetaLabeler(
        _ProbStub([0.05, 0.10, 0.15, 0.20, 0.30]), 0.30, 0.70
    ).fit(np.zeros((5, 2)), np.ones(5))
    # 高位分布的下沿分位仍高于低位分布的上沿分位
    assert high._q_lo_val > low._q_hi_val
    # 阈值取自训练概率分位，不落到固定字面量
    assert high._q_lo_val != pytest.approx(0.55)
    assert low._q_hi_val != pytest.approx(0.45)


def test_predict_prob_and_k_in_unit_range():
    m = MetaLabeler(
        _ProbStub([0.20, 0.40, 0.60, 0.80]), 0.30, 0.70
    ).fit(np.zeros((4, 2)), np.ones(4))
    p, k = m.predict(np.zeros((1, 2)))
    assert np.all((p >= 0.0) & (p <= 1.0))
    assert np.all((k >= 0.0) & (k <= 1.0))
