# -*- coding: utf-8 -*-
"""趋势突破策略单测。

覆盖：历史不足 / 上破做多 / 下破做空 / 因果性（重复调用一致 + 拒绝未来 bar）
/ 通道内无信号 / Donchian 通道排除当前 bar / 慢均线过滤逆势突破。
"""
from __future__ import annotations

import _bt_helpers as H
import pytest

from core.strategies.trend_breakout import TrendBreakoutStrategy


def _bars(closes, spread: float = 0.2):
    return H.make_bars(list(closes), spread=spread)


def _up_breakout_bars():
    """55 根单调上行（1700→1808）+ 最后一根收 1812 突破前 20 根通道。"""
    closes = [1700.0 + 2.0 * k for k in range(55)] + [1812.0]
    return _bars(closes)


def _down_breakout_bars():
    """55 根单调下行（1900→1792）+ 最后一根收 1788 跌破前 20 根通道。"""
    closes = [1900.0 - 2.0 * k for k in range(55)] + [1788.0]
    return _bars(closes)


def test_insufficient_history_returns_none():
    strat = TrendBreakoutStrategy()
    bars10 = _bars([1800.0] * 10)
    assert strat.on_bar_close(bars10, bars10[-1]) is None
    # 默认 min_history = max(entry_period+2, sma_period, atr_period+1) = 50
    bars49 = _bars([1800.0] * 49)
    assert strat.on_bar_close(bars49, bars49[-1]) is None
    assert strat._min_history == 50


def test_upward_breakout_returns_long_with_atr_based_entry_dist():
    strat = TrendBreakoutStrategy()
    bars = _up_breakout_bars()
    sig = strat.on_bar_close(bars, bars[-1])
    assert sig is not None
    assert sig.direction == +1
    assert sig.expert == "trend_breakout"
    assert sig.meta_p is None
    assert sig.l1_in_zone is True
    assert sig.regime_weights == {"trend": 1.0, "mr": 0.0, "range": 0.0}
    assert sig.price_ref == pytest.approx(1812.0)
    assert sig.bar_ts_utc == bars[-1].ts_utc
    assert sig.atr0 > 0.0
    assert sig.entry_dist == pytest.approx(2.0 * sig.atr0)
    assert sig.signal_id == (
        f"XAUUSD_{bars[-1].ts_utc.isoformat()}_trend_breakout_1")


def test_downward_breakout_returns_short():
    strat = TrendBreakoutStrategy()
    bars = _down_breakout_bars()
    sig = strat.on_bar_close(bars, bars[-1])
    assert sig is not None
    assert sig.direction == -1
    assert sig.atr0 > 0.0
    assert sig.entry_dist == pytest.approx(2.0 * sig.atr0)
    assert sig.signal_id.endswith("_trend_breakout_-1")


def test_signal_is_deterministic_given_same_history():
    """因果性：同一已收盘 history 重复调用必须给出完全一致的信号。"""
    strat = TrendBreakoutStrategy()
    bars = _up_breakout_bars()
    sig1 = strat.on_bar_close(bars, bars[-1])
    sig2 = strat.on_bar_close(list(bars), bars[-1])   # 不同 list 对象、同内容
    assert sig1 is not None
    assert sig2 is not None
    assert (sig1.signal_id, sig1.bar_ts_utc, sig1.direction, sig1.price_ref,
            sig1.atr0, sig1.entry_dist, sig1.meta_p) == (
        sig2.signal_id, sig2.bar_ts_utc, sig2.direction, sig2.price_ref,
        sig2.atr0, sig2.entry_dist, sig2.meta_p)


def test_history_containing_future_bar_is_rejected():
    """因果性：history 末元素不是当前 bar（含未来 bar）时必须显式失败。"""
    strat = TrendBreakoutStrategy()
    bars = _up_breakout_bars()
    future = H.make_bar(200, open_=1812.0, high=1999.0, low=1700.0, close=1850.0)
    with pytest.raises(ValueError):
        strat.on_bar_close(bars + [future], bars[-1])


def test_price_inside_channel_returns_none():
    """无信号区间：价格在通道内（震荡）时不做突破。"""
    strat = TrendBreakoutStrategy()
    closes = [1800.0 + (0.5 if k % 2 == 0 else -0.5) for k in range(60)]
    bars = _bars(closes)
    assert strat.on_bar_close(bars, bars[-1]) is None


def test_donchian_channel_excludes_current_bar():
    """通道必须只含前 N 根：当前 bar 自身 high(1810) 不得计入通道。

    若把当前 bar 混进通道，hh=1810，close=1805 永远不可能 > hh，信号消失。
    """
    strat = TrendBreakoutStrategy()
    bars = _bars([1800.0] * 55)
    bars.append(H.make_bar(55, open_=1800.0, high=1810.0,
                           low=1799.9, close=1805.0))
    sig = strat.on_bar_close(bars, bars[-1])
    assert sig is not None
    assert sig.direction == +1


def test_slow_sma_filters_counter_trend_breakout():
    """慢均线过滤：下跌途中上破通道但 close < SMA50 时不发多单。

    正对照：把 sma_period 收到 5，同一根 bar 会发出多单 —— 证明突破本身存在，
    是 SMA50 趋势过滤（而不是通道条件）拒掉了它。
    """
    bars = _bars([1900.0 - 1.0 * k for k in range(60)] + [1862.0])
    strat = TrendBreakoutStrategy()
    assert strat.on_bar_close(bars, bars[-1]) is None

    control = TrendBreakoutStrategy(sma_period=5)
    sig = control.on_bar_close(bars, bars[-1])
    assert sig is not None
    assert sig.direction == +1
