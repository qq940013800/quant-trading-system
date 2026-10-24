# -*- coding: utf-8 -*-
"""core.risk.sizing —— 仓位计算：固定分数 + 波动率目标叠加 + fractional Kelly 上限。

冻结接口（设计 3.2）：
    target_lots(equity, risk_pct, atr0, point_value,
                min_lot, lot_step, kelly_cap) -> float

纪律（硬规则 8 / 不变量 3）：
- 所有阈值/参数由调用方从 config 传入；本模块不出现业务字面量。
- atr0 为入场冻结的"每单位止损距离（价格单位）"。设计①式 size = 风险预算/(atr0*entryDist*point_value)，
  其中 entryDist 是入场到止损的价格距离；当 entry_dist 已按 2×atr0 校准后，调用方直接把冻结的
  止损距离（即 entry_dist 价格值）作为 atr0 形参传入，分母即 per-unit 风险价。
- 输出按 lot_step 向下取整；低于 min_lot 返回 0（不交易）；风险比例被 kelly_cap 截断。
"""
from __future__ import annotations

import math

import numpy as np


def quantile_threshold(values, q: float) -> float:
    """阈值来自分布（不变量 3）：从给定样本估计的 q 分位数派生阈值。

    依据注释：CLEAN 集统计量 -> np.quantile 取分位 -> 作为门限；
    禁止按绩效网格搜索产生阈值。q 由 config 指定（如 news/heat 分位）。
    """
    arr = np.asarray(list(values), dtype=float)
    if arr.size == 0:
        raise ValueError({"layer": "risk.sizing", "detail":
                           "quantile_threshold called on empty sample"})
    if not 0.0 <= q <= 1.0:
        raise ValueError({"layer": "risk.sizing", "detail": f"q out of [0,1]: {q}"})
    return float(np.quantile(arr, q))


def target_lots(equity: float, risk_pct: float, atr0: float,
                point_value: float, min_lot: float, lot_step: float,
                kelly_cap: float, max_lot: float = 100.0) -> float:
    """按冻结公式计算手数。

    参数（全部来自 config，禁止硬编码）：
        equity:        当前权益（USD）
        risk_pct:      固定分数风险比例（如 0.01 = 1%）
        atr0:          入场冻结的每单位止损距离（价格单位）
        point_value:   每手每 1.0 价格波动的盈亏（USD/手，XAUUSD≈100）
        min_lot:       最小手数
        lot_step:      手数步长
        kelly_cap:     fractional Kelly 上限（如 0.25 = 1/4 Kelly），截断 risk_pct
        max_lot:       最大手数（保护上限）
    返回：向下对齐 lot_step 的手数；低于 min_lot 返回 0.0。
    """
    if equity <= 0:
        raise ValueError({"layer": "risk.sizing", "detail": f"equity must be >0: {equity}"})
    if atr0 <= 0:
        raise ValueError({"layer": "risk.sizing", "detail": f"atr0(stop dist) must be >0: {atr0}"})
    if point_value <= 0:
        raise ValueError({"layer": "risk.sizing", "detail": f"point_value must be >0: {point_value}"})
    if lot_step <= 0:
        raise ValueError({"layer": "risk.sizing", "detail": f"lot_step must be >0: {lot_step}"})

    # fractional Kelly 上限：单笔风险比例不得超过 kelly_cap（设计：1/4~1/2 Kelly）
    eff_risk_pct = min(float(risk_pct), float(kelly_cap))
    risk_budget = equity * eff_risk_pct

    # 每手止损亏损 = 冻结止损距离 × point_value
    per_unit_risk = float(atr0) * float(point_value)
    raw_lots = risk_budget / per_unit_risk

    # 向下对齐 lot_step（禁止四舍五入放大风险）
    lots = math.floor(raw_lots / lot_step + 1e-9) * lot_step
    # 浮点步长对齐后裁剪小数尾差
    lots = round(lots, 8)
    if lots < min_lot:
        return 0.0
    return min(lots, float(max_lot))


def vol_target_scale(realized_vol: float, target_vol: float) -> float:
    """波动率目标叠加系数：实际波动 > 目标波动时降仓，否则不放大（上限 1.0）。

    scale = min(1.0, target_vol / realized_vol)。由引擎乘到 target_lots 结果上。
    realized_vol/target_vol 均由调用方从 CLEAN 分布估计（config 给出目标）。
    """
    if realized_vol <= 0 or target_vol <= 0:
        raise ValueError({"layer": "risk.sizing", "detail":
                           f"vol must be >0: realized={realized_vol}, target={target_vol}"})
    return float(min(1.0, target_vol / realized_vol))
