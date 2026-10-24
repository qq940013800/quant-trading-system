# -*- coding: utf-8 -*-
"""core.models.labels —— triple-barrier 标签（因果：只用已收盘 bar 的未来路径）。

标签语义（设计文档 3.2 + IMPLEMENTATION_SPEC §4.2）：
    入场价 p0 = close[i]；屏障宽度 = atr0 * mult（atr0 入场 bar 冻结，不重算）。
    - 上屏障 p0 + tp_mult*atr0 先触 → +1
    - 下屏障 p0 - sl_mult*atr0 先触 → -1
    - 同一根 bar 两屏障都触：保守假设先触止损 → -1
    - max_holding_bars 内均未触 → 0（时间屏障）

注意：标签本身是"未来路径"的函数，天然含未来 bar——这不违反因果；
因果纪律在于：特征/统计量不得偷看标签对应的未来区间（由 purged WF + embargo 保证）。
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger("core.models")


def triple_barrier_labels(bars: list, atr: pd.Series, *,
                          tp_mult: float, sl_mult: float,
                          max_holding_bars: int) -> pd.Series:
    """逐 bar 生成 triple-barrier 标签。

    Parameters
    ----------
    bars : list[BarLike]，按 ts_utc 升序、全部已收盘；
    atr  : 与 bars 对齐的 ATR 序列（pd.Series，index 默认 RangeIndex）；
    tp_mult / sl_mult : 上/下屏障对 atr0 的倍数（配置传入，非绩效调参）；
    max_holding_bars : 时间屏障（embargo 宽度必须 >= 本值）。

    Returns
    -------
    pd.Series，index 与 atr 对齐，取值 {-1, 0, +1}；atr0 缺失/未来不足返回 0。
    """
    if tp_mult <= 0 or sl_mult <= 0:
        raise ValueError("tp_mult/sl_mult must be positive")
    if max_holding_bars < 1:
        raise ValueError("max_holding_bars must be >= 1")
    n = len(bars)
    if n != len(atr):
        raise ValueError(f"bars/atr length mismatch: {n} vs {len(atr)}")

    high = np.fromiter((b.high for b in bars), dtype=np.float64, count=n)
    low = np.fromiter((b.low for b in bars), dtype=np.float64, count=n)
    close = np.fromiter((b.close for b in bars), dtype=np.float64, count=n)
    atr_arr = np.asarray(atr, dtype=np.float64)

    labels = np.zeros(n, dtype=np.int8)
    for i in range(n):
        a0 = atr_arr[i]
        if not np.isfinite(a0) or a0 <= 0:
            labels[i] = 0
            continue
        p0 = close[i]
        up = p0 + tp_mult * a0
        dn = p0 - sl_mult * a0
        end = min(i + max_holding_bars, n - 1)
        lab = 0
        for j in range(i + 1, end + 1):
            hit_up = high[j] >= up
            hit_dn = low[j] <= dn
            if hit_dn and hit_up:
                lab = -1  # 保守：同 bar 双触按止损先触
                break
            if hit_up:
                lab = 1
                break
            if hit_dn:
                lab = -1
                break
        labels[i] = lab
    return pd.Series(labels, index=atr.index, name="label")
