"""Offline unit tests for CryptoDataSource ticker transient-error retry.

The exchange client is mocked; no live CCXT network call is made. These tests
still require the backend dependencies (ccxt) to be installed so the module
can be imported — run them in the backend container or a populated venv.
"""
from unittest.mock import MagicMock

import pytest

from app.data_sources.crypto import CryptoDataSource


def _make_source() -> CryptoDataSource:
    """Build a source without running ``__init__`` (which constructs a real CCXT client)."""
    source = object.__new__(CryptoDataSource)
    source.exchange = MagicMock()
    return source


def test_transient_error_retried_once_then_succeeds():
    source = _make_source()
    source.exchange.fetch_ticker.side_effect = [
        Exception("Connection reset by peer"),
        {"last": 64000.0, "symbol": "BTC/USDT"},
    ]

    ticker = source._fetch_ticker_with_retry("BTC/USDT")

    assert ticker["last"] == 64000.0
    assert source.exchange.fetch_ticker.call_count == 2


def test_symbol_not_found_is_not_retried():
    source = _make_source()
    source.exchange.fetch_ticker.side_effect = Exception(
        "binance does not have market symbol FOOBAR/USDT"
    )

    with pytest.raises(Exception):
        source._fetch_ticker_with_retry("FOOBAR/USDT")

    # Symbol-not-found is a permanent classification, not a transient blip.
    assert source.exchange.fetch_ticker.call_count == 1


def test_two_transient_failures_reraise_after_two_attempts():
    source = _make_source()
    source.exchange.fetch_ticker.side_effect = Exception("503 Service Unavailable")

    with pytest.raises(Exception):
        source._fetch_ticker_with_retry("BTC/USDT")

    assert source.exchange.fetch_ticker.call_count == 2
