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

import numpy as np


class PurgedCVError(ValueError):
    """purged walk-forward 参数/布局违反契约。"""


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
