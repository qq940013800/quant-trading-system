# -*- coding: utf-8 -*-
"""tests.test_audit.test_knowledge_normalize —— 条目结构化与标签归一测试。"""
from __future__ import annotations

import inspect

import pytest

from core.audit.knowledge_normalize import (
    generate_id,
    normalize_entry,
    normalize_severity,
    normalize_status,
    normalize_tag,
    normalize_tags,
)


class TestTagNormalize:
    @pytest.mark.parametrize("raw,expected", [
        (" Timeout ", "timeout"),
        ("TIMEOUT", "timeout"),
        ("超时", "timeout"),
        ("Stop Loss", "stop_loss"),
        ("stop-loss", "stop_loss"),
        ("连接失败", "connection"),
        ("  滑点 ", "slippage"),
        ("API", "api"),
    ])
    def test_tag_synonym_and_case_fold(self, raw, expected):
        assert normalize_tag(raw) == expected

    def test_tags_split_dedupe_preserve_order(self):
        tags = normalize_tags("超时, 超时; stop loss、API api")
        assert tags == ["timeout", "stop_loss", "api"]

    def test_tags_accept_list_and_drop_empty(self):
        assert normalize_tags(["  ", "", "risk"]) == ["risk"]
        assert normalize_tags(None) == []


class TestSeverityStatus:
    @pytest.mark.parametrize("raw,expected", [
        ("Critical", "P0"), ("P1", "P1"), ("中", "P2"), ("low", "P3"),
    ])
    def test_severity_map(self, raw, expected):
        sev, warn = normalize_severity(raw)
        assert sev == expected
        assert warn is None

    def test_unknown_severity_falls_back_with_warning(self):
        sev, warn = normalize_severity("banana")
        assert sev == "P3"
        assert warn is not None and "banana" in warn

    @pytest.mark.parametrize("raw,expected", [
        ("closed", "closed"), ("已修复", "closed"), ("investigating", "investigating"),
        ("verified", "verified"),
    ])
    def test_status_map(self, raw, expected):
        status, warn = normalize_status(raw)
        assert status == expected
        assert warn is None

    def test_unknown_status_falls_back_with_warning(self):
        status, warn = normalize_status("weird")
        assert status == "open"
        assert warn is not None


class TestNormalizeEntry:
    def test_dict_entry_with_aliases_and_normalization(self):
        raw = {
            "uid": "F-12",
            "标题": "下单超时导致拒单",
            "症状": "OrderSend 超时，连接断开",
            "根因": "网络抖动",
            "方案": "加重试与心跳",
            "标签": ["Timeout", "连接失败", "risk"],
            "严重度": "High",
            "状态": "处理中",
        }
        entry = normalize_entry(raw)
        assert entry.entry_id == "F-12"
        assert entry.title == "下单超时导致拒单"
        assert entry.tags == ["timeout", "connection", "risk"]
        assert entry.severity == "P1"
        assert entry.status == "investigating"
        assert entry.root_cause == "网络抖动"
        assert entry.solution == "加重试与心跳"

    def test_missing_id_is_deterministic(self):
        a = normalize_entry({"title": "连接超时", "症状": "无法下单"})
        b = normalize_entry({"title": "连接超时", "症状": "无法下单"})
        assert a.entry_id == b.entry_id
        assert len(a.entry_id) == 16

    def test_warnings_for_missing_title_and_symptom(self):
        entry = normalize_entry({"标签": ["risk"]})
        assert any("缺少标题与症状" in w for w in entry.warnings)

    def test_text_entry_normalized(self):
        entry = normalize_entry("  OrderSend 超时，连接被重置。需要加重试机制 ")
        assert entry.symptom.startswith("ordersend")
        assert entry.title
        assert entry.status == "open"
        assert any("自由文本" in w for w in entry.warnings)

    def test_empty_text_raises(self):
        with pytest.raises(ValueError):
            normalize_entry("   ")

    def test_non_dict_str_raises_type_error(self):
        with pytest.raises(TypeError):
            normalize_entry(12345)

    def test_generate_id_stable(self):
        assert generate_id("同样标题") == generate_id("同样标题")


class TestNoExternalDependency:
    def test_module_source_has_no_db_or_network_imports(self):
        from core.audit import knowledge_normalize as mod
        src = inspect.getsource(mod)
        for banned in ("psycopg", "requests", "socket", "db_writer",
                       "sqlalchemy", "httpx", "urllib.request"):
            assert banned not in src
