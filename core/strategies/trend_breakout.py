# -*- coding: utf-8 -*-
"""core.strategies.trend_breakout —— Donchian 突破 + 慢均线趋势过滤。

第一性原理：趋势跟踪押的是「波动继续」，因此需要三个正交条件同时成立：
1. 突破：close 越过前 entry_period 根 bar 的 Donchian 通道；
   通道窗口显式取 history[-(N+1):-1]，即 **不含当前 bar**，杜绝
   「当前 bar 和自己比」（含当前 bar 时 close > hh 永远不可能成立）。
2. 方向一致：close 在慢均线同侧（多头 close > SMA，空头 close < SMA），
   过滤掉逆势的假突破。
3. 可交易性：ATR > 0，否则无法给出止损距离（entry_dist = mult × ATR），
   atr<=0 时直接放弃信号。

因果纪律（AGENTS.md 硬规则 1，前视守卫）：通道 / 均线 / ATR 全部只用
传入的已收盘 history 计算；本模块不读取 bar 之外的对象、不保存跨调用状态。
本策略不计算手数（硬规则 8），只输出 atr0 与 entry_dist 供风控层裁决。
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
        raise ValueError({"layer": "strategies.trend_breakout", "detail":
                          f"{name} must be finite, got {val!r}"})
    return v


def _period(name: str, val: int) -> int:
    if isinstance(val, bool) or not isinstance(val, int) or val < 2:
        raise ValueError({"layer": "strategies.trend_breakout", "detail":
                          f"{name} must be an int >= 2, got {val!r}"})
    return val

#: 趋势专家在 regime 混合中的固定权重（trend=1：由趋势专家独占）。
_REGIME_WEIGHTS = {"trend": 1.0, "mr": 0.0, "range": 0.0}


@dataclass
class _Signal:
    """与 core.backtest.engine._Signal 同构的鸭子类型（不 import，保持解耦）。

    字段与 docs/trading/AI_ML_SYSTEM_DESIGN.md 3.1 Signal schema 对齐。
    """

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
    """契约守卫：history 必须以「当前已收盘 bar」结尾。

    history 在引擎里恒为 bars[:i+1]（时间单调），所以只需要检查末元素；
    若末元素不是 bar，说明调用方把未来 bar 混了进来，属于前视错误，
    必须显式失败（硬规则 1/9：不带上下文的静默兜底不可接受）。
    """
    if not history:
        raise ValueError({"layer": "strategies.trend_breakout",
                          "detail": "empty history"})
    if history[-1].ts_utc != bar.ts_utc:
        raise ValueError({
            "layer": "strategies.trend_breakout",
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
    """Wilder ATR(period)：TR 的 Wilder 平滑（只用 history，无未来数据）。

    history 内 TR 数 < period 时返回 0.0，调用方据此放弃信号（不猜）。
    """
    if period < 2:
        raise ValueError({"layer": "strategies.trend_breakout",
                          "detail": f"atr period must be >= 2, got {period}"})
    tr = _true_range_arr(history)
    if tr.size < period:
        return 0.0
    atr = float(tr[:period].mean())
    for x in tr[period:]:
        atr = (atr * (period - 1) + float(x)) / float(period)
    return atr


class TrendBreakoutStrategy:
    """Donchian(entry_period) 突破 + SMA(sma_period) 趋势过滤。

    Attributes:
        entry_period:   通道回看根数（默认 20，通道不含当前 bar）
        sma_period:     慢均线周期（默认 50）
        atr_period:     ATR 周期（默认 14）
        entry_dist_mult: 止损距离 = mult × ATR（默认 2.0，即 entry_dist=2×atr0）
        symbol:         signal_id 前缀（品种来自调用方，不硬编码点值）
    """

    expert = "trend_breakout"

    def __init__(self, entry_period: int = 20, sma_period: int = 50,
                 atr_period: int = 14, entry_dist_mult: float = 2.0,
                 symbol: str = "XAUUSD"):
        self.entry_period = _period("entry_period", entry_period)
        self.sma_period = _period("sma_period", sma_period)
        self.atr_period = _period("atr_period", atr_period)
        mult = _finite("entry_dist_mult", entry_dist_mult)
        if mult <= 0:
            raise ValueError({"layer": "strategies.trend_breakout",
                              "detail": f"entry_dist_mult must be > 0, "
                                        f"got {mult}"})
        self.entry_dist_mult = mult
        self.symbol = str(symbol)
        # 历史不足阈值：通道需要 entry_period 根 + 当前 bar，均线需要
        # sma_period 根，ATR 需要 atr_period+1 根（TR 比 close 多一根）。
        self._min_history = max(self.entry_period + 2, self.sma_period,
                                self.atr_period + 1)

    def on_bar_close(self, history: list, bar) -> Optional[_Signal]:
        """在本根已收盘 bar 上决策；不足历史 / atr<=0 / 无突破时返回 None。"""
        _check_closed_window(history, bar)
        if len(history) < self._min_history:
            return None

        window = history[-(self.entry_period + 1):-1]  # 不含当前 bar
        hh = max(float(b.high) for b in window)
        ll = min(float(b.low) for b in window)

        atr0 = wilder_atr(history, self.atr_period)
        if atr0 <= 0.0:
            return None

        sma = float(np.mean([float(b.close)
                             for b in history[-self.sma_period:]]))
        price = float(bar.close)
        if price > hh and price > sma:
            direction = +1
        elif price < ll and price < sma:
            direction = -1
        else:
            direction = 0
        if direction == 0:
            return None

        return _Signal(
            signal_id=f"{self.symbol}_{bar.ts_utc.isoformat()}"
                      f"_trend_breakout_{direction}",
            bar_ts_utc=bar.ts_utc,
            expert="trend_breakout",
            direction=direction,
            price_ref=price,
            atr0=atr0,
            entry_dist=self.entry_dist_mult * atr0,
            l1_in_zone=True,           # L1 区域层由其它模块裁决，这里不越权
            regime_weights=dict(_REGIME_WEIGHTS),
            meta_p=None,               # 无 ML meta-label 置信度
        )


__all__ = ["TrendBreakoutStrategy", "wilder_atr"]
