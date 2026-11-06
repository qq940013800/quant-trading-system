# -*- coding: utf-8 -*-
"""tests/test_selector_audit.py —— SelectionRecord 落盘/读回/回放单测。

覆盖：
1. write/read 往返（字段不丢、类型还原）；
2. replay_selection 重算强度与记录一致；
3. 篡改权重（事后改 strategy_weights）→ replay 交叉校验抛带上下文错误；
4. 缺字段 → read_selections 抛带上下文错误；
5. 权重和不为 1 / 负权重 → 构造即抛（frozen 校验）。
"""
from __future__ import annotations

import json

import pytest

from core.selector.audit import (SelectionAuditError, SelectionRecord,
                                 read_selections, replay_selection,
                                 write_selection)


def _sample_record() -> SelectionRecord:
    return SelectionRecord(
        ts_utc="2024-01-01T00:05:00+00:00",
        state="trend",
        regime_probs={"trend": 0.8, "mean_reversion": 0.1, "ranging": 0.1},
        strategy_weights={"e_trend": 0.8, "e_mr": 0.2},
        expert_signals={
            "e_trend": {"has_signal": True, "direction": 1,
                        "atr0": 1.0, "entry_dist": 2.0},
            "e_mr": {"has_signal": True, "direction": -1,
                     "atr0": 0.5, "entry_dist": 1.0},
        },
        # 净强度 = |0.8·(+1) + 0.2·(-1)| = 0.6（与回放重算口径一致）
        blend_strength=0.6,
        strategy_versions={"e_trend": "e_trend-v1", "e_mr": "e_mr-v1"},
        degraded=False,
        signal_id="XAUUSD_2024-01-01T00:05:00+00:00_regime_blend_v1_1",
    )


def test_write_read_roundtrip(tmp_path):
    p = tmp_path / "sel.jsonl"
    rec = _sample_record()
    write_selection(str(p), rec)
    back = read_selections(str(p))
    assert len(back) == 1
    r = back[0]
    assert r.state == "trend"
    assert r.regime_probs["trend"] == pytest.approx(0.8)
    assert r.strategy_weights["e_trend"] == pytest.approx(0.8)
    assert r.expert_signals["e_trend"]["direction"] == 1
    assert r.signal_id == rec.signal_id
    # 回放自洽
    rep = replay_selection(r)
    assert rep["blend_strength"] == pytest.approx(0.6)
    assert rep["strategy_weights"]["e_trend"] == pytest.approx(0.8)


def test_replay_detects_weight_tamper(tmp_path):
    """事后篡改 strategy_weights（仍保持和为 1）→ 重算强度与记录不符。"""
    p = tmp_path / "sel.jsonl"
    write_selection(str(p), _sample_record())
    raw = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    raw["strategy_weights"]["e_trend"] = 0.95
    raw["strategy_weights"]["e_mr"] = 0.05     # 和仍为 1，绕过构造校验
    p.write_text(json.dumps(raw, ensure_ascii=False) + "\n", encoding="utf-8")
    back = read_selections(str(p))             # 构造校验能过
    with pytest.raises(SelectionAuditError) as exc:
        replay_selection(back[0])              # 重算 0.95≠0.6 → 抓到
    assert "tampered" in str(exc.value.context["detail"])


def test_missing_field_raises(tmp_path):
    p = tmp_path / "sel.jsonl"
    write_selection(str(p), _sample_record())
    raw = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    raw.pop("expert_signals")
    p.write_text(json.dumps(raw, ensure_ascii=False) + "\n", encoding="utf-8")
    with pytest.raises(SelectionAuditError) as exc:
        read_selections(str(p))
    assert "missing field" in str(exc.value.context["detail"])


def test_malformed_json_raises(tmp_path):
    p = tmp_path / "sel.jsonl"
    p.write_text("{not json}\n", encoding="utf-8")
    with pytest.raises(SelectionAuditError):
        read_selections(str(p))


def test_construction_validates_weights():
    base = dict(
        ts_utc="2024-01-01T00:05:00+00:00", state="trend",
        regime_probs={"trend": 1.0},
        expert_signals={}, blend_strength=0.0,
        strategy_versions={}, degraded=False)
    with pytest.raises(SelectionAuditError):
        SelectionRecord(**base, strategy_weights={"a": 0.9, "b": 0.2})  # 和≠1
    with pytest.raises(SelectionAuditError):
        SelectionRecord(**base, strategy_weights={"a": -0.1, "b": 1.1})  # 负权重
    with pytest.raises(SelectionAuditError):
        SelectionRecord(**base, strategy_weights={})                    # 空 dict
