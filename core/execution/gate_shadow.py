# -*- coding: utf-8 -*-
"""core.execution.gate_shadow —— 后端账户风险快照与 core 纯判定的 shadow 对照。

第一性原理：
    迁移到统一闸之前，先在**不改放行结果**的前提下并行跑 core 纯判定，
    与后端既有快照逐条比对 violation 集合；不一致只暴露差异供审计，
    不阻断、不下单、不写库。快照取数、限额回退、结果落库仍在后端适配器侧。

边界：
    - 本模块只做 dict 映射 + 纯判定 + 集合比对，不发起 REST、不查库、不写库；
    - 快照缺字段按 0 兜底并记入 ``missing_fields``，shadow 容错不抛异常；
    - violation 码前缀与 ``pretrade_gate`` / 后端 ``account_risk`` 保持 ``accountRisk.``。
"""
from __future__ import annotations

from typing import Any, Mapping

from .pretrade_gate import (
    RiskLimits,
    RiskProjection,
    evaluate_projected_limits,
)

# 后端快照字段 → core 投影字段（费用/资金费在后端用往返口径命名）。
_PROJECTION_FIELDS: dict[str, str] = {
    "long_notional": "long_notional",
    "short_notional": "short_notional",
    "margin_estimate": "margin_estimate",
    "round_trip_fee_estimate": "fee_estimate",
    "funding_per_interval_estimate": "funding_estimate",
    "capital_budget": "capital_budget",
    "gross_capacity": "gross_capacity",
}

# 后端快照 limits 子表字段 → core 限额字段（同名直映）。
_LIMIT_FIELDS: tuple[str, ...] = (
    "max_gross_notional",
    "max_symbol_gross_notional",
    "max_margin_estimate",
    "max_round_trip_fee",
    "max_funding_per_interval",
    "max_gross_leverage",
)

_PROJECTION_NUMERIC = set(_PROJECTION_FIELDS)
_PROJECTION_INT = {"unpriced_position_count"}


def _num(value: Any, default: float = 0.0) -> float:
    """容错转有限非负浮点；非有限/不可解析回退 default。"""
    try:
        v = float(value if value is not None else default)
    except (TypeError, ValueError):
        return default
    if v != v or v in (float("inf"), float("-inf")):
        return default
    return v if v > 0 else 0.0


def _count(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(float(value if value is not None else default)))
    except (TypeError, ValueError):
        return default


def _symbol_gross(value: Any) -> dict[str, float]:
    if not isinstance(value, Mapping):
        return {}
    out: dict[str, float] = {}
    for key, val in value.items():
        out[str(key)] = _num(val)
    return out


def build_projection(snapshot: Mapping[str, Any]) -> RiskProjection:
    """把后端快照 dict 映射为 core 投影；缺字段按 0 兜底。"""
    snapshot = snapshot if isinstance(snapshot, Mapping) else {}
    kwargs: dict[str, Any] = {}
    for src, dst in _PROJECTION_FIELDS.items():
        kwargs[dst] = _num(snapshot.get(src))
    kwargs["symbol_gross"] = _symbol_gross(snapshot.get("symbol_gross_notional"))
    kwargs["unpriced_position_count"] = _count(
        snapshot.get("unpriced_position_count")
    )
    return RiskProjection(**kwargs)


def build_limits(snapshot: Mapping[str, Any]) -> RiskLimits:
    """把后端快照 limits 子表映射为 core 限额；缺字段按 0（不启用约束）。"""
    snapshot = snapshot if isinstance(snapshot, Mapping) else {}
    limits_raw = snapshot.get("limits")
    limits_raw = limits_raw if isinstance(limits_raw, Mapping) else {}
    kwargs: dict[str, Any] = {}
    for field in _LIMIT_FIELDS:
        kwargs[field] = _num(limits_raw.get(field))
    return RiskLimits(**kwargs)


def _missing_fields(snapshot: Mapping[str, Any]) -> list[str]:
    """记录投影/限额关键缺失字段，供审计判断对照可信度（不阻断）。"""
    if not isinstance(snapshot, Mapping):
        return ["snapshot_not_mapping"]
    missing: list[str] = []
    for src in _PROJECTION_FIELDS:
        if src not in snapshot:
            missing.append(src)
    limits_raw = snapshot.get("limits")
    if not isinstance(limits_raw, Mapping):
        missing.append("limits")
    else:
        for field in _LIMIT_FIELDS:
            if field not in limits_raw:
                missing.append(f"limits.{field}")
    return missing


def compare_snapshot(
    snapshot: Mapping[str, Any],
    *,
    proposed_symbol: str = "",
    proposed_price_missing: bool = False,
) -> dict[str, Any]:
    """并行跑 core 全量投影判定，与后端快照 violation 集合比对。

    Returns:
        dict: ``match`` 两侧违规码集合是否一致；``core_allowed`` /
        ``backend_allowed`` 两侧放行结论；``core_violations`` /
        ``backend_violations`` 排序后的违规码；``only_core`` / ``only_backend``
        单边命中码；``estimates`` 侧记 core 估算指标；``missing_fields``
        缺失字段清单。shadow 对照不改后端既有放行结论。
    """
    raw = snapshot
    snapshot = raw if isinstance(raw, Mapping) else {}
    projection = build_projection(snapshot)
    limits = build_limits(snapshot)

    core_result = evaluate_projected_limits(
        projection,
        limits,
        proposed_symbol=proposed_symbol,
        proposed_price_missing=proposed_price_missing,
    )

    backend_raw = snapshot.get("violations")
    backend_violations = sorted(
        str(code) for code in backend_raw if isinstance(code, (str, bytes))
    ) if isinstance(backend_raw, (list, tuple)) else []
    core_violations = sorted(core_result.violations)

    only_core = sorted(set(core_violations) - set(backend_violations))
    only_backend = sorted(set(backend_violations) - set(core_violations))

    backend_allowed = snapshot.get("allowed")
    if not isinstance(backend_allowed, bool):
        backend_allowed = len(backend_violations) == 0

    return {
        "match": core_violations == backend_violations,
        "core_allowed": core_result.allowed,
        "backend_allowed": backend_allowed,
        "core_violations": core_violations,
        "backend_violations": backend_violations,
        "only_core": only_core,
        "only_backend": only_backend,
        "estimates": {
            "gross_notional": core_result.gross_notional,
            "net_notional": core_result.net_notional,
            "gross_leverage": core_result.gross_leverage,
            "margin_estimate": core_result.margin_estimate,
            "fee_estimate": core_result.fee_estimate,
            "funding_estimate": core_result.funding_estimate,
        },
        "missing_fields": _missing_fields(raw),
    }
