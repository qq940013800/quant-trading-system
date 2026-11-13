# -*- coding: utf-8 -*-
"""core.execution.pretrade_gate —— 统一 pre-trade 风控闸纯判断。

第一性原理：
    任何入口（策略自动 / 手动 / 快捷）在下单前必须经过同一套风险限额与归属判断；
    闸口失败默认拒绝（fail-closed）。取数、REST、写库都在适配器侧，本模块只做
    纯计算：把提议订单并入账户投影 → 对照限额产出违规码 → 组合归属结论。

口径与后端 ``app.services.live_trading.account_risk`` 对齐，避免双份口径漂移；
violation 码前缀保持 ``accountRisk.``。限额为 0 表示该约束不启用。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

_TOL = 1e-8
_VIOLATION_PREFIX = "accountRisk."


def _nonneg(value: Any) -> float:
    try:
        v = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(v) or v <= 0:
        return 0.0
    return v


def _positive(value: Any, default: float = 0.0) -> float:
    try:
        v = float(value or 0.0)
    except (TypeError, ValueError):
        return _nonneg(default)
    if not math.isfinite(v) or v <= 0:
        return _nonneg(default)
    return v


@dataclass(frozen=True)
class RiskProjection:
    """账户既有持仓投影（适配器从账本行/成交腿聚合后注入，纯数据）。"""

    long_notional: float = 0.0
    short_notional: float = 0.0
    margin_estimate: float = 0.0
    fee_estimate: float = 0.0
    funding_estimate: float = 0.0
    symbol_gross: dict[str, float] = field(default_factory=dict)
    capital_budget: float = 0.0
    gross_capacity: float = 0.0
    unpriced_position_count: int = 0


@dataclass(frozen=True)
class ProposedOrder:
    """提议入场订单（金额/费率由适配器在调用前冻结注入）。"""

    symbol: str = ""
    side: str = ""
    quantity: float = 0.0
    price: float = 0.0
    leverage: float = 1.0
    fee_rate: float = 0.0
    funding_rate: float = 0.0


@dataclass(frozen=True)
class RiskLimits:
    """账户风险限额；字段为 0 表示该约束不启用（回退默认在适配器侧完成）。"""

    max_gross_notional: float = 0.0
    max_symbol_gross_notional: float = 0.0
    max_margin_estimate: float = 0.0
    max_round_trip_fee: float = 0.0
    max_funding_per_interval: float = 0.0
    max_gross_leverage: float = 0.0


@dataclass(frozen=True)
class RiskGateResult:
    """风险限额判定结果（纯结果，含审计指标）。"""

    allowed: bool
    violations: list[str]
    long_notional: float
    short_notional: float
    gross_notional: float
    net_notional: float
    hedge_ratio: float
    gross_leverage: float
    margin_estimate: float
    fee_estimate: float
    funding_estimate: float
    symbol_gross: dict[str, float]
    proposed_price_missing: bool


def project_proposed(
    projection: RiskProjection,
    proposed: ProposedOrder,
) -> tuple[RiskProjection, bool]:
    """把提议订单并入账户投影；返回 ``(并入后投影, proposed_price_missing)``。"""
    qty = _nonneg(proposed.quantity)
    price = _nonneg(proposed.price)
    notional = qty * price
    price_missing = qty > 0 and price <= 0

    long_n = projection.long_notional
    short_n = projection.short_notional
    margin = projection.margin_estimate
    fee = projection.fee_estimate
    funding = projection.funding_estimate
    symbol_gross = dict(projection.symbol_gross)

    if notional > 0:
        if str(proposed.side or "").strip().lower() == "short":
            short_n += notional
        else:
            long_n += notional
        if proposed.symbol:
            symbol_gross[proposed.symbol] = (
                symbol_gross.get(proposed.symbol, 0.0) + notional
            )
        lev = max(1.0, _positive(proposed.leverage, 1.0))
        margin += notional / lev
        fee += notional * _nonneg(proposed.fee_rate) * 2.0
        funding += notional * _nonneg(proposed.funding_rate)

    projected = RiskProjection(
        long_notional=long_n,
        short_notional=short_n,
        margin_estimate=margin,
        fee_estimate=fee,
        funding_estimate=funding,
        symbol_gross=symbol_gross,
        capital_budget=projection.capital_budget,
        gross_capacity=projection.gross_capacity,
        unpriced_position_count=projection.unpriced_position_count,
    )
    return projected, price_missing


def _judge(
    projected: RiskProjection,
    limits: RiskLimits,
    *,
    proposed_symbol: str,
    price_missing: bool,
) -> RiskGateResult:
    """对已并入提议的全量投影对照限额判定（纯函数，公共判定层）。"""
    gross = projected.long_notional + projected.short_notional
    net = projected.long_notional - projected.short_notional
    max_side = max(projected.long_notional, projected.short_notional)
    hedge_ratio = (
        min(projected.long_notional, projected.short_notional) / max_side
        if max_side > 0
        else 0.0
    )
    gross_leverage = (
        gross / projected.capital_budget if projected.capital_budget > 0 else 0.0
    )

    violations: list[str] = []
    if projected.unpriced_position_count > 0:
        violations.append(_VIOLATION_PREFIX + "positionPriceMissing")
    if price_missing:
        violations.append(_VIOLATION_PREFIX + "proposedPriceMissing")
    if limits.max_gross_notional > 0 and gross > limits.max_gross_notional + _TOL:
        violations.append(_VIOLATION_PREFIX + "grossNotionalExceeded")
    if (
        limits.max_margin_estimate > 0
        and projected.margin_estimate > limits.max_margin_estimate + _TOL
    ):
        violations.append(_VIOLATION_PREFIX + "marginEstimateExceeded")
    if (
        limits.max_round_trip_fee > 0
        and projected.fee_estimate > limits.max_round_trip_fee + _TOL
    ):
        violations.append(_VIOLATION_PREFIX + "feeBudgetExceeded")
    if (
        limits.max_funding_per_interval > 0
        and projected.funding_estimate > limits.max_funding_per_interval + _TOL
    ):
        violations.append(_VIOLATION_PREFIX + "fundingBudgetExceeded")
    if (
        limits.max_gross_leverage > 0
        and gross_leverage > limits.max_gross_leverage + _TOL
    ):
        violations.append(_VIOLATION_PREFIX + "grossLeverageExceeded")
    if limits.max_symbol_gross_notional > 0 and proposed_symbol:
        if (
            projected.symbol_gross.get(proposed_symbol, 0.0)
            > limits.max_symbol_gross_notional + _TOL
        ):
            violations.append(_VIOLATION_PREFIX + "symbolGrossNotionalExceeded")

    return RiskGateResult(
        allowed=not violations,
        violations=violations,
        long_notional=projected.long_notional,
        short_notional=projected.short_notional,
        gross_notional=gross,
        net_notional=net,
        hedge_ratio=hedge_ratio,
        gross_leverage=gross_leverage,
        margin_estimate=projected.margin_estimate,
        fee_estimate=projected.fee_estimate,
        funding_estimate=projected.funding_estimate,
        symbol_gross=projected.symbol_gross,
        proposed_price_missing=price_missing,
    )


def evaluate_risk_limits(
    projection: RiskProjection,
    proposed: ProposedOrder,
    limits: RiskLimits,
) -> RiskGateResult:
    """对照账户限额判定提议订单；纯函数、无 I/O。

    先把提议增量并入既有投影（``project_proposed``），再走公共限额判定。
    """
    projected, price_missing = project_proposed(projection, proposed)
    return _judge(
        projected, limits,
        proposed_symbol=proposed.symbol, price_missing=price_missing,
    )


def evaluate_projected_limits(
    projection: RiskProjection,
    limits: RiskLimits,
    *,
    proposed_symbol: str = "",
    proposed_price_missing: bool = False,
) -> RiskGateResult:
    """对**已含提议**的全量投影直接判定，不再二次并入提议。

    供适配器 shadow 对照使用：后端快照已把提议并入全量（与本模块
    ``project_proposed`` 增量模型不同），直接喂入全量投影即可逐条比对
    violation 码，无需先拆分既有持仓与提议增量。限额回退默认仍在适配器侧完成。
    """
    return _judge(
        projection, limits,
        proposed_symbol=proposed_symbol,
        price_missing=proposed_price_missing,
    )


@dataclass(frozen=True)
class PretradeGateResult:
    """归属 + 风险组合闸结果（fail-closed）。"""

    allowed: bool
    violations: list[str]
    ownership_error: str
    audit: dict[str, Any]


def evaluate_pretrade_gate(
    *,
    ownership_allowed: bool,
    ownership_error: str = "",
    risk: RiskGateResult,
) -> PretradeGateResult:
    """组合归属闸与风险闸：任一不通过即拒绝；失败留痕原因码。"""
    ownership_ok = bool(ownership_allowed)
    risk_ok = risk.allowed
    allowed = ownership_ok and risk_ok
    audit: dict[str, Any] = {
        "ownership_allowed": ownership_ok,
        "risk_allowed": risk_ok,
        "gross_notional": risk.gross_notional,
        "gross_leverage": risk.gross_leverage,
    }
    return PretradeGateResult(
        allowed=allowed,
        violations=list(risk.violations),
        ownership_error=ownership_error or "",
        audit=audit,
    )
