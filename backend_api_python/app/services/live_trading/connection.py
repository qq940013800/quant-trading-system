# -*- coding: utf-8 -*-
"""
Unified read-only live-exchange connection module (2026-11-02).

One code path for "saved credential / strategy binding -> connection health"
that reuses the canonical chain already proven at runtime in
dashboard.py and strategy_account_routes.py:

    exchange_execution.resolve_exchange_config   (credential ref -> plain config)
    live_trading.factory.create_client           (config -> exchange client)
    client.get_balance() / ping()                (read-only private probe)

Everything here is read-only: no order placement, no config writes, no DB
writes. Secret material never leaves the module; callers only see ids, hints,
environments, latency and (for OKX) total equity.

Public API
----------
- list_saved_credentials(user_id)                -> rows (ids + hints only)
- resolve_credential_config(credential_id, uid)  -> plain config via exchange_execution
- probe_connection(cfg, markets=None)            -> health dict, never raises
- test_saved_credential(credential_id, uid)      -> fresh health dict for one credential
- test_strategy_connection(strategy_id, uid)     -> fresh health dict for a strategy binding
- connection_overview(user_id)                   -> health of saved credentials (30s TTL cache)
- fetch_account_equity(uid, credential_id=None, market_type="swap", use_cache=True)
                                                  -> float | None (OKX totalEq, best-effort)
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

from app.utils.logger import get_logger
from app.services.live_trading.base import LiveTradingError

logger = get_logger(__name__)

_OVERVIEW_CACHE_TTL_SEC = 30.0
_overview_lock = threading.Lock()
_overview_cache: Dict[str, Any] = {}  # key -> {"ts": float, "payload": Any}

# Exchanges auto-probed by connection_overview(). ibkr is intentionally
# excluded: create_client(ibkr) opens a live TWS/Gateway session per client,
# which is not appropriate for a polled overview. Use the explicit test
# endpoint for desktop brokers.
_AUTO_PROBE_EXCHANGES = {"binance", "okx", "bitget", "bybit", "gate", "htx", "alpaca"}


def list_saved_credentials(user_id: int) -> List[Dict[str, Any]]:
    """Saved exchange credentials for a user (ids + hints only, never secrets)."""
    from app.utils.db import get_db_connection

    rows: List[Dict[str, Any]] = []
    with get_db_connection() as db:
        cur = db.cursor()
        cur.execute(
            """
            SELECT id, user_id, name, exchange_id, api_key_hint, created_at, updated_at
            FROM qd_exchange_credentials
            WHERE user_id = %s
            ORDER BY id DESC
            LIMIT 50
            """,
            (int(user_id),),
        )
        rows = cur.fetchall() or []
        cur.close()
    out: List[Dict[str, Any]] = []
    for r in rows:
        item = dict(r or {})
        item.pop("encrypted_config", None)  # defensive: never expose secrets
        out.append(item)
    return out


def resolve_credential_config(credential_id: int, user_id: int = 1) -> Dict[str, Any]:
    """Resolve a saved credential into a plain exchange config (reuses exchange_execution)."""
    from app.services.exchange_execution import resolve_exchange_config

    cfg = resolve_exchange_config({"credential_id": int(credential_id)}, user_id=int(user_id))
    if not isinstance(cfg, dict) or not cfg:
        raise ValueError("CREDENTIAL_CONFIG_EMPTY")
    if not str(cfg.get("exchange_id") or cfg.get("exchangeId") or "").strip():
        raise ValueError("CREDENTIAL_CONFIG_MISSING_EXCHANGE_ID")
    return cfg


def _market_types_for_scope(cfg: Dict[str, Any]) -> List[str]:
    """Markets to probe for a config: both -> spot+swap, otherwise single scope."""
    from app.services.live_trading.factory import exchange_market_scope

    scope = exchange_market_scope(cfg)
    if scope == "spot":
        return ["spot"]
    if scope == "swap":
        return ["swap"]
    return ["spot", "swap"]


def _probe_one(client: Any, market_type: str) -> Dict[str, Any]:
    """
    Read-only probe of a live client; captures latency and (OKX) total equity.
    Raises LiveTradingError on failure — callers surface it via the health dict.
    """
    started = time.perf_counter()
    equity: Optional[float] = None

    balance = None
    if hasattr(client, "get_balance"):
        balance = client.get_balance()
    elif hasattr(client, "ping"):
        ok = client.ping()
        if not ok:
            raise LiveTradingError("PING_FAILED")
    elif hasattr(client, "get_account"):
        client.get_account()
    elif hasattr(client, "get_wallet_balance"):
        client.get_wallet_balance()
    elif hasattr(client, "get_assets"):
        client.get_assets()
    else:
        raise LiveTradingError("PRIVATE_ACCOUNT_PROBE_UNAVAILABLE")

    # OKX balance payload: {"code": ..., "data": [{"totalEq": "..."}]}
    if isinstance(balance, dict):
        arr = balance.get("data") or []
        if arr and isinstance(arr[0], dict):
            raw_eq = arr[0].get("totalEq")
            if raw_eq not in (None, ""):
                try:
                    equity = float(raw_eq)
                except (TypeError, ValueError):
                    equity = None

    out: Dict[str, Any] = {
        "tested_markets": [market_type],
        "latency_ms": round((time.perf_counter() - started) * 1000.0, 1),
    }
    if equity is not None:
        out["equity"] = equity
    return out


def probe_connection(cfg: Dict[str, Any], markets: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Build a client through the canonical factory and run read-only probes.
    Returns a health dict — never raises.
    """
    from app.services.live_trading.factory import (
        create_client,
        exchange_trading_environment,
        exchange_market_scope,
    )

    exchange_id = str(cfg.get("exchange_id") or cfg.get("exchangeId") or "").strip().lower()
    environment = exchange_trading_environment(cfg, exchange_id)
    market_scope = exchange_market_scope(cfg)
    result: Dict[str, Any] = {
        "ok": False,
        "exchange_id": exchange_id,
        "environment": environment,
        "market_scope": market_scope,
        "tested_markets": [],
        "latency_ms": None,
    }
    try:
        mts = markets or _market_types_for_scope(cfg)
        probed: List[str] = []
        last_latency: Optional[float] = None
        equity: Optional[float] = None
        for mt in mts:
            client = create_client(cfg, market_type=mt)
            extra = _probe_one(client, mt)
            probed.extend(extra.get("tested_markets") or [])
            if extra.get("equity") is not None:
                equity = extra["equity"]
            if extra.get("latency_ms") is not None:
                last_latency = extra["latency_ms"]
        result.update(
            {
                "ok": True,
                "tested_markets": probed,
                "latency_ms": last_latency,
            }
        )
        if equity is not None:
            result["equity"] = equity
    except Exception as exc:
        result["error"] = str(exc) or exc.__class__.__name__
        logger.debug("probe_connection(%s) failed: %s", exchange_id, exc)
    return result


