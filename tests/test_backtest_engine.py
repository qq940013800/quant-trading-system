# -*- coding: utf-8 -*-
"""test_backtest_engine.py —— 事件驱动、已收盘 bar 决策、成本生效、止损出场、拒绝落盘。"""
from __future__ import annotations

import _bt_helpers as H  # noqa: F401
import pandas as pd
import pytest

from core.backtest.costs import CostModel
from core.backtest.engine import (DemoBreakoutStrategy, _breakeven_candidate,
                                  _trailing_candidate, _wilder_atr,
                                  run_backtest)


def _flat_with_drop():
    prices = [1800.0] * 15 + [1790.0] + [1790.0] * 10
    return H.make_bars(prices)


class _StubLongAt:
    """在指定 bar 索引发多单，其余不发。"""

    def __init__(self, at_idx: int):
        self.at_idx = at_idx
        self.seen = []

    def on_bar_close(self, history, bar):
        self.seen.append(len(history))
        # 因果断言：history 末尾必须就是当前已收盘 bar（不允许看到未来 bar）
        assert history[-1].ts_utc == bar.ts_utc
        if len(history) - 1 == self.at_idx:
            atr0 = 0.2
            return H.Signal(
                signal_id=f"T_{bar.ts_utc.isoformat()}", bar_ts_utc=bar.ts_utc,
                expert="stub", direction=+1, price_ref=float(bar.close),
                atr0=atr0, entry_dist=2 * atr0, l1_in_zone=True,
                regime_weights={"trend": 1.0})
        return None


def _cost():
    return CostModel(base_spread=0.20, news_spread=0.60, gap_spread=1.0,
                     gap_threshold=1.0, base_slippage=0.05,
                     slippage_per_volume_frac=0.10, commission_per_lot=0.0,
                     news_minutes=15.0)


def test_signal_fills_at_next_bar_open():
    bars = _flat_with_drop()
    strat = _StubLongAt(at_idx=10)
    res = run_backtest(bars, strat, _cost(),
                       {"initial_equity": 10_000, "point_value": 100,
                        "risk_pct": 0.01, "kelly_cap": 1.0,
                        "min_lot": 0.01, "lot_step": 0.01, "heat_limit": 1,
                        "daily_loss_limit": 0.5, "trail_enable": False})
    # 信号在 bar10(收盘1800) -> bar11 open=1800 成交
    # 成本 = 半幅点差 0.10 + 滑点(基础0.05 + 0.10*手数/量)；手数=2.5, tick_vol=1000
    assert len(res.trades) >= 1
    entry = res.trades[0]["entry_price"]
    slip = 0.05 + 0.10 * (2.5 / 1000.0)
    assert entry == pytest.approx(1800.0 + 0.10 + slip, abs=1e-6)


def test_engine_only_sees_closed_bars():
    bars = _flat_with_drop()
    strat = _StubLongAt(at_idx=10)
    run_backtest(bars, strat, _cost(),
                 {"initial_equity": 10_000, "daily_loss_limit": 0.5})
    # 每次回调 history 长度递增且等于已收盘计数（末根含当前 bar）
    assert strat.seen[-1] == len(bars)


def test_cost_model_changes_outcome():
    bars = H.make_trend_bars(n=300, seed=1)
    strat = DemoBreakoutStrategy(lookback=15)
    base = {"initial_equity": 10_000, "point_value": 100, "risk_pct": 0.01,
            "kelly_cap": 1.0, "min_lot": 0.01, "lot_step": 0.01,
            "daily_loss_limit": 0.5, "trail_enable": False}
    with_cost = run_backtest(bars, strat, _cost(), dict(base)).metrics
    zero_cost = run_backtest(bars, strat, None, dict(base)).metrics
    # 成本开关必须显著改变结果（防止零成本假设旁路成本模型）
    assert with_cost["final_equity"] != zero_cost["final_equity"]


def test_news_window_rejects_and_records():
    bars = _flat_with_drop()
    news = [pd.Timestamp("2021-01-04 00:50", tz="UTC")]  # bar10 = 00:50
    strat = _StubLongAt(at_idx=10)
    res = run_backtest(bars, strat, _cost(),
                       {"initial_equity": 10_000, "daily_loss_limit": 0.5,
                        "news_window": news})
    rejects = [d for d in res.decisions if not d.accepted]
    assert rejects and rejects[0].reject_reason == "news_window"
    assert rejects[0].final_signed_lots == 0.0


def test_stop_out_trade_recorded_with_r():
    bars = _flat_with_drop()   # bar15 跳水，多头被止损
    strat = _StubLongAt(at_idx=10)
    res = run_backtest(bars, strat, _cost(),
                       {"initial_equity": 10_000, "daily_loss_limit": 0.5,
                        "trail_enable": False})
    t = res.trades[0]
    assert t["direction"] == +1
    assert t["r_multiple"] < 0          # 止损单亏损，R 为负


