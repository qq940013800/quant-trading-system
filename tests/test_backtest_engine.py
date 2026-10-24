# -*- coding: utf-8 -*-
"""test_backtest_engine.py —— 事件驱动、已收盘 bar 决策、成本生效、止损出场、拒绝落盘。"""
from __future__ import annotations

import _bt_helpers as H  # noqa: F401
import pandas as pd
import pytest

from core.backtest.costs import CostModel
from core.backtest.engine import DemoBreakoutStrategy, run_backtest


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
