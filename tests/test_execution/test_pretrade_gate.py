# -*- coding: utf-8 -*-
"""tests.test_execution.test_pretrade_gate —— 统一 pre-trade 风控闸单测。"""
from __future__ import annotations

import math

import pytest

from core.execution.pretrade_gate import (
    ProposedOrder,
    RiskLimits,
    RiskProjection,
    evaluate_pretrade_gate,
    evaluate_projected_limits,
    evaluate_risk_limits,
    project_proposed,
)

P = "accountRisk."


def _projection(**kw) -> RiskProjection:
    defaults = dict(capital_budget=1000.0)
    defaults.update(kw)
    return RiskProjection(**defaults)


def _proposed(**kw) -> ProposedOrder:
    defaults = dict(symbol="BTC/USDT", side="long", quantity=10.0, price=100.0)
    defaults.update(kw)
    return ProposedOrder(**defaults)


def test_clean_order_passes():
    risk = evaluate_risk_limits(_projection(), _proposed(), RiskLimits())
    assert risk.allowed is True
    assert risk.violations == []
    assert risk.gross_notional == pytest.approx(1000.0)


def test_proposed_merges_into_projection():
    projected, missing = project_proposed(_projection(), _proposed(side="short"))
    assert missing is False
    assert projected.short_notional == pytest.approx(1000.0)
    assert projected.long_notional == 0.0
    assert projected.symbol_gross["BTC/USDT"] == pytest.approx(1000.0)
    # leverage=1 → margin = notional
    assert projected.margin_estimate == pytest.approx(1000.0)


def test_gross_notional_exceeded():
    limits = RiskLimits(max_gross_notional=500.0)
    risk = evaluate_risk_limits(_projection(), _proposed(), limits)
    assert not risk.allowed
    assert P + "grossNotionalExceeded" in risk.violations


def test_margin_exceeded():
    limits = RiskLimits(max_margin_estimate=500.0)
    risk = evaluate_risk_limits(_projection(), _proposed(leverage=1.0), limits)
    assert P + "marginEstimateExceeded" in risk.violations


def test_fee_budget_exceeded():
    limits = RiskLimits(max_round_trip_fee=1.0)
    risk = evaluate_risk_limits(
        _projection(), _proposed(fee_rate=0.001), limits
    )
    # fee = 1000 * 0.001 * 2 = 2.0
    assert risk.fee_estimate == pytest.approx(2.0)
    assert P + "feeBudgetExceeded" in risk.violations


def test_funding_budget_exceeded():
    limits = RiskLimits(max_funding_per_interval=5.0)
    risk = evaluate_risk_limits(
        _projection(), _proposed(funding_rate=0.01), limits
    )
    assert risk.funding_estimate == pytest.approx(10.0)
    assert P + "fundingBudgetExceeded" in risk.violations


def test_gross_leverage_exceeded():
    limits = RiskLimits(max_gross_leverage=0.5)
    risk = evaluate_risk_limits(_projection(capital_budget=1000.0), _proposed(), limits)
    assert risk.gross_leverage == pytest.approx(1.0)
    assert P + "grossLeverageExceeded" in risk.violations


def test_symbol_gross_exceeded():
    proj = _projection(symbol_gross={"BTC/USDT": 800.0})
    limits = RiskLimits(max_symbol_gross_notional=500.0)
    risk = evaluate_risk_limits(proj, _proposed(quantity=2.0, price=100.0), limits)
    # 800 + 200 = 1000
    assert P + "symbolGrossNotionalExceeded" in risk.violations


def test_proposed_price_missing():
    risk = evaluate_risk_limits(_projection(), _proposed(price=0.0), RiskLimits())
    assert risk.proposed_price_missing is True
    assert P + "proposedPriceMissing" in risk.violations


def test_existing_unpriced_position_flagged():
    proj = _projection(unpriced_position_count=1)
    risk = evaluate_risk_limits(proj, _proposed(), RiskLimits())
    assert P + "positionPriceMissing" in risk.violations


def test_zero_limit_disables_constraint():
    # 超限但限额为 0（不启用）→ 不报对应码
    risk = evaluate_risk_limits(
        _projection(), _proposed(), RiskLimits(max_gross_notional=0.0)
    )
    assert P + "grossNotionalExceeded" not in risk.violations


