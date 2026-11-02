# -*- coding: utf-8 -*-
"""Tests for the unified read-only live-exchange connection module."""

import pytest

from app.services.live_trading import connection as conn


@pytest.fixture(autouse=True)
def _clear_cache():
    conn._overview_cache.clear()
    yield
    conn._overview_cache.clear()


class _FakeOkxClient:
    """Minimal client exposing only get_balance() in OKX payload shape."""

    def __init__(self, payload=None, raise_exc=None):
        self._payload = payload or {"code": "0", "data": [{"totalEq": "12345.67"}]}
        self._raise_exc = raise_exc

    def get_balance(self):
        if self._raise_exc:
            raise self._raise_exc
        return self._payload


class _FakePingClient:
    """Minimal client exposing only ping() (public-endpoint fallback)."""

    def __init__(self, ok=True):
        self._ok = ok

    def ping(self):
        return self._ok


def _okx_cfg():
    return {
        "exchange_id": "okx",
        "api_key": "fake-key",
        "secret_key": "fake-secret",
        "passphrase": "fake-pass",
        "environment": "live",
        "market_scope": "both",
        "enable_demo_trading": False,
    }


def _patch_factory(monkeypatch, client):
    monkeypatch.setattr("app.services.live_trading.factory.create_client", lambda cfg, market_type=None: client)


# ---------------------------------------------------------------- fetch_account_equity

def test_fetch_account_equity_extracts_okx_total_eq(monkeypatch):
    monkeypatch.setattr("app.routes.strategy_account_routes._first_okx_credential_id", lambda uid: 7)
    monkeypatch.setattr(conn, "resolve_credential_config", lambda cid, user_id=1: _okx_cfg())
    _patch_factory(monkeypatch, _FakeOkxClient())

    assert conn.fetch_account_equity(1, use_cache=False) == 12345.67


def test_fetch_account_equity_non_okx_returns_none(monkeypatch):
    cfg = _okx_cfg()
    cfg["exchange_id"] = "bybit"
    monkeypatch.setattr("app.routes.strategy_account_routes._first_okx_credential_id", lambda uid: 7)
    monkeypatch.setattr(conn, "resolve_credential_config", lambda cid, user_id=1: cfg)

    assert conn.fetch_account_equity(1, use_cache=False) is None


def test_fetch_account_equity_failure_returns_none(monkeypatch):
    monkeypatch.setattr("app.routes.strategy_account_routes._first_okx_credential_id", lambda uid: 7)
    monkeypatch.setattr(conn, "resolve_credential_config", lambda cid, user_id=1: _okx_cfg())
    _patch_factory(monkeypatch, _FakeOkxClient(raise_exc=RuntimeError("boom")))

    assert conn.fetch_account_equity(1, use_cache=False) is None


def test_fetch_account_equity_success_is_cached(monkeypatch):
    monkeypatch.setattr("app.routes.strategy_account_routes._first_okx_credential_id", lambda uid: 7)
    monkeypatch.setattr(conn, "resolve_credential_config", lambda cid, user_id=1: _okx_cfg())
    calls = {"n": 0}
    real = _FakeOkxClient()

    def _create(cfg, market_type=None):
        calls["n"] += 1
        return real

    monkeypatch.setattr("app.services.live_trading.factory.create_client", _create)

    assert conn.fetch_account_equity(1, use_cache=True) == 12345.67
    assert conn.fetch_account_equity(1, use_cache=True) == 12345.67
    assert calls["n"] == 1  # second read served from the 30s TTL cache


# ---------------------------------------------------------------- probe_connection

def test_probe_connection_success_captures_equity_and_latency(monkeypatch):
    _patch_factory(monkeypatch, _FakeOkxClient())
    result = conn.probe_connection(_okx_cfg(), markets=["swap"])
    assert result["ok"] is True
    assert result["exchange_id"] == "okx"
    assert result["environment"] == "live"
    assert result["equity"] == 12345.67
    assert result["latency_ms"] is not None
    assert result["tested_markets"] == ["swap"]


def test_probe_connection_error_never_raises(monkeypatch):
    _patch_factory(monkeypatch, _FakeOkxClient(raise_exc=RuntimeError("auth denied")))
    result = conn.probe_connection(_okx_cfg(), markets=["swap"])
    assert result["ok"] is False
    assert "auth denied" in (result.get("error") or "")


def test_probe_connection_ping_fallback(monkeypatch):
    _patch_factory(monkeypatch, _FakePingClient(ok=True))
    result = conn.probe_connection({"exchange_id": "okx", "environment": "live"}, markets=["swap"])
    assert result["ok"] is True
    assert result.get("equity") is None


