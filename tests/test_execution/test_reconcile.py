# -*- coding: utf-8 -*-
"""tests.test_execution.test_reconcile —— 订单/持仓对账单测。"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from core.control.kill_switch import KillSwitch
from core.execution.engine import Order, OrderSide, OrderStatus
from core.execution.reconcile import (
    OrderView,
    PositionView,
    Tolerance,
    enforce,
    normalize_side,
    reconcile,
)


@dataclass
class _BTPosition:
    """模拟 core.backtest.engine.Position（direction 为 ±1）。"""
    symbol: str
    direction: int
    entry_price: float
    lots: float


def _order(oid: str, side: OrderSide, qty: float, filled: float = 0.0) -> Order:
    return Order(order_id=oid, symbol="XAUUSD", side=side,
                 order_type=None, quantity=qty, filled_quantity=filled)  # type: ignore[arg-type]


def test_clean_reconcile():
    local_orders = [_order("o1", OrderSide.BUY, 1.0, 1.0)]
    broker_orders = [{"order_id": "o1", "symbol": "XAUUSD", "side": "buy",
                      "quantity": 1.0, "filled_quantity": 1.0, "status": "filled"}]
    local_pos = {"XAUUSD": {"symbol": "XAUUSD", "side": "buy", "quantity": 1.0}}
    broker_pos = [{"symbol": "XAUUSD", "side": "buy", "quantity": 1.0}]
    report = reconcile(local_orders, local_pos, broker_orders, broker_pos)
    assert report.is_clean
    assert report.critical_codes() == []
    assert report.to_dict()["is_clean"] is True


def test_missing_and_unknown_orders():
    local = [_order("o1", OrderSide.BUY, 1.0), _order("o2", OrderSide.SELL, 0.5)]
    broker = [{"order_id": "o2", "side": "sell", "quantity": 0.5},
              {"order_id": "o3", "side": "buy", "quantity": 2.0}]
    report = reconcile(local, {}, broker, {})
    assert report.missing_orders == ["o1"]
    assert report.unknown_orders == ["o3"]
    assert "ORDER_MISSING" in report.critical_codes()
    assert "ORDER_UNKNOWN" in report.critical_codes()


def test_quantity_mismatch_and_tolerance():
    local = [_order("o1", OrderSide.BUY, 1.0, 1.0)]
    within = [{"order_id": "o1", "side": "buy", "quantity": 1.0, "filled_quantity": 1.0000001}]
    assert reconcile(local, {}, within, {}).is_clean

    outside = [{"order_id": "o1", "side": "buy", "quantity": 1.01, "filled_quantity": 1.0}]
    report = reconcile(local, {}, outside, {})
    assert not report.is_clean
    fields = {(m["order_id"], m["field"]) for m in report.order_mismatches}
    assert ("o1", "quantity") in fields


def test_side_mismatch():
    local = [_order("o1", OrderSide.BUY, 1.0)]
    broker = [{"order_id": "o1", "side": "sell", "quantity": 1.0}]
    report = reconcile(local, {}, broker, {})
    assert report.order_mismatches[0]["field"] == "side"


def test_duplicate_ids_flagged():
    local = [_order("dup", OrderSide.BUY, 1.0), _order("dup", OrderSide.BUY, 1.0)]
    broker = [{"order_id": "dup", "side": "buy", "quantity": 1.0},
              {"order_id": "dup", "side": "buy", "quantity": 1.0}]
    report = reconcile(local, {}, broker, {})
    assert report.duplicate_local_orders == ["dup"]
    assert report.duplicate_broker_orders == ["dup"]
    assert "ORDER_DUPLICATE_LOCAL" in report.critical_codes()


def test_position_mismatches_from_backtest_positions():
    local_positions = [_BTPosition("XAUUSD", +1, 2600.0, 1.0)]
    broker_positions = [
        {"symbol": "XAUUSD", "side": "buy", "quantity": 0.5},
        {"symbol": "EURUSD", "side": "sell", "quantity": 2.0},
    ]
    report = reconcile([], local_positions, [], broker_positions)
    assert report.missing_positions == []
    assert report.unknown_positions == ["EURUSD"]
    fields = {(m["symbol"], m["field"]) for m in report.position_mismatches}
    assert ("XAUUSD", "quantity") in fields


def test_missing_position_is_critical():
    local_positions = [{"symbol": "XAUUSD", "side": "buy", "quantity": 1.0}]
    report = reconcile([], local_positions, [], [])
    assert report.missing_positions == ["XAUUSD"]
    assert "POSITION_MISSING" in report.critical_codes()


def test_empty_inputs_are_clean():
    assert reconcile(None, None, None, None).is_clean


def test_normalize_side_variants():
    assert normalize_side(OrderSide.BUY) == "buy"
    assert normalize_side(-1) == "sell"
    assert normalize_side("LONG") == "buy"
    assert normalize_side("short") == "sell"


def test_enforce_triggers_kill_switch_on_mismatch(tmp_path):
    ks = KillSwitch(tmp_path / "ks.json")
    dirty = reconcile([_order("o1", OrderSide.BUY, 1.0)], {}, [], {})
    enforce(dirty, ks, source="unit-test")
    assert ks.is_armed() is True
    assert "reconcile" in ks.state().reason


def test_enforce_does_not_trigger_when_clean(tmp_path):
    ks = KillSwitch(tmp_path / "ks.json")
    clean = reconcile([], {}, [], {})
    enforce(clean, ks)
    assert ks.is_armed() is False


def test_tolerance_validation():
    tol = Tolerance(qty_abs=1e-3, qty_rel=0.0)
    assert tol.equals(1.0, 1.0005)
    assert not tol.equals(1.0, 1.01)
