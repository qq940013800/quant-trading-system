# -*- coding: utf-8 -*-
"""tests.test_registry.test_deployment_guard —— 部署校验纯函数单测。"""
from __future__ import annotations

from datetime import datetime

from core.registry import ModelStage, ModelVersion, StrategyStatus, StrategyVersion
from core.registry.deployment_guard import (
    check_model_deployment,
    check_strategy_deployment,
)


def _strategy(status: StrategyStatus) -> StrategyVersion:
    sv = StrategyVersion(
        strategy_id="s1", version="v1.0.0",
        created_at=datetime.now(), parameters={"x": 1},
        status=StrategyStatus.DRAFT,
    )
    sv.freeze_parameters()
    sv.update_status(StrategyStatus.BACKTEST)
    sv.update_status(StrategyStatus.PAPER)
    if status == StrategyStatus.LIVE:
        sv.update_status(StrategyStatus.LIVE)
    elif status == StrategyStatus.PAUSED:
        sv.update_status(StrategyStatus.PAUSED)
    elif status == StrategyStatus.RETIRED:
        sv.update_status(StrategyStatus.RETIRED)
    return sv


def _model(stage: ModelStage, checksum: str = "abc123") -> ModelVersion:
    m = ModelVersion(
        model_id="m1", version="v1", created_at=datetime.now(),
        artifact_checksum=checksum, stage=ModelStage.CANDIDATE,
    )
    m.freeze()
    if stage in (ModelStage.STAGED, ModelStage.PRODUCTION):
        m.transition(ModelStage.STAGED)
    if stage == ModelStage.PRODUCTION:
        m.transition(ModelStage.PRODUCTION)
    return m


# ---------------------------------------------------------------- 策略
def test_strategy_paper_allowed_on_paper():
    res = check_strategy_deployment(_strategy(StrategyStatus.PAPER), "paper")
    assert res.allowed is True
    assert res.reasons == []


def test_strategy_live_allowed_on_live():
    res = check_strategy_deployment(_strategy(StrategyStatus.LIVE), "live")
    assert res.allowed is True


def test_strategy_paper_rejected_on_live():
    res = check_strategy_deployment(_strategy(StrategyStatus.PAPER), "live")
    assert not res.allowed
    assert "status_not_eligible" in res.reasons


def test_strategy_draft_unfrozen_rejected():
    sv = StrategyVersion(
        strategy_id="s1", version="v0.1.0",
        created_at=datetime.now(), parameters={}, status=StrategyStatus.DRAFT,
    )
    res = check_strategy_deployment(sv, "paper")
    assert not res.allowed
    assert "parameters_not_frozen" in res.reasons
    assert "status_not_eligible" in res.reasons


def test_strategy_retired_rejected():
    res = check_strategy_deployment(_strategy(StrategyStatus.RETIRED), "paper")
    assert not res.allowed
    assert "retired" in res.reasons


def test_strategy_paused_rejected():
    res = check_strategy_deployment(_strategy(StrategyStatus.PAUSED), "paper")
    assert not res.allowed
    assert "paused" in res.reasons


def test_strategy_unknown_env_rejected():
    res = check_strategy_deployment(_strategy(StrategyStatus.PAPER), "sandbox")
    assert not res.allowed
    assert "unknown_environment" in res.reasons


# ---------------------------------------------------------------- 模型
def test_model_staged_allowed_on_paper():
    res = check_model_deployment(_model(ModelStage.STAGED), "paper")
    assert res.allowed is True


def test_model_production_allowed_on_live():
    res = check_model_deployment(_model(ModelStage.PRODUCTION), "live")
    assert res.allowed is True


def test_model_candidate_rejected():
    m = ModelVersion(
        model_id="m1", version="v1", created_at=datetime.now(),
        stage=ModelStage.CANDIDATE,
    )
    res = check_model_deployment(m, "paper")
    assert not res.allowed
    assert "stage_not_eligible" in res.reasons
    assert "snapshot_not_frozen" in res.reasons


def test_model_checksum_match_passes():
    res = check_model_deployment(_model(ModelStage.STAGED), "paper", expected_checksum="abc123")
    assert res.allowed is True


def test_model_checksum_mismatch_rejected():
    res = check_model_deployment(
        _model(ModelStage.STAGED, checksum="abc123"), "paper", expected_checksum="deadbeef"
    )
    assert not res.allowed
    assert "checksum_mismatch" in res.reasons


def test_model_no_expected_checksum_skips_check():
    res = check_model_deployment(_model(ModelStage.STAGED, checksum=""), "paper")
    assert res.allowed is True


def test_model_unknown_env_rejected():
    res = check_model_deployment(_model(ModelStage.STAGED), "sandbox")
    assert not res.allowed
    assert "unknown_environment" in res.reasons
