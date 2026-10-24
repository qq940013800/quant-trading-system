# -*- coding: utf-8 -*-
"""core.backtest.costs —— 分时段成本模型（三档点差 + 滑点 + 佣金）。

冻结接口（设计 3.2）：
    spread_at(bar, news_window) -> float
    slippage_points(bar, lot_fraction_of_volume) -> float

纪律（硬规则 8 / 设计⑦.C）：
- 所有成本参数由 CostModel 从 config 传入，禁止模块内业务字面量。
- spread_at 新闻窗口内 > 平静窗口默认点差（单测断言该不等式，防成本模型被旁路成常数）。
- 返回值一律为价格单位（USD，XAUUSD 报价币）；点->价换算由调用方/经纪商 SymbolInfo 负责。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Iterable, Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CostModel:
    """成本参数容器（全部来自 config；无默认业务值硬编码在逻辑里）。

    base_spread:      平静期点差（价格单位）
    news_spread:      新闻窗口（±news_minutes）点差
    gap_spread:       跳空 bar 点差
    gap_threshold:    |open - prev_close| 超过此值判为跳空（价格单位）
    base_slippage:    基础滑点（价格单位）
    slippage_per_volume_frac: 滑点随手数/成交量占比放大的系数
    commission_per_lot: 每手往返或单边佣金（USD/手），由 config 定义口径
    news_minutes:     新闻事件前后窗口分钟数
    """

    base_spread: float
    news_spread: float
    gap_spread: float
    gap_threshold: float
    base_slippage: float
    slippage_per_volume_frac: float
    commission_per_lot: float
    news_minutes: float = 15.0

    def tiers_valid(self) -> bool:
        """成本三档单调：新闻/跳空点差不得低于平静期（防配错导致零成本假设）。"""
        return self.news_spread >= self.base_spread and self.gap_spread >= self.base_spread


def is_news_time(bar_ts_utc: pd.Timestamp, news_window: Iterable[pd.Timestamp],
                news_minutes: float = 15.0) -> bool:
    """bar 时刻是否落在任一新闻事件 ±news_minutes 窗口内。"""
    if not news_window:
        return False
    half = timedelta(minutes=float(news_minutes))
    for ev in news_window:
        if abs(bar_ts_utc - ev) <= half:
            return True
    return False


def spread_at(bar, news_window: Iterable[pd.Timestamp],
             prev_close: Optional[float] = None,
             cost_model: Optional[CostModel] = None,
             news_minutes: float = 15.0) -> float:
    """三档点差（价格单位）。

    优先级：跳空 bar > 新闻窗口 > 平静期。
    cost_model 为 None 时用 base_spread=0 的零成本退化（仅对照实验，默认不用于正式回测）。
    """
    if cost_model is None:
        return 0.0

    # 跳空判定：本 bar.open 相对上一 bar.close 的跳空幅度
    if prev_close is not None:
        try:
            if abs(float(bar.open_) - float(prev_close)) > cost_model.gap_threshold:
                return float(cost_model.gap_spread)
        except AttributeError as e:
            raise ValueError({"layer": "backtest.costs", "detail":
                              f"bar missing open_ attr for gap check: {e}"}) from e

    if is_news_time(bar.ts_utc, news_window,
                    cost_model.news_minutes if cost_model else news_minutes):
        return float(cost_model.news_spread)

    return float(cost_model.base_spread)


def slippage_points(bar, lot_fraction_of_volume: float,
                    cost_model: Optional[CostModel] = None) -> float:
    """滑点（价格单位）。手数占该 bar 成交量比例越大，滑点越深。"""
    if cost_model is None:
        return 0.0
    frac = min(max(float(lot_fraction_of_volume), 0.0), 1.0)
    return float(cost_model.base_slippage) + \
        float(cost_model.slippage_per_volume_frac) * frac


# ------------------------------------------------------------------
# 高级滑点模型
# ------------------------------------------------------------------
def sqrt_slippage(base_slippage: float, impact_coeff: float,
                  order_fraction: float) -> float:
    """平方根滑点模型（更符合实际市场冲击）。

    第一性原理：市场冲击不是线性的——
    小单子冲击小，大单子冲击增长变慢（因为流动性是分层的）。
    平方根模型比线性模型更接近真实市场。

    Args:
        base_slippage: 基础滑点
        impact_coeff: 冲击系数
        order_fraction: 订单占市场成交量比例

    Returns:
        滑点（价格单位）
    """
    frac = min(max(order_fraction, 0.0), 1.0)
    return float(base_slippage) + float(impact_coeff) * np.sqrt(frac)


def volume_impact_slippage(base_slippage: float, impact_coeff: float,
                           order_size: float, market_volume: float) -> float:
    """成交量冲击滑点（基于订单占市场成交量比例）。

    Args:
        base_slippage: 基础滑点
        impact_coeff: 冲击系数
        order_size: 订单大小（手数）
        market_volume: 市场总成交量（手数）

    Returns:
        滑点（价格单位）
    """
    if market_volume <= 0:
        return base_slippage * 3  # 流动性极差，滑点放大3倍
    frac = order_size / market_volume
    return sqrt_slippage(base_slippage, impact_coeff, frac)


def volatility_adjusted_slippage(base_slippage: float, atr: float,
                                  current_vol: float, avg_vol: float) -> float:
    """波动率调整滑点。

    第一性原理：波动大的时候，点差会扩大，滑点也会变大——
    做市商要求更多补偿来承担库存风险。

    Args:
        base_slippage: 平均波动率下的基础滑点
        atr: 当前 ATR
        current_vol: 当前波动率
        avg_vol: 平均波动率

    Returns:
        调整后的滑点
    """
    if avg_vol <= 0:
        return base_slippage
    vol_ratio = current_vol / avg_vol
    # 波动率越高，滑点越大（次线性关系）
    return float(base_slippage) * (1.0 + 0.5 * np.log(vol_ratio))


def estimate_total_slippage(cost_model: CostModel,
                            order_frac: float = 0.01,
                            current_vol_ratio: float = 1.0,
                            atr: float = 1.0) -> float:
    """综合滑点估算（基础 + 冲击 + 波动率调整）。

    Args:
        cost_model: 成本模型
        order_frac: 订单占市场成交量比例
        current_vol_ratio: 当前波动率/平均波动率
        atr: 当前 ATR

    Returns:
        总滑点估计
    """
    # 1. 基础滑点 + 线性冲击
    base_slip = slippage_points(None, order_frac, cost_model)
    
    # 2. 波动率调整
    vol_slip = volatility_adjusted_slippage(
        cost_model.base_slippage, atr,
        current_vol=current_vol_ratio,
        avg_vol=1.0,
    )
    
    # 取两者的较大值（保守估计）
    return max(base_slip, vol_slip)
