# -*- coding: utf-8 -*-
"""core.control —— 控制面：独立于策略进程的安全开关。

设计第一性原理（见 docs/knowledge/06_failures_and_lessons.md）：
    失败案例里没有一个是"看错方向"，全部是"错了之后停不下来"。
因此安全开关必须是**跨进程可见、进程崩溃后仍生效、默认失败关闭（fail-closed）**的。

本包当前只包含 KillSwitch；后续 LimitBook / ConfigProvider / DeployGuard 同属控制面。
"""
from __future__ import annotations

from .kill_switch import (
    KillSwitch,
    KillSwitchArmed,
    KillSwitchError,
    KillSwitchState,
)
from .dual_review import DualReviewResult, evaluate_dual_review
from .rollout import (
    RolloutDecision,
    RolloutStage,
    RolloutThresholds,
    evaluate_rollout,
)

__all__ = [
    "KillSwitch",
    "KillSwitchArmed",
    "KillSwitchError",
    "KillSwitchState",
    "DualReviewResult",
    "evaluate_dual_review",
    "RolloutDecision",
    "RolloutStage",
    "RolloutThresholds",
    "evaluate_rollout",
]
