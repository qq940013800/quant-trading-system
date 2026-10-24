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
