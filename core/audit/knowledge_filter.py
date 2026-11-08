# -*- coding: utf-8 -*-
"""core.audit.knowledge_filter —— 检索前/后的确定性过滤纯函数（无 DB/网络/向量库）。

第一性原理：
    相似度再高，未验证的故障、未关闭的复盘也不能进入可复用候选；
    分类必须精确匹配；关键词命中要能定位到具体字段，便于事后审计命中来源。

纯逻辑约束：
    - 不读文件、不连库、不触网、不调用向量服务；
    - 输入为 dict / NormalizedEntry / 自由文本，返回纯数据；
    - 不放宽既有阈值口径，不在本模块反推风控阈值。
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

from .knowledge_normalize import normalize_status, normalize_text

FAULT_KIND = "fault"
POST_MORTEM_KIND = "post_mortem"
_VALID_KINDS = (FAULT_KIND, POST_MORTEM_KIND)

_DEFAULT_KEYWORD_FIELDS = ("title", "symptom", "root_cause", "solution")


def _get(entry: Any, field: str) -> Any:
    if isinstance(entry, dict):
        return entry.get(field)
    return getattr(entry, field, None)


def category_matches(entry: Any, category: Optional[str]) -> bool:
    """分类归一化精确匹配；category 为 None/空字符串时放行（不限制分类）。"""
    if category is None or normalize_text(category) == "":
        return True
    return normalize_text(_get(entry, "category")) == normalize_text(category)


def filter_by_category(entries: Sequence[Any], category: Optional[str]) -> list[Any]:
    """保留分类匹配的条目，顺序保持不变。"""
    return [e for e in entries if category_matches(e, category)]


def is_validated(entry: Any, kind: str) -> bool:
    """条目是否达到可复用门槛。

    - fault：`verified` 为真值才放行；未验证故障默认排除。
    - post_mortem：`status` 归一为 ``closed`` 才放行；未关闭复盘默认排除。

    Raises:
        ValueError: kind 不在已知取值内（带上下文，硬规则 9）。
    """
    if kind not in _VALID_KINDS:
        raise ValueError(f"unknown kind {kind!r}; expected one of {_VALID_KINDS}")
    if kind == FAULT_KIND:
        return bool(_get(entry, "verified"))
    status, _ = normalize_status(_get(entry, "status"))
    return status == "closed"


def filter_validated(entries: Sequence[Any], kind: str) -> list[Any]:
    """仅保留达到可复用门槛的条目，顺序保持不变。"""
    return [e for e in entries if is_validated(e, kind)]


def keyword_hits(entry: Any, keyword: str,
                 fields: Optional[Sequence[str]] = None) -> list[str]:
    """返回归一化后包含关键词子串的字段名列表（保序、去重）。

    Args:
        entry: 候选条目。
        keyword: 搜索关键词；空关键词返回空列表。
        fields: 参与命中的字段；缺省为 title/symptom/root_cause/solution。
    """
    kw = normalize_text(keyword)
    if kw == "":
        return []
    target_fields = tuple(fields) if fields else _DEFAULT_KEYWORD_FIELDS
    hits: list[str] = []
    for field in target_fields:
        if kw in normalize_text(_get(entry, field)):
            if field not in hits:
                hits.append(field)
    return hits


def filter_by_keyword(entries: Sequence[Any], keyword: str,
                      fields: Optional[Sequence[str]] = None) -> list[Any]:
    """保留至少一个指定字段命中关键词的条目，顺序保持不变。"""
    return [e for e in entries if keyword_hits(e, keyword, fields)]
