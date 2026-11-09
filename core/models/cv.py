# -*- coding: utf-8 -*-
"""core.models.cv —— purged walk-forward + embargo（禁随机 KFold）。

契约（设计文档 3.2 + IMPLEMENTATION_SPEC §4.3）：
    purged_walk_forward(n, embargo_bars, n_splits) -> list[(train_idx, test_idx)]

防泄漏双重机制（López de Prado）：
  1. purge：剔除 train 中标签窗口与 test 区间重叠的样本
     —— train i 的标签覆盖 [i, i+L]，与 test [s,e) 重叠 ⟺ i >= s-L；
  2. embargo：剔除每个 test 块之后的 embargo_bars 个样本（序列相关污染）。

约束：embargo_bars >= 标签窗口长度（max_holding_bars），否则 raise——
防止实现忘记 purge 宽度必须覆盖标签视野。
"""
from __future__ import annotations

from itertools import combinations

import numpy as np


class PurgedCVError(ValueError):
    """purged walk-forward 参数/布局违反契约。"""


def _as_int(name: str, val: int) -> int:
    if isinstance(val, bool) or not isinstance(val, int):
        raise PurgedCVError(f"{name} 必须为整数，收到 {val!r}")
    return val


def _as_nonneg_int(name: str, val: int) -> int:
    if isinstance(val, bool) or not isinstance(val, int) or val < 0:
        raise PurgedCVError(f"{name} 必须为 ≥0 整数，收到 {val!r}")
    return val


def purged_walk_forward(n: int, embargo_bars: int, n_splits: int, *,
                        label_window_bars: int | None = None
                        ) -> list[tuple[np.ndarray, np.ndarray]]:
    """expanding-window walk-forward，每折 test 为连续块（禁随机打乱）。

    Parameters
    ----------
    n : 样本总数；
    embargo_bars : embargo 宽度（bar 数），必须 >= label_window_bars；
    n_splits : test 块数；
    label_window_bars : 标签最大视野（= max_holding_bars）；提供且
        embargo_bars < label_window_bars 时 raise PurgedCVError。

    Returns
    -------
    [(train_idx, test_idx), ...]，时间顺序排列；train 全部 < test 最小下标。
    """
    n = _as_nonneg_int("n", n)
    embargo_bars = _as_nonneg_int("embargo_bars", embargo_bars)
    n_splits = _as_int("n_splits", n_splits)
    if label_window_bars is not None:
        label_window_bars = _as_nonneg_int("label_window_bars", label_window_bars)
    if n < 1:
        raise PurgedCVError(f"n 必须 ≥1，收到 {n!r}")
    if n_splits < 2:
        raise PurgedCVError(f"n_splits must be >= 2, got {n_splits}")
    if embargo_bars < 0:
        raise PurgedCVError("embargo_bars must be >= 0")
    if label_window_bars is not None and embargo_bars < label_window_bars:
        raise PurgedCVError(
            f"embargo_bars({embargo_bars}) < label_window_bars({label_window_bars}): "
            "purge 宽度不足以覆盖标签视野，训练集会泄漏测试段标签")
    warm = n // (n_splits + 1)
    if warm <= embargo_bars:
        raise PurgedCVError("warmup block too small relative to embargo_bars")

    # 预计算每个 test 块的 [start, end)
    blocks: list[tuple[int, int]] = []
    for k in range(n_splits):
        s = (k + 1) * warm
        e = min((k + 2) * warm, n)
        blocks.append((s, e))

    folds: list[tuple[np.ndarray, np.ndarray]] = []
    for k, (s, e) in enumerate(blocks):
        # purge：train 末端剔除与 test 标签窗口重叠的 embargo_bars 个样本
        train_end = s - embargo_bars
        if train_end <= 0:
            continue
        train_idx = set(range(0, train_end))
        # embargo：剔除此前每个 test 块之后的 embargo_bars 个样本
        for j in range(k):
            prev_e = blocks[j][1]
            train_idx -= set(range(prev_e, min(prev_e + embargo_bars, n)))
        if not train_idx:
            continue
        folds.append((np.array(sorted(train_idx), dtype=np.int64),
                      np.arange(s, e, dtype=np.int64)))
    if len(folds) < 1:
        raise PurgedCVError("no valid fold produced; increase n or reduce embargo/splits")
    return folds


def combinatorial_purged_folds(n: int, n_blocks: int, k: int, embargo_bars: int, *,
                               label_window_bars: int | None = None
                               ) -> list[tuple[np.ndarray, np.ndarray]]:
    """CPCV（López de Prado 组合净化交叉验证）。

    把序列切成 ``n_blocks`` 个等界块，取 C(n_blocks, k) 种 k 块并集作为
    test，其余块经 purge + embargo 净化后作为 train。与
    :func:`purged_walk_forward` 的区别：test 可由多个不连续块组成（组合
    交叉），折数为组合数 C(n_blocks, k)，而非顺序单链。

    Parameters
    ----------
    n : 样本总数；
    n_blocks : 等界块数（>= 2）；
    k : 每折并入 test 的块数（1 <= k <= n_blocks-1）；
    embargo_bars : embargo/purge 宽度（bar 数），必须 >= label_window_bars；
    label_window_bars : 标签最大视野（= max_holding_bars，可选）。

    Returns
    -------
    [(train_idx, test_idx), ...]，每折 train/test 为排序后的 int64 索引数组。
    """
    n = _as_nonneg_int("n", n)
    n_blocks = _as_int("n_blocks", n_blocks)
    k = _as_int("k", k)
    embargo_bars = _as_nonneg_int("embargo_bars", embargo_bars)
    if label_window_bars is not None:
        label_window_bars = _as_nonneg_int("label_window_bars", label_window_bars)
    if n < 1:
        raise PurgedCVError(f"n 必须 ≥1，收到 {n!r}")
    if n_blocks < 2:
        raise PurgedCVError(f"n_blocks 必须 >= 2，收到 {n_blocks!r}")
    if not (1 <= k <= n_blocks - 1):
        raise PurgedCVError(
            f"k 必须位于 [1, n_blocks-1]，收到 k={k}, n_blocks={n_blocks}")
    if label_window_bars is not None and embargo_bars < label_window_bars:
        raise PurgedCVError(
            f"embargo_bars({embargo_bars}) < label_window_bars({label_window_bars}): "
            "purge 宽度不足以覆盖标签视野，训练集会泄漏测试段标签")

    edges = [round(i * n / n_blocks) for i in range(n_blocks + 1)]
    blocks: list[tuple[int, int]] = [(edges[b], edges[b + 1]) for b in range(n_blocks)]

    folds: list[tuple[np.ndarray, np.ndarray]] = []
    for test_blocks in combinations(range(n_blocks), k):
        test_idx: set[int] = set()
        train_idx: set[int] = set(range(n))
        for b in test_blocks:
            s, e = blocks[b]
            test_idx.update(range(s, e))
            train_idx -= set(range(s, e))
        # purge：剔除 train 中与 test 标签窗口重叠的 test 前端带
        for b in test_blocks:
            s, _ = blocks[b]
            train_idx -= set(range(max(0, s - embargo_bars), s))
        # embargo：剔除每个 test 块之后的 embargo_bars 个样本
        for b in test_blocks:
            _, e = blocks[b]
            train_idx -= set(range(e, min(e + embargo_bars, n)))
        if not train_idx or not test_idx:
            continue
        folds.append((np.array(sorted(train_idx), dtype=np.int64),
                      np.array(sorted(test_idx), dtype=np.int64)))
    if not folds:
        raise PurgedCVError(
            "no valid CPCV fold produced; increase n or reduce embargo/blocks")
    return folds
