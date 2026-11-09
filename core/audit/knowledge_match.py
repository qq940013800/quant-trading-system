# -*- coding: utf-8 -*-
"""core.audit.knowledge_match —— 条目相似度纯函数（无向量库 / 无外部资源）。

第一性原理：
    相似性不一定要靠嵌入向量。在标签口径已归一的前提下，
    标签重合（Jaccard）+ 文本词/字符重合，就能给出可解释、可审计的
    匹配分数；每一分量都能单独复核，不引入黑盒。

口径：
    - 标签分量：标签集合 Jaccard。
    - 文本分量：词元集合 Jaccard 与字符二元组重叠的平均。
    - 综合分 = tag_weight * 标签分量 + (1 - tag_weight) * 文本分量。

纯逻辑约束：不读文件、不连库、不调用向量服务；输入为归一化条目或 dict。
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Sequence, Union

from .knowledge_normalize import (
    NormalizedEntry,
    normalize_entry,
    normalize_tags,
    normalize_text,
)

_LATIN_TOKEN_RE = re.compile(r"[a-z0-9]+")
_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]+")
_TEXT_FIELDS = ("title", "symptom", "root_cause", "solution")


def _ratio(name: str, val: Any, lo: float = 0.0, hi: float = 1.0) -> float:
    if isinstance(val, bool) or not isinstance(val, (int, float)) \
            or not math.isfinite(val):
        raise ValueError(f"{name} 必须为有限数值，收到 {val!r}")
    if not lo <= val <= hi:
        raise ValueError(f"{name} 必须落在 [{lo}, {hi}]，收到 {val!r}")
    return float(val)


def _as_set(tags: Union[Iterable[str], None]) -> set[str]:
    if tags is None:
        return set()
    return set(tags)


def tag_jaccard(tags_a: Iterable[str], tags_b: Iterable[str]) -> float:
    """标签集合 Jaccard；两集合皆空时返回 0.0（不判为相似）。"""
    a = _as_set(tags_a)
    b = _as_set(tags_b)
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _cjk_bigrams(run: str) -> set[str]:
    if len(run) < 2:
        return {run} if run else set()
    return {run[i:i + 2] for i in range(len(run) - 1)}


def text_token_set(text: str) -> set[str]:
    """文本词元集合：拉丁/数字词 + 中文成串 + 中文二元组。"""
    norm = normalize_text(text)
    tokens: set[str] = set(_LATIN_TOKEN_RE.findall(norm))
    for run in _CJK_RUN_RE.findall(norm):
        tokens.add(run)
        tokens |= _cjk_bigrams(run)
    return tokens


def _char_bigrams(text: str) -> set[str]:
    norm = normalize_text(text).replace(" ", "")
    if len(norm) < 2:
        return {norm} if norm else set()
    return {norm[i:i + 2] for i in range(len(norm) - 1)}


def text_jaccard(text_a: str, text_b: str) -> float:
    """词元集合 Jaccard；两边皆空返回 0.0。"""
    a = text_token_set(text_a)
    b = text_token_set(text_b)
    if not a and not b:
        return 0.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def char_overlap(text_a: str, text_b: str) -> float:
    """字符二元组重叠（Jaccard）；两边皆空返回 0.0。"""
    a = _char_bigrams(text_a)
    b = _char_bigrams(text_b)
    if not a and not b:
        return 0.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _entry_tags(entry: Any) -> list[str]:
    if isinstance(entry, NormalizedEntry):
        return list(entry.tags)
    if isinstance(entry, dict):
        return normalize_tags(entry.get("tags"))
    return []


def _entry_text(entry: Any) -> str:
    if isinstance(entry, NormalizedEntry):
        return " ".join(getattr(entry, f) for f in _TEXT_FIELDS)
    if isinstance(entry, dict):
        return " ".join(normalize_text(entry.get(f)) for f in _TEXT_FIELDS)
    return normalize_text(str(entry))


@dataclass(frozen=True)
class MatchScore:
    """两条目的相似度分解（可审计分量）。"""

    score: float
    tag_jaccard: float
    text_jaccard: float
    char_overlap: float
    tag_weight: float
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "tag_jaccard": self.tag_jaccard,
            "text_jaccard": self.text_jaccard,
            "char_overlap": self.char_overlap,
            "tag_weight": self.tag_weight,
            "detail": dict(self.detail),
        }


def similarity(entry_a: Any, entry_b: Any,
               tag_weight: float = 0.5) -> MatchScore:
    """计算两条目的综合相似度。

    Args:
        entry_a: 归一化条目 / dict / 自由文本。
        entry_b: 同上。
        tag_weight: 标签分量权重，∈ [0, 1]；文本分量权重为 1 - tag_weight。

    Returns:
        MatchScore，含各分量与综合分。
    """
    _ratio("tag_weight", tag_weight)

    tags_a, tags_b = _entry_tags(entry_a), _entry_tags(entry_b)
    text_a, text_b = _entry_text(entry_a), _entry_text(entry_b)

    tag_component = tag_jaccard(tags_a, tags_b)
    t_jac = text_jaccard(text_a, text_b)
    c_ov = char_overlap(text_a, text_b)
    text_component = 0.5 * t_jac + 0.5 * c_ov

    score = tag_weight * tag_component + (1.0 - tag_weight) * text_component

    return MatchScore(
        score=score,
        tag_jaccard=tag_component,
        text_jaccard=t_jac,
        char_overlap=c_ov,
        tag_weight=tag_weight,
        detail={
            "tags_a": tags_a,
            "tags_b": tags_b,
        },
    )


def find_similar(query: Any, entries: Sequence[Any],
                 threshold: float = 0.0,
                 tag_weight: float = 0.5) -> list[dict]:
    """在条目列表中检索与 query 最相似的条目，按分数降序。

    Args:
        query: 条目 / dict / 自由文本（str 会先归一化）。
        entries: 候选条目序列。
        threshold: 综合分下限（含）。
        tag_weight: 标签分量权重。

    Returns:
        [{"entry": <原始条目>, "score": float, "match": MatchScore}, ...]
        仅保留 score >= threshold；不做截断 limit，由调用方取用。
    """
    _ratio("threshold", threshold)
    _ratio("tag_weight", tag_weight)

    if isinstance(query, (str, dict)):
        query = normalize_entry(query)

    scored: list[dict] = []
    for entry in entries:
        match = similarity(query, entry, tag_weight=tag_weight)
        if match.score >= threshold:
            scored.append({"entry": entry, "score": match.score, "match": match})

    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored
