# -*- coding: utf-8 -*-
"""tests.test_execution.test_spot_ownership —— 现货两层口径与平仓封顶单测。"""
from __future__ import annotations

import pytest

from core.execution.spot_ownership import (
    resolve_spot_close,
    resolve_spot_ownership,
)


def test_free_exceeds_tracked_marks_unmanaged_stock():
    snap = resolve_spot_ownership(tracked_net=1.0, wallet_total=1.5, wallet_free=1.5)
    assert snap.unmanaged_stock == pytest.approx(0.5)
    assert snap.shortfall == 0.0
    assert snap.ownership_cap == 1.0
    assert snap.physical_cap == pytest.approx(1.5)
    assert snap.free_known is True


def test_free_below_tracked_marks_shortfall():
    snap = resolve_spot_ownership(tracked_net=1.0, wallet_total=0.8, wallet_free=0.8)
    assert snap.shortfall == pytest.approx(0.2)
    assert snap.unmanaged_stock == 0.0


def test_free_unknown_is_fail_closed_and_not_inferred():
    snap = resolve_spot_ownership(tracked_net=1.0, wallet_total=1.0, wallet_free=None)
    assert snap.free_known is False
    assert snap.wallet_free is None
    assert snap.physical_cap is None
    assert snap.unmanaged_stock == 0.0
    assert snap.shortfall == 0.0


def test_total_including_locked_does_not_affect_free():
    snap = resolve_spot_ownership(tracked_net=1.0, wallet_total=2.0, wallet_free=1.2)
    assert snap.wallet_total == 2.0
    assert snap.wallet_free == pytest.approx(1.2)


def test_tracked_close_capped_by_ownership():
    snap = resolve_spot_ownership(tracked_net=1.0, wallet_total=1.2, wallet_free=1.2)
    dec = resolve_spot_close(snap, requested=2.0, intent="tracked")
    assert dec.allowed is True
    assert dec.final_qty == pytest.approx(1.0)
    assert dec.capped_by == "ownership"


def test_tracked_close_capped_by_physical_when_free_below_tracked():
    snap = resolve_spot_ownership(tracked_net=1.0, wallet_total=0.8, wallet_free=0.8)
    dec = resolve_spot_close(snap, requested=2.0, intent="tracked")
    assert dec.allowed is True
    assert dec.final_qty == pytest.approx(0.8)
    assert dec.capped_by == "physical"


def test_full_close_uses_physical_cap_and_flags_unmanaged():
    snap = resolve_spot_ownership(tracked_net=1.0, wallet_total=1.5, wallet_free=1.5)
    dec = resolve_spot_close(snap, requested=2.0, intent="full")
    assert dec.allowed is True
    assert dec.final_qty == pytest.approx(1.5)
    assert dec.capped_by == "physical"
    assert dec.audit["includes_unmanaged_stock"] is True


def test_lot_step_floors_downward():
    snap = resolve_spot_ownership(1.0, 1.0, 1.0)
    dec = resolve_spot_close(snap, 0.123456, intent="tracked", lot_step=0.01)
    assert dec.final_qty == pytest.approx(0.12)


def test_nonpositive_request_rejected():
    snap = resolve_spot_ownership(1.0, 1.0, 1.0)
    for bad in (0.0, -0.5, None, "x"):
        dec = resolve_spot_close(snap, bad, intent="tracked")
        assert dec.allowed is False
        assert dec.reason_code == "rejected_nonpositive"
        assert dec.final_qty == 0.0


def test_free_unknown_close_is_fail_closed():
    snap = resolve_spot_ownership(1.0, 1.0, None)
    dec = resolve_spot_close(snap, 1.0, intent="tracked")
    assert dec.allowed is False
    assert dec.reason_code == "rejected_free_unknown"
    assert dec.final_qty == 0.0


def test_invalid_ratio_falls_back_to_default():
    snap = resolve_spot_ownership(1.0, 1.0, 1.0, safety_ratio=2.0)
    assert snap.physical_cap == pytest.approx(1.0)
    snap2 = resolve_spot_ownership(1.0, 1.0, 1.0, safety_ratio=-0.1)
    assert snap2.physical_cap == pytest.approx(1.0)


def test_safety_ratio_applies_to_physical_cap():
    snap = resolve_spot_ownership(1.0, 1.0, 1.0, safety_ratio=0.95)
    assert snap.physical_cap == pytest.approx(0.95)


def test_invalid_inputs_clamp_to_zero():
    snap = resolve_spot_ownership("bad", None, "n/a")
    assert snap.tracked_net == 0.0
    assert snap.wallet_total == 0.0
    assert snap.wallet_free == 0.0
