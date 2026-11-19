#!/usr/bin/env python3
"""Simulated-account trading smoke for stored exchange credentials.

This runner exists so live-environment smoke can be replaced by a demo/testnet
account. It refuses to run against a live credential at all: every step, including
read-only ones, is gated on ``environment in {demo, testnet}``.

Examples:
  python scripts/demo_trading_smoke.py --credential-id 2 --market spot --symbol BTC/USDT
  DEMO_SMOKE_ALLOW_ORDERS=1 python scripts/demo_trading_smoke.py \
      --credential-id 2 --allow-orders --limit-price 50000 --limit-quantity 0.0001
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.grid.exchange_orders import (  # noqa: E402
    cancel_grid_order,
    place_grid_limit_order,
    query_grid_order_fill,
)
from app.services.live_trading.base import LiveTradingError  # noqa: E402
from app.services.live_trading.factory import create_client, exchange_trading_environment  # noqa: E402
from app.services.live_trading.position_query import query_exchange_position_size  # noqa: E402
from app.services.live_trading.spot_wallet_snapshot import list_spot_wallet_positions  # noqa: E402

SECRET_KEYS = ("api_key", "apiKey", "secret_key", "secret", "passphrase", "password")
SIMULATED_ENVIRONMENTS = ("demo", "testnet")


def mask_secret(value: Any) -> str:
    """Never echo a secret: keep at most 2 leading characters plus its length."""
    s = str(value or "")
    if not s:
        return ""
    if len(s) <= 4:
        return "***"
    return f"{s[:2]}***len{len(s)}"


def mask_config(config: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(config or {})
    for key in SECRET_KEYS:
        if out.get(key):
            out[key] = mask_secret(out.get(key))
    return out


def require_simulated_credential(config: Dict[str, Any]) -> str:
    """Fail closed unless the credential is a simulated one.

    A live credential must never reach this runner: the whole point is that demo
    replaces live smoke, not that live keys get exercised under a demo flag.
    """
    environment = exchange_trading_environment(config)
    if environment not in SIMULATED_ENVIRONMENTS:
        raise LiveTradingError(
            f"DEMO_SMOKE_REQUIRES_SIMULATED_CREDENTIAL: credential environment is {environment!r}, "
            f"allowed are {SIMULATED_ENVIRONMENTS}"
        )
    return environment


def order_notional_ok(price: float, quantity: float, max_usdt: float) -> Tuple[bool, str]:
    qty = float(quantity or 0.0)
    px = float(price or 0.0)
    if qty <= 0 or px <= 0:
        return False, "limit_price and limit_quantity are required"
    notional = qty * px
    if notional > float(max_usdt or 0.0):
        return False, f"notional {notional:.8f} > max_usdt {float(max_usdt or 0.0):.8f}"
    return True, f"notional={notional:.8f}"


def demo_header(client: Any) -> Optional[str]:
    """Return the simulated-trading header value the client will send, if any."""
    headers_fn = getattr(client, "_headers", None)
    if not callable(headers_fn):
        return None
    try:
        headers = headers_fn(str(int(time.time() * 1000)), "probe")
    except Exception as exc:  # pragma: no cover - adapter specific
        raise LiveTradingError(f"DEMO_SMOKE_HEADER_PROBE_FAILED: {type(exc).__name__}: {exc}") from exc
    if not isinstance(headers, dict):
        return None
    for key, value in headers.items():
        if str(key).lower() in ("x-simulated-trading", "paptrading"):
            return str(value)
    return None


def pending_orders(client: Any, market_type: str) -> Optional[int]:
    signed = getattr(client, "_signed_request", None)
    if not callable(signed):
        return None
    inst_type = "SPOT" if market_type == "spot" else "SWAP"
    raw = signed("GET", "/api/v5/trade/orders-pending", params={"instType": inst_type})
    if not isinstance(raw, dict) or raw.get("code") not in ("0", 0):
        raise LiveTradingError(f"DEMO_SMOKE_PENDING_ORDERS_UNREADABLE: {raw}")
    return len(raw.get("data") or [])


def load_dotenv(path: Path) -> None:
    """Populate missing environment variables from .env without overriding the process env."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, val = s.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def load_credential_config(credential_id: int, database_url: str) -> Dict[str, Any]:
    import psycopg2

    from app.utils.credential_crypto import decrypt_credential_blob

    if not database_url:
        raise LiveTradingError(
            "DEMO_SMOKE_DATABASE_URL_MISSING: run inside the backend container "
            "(DATABASE_URL host is the compose service name) or export DATABASE_URL"
        )
    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor() as cur:
            cur.execute("select encrypted_config from qd_exchange_credentials where id=%s", (credential_id,))
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        raise LiveTradingError(f"DEMO_SMOKE_CREDENTIAL_NOT_FOUND: id={credential_id}")
    return json.loads(decrypt_credential_blob(row[0]))


