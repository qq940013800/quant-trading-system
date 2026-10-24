# -*- coding: utf-8 -*-
"""core.features.regime —— L2 状态层：ADX / Hurst / regime 分数 w 向量。

输出连续权重 w_trend / w_mr / w_range（非 0/1），供 Signal.regime_weights。
阈值来自分布：门控参数一律是分位数（调用方从 CLEAN 分布校准后传入），
模块内不出现 0.5/20 等绩效字面量。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import as_of, _arrays, _wilder_ewma


@as_of
def adx(history: list, as_of: pd.Timestamp, period: int = 14) -> float:
    """Wilder ADX(period)，返回 as_of 处最新值。ADX 是趋势强度指标（不分方向）。"""
    if period < 2:
        raise ValueError(f"period must be >= 2, got {period}")
    if len(history) < 2 * period + 1:
        return np.nan
    a = _arrays(history)
    high, low = a["high"], a["low"]

    up_move = high[1:] - high[:-1]
    down_move = low[:-1] - low[1:]
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    prev_close = np.concatenate(([a["close"][0]], a["close"][:-1]))
    tr = np.maximum.reduce([
        high - low,
        np.abs(high - prev_close),
        np.abs(low - prev_close),
    ])
    tr = tr[1:]

    atr_ = _wilder_ewma(tr, period)
    plus_di = 100.0 * _wilder_ewma(plus_dm, period) / atr_
    minus_di = 100.0 * _wilder_ewma(minus_dm, period) / atr_
    di_sum = plus_di + minus_di
    dx = np.where(di_sum > 0, 100.0 * np.abs(plus_di - minus_di) / di_sum, 0.0)
    adx_ = _wilder_ewma(dx[period - 1:], period)
    val = adx_[-1]
    return float(val) if np.isfinite(val) else np.nan


@as_of
def hurst_exponent(history: list, as_of: pd.Timestamp,
                   window: int = 512, min_window: int = 64) -> float:
    """R/S 法 Hurst 指数（causal：只在截至 as_of 的滚动窗内计算）。

    H≈0.5 随机游走；H>0.5 趋势持续；H<0.5 反持续（均值回复）。
    window/min_window 是窗长参数（配置传入），非绩效调参。
    """
    n = min(len(history), window)
    if n < min_window:
        return np.nan
    close = _arrays(history)["close"][-n:]
    rets = np.diff(np.log(close))
    max_lag = max(8, n // 8)
    lags = np.arange(2, max_lag)
    rs = []
    used_lags = []
    for lag in lags:
        if lag >= rets.size:
            break
        # R/S：对每个 lag，把收益序列切成 m 段，求每段 (max cum - min cum)/std
        n_chunks = rets.size // lag
        if n_chunks < 2:
            continue
        chunks = rets[: n_chunks * lag].reshape(n_chunks, lag)
        cum = np.cumsum(chunks, axis=1)
        cum -= cum.mean(axis=1, keepdims=True)
        r = cum.max(axis=1) - cum.min(axis=1)
        s = chunks.std(axis=1, ddof=1)
        mask = s > 0
        if mask.sum() < 2:
            continue
        rs.append(np.mean(r[mask] / s[mask]))
        used_lags.append(lag)
    if len(rs) < 4:
        return np.nan
    slope = np.polyfit(np.log(used_lags), np.log(rs), 1)[0]
    return float(np.clip(slope, 0.0, 1.0))


def regime_weights(adx_val: float, hurst_val: float, atr_pct: float, *,
                   adx_q_lo: float, adx_q_hi: float,
                   mr_hurst_thresh: float = 0.5) -> dict[str, float]:
    """regime 分数 w 向量（连续，非 0/1）。

    参数全部为"分布派生阈值"：
    - adx_q_lo / adx_q_hi：ADX 在 CLEAN 分布上的低分位/高分位（如 q30/q70），
      来自 scripts/calibrate_regime.py --mode distribution；
    - mr_hurst_thresh：Hurst 反持续判据（0.5=随机游走分界，理论值，非绩效调参）。

    映射（单调、可微、在分布区间内线性过渡）：
      w_trend = clip((adx - q_lo)/(q_hi - q_lo), 0, 1)
      w_mr    = clip(mr_hurst_thresh - hurst, 0, 1) * (1 - w_trend)
      w_range = (1 - atr_pct) * (1 - w_trend)          # 低波盘整
    最后归一化使三权重和为 1（防御型归一化，全 NaN 时返回均匀分布）。
    """
    if np.isnan(adx_val) or np.isnan(hurst_val) or np.isnan(atr_pct):
        return {"w_trend": 1.0 / 3, "w_mr": 1.0 / 3, "w_range": 1.0 / 3}
    span = adx_q_hi - adx_q_lo
    if span <= 0:
        raise ValueError("adx_q_hi must be > adx_q_lo (distribution quantiles)")
    w_trend = float(np.clip((adx_val - adx_q_lo) / span, 0.0, 1.0))
    w_mr = float(np.clip(mr_hurst_thresh - hurst_val, 0.0, 1.0)) * (1.0 - w_trend)
    w_range = float(1.0 - atr_pct) * (1.0 - w_trend)
    total = w_trend + w_mr + w_range
    if total <= 0:
        return {"w_trend": 1.0 / 3, "w_mr": 1.0 / 3, "w_range": 1.0 / 3}
    return {"w_trend": w_trend / total, "w_mr": w_mr / total, "w_range": w_range / total}
