# -*- coding: utf-8 -*-
"""tests.test_execution.test_engine —— 执行引擎测试。"""
from __future__ import annotations

import pytest

from core.execution.engine import (
    ExecutionEngine,
    ExecutionConfig,
    OrderSide,
    OrderType,
    OrderStatus,
)


# ------------------------------------------------------------------
# 信号执行
# ------------------------------------------------------------------
class TestExecuteSignal:
    def test_buy_signal_creates_position(self):
        """买入信号应该创建持仓。"""
        engine = ExecutionEngine()
        pos = engine.execute_signal(
            symbol="XAUUSD",
            side=OrderSide.BUY,
            signal_strength=0.8,
            equity=100000,
            atr=2.5,
        )
        assert pos is not None
        assert pos.side == OrderSide.BUY
        assert pos.quantity > 0

    def test_weak_signal_ignored(self):
        """弱信号应该被忽略。"""
        engine = ExecutionEngine()
        pos = engine.execute_signal(
            symbol="XAUUSD",
            side=OrderSide.BUY,
            signal_strength=0.1,  # 太弱
            equity=100000,
            atr=2.5,
        )
        assert pos is None

    def test_position_has_stop_loss(self):
        """持仓应该有止损。"""
        engine = ExecutionEngine()
        pos = engine.execute_signal(
            symbol="XAUUSD",
            side=OrderSide.BUY,
            signal_strength=0.8,
            equity=100000,
            atr=2.5,
        )
        assert pos.stop_loss < pos.entry_price  # 多头止损在入场价下方


# ------------------------------------------------------------------
# 止损单调不变量
# ------------------------------------------------------------------
class TestStopLossMonotonic:
    def test_buy_stop_can_move_up(self):
        """多头止损应该可以上移。"""
        engine = ExecutionEngine()
        pos = engine.execute_signal(
            symbol="XAUUSD",
            side=OrderSide.BUY,
            signal_strength=0.8,
            equity=100000,
            atr=2.5,
        )
        # 止损上移（向盈利方向）应该成功
        new_stop = pos.stop_loss + 1.0
        assert engine.update_stop_loss("XAUUSD", new_stop) is True

    def test_buy_stop_cannot_move_down(self):
        """多头止损不应该可以下移。"""
        engine = ExecutionEngine()
        pos = engine.execute_signal(
            symbol="XAUUSD",
            side=OrderSide.BUY,
            signal_strength=0.8,
            equity=100000,
            atr=2.5,
        )
        # 止损下移（向亏损方向）应该失败
        new_stop = pos.stop_loss - 1.0
        assert engine.update_stop_loss("XAUUSD", new_stop) is False


# ------------------------------------------------------------------
# 平仓
# ------------------------------------------------------------------
class TestClosePosition:
    def test_close_position_removes_it(self):
        """平仓应该移除持仓。"""
        engine = ExecutionEngine()
        engine.execute_signal(
            symbol="XAUUSD",
            side=OrderSide.BUY,
            signal_strength=0.8,
            equity=100000,
            atr=2.5,
        )
        assert len(engine.get_open_positions()) == 1

        order = engine.close_position("XAUUSD")
        assert order is not None
        assert len(engine.get_open_positions()) == 0


# ------------------------------------------------------------------
# 边界 / 异常路径补充
# ------------------------------------------------------------------
class TestEngineBoundary:
    def test_sell_position_stop_above_entry(self):
        engine = ExecutionEngine()
        pos = engine.execute_signal(
            symbol="XAUUSD", side=OrderSide.SELL, signal_strength=0.8,
            equity=100_000, atr=2.5,
        )
        assert pos is not None
        assert pos.side == OrderSide.SELL
        # 空头止损在入场价上方
        assert pos.stop_loss > pos.entry_price

    def test_risk_check_rejection_leaves_no_position(self):
        engine = ExecutionEngine(
            risk_check_fn=lambda s, side, q, p: (False, "risk deny"))
        pos = engine.execute_signal(
            symbol="XAUUSD", side=OrderSide.BUY, signal_strength=0.8,
            equity=100_000, atr=2.5,
        )
        assert pos is None
        assert engine.positions == {}

    def test_order_rejected_leaves_no_position(self):
        def reject(order):
            order.status = OrderStatus.REJECTED
            order.error_message = "no liquidity"
            return order

        engine = ExecutionEngine(order_fn=reject)
        pos = engine.execute_signal(
            symbol="XAUUSD", side=OrderSide.BUY, signal_strength=0.8,
            equity=100_000, atr=2.5,
        )
        assert pos is None
        assert engine.orders[0].status == OrderStatus.REJECTED
        assert engine.orders[0].error_message == "no liquidity"

    def test_order_exception_retries_then_succeeds(self):
        calls = {"n": 0}

        def flaky(order):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("network down")
            order.status = OrderStatus.FILLED
            order.filled_quantity = order.quantity
            order.avg_fill_price = 2000.0
            return order

        engine = ExecutionEngine(order_fn=flaky)
        pos = engine.execute_signal(
            symbol="XAUUSD", side=OrderSide.BUY, signal_strength=0.8,
            equity=100_000, atr=2.5,
        )
        assert pos is not None
        assert calls["n"] == 2  # 首次异常后重试一次成功

    def test_sell_stop_can_only_move_down(self):
        engine = ExecutionEngine()
        pos = engine.execute_signal(
            symbol="XAUUSD", side=OrderSide.SELL, signal_strength=0.8,
            equity=100_000, atr=2.5,
        )
        # 空头止损下移（盈利方向）允许
        assert engine.update_stop_loss("XAUUSD", pos.stop_loss - 1.0) is True
        # 空头止损上移（放宽风险）拒绝
        assert engine.update_stop_loss("XAUUSD", pos.stop_loss + 1.0) is False

    def test_update_stop_missing_symbol_returns_false(self):
        engine = ExecutionEngine()
        assert engine.update_stop_loss("EURUSD", 1.0) is False

    def test_close_missing_position_returns_none(self):
        engine = ExecutionEngine()
        assert engine.close_position("EURUSD") is None

    def test_signal_strength_boundary_03_passes(self):
        """signal_strength 恰好 0.3 达到过滤下限，允许继续。"""
        engine = ExecutionEngine()
        pos = engine.execute_signal(
            symbol="XAUUSD", side=OrderSide.BUY, signal_strength=0.3,
            equity=100_000, atr=2.5,
        )
        assert pos is not None
