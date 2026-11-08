# -*- coding: utf-8 -*-
"""core.execution.economics_gate —— 边际经济准入纯判断。

第一性原理：
    一笔交易只有在预期边际收益覆盖往返成本并留出安全边际时才值得开仓。
    预期收益不达成本的 k 倍，边际上不经济，应在前置闸拒绝（fail-closed）。

边界与不变量：
- 纯函数：无 IO、不查库、不发起下单；只给准入判断与审计指标。
- 阈值（k 倍）由调用方/配置注入，模块内不写业务阈值（AGENTS 硬规则 8）。
- 输入守卫：边际收益有限；往返成本有限且非负；倍数 ≥1。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class EconomicsResult:
    """边际经济准入结果（纯结果，含审计指标）。"""

    allowed: bool
    expected_edge: float
    round_trip_cost: float
    edge_cost_ratio: Optional[float]  # edge/cost；成本为 0 时为 None（不除零）
    reason: str


def economics_gate(
    *,
    expected_edge: float,
    round_trip_cost: float,
    min_edge_multiple: float = 2.0,
) -> EconomicsResult:
    """判断预期边际收益是否达到往返成本的安全倍数。

    Args:
        expected_edge: 预期单笔边际收益（与成本同口径，金额或价格单位）。
        round_trip_cost: 往返成本（点差 + 滑点 + 佣金 + 资金费估算）。
        min_edge_multiple: 放行所需最低收益/成本倍数，须 ≥1。

    Returns:
        ``EconomicsResult``：``allowed`` 为是否放行，``edge_cost_ratio`` 为
        边际收益对成本的倍数（成本为 0 时为 None），``reason`` 留痕原因。
    """
    edge = float(expected_edge)
    cost = float(round_trip_cost)
    multiple = float(min_edge_multiple)

    if not math.isfinite(edge):
        raise ValueError("expected_edge 必须为有限数")
    if not math.isfinite(cost) or cost < 0:
        raise ValueError("round_trip_cost 必须为非负有限数")
    if not math.isfinite(multiple) or multiple < 1.0:
        raise ValueError("min_edge_multiple 必须 ≥1")

    if cost <= 0:
        allowed = edge > 0
        reason = (
            "无往返成本约束，边际收益为正即放行"
            if allowed
            else "边际收益非正，拒绝"
        )
        return EconomicsResult(allowed, edge, cost, None, reason)

    ratio = edge / cost
    if edge >= multiple * cost:
        allowed = True
        reason = (
            f"边际收益 {edge:.4f} ≥ {multiple}×成本 {cost:.4f}"
            f"（倍数 {ratio:.2f}）"
        )
    else:
        allowed = False
        reason = (
            f"边际收益 {edge:.4f} 未达 {multiple}×成本 {cost:.4f}"
            f"（倍数 {ratio:.2f}）"
        )
    return EconomicsResult(allowed, edge, cost, ratio, reason)