def test_trailing_candidate_long_short_symmetric():
    # 多头：自峰值回撤 offset×dist；空头：自谷值上抬 offset×dist（冻结 entry_dist）
    assert _trailing_candidate(102.0, +1, 1.0, 2.0) == pytest.approx(100.0)
    assert _trailing_candidate(98.0, -1, 1.0, 2.0) == pytest.approx(100.0)
    # 零偏移：候选即峰值/谷值本身
    assert _trailing_candidate(102.0, +1, 0.0, 2.0) == pytest.approx(102.0)
    assert _trailing_candidate(98.0, -1, 0.0, 2.0) == pytest.approx(98.0)


def test_trailing_lock_profit_after_uptrend_pullback():
    # 先冲高后回撤：峰值跟踪应锁定盈利出场，而不是在保本/固定 R 位被扫出
    prices = [1800.0] * 11 + [1802.0, 1804.0, 1806.0, 1806.0,
                              1805.0, 1803.0, 1801.0, 1799.0, 1799.0]
    bars = H.make_bars(prices)
    strat = _StubLongAt(at_idx=10)
    res = run_backtest(bars, strat, _cost(),
                       {"initial_equity": 10_000, "daily_loss_limit": 0.5,
                        "trail_enable": True, "trail_after_r": 1.0,
                        "trail_offset_r": 1.0})
    assert len(res.trades) == 1
    t = res.trades[0]
    assert t["direction"] == +1
    assert t["exit_price"] > t["entry_price"]
    assert t["r_multiple"] > 0


def test_breakeven_candidate_long_short_symmetric():
    # 多头保本位 entry + offset×dist；空头 entry - offset×dist（冻结 entry_dist）
    assert _breakeven_candidate(100.0, +1, 0.1, 2.0) == pytest.approx(100.2)
    assert _breakeven_candidate(100.0, -1, 0.1, 2.0) == pytest.approx(99.8)
    # 零偏移：候选即入场价本身
    assert _breakeven_candidate(100.0, +1, 0.0, 2.0) == pytest.approx(100.0)


def test_breakeven_locks_after_profit_pullback():
    # 涨过保本 R 后回落：保本止损抬升，回落以保本位附近退出，不在初始止损亏损出场
    prices = [1800.0] * 11 + [1801.0, 1801.0, 1800.5, 1799.8, 1799.8]
    bars = H.make_bars(prices)
    strat = _StubLongAt(at_idx=10)
    res = run_backtest(bars, strat, _cost(),
                       {"initial_equity": 10_000, "daily_loss_limit": 0.5,
                        "trail_enable": False, "breakeven_r": 1.0,
                        "breakeven_offset_r": 0.5})
    assert len(res.trades) == 1
    t = res.trades[0]
    assert t["direction"] == +1
    assert t["exit_price"] > t["entry_price"]
    assert t["r_multiple"] > 0


class TestEngineGuards:
    @pytest.mark.parametrize("fn", [_trailing_candidate, _breakeven_candidate])
    @pytest.mark.parametrize("kwargs", [
        {"direction": 0}, {"direction": 2}, {"direction": True},
        {"offset_r": -0.1}, {"offset_r": float("nan")},
        {"entry_dist": -1.0}, {"entry_dist": float("inf")},
    ])
    def test_candidate_guards(self, fn, kwargs):
        price_key = "peak_price" if fn is _trailing_candidate else "entry_price"
        base = {price_key: 100.0, "direction": +1,
                "offset_r": 1.0, "entry_dist": 2.0}
        base.update(kwargs)
        with pytest.raises(ValueError):
            fn(**base)

    @pytest.mark.parametrize("bad", [0, -1, 1.5, True])
    def test_wilder_atr_n_rejected(self, bad):
        with pytest.raises(ValueError):
            _wilder_atr([], n=bad)

    @pytest.mark.parametrize("kwargs", [
        {"lookback": 0}, {"lookback": -1}, {"lookback": 1.5},
        {"atr_n": 0}, {"atr_n": True},
        {"entry_dist_mult": -0.5}, {"entry_dist_mult": float("nan")},
    ])
    def test_demo_strategy_constructor_rejected(self, kwargs):
        with pytest.raises(ValueError):
            DemoBreakoutStrategy(**kwargs)

    def test_valid_constructor_accepted(self):
        s = DemoBreakoutStrategy(lookback=15, atr_n=10, entry_dist_mult=2.5)
        assert s.lookback == 15 and s.atr_n == 10
