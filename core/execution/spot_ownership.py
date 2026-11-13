# -*- coding: utf-8 -*-
"""core.execution.spot_ownership —— 现货两层持仓口径与平仓封顶纯函数。

第一性原理：
    系统只对「自己跟踪到的净持仓」负有平仓语义；钱包 free 只是交易所侧的
    可成交物理上限，不是所有权口径。两层口径必须分开留痕，禁止把账户原有
    存量当作可处置额度。

纯逻辑约束：
    - 不触网、不读库；本地跟踪净额与钱包快照由适配器在调用前聚合/拉取后注入；
    - 不反推新风控阈值；``safety_ratio`` 为占位默认（对齐既有 env 默认 1.0），
      正式取值须经 CLEAN 分布校准；
    - free 未知时 fail-closed，不把 0 或缺失推断为无存量。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional

# 占位默认安全比率，非 CLEAN 校准产物（对齐 spot_sizing._DEFAULT_CLOSE_SAFETY）。
DEFAULT_CLOSE_SAFETY_RATIO = 1.0


def _nonneg(value: Any) -> float:
    """容错转非负浮点；非法/缺失/非有限按 0.0 处理。"""
    try:
        v = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(v):
        return 0.0
    return v if v > 0 else 0.0


def _valid_ratio(ratio: Optional[float]) -> float:
    if ratio is None:
        return DEFAULT_CLOSE_SAFETY_RATIO
    try:
        v = float(ratio)
    except (TypeError, ValueError):
        return DEFAULT_CLOSE_SAFETY_RATIO
    if not math.isfinite(v) or v <= 0 or v > 1.0:
        return DEFAULT_CLOSE_SAFETY_RATIO
    return v


@dataclass(frozen=True)
class SpotOwnershipSnapshot:
    """现货持仓两层口径快照（纯数据，不含 I/O）。

    Attributes:
        tracked_net: L1 系统跟踪净 base 量（本地台账聚合，非负）。
        wallet_total: L2 钱包 total（含锁定与账户原有存量）。
        wallet_free: L2 钱包可用 free；``None`` 表示未知（不可推断）。
        free_known: free 是否为已知有效值。
        unmanaged_stock: free 超出 tracked_net 的存量部分（不进入可平仓额度）。
        shortfall: tracked_net 超出 free 的口径缺口（成交漏记/手续费侵蚀等）。
        ownership_cap: L1 所有权硬上限（= tracked_net）。
        physical_cap: L2 物理上限（= free × 安全比率）；free 未知时为 ``None``。
    """

    tracked_net: float
    wallet_total: float
    wallet_free: Optional[float]
    free_known: bool
    unmanaged_stock: float
    shortfall: float
    ownership_cap: float
    physical_cap: Optional[float]


def resolve_spot_ownership(
    tracked_net: Any,
    wallet_total: Any,
    wallet_free: Optional[Any],
    safety_ratio: Optional[float] = DEFAULT_CLOSE_SAFETY_RATIO,
) -> SpotOwnershipSnapshot:
    """解析 L1/L2 两层持仓口径。

    Args:
        tracked_net: 本地系统跟踪净额（适配器聚合后注入）。
        wallet_total: 钱包 total 快照。
        wallet_free: 钱包可用 free；传 ``None`` 表示快照缺失/未知。
        safety_ratio: 物理上限安全比率（占位默认，待分布校准）。
    """
    tracked = _nonneg(tracked_net)
    total = _nonneg(wallet_total)

    if wallet_free is None:
        return SpotOwnershipSnapshot(
            tracked_net=tracked,
            wallet_total=total,
            wallet_free=None,
            free_known=False,
            unmanaged_stock=0.0,
            shortfall=0.0,
            ownership_cap=tracked,
            physical_cap=None,
        )

    free = _nonneg(wallet_free)
    ratio = _valid_ratio(safety_ratio)
    unmanaged = max(0.0, free - tracked)
    shortfall = max(0.0, tracked - free)
    physical = free * ratio

    return SpotOwnershipSnapshot(
        tracked_net=tracked,
        wallet_total=total,
        wallet_free=free,
        free_known=True,
        unmanaged_stock=unmanaged,
        shortfall=shortfall,
        ownership_cap=tracked,
        physical_cap=physical,
    )


@dataclass(frozen=True)
class SpotCloseDecision:
    """平仓数量决策（纯结果，含审计留痕）。"""

    final_qty: float
    intent: str
    allowed: bool
    reason_code: str
    capped_by: str
    audit: dict[str, Any]


def _floor_to_step(qty: float, lot_step: Optional[float]) -> float:
    """向下归一化到交易所步长；步长缺失/非法时不归一化。"""
    if lot_step is None:
        return qty
    try:
        step = float(lot_step)
    except (TypeError, ValueError):
        return qty
    if step <= 0:
        return qty
    return math.floor(qty / step) * step


def resolve_spot_close(
    snapshot: SpotOwnershipSnapshot,
    requested: Any,
    intent: str = "tracked",
    lot_step: Optional[float] = None,
) -> SpotCloseDecision:
    """按平仓意图计算可平仓数量并做两层封顶。

    Args:
        snapshot: :class:`SpotOwnershipSnapshot` 口径快照。
        requested: 请求平仓量。
        intent: ``tracked``（只平系统跟踪净额，L1 所有权硬上限）或
            ``full``（显式处置整个钱包持仓，仅以 L2 物理上限封顶，打标含存量）。
        lot_step: 交易所最小步长（适配器注入）；缺省不归一化。

    Returns:
        :class:`SpotCloseDecision`；拒绝时 ``allowed=False`` 并带原因码。
    """
    req = _nonneg(requested)
    normalized_intent = "full" if str(intent).strip().lower() == "full" else "tracked"
    audit: dict[str, Any] = {
        "intent": normalized_intent,
        "tracked_net": snapshot.tracked_net,
        "wallet_free": snapshot.wallet_free,
        "physical_cap": snapshot.physical_cap,
    }

    if req <= 0:
        return SpotCloseDecision(0.0, normalized_intent, False,
                                 "rejected_nonpositive", "none", audit)

    if not snapshot.free_known:
        # fail-closed：快照缺失不产出可平仓额度，不回退到按请求量放行。
        return SpotCloseDecision(0.0, normalized_intent, False,
                                 "rejected_free_unknown", "none", audit)

    if normalized_intent == "full":
        cap = snapshot.physical_cap
        capped_by = "physical"
        audit["includes_unmanaged_stock"] = True
    else:
        own = snapshot.ownership_cap
        phys = snapshot.physical_cap
        cap = min(own, phys)
        capped_by = "ownership" if own <= phys else "physical"

    if cap is None or cap <= 0:
        return SpotCloseDecision(0.0, normalized_intent, False,
                                 "rejected_no_cap", capped_by, audit)

    raw = min(req, cap)
    final = max(0.0, _floor_to_step(raw, lot_step))

    audit["requested"] = req
    audit["cap"] = cap
    audit["capped_before_normalize"] = raw
    audit["lot_step"] = lot_step
    return SpotCloseDecision(final, normalized_intent, True, "ok", capped_by, audit)