def test_probe_connection_scope_both_probes_spot_and_swap(monkeypatch):
    seen = []

    def _create(cfg, market_type=None):
        seen.append(market_type)
        return _FakePingClient(ok=True)

    monkeypatch.setattr("app.services.live_trading.factory.create_client", _create)
    result = conn.probe_connection(_okx_cfg())
    assert result["ok"] is True
    assert seen == ["spot", "swap"]


# ---------------------------------------------------------------- test_saved_credential / test_strategy_connection

def test_test_saved_credential_tags_credential_id(monkeypatch):
    monkeypatch.setattr(conn, "resolve_credential_config", lambda cid, user_id=1: _okx_cfg())
    _patch_factory(monkeypatch, _FakeOkxClient())
    result = conn.test_saved_credential(9, user_id=1)
    assert result["credential_id"] == 9
    assert result["ok"] is True


def test_test_strategy_connection_without_exchange_config(monkeypatch):
    monkeypatch.setattr(
        "app.services.exchange_execution.load_strategy_configs", lambda sid: {"id": sid}
    )
    result = conn.test_strategy_connection(11, user_id=1)
    assert result["ok"] is False
    assert result["error"] == "STRATEGY_HAS_NO_EXCHANGE_CONFIG"
    assert result["strategy_id"] == 11


def test_test_strategy_connection_resolves_credential_ref(monkeypatch):
    monkeypatch.setattr(
        "app.services.exchange_execution.load_strategy_configs",
        lambda sid: {
            "id": sid,
            "user_id": 1,
            "market_type": "swap",
            "exchange_config": {"credential_id": 7},
        },
    )
    monkeypatch.setattr(
        "app.services.exchange_execution.resolve_exchange_config",
        lambda cfg, user_id=1: _okx_cfg(),
    )
    _patch_factory(monkeypatch, _FakeOkxClient())
    result = conn.test_strategy_connection(11, user_id=1)
    assert result["ok"] is True
    assert result["strategy_id"] == 11
    assert result["tested_markets"] == ["swap"]


# ---------------------------------------------------------------- connection_overview

def test_connection_overview_marks_ok_and_error(monkeypatch):
    monkeypatch.setattr(
        conn,
        "list_saved_credentials",
        lambda uid: [
            {"id": 1, "name": "OKX Live", "exchange_id": "okx", "api_key_hint": "a***z"},
            {"id": 2, "name": "Bybit", "exchange_id": "bybit", "api_key_hint": "b***y"},
        ],
    )
    monkeypatch.setattr(
        conn,
        "resolve_credential_config",
        lambda cid, user_id=1: _okx_cfg(),
    )

    def _fake_probe(cfg, markets=None):
        cid = cfg.get("_cid", 1)
        if cid == 2:
            return {"ok": False, "exchange_id": "bybit", "error": "auth denied"}
        return {"ok": True, "exchange_id": "okx", "latency_ms": 42.0}

    # probe_connection is monkeypatched at the module level; cfg carries _cid.
    def _resolved(cid, user_id=1):
        cfg = _okx_cfg()
        cfg["_cid"] = int(cid)
        return cfg

    monkeypatch.setattr(conn, "resolve_credential_config", _resolved)
    monkeypatch.setattr(conn, "probe_connection", _fake_probe)

    payload = conn.connection_overview(1)
    assert payload["total"] == 2
    assert payload["ok_count"] == 1
    by_exchange = {c["exchange_id"]: c for c in payload["connections"]}
    assert by_exchange["okx"]["ok"] is True
    assert by_exchange["bybit"]["ok"] is False


def test_connection_overview_skips_ibkr(monkeypatch):
    monkeypatch.setattr(
        conn,
        "list_saved_credentials",
        lambda uid: [{"id": 5, "name": "IBKR", "exchange_id": "ibkr", "api_key_hint": ""}],
    )
    payload = conn.connection_overview(1)
    assert payload["total"] == 1
    assert payload["ok_count"] == 0
    assert payload["connections"][0]["skipped"] is True
    assert payload["connections"][0]["ok"] is None


def test_connection_overview_is_cached(monkeypatch):
    monkeypatch.setattr(conn, "list_saved_credentials", lambda uid: [])
    monkeypatch.setattr(conn, "probe_connection", lambda cfg, markets=None: {"ok": True})
    first = conn.connection_overview(1)
    second = conn.connection_overview(1)
    assert first["checked_at"] == second["checked_at"]  # served from 30s TTL cache
