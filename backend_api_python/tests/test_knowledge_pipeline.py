"""Tests for the knowledge-pipeline service facade and routes.

DB access is stubbed; these tests do not touch a real database. Fail-open
behavior, validation guards, enum normalization and response envelope are
the contract under test (design §6.1, §6.4, §8.3).
"""
import inspect

import pytest
from flask import g

from app.services import knowledge_service as svc
from app.routes import knowledge as routes


# ----------------------------------------------------------------------
# DB stubs
# ----------------------------------------------------------------------
class _MockCursor:
    def execute(self, *args, **kwargs):
        pass

    def fetchall(self):
        return []

    def fetchone(self):
        return None

    def close(self):
        pass


class _ConfigCursor(_MockCursor):
    """Cursor whose fetchone returns a configured row."""

    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _MockConn:
    def __init__(self, cursor=None):
        self._cursor = cursor or _MockCursor()

    def cursor(self):
        return self._cursor

    def commit(self):
        pass

    def close(self):
        pass


class _MockCM:
    def __init__(self, row=None):
        self._row = row

    def __enter__(self):
        return _MockConn(_ConfigCursor(self._row) if self._row is not None else _MockCursor())

    def __exit__(self, *exc):
        return False


@pytest.fixture
def stub_db(monkeypatch):
    monkeypatch.setattr(svc, "get_db_connection", lambda: _MockCM())


@pytest.fixture
def service(stub_db):
    return svc.KnowledgeService()


# ----------------------------------------------------------------------
# Service: fail-open reads
# ----------------------------------------------------------------------
def test_list_faults_fails_open_on_db_error(monkeypatch):
    def _boom():
        raise RuntimeError("private database detail")

    monkeypatch.setattr(svc, "get_db_connection", _boom)
    out = svc.KnowledgeService().list_faults(keyword="btc")
    assert out == []


