# -*- coding: utf-8 -*-
"""core.registry.deployment_guard —— 注册中心版本上线前部署校验纯函数。

第一性原理：
    进入交易链路的版本必须满足：状态允许、参数/快照已冻结、未退役/暂停、
    制品校验和一致。校验只读取注册快照，不连库、不触网、不改状态；不满足
    条件时 fail-closed（拒绝上线并留痕原因码）。

环境口径：
    - ``paper``：模拟 / demo 环境，允许 PAPER（策略）/ STAGED（模型）及以上在线态；
    - ``live``：实盘环境，仅允许 LIVE（策略）/ PRODUCTION（模型）。
    未知环境一律拒绝上线。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from core.registry.model_registry import ModelStage, ModelVersion
from core.registry.strategy_registry import StrategyStatus, StrategyVersion

_STRATEGY_ENV_ALLOWED = {
    "paper": {StrategyStatus.PAPER, StrategyStatus.LIVE},
    "live": {StrategyStatus.LIVE},
}

_MODEL_ENV_ALLOWED = {
    "paper": {ModelStage.STAGED, ModelStage.PRODUCTION},
    "live": {ModelStage.PRODUCTION},
}


@dataclass(frozen=True)
class DeploymentResult:
    """部署校验结果（纯结果，含审计快照）。"""

    allowed: bool
    reasons: list[str]
    audit: dict[str, Any]


def check_strategy_deployment(
    version: StrategyVersion,
    target_env: str,
) -> DeploymentResult:
    """校验策略版本是否可部署到目标环境。

    只读 ``StrategyVersion`` 快照；原因码稳定，便于审计与前端留痕。
    """
    env = str(target_env or "").strip().lower()
    reasons: list[str] = []

    if env not in _STRATEGY_ENV_ALLOWED:
        reasons.append("unknown_environment")
    if version.status == StrategyStatus.RETIRED:
        reasons.append("retired")
    if version.status == StrategyStatus.PAUSED:
        reasons.append("paused")
    if env in _STRATEGY_ENV_ALLOWED and version.status not in _STRATEGY_ENV_ALLOWED[env]:
        reasons.append("status_not_eligible")
    if not version.is_frozen():
        reasons.append("parameters_not_frozen")

    audit = {
        "strategy_id": version.strategy_id,
        "version": version.version,
        "status": version.status.value,
        "frozen": version.is_frozen(),
        "env": env,
    }
    return DeploymentResult(allowed=not reasons, reasons=reasons, audit=audit)


def check_model_deployment(
    version: ModelVersion,
    target_env: str,
    expected_checksum: Optional[str] = None,
) -> DeploymentResult:
    """校验模型版本是否可部署到目标环境；可选校验制品校验和。"""
    env = str(target_env or "").strip().lower()
    reasons: list[str] = []

    if env not in _MODEL_ENV_ALLOWED:
        reasons.append("unknown_environment")
    if version.stage == ModelStage.RETIRED:
        reasons.append("retired")
    if env in _MODEL_ENV_ALLOWED and version.stage not in _MODEL_ENV_ALLOWED[env]:
        reasons.append("stage_not_eligible")
    if not version.is_frozen():
        reasons.append("snapshot_not_frozen")

    if expected_checksum:
        actual = (version.artifact_checksum or "").strip()
        if not actual or actual != str(expected_checksum).strip():
            reasons.append("checksum_mismatch")

    audit = {
        "model_id": version.model_id,
        "version": version.version,
        "stage": version.stage.value,
        "frozen": version.is_frozen(),
        "env": env,
    }
    return DeploymentResult(allowed=not reasons, reasons=reasons, audit=audit)
