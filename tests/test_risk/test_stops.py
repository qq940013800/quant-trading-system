# -*- coding: utf-8 -*-
"""tests.test_risk.test_stops —— 四级止损体系测试。"""
from __future__ import annotations

import pytest

from core.risk.stops import (
    StopWideningError,
    StopType,
    StopConfig,
    StopState,
    compute_current_r,
    initial_stop,
    update_stop,
    check_time_stop,
    check_signal_stop,
    update_breakeven_stop,
    update_trailing_stop,
    evaluate_stops,
)


# ------------------------------------------------------------------
# 基础功能测试（原有）
# ------------------------------------------------------------------
class TestInitialStop:
    def test_long_stop(self):
        stop = initial_stop(100.0, +1, 2.0)
        assert stop == 98.0

    def test_short_stop(self):
        stop = initial_stop(100.0, -1, 2.0)
        assert stop == 102.0

    def test_invalid_dist(self):
        with pytest.raises(ValueError):
            initial_stop(100.0, +1, 0)

    def test_invalid_direction(self):
        with pytest.raises(ValueError):
            initial_stop(100.0, 0, 2.0)


class TestUpdateStop:
    def test_long_stop_can_move_up(self):
        new = update_stop(98.0, 99.0, +1)
        assert new == 99.0

    def test_long_stop_cannot_move_down(self):
        with pytest.raises(StopWideningError):
            update_stop(98.0, 97.0, +1)

    def test_short_stop_can_move_down(self):
        new = update_stop(102.0, 101.0, -1)
        assert new == 101.0

    def test_short_stop_cannot_move_up(self):
        with pytest.raises(StopWideningError):
            update_stop(102.0, 103.0, -1)


# ------------------------------------------------------------------
# 四级止损测试
# ------------------------------------------------------------------
class TestComputeR:
    def test_long_profit_r(self):
        r = compute_current_r(100.0, +1, 102.0, 2.0)
        assert r == pytest.approx(1.0)

    def test_long_loss_r(self):
        r = compute_current_r(100.0, +1, 99.0, 2.0)
        assert r == pytest.approx(-0.5)

    def test_short_profit_r(self):
        r = compute_current_r(100.0, -1, 98.0, 2.0)
        assert r == pytest.approx(1.0)


class TestTimeStop:
    def test_time_stop_triggers(self):
        state = StopState(
            entry_price=100.0, direction=+1,
            entry_atr=2.0, entry_dist=2.0,
            current_stop=98.0, bars_held=25, max_favorable_r=0.5,
        )
        config = StopConfig(max_holding_bars=20)
        assert check_time_stop(state, config) is True

    def test_time_stop_no_trigger_below_bars(self):
        state = StopState(
            entry_price=100.0, direction=+1,
            entry_atr=2.0, entry_dist=2.0,
            current_stop=98.0, bars_held=10, max_favorable_r=0.5,
        )
        config = StopConfig(max_holding_bars=20)
        assert check_time_stop(state, config) is False

    def test_time_stop_no_trigger_above_r(self):
        state = StopState(
            entry_price=100.0, direction=+1,
            entry_atr=2.0, entry_dist=2.0,
            current_stop=98.0, bars_held=25, max_favorable_r=1.5,
        )
        config = StopConfig(max_holding_bars=20, breakeven_r=1.0)
        # 已经赚了 1.5R，时间止损不触发（因为有盈利）
        assert check_time_stop(state, config) is False


class TestSignalStop:
    def test_signal_stop_triggers(self):
        assert check_signal_stop(+1, signal_reversed=True) is True

    def test_signal_stop_no_trigger(self):
        assert check_signal_stop(+1, signal_reversed=False) is False


class TestBreakevenStop:
    def test_breakeven_triggers(self):
        state = StopState(
            entry_price=100.0, direction=+1,
            entry_atr=2.0, entry_dist=2.0,
            current_stop=98.0, max_favorable_r=1.5,
        )
        config = StopConfig(breakeven_r=1.0, breakeven_offset_r=0.1)
        new_stop = update_breakeven_stop(state, config)
        assert new_stop is not None
        # entry + 0.1R = 100 + 0.1 × 2 = 100.2
        assert new_stop == pytest.approx(100.2)

    def test_breakeven_not_triggered(self):
        state = StopState(
            entry_price=100.0, direction=+1,
            entry_atr=2.0, entry_dist=2.0,
            current_stop=98.0, max_favorable_r=0.5,
        )
        config = StopConfig(breakeven_r=1.0)
        assert update_breakeven_stop(state, config) is None


