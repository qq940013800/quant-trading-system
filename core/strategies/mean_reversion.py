# -*- coding: utf-8 -*-
"""core.strategies.mean_reversion —— RSI(14)/布林带极值 + 非强趋势门控。

第一性原理：均值回归赚的是「区间内的过度反应」，所以必须同时满足
1. 极值触发（做多，任一即可）：
   - RSI(14, Wilder) < oversold（默认 30），或
   - close < 布林下轨（bb_period=20, bb_sigma=2σ，σ 用总体标准差 ddof=0）
   做空对称：RSI(14) > overbought（默认 70）或 close > 布林上轨。
2. 非强趋势门控（本实现选择「距离」判据，二选一里写清楚）：
   ``|close - SMA50| / ATR(14) < trend_dist_max``（默认 2.0）。
   若价格已偏离慢均线 2 个 ATR 以上，说明是趋势行情而非区间，
   逆势均值回归不做（不接飞刀、不摸顶）。ADX(14) 方案被舍弃：
   本仓库没有内置 ADX 特征，且距离判据同样只依赖已收盘价格且更易复现。
3. 可交易性：ATR > 0，否则无法给出止损距离；atr<=0 直接放弃。

时间止损：暴露 ``max_hold_bars``（默认 24）供引擎/测试读取。引擎主循环
当前尚未接入时间止损，本字段先保留且可审计（不静默消失）。

因果纪律（AGENTS.md 硬规则 1/5）：RSI/布林/ATR/SMA 全部只用传入的已收盘
history；不计算手数（硬规则 8），只输出 atr0 与 entry_dist。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


def _finite(name: str, val: float) -> float:
    v = float(val)
    if not math.isfinite(v):
        raise ValueError({"layer": "strategies.mean_reversion", "detail":
                          f"{name} must be finite, got {val!r}"})
    return v


def _period(name: str, val: int) -> int:
    if isinstance(val, bool) or not isinstance(val, int) or val < 2:
        raise ValueError({"layer": "strategies.mean_reversion", "detail":
                          f"{name} must be an int >= 2, got {val!r}"})
    return val

#: 均值回归专家在 regime 混合中的固定权重（mr=1：由均值回归专家独占）。
_REGIME_WEIGHTS = {"trend": 0.0, "mr": 1.0, "range": 0.0}


@dataclass
class _Signal:
    """与 core.backtest.engine._Signal 同构的鸭子类型（不 import，保持解耦）。"""

    signal_id: str
    bar_ts_utc: pd.Timestamp
    expert: str
    direction: int
    price_ref: float
    atr0: float
    entry_dist: float
    l1_in_zone: bool
    regime_weights: dict
    meta_p: Optional[float]


def _check_closed_window(history: list, bar) -> None:
    """契约守卫：history 必须以「当前已收盘 bar」结尾（不许混入未来 bar）。"""
    if not history:
        raise ValueError({"layer": "strategies.mean_reversion",
                          "detail": "empty history"})
    if history[-1].ts_utc != bar.ts_utc:
        raise ValueError({
            "layer": "strategies.mean_reversion",
            "ts_utc": str(bar.ts_utc),
            "history_last_ts_utc": str(history[-1].ts_utc),
            "detail": "history must end at the current closed bar "
                      "(no future bars allowed)",
        })


def _true_range_arr(history: list) -> np.ndarray:
    """逐 bar True Range；只用 history 内数据，首根退化为 high-low。"""
    trs = []
    prev_close = None
    for b in history:
        hi, lo = float(b.high), float(b.low)
        if prev_close is None:
            trs.append(hi - lo)
        else:
            trs.append(max(hi - lo, abs(hi - prev_close), abs(lo - prev_close)))
        prev_close = float(b.close)
    return np.asarray(trs, dtype=float)


def wilder_atr(history: list, period: int = 14) -> float:
    """Wilder ATR(period)：TR 的 Wilder 平滑（只用 history，无未来数据）。"""
    if period < 2:
        raise ValueError({"layer": "strategies.mean_reversion",
                          "detail": f"atr period must be >= 2, got {period}"})
    tr = _true_range_arr(history)
    if tr.size < period:
        return 0.0
    atr = float(tr[:period].mean())
    for x in tr[period:]:
        atr = (atr * (period - 1) + float(x)) / float(period)
    return atr


def wilder_rsi(closes, period: int = 14) -> float:
    """Wilder RSI(period)。

    closes 长度 < period+1 时返回 NaN（调用方按「无信号」处理，不猜）。
    avg_loss == 0 时：有上涨记 100，全平盘记 50（避免除零，语义可审计）。
    """
    if period < 2:
        raise ValueError({"layer": "strategies.mean_reversion",
                          "detail": f"rsi period must be >= 2, got {period}"})
    arr = np.asarray(list(closes), dtype=float)
    if arr.size < period + 1:
        return float("nan")
    deltas = np.diff(arr)
    gains = np.clip(deltas, 0.0, None)
    losses = np.clip(-deltas, 0.0, None)
    avg_gain = float(gains[:period].mean())
    avg_loss = float(losses[:period].mean())
    for k in range(period, deltas.size):
        avg_gain = (avg_gain * (period - 1) + float(gains[k])) / float(period)
        avg_loss = (avg_loss * (period - 1) + float(losses[k])) / float(period)
    if avg_loss <= 0.0:
        return 100.0 if avg_gain > 0.0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def bollinger_bands(closes, period: int = 20,
                    sigma: float = 2.0) -> tuple[float, float, float]:
    """布林带 (lower, mid, upper)；σ 为总体标准差（ddof=0）。"""
    period = _period("period", period)
    sigma_v = _finite("sigma", sigma)
    if sigma_v <= 0:
        raise ValueError({"layer": "strategies.mean_reversion",
                          "detail": f"sigma must be > 0, got {sigma!r}"})
    arr = np.asarray(list(closes), dtype=float)[-period:]
    if arr.size == 0:
        raise ValueError({"layer": "strategies.mean_reversion",
                          "detail": "empty closes for bollinger bands"})
    mid = float(arr.mean())
    sd = float(arr.std(ddof=0))
    return mid - float(sigma_v) * sd, mid, mid + float(sigma_v) * sd


class MeanReversionStrategy:
    """RSI(14) + 布林带(20,2σ) 极值触发，配 ``|close-SMA50|/ATR < 2`` 门控。

    Attributes:
        rsi_period/rsi_oversold/rsi_overbought: RSI 触发参数（默认 14/30/70）
        bb_period/bb_sigma: 布林带参数（默认 20 / 2.0）
        sma_period: 门控用慢均线（默认 50）
        trend_dist_max: 强趋势拒绝阈值（默认 2.0 个 ATR）
        atr_period: ATR 周期（默认 14）
        entry_dist_mult: 止损距离 = mult × ATR（默认 2.0）
        max_hold_bars: 时间止损根数（默认 24；引擎暂未接入，先保留可读字段）
        symbol: signal_id 前缀
    """

    expert = "mean_reversion"

    def __init__(self, rsi_period: int = 14, rsi_oversold: float = 30.0,
                 rsi_overbought: float = 70.0, bb_period: int = 20,
                 bb_sigma: float = 2.0, sma_period: int = 50,
                 trend_dist_max: float = 2.0, atr_period: int = 14,
                 entry_dist_mult: float = 2.0, max_hold_bars: int = 24,
                 symbol: str = "XAUUSD"):
        self.rsi_period = _period("rsi_period", rsi_period)
        lo = _finite("rsi_oversold", rsi_oversold)
        hi = _finite("rsi_overbought", rsi_overbought)
        if not 0.0 <= lo < hi <= 100.0:
            raise ValueError({"layer": "strategies.mean_reversion",
                              "detail": "require 0 <= rsi_oversold < "
                                        "rsi_overbought <= 100, got "
                                        f"{lo}/{hi}"})
        self.rsi_oversold = lo
        self.rsi_overbought = hi
        self.bb_period = _period("bb_period", bb_period)
        sigma = _finite("bb_sigma", bb_sigma)
        if sigma <= 0:
            raise ValueError({"layer": "strategies.mean_reversion",
                              "detail": f"bb_sigma must be > 0, got {sigma}"})
        self.bb_sigma = sigma
        self.sma_period = _period("sma_period", sma_period)
        tdm = _finite("trend_dist_max", trend_dist_max)
        if tdm <= 0:
            raise ValueError({"layer": "strategies.mean_reversion",
                              "detail": f"trend_dist_max must be > 0, "
                                        f"got {tdm}"})
        self.trend_dist_max = tdm
        self.atr_period = _period("atr_period", atr_period)
        mult = _finite("entry_dist_mult", entry_dist_mult)
        if mult <= 0:
            raise ValueError({"layer": "strategies.mean_reversion",
                              "detail": f"entry_dist_mult must be > 0, "
                                        f"got {mult}"})
        self.entry_dist_mult = mult
        if isinstance(max_hold_bars, bool) or not isinstance(max_hold_bars, int) \
                or max_hold_bars < 1:
            raise ValueError({"layer": "strategies.mean_reversion",
                              "detail": f"max_hold_bars must be an int >= 1, "
                                        f"got {max_hold_bars!r}"})
        self.max_hold_bars = max_hold_bars
        self.symbol = str(symbol)
        # RSI 需要 period+1 根 close；布林/均线需要 period 根；ATR 需要 +1。
        self._min_history = max(self.rsi_period + 1, self.bb_period,
                                self.sma_period, self.atr_period + 1)

    def _trend_gate(self, price: float, sma: float, atr0: float) -> bool:
        """非强趋势门控：价格离慢均线 < trend_dist_max 个 ATR 才允许逆势。"""
        return abs(price - sma) / atr0 < self.trend_dist_max

    def on_bar_close(self, history: list, bar) -> Optional[_Signal]:
        """在本根已收盘 bar 上决策；不足历史 / 强趋势 / 无触发时返回 None。"""
        _check_closed_window(history, bar)
        if len(history) < self._min_history:
            return None

        atr0 = wilder_atr(history, self.atr_period)
        if atr0 <= 0.0:
            return None

        closes = [float(b.close) for b in history]
        price = float(bar.close)
        sma = float(np.mean(closes[-self.sma_period:]))
        if not self._trend_gate(price, sma, atr0):
            return None  # 强趋势：拒绝逆势均值回归

        rsi = wilder_rsi(closes, self.rsi_period)
        lower, _mid, upper = bollinger_bands(closes, self.bb_period,
                                             self.bb_sigma)
        hit_long = (np.isfinite(rsi) and rsi < self.rsi_oversold) or price < lower
        hit_short = (np.isfinite(rsi) and rsi > self.rsi_overbought) or price > upper
        if hit_long:
            direction = +1
        elif hit_short:
            direction = -1
        else:
            return None

        return _Signal(
            signal_id=f"{self.symbol}_{bar.ts_utc.isoformat()}"
                      f"_mean_reversion_{direction}",
            bar_ts_utc=bar.ts_utc,
            expert="mean_reversion",
            direction=direction,
            price_ref=price,
            atr0=atr0,
            entry_dist=self.entry_dist_mult * atr0,
            l1_in_zone=True,           # L1 区域层由其它模块裁决，这里不越权
            regime_weights=dict(_REGIME_WEIGHTS),
            meta_p=None,               # 无 ML meta-label 置信度
        )


__all__ = ["MeanReversionStrategy", "wilder_atr", "wilder_rsi",
           "bollinger_bands"]
