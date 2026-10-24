# -*- coding: utf-8 -*-
"""tests.test_backtest.test_slippage —— 滑点模型优化测试。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.backtest.costs import (
    CostModel,
    slippage_points,
    sqrt_slippage,
    volume_impact_slippage,
    volatility_adjusted_slippage,
    estimate_total_slippage,
)


# ------------------------------------------------------------------
# 基础滑点测试
# ------------------------------------------------------------------
class TestBaseSlippage:
    def test_zero_lot_zero_slippage(self):
        """零手数，零滑点。"""
        model = CostModel(
            base_spread=0.2,
            news_spread=0.5,
            gap_spread=1.0,
            gap_threshold=1.0,
            base_slippage=0.1,
            slippage_per_volume_frac=0.5,
            commission_per_lot=7.0,
        )
        slippage = slippage_points(None, 0.0, model)
        assert slippage == pytest.approx(0.1)  # 基础滑点还是有的

    def test_large_lot_more_slippage(self):
        """大手数，滑点更大。"""
        model = CostModel(
            base_spread=0.2,
            news_spread=0.5,
            gap_spread=1.0,
            gap_threshold=1.0,
            base_slippage=0.1,
            slippage_per_volume_frac=0.5,
            commission_per_lot=7.0,
        )
        slippage_small = slippage_points(None, 0.01, model)
        slippage_large = slippage_points(None, 0.5, model)
        assert slippage_large > slippage_small


# ------------------------------------------------------------------
# 平方根滑点模型
# ------------------------------------------------------------------
class TestSqrtSlippage:
    def test_sqrt_sublinear_growth(self):
        """平方根滑点是次线性增长：订单翻倍，冲击增长不到一倍。"""
        base = 0.1
        impact_coeff = 1.0
        
        # 小订单
        s_small = sqrt_slippage(base, impact_coeff, 0.1)
        # 订单翻倍到 0.2
        s_double = sqrt_slippage(base, impact_coeff, 0.2)
        
        # 次线性：翻倍后冲击增长不到一倍
        # 如果是线性的，应该增长 2 倍；平方根模型增长不到 2 倍
        growth_ratio = (s_double - base) / (s_small - base)
        assert growth_ratio < 2.0  # 次线性（线性模型会是 2.0）


# ------------------------------------------------------------------
# 成交量冲击滑点
# ------------------------------------------------------------------
class TestVolumeImpact:
    def test_higher_volume_lower_slippage(self):
        """成交量越大，同样手数的滑点越小（流动性好）。"""
        base = 0.1
        impact_coeff = 1.0
        
        # 低流动性
        slippage_thin = volume_impact_slippage(
            base, impact_coeff, 
            order_size=10, market_volume=100  # 占10%
        )
        # 高流动性
        slippage_deep = volume_impact_slippage(
            base, impact_coeff,
            order_size=10, market_volume=1000  # 占1%
        )
        assert slippage_deep < slippage_thin


# ------------------------------------------------------------------
# 波动率调整滑点
# ------------------------------------------------------------------
class TestVolatilityAdjusted:
    def test_high_volatility_more_slippage(self):
        """高波动时期，滑点更大。"""
        base = 0.1
        atr = 2.0
        
        # 低波动
        slippage_low_vol = volatility_adjusted_slippage(
            base, atr, current_vol=0.5, avg_vol=1.0
        )
        # 高波动
        slippage_high_vol = volatility_adjusted_slippage(
            base, atr, current_vol=2.0, avg_vol=1.0
        )
        assert slippage_high_vol > slippage_low_vol


# ------------------------------------------------------------------
# 综合滑点估算
# ------------------------------------------------------------------
class TestTotalSlippage:
    def test_total_slippage_positive(self):
        """综合滑点估算应该为正。"""
        model = CostModel(
            base_spread=0.2,
            news_spread=0.5,
            gap_spread=1.0,
            gap_threshold=1.0,
            base_slippage=0.1,
            slippage_per_volume_frac=0.5,
            commission_per_lot=7.0,
        )
        
        total = estimate_total_slippage(
            cost_model=model,
            order_frac=0.1,
            current_vol_ratio=1.0,
            atr=2.0,
        )
        assert total > 0
