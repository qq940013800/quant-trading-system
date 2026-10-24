# -*- coding: utf-8 -*-
"""core.models.drift —— 特征漂移监控（PSI）与滚动命中率。

PSII（Population Stability Index）：|PSI| < 0.1 稳定；0.1~0.25 关注；
>0.25 显著漂移。分桶按 reference 分布的分位点（阈值来自分布）。
"""
from __future__ import annotations

import numpy as np


def psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    """Population Stability Index。expected=训练分布，actual=当前分布。"""
    e = np.asarray(expected, dtype=np.float64)
    a = np.asarray(actual, dtype=np.float64)
    e = e[np.isfinite(e)]
    a = a[np.isfinite(a)]
    if e.size < bins or a.size < bins:
        return np.nan
    edges = np.quantile(e, np.linspace(0.0, 1.0, bins + 1)[1:-1])
    e_counts, _ = np.histogram(e, bins=np.concatenate([[-np.inf], edges, [np.inf]]))
    a_counts, _ = np.histogram(a, bins=np.concatenate([[-np.inf], edges, [np.inf]]))
    e_freq = np.clip(e_counts / e_counts.sum(), 1e-6, None)
    a_freq = np.clip(a_counts / a_counts.sum(), 1e-6, None)
    return float(np.sum((a_freq - e_freq) * np.log(a_freq / e_freq)))


def rolling_hit_rate(correct: np.ndarray, window: int) -> np.ndarray:
    """滚动窗口命中率（事后监控：OOS 命中率相对训练段的偏移报警用）。"""
    c = np.asarray(correct, dtype=np.float64)
    if window < 2:
        raise ValueError("window must be >= 2")
    out = np.full(c.shape, np.nan, dtype=np.float64)
    if c.size < window:
        return out
    # causal rolling：只用当前及过去 bar
    csum = np.concatenate(([0.0], np.cumsum(c)))
    rates = (csum[window:] - csum[:-window]) / window
    out[window - 1:] = rates
    return out
