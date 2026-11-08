# -*- coding: utf-8 -*-
"""tests.test_audit.test_knowledge_filter —— 检索过滤纯函数测试。"""
from __future__ import annotations

import pytest

from core.audit.knowledge_filter import (
    FAULT_KIND,
    POST_MORTEM_KIND,
    category_matches,
    filter_by_category,
    filter_by_keyword,
    filter_validated,
    is_validated,
    keyword_hits,
)
from core.audit.knowledge_normalize import NormalizedEntry


class TestCategoryMatch:
    def test_empty_category_passes_all(self):
        entry = {"category": "timeout"}
        assert category_matches(entry, None) is True
        assert category_matches(entry, "") is True

    def test_exact_match_after_normalization(self):
        entry = {"category": "  Timeout "}
        assert category_matches(entry, "timeout") is True
        assert category_matches(entry, "TIMEOUT") is True

    def test_mismatch_excluded(self):
        entry = {"category": "connection"}
        assert category_matches(entry, "timeout") is False

    def test_filter_preserves_order(self):
        entries = [{"category": "a"}, {"category": "b"}, {"category": "a"}]
        kept = filter_by_category(entries, "a")
        assert kept == [entries[0], entries[2]]


class TestValidatedFault:
    def test_verified_true_passes(self):
        assert is_validated({"verified": True}, FAULT_KIND) is True

    def test_unverified_excluded(self):
        assert is_validated({"verified": False}, FAULT_KIND) is False
        assert is_validated({"verified": None}, FAULT_KIND) is False

    def test_filter_validated_faults(self):
        entries = [{"verified": True}, {"verified": False}, {"verified": True}]
        kept = filter_validated(entries, FAULT_KIND)
        assert kept == [entries[0], entries[2]]


class TestValidatedPostMortem:
    @pytest.mark.parametrize("status", ["closed", "resolved", "fixed", "已关闭"])
    def test_closed_alias_passes(self, status):
        assert is_validated({"status": status}, POST_MORTEM_KIND) is True

    @pytest.mark.parametrize("status", ["open", "investigating", "待处理", None])
    def test_open_or_pending_excluded(self, status):
        assert is_validated({"status": status}, POST_MORTEM_KIND) is False

    def test_filter_validated_post_mortems(self):
        entries = [{"status": "open"}, {"status": "closed"}, {"status": "investigating"}]
        kept = filter_validated(entries, POST_MORTEM_KIND)
        assert kept == [entries[1]]


class TestUnknownKind:
    def test_unknown_kind_raises_with_context(self):
        with pytest.raises(ValueError, match="unknown kind"):
            is_validated({"verified": True}, "unknown")


class TestKeywordHits:
    def test_hit_field_located(self):
        entry = {"title": "下单超时", "symptom": "连接正常", "root_cause": "", "solution": ""}
        assert keyword_hits(entry, "超时") == ["title"]

    def test_empty_keyword_returns_empty(self):
        entry = {"title": "下单超时"}
        assert keyword_hits(entry, "") == []
        assert keyword_hits(entry, None) == []

    def test_custom_fields(self):
        entry = {"title": "x", "root_cause": "信号重合度高"}
        assert keyword_hits(entry, "重合", fields=("root_cause",)) == ["root_cause"]

    def test_filter_by_keyword_preserves_order(self):
        entries = [
            {"title": "突破2000", "symptom": "早盘放量"},
            {"title": "均值回归", "symptom": "震荡回落"},
            {"title": "突破后回踩", "symptom": "量能不足"},
        ]
        kept = filter_by_keyword(entries, "突破")
        assert kept == [entries[0], entries[2]]


class TestNormalizedEntryAttrPath:
    def test_filter_works_on_normalized_entry(self):
        entry = NormalizedEntry(
            entry_id="x", title="超时断连", symptom="", root_cause="", solution="",
            tags=["timeout"], status="closed",
        )
        assert is_validated(entry, POST_MORTEM_KIND) is True
        assert category_matches(entry, None) is True
        assert keyword_hits(entry, "断连") == ["title"]
