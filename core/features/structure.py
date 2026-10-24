# -*- coding: utf-8 -*-
"""core.features.structure —— L1 位置层：Donchian 通道、swing 点、BOS/CHoCH、市场结构。

集合分离（硬规则 2）：供需区结构只应在 KNOWN 集上构建——本模块只提供
"在传入 history 上确认的 swing/通道位置"，区间选择由调用方（splits 层）完成。
因果：swing 点需 k 根确认 bar 后才算成立；as_of 处只使用已确认的结构。

核心概念：
- Swing Point：波段高低点（需要 k 根确认）
- BOS (Break of Structure)：趋势延续，突破前一个同向 swing
- CHoCH (Change of Character)：趋势反转，突破前一个反向 swing
- Market Structure：当前市场结构（上升/下降/震荡）
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd

from .base import as_of, _arrays


# ------------------------------------------------------------------
# 数据类
# ------------------------------------------------------------------
@dataclass
class SwingPoint:
    """波段点（swing high 或 swing low）。

    Attributes:
        index: 在 history 中的位置
        price: 价格
        type: "high" 或 "low"
        confirmed_at: 确认位置（index + k）
    """
    index: int
    price: float
    type: str  # "high" or "low"
    confirmed_at: int

    def __repr__(self):
        return f"Swing({self.type}@{self.index}, price={self.price:.2f})"


@dataclass
class StructureBreak:
    """结构突破（BOS 或 CHoCH）。

    Attributes:
        index: 突破发生位置
        price: 突破价格
        direction: "bullish" 或 "bearish"
        break_type: "BOS"（趋势延续）或 "CHoCH"（趋势反转）
        broken_swing: 被突破的 swing point
    """
    index: int
    price: float
    direction: str  # "bullish" or "bearish"
    break_type: str  # "BOS" or "CHoCH"
    broken_swing: SwingPoint

    def __repr__(self):
        return f"{self.break_type}({self.direction}@{self.index}, price={self.price:.2f})"


@dataclass
class MarketStructure:
    """当前市场结构判断。

    Attributes:
        trend: "bullish" / "bearish" / "ranging"
        last_swing_high: 最近确认的 swing high
        last_swing_low: 最近确认的 swing low
        last_bos: 最近一次 BOS
        last_choch: 最近一次 CHoCH
    """
    trend: str
    last_swing_high: SwingPoint | None = None
    last_swing_low: SwingPoint | None = None
    last_bos: StructureBreak | None = None
    last_choch: StructureBreak | None = None

    def __repr__(self):
        return f"MarketStructure(trend={self.trend})"


# ------------------------------------------------------------------
# Donchian 通道（原有功能）
# ------------------------------------------------------------------
@as_of
def donchian_position(history: list, as_of: pd.Timestamp, window: int = 20) -> float:
    """现价在过去 window 根 bar Donchian 通道中的归一位置（0=下沿, 1=上沿）。

    window 不含未来 bar：取 history 末尾 window 根（全部 <= as_of）。
    """
    if window < 2:
        raise ValueError(f"window must be >= 2, got {window}")
    if len(history) < window:
        return np.nan
    a = _arrays(history)
    upper = a["high"][-window:].max()
    lower = a["low"][-window:].min()
    close = a["close"][-1]
    if upper <= lower:
        return np.nan
    return float((close - lower) / (upper - lower))


# ------------------------------------------------------------------
# Swing 点检测
# ------------------------------------------------------------------
@as_of
def nearest_confirmed_swing(history: list, as_of: pd.Timestamp,
                            k: int = 3) -> dict[str, float]:
    """最近一个已确认 swing high/low 到现价的距离（A TR 无关的绝对价格差）。

    swing high：high[i] = max(high[i-k..i+k])，在 i+k 处才确认。
    因此 history[-1] 处能确认的最近 swing 必然 <= len-1-k。
    返回 {"dist_high": +float(现价-最近swing高), "dist_low": -float(现价-最近swing低)}，
    找不到（历史太短）返回 NaN。
    """
    if k < 1:
        raise ValueError(f"k must be >= 1, got {k}")
    n = len(history)
    if n < 2 * k + 1:
        return {"dist_high": np.nan, "dist_low": np.nan}
    a = _arrays(history)
    high, low, close = a["high"], a["low"], a["close"]
    last_close = close[-1]
    swing_high_price = np.nan
    swing_low_price = np.nan
    # 从最新可确认位置往前找最近一个 swing
    for i in range(n - 1 - k, k - 1, -1):
        win_hi = high[i - k: i + k + 1]
        win_lo = low[i - k: i + k + 1]
        if np.isnan(swing_high_price) and high[i] == win_hi.max():
            swing_high_price = high[i]
        if np.isnan(swing_low_price) and low[i] == win_lo.min():
            swing_low_price = low[i]
        if np.isfinite(swing_high_price) and np.isfinite(swing_low_price):
            break
    return {
        "dist_high": float(last_close - swing_high_price) if np.isfinite(swing_high_price) else np.nan,
        "dist_low": float(last_close - swing_low_price) if np.isfinite(swing_low_price) else np.nan,
    }


def detect_swing_points(history: list, k: int = 3) -> list[SwingPoint]:
    """检测所有 swing 点（需要 k 根确认 bar）。

    swing high：high[i] = max(high[i-k..i+k])
    swing low：low[i] = min(low[i-k..i+k])

    因果性：index=i 的 swing 在 i+k 处才确认（confirmed_at = i+k）。
    只有 confirmed_at <= len-1 的 swing 才算有效。

    Args:
        history: K线数据列表
        k: 确认窗口（左右各 k 根）

    Returns:
        SwingPoint 列表，按 index 升序
    """
    if k < 1:
        raise ValueError(f"k must be >= 1, got {k}")
    n = len(history)
    if n < 2 * k + 1:
        return []

    a = _arrays(history)
    high, low = a["high"], a["low"]
    swings = []

    for i in range(k, n - k):
        # swing high
        win_hi = high[i - k: i + k + 1]
        if high[i] == win_hi.max():
            swings.append(SwingPoint(
                index=i,
                price=float(high[i]),
                type="high",
                confirmed_at=i + k,  # 在 i+k 处才确认
            ))
        # swing low
        win_lo = low[i - k: i + k + 1]
        if low[i] == win_lo.min():
            swings.append(SwingPoint(
                index=i,
                price=float(low[i]),
                type="low",
                confirmed_at=i + k,
            ))

    # 按 index 排序
    swings.sort(key=lambda s: s.index)
    return swings


# ------------------------------------------------------------------
# BOS / CHoCH 检测
# ------------------------------------------------------------------
def detect_bos(history: list, swings: list[SwingPoint]) -> list[StructureBreak]:
    """检测 BOS (Break of Structure)：趋势延续的突破。

    看涨 BOS：收盘价突破前一个 swing high（上升趋势延续）
    看跌 BOS：收盘价跌破前一个 swing low（下降趋势延续）

    Args:
        history: K线数据列表
        swings: 已检测的 swing 点列表

    Returns:
        StructureBreak 列表，break_type = "BOS"
    """
    if len(swings) < 2:
        return []

    a = _arrays(history)
    close = a["close"]
    n = len(close)
    breaks = []

    # 只看已确认的 swing（confirmed_at <= 当前位置）
    # 从后往前遍历，找到最近的未被突破的 swing high/low
    last_swing_high = None
    last_swing_low = None

    for i in range(n):
        # 更新最近的已确认 swing
        for s in swings:
            if s.confirmed_at == i:
                if s.type == "high":
                    last_swing_high = s
                else:
                    last_swing_low = s

        # 检查是否突破
        # 看涨 BOS：突破前一个 swing high
        if last_swing_high is not None and i > last_swing_high.confirmed_at:
            if close[i] > last_swing_high.price:
                breaks.append(StructureBreak(
                    index=i,
                    price=float(close[i]),
                    direction="bullish",
                    break_type="BOS",
                    broken_swing=last_swing_high,
                ))
                # 突破后，这个 swing 就失效了，等下一个
                last_swing_high = None

        # 看跌 BOS：跌破前一个 swing low
        if last_swing_low is not None and i > last_swing_low.confirmed_at:
            if close[i] < last_swing_low.price:
                breaks.append(StructureBreak(
                    index=i,
                    price=float(close[i]),
                    direction="bearish",
                    break_type="BOS",
                    broken_swing=last_swing_low,
                ))
                last_swing_low = None

    return breaks


def detect_choch(history: list, swings: list[SwingPoint]) -> list[StructureBreak]:
    """检测 CHoCH (Change of Character)：趋势反转信号。

    看涨 CHoCH：下跌趋势中，价格突破前一个 lower high（下跌可能结束）
    看跌 CHoCH：上升趋势中，价格跌破前一个 higher low（上涨可能结束）

    CHoCH 和 BOS 的区别：
    - BOS：突破同向 swing（趋势延续）
    - CHoCH：突破反向 swing（趋势可能反转）

    Args:
        history: K线数据列表
        swings: 已检测的 swing 点列表

    Returns:
        StructureBreak 列表，break_type = "CHoCH"
    """
    if len(swings) < 3:
        return []

    a = _arrays(history)
    close = a["close"]
    n = len(close)
    breaks = []

    # 找到最近的 swing high/low，判断趋势方向
    recent_highs = [s for s in swings if s.type == "high"]
    recent_lows = [s for s in swings if s.type == "low"]

    if len(recent_highs) < 2 or len(recent_lows) < 2:
        return []

    # 判断当前趋势
    # 上升趋势：高点抬高 + 低点抬高
    # 下降趋势：高点降低 + 低点降低
    last_two_highs = recent_highs[-2:]
    last_two_lows = recent_lows[-2:]

    higher_highs = last_two_highs[1].price > last_two_highs[0].price
    higher_lows = last_two_lows[1].price > last_two_lows[0].price
    lower_highs = last_two_highs[1].price < last_two_highs[0].price
    lower_lows = last_two_lows[1].price < last_two_lows[0].price

    uptrend = higher_highs and higher_lows
    downtrend = lower_highs and lower_lows

    # 看跌 CHoCH：上升趋势中，跌破前一个 higher low
    if uptrend:
        prev_low = last_two_lows[-2]  # 前一个 higher low
        for i in range(prev_low.confirmed_at + 1, n):
            if close[i] < prev_low.price:
                breaks.append(StructureBreak(
                    index=i,
                    price=float(close[i]),
                    direction="bearish",
                    break_type="CHoCH",
                    broken_swing=prev_low,
                ))
                break  # 只记录第一次

    # 看涨 CHoCH：下降趋势中，突破前一个 lower high
    if downtrend:
        prev_high = last_two_highs[-2]  # 前一个 lower high
        for i in range(prev_high.confirmed_at + 1, n):
            if close[i] > prev_high.price:
                breaks.append(StructureBreak(
                    index=i,
                    price=float(close[i]),
                    direction="bullish",
                    break_type="CHoCH",
                    broken_swing=prev_high,
                ))
                break

    return breaks


# ------------------------------------------------------------------
# 综合市场结构判断
# ------------------------------------------------------------------
def get_market_structure(history: list, k: int = 3) -> MarketStructure:
    """综合判断当前市场结构。

    Args:
        history: K线数据列表
        k: swing 确认窗口

    Returns:
        MarketStructure 对象
    """
    swings = detect_swing_points(history, k=k)
    bos_list = detect_bos(history, swings)
    choch_list = detect_choch(history, swings)

    recent_highs = [s for s in swings if s.type == "high"]
    recent_lows = [s for s in swings if s.type == "low"]

    # 判断趋势
    trend = "ranging"
    if len(recent_highs) >= 2 and len(recent_lows) >= 2:
        hh = recent_highs[-1].price > recent_highs[-2].price
        hl = recent_lows[-1].price > recent_lows[-2].price
        lh = recent_highs[-1].price < recent_highs[-2].price
        ll = recent_lows[-1].price < recent_lows[-2].price

        if hh and hl:
            trend = "bullish"
        elif lh and ll:
            trend = "bearish"

    return MarketStructure(
        trend=trend,
        last_swing_high=recent_highs[-1] if recent_highs else None,
        last_swing_low=recent_lows[-1] if recent_lows else None,
        last_bos=bos_list[-1] if bos_list else None,
        last_choch=choch_list[-1] if choch_list else None,
    )
