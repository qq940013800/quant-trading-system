# -*- coding: utf-8 -*-
"""tests/test_score_agent_eval.py —— 评分脚本、答案键与 registry 结构的静态校验。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import score_agent_eval as s  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "causal_guard"
KEY = s.load_json(FIXTURES / "answer_key.json")


def test_perfect_results_score_full() -> None:
    """输入约束：答案键自身作为结果。不变量：检出率 1、误报率 0、无缺失。"""
    r = s.score(KEY, KEY)
    assert r["detection_rate"] == 1.0 and r["false_positive_rate"] == 0.0 and r["missing"] == 0


def test_missing_is_not_pass() -> None:
    """不变量：缺失项只计 missing，不计 TN，也不计检出。"""
    r = s.score(KEY, {})
    assert r["missing"] == sum(len(v) for v in KEY.values())
    assert r["tp"] == r["tn"] == r["fp"] == r["fn"] == 0


def test_unknown_is_neither_detection_nor_false_positive() -> None:
    """不变量：UNKNOWN 不增加 tp/fp，只计入 unknown。"""
    results = {case: {c: "UNKNOWN" for c in checks} for case, checks in KEY.items()}
    r = s.score(KEY, results)
    assert r["tp"] == r["fp"] == 0 and r["unknown"] == sum(len(v) for v in KEY.values())


def test_false_positive_on_clean_case() -> None:
    """干净对照被判 FAIL 必须计入误报。"""
    r = s.score(KEY, {"c05_clean": {"1": "FAIL"}})
    assert r["fp"] == 1


def test_invalid_verdict_rejected(tmp_path: Path) -> None:
    """非法 verdict 必须抛出 ValueError，而不是被忽略。"""
    bad = tmp_path / "bad.json"
    bad.write_text('{"c01": {"1": "MAYBE"}}', encoding="utf-8")
    try:
        s.load_json(bad)
    except ValueError:
        return
    raise AssertionError("非法 verdict 未被拒绝")


def test_every_fixture_has_key_entry() -> None:
    """不变量：每个用例文件在答案键中有条目，反之亦然。"""
    cases = {p.stem for p in FIXTURES.glob("c*.txt")}
    assert cases == set(KEY), f"用例与答案键不一致：{sorted(cases ^ set(KEY))}"


def test_registry_trials_n_is_non_negative_int() -> None:
    """registry.yaml 必须含非负整数 trials_N 与 decision_rule 段。"""
    text = (ROOT / "registry.yaml").read_text(encoding="utf-8")
    m = re.search(r"^trials_N:\s*(\d+)\b", text, re.M)
    assert m, "trials_N 缺失或不是非负整数"
    assert re.search(r"^decision_rule:", text, re.M), "缺少 decision_rule"
