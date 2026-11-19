from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "demo_trading_smoke.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("demo_trading_smoke", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _config(environment="demo", exchange_id="okx"):
    cfg = {
        "exchange_id": exchange_id,
        "api_key": "demo-api-key-value",
        "secret_key": "demo-secret-key-value",
        "environment": environment,
        "market_scope": "both",
    }
    if exchange_id in ("okx", "bitget"):
        cfg["passphrase"] = "demo-passphrase-value"
    return cfg


def test_require_simulated_credential_accepts_demo_and_testnet():
    mod = _load_module()
    assert mod.require_simulated_credential(_config("demo")) == "demo"
    assert mod.require_simulated_credential(_config("testnet", "gate")) == "testnet"


def test_require_simulated_credential_refuses_live():
    mod = _load_module()
    with pytest.raises(Exception) as excinfo:
        mod.require_simulated_credential(_config("live"))
    assert "DEMO_SMOKE_REQUIRES_SIMULATED_CREDENTIAL" in str(excinfo.value)


def test_run_steps_does_not_touch_a_live_credential(monkeypatch):
    mod = _load_module()
    called = []

    def fake_create(config, *, market_type):
        called.append(market_type)
        raise AssertionError("create_client must not run for a live credential")

    monkeypatch.setattr(mod, "create_client", fake_create)
    with pytest.raises(Exception) as excinfo:
        mod.run_steps(
            _config("live"),
            market_type="spot",
            symbol="BTC/USDT",
            limit_price=0.0,
            limit_quantity=0.0,
            max_usdt=5.0,
            allow_orders=False,
        )
    assert "DEMO_SMOKE_REQUIRES_SIMULATED_CREDENTIAL" in str(excinfo.value)
    assert called == []


def test_order_notional_guard_boundaries():
    mod = _load_module()
    assert mod.order_notional_ok(0.0, 0.1, 5.0)[0] is False
    assert mod.order_notional_ok(50000.0, 0.0, 5.0)[0] is False
    ok, detail = mod.order_notional_ok(50000.0, 0.0001, 5.0)
    assert ok is True and "notional=5.00000000" in detail
    ok, detail = mod.order_notional_ok(50000.0, 0.00011, 5.0)
    assert ok is False and "max_usdt" in detail


def test_mask_config_never_echoes_secret_material():
    mod = _load_module()
    original = _config("demo")
    masked = mod.mask_config(original)
    for key in ("api_key", "secret_key", "passphrase"):
        raw = original[key]
        assert masked[key] != raw
        assert raw[2:] not in masked[key]
        assert raw[-4:] not in masked[key]
        assert masked[key].startswith(f"{raw[:2]}***len")
    assert masked["environment"] == "demo"


def test_demo_header_reads_okx_simulated_flag():
    mod = _load_module()
    client = mod.create_client(_config("demo"), market_type="spot")
    assert mod.demo_header(client) == "1"


def test_demo_header_returns_none_for_adapter_without_headers():
    mod = _load_module()

    class Plain:
        pass

    assert mod.demo_header(Plain()) is None


class _FakeClient:
    def __init__(self, pending=None, ticker_last="63958.6"):
        self._pending = pending
        self._ticker_last = ticker_last

    def _headers(self, ts, sig):
        return {"x-simulated-trading": "1"}

    def get_ticker(self, symbol):
        return {"last": self._ticker_last}

    def _signed_request(self, method, path, params=None):
        if self._pending is None:
            return {"code": "0", "data": []}
        return {"code": "0", "data": [{"ordId": str(i)} for i in range(self._pending)]}


