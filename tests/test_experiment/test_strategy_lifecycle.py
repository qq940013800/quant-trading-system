# -*- coding: utf-8 -*-
"""tests.test_experiment.test_strategy_lifecycle —— 策略生命周期测试。"""
from __future__ import annotations

import pytest

from core.experiment.strategy_lifecycle import (
    StrategyState,
    StrategyLifecycle,
    LaunchCriteria,
    LaunchGate,
    LIFECYCLE_STAGES,
    WatchThresholds,
    assess_crowding,
    assess_decay,
    recommend_retirement,
    stage_of_state,
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


# ------------------------------------------------------------------
# 八阶段映射
# ------------------------------------------------------------------
class TestLifecycleStages:
    def test_eight_stages_present(self):
        assert len(LIFECYCLE_STAGES) == 8
        assert LIFECYCLE_STAGES == (
            "discovery", "validation", "small_capital", "scale",
            "crowding", "decay", "retired", "post_mortem",
        )

    def test_stage_of_state_mapping(self):
        assert stage_of_state(StrategyState.DRAFT) == "discovery"
        assert stage_of_state(StrategyState.AB_TESTING) == "validation"
        assert stage_of_state(StrategyState.LIVE_SMALL) == "small_capital"
        assert stage_of_state(StrategyState.LIVE_FULL) == "scale"
        assert stage_of_state(StrategyState.MONITORING) == "decay"
        assert stage_of_state(StrategyState.RETIRED) == "retired"


# ------------------------------------------------------------------
# 拥挤 / 衰减 / 退役纯判定
# ------------------------------------------------------------------
HEALTHY_CROWD = {
    "fill_rate": 0.98, "slippage_bps": 2.0,
    "capacity_util": 0.5, "peer_corr": 0.3,
}
HEALTHY_DECAY = {
    "current_sharpe": 1.4, "baseline_sharpe": 1.5,
    "current_win_rate": 0.55, "baseline_win_rate": 0.55,
    "current_expectancy": 0.8, "current_max_drawdown": 0.10,
    "n_trades": 50,
}


class TestAssessCrowding:
    def test_healthy_not_crowded(self):
        report = assess_crowding(HEALTHY_CROWD, WatchThresholds())
        assert not report.crowded
        assert report.reasons == []

    def test_fill_rate_drop_reason(self):
        m = dict(HEALTHY_CROWD, fill_rate=0.70)
        report = assess_crowding(m, WatchThresholds())
        assert report.crowded
        assert "crowd_fill_rate_drop" in report.reasons

    def test_slippage_and_capacity_and_corr_reasons(self):
        m = dict(HEALTHY_CROWD, slippage_bps=9.0, capacity_util=0.95, peer_corr=0.8)
        report = assess_crowding(m, WatchThresholds())
        assert report.crowded
        assert "crowd_slippage_rise" in report.reasons
        assert "crowd_capacity_limit" in report.reasons
        assert "crowd_peer_corr_high" in report.reasons

    def test_thresholds_are_caller_supplied(self):
        # 放宽阈值后，原本拥挤的指标也能通过
        m = dict(HEALTHY_CROWD, fill_rate=0.70)
        loose = WatchThresholds(min_fill_rate=0.60)
        assert not assess_crowding(m, loose).crowded


class TestAssessDecay:
    def test_healthy_not_decayed(self):
        report = assess_decay(HEALTHY_DECAY, WatchThresholds())
        assert not report.decayed
        assert report.reasons == []

    def test_sharpe_and_winrate_decline(self):
        m = dict(HEALTHY_DECAY, current_sharpe=0.5, current_win_rate=0.40)
        report = assess_decay(m, WatchThresholds())
        assert report.decayed
        assert "decay_sharpe_down" in report.reasons
        assert "decay_winrate_down" in report.reasons

    def test_expectancy_and_drawdown_reasons(self):
        m = dict(HEALTHY_DECAY, current_expectancy=-0.2, current_max_drawdown=0.30)
        report = assess_decay(m, WatchThresholds())
        assert "decay_expectancy_down" in report.reasons
        assert "decay_drawdown_excess" in report.reasons

    def test_missing_dimensions_are_skipped(self):
        report = assess_decay({"n_trades": 5}, WatchThresholds())
        assert not report.decayed


class TestRecommendRetirement:
    def test_healthy_keep(self):
        decay = assess_decay(HEALTHY_DECAY, WatchThresholds())
        crowd = assess_crowding(HEALTHY_CROWD, WatchThresholds())
        rec = recommend_retirement(decay, crowd, HEALTHY_DECAY, WatchThresholds())
        assert rec.recommendation == "keep"
        assert rec.reasons == []

    def test_soft_decay_watches(self):
        m = dict(HEALTHY_DECAY, current_sharpe=0.5)
        decay = assess_decay(m, WatchThresholds())
        crowd = assess_crowding(HEALTHY_CROWD, WatchThresholds())
        rec = recommend_retirement(decay, crowd, m, WatchThresholds())
        assert rec.recommendation == "watch"

    def test_drawdown_breach_retires(self):
        m = dict(HEALTHY_DECAY, current_max_drawdown=0.30)
        decay = assess_decay(m, WatchThresholds())
        crowd = assess_crowding(HEALTHY_CROWD, WatchThresholds())
        rec = recommend_retirement(decay, crowd, m, WatchThresholds())
        assert rec.recommendation == "retire"
        assert "retire_breach_risk_limit" in rec.reasons

    def test_structural_break_retires(self):
        m = dict(HEALTHY_DECAY, structural_break=True)
        decay = assess_decay(HEALTHY_DECAY, WatchThresholds())
        crowd = assess_crowding(HEALTHY_CROWD, WatchThresholds())
        rec = recommend_retirement(decay, crowd, m, WatchThresholds())
        assert rec.recommendation == "retire"
        assert "retire_structural_break" in rec.reasons

    def test_capacity_exhausted_retires(self):
        crowd_m = dict(HEALTHY_CROWD, capacity_util=0.95)
        decay = assess_decay(HEALTHY_DECAY, WatchThresholds())
        crowd = assess_crowding(crowd_m, WatchThresholds())
        rec = recommend_retirement(decay, crowd, HEALTHY_DECAY, WatchThresholds())
        assert rec.recommendation == "retire"
        assert "retire_capacity_exhausted" in rec.reasons

    def test_prolonged_decay_retires(self):
        m = dict(HEALTHY_DECAY, current_expectancy=-0.2, n_trades=30)
        decay = assess_decay(m, WatchThresholds())
        crowd = assess_crowding(HEALTHY_CROWD, WatchThresholds())
        rec = recommend_retirement(decay, crowd, m, WatchThresholds())
        assert rec.recommendation == "retire"
        assert "retire_prolonged_decay" in rec.reasons

    def test_voluntary_retire(self):
        m = dict(HEALTHY_DECAY, voluntary_retire=True)
        decay = assess_decay(HEALTHY_DECAY, WatchThresholds())
        crowd = assess_crowding(HEALTHY_CROWD, WatchThresholds())
        rec = recommend_retirement(decay, crowd, m, WatchThresholds())
        assert rec.recommendation == "retire"
        assert "retire_voluntary" in rec.reasons

    def test_insufficient_sample_soft_decay_not_retire(self):
        # 样本不足：期望为负也只 watch，不触发持续衰减退役
        m = dict(HEALTHY_DECAY, current_expectancy=-0.2, n_trades=5)
        decay = assess_decay(m, WatchThresholds())
        crowd = assess_crowding(HEALTHY_CROWD, WatchThresholds())
        rec = recommend_retirement(decay, crowd, m, WatchThresholds())
        assert rec.recommendation == "watch"
        assert "retire_prolonged_decay" not in rec.reasons
