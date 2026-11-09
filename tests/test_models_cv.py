# -*- coding: utf-8 -*-
"""tests/test_models_cv.py —— purged walk-forward：embargo/防泄漏约束断言。"""
from __future__ import annotations

import math

import numpy as np
import pytest

from _tp_bootstrap import ROOT  # noqa: F401
from core.models.cv import (
    PurgedCVError,
    combinatorial_purged_folds,
    purged_walk_forward,
)


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


class TestConstructorGuards:
    @pytest.mark.parametrize("kw", [
        {"n": 1000.0}, {"n": -1}, {"n": 0}, {"n": "1000"},
        {"embargo_bars": 3.0}, {"embargo_bars": -1},
        {"n_splits": 4.0}, {"n_splits": True},
        {"label_window_bars": 12.0}, {"label_window_bars": -2},
    ])
    def test_non_integer_or_out_of_range_rejected(self, kw):
        base = dict(n=1000, embargo_bars=12, n_splits=4)
        base.update(kw)
        with pytest.raises(PurgedCVError):
            purged_walk_forward(**base)

    def test_valid_integer_layout_accepted(self):
        folds = purged_walk_forward(n=1000, embargo_bars=12, n_splits=4,
                                   label_window_bars=12)
        assert len(folds) == 4


# ------------------------------------------------------------------
# CPCV 组合净化交叉验证（combinatorial purged CV）
# ------------------------------------------------------------------
class TestCombinatorialPurgedFolds:
    def test_number_of_folds_matches_combinations(self):
        folds = combinatorial_purged_folds(
            n=120, n_blocks=6, k=2, embargo_bars=6, label_window_bars=6)
        assert len(folds) == math.comb(6, 2)

    def test_train_test_disjoint(self):
        folds = combinatorial_purged_folds(
            n=120, n_blocks=6, k=2, embargo_bars=6, label_window_bars=6)
        for tr, te in folds:
            assert set(tr.tolist()).isdisjoint(set(te.tolist()))

    def test_purge_and_embargo_bands_excluded(self):
        n, blocks, k, embargo = 120, 6, 2, 6
        edges = [round(i * n / blocks) for i in range(blocks + 1)]
        folds = combinatorial_purged_folds(
            n=n, n_blocks=blocks, k=k, embargo_bars=embargo, label_window_bars=embargo)
        for tr, te in folds:
            train_set = set(tr.tolist())
            for idx in te.tolist():
                # 找到该 test 样本所属块
                b = next(b for b in range(blocks) if edges[b] <= idx < edges[b + 1])
                s, e = edges[b], edges[b + 1]
                # purge 前端带、embargo 后端带不得落入 train
                for leak in range(max(0, s - embargo), s):
                    assert leak not in train_set
                for leak in range(e, min(e + embargo, n)):
                    assert leak not in train_set

    def test_k_two_produces_multiblock_test(self):
        folds = combinatorial_purged_folds(
            n=120, n_blocks=6, k=2, embargo_bars=6, label_window_bars=6)
        # k=2：存在 test 由两段不连续区间组成的折
        multiblock = False
        for _, te in folds:
            diff = np.diff(te)
            if (diff > 1).any():
                multiblock = True
                break
        assert multiblock

    @pytest.mark.parametrize("kw", [
        {"n_blocks": 1}, {"k": 0}, {"k": 6},
        {"n_blocks": 6.0}, {"k": 2.0}, {"k": True},
        {"embargo_bars": 3.0}, {"embargo_bars": -1},
        {"label_window_bars": 12.0},
    ])
    def test_invalid_layout_rejected(self, kw):
        base = dict(n=120, n_blocks=6, k=2, embargo_bars=6,
                    label_window_bars=6)
        base.update(kw)
        with pytest.raises(PurgedCVError):
            combinatorial_purged_folds(**base)

    def test_embargo_smaller_than_label_window_raises(self):
        with pytest.raises(PurgedCVError):
            combinatorial_purged_folds(
                n=120, n_blocks=6, k=2, embargo_bars=3, label_window_bars=12)

    def test_valid_layout_accepted(self):
        folds = combinatorial_purged_folds(
            n=120, n_blocks=6, k=2, embargo_bars=6, label_window_bars=6)
        assert len(folds) > 0
