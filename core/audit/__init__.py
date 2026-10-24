# -*- coding: utf-8 -*-
"""core.audit —— 决策审计包（第二阶段分片③）。

每笔接受/拒绝都落一条 Decision 快照（JSONL），replay 可完整还原。
"""
from .record import Decision, SignalLikeError, write_decision, decision_to_dict
from .replay import read_decisions, replay_decision, ReplayMismatch

__all__ = [
    "Decision",
    "SignalLikeError",
    "write_decision",
    "decision_to_dict",
    "read_decisions",
    "replay_decision",
    "ReplayMismatch",
]
