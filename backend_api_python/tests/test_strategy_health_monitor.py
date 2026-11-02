# -*- coding: utf-8 -*-
"""Tests for strategy health monitor (lifecycle auto-retire wiring)."""

from app.services.strategy_health_monitor import (
    build_strategy_performance_from_rows,
    run_strategy_health_check_once,
)
from app.services.strategy_lifecycle import HealthStatus, evaluate_strategy_health


def _trade(tid: int, ttype: str, profit, *, amount: float = 1.0):
    """qd_strategy_trades-like close row. profit=None => open/add event."""
    return {
        "id": tid,
        "type": ttype,
        "trade_type": ttype,
        "symbol": "BTC-USDT-SWAP",
        "symbol_canonical": "BTC-USDT-SWAP",
        "amount": amount,
        "profit": profit,
        "commission": 0.0,
        "commission_quote": 0.0,
        "created_at": 1_700_000_000 + tid,
        "strategy_id": 1,
    }


def _strategy(sid: int = 1, capital: float = 10_000.0):
    return {"id": sid, "strategy_name": "test-strat", "initial_capital": capital, "user_id": 1}


def _deep_drawdown_trades(n_wins: int = 30, win: float = 100.0, n_losses: int = 30, loss: float = -250.0):
    """Cumulative curve peaks then drops >20% from peak -> RED by drawdown."""
    trades = []
    tid = 1
    for _ in range(n_wins):
        trades.append(_trade(tid, "close_long", win))
        tid += 1
    for _ in range(n_losses):
        trades.append(_trade(tid, "close_long", loss))
        tid += 1
    return trades


def test_deep_drawdown_evaluates_red():
    perf = build_strategy_performance_from_rows(
        _strategy(), _deep_drawdown_trades()
    )
    decision = evaluate_strategy_health(perf, baseline_perf=None)
    assert decision.status == HealthStatus.RED
    assert decision.position_adjustment == 0.0
    assert "清仓" in decision.suggested_action
    assert perf.max_drawdown > 0.20


def test_ten_loss_streak_is_yellow_without_deep_drawdown():
    trades = [_trade(i + 1, "close_long", -10.0) for i in range(10)]
    perf = build_strategy_performance_from_rows(_strategy(), trades)
    decision = evaluate_strategy_health(perf, baseline_perf=None)
    # 连亏10 => red_score=2；无深回撤 => 不到 RED，落入 YELLOW（red_score>=1）
    assert perf.loss_streak == 10
    assert decision.status == HealthStatus.YELLOW


def test_small_sample_profitable_is_green():
    trades = [_trade(i + 1, "close_long", 50.0) for i in range(5)]
    perf = build_strategy_performance_from_rows(_strategy(), trades)
    decision = evaluate_strategy_health(perf, baseline_perf=None)
    assert decision.status == HealthStatus.GREEN
    assert perf.trades_count == 5
    assert perf.win_rate == 1.0


def test_open_rows_do_not_count_toward_performance():
    trades = [
        _trade(1, "open_long", None),
        _trade(2, "close_long", 30.0),
        _trade(3, "add_long", None),
    ]
    perf = build_strategy_performance_from_rows(_strategy(), trades)
    assert perf.trades_count == 1
    assert perf.total_return > 0


def test_run_once_retires_red_strategy(monkeypatch):
    called = {}

    def fake_live():
        return [_strategy()]

    def fake_trades(sid):
        return _deep_drawdown_trades()

    def fake_retire(sid, decision, user_id=None):
        called["sid"] = sid
        called["status"] = decision.status
        return {"strategy_id": sid, "status": "retired", "close_ok": True, "close_detail": ""}

    monkeypatch.setattr("app.services.strategy_health_monitor.fetch_live_strategies", fake_live)
    monkeypatch.setattr("app.services.strategy_health_monitor.fetch_strategy_trades", fake_trades)
    monkeypatch.setattr("app.services.strategy_health_monitor.retire_strategy", fake_retire)

    summary = run_strategy_health_check_once()
    assert summary["checked"] == 1
    assert summary["red"] == 1
    assert summary["retired"][0]["strategy_id"] == 1
    assert called["sid"] == 1
    assert called["status"] == HealthStatus.RED
