"""Price→base-qty conversion fallback safety for quick-trade.

A missing/unreachable ticker must yield a zero base qty (rejected downstream
by the size guard), never the raw USDT amount mistaken for a base quantity.
"""

from app.routes.quick_trade import _convert_usdt_to_base_qty


class _TickerClient:
    def __init__(self, ticker=None, raise_on_ticker=False):
        self._ticker = ticker
        self._raise = raise_on_ticker

    def get_ticker(self, symbol=""):
        if self._raise:
            raise RuntimeError("ticker unreachable")
        return self._ticker


def test_limit_price_takes_precedence_over_ticker():
    client = _TickerClient({"last": 50000.0})
    qty = _convert_usdt_to_base_qty(client, "BTC-USDT", 100.0, "spot", limit_price=100.0)
    assert qty == 1.0


def test_converts_using_ticker_last_price():
    client = _TickerClient({"last": 25000.0})
    qty = _convert_usdt_to_base_qty(client, "BTC-USDT", 100.0, "spot")
    assert qty == 100.0 / 25000.0


def test_missing_price_returns_zero_not_raw_amount():
    client = _TickerClient({})
    qty = _convert_usdt_to_base_qty(client, "BTC-USDT", 100.0, "spot")
    assert qty == 0.0


def test_ticker_exception_returns_zero_not_raw_amount():
    client = _TickerClient(raise_on_ticker=True)
    qty = _convert_usdt_to_base_qty(client, "BTC-USDT", 100.0, "spot")
    assert qty == 0.0


def test_nonpositive_amount_passes_through_zero():
    client = _TickerClient({"last": 25000.0})
    assert _convert_usdt_to_base_qty(client, "BTC-USDT", 0.0, "spot") == 0.0
