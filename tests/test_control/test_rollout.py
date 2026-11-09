# -*- coding: utf-8 -*-
"""tests.test_control.test_rollout —— 灰度阶段晋升与回滚纯判定单测。"""
from __future__ import annotations

import math
import pytest

from core.control.rollout import (
    RolloutDecision,
    RolloutStage,
    RolloutThresholds,
    evaluate_rollout,
)


def thresholds(**over) -> RolloutThresholds:
    base = dict(min_sharpe=0.6, max_drawdown=0.20, max_cost_deviation=0.25)
    base.update(over)
    return RolloutThresholds(**base)


def test_shadow_qualified_advances_to_small():
    res = evaluate_rollout(stage="shadow", sharpe=0.8, drawdown=0.10,
                           thresholds=thresholds())
    assert res.action == "advance"
    assert res.stage is RolloutStage.SMALL
    assert res.reason_code == "advance_to_small"


def test_small_qualified_advances_to_full():
    res = evaluate_rollout(stage=RolloutStage.SMALL, sharpe=0.9, drawdown=0.12,
                           thresholds=thresholds())
    assert res.action == "advance"
    assert res.stage is RolloutStage.FULL
    assert res.reason_code == "advance_to_full"


def test_full_holds_full():
    res = evaluate_rollout(stage="full", sharpe=1.0, drawdown=0.10,
                           thresholds=thresholds())
    assert res.action == "hold"
    assert res.stage is RolloutStage.FULL
    assert res.reason_code == "hold_full"


def test_drawdown_excess_rolls_back():
    res = evaluate_rollout(stage="small", sharpe=0.9, drawdown=0.30,
                           thresholds=thresholds())
    assert res.action == "rollback"
    assert res.stage is RolloutStage.ROLLBACK
    assert res.reason_code == "rollback_drawdown_excess"


def test_sharpe_below_rolls_back():
    res = evaluate_rollout(stage="small", sharpe=0.3, drawdown=0.10,
                           thresholds=thresholds())
    assert res.action == "rollback"
    assert res.reason_code == "rollback_sharpe_below"


def test_cost_deviation_excess_rolls_back():
    res = evaluate_rollout(stage="small", sharpe=0.9, drawdown=0.10,
                           cost_deviation=0.40, thresholds=thresholds())
    assert res.action == "rollback"
    assert res.reason_code == "rollback_cost_excess"


def test_cost_deviation_within_limit_no_cost_rollback():
    res = evaluate_rollout(stage="small", sharpe=0.9, drawdown=0.10,
                           cost_deviation=0.10, thresholds=thresholds())
    assert res.action == "advance"
    assert res.reason_code == "advance_to_full"


def test_cost_deviation_disabled_when_none():
    res = evaluate_rollout(stage="small", sharpe=0.9, drawdown=0.10,
                           cost_deviation=None,
                           thresholds=thresholds(max_cost_deviation=None))
    assert res.action == "advance"


def test_negative_drawdown_abs_treated():
    res = evaluate_rollout(stage="small", sharpe=0.9, drawdown=-0.10,
                           thresholds=thresholds())
    assert res.action == "advance"
    assert res.audit["drawdown"] == pytest.approx(0.10)


def test_invalid_stage_rejected():
    with pytest.raises(ValueError):
        evaluate_rollout(stage="unknown", sharpe=0.8, drawdown=0.10,
                         thresholds=thresholds())


@pytest.mark.parametrize("bad_sharpe", [math.nan, math.inf, -math.inf, "0.8", True])
def test_invalid_sharpe_rejected(bad_sharpe):
    with pytest.raises(ValueError):
        evaluate_rollout(stage="shadow", sharpe=bad_sharpe, drawdown=0.10,
                         thresholds=thresholds())


@pytest.mark.parametrize("bad_dd", [math.nan, math.inf, "0.1", True])
def test_invalid_drawdown_rejected(bad_dd):
    with pytest.raises(ValueError):
        evaluate_rollout(stage="shadow", sharpe=0.8, drawdown=bad_dd,
                         thresholds=thresholds())


def test_thresholds_negative_drawdown_rejected():
    with pytest.raises(ValueError):
        thresholds(max_drawdown=-0.1)


def test_audit_carries_snapshot_and_thresholds():
    res = evaluate_rollout(stage="shadow", sharpe=0.7, drawdown=0.08,
                           cost_deviation=0.12, thresholds=thresholds())
    assert isinstance(res, RolloutDecision)
    assert res.audit["sharpe"] == pytest.approx(0.7)
    assert res.audit["thresholds"]["min_sharpe"] == 0.6
    assert res.audit["cost_deviation"] == pytest.approx(0.12)
