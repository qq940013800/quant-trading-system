# -*- coding: utf-8 -*-
"""tests.test_audit.test_knowledge_match —— 相似度纯函数测试。"""
from __future__ import annotations

import inspect

import pytest

from core.audit.knowledge_match import (
    char_overlap,
    find_similar,
    similarity,
    tag_jaccard,
    text_jaccard,
)


class TestTagJaccard:
    def test_identical_tags_score_one(self):
        assert tag_jaccard(["risk", "timeout"], ["timeout", "risk"]) == 1.0

    def test_disjoint_tags_score_zero(self):
        assert tag_jaccard(["risk"], ["api"]) == 0.0

    def test_partial_overlap(self):
        # 交集 1，并集 3 → 1/3
        assert tag_jaccard(["a", "b"], ["b", "c"]) == pytest.approx(1 / 3)

    def test_both_empty_guarded(self):
        assert tag_jaccard([], []) == 0.0


class TestTextOverlap:
    def test_identical_text_score_one(self):
        assert text_jaccard("下单超时连接断开", "下单超时连接断开") == 1.0
        assert char_overlap("下单超时连接断开", "下单超时连接断开") == 1.0

    def test_disjoint_text_score_zero(self):
        assert text_jaccard("趋势突破", "均值回归震荡") == 0.0

    def test_chinese_bigram_overlap_positive(self):
        ov = char_overlap("下单超时", "下单失败")
        assert 0.0 < ov < 1.0

    def test_char_overlap_distinguishes_text(self):
        close = char_overlap("止损被扫后反弹", "止损被扫后回落")
        far = char_overlap("止损被扫后反弹", "数据库连接配置错误")
        assert close > far


class TestSimilarity:
    def test_tag_match_beats_disjoint(self):
        a = {"title": "下单超时", "tags": ["timeout", "connection"]}
        close = {"title": "连接超时", "tags": ["timeout"]}
        far = {"title": "数据库配置", "tags": ["db", "config"]}
        assert similarity(a, close).score > similarity(a, far).score

    def test_tag_weight_one_ignores_text(self):
        a = {"title": "完全不同的文本内容甲乙丙", "tags": ["risk"]}
        b = {"title": "另一套毫无关系的文本丁戊己", "tags": ["risk"]}
        m = similarity(a, b, tag_weight=1.0)
        assert m.tag_jaccard == 1.0
        assert m.score == pytest.approx(1.0)

    def test_score_components_within_range(self):
        m = similarity({"title": "突破 2000 止损", "tags": ["risk"]},
                       {"title": "均值回归 震荡", "tags": ["data"]})
        assert 0.0 <= m.score <= 1.0
        assert 0.0 <= m.tag_jaccard <= 1.0
        assert 0.0 <= m.text_jaccard <= 1.0

    def test_invalid_tag_weight_raises(self):
        with pytest.raises(ValueError):
            similarity({"tags": []}, {"tags": []}, tag_weight=1.5)


class TestFindSimilar:
    def test_ranking_and_threshold(self):
        entries = [
            {"title": "下单超时被拒", "tags": ["timeout", "order"]},
            {"title": "数据库写入失败", "tags": ["db"]},
            {"title": "连接超时重试", "tags": ["timeout", "connection"]},
        ]
        results = find_similar("超时", entries, threshold=0.0)
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)
        assert results[0]["entry"]["title"] in ("下单超时被拒", "连接超时重试")

        strict = find_similar("超时", entries, threshold=0.5)
        assert all(r["score"] >= 0.5 for r in strict)

    def test_query_str_is_normalized(self):
        entries = [{"title": "连接超时", "tags": ["timeout"]}]
        results = find_similar("超时 timeout", entries)
        assert len(results) == 1

    def test_invalid_threshold_raises(self):
        with pytest.raises(ValueError):
            find_similar("x", [{"title": "y"}], threshold=2.0)


class TestNoExternalDependency:
    def test_module_source_has_no_db_or_network_imports(self):
        from core.audit import knowledge_match as mod
        src = inspect.getsource(mod)
        for banned in ("psycopg", "requests", "socket", "db_writer",
                       "sqlalchemy", "httpx", "urllib.request", "numpy"):
            assert banned not in src