def test_run_steps_walks_read_only_path_and_skips_orders(monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod, "create_client", lambda config, *, market_type: _FakeClient())
    monkeypatch.setattr(mod, "list_spot_wallet_positions", lambda client: [{"symbol": "USDT", "size": 4156.9}])

    steps = mod.run_steps(
        _config("demo"),
        market_type="spot",
        symbol="BTC/USDT",
        limit_price=0.0,
        limit_quantity=0.0,
        max_usdt=5.0,
        allow_orders=False,
    )

    by_name = {s["name"]: s for s in steps}
    assert by_name["credential_environment"]["status"] == "PASS"
    assert by_name["simulated_header"]["status"] == "PASS"
    assert by_name["ticker"]["detail"] == "last=63958.6"
    assert by_name["spot_wallet"]["status"] == "PASS"
    assert by_name["limit_roundtrip"]["status"] == "SKIP"
    assert by_name["pending_orders"]["status"] == "PASS"


def test_run_steps_fails_when_orders_would_leave_residue(monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod, "create_client", lambda config, *, market_type: _FakeClient(pending=2))
    monkeypatch.setattr(mod, "list_spot_wallet_positions", lambda client: [])

    steps = mod.run_steps(
        _config("demo"),
        market_type="spot",
        symbol="BTC/USDT",
        limit_price=0.0,
        limit_quantity=0.0,
        max_usdt=5.0,
        allow_orders=False,
    )

    by_name = {s["name"]: s for s in steps}
    assert by_name["pending_orders"]["status"] == "FAIL"
    assert by_name["pending_orders"]["detail"] == "open=2"


def test_order_guard_rejection_is_reported_without_placing(monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod, "create_client", lambda config, *, market_type: _FakeClient())
    monkeypatch.setattr(mod, "list_spot_wallet_positions", lambda client: [])
    placed = []
    monkeypatch.setattr(mod, "place_grid_limit_order", lambda *a, **k: placed.append(k) or None)

    steps = mod.run_steps(
        _config("demo"),
        market_type="spot",
        symbol="BTC/USDT",
        limit_price=50000.0,
        limit_quantity=0.001,
        max_usdt=5.0,
        allow_orders=True,
    )

    by_name = {s["name"]: s for s in steps}
    assert by_name["limit_roundtrip"]["status"] == "FAIL"
    assert "local guard" in by_name["limit_roundtrip"]["detail"]
    assert placed == []


class _Placed:
    exchange_order_id = "4113"


def _order_kwargs(allow_orders=True):
    return dict(
        market_type="spot",
        symbol="BTC/USDT",
        limit_price=50000.0,
        limit_quantity=0.0001,
        max_usdt=5.0,
        allow_orders=allow_orders,
    )


def test_happy_path_cancels_exactly_once(monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod, "create_client", lambda config, *, market_type: _FakeClient())
    monkeypatch.setattr(mod, "list_spot_wallet_positions", lambda client: [])
    monkeypatch.setattr(mod, "place_grid_limit_order", lambda *a, **k: _Placed())
    monkeypatch.setattr(mod, "query_grid_order_fill", lambda *a, **k: (0.0, 0.0, "open"))
    cancels = []
    monkeypatch.setattr(mod, "cancel_grid_order", lambda *a, **k: cancels.append(k.get("exchange_order_id")))

    steps = mod.run_steps(_config("demo"), **_order_kwargs())

    by_name = {s["name"]: s for s in steps}
    assert by_name["limit_roundtrip"]["status"] == "PASS"
    assert cancels == ["4113"]
    assert "cleanup_cancel" not in by_name


def test_cleanup_cancel_runs_when_the_happy_path_breaks(monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod, "create_client", lambda config, *, market_type: _FakeClient())
    monkeypatch.setattr(mod, "list_spot_wallet_positions", lambda client: [])
    monkeypatch.setattr(mod, "place_grid_limit_order", lambda *a, **k: _Placed())

    def boom(*a, **k):
        raise RuntimeError("query down")

    monkeypatch.setattr(mod, "query_grid_order_fill", boom)
    cancels = []
    monkeypatch.setattr(mod, "cancel_grid_order", lambda *a, **k: cancels.append(k.get("exchange_order_id")))

    with pytest.raises(RuntimeError):
        mod.run_steps(_config("demo"), **_order_kwargs())

    assert cancels == ["4113"]
