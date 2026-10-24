# -*- coding: utf-8 -*-
"""core.features.atr —— Wilder ATR（因果）。

契约：ATR 统计量只应在 CLEAN 集估计（硬规则 2 集合分离）；调用方传入
对应 CLEAN 区间 history 即可。入场冻结 atr0 由风控层取本函数在入场 bar
的返回值，持仓期不得重算（c04_atr_recompute 夹具语义）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import as_of, _arrays, _wilder_ewma


@as_of
def wilder_atr(history: list, as_of: pd.Timestamp, period: int = 14) -> float:
    """Wilder ATR(period)，返回 as_of 所在 bar 收盘时刻的最新值。

    period 为窗长参数（调用方配置传入）；阈值/窗长本身由 CLEAN 分布校准，
    不在此处绩效调参。history 长度 < period+1 时返回 NaN（不猜未来）。
    """
    if period < 2:
        raise ValueError(f"period must be >= 2, got {period}")
    if len(history) < period + 1:
        return np.nan
    a = _arrays(history)
    high, low, close = a["high"], a["low"], a["close"]
    prev_close = np.concatenate(([close[0]], close[:-1]))
    tr = np.maximum.reduce([
        high - low,
        np.abs(high - prev_close),
        np.abs(low - prev_close),
    ])
    atr = _wilder_ewma(tr, period)
    val = atr[-1]
    return float(val) if np.isfinite(val) else np.nan
