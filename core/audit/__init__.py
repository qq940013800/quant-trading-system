# -*- coding: utf-8 -*-
"""core.audit —— 决策审计包（第二阶段分片③）。

每笔接受/拒绝都落一条 Decision 快照（JSONL），replay 可完整还原。
"""
from .record import Decision, SignalLikeError, write_decision, decision_to_dict
from .replay import read_decisions, replay_decision, ReplayMismatch
from .attribution import (
    AttributionResult,
    split_trade_outcome,
    aggregate_attribution,
    AttributionError,
)
from .knowledge_normalize import (
    NormalizedEntry,
    normalize_entry,
    normalize_tags,
    normalize_tag,
)
from .knowledge_match import similarity, find_similar, MatchScore
from .knowledge_filter import (
    FAULT_KIND,
    POST_MORTEM_KIND,
    category_matches,
    filter_by_category,
    filter_by_keyword,
    filter_validated,
    is_validated,
    keyword_hits,
)
from .evolution_rules import (
    ReviewThresholds,
    classify_fault,
    classify_health,
    detect_health_warnings,
    evaluate_review_triggers,
    score_health,
)

__all__ = [
    "Decision",
    "SignalLikeError",
    "write_decision",
    "decision_to_dict",
    "read_decisions",
    "replay_decision",
    "ReplayMismatch",
    "AttributionResult",
    "split_trade_outcome",
    "aggregate_attribution",
    "AttributionError",
    "NormalizedEntry",
    "normalize_entry",
    "normalize_tags",
    "normalize_tag",
    "similarity",
    "find_similar",
    "MatchScore",
    "FAULT_KIND",
    "POST_MORTEM_KIND",
    "category_matches",
    "filter_by_category",
    "filter_by_keyword",
    "filter_validated",
    "is_validated",
    "keyword_hits",
    "ReviewThresholds",
    "classify_fault",
    "classify_health",
    "detect_health_warnings",
    "evaluate_review_triggers",
    "score_health",
]
