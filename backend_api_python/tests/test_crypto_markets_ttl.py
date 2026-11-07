"""Offline unit tests for CryptoDataSource markets snapshot TTL refresh.

The CCXT client is mocked; no live network call is made. These tests still
require the backend dependencies (ccxt) so the module can be imported — run
them in the backend container or a populated venv.
"""
import threading
import time
from unittest.mock import MagicMock

from app.data_sources.crypto import CryptoDataSource, _markets_cache_ttl_sec


def _make_source() -> CryptoDataSource:
    source = object.__new__(CryptoDataSource)
    source.exchange = MagicMock()
    source.exchange.markets = {"BTC/USDT": {"id": "BTC/USDT"}}
    source._markets_load_lock = threading.Lock()
    source._markets_loaded = False
    source._markets_cache = None
    source._markets_loaded_at = 0.0
    return source


def test_first_load_calls_load_markets_without_force_reload():
    source = _make_source()

    assert source._ensure_markets_loaded() is True

    source.exchange.load_markets.assert_called_once_with(reload=False)
    assert source._markets_loaded is True
    assert source._markets_cache == {"BTC/USDT": {"id": "BTC/USDT"}}
    assert source._markets_loaded_at > 0.0


def test_fresh_snapshot_is_not_reloaded():
    source = _make_source()
    source._ensure_markets_loaded()
    first_calls = source.exchange.load_markets.call_count

    assert source._ensure_markets_loaded() is True

    assert source.exchange.load_markets.call_count == first_calls


def test_expired_snapshot_is_force_reloaded():
    source = _make_source()
    source._ensure_markets_loaded()
    # Age the snapshot past the TTL window.
    source._markets_loaded_at = time.time() - _markets_cache_ttl_sec() - 1.0

    assert source._ensure_markets_loaded() is True

    source.exchange.load_markets.assert_called_with(reload=True)
