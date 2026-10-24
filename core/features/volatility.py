# -*- coding: utf-8 -*-
"""core.features.volatility —— 已实现波动率与 expanding 归一化（禁全样本 z-score）。

归一化纪律（设计文档②）：禁止全样本 z-score。本模块只提供两类"只用过去"的
归一化：
  1. rolling 标准化：均值/标准差取自截至 as_of 的滚动窗；
  2. expanding 分位：当前值在截至 as_of 的历史分布中的分位（0~1）。
阈值来自分布——regime 门控用的就是分位而非固定常数。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import as_of, _arrays, expanding_percentile_rank


@as_of
def realized_vol(history: list, as_of: pd.Timestamp, window: int = 48) -> float:
    """已实现波动率：截至 as_of 的 window 根已收盘 bar 对数收益标准差。

    window=48 对应 M5 的 4 小时；年化/缩放因子不在此处硬编码——返回的是
    原始 std，跨品种缩放由调用方配置决定。
    """
    if window < 2:
        raise ValueError(f"window must be >= 2, got {window}")
    if len(history) < window + 1:
        return np.nan
    close = _arrays(history)["close"]
    log_ret = np.diff(np.log(close[-window - 1:]))
    return float(np.std(log_ret, ddof=1))


@as_of
def atr_percentile_rank(history: list, as_of: pd.Timestamp,
                        atr_series: np.ndarray, period: int = 14,
                        min_history: int = 96) -> float:
    """当前 ATR 在自身 expanding 分布中的分位（0~1）。

    atr_series：与 history 对齐的 ATR 序列（调用方用 wilder_atr 逐 bar 预算，
    保证 ATR 本身因果）。只用 as_of 及之前的 ATR 值做分位——分布派生阈值。
    """
    if len(history) != len(atr_series):
        raise ValueError("history/atr_series length mismatch")
    cur = atr_series[len(history) - 1]
    if not np.isfinite(cur):
        return np.nan
    past = atr_series[: len(history) - 1]
    past = past[np.isfinite(past)]
    if past.size < min_history:
        return np.nan
    return expanding_percentile_rank(past, float(cur))
