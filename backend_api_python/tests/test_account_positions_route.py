# -*- coding: utf-8 -*-
"""#295 account positions route: snapshot-to-contract mapping and fallback behavior."""

import inspect

import pytest
from flask import g

import app.routes.account as routes
from app.services.live_trading import account_snapshot, connection


# ----------------------------------------------------------------- pure mapping


def test_build_payload_maps_swap_and_spot_legs():
    snapshot = {
        "swap_positions": [
            {
                "symbol": "BTC/USDT",
                "side": "long",
                "size": 0.5,
                "entry_price": 60000.0,
                "market_type": "swap",
                "inst_id": "BTC-USDT-SWAP",
            }
        ],
        "spot_positions": [
            {
                "symbol": "ETH/USDT",
                "side": "long",
                "size": 2.0,
                "entry_price": 2000.0,
                "market_type": "spot",
                "inst_id": "ETH-USDT",
            }
        ],
        "warnings": ["demo"],
    }
    payload = routes._build_positions_payload(snapshot, 12345.678)

    assert payload["count"] == 2
    assert payload["positions"] is payload["items"]
    btc = next(x for x in payload["positions"] if x["symbol"] == "BTC/USDT")
    assert btc["amount"] == 0.5
    assert btc["value_usd"] == 30000.0
    assert btc["market_type"] == "swap"
    eth = next(x for x in payload["positions"] if x["symbol"] == "ETH/USDT")
    assert eth["amount"] == 2.0
    assert eth["value_usd"] == 4000.0
    assert eth["market_type"] == "spot"
    assert payload["total_equity"] == "12345.68"
    assert payload["warnings"] == ["demo"]


def test_build_payload_filters_zero_size_and_zero_entry_value():
    snapshot = {
        "swap_positions": [
            {"symbol": "BTC/USDT", "side": "long", "size": 0.0, "entry_price": 60000.0},
            {"symbol": "ETH/USDT", "side": "short", "size": 1.0, "entry_price": 0.0},
        ],
        "spot_positions": [],
    }
    payload = routes._build_positions_payload(snapshot, None)

    assert payload["count"] == 1
    eth = payload["positions"][0]
    assert eth["symbol"] == "ETH/USDT"
    assert eth["value_usd"] == 0.0
    assert payload["total_equity"] is None


def test_build_payload_excludes_usdt_cash_leg():
    snapshot = {
        "swap_positions": [],
        "spot_positions": [
            {"symbol": "BTC/USDT", "side": "long", "size": 1.0, "entry_price": 77000.0},
            {"symbol": "USDT", "side": "long", "size": 4226.0, "entry_price": 0.0, "inst_id": "USDT"},
        ],
    }
    payload = routes._build_positions_payload(snapshot, 91356.08)
    assert payload["count"] == 1
    assert payload["positions"][0]["symbol"] == "BTC/USDT"


def test_build_payload_empty_snapshot():
    payload = routes._build_positions_payload(None, None)
    assert payload["positions"] == []
    assert payload["items"] == []
    assert payload["count"] == 0
    assert payload["total_equity"] is None
    assert payload["warnings"] == []


# ----------------------------------------------------------------- route view


def _run_view(app):
    return inspect.unwrap(routes.get_positions)()


def test_positions_route_uses_live_snapshot_chain(app, monkeypatch):
    monkeypatch.setattr(
        connection,
        "list_saved_credentials",
        lambda uid: [{"id": 7, "exchange_id": "okx"}],
    )
    monkeypatch.setattr(
        account_snapshot,
        "fetch_account_snapshot",
        lambda *, user_id, credential_id: {
            "swap_positions": [
                {
                    "symbol": "BTC/USDT",
                    "side": "long",
                    "size": 0.5,
                    "entry_price": 60000.0,
                    "market_type": "swap",
                    "inst_id": "BTC-USDT-SWAP",
                }
            ],
            "spot_positions": [],
            "warnings": [],
        },
    )
    monkeypatch.setattr(connection, "fetch_account_equity", lambda uid, **kw: 9999.0)

    with app.test_request_context("/api/account/positions"):
        g.user_id = 1
        resp = _run_view(app)

    body = resp.get_json()
    assert resp.status_code == 200
    assert body["code"] == 1
    assert body["success"] is True
    data = body["data"]
    assert data["count"] == 1
    assert data["positions"][0]["symbol"] == "BTC/USDT"
    assert data["total_equity"] == "9999.00"


def test_positions_route_no_credential_returns_empty(app, monkeypatch):
    monkeypatch.setattr(connection, "list_saved_credentials", lambda uid: [])
    called = {"snapshot": False}

    def _snapshot(**kw):
        called["snapshot"] = True
        return {}

    monkeypatch.setattr(account_snapshot, "fetch_account_snapshot", _snapshot)
    monkeypatch.setattr(connection, "fetch_account_equity", lambda uid, **kw: None)

    with app.test_request_context("/api/account/positions"):
        g.user_id = 1
        resp = _run_view(app)

    body = resp.get_json()
    assert resp.status_code == 200
    assert body["data"]["positions"] == []
    assert body["data"]["total_equity"] is None
    assert called["snapshot"] is False


def test_positions_route_swallows_chain_exception(app, monkeypatch):
    def _raise(uid):
        raise RuntimeError("private database detail")

    monkeypatch.setattr(connection, "list_saved_credentials", _raise)

    with app.test_request_context("/api/account/positions"):
        g.user_id = 1
        resp = _run_view(app)

    body = resp.get_json()
    assert resp.status_code == 200
    assert body["code"] == 1
    assert body["data"]["positions"] == []
    assert "private database detail" not in str(body)
