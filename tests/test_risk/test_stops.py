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


# ------------------------------------------------------------------
# 边界 / 状态迁移 / 异常路径补充
# ------------------------------------------------------------------
class TestStopsBoundary:
    def test_breakeven_branch_updates_stop(self):
        """R 介于保本线与跟踪激活线之间：走保本分支，返回 BREAKEVEN。"""
        state = StopState(
            entry_price=100.0, direction=+1,
            entry_atr=2.0, entry_dist=2.0,
            current_stop=98.0, bars_held=5, max_favorable_r=1.5,
        )
        config = StopConfig(breakeven_r=1.0, breakeven_offset_r=0.1,
                            trailing_activation_r=2.0)
        should_exit, new_stop, stop_type = evaluate_stops(
            state, config, current_price=101.0,
        )
        assert should_exit is False
        assert stop_type == StopType.BREAKEVEN
        # 审计可区分：保本止损不得被误标为初始 ATR 止损
        assert state.stop_type == StopType.BREAKEVEN
        assert stop_type != StopType.PRICE_ATR
        # 保本价 = entry + 0.1R × entry_dist = 100.2
        assert new_stop == pytest.approx(100.2)
        assert state.current_stop == pytest.approx(100.2)

    def test_evaluate_refreshes_max_favorable_r(self):
        """当前价更有利时，max_favorable_r 被推高（状态迁移可审计）。"""
        state = StopState(
            entry_price=100.0, direction=+1,
            entry_atr=2.0, entry_dist=2.0,
            current_stop=98.0, bars_held=5, max_favorable_r=0.0,
        )
        evaluate_stops(state, StopConfig(), current_price=104.0)
        # (104-100)/2 = 2.0R
        assert state.max_favorable_r == pytest.approx(2.0)

    def test_short_breakeven_stop_sign(self):
        state = StopState(
            entry_price=100.0, direction=-1,
            entry_atr=2.0, entry_dist=2.0,
            current_stop=102.0, max_favorable_r=1.5,
        )
        config = StopConfig(breakeven_r=1.0, breakeven_offset_r=0.1)
        # 空头保本价 = entry - 0.1R × dist = 99.8
        assert update_breakeven_stop(state, config) == pytest.approx(99.8)

    def test_breakeven_triggers_at_exact_boundary(self):
        """R 恰好等于 breakeven_r 即触发（>= 口径）。"""
        state = StopState(
            entry_price=100.0, direction=+1,
            entry_atr=2.0, entry_dist=2.0,
            current_stop=98.0, max_favorable_r=1.0,
        )
        config = StopConfig(breakeven_r=1.0)
        assert update_breakeven_stop(state, config) is not None

    def test_trailing_triggers_at_exact_boundary(self):
        state = StopState(
            entry_price=100.0, direction=+1,
            entry_atr=2.0, entry_dist=2.0,
            current_stop=98.0, max_favorable_r=2.0,
        )
        config = StopConfig(trailing_activation_r=2.0)
        assert update_trailing_stop(state, config) is not None

    def test_compute_r_short_loss_is_negative(self):
        # 空头价格上涨 = 亏损，R 为负
        assert compute_current_r(100.0, -1, 101.0, 2.0) == pytest.approx(-0.5)

    def test_state_current_r_is_not_implemented(self):
        state = StopState(100.0, +1, 2.0, 2.0, 98.0)
        with pytest.raises(NotImplementedError):
            state.current_r()

    def test_update_stop_rejects_invalid_direction(self):
        with pytest.raises(ValueError):
            update_stop(100.0, 99.0, 0)

    def test_widen_error_carries_full_context(self):
        with pytest.raises(StopWideningError) as ei:
            update_stop(100.0, 99.0, +1, symbol="XAUUSD",
                        ts_utc="2021-01-04 09:30:00")
        ctx = ei.value.context
        assert ctx["layer"] == "risk.stops"
        assert ctx["symbol"] == "XAUUSD"
        assert ctx["ts_utc"] == "2021-01-04 09:30:00"
        assert ctx["current_stop"] == 100.0
        assert ctx["new_stop"] == 99.0
        assert "widened" in ctx["detail"]