def test_saved_credential(
    credential_id: int, user_id: int = 1, market_type: Optional[str] = None
) -> Dict[str, Any]:
    """Read-only connection test for a saved credential (always fresh, no cache)."""
    cfg = resolve_credential_config(int(credential_id), user_id=int(user_id))
    markets = [str(market_type).strip().lower()] if market_type else None
    result = probe_connection(cfg, markets=markets)
    result["credential_id"] = int(credential_id)
    return result


def test_strategy_connection(strategy_id: int, user_id: int = 1) -> Dict[str, Any]:
    """
    Read-only: resolve a strategy's exchange binding (row exchange_config,
    credential ref resolved through exchange_execution) and probe it.
    """
    from app.services.exchange_execution import load_strategy_configs, resolve_exchange_config

    sid = int(strategy_id)
    scfg = load_strategy_configs(sid) or {}
    if not scfg.get("exchange_config"):
        return {"ok": False, "error": "STRATEGY_HAS_NO_EXCHANGE_CONFIG", "strategy_id": sid}
    cfg = resolve_exchange_config(
        scfg["exchange_config"], user_id=int(scfg.get("user_id") or user_id)
    )
    if not str(cfg.get("exchange_id") or "").strip():
        return {"ok": False, "error": "STRATEGY_EXCHANGE_NOT_RESOLVED", "strategy_id": sid}
    mt = str(scfg.get("market_type") or "swap").strip().lower()
    if mt in ("futures", "future", "perp", "perpetual"):
        mt = "swap"
    result = probe_connection(cfg, markets=[mt])
    result["strategy_id"] = sid
    return result


