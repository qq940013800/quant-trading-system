# -*- coding: utf-8 -*-
"""core.experiment —— 实验管理、AB 测试与策略生命周期。"""
from .retirement_arbitration import (
    RetirementArbitration,
    arbitrate_retirement,
    DECISION_KEEP,
    DECISION_WATCH,
    DECISION_RETIRE,
    RETIRE_LOW_HEALTH,
    WATCH_LOW_HEALTH,
)

__all__ = [
    "RetirementArbitration",
    "arbitrate_retirement",
    "DECISION_KEEP",
    "DECISION_WATCH",
    "DECISION_RETIRE",
    "RETIRE_LOW_HEALTH",
    "WATCH_LOW_HEALTH",
]
