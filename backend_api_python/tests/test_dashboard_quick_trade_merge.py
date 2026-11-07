"""Offline unit tests for the quick-trade / strategy-trade list merge.

Contract (option A, list-only merge):
- Quick fills render in the dashboard trade list, tagged "快捷交易".
- Quick fills carry no matched/realised P&L, so the performance stats
  (win-rate, profit-factor, realised PnL) keep counting strategy closes only.

Requires backend dependencies to be importable — run in the backend container
or a populated venv (the host interpreter may lack flask/ccxt/numpy).
"""
from app.routes.dashboard import _build_quick_trade_row, _compute_performance_stats


def test_quick_trade_row_maps_to_recent_trade_shape_without_pnl():
    row = _build_quick_trade_row(
        {
            "id": 2,
            "exchange_id": "okx",
            "symbol": "BTC/USDT",
            "side": "sell",
            "market_type": "spot",
            "filled_amount": 0.0001319,
            "avg_fill_price": 75785.3,
            "amount": 0.0001319,
            "price": 75785.3,
            "commission": 0.00999608107,
            "commission_quote": 0.00999608107,
            "source": "manual",
            "created_at": 1700000001,
        }
    )

    assert row["symbol"] == "BTC/USDT"
    assert row["type"] == "sell"
    assert row["side"] == "sell"
    assert row["amount"] == 0.0001319
    assert row["price"] == 75785.3
    assert row["strategy_name"] == "快捷交易"
    assert row["source"] == "manual"
    # Isolation invariant: no realised P&L on a quick fill.
    assert row["profit"] is None
    assert row["net_pnl"] is None


def test_performance_stats_exclude_quick_fills():
    strategy_close = {
        "profit": 10.0,
        "created_at": 1700000000,
        "commission": 0.0,
        "commission_quote": None,
    }
    quick_buy = _build_quick_trade_row(
        {"side": "buy", "symbol": "BTC/USDT", "filled_amount": 0.0001319,
         "avg_fill_price": 75810.0, "created_at": 1700000002}
    )
    quick_sell = _build_quick_trade_row(
        {"side": "sell", "symbol": "BTC/USDT", "filled_amount": 0.0001319,
         "avg_fill_price": 75785.3, "created_at": 1700000003}
    )

    stats = _compute_performance_stats(
        [strategy_close, quick_buy, quick_sell], initial_capital=5000.0
    )

    # Only the strategy close counts toward trade count / win-rate / PnL.
    assert stats["total_trades"] == 1
    assert stats["winning_trades"] == 1
    assert stats["losing_trades"] == 0
    assert stats["win_rate"] == 100.0
    assert stats["total_profit"] == 10.0