def _cache_get(key: str) -> Any:
    with _overview_lock:
        hit = _overview_cache.get(key)
        if hit and (time.time() - float(hit["ts"])) <= _OVERVIEW_CACHE_TTL_SEC:
            return hit["payload"]
    return None


def _cache_set(key: str, payload: Any) -> None:
    with _overview_lock:
        _overview_cache[key] = {"ts": time.time(), "payload": payload}


def fetch_account_equity(
    user_id: int,
    credential_id: Optional[int] = None,
    market_type: str = "swap",
    use_cache: bool = True,
) -> Optional[float]:
    """
    Best-effort OKX total equity via the standard credential -> factory chain.

    Returns float (OKX totalEq) or None when no OKX credential exists / the
    lookup fails. Never raises: callers fall back to their library-side figure.
    Success is cached briefly so polled endpoints do not hammer OKX.
    """
    mt = str(market_type or "swap").strip().lower()
    cache_key = f"eq:{int(user_id)}:{int(credential_id or 0)}:{mt}"
    if use_cache:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

    value: Optional[float] = None
    try:
        from app.routes.strategy_account_routes import _first_okx_credential_id

        cid = credential_id or _first_okx_credential_id(int(user_id))
        if not cid:
            return None
        cfg = resolve_credential_config(int(cid), user_id=int(user_id))
        if str(cfg.get("exchange_id") or "").lower() != "okx":
            return None
        from app.services.live_trading.factory import create_client

        bal = create_client(cfg, market_type=mt).get_balance()
        arr = (bal or {}).get("data") or []
        if arr and isinstance(arr[0], dict) and arr[0].get("totalEq") is not None:
            value = float(arr[0]["totalEq"])
    except Exception as exc:
        logger.warning("fetch_account_equity skipped: %s", exc)
        return None

    if value is not None and use_cache:
        _cache_set(cache_key, value)
    return value


def connection_overview(user_id: int) -> Dict[str, Any]:
    """Health of every saved credential (read-only, cached 30s)."""
    cache_key = f"ov:{int(user_id)}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    credentials = list_saved_credentials(int(user_id))
    connections: List[Dict[str, Any]] = []
    for cred in credentials[:10]:
        cid = int(cred.get("id") or 0)
        exchange_id = str(cred.get("exchange_id") or "").strip().lower()
        entry: Dict[str, Any] = {
            "credential_id": cid,
            "name": cred.get("name") or f"Credential_{cid}",
            "exchange_id": exchange_id,
            "api_key_hint": cred.get("api_key_hint") or "",
        }
        if exchange_id not in _AUTO_PROBE_EXCHANGES:
            entry["ok"] = None
            entry["skipped"] = True
            entry["note"] = "use explicit test endpoint (desktop broker or unsupported)"
            connections.append(entry)
            continue
        try:
            entry.update(probe_connection(resolve_credential_config(cid, user_id=int(user_id))))
        except Exception as exc:
            entry["ok"] = False
            entry["error"] = str(exc) or exc.__class__.__name__
        connections.append(entry)

    payload: Dict[str, Any] = {
        "connections": connections,
        "total": len(connections),
        "ok_count": len([c for c in connections if c.get("ok") is True]),
        "checked_at": time.time(),
    }
    _cache_set(cache_key, payload)
    return payload
