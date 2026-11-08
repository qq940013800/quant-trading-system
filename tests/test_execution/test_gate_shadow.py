# -*- coding: utf-8 -*-
"""tests.test_execution.test_gate_shadow —— 后端快照 ↔ core 判定 shadow 对照单测。"""
from __future__ import annotations

from core.execution.gate_shadow import (
    build_limits,
    build_projection,
    compare_snapshot,
)

P = "accountRisk."


def _snapshot(**kw) -> dict:
    base = {
        "allowed": True,
        "violations": [],
        "long_notional": 0.0,
        "short_notional": 0.0,
        "gross_notional": 0.0,
        "margin_estimate": 0.0,
        "round_trip_fee_estimate": 0.0,
        "funding_per_interval_estimate": 0.0,
        "capital_budget": 1000.0,
        "gross_capacity": 1000.0,
        "symbol_gross_notional": {},
        "unpriced_position_count": 0,
        "limits": {
            "max_gross_notional": 0.0,
            "max_symbol_gross_notional": 0.0,
            "max_margin_estimate": 0.0,
            "max_round_trip_fee": 0.0,
            "max_funding_per_interval": 0.0,
            "max_gross_leverage": 0.0,
        },
    }
    base.update(kw)
    return base


def test_clean_snapshot_matches():
    out = compare_snapshot(_snapshot())
    assert out["match"] is True
    assert out["core_allowed"] is True
    assert out["backend_allowed"] is True
    assert out["only_core"] == []
    assert out["only_backend"] == []
    assert out["missing_fields"] == []


def test_consistent_gross_exceeded():
    snap = _snapshot(
        long_notional=1200.0,
        gross_notional=1200.0,
        allowed=False,
        violations=[P + "grossNotionalExceeded"],
        limits={"max_gross_notional": 1000.0},
    )
    out = compare_snapshot(snap, proposed_symbol="BTC/USDT")
    assert out["match"] is True
    assert out["core_allowed"] is False
    assert out["backend_allowed"] is False
    assert P + "grossNotionalExceeded" in out["core_violations"]


def test_core_extra_violation_flagged_only_core():
    # 后端漏判：快照自报放行，但投影已超 core 限额。
    snap = _snapshot(
        long_notional=1200.0,
        gross_notional=1200.0,
        allowed=True,
        violations=[],
        limits={"max_gross_notional": 1000.0},
    )
    out = compare_snapshot(snap)
    assert out["match"] is False
    assert out["core_allowed"] is False
    assert out["backend_allowed"] is True
    assert out["only_core"] == [P + "grossNotionalExceeded"]
    assert out["only_backend"] == []


def test_backend_extra_violation_flagged_only_backend():
    # 后端多报：core 限额 0（不启用）不应判超限，差异归入 only_backend。
    snap = _snapshot(
        long_notional=1200.0,
        allowed=False,
        violations=[P + "grossNotionalExceeded"],
        limits={"max_gross_notional": 0.0},
    )
    out = compare_snapshot(snap)
    assert out["match"] is False
    assert out["core_allowed"] is True
    assert out["only_core"] == []
    assert out["only_backend"] == [P + "grossNotionalExceeded"]


def test_missing_fields_degrade_to_zero_without_raise():
    out = compare_snapshot({})
    assert out["core_allowed"] is True
    assert out["missing_fields"]  # 记录缺失，不阻断
    assert "long_notional" in out["missing_fields"]
    assert "limits" in out["missing_fields"]


def test_fee_funding_symbol_gross_mapped_into_projection():
    snap = _snapshot(
        round_trip_fee_estimate=3.0,
        funding_per_interval_estimate=4.0,
        symbol_gross_notional={"BTC/USDT": 500.0},
    )
    proj = build_projection(snap)
    assert proj.fee_estimate == 3.0
    assert proj.funding_estimate == 4.0
    assert proj.symbol_gross["BTC/USDT"] == 500.0
    limits = build_limits(snap)
    assert limits.max_gross_notional == 0.0


def test_proposed_price_missing_passthrough_only_core():
    snap = _snapshot(allowed=True, violations=[])
    out = compare_snapshot(snap, proposed_price_missing=True)
    assert out["core_allowed"] is False
    assert out["only_core"] == [P + "proposedPriceMissing"]


def test_non_mapping_snapshot_safe():
    for bad in (None, [], "nope", 123):
        out = compare_snapshot(bad)  # type: ignore[arg-type]
        assert out["core_allowed"] is True
        assert out["match"] is True
        assert out["missing_fields"] == ["snapshot_not_mapping"]
