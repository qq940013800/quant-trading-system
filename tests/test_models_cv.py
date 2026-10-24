# -*- coding: utf-8 -*-
"""tests/test_models_cv.py —— purged walk-forward：embargo/防泄漏约束断言。"""
from __future__ import annotations

import numpy as np
import pytest

from _tp_bootstrap import ROOT  # noqa: F401
from core.models.cv import purged_walk_forward, PurgedCVError


def test_embargo_smaller_than_label_window_raises():
    with pytest.raises(PurgedCVError):
        purged_walk_forward(n=1000, embargo_bars=5, n_splits=4,
                            label_window_bars=12)


def test_no_random_kfold_and_chronological():
    folds = purged_walk_forward(n=1000, embargo_bars=12, n_splits=4,
                                label_window_bars=12)
    assert len(folds) == 4
    prev_test_end = -1
    for tr, te in folds:
        assert tr.max() < te.min()                       # train 全在 test 之前
        assert np.array_equal(te, np.arange(te.min(), te.max() + 1))  # test 连续块
        assert te.min() >= prev_test_end                 # test 块时间有序
        prev_test_end = te.max() + 1


def test_purge_gap_before_test():
    """train 末尾必须留出 embargo_bars（覆盖标签窗口）。"""
    n, embargo, splits = 1000, 12, 4
    folds = purged_walk_forward(n=n, embargo_bars=embargo, n_splits=splits,
                                label_window_bars=embargo)
    warm = n // (splits + 1)
    for k, (tr, te) in enumerate(folds):
        test_start = (k + 1) * warm
        assert tr.max() <= test_start - embargo   # purge：剔除与 test 标签重叠段


def test_embargo_after_previous_test_blocks_excluded():
    n, embargo, splits = 1000, 12, 4
    warm = n // (splits + 1)
    folds = purged_walk_forward(n=n, embargo_bars=embargo, n_splits=splits,
                                label_window_bars=embargo)
    # fold k 的 train 不得落入此前任一 test 块之后的 embargo 段
    for k, (tr, te) in enumerate(folds):
        for j in range(k):
            prev_e = (j + 2) * warm
            leak = [i for i in range(prev_e, prev_e + embargo) if i in set(tr.tolist())]
            assert leak == [], f"fold {k} train contains embargo-after-test{j}: {leak}"


def test_invalid_layout_raises():
    with pytest.raises(PurgedCVError):
        purged_walk_forward(n=20, embargo_bars=5, n_splits=4)  # warmup 太小
