# -*- coding: utf-8 -*-
"""core.risk.drawdown_tier —— 回撤分级降档纯函数（tiered de-risking）。

第一性原理：
    回撤扩大时不应一次性清仓，也不应维持满仓；按回撤深度逐级下调仓位系数
    （海龟式阶梯降档）。分级算术与阈值解耦：步长、每档系数、起始系数、最大
    档位全部由调用方/配置注入，本模块不写死业务阈值，也不读库、不下单。

口径（与历史回测引擎等价）：
    dd = equity / peak_equity - 1；
    steps = floor(-dd / dd_step)，截断到 ≥0；
    factor = base_factor * tier_mult ** steps。

不变量：
- peak_equity ≤ 0 或权益非有限时安全降级为 base_factor（不放大、不额外降档）；
- tier_mult 必须在 (0, 1]：>1 会随回撤放大仓位，违背降档语义；
- 纯函数：无 IO、无随机、无全局状态。
"""
from __future__ import annotations

import math
from typing import Any


def _finite(name: str, val: Any) -> float:
    v = float(val)
    if not math.isfinite(v):
        raise ValueError(f"drawdown_tier: {name} 必须为有限数，收到 {val!r}")
    return v


def drawdown_tier_factor(
    equity: float,
    peak_equity: float,
    *,
    dd_step: float = 0.10,
    tier_mult: float = 0.8,
    base_factor: float = 1.0,
    max_steps: int | None = None,
) -> float:
    """按当前权益相对峰值的回撤深度计算仓位降档系数。

    Args:
        equity: 当前权益（有限数）。
        peak_equity: 历史峰值权益；≤0 时安全降级为 base_factor。
        dd_step: 每档回撤步长（正数，如 0.10 = 每回撤 10% 一档）。
        tier_mult: 每档仓位系数，必须 ∈ (0, 1]。
        base_factor: 未触发任何档位时的起始系数（>0）。
        max_steps: 可选最大档位（非负整数）；None 表示不封顶。

    Returns:
        仓位系数 base_factor * tier_mult ** steps；无回撤/峰值非法时返回 base_factor。
    """
    eq = _finite("equity", equity)
    peak = _finite("peak_equity", peak_equity)
    step = _finite("dd_step", dd_step)
    mult = _finite("tier_mult", tier_mult)
    base = _finite("base_factor", base_factor)

    if step <= 0:
        raise ValueError(f"dd_step 必须 >0，收到 {step!r}")
    if not (0.0 < mult <= 1.0):
        raise ValueError(f"tier_mult 必须 ∈ (0, 1]，收到 {mult!r}")
    if base <= 0:
        raise ValueError(f"base_factor 必须 >0，收到 {base!r}")
    if max_steps is not None:
        if isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps < 0:
            raise ValueError(f"max_steps 必须为非负整数或 None，收到 {max_steps!r}")

    if peak <= 0:
        return float(base)

    dd = eq / peak - 1.0
    raw_steps = math.floor(-dd / step)
    steps = max(0, raw_steps)
    if max_steps is not None:
        steps = min(steps, max_steps)
    return float(base * mult ** steps)
