# -*- coding: utf-8 -*-
"""core.features.patterns —— K线形态识别库（反转形态为主）。

基于第一性原理：K线形态反映的是多空力量在特定价格区域的博弈结果。
- 底部反转形态：空方力量耗尽，多方开始反扑
- 顶部反转形态：多方力量耗尽，空方开始反扑

所有形态都基于已收盘 bar，保证因果性。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import as_of, _arrays


# ------------------------------------------------------------------
# 基础工具函数
# ------------------------------------------------------------------
def _body(open_: float, close: float) -> float:
    """K线实体大小（绝对值）。"""
    return abs(close - open_)


def _upper_shadow(open_: float, close: float, high: float) -> float:
    """上影线长度。"""
    return high - max(open_, close)


def _lower_shadow(open_: float, close: float, low: float) -> float:
    """下影线长度。"""
    return min(open_, close) - low


def _is_bull(open_: float, close: float) -> bool:
    """阳线。"""
    return close > open_


def _is_bear(open_: float, close: float) -> bool:
    return close < open_


# ------------------------------------------------------------------
# 单根K线形态
# ------------------------------------------------------------------
def is_hammer(bar, direction: str = "bullish",
              shadow_ratio: float = 2.0, max_upper_ratio: float = 0.5) -> bool:
    """锤子线 / 上吊线。

    特征：
    - 下影线长度 >= shadow_ratio × 实体
    - 上影线很短（<= max_upper_ratio × 实体）
    - 实体较小

    Args:
        bar: K线对象（有 open_/high/low/close 属性）
        direction: "bullish"（底部锤子）或 "bearish"（顶部上吊线）
        shadow_ratio: 下影线/实体比例阈值
        max_upper_ratio: 上影线/实体最大比例

    Returns:
        True = 是锤子线
    """
    o, h, l, c = bar.open_, bar.high, bar.low, bar.close
    body = _body(o, c)
    if body == 0:
        return False
    lower = _lower_shadow(o, c, l)
    upper = _upper_shadow(o, c, h)
    return lower >= shadow_ratio * body and upper <= max_upper_ratio * body


def is_shooting_star(bar, direction: str = "bearish",
                    shadow_ratio: float = 2.0, max_lower_ratio: float = 0.5) -> bool:
    """流星 / 倒锤子。

    特征：
    - 上影线长度 >= shadow_ratio × 实体
    - 下影线很短（<= max_lower_ratio × 实体）
    """
    o, h, l, c = bar.open_, bar.high, bar.low, bar.close
    body = _body(o, c)
    if body == 0:
        return False
    lower = _lower_shadow(o, c, l)
    upper = _upper_shadow(o, c, h)
    return upper >= shadow_ratio * body and lower <= max_lower_ratio * body


def is_doji(bar, tolerance_ratio: float = 0.1) -> bool:
    """十字星：开盘价≈收盘价。

    Args:
        tolerance_ratio: 实体相对整体波幅的容忍度
    """
    o, h, l, c = bar.open_, bar.high, bar.low, bar.close
    total_range = h - l
    if total_range == 0:
        return False
    body = _body(o, c)
    return body <= tolerance_ratio * total_range


# ------------------------------------------------------------------
# 两根K线形态
# ------------------------------------------------------------------
def is_engulfing(history, direction: str = "bullish") -> bool:
    """吞没形态。

    看涨吞没：前阴后阳，后阳实体包住前阴实体
    看跌吞没：前阳后阴，后阴实体包住前阳实体
    """
    if len(history) < 2:
        return False
    prev, cur = history[-2], history[-1]

    prev_body = _body(prev.open_, prev.close)
    cur_body = _body(cur.open_, cur.close)

    if direction == "bullish":
        # 前阴后阳，阳包阴
        return (_is_bear(prev.open_, prev.close) and
                _is_bull(cur.open_, cur.close) and
                cur.close >= prev.open_ and
                cur.open_ <= prev.close)
    else:
        # 前阳后阴，阴包阳
        return (_is_bull(prev.open_, prev.close) and
                _is_bear(cur.open_, cur.close) and
                cur.close <= prev.open_ and
                cur.open_ >= prev.close)


def is_piercing(history, min_penetration_ratio: float = 0.5) -> bool:
    """刺透形态（看涨反转）。

    特征：
    - 第一根大阴线
    - 第二根低开高走，收盘价深入前阴实体一半以上
    """
    if len(history) < 2:
        return False
    prev, cur = history[-2], history[-1]

    if not (_is_bear(prev.open_, prev.close) and _is_bull(cur.open_, cur.close)):
        return False

    prev_mid = (prev.open_ + prev.close) / 2
    # 第二根收盘价深入前阴实体一半以上
    # 且开盘价低于前低
    return (cur.close > prev_mid and
            cur.close < prev.open_ and
            cur.open_ < prev.low)


def is_dark_cloud_cover(history, min_penetration_ratio: float = 0.5) -> bool:
    """乌云盖顶（看跌反转）。

    特征：
    - 第一根大阳线
    - 第二根高开低走，收盘价深入前阳实体一半以上
    """
    if len(history) < 2:
        return False
    prev, cur = history[-2], history[-1]

    if not (_is_bull(prev.open_, prev.close) and _is_bear(cur.open_, cur.close)):
        return False

    prev_mid = (prev.open_ + prev.close) / 2
    return (cur.close < prev_mid and
            cur.close > prev.open_ and
            cur.open_ > prev.high)


# ------------------------------------------------------------------
# 三根K线形态
# ------------------------------------------------------------------
def is_morning_star(history, body_ratio: float = 0.3) -> bool:
    """启明星（底部反转）。

    特征：
    - 第一根：大阴线
    - 第二根：小实体（跳空低开，星线）
    - 第三根：大阳线，深入第一根实体一半以上
    """
    if len(history) < 3:
        return False
    b1, b2, b3 = history[-3], history[-2], history[-1]

    b1_body = _body(b1.open_, b1.close)
    b2_body = _body(b2.open_, b2.close)
    b3_body = _body(b3.open_, b3.close)

    # 第一根大阴，第二根小实体，第三根大阳
    if not (_is_bear(b1.open_, b1.close) and
            _is_bull(b3.open_, b3.close)):
        return False

    if b2_body > body_ratio * b1_body:  # 第二根实体要小
        return False

    # 第三根收盘价深入第一根实体一半以上
    b1_mid = (b1.open_ + b1.close) / 2
    return b3.close > b1_mid


def is_evening_star(history, body_ratio: float = 0.3) -> bool:
    """黄昏星（顶部反转）。

    特征：
    - 第一根：大阳线
    - 第二根：小实体（跳空高开，星线）
    - 第三根：大阴线，深入第一根实体一半以上
    """
    if len(history) < 3:
        return False
    b1, b2, b3 = history[-3], history[-2], history[-1]

    b1_body = _body(b1.open_, b1.close)
    b2_body = _body(b2.open_, b2.close)

    if not (_is_bull(b1.open_, b1.close) and
            _is_bear(b3.open_, b3.close)):
        return False

    if b2_body > body_ratio * b1_body:
        return False

    b1_mid = (b1.open_ + b1.close) / 2
    return b3.close < b1_mid


# ------------------------------------------------------------------
# 原有 FVG 和吞没（保留，兼容旧代码）
# ------------------------------------------------------------------
@as_of
def bull_fvg(history: list, as_of: pd.Timestamp) -> float:
    """最近 bar 是否形成多头 FVG（1.0/0.0）。"""
    if len(history) < 3:
        return np.nan
    a = _arrays(history)
    return 1.0 if a["low"][-1] > a["high"][-3] else 0.0


@as_of
def bear_fvg(history: list, as_of: pd.Timestamp) -> float:
    """最近 bar 是否形成空头 FVG（1.0/0.0）。"""
    if len(history) < 3:
        return np.nan
    a = _arrays(history)
    return 1.0 if a["high"][-1] < a["low"][-3] else 0.0


@as_of
def bull_engulfing(history: list, as_of: pd.Timestamp) -> float:
    """多头吞没（当前阳线实体包住前一根阴线实体）。"""
    return 1.0 if is_engulfing(history, direction="bullish") else 0.0


@as_of
def bear_engulfing(history: list, as_of: pd.Timestamp) -> float:
    """空头吞没（当前阴线实体包住前一根阳线实体）。"""
    return 1.0 if is_engulfing(history, direction="bearish") else 0.0