class TestTrailingStop:
    def test_trailing_triggers_long(self):
        state = StopState(
            entry_price=100.0, direction=+1,
            entry_atr=2.0, entry_dist=2.0,
            current_stop=100.2, max_favorable_r=2.5,  # 最高到 105
        )
        config = StopConfig(trailing_activation_r=2.0, trailing_offset_r=1.0)
        new_stop = update_trailing_stop(state, config)
        assert new_stop is not None
        # entry + (2.5 - 1.0) × 2 = 100 + 3 = 103
        assert new_stop == pytest.approx(103.0)

    def test_trailing_triggers_short(self):
        state = StopState(
            entry_price=100.0, direction=-1,
            entry_atr=2.0, entry_dist=2.0,
            current_stop=99.8, max_favorable_r=3.0,  # 最低到 94
        )
        config = StopConfig(trailing_activation_r=2.0, trailing_offset_r=1.0)
        new_stop = update_trailing_stop(state, config)
        assert new_stop is not None
        # entry - (3.0 - 1.0) × 2 = 100 - 4 = 96
        assert new_stop == pytest.approx(96.0)

    def test_trailing_not_triggered(self):
        state = StopState(
            entry_price=100.0, direction=+1,
            entry_atr=2.0, entry_dist=2.0,
            current_stop=98.0, max_favorable_r=1.0,
        )
        config = StopConfig(trailing_activation_r=2.0)
        assert update_trailing_stop(state, config) is None


# ------------------------------------------------------------------
# 综合评估测试
# ------------------------------------------------------------------
class TestEvaluateStops:
    def test_signal_stop_priority(self):
        """信号止损优先级最高。"""
        state = StopState(
            entry_price=100.0, direction=+1,
            entry_atr=2.0, entry_dist=2.0,
            current_stop=98.0, bars_held=5, max_favorable_r=0.5,
        )
        config = StopConfig()
        should_exit, new_stop, stop_type = evaluate_stops(
            state, config, current_price=101.0, signal_reversed=True
        )
        assert should_exit is True
        assert stop_type == StopType.SIGNAL

    def test_time_stop_priority(self):
        """时间止损优先级高于跟踪止损。"""
        state = StopState(
            entry_price=100.0, direction=+1,
            entry_atr=2.0, entry_dist=2.0,
            current_stop=98.0, bars_held=25, max_favorable_r=0.5,
        )
        config = StopConfig(max_holding_bars=20, breakeven_r=1.0)
        should_exit, new_stop, stop_type = evaluate_stops(
            state, config, current_price=100.5, signal_reversed=False
        )
        assert should_exit is True
        assert stop_type == StopType.TIME

    def test_trailing_stop_updates(self):
        """达到跟踪条件，更新止损。"""
        state = StopState(
            entry_price=100.0, direction=+1,
            entry_atr=2.0, entry_dist=2.0,
            current_stop=100.2, bars_held=10, max_favorable_r=2.5,
        )
        config = StopConfig(trailing_activation_r=2.0, trailing_offset_r=1.0)
        should_exit, new_stop, stop_type = evaluate_stops(
            state, config, current_price=105.0, signal_reversed=False
        )
        assert should_exit is False
        assert new_stop is not None
        assert stop_type == StopType.TRAILING

    def test_no_stop_update(self):
        """没达到任何条件，保持原样。"""
        state = StopState(
            entry_price=100.0, direction=+1,
            entry_atr=2.0, entry_dist=2.0,
            current_stop=98.0, bars_held=5, max_favorable_r=0.5,
        )
        config = StopConfig()
        should_exit, new_stop, stop_type = evaluate_stops(
            state, config, current_price=101.0, signal_reversed=False
        )
        assert should_exit is False
        assert new_stop is None
        assert stop_type == StopType.PRICE_ATR
