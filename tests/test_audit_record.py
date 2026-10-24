# -*- coding: utf-8 -*-
"""test_audit_record.py —— Decision JSONL 单行落盘 + 接受/拒绝不变量。"""
from __future__ import annotations

import _bt_helpers as H  # noqa: F401
import json

import pytest

from core.audit.record import Decision, decision_to_dict, write_decision
from core.risk.state import RiskState


def _sig(ts):
    return H.Signal(signal_id=f"S_{ts.isoformat()}", bar_ts_utc=ts, expert="stub",
                    direction=+1, price_ref=1800.0, atr0=0.2, entry_dist=0.4,
                    l1_in_zone=True, regime_weights={"trend": 1.0})


def _state(eq=10_000):
    return RiskState(equity=eq, atr0=0.2, entry_dist=0.4, stop_price=1799.6,
                     heat_units=0, circuit_state="normal")


def test_accepted_decision_requires_positive_lots(tmp_path):
    ts = H.make_bar(1, 0, 0, 0, 0).ts_utc
    with pytest.raises(Exception):
        Decision(decision_id="D1", signal=_sig(ts), feature_snapshot={},
                 model_version="rules-v1", risk_state=_state(), accepted=True,
                 reject_reason=None, final_signed_lots=0.0,
                 threshold_dataset="CLEAN", decision_rule_version="rules-v1")


def test_rejected_decision_requires_zero_lots(tmp_path):
    ts = H.make_bar(1, 0, 0, 0, 0).ts_utc
    with pytest.raises(Exception):
        Decision(decision_id="D1", signal=_sig(ts), feature_snapshot={},
                 model_version="rules-v1", risk_state=_state(), accepted=False,
                 reject_reason="news_window", final_signed_lots=0.5,
                 threshold_dataset="CLEAN", decision_rule_version="rules-v1")


def test_threshold_dataset_enforced(tmp_path):
    ts = H.make_bar(1, 0, 0, 0, 0).ts_utc
    with pytest.raises(Exception):
        Decision(decision_id="D1", signal=_sig(ts), feature_snapshot={},
                 model_version="rules-v1", risk_state=_state(), accepted=False,
                 reject_reason="x", final_signed_lots=0.0,
                 threshold_dataset="XXX", decision_rule_version="rules-v1")


def test_write_decision_one_line_jsonl(tmp_path):
    ts = H.make_bar(1, 0, 0, 0, 0).ts_utc
    fs = {"equity": 10_000, "risk_pct": 0.01, "stop_dist_price": 0.4,
          "point_value": 100, "min_lot": 0.01, "lot_step": 0.01,
          "kelly_cap": 1.0, "vol_scale": 1.0}
    dec = Decision(decision_id="D1", signal=_sig(ts), feature_snapshot=fs,
                   model_version="rules-v1", risk_state=_state(), accepted=True,
                   reject_reason=None, final_signed_lots=2.5,
                   threshold_dataset="CLEAN", decision_rule_version="rules-v1")
    p = tmp_path / "decisions.jsonl"
    write_decision(str(p), dec)
    write_decision(str(p), dec)
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2                       # 单行一条，追加
    rec = json.loads(lines[0])
    assert rec["decision_id"] == "D1"
    assert rec["accepted"] is True
    assert rec["signal"]["direction"] == 1       # 嵌套 signal 被序列化
    assert rec["risk_state"]["entry_dist"] == 0.4  # 嵌套 risk_state 被序列化
    assert rec["threshold_dataset"] == "CLEAN"


def test_decision_to_dict_handles_nan():
    ts = H.make_bar(1, 0, 0, 0, 0).ts_utc
    dec = Decision(decision_id="D1", signal=_sig(ts), feature_snapshot={"x": float("nan")},
                   model_version="rules-v1", risk_state=_state(), accepted=False,
                   reject_reason="news_window", final_signed_lots=0.0,
                   threshold_dataset="CLEAN", decision_rule_version="rules-v1")
    d = decision_to_dict(dec)
    assert d["feature_snapshot"]["x"] is None    # NaN -> null，JSON 合法
