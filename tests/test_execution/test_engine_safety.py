# -*- coding: utf-8 -*-
"""tests.test_execution.test_engine_safety —— 执行引擎接入控制面的单测。"""
from __future__ import annotations

import pytest

from core.control.kill_switch import KillSwitch
from core.execution.engine import ExecutionEngine, OrderSide


def _engine(tmp_path) -> tuple[ExecutionEngine, KillSwitch]:
    ks = KillSwitch(tmp_path / "ks.json")
    return ExecutionEngine(kill_switch=ks), ks


def test_armed_kill_switch_blocks_new_position(tmp_path):
    engine, ks = _engine(tmp_path)
    ks.trigger("drawdown limit", "unit-test")
    pos = engine.execute_signal(
        symbol="XAUUSD", side=OrderSide.BUY, signal_strength=0.8,
        equity=100_000.0, atr=2.5,
    )
    assert pos is None
    assert engine.orders == []
    assert engine.positions == {}


def test_unarmed_kill_switch_allows_trade(tmp_path):
    engine, _ = _engine(tmp_path)
    pos = engine.execute_signal(
        symbol="XAUUSD", side=OrderSide.BUY, signal_strength=0.8,
        equity=100_000.0, atr=2.5,
    )
    assert pos is not None
    assert pos.symbol == "XAUUSD"
    assert engine.orders


def test_kill_switch_checked_each_call(tmp_path):
    engine, ks = _engine(tmp_path)
    assert engine.execute_signal(
        symbol="XAUUSD", side=OrderSide.BUY, signal_strength=0.8,
        equity=100_000.0, atr=2.5,
    ) is not None
    ks.trigger("mid-run stop", "unit-test")
    assert engine.execute_signal(
        symbol="XAUUSD", side=OrderSide.BUY, signal_strength=0.8,
        equity=100_000.0, atr=2.5,
    ) is None


def test_engine_reconcile_clean(tmp_path):
    engine, ks = _engine(tmp_path)
    pos = engine.execute_signal(
        symbol="XAUUSD", side=OrderSide.BUY, signal_strength=0.8,
        equity=100_000.0, atr=2.5,
    )
    assert pos is not None
    order = engine.orders[0]
    broker_orders = [{"order_id": order.order_id, "symbol": "XAUUSD",
                      "side": "buy", "quantity": order.quantity,
                      "filled_quantity": order.filled_quantity}]
    broker_positions = [{"symbol": "XAUUSD", "side": "buy",
                         "quantity": pos.quantity}]
    report = engine.reconcile(broker_orders, broker_positions)
    assert report.is_clean
    assert ks.is_armed() is False


def test_engine_reconcile_mismatch_arms_kill_switch(tmp_path):
    engine, ks = _engine(tmp_path)
    engine.execute_signal(
        symbol="XAUUSD", side=OrderSide.BUY, signal_strength=0.8,
        equity=100_000.0, atr=2.5,
    )
    report = engine.reconcile([], [])  # 经纪商侧什么都没有 -> 幽灵单
    assert not report.is_clean
    assert ks.is_armed() is True
    assert "ORDER_MISSING" in ks.state().reason or "reconcile" in ks.state().reason


def test_engine_reconcile_can_skip_enforcement(tmp_path):
    engine, ks = _engine(tmp_path)
    engine.execute_signal(
        symbol="XAUUSD", side=OrderSide.BUY, signal_strength=0.8,
        equity=100_000.0, atr=2.5,
    )
    report = engine.reconcile([], [], enforce_switch=False)
    assert not report.is_clean
    assert ks.is_armed() is False