def run_steps(
    config: Dict[str, Any],
    *,
    market_type: str,
    symbol: str,
    limit_price: float,
    limit_quantity: float,
    max_usdt: float,
    allow_orders: bool,
) -> List[Dict[str, Any]]:
    steps: List[Dict[str, Any]] = []

    def record(name: str, status: str, detail: str) -> None:
        steps.append({"name": name, "status": status, "detail": detail})

    environment = require_simulated_credential(config)
    record("credential_environment", "PASS", f"environment={environment}")

    client = create_client(config, market_type=market_type)
    record("create_client", "PASS", f"{type(client).__name__} {mask_config(config)}")

    header = demo_header(client)
    record(
        "simulated_header",
        "PASS" if header in ("1", "true", "True") else "FAIL",
        f"value={header}",
    )

    ticker = client.get_ticker(symbol=symbol)
    last = ticker.get("last") if isinstance(ticker, dict) else None
    record("ticker", "PASS" if last else "WARN", f"last={last}")

    if market_type == "spot":
        rows = list_spot_wallet_positions(client)
        record("spot_wallet", "PASS", f"rows={len(rows)}")
    else:
        for side in ("long", "short"):
            size = query_exchange_position_size(
                client=client,
                symbol=symbol,
                pos_side=side,
                market_type=market_type,
                exchange_config=config,
            )
            record(f"position_{side}", "PASS", f"size={size}")

    if not allow_orders:
        record("limit_roundtrip", "SKIP", "set --allow-orders and DEMO_SMOKE_ALLOW_ORDERS=1")
    else:
        ok, reason = order_notional_ok(limit_price, limit_quantity, max_usdt)
        if not ok:
            record("limit_roundtrip", "FAIL", f"order rejected by local guard: {reason}")
        else:
            client_order_id = f"dsmoke{int(time.time()) % 100000000}"
            order_id = ""
            cancelled = False
            try:
                placed = place_grid_limit_order(
                    client,
                    symbol=symbol,
                    side="buy",
                    quantity=limit_quantity,
                    price=limit_price,
                    market_type=market_type,
                    exchange_config=config,
                    pos_side="long",
                    reduce_only=False,
                    client_order_id=client_order_id,
                    leverage=1.0,
                    margin_mode="cross",
                    post_only=True,
                )
                order_id = str(getattr(placed, "exchange_order_id", "") or "")
                filled, avg, status = query_grid_order_fill(
                    client,
                    symbol=symbol,
                    market_type=market_type,
                    exchange_order_id=order_id,
                    client_order_id=client_order_id,
                    exchange_config=config,
                )
                cancel_grid_order(
                    client,
                    symbol=symbol,
                    market_type=market_type,
                    exchange_order_id=order_id,
                    client_order_id=client_order_id,
                    exchange_config=config,
                )
                cancelled = True
                record(
                    "limit_roundtrip",
                    "PASS",
                    f"{reason} order={order_id or client_order_id} status={status} filled={filled} avg={avg}",
                )
            finally:
                if order_id and not cancelled:
                    try:
                        cancel_grid_order(
                            client,
                            symbol=symbol,
                            market_type=market_type,
                            exchange_order_id=order_id,
                            client_order_id=client_order_id,
                            exchange_config=config,
                        )
                        record("cleanup_cancel", "PASS", "cancelled after an error in the happy path")
                    except Exception as exc:
                        record("cleanup_cancel", "WARN", f"{type(exc).__name__}: {exc}")

    leftovers = pending_orders(client, market_type)
    if leftovers is None:
        record("pending_orders", "SKIP", "adapter exposes no pending-order reader")
    else:
        record("pending_orders", "PASS" if leftovers == 0 else "FAIL", f"open={leftovers}")

    return steps


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run a demo/testnet trading smoke for a stored credential")
    parser.add_argument("--credential-id", type=int, required=True, help="qd_exchange_credentials id")
    parser.add_argument("--market", default="spot", choices=["spot", "swap"])
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--allow-orders", action="store_true", help="Enable post-only limit place/query/cancel")
    parser.add_argument("--limit-price", type=float, default=0.0)
    parser.add_argument("--limit-quantity", type=float, default=0.0)
    parser.add_argument("--max-usdt", type=float, default=5.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    allow_orders = bool(args.allow_orders and str(os.getenv("DEMO_SMOKE_ALLOW_ORDERS", "")).strip().lower() in ("1", "true", "yes", "on"))

    try:
        load_dotenv(ROOT / ".env")
        config = load_credential_config(args.credential_id, os.getenv("DATABASE_URL", ""))
    except Exception as exc:
        print(f"credential error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    try:
        steps = run_steps(
            config,
            market_type=args.market,
            symbol=args.symbol,
            limit_price=args.limit_price,
            limit_quantity=args.limit_quantity,
            max_usdt=args.max_usdt,
            allow_orders=allow_orders,
        )
    except LiveTradingError as exc:
        print(f"smoke refused: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({"credential_id": args.credential_id, "steps": steps}, ensure_ascii=False, indent=2))
    else:
        for step in steps:
            print(f"{step['status']:4} {step['name']:24} {step['detail']}")
    return 1 if any(s["status"] == "FAIL" for s in steps) else 0


if __name__ == "__main__":
    raise SystemExit(main())