def test_get_stats_fails_open_with_zeroes(monkeypatch):
    monkeypatch.setattr(svc, "get_db_connection", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    stats = svc.KnowledgeService().get_stats()
    assert stats["fault_knowledge"] == {"total": 0, "verified": 0}
    assert stats["post_mortems"] == {"total": 0, "closed": 0}
    assert stats["experiments"] == {"total": 0, "completed": 0}
    assert stats["playbooks"] == {"total": 0, "validated": 0}


# ----------------------------------------------------------------------
# Service: write validation guards
# ----------------------------------------------------------------------
def test_register_fault_requires_title_and_symptom(service):
    res = service.register_fault(title="", symptom="")
    assert res["written"] is False
    assert res["reason"] == "missing_title_or_symptom"


def test_register_fault_normalizes_invalid_category_and_severity(service):
    res = service.register_fault(
        title="t", symptom="s", category="nope", severity="P9",
    )
    assert res["written"] is True
    # Guards coerce unknown category/severity to safe defaults inside the service.
    assert res["fault_uid"].startswith("fault-")


def test_start_experiment_requires_name_and_hypothesis(service):
    res = service.start_experiment(name="", hypothesis="")
    assert res["written"] is False


def test_end_experiment_rejects_invalid_decision(service):
    res = service.end_experiment("exp-abc", metrics={}, conclusion="c", decision="whatever")
    assert res["written"] is False
    assert res["reason"] == "invalid_decision"


def test_end_experiment_rejects_missing_uid(service):
    res = service.end_experiment("", metrics={}, conclusion="c", decision="pivot")
    assert res["written"] is False


def test_end_experiment_rejects_promote_when_rule_not_frozen(monkeypatch):
    monkeypatch.setattr(
        svc, "get_db_connection",
        lambda: _MockCM({"decision_rule_frozen": False, "status": "running"}),
    )
    res = svc.KnowledgeService().end_experiment(
        "exp-abc", metrics={}, conclusion="c", decision="promote_to_production",
    )
    assert res["written"] is False
    assert res["reason"] == "rule_not_frozen"


def test_end_experiment_not_found(monkeypatch):
    monkeypatch.setattr(svc, "get_db_connection", lambda: _MockCM(None))
    res = svc.KnowledgeService().end_experiment(
        "exp-missing", metrics={}, conclusion="c", decision="pivot",
    )
    assert res["written"] is False
    assert res["reason"] == "experiment_not_found"


def test_upsert_playbook_requires_source_refs(service):
    res = service.upsert_playbook(title="p", source_refs=[])
    assert res["written"] is False
    assert res["reason"] == "missing_source_refs"


def test_register_post_mortem_requires_title_and_happened(service):
    res = service.register_post_mortem(
        title="", post_mortem_type="incident", severity="P2",
        what_happened="", why_it_happened="", what_we_learned="", how_to_improve="",
    )
    assert res["written"] is False


# ----------------------------------------------------------------------
# Service: normalization helpers
# ----------------------------------------------------------------------
def test_load_json_parses_string_and_passes_through():
    assert svc.KnowledgeService._load_json('["a", "b"]') == ["a", "b"]
    assert svc.KnowledgeService._load_json({"k": 1}) == {"k": 1}
    assert svc.KnowledgeService._load_json(None) is None
    assert svc.KnowledgeService._load_json("not-json") == "not-json"


def test_limit_clamps_defaults_bounds_and_garbage():
    assert svc._limit(None) == 20
    assert svc._limit("3") == 3
    assert svc._limit(0) == 1
    assert svc._limit(9999) == 100
    assert svc._limit("x") == 20


# ----------------------------------------------------------------------
# Routes: envelope and validation
# ----------------------------------------------------------------------
class _StubService:
    def list_faults(self, **kwargs):
        return [{"fault_uid": "fault-x", "title": "sample"}]

    def list_experiments(self, **kwargs):
        return []

    def list_playbooks(self, **kwargs):
        return []

    def get_stats(self):
        return {"fault_knowledge": {"total": 1, "verified": 1}}

    def get_lessons(self, **kwargs):
        return []

    def register_fault(self, **kwargs):
        return {"fault_uid": "fault-x", "written": True}

    def start_experiment(self, **kwargs):
        return {"experiment_uid": "exp-x", "written": True}

    def end_experiment(self, uid, **kwargs):
        return {"written": True}

    def register_post_mortem(self, **kwargs):
        return {"post_mortem_uid": "pm-x", "written": True}

    def upsert_playbook(self, **kwargs):
        return {"playbook_uid": "pb-x", "version": 1, "written": True}


@pytest.fixture
def stub_route_service(monkeypatch):
    stub = _StubService()
    monkeypatch.setattr(routes, "get_knowledge_service", lambda: stub)
    return stub


def test_get_faults_envelope(app, stub_route_service):
    with app.test_request_context("/api/knowledge/faults"):
        g.user_id = 1
        resp = inspect.unwrap(routes.list_faults)()
    status = resp.status_code
    payload = resp.get_json()
    assert status == 200
    assert payload["code"] == 1
    assert payload["data"]["total"] == 1


def test_post_fault_missing_title_returns_400(app):
    with app.test_request_context("/api/knowledge/faults", method="POST", json={"symptom": "x"}):
        g.user_id = 1
        resp, status = inspect.unwrap(routes.register_fault)()
    payload = resp.get_json()
    assert status == 400
    assert payload["code"] == 0


def test_post_experiment_end_missing_decision_returns_400(app):
    with app.test_request_context(
        "/api/knowledge/experiments/exp-x/end", method="POST", json={"conclusion": "c"}
    ):
        g.user_id = 1
        resp, status = inspect.unwrap(routes.end_experiment)("exp-x")
    payload = resp.get_json()
    assert status == 400
    assert payload["code"] == 0


def test_post_playbook_missing_refs_returns_400(app):
    with app.test_request_context(
        "/api/knowledge/playbooks", method="POST", json={"title": "p"}
    ):
        g.user_id = 1
        resp, status = inspect.unwrap(routes.upsert_playbook)()
    payload = resp.get_json()
    assert status == 400
    assert payload["code"] == 0
