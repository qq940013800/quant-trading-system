"""Tests for validation-layer honest-display contract.

The validation endpoints expose read-only module status / audit log / stress
test views. When no real probe or persisted event source exists, the contract
is: no fabricated metrics, no simulated audit entries, and demo stress
scenarios are explicitly tagged so the frontend renders an empty state.

No live order, position or balance path is touched (design §8.3).
"""
import pytest


def test_status_modules_are_pending_without_fabricated_details(client):
    resp = client.get("/api/validation/status")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["code"] == 1
    data = payload["data"]

    modules = data["modules"]
    assert len(modules) == 13
    assert data["healthy"] == 0
    assert data["connected"] == 0
    assert data["pending"] == len(modules)

    # Fabricated metric sentinels must not appear in any module detail.
    forbidden = ["0.15", "1.23", "0.032", "78.5", "0.1bp", "24种", "23ms", "5个Active"]
    for m in modules:
        assert m["status"] == "pending"
        assert m["details"] == ""
        for token in forbidden:
            assert token not in (m["details"] or ""), f"fabricated token {token} in {m['id']}"


def test_audit_logs_return_empty_without_persisted_events(client):
    resp = client.get("/api/validation/audit-logs?limit=20")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["code"] == 1
    assert payload["data"]["logs"] == []
    assert payload["data"]["total"] == 0


def test_audit_logs_limit_is_clamped(client):
    resp = client.get("/api/validation/audit-logs?limit=99999")
    assert resp.status_code == 200
    assert resp.get_json()["data"]["limit"] == 100


def test_stress_test_is_tagged_demo_without_fabricated_score(client):
    resp = client.get("/api/validation/stress-test")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["code"] == 1
    data = payload["data"]

    assert data["data_kind"] == "demo"
    assert data["overall_risk_score"] is None
    assert data["risk_level"] is None
    assert len(data["scenarios"]) == 5
    # Demo summary must not assert a real drawdown conclusion.
    assert "2%以内" not in (data["summary"] or "")