def test_hedge_ratio_and_net_notional():
    proj = _projection(long_notional=600.0, short_notional=400.0)
    risk = evaluate_risk_limits(proj, _proposed(quantity=0.0), RiskLimits())
    assert risk.net_notional == pytest.approx(200.0)
    assert risk.hedge_ratio == pytest.approx(400.0 / 600.0)


def test_gate_rejects_when_ownership_rejected():
    risk = evaluate_risk_limits(_projection(), _proposed(), RiskLimits())
    gate = evaluate_pretrade_gate(
        ownership_allowed=False,
        ownership_error="position_drift_detected:side=long",
        risk=risk,
    )
    assert not gate.allowed
    assert gate.ownership_error == "position_drift_detected:side=long"
    assert gate.violations == []


def test_gate_rejects_when_risk_rejected():
    limits = RiskLimits(max_gross_notional=500.0)
    risk = evaluate_risk_limits(_projection(), _proposed(), limits)
    gate = evaluate_pretrade_gate(ownership_allowed=True, risk=risk)
    assert not gate.allowed
    assert P + "grossNotionalExceeded" in gate.violations
    assert gate.ownership_error == ""


def test_gate_allows_when_both_pass():
    risk = evaluate_risk_limits(_projection(), _proposed(), RiskLimits())
    gate = evaluate_pretrade_gate(ownership_allowed=True, risk=risk)
    assert gate.allowed is True
    assert gate.audit["ownership_allowed"] is True
    assert gate.audit["risk_allowed"] is True


def test_invalid_inputs_tolerated():
    risk = evaluate_risk_limits(
        _projection(),
        _proposed(quantity="bad", price=None),
        RiskLimits(),
    )
    assert risk.gross_notional == 0.0
    assert risk.allowed is True


def test_infinite_quantity_normalized_to_zero():
    # inf 数量不得产生 inf 名义敞口；限额禁用时也不得 fail-open 放行 inf 仓位
    risk = evaluate_risk_limits(
        _projection(),
        _proposed(quantity=float("inf"), price=100.0),
        RiskLimits(),
    )
    assert risk.gross_notional == 0.0
    assert not math.isinf(risk.gross_notional)
    assert risk.proposed_price_missing is False


def test_nan_price_treated_as_missing():
    # NaN 价格归一为 0；有数量无有效价格须判价格缺失并留痕
    risk = evaluate_risk_limits(
        _projection(),
        _proposed(quantity=10.0, price=float("nan")),
        RiskLimits(),
    )
    assert risk.gross_notional == 0.0
    assert risk.proposed_price_missing is True
    assert P + "proposedPriceMissing" in risk.violations


def test_infinite_leverage_falls_back_to_default():
    risk = evaluate_risk_limits(
        _projection(),
        _proposed(quantity=10.0, price=100.0, leverage=float("inf")),
        RiskLimits(),
    )
    # leverage 归默认 1.0 → margin = notional = 1000，不产生 inf margin
    assert risk.margin_estimate == pytest.approx(1000.0)
    assert not math.isinf(risk.margin_estimate)


# ------------------------------------------------- 全量投影直接判定（shadow 对照）
def test_projected_limits_clean_passes():
    projected = _projection(long_notional=800.0, short_notional=200.0)
    risk = evaluate_projected_limits(projected, RiskLimits())
    assert risk.allowed is True
    assert risk.gross_notional == pytest.approx(1000.0)
    assert risk.net_notional == pytest.approx(600.0)


def test_projected_limits_does_not_remerge_proposed():
    # 投影已含 1000 long；再传一个 500 提议也不应二次并入（无增量入口）。
    projected = _projection(long_notional=1000.0)
    risk = evaluate_projected_limits(
        projected, RiskLimits(max_gross_notional=800.0),
        proposed_symbol="BTC/USDT",
    )
    assert not risk.allowed
    assert P + "grossNotionalExceeded" in risk.violations
    assert risk.gross_notional == pytest.approx(1000.0)


def test_projected_limits_proposed_price_missing_passthrough():
    projected = _projection()
    risk = evaluate_projected_limits(
        projected, RiskLimits(), proposed_price_missing=True,
    )
    assert not risk.allowed
    assert P + "proposedPriceMissing" in risk.violations


def test_projected_limits_symbol_gross_exceeded():
    projected = _projection(symbol_gross={"BTC/USDT": 1200.0})
    risk = evaluate_projected_limits(
        projected, RiskLimits(max_symbol_gross_notional=1000.0),
        proposed_symbol="BTC/USDT",
    )
    assert P + "symbolGrossNotionalExceeded" in risk.violations
