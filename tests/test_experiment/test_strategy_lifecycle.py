# -*- coding: utf-8 -*-
"""tests.test_experiment.test_strategy_lifecycle —— 策略生命周期测试。"""
from __future__ import annotations

import pytest

from core.experiment.strategy_lifecycle import (
    StrategyState,
    StrategyLifecycle,
    LaunchCriteria,
    LaunchGate,
)


# ------------------------------------------------------------------
# 状态转移
# ------------------------------------------------------------------
class TestStrategyLifecycle:
    def test_initial_state_is_draft(self):
        """初始状态应该是draft。"""
        lifecycle = StrategyLifecycle("test_strategy")
        assert lifecycle.current_state == StrategyState.DRAFT

    def test_valid_transition(self):
        """合法状态转移应该成功。"""
        lifecycle = StrategyLifecycle("test_strategy")
        lifecycle.transition_to(StrategyState.BACKTESTING, "完成研究")
        assert lifecycle.current_state == StrategyState.BACKTESTING

    def test_invalid_transition_raises_error(self):
        """非法状态转移应该报错。"""
        lifecycle = StrategyLifecycle("test_strategy")
        # draft 不能直接跳到 live
        with pytest.raises(ValueError):
            lifecycle.transition_to(StrategyState.LIVE_SMALL, "跳过步骤")

    def test_audit_trail_records_all_events(self):
        """审计轨迹应该记录所有事件。"""
        lifecycle = StrategyLifecycle("test_strategy")
        lifecycle.transition_to(StrategyState.BACKTESTING, "完成研究")
        lifecycle.transition_to(StrategyState.AB_TESTING, "回测达标")

        trail = lifecycle.get_audit_trail()
        assert len(trail) == 3  # 初始 + 2次转移

    def test_is_live(self):
        """is_live应该正确判断。"""
        lifecycle = StrategyLifecycle("test_strategy")
        assert not lifecycle.is_live()

        lifecycle.current_state = StrategyState.LIVE_SMALL
        assert lifecycle.is_live()

        lifecycle.current_state = StrategyState.RETIRED
        assert not lifecycle.is_live()


# ------------------------------------------------------------------
# 上线闸门
# ------------------------------------------------------------------
class TestLaunchGate:
    def test_good_strategy_passes_backtest_gate(self):
        """好的策略应该通过回测闸门。"""
        gate = LaunchGate()
        passed, issues = gate.check_backtest_ready(
            sharpe=1.5, max_dd=0.10, n_trades=50
        )
        assert passed
        assert len(issues) == 0

    def test_low_sharpe_fails_gate(self):
        """Sharpe太低应该不通过。"""
        gate = LaunchGate()
        passed, issues = gate.check_backtest_ready(
            sharpe=0.5, max_dd=0.10, n_trades=50
        )
        assert not passed
        assert any("Sharpe" in i for i in issues)

    def test_too_many_drawdown_fails_gate(self):
        """回撤太大应该不通过。"""
        gate = LaunchGate()
        passed, issues = gate.check_backtest_ready(
            sharpe=1.5, max_dd=0.30, n_trades=50
        )
        assert not passed
        assert any("回撤" in i for i in issues)

    def test_ab_test_launch_conclusion_passes(self):
        """AB测试launch结论应该通过。"""
        gate = LaunchGate()
        passed, issues = gate.check_ab_test_passed(
            ab_conclusion="launch",
            overfitting_score=0.1,
        )
        assert passed

    def test_ab_test_continue_conclusion_fails(self):
        """AB测试continue结论应该不通过。"""
        gate = LaunchGate()
        passed, issues = gate.check_ab_test_passed(
            ab_conclusion="continue",
            overfitting_score=0.1,
        )
        assert not passed
