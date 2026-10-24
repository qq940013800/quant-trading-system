# -*- coding: utf-8 -*-
"""tests.test_features.test_patterns —— K线形态识别测试。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.features.patterns import (
    is_hammer,
    is_shooting_star,
    is_doji,
    is_engulfing,
    is_piercing,
    is_dark_cloud_cover,
    is_morning_star,
    is_evening_star,
    bull_fvg,
    bear_fvg,
    bull_engulfing,
    bear_engulfing,
)


# ------------------------------------------------------------------
# 辅助：构造测试数据
# ------------------------------------------------------------------
class FakeBar:
    def __init__(self, open_, high, low, close, ts=None):
        self.open_ = open_
        self.high = high
        self.low = low
        self.close = close
        self.ts_utc = ts


def make_bars(*bars):
    """从 (open, high, low, close) 元组列表构造 history。"""
    history = []
    for i, (o, h, l, c) in enumerate(bars):
        ts = pd.Timestamp(f"2024-01-{i+1:02d}", tz="UTC")
        history.append(FakeBar(o, h, l, c, ts))
    return history


# ------------------------------------------------------------------
# 锤子线 / 上吊线
# ------------------------------------------------------------------
class TestHammer:
    def test_bullish_hammer(self):
        """看涨锤子线：下影线长，实体小，在底部。"""
        # 实体小，下影线是实体的2倍以上，上影线很短
        history = make_bars(
            (100, 100.25, 95, 100.2),  # 下影线5，实体0.2，上影线0.05
        )
        bar = history[-1]
        assert is_hammer(bar, direction="bullish") is True

    def test_not_hammer_no_long_lower_shadow(self):
        """下影线不够长，不是锤子线。"""
        history = make_bars(
            (100, 102, 99, 101),  # 下影线只有1
        )
        bar = history[-1]
        assert is_hammer(bar, direction="bullish") is False


# ------------------------------------------------------------------
# 流星 / 倒锤子
# ------------------------------------------------------------------
class TestShootingStar:
    def test_bearish_shooting_star(self):
        """看跌流星：上影线长，实体小，在顶部。"""
        history = make_bars(
            (100, 105, 99.95, 100.1),  # 上影线4.9，实体0.1，下影线0.05
        )
        bar = history[-1]
        assert is_shooting_star(bar, direction="bearish") is True


# ------------------------------------------------------------------
# 十字星
# ------------------------------------------------------------------
class TestDoji:
    def test_doji(self):
        """十字星：开盘价≈收盘价。"""
        history = make_bars(
            (100, 102, 98, 100.1),  # 实体几乎为0
        )
        bar = history[-1]
        assert is_doji(bar) is True

    def test_not_doji(self):
        """实体太大，不是十字星。"""
        history = make_bars(
            (100, 102, 98, 103),  # 实体3
        )
        bar = history[-1]
        assert is_doji(bar) is False


# ------------------------------------------------------------------
# 吞没形态
# ------------------------------------------------------------------
class TestEngulfing:
    def test_bullish_engulfing(self):
        """看涨吞没：阳包阴。"""
        history = make_bars(
            (100, 101, 99, 99.5),   # 前阴
            (99, 103, 98, 102),     # 后阳，包住前阴
        )
        assert is_engulfing(history, direction="bullish") is True

    def test_bearish_engulfing(self):
        """看跌吞没：阴包阳。"""
        history = make_bars(
            (100, 103, 99, 102),    # 前阳
            (102, 103, 98, 99),     # 后阴，包住前阳
        )
        assert is_engulfing(history, direction="bearish") is True


# ------------------------------------------------------------------
# 刺透形态 / 乌云盖顶
# ------------------------------------------------------------------
class TestPiercing:
    def test_piercing_pattern(self):
        """刺透形态：阳线深入阴线实体一半以上。"""
        history = make_bars(
            (100, 101, 95, 96),     # 前阴：开100收96，mid=98，low=95
            (94, 100, 93, 99),      # 后阳：开94（低于前低95），收99（深入前阴mid=98）
        )
        assert is_piercing(history) is True


# ------------------------------------------------------------------
# 启明星 / 黄昏星
# ------------------------------------------------------------------
class TestMorningStar:
    def test_morning_star(self):
        """启明星：大跌 + 小实体 + 大涨。"""
        history = make_bars(
            (100, 101, 90, 91),     # 第一根：大阴线
            (91, 92, 89, 90.5),     # 第二根：小实体（星）
            (90.5, 98, 90, 97),     # 第三根：大阳线
        )
        assert is_morning_star(history) is True

    def test_evening_star(self):
        """黄昏星：大涨 + 小实体 + 大跌。"""
        history = make_bars(
            (90, 100, 89, 99),      # 第一根：大阳线
            (99, 101, 98, 99.5),    # 第二根：小实体（星）
            (99.5, 100, 92, 93),    # 第三根：大阴线
        )
        assert is_evening_star(history) is True


# ------------------------------------------------------------------
# 乌云盖顶（补充：之前完全没测）
# ------------------------------------------------------------------
class TestDarkCloudCover:
    def test_dark_cloud_cover(self):
        """乌云盖顶：阳线后阴线深入一半以上。"""
        history = make_bars(
            (100, 110, 99, 109),    # 前阳：开100收109，mid=104.5，high=110
            (111, 112, 103, 104),   # 后阴：开111（高于前高110），收104（低于mid=104.5）
        )
        assert is_dark_cloud_cover(history) is True

    def test_not_dark_cloud_no_penetration(self):
        """阴线没深入一半，不是乌云盖顶。"""
        history = make_bars(
            (100, 110, 99, 109),    # 前阳
            (110.5, 111, 108, 108.5),  # 后阴，但只跌了一点，没到mid
        )
        assert is_dark_cloud_cover(history) is False


# ------------------------------------------------------------------
# 边界情况测试
# ------------------------------------------------------------------
class TestEdgeCases:
    def test_hammer_zero_body_returns_false(self):
        """实体为0（十字星）不是锤子线。"""
        bar = FakeBar(open_=100, high=102, low=98, close=100)
        assert is_hammer(bar) is False

    def test_shooting_star_zero_body_returns_false(self):
        """实体为0不是流星。"""
        bar = FakeBar(open_=100, high=102, low=98, close=100)
        assert is_shooting_star(bar) is False

    def test_doji_zero_range_returns_false(self):
        """最高价=最低价（一字板）不是十字星。"""
        bar = FakeBar(open_=100, high=100, low=100, close=100)
        assert is_doji(bar) is False

    def test_engulfing_too_short_history(self):
        """history不够2根，不是吞没。"""
        history = make_bars((100, 101, 99, 100.5))
        assert is_engulfing(history) is False

    def test_piercing_too_short_history(self):
        """history不够2根，不是刺透。"""
        history = make_bars((100, 101, 99, 99.5))
        assert is_piercing(history) is False

    def test_morning_star_too_short_history(self):
        """history不够3根，不是启明星。"""
        history = make_bars((100, 101, 90, 91), (91, 92, 89, 90.5))
        assert is_morning_star(history) is False

    def test_evening_star_too_short_history(self):
        """history不够3根，不是黄昏星。"""
        history = make_bars((90, 100, 89, 99), (99, 101, 98, 99.5))
        assert is_evening_star(history) is False


# ------------------------------------------------------------------
# FVG（公允价格缺口）测试
# ------------------------------------------------------------------
class TestFVG:
    def test_bull_fvg_present(self):
        """多头FVG：当前低点 > 前三根高点。"""
        history = make_bars(
            (100, 105, 99, 104),    # b-3
            (104, 106, 103, 105),   # b-2
            (106, 115, 107, 114),   # b-1：低点107 > b-3高点105
        )
        ts = pd.Timestamp("2024-01-03", tz="UTC")
        result = bull_fvg(history, ts)
        assert result == 1.0

    def test_bear_fvg_present(self):
        """空头FVG：当前高点 < 前三根低点。"""
        history = make_bars(
            (100, 101, 95, 96),     # b-3：low=95
            (96, 97, 94, 95),       # b-2
            (95, 93, 90, 91),       # b-1：high=93 < b-3 low=95
        )
        ts = pd.Timestamp("2024-01-03", tz="UTC")
        result = bear_fvg(history, ts)
        assert result == 1.0

    def test_fvg_too_short_history(self):
        """history不够3根返回nan。"""
        history = make_bars((100, 105, 99, 104), (104, 106, 103, 105))
        ts = pd.Timestamp("2024-01-02", tz="UTC")
        assert np.isnan(bull_fvg(history, ts))


# ------------------------------------------------------------------
# 兼容函数（bull/bear engulfing wrapper）
# ------------------------------------------------------------------
class TestEngulfingWrappers:
    def test_bull_engulfing_wrapper(self):
        """多头吞没包装函数。"""
        history = make_bars(
            (100, 101, 99, 99.5),   # 前阴
            (99, 103, 98, 102),     # 后阳
        )
        ts = pd.Timestamp("2024-01-02", tz="UTC")
        assert bull_engulfing(history, ts) == 1.0

    def test_bear_engulfing_wrapper(self):
        """空头吞没包装函数。"""
        history = make_bars(
            (100, 103, 99, 102),    # 前阳
            (102, 103, 98, 99),     # 后阴
        )
        ts = pd.Timestamp("2024-01-02", tz="UTC")
        assert bear_engulfing(history, ts) == 1.0
