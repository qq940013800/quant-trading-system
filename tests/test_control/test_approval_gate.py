# -*- coding: utf-8 -*-
"""tests.test_control.test_approval_gate —— 危险动作审批闸纯判定单测。"""
from __future__ import annotations

import pytest

from core.control.approval_gate import (
    ApprovalResult,
    RUNTIME_CONTROL,
    TRADING,
    WRITE_CONFIG,
    WRITE_DRAFT,
    evaluate_approval,
)


def test_read_level_passes():
    res = evaluate_approval(risk_level="read")
    assert res.allowed is True
    assert res.reason_code == "read_only_allowed"


def test_read_only_flag_passes_even_without_level():
    res = evaluate_approval(risk_level="", read_only=True)
    assert res.allowed is True
    assert res.reason_code == "read_only_allowed"


def test_draft_passes_without_confirmation():
    res = evaluate_approval(risk_level=WRITE_DRAFT, confirmed=False)
    assert res.allowed is True
    assert res.reason_code == "draft_allowed"


def test_write_config_requires_confirmation():
    res = evaluate_approval(risk_level=WRITE_CONFIG, confirmed=False)
    assert not res.allowed
    assert res.reason_code == "confirmation_required"

    ok = evaluate_approval(risk_level=WRITE_CONFIG, confirmed=True)
    assert ok.allowed is True
    assert ok.reason_code == "approved"


def test_runtime_control_requires_scope_and_confirmation():
    no_scope = evaluate_approval(
        risk_level=RUNTIME_CONTROL, confirmed=True, scope_granted=False
    )
    assert not no_scope.allowed
    assert no_scope.reason_code == "scope_required"

    no_confirm = evaluate_approval(
        risk_level=RUNTIME_CONTROL, confirmed=False, scope_granted=True
    )
    assert not no_confirm.allowed
    assert no_confirm.reason_code == "confirmation_required"

    ok = evaluate_approval(
        risk_level=RUNTIME_CONTROL, confirmed=True, scope_granted=True
    )
    assert ok.allowed is True


def test_trading_paper_passes_with_confirmation_and_scope():
    res = evaluate_approval(
        risk_level=TRADING, confirmed=True, scope_granted=True, is_paper=True
    )
    assert res.allowed is True
    assert res.reason_code == "approved"


def test_trading_live_requires_live_conditions():
    blocked = evaluate_approval(
        risk_level=TRADING,
        confirmed=True,
        scope_granted=True,
        is_paper=False,
        live_conditions_met=False,
    )
    assert not blocked.allowed
    assert blocked.reason_code == "live_conditions_required"

    ok = evaluate_approval(
        risk_level=TRADING,
        confirmed=True,
        scope_granted=True,
        is_paper=False,
        live_conditions_met=True,
    )
    assert ok.allowed is True


def test_unknown_level_fails_closed():
    res = evaluate_approval(risk_level="nuclear_launch", confirmed=True)
    assert not res.allowed
    assert res.reason_code == "unknown_risk_level"


def test_audit_records_inputs():
    res = evaluate_approval(
        risk_level=TRADING,
        confirmed=False,
        scope_granted=True,
        is_paper=True,
    )
    assert res.audit["risk_level"] == TRADING
    assert res.audit["confirmed"] is False
    assert res.audit["scope_granted"] is True
    assert res.audit["is_paper"] is True


class TestResultGuard:
    @pytest.mark.parametrize("bad", [1, 0, "true", None, ""])
    def test_allowed_must_be_bool(self, bad):
        with pytest.raises(ValueError):
            ApprovalResult(bad, "approved", {})

    @pytest.mark.parametrize("bad", ["", "   ", None, 123])
    def test_reason_code_must_be_nonempty_str(self, bad):
        with pytest.raises(ValueError):
            ApprovalResult(True, bad, {})

    @pytest.mark.parametrize("bad", [["x"], None, "dict", 1])
    def test_audit_must_be_dict(self, bad):
        with pytest.raises(ValueError):
            ApprovalResult(True, "approved", bad)

    def test_valid_result_accepted(self):
        res = ApprovalResult(True, "approved", {"risk_level": TRADING})
        assert res.allowed is True
        assert res.reason_code == "approved"
