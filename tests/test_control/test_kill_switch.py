# -*- coding: utf-8 -*-
"""tests.test_control.test_kill_switch —— 独立安全开关的单测。"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from core.control.kill_switch import (
    KillSwitch,
    KillSwitchArmed,
    KillSwitchError,
)


def _fixed_clock(ts: str):
    fixed = datetime.fromisoformat(ts)
    return lambda: fixed


def test_initial_state_not_armed(tmp_path):
    ks = KillSwitch(tmp_path / "ks.json", clock=_fixed_clock("2026-11-02T00:00:00+00:00"))
    assert ks.is_armed() is False
    state = ks.state()
    assert state.armed is False
    assert state.triggered_at is None
    assert (tmp_path / "ks.audit.jsonl").exists()


def test_trigger_persists_across_instances(tmp_path):
    path = tmp_path / "ks.json"
    clock = _fixed_clock("2026-11-02T01:02:03+00:00")
    ks = KillSwitch(path, clock=clock)
    ks.trigger("daily loss 4% > 3%", "risk.circuit")
    # 模拟另一个进程：全新实例，只靠文件通信
    other = KillSwitch(path, clock=clock)
    assert other.is_armed() is True
    state = other.state()
    assert state.reason == "daily loss 4% > 3%"
    assert state.source == "risk.circuit"
    assert state.triggered_at == "2026-11-02T01:02:03+00:00"


def test_trigger_is_idempotent_and_keeps_first_reason(tmp_path):
    ks = KillSwitch(tmp_path / "ks.json")
    ks.trigger("first", "unit-test")
    state = ks.trigger("second", "unit-test")
    assert state.reason == "first"
    lines = (tmp_path / "ks.audit.jsonl").read_text(encoding="utf-8").splitlines()
    actions = [json.loads(line)["action"] for line in lines]
    assert actions.count("trigger") == 1
    assert actions.count("trigger_ignored") == 1


def test_reset_requires_operator_and_clears(tmp_path):
    ks = KillSwitch(tmp_path / "ks.json")
    ks.trigger("test", "unit-test")
    with pytest.raises(KillSwitchError):
        ks.reset("", "no operator")
    with pytest.raises(KillSwitchError):
        ks.reset("ops-01", "")
    state = ks.reset("ops-01", "incident reviewed")
    assert state.armed is False
    assert state.reset_at is not None
    assert ks.is_armed() is False
    actions = [
        json.loads(line)["action"]
        for line in (tmp_path / "ks.audit.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert "reset" in actions


def test_guard_raises_when_armed(tmp_path):
    ks = KillSwitch(tmp_path / "ks.json")
    ks.guard()  # 未触发不抛
    ks.trigger("stop", "unit-test")
    with pytest.raises(KillSwitchArmed) as exc:
        ks.guard()
    assert exc.value.state.armed is True
    assert "stop" in str(exc.value)


def test_corrupt_state_fails_closed(tmp_path):
    path = tmp_path / "ks.json"
    path.write_text("{not valid json", encoding="utf-8")
    ks = KillSwitch(path)
    assert ks.is_armed() is True
    assert "corrupted" in ks.state().reason


def test_missing_state_with_audit_fails_closed(tmp_path):
    path = tmp_path / "ks.json"
    ks = KillSwitch(path)
    ks.trigger("tamper test", "unit-test")
    path.unlink()  # 模拟有人删掉状态文件以绕过
    reopened = KillSwitch(path)
    assert reopened.is_armed() is True
    assert "missing" in reopened.state().reason


def test_atomic_write_leaves_no_temp_files(tmp_path):
    ks = KillSwitch(tmp_path / "ks.json")
    ks.trigger("atomic", "unit-test")
    ks.reset("ops-01", "done")
    leftovers = [p.name for p in tmp_path.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []


def test_audit_contains_metadata(tmp_path):
    ks = KillSwitch(tmp_path / "ks.json")
    ks.trigger("reconcile mismatch", "execution.reconcile",
               metadata={"codes": ["ORDER_MISSING"]})
    line = (tmp_path / "ks.audit.jsonl").read_text(encoding="utf-8").splitlines()[-1]
    entry = json.loads(line)
    assert entry["metadata"] == {"codes": ["ORDER_MISSING"]}
