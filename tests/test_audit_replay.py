# -*- coding: utf-8 -*-
"""test_audit_replay.py —— 快照回放可还原五要素（实现 spec 4.6 / 设计⑦.D）。"""
from __future__ import annotations

import _bt_helpers as H  # noqa: F401
import json

import pytest

from core.audit.record import Decision, write_decision
from core.audit.replay import ReplayMismatch, read_decisions, replay_decision
from core.risk.state import RiskState


def _fs(equity=10_000, risk_pct=0.01, stop_dist=0.4, vol_scale=1.0):
    return {"equity": equity, "risk_pct": risk_pct, "stop_dist_price": stop_dist,
            "point_value": 100, "min_lot": 0.01, "lot_step": 0.01,
            "kelly_cap": 1.0, "vol_scale": vol_scale}


def _dec(rid, accepted, lots, reject, fs):
    ts = H.make_bar(int(rid[1:]), 0, 0, 0, 0).ts_utc
    sig = H.Signal(signal_id=f"S_{rid}", bar_ts_utc=ts, expert="stub", direction=+1,
                   price_ref=1800.0, atr0=0.2, entry_dist=0.4)
    st = RiskState(equity=fs["equity"], atr0=0.2, entry_dist=0.4, stop_price=1799.6,
                   heat_units=0)
    return Decision(decision_id=rid, signal=sig, feature_snapshot=fs,
                    model_version="rules-v1", risk_state=st, accepted=accepted,
                    reject_reason=reject, final_signed_lots=lots,
                    threshold_dataset="CLEAN", decision_rule_version="rules-v1")


def test_replay_accepted_lots_match(tmp_path):
    # risk_budget=100, per_unit=0.4*100=40 -> 2.5 lots
    dec = _dec("D1", True, 2.5, None, _fs())
    p = tmp_path / "d.jsonl"
    write_decision(str(p), dec)
    rec = read_decisions(str(p))[0]
    out = replay_decision(rec)
    assert out["ok"] is True
    assert out["accepted"] is True
    assert out["recomputed_lots"] == pytest.approx(2.5)


def test_replay_rejected_zero_lots(tmp_path):
    dec = _dec("D2", False, 0.0, "news_window", _fs())
    p = tmp_path / "d.jsonl"
    write_decision(str(p), dec)
    rec = read_decisions(str(p))[0]
    out = replay_decision(rec)
    assert out["ok"] is True and out["accepted"] is False
    assert out["reject_reason"] == "news_window"


def test_replay_detects_tampered_lots(tmp_path):
    dec = _dec("D3", True, 2.5, None, _fs())
    p = tmp_path / "d.jsonl"
    write_decision(str(p), dec)
    # 篡改手数
    rec = read_decisions(str(p))[0]
    rec["final_signed_lots"] = 9.99
    with pytest.raises(ReplayMismatch):
        replay_decision(rec)


def test_replay_missing_inputs_raises(tmp_path):
    rec = {"decision_id": "D4", "accepted": True, "final_signed_lots": 1.0,
           "reject_reason": None, "feature_snapshot": {"equity": 1000}}
    with pytest.raises(ReplayMismatch):
        replay_decision(rec)
