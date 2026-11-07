"""Offline unit tests for dashboard performance Sharpe statistics.

The Sharpe here is computed on the per-trade net P&L series (not annualized):
mean / population std. With fewer than two trades, or zero variance, it must
be ``None`` so the frontend renders "--" instead of a placeholder number.

These tests require the backend dependencies to be importable — run them in
the backend container or a populated venv (the host interpreter may lack
flask/ccxt).
"""
from app.routes.dashboard import _compute_performance_stats


def _trade(profit: float, ts: int = 1700000000) -> dict:
    return {
        "profit": profit,
        "created_at": ts,
        "commission": 0,
        "commission_quote": None,
    }


def test_empty_trades_report_null_sharpe_and_zero_counts():
    stats = _compute_performance_stats([], initial_capital=5000.0)

    assert stats["total_trades"] == 0
    assert stats["win_rate"] == 0.0
    assert stats["sharpe"] is None


def test_single_trade_has_insufficient_sample_for_sharpe():
    stats = _compute_performance_stats([_trade(10.0)], initial_capital=5000.0)

    assert stats["total_trades"] == 1
    assert stats["sharpe"] is None


def test_zero_variance_series_yields_null_sharpe():
    stats = _compute_performance_stats([_trade(10.0), _trade(10.0)], initial_capital=5000.0)

    assert stats["total_trades"] == 2
    assert stats["sharpe"] is None


def test_sharpe_matches_mean_over_population_std():
    # profits = [10, -5] -> mean 2.5, std 7.5, mean/std = 0.3333 -> 0.33
    stats = _compute_performance_stats([_trade(10.0), _trade(-5.0)], initial_capital=5000.0)

    assert stats["total_trades"] == 2
    assert stats["sharpe"] == 0.33
    # Win-rate denominator excludes break-even only; one win / one loss -> 50%.
    assert stats["win_rate"] == 50.0
