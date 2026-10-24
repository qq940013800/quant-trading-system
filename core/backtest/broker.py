# -*- coding: utf-8 -*-
"""core.backtest.broker —— 成交模拟（点差+滑点+佣金）。

多头买入吃 ask = ref + spread/2 + slippage；空头卖出吃 bid = ref - spread/2 - slippage。
佣金按手数计。返回成交价与成本（USD）。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Fill:
    fill_price: float     # 实际成交价（价格单位）
    cost: float           # 本次成交总成本（USD，含点差/滑点折算 + 佣金）
    slippage_price: float  # 成交价相对 ref 的不利偏移（价格单位）


def simulate_fill(direction: int, ref_price: float, spread: float,
                  slippage: float, commission_per_lot: float,
                  lots: float, point_value: float) -> Fill:
    """按方向与成本参数模拟成交。

    direction=+1 买：成交价 = ref + spread/2 + slippage
    direction=-1 卖：成交价 = ref - spread/2 - slippage
    point_value: 每手每 1.0 价格波动的 USD，用于把 spread/slippage 折成 USD 成本。
    """
    if direction not in (+1, -1):
        raise ValueError({"layer": "backtest.broker", "detail":
                          f"direction must be +1/-1, got {direction}"})
    if lots <= 0:
        raise ValueError({"layer": "backtest.broker", "detail":
                          f"lots must be >0, got {lots}"})

    half_spread = float(spread) / 2.0
    adverse = half_spread + float(slippage)            # 不利价格偏移
    fill_price = float(ref_price) + direction * adverse
    spread_cost_usd = adverse * float(lots) * float(point_value)
    commission_usd = float(commission_per_lot) * float(lots)
    return Fill(fill_price=fill_price,
                slippage_price=adverse,
                cost=spread_cost_usd + commission_usd)
