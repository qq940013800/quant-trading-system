# -*- coding: utf-8 -*-
"""均值回归策略单测。

覆盖：历史不足 / 超卖做多 / 超买做空 / 布林下轨分支（关掉 RSI 触发）/
强趋势门控拒绝逆势（含正对照）/ 震荡无信号 / 信号字段 / 因果性。
"""
from __future__ import annotations

import _bt_helpers as H
import pytest

from core.strategies.mean_reversion import MeanReversionStrategy, bollinger_bands


def _wide_bars(closes, half_range: float = 3.0):
    """宽幅 bar：ATR 大、收盘位移小 —— 模拟「非强趋势」的高波动区间。"""
    bars = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i > 0 else c
        bars.append(H.make_bar(i, open_=o, high=max(o, c) + half_range,
                               low=min(o, c) - half_range, close=c))
    return bars


def _tight_bars(closes):
    """窄幅 bar：ATR 小 —— 模拟单边强趋势。"""
    return _wide_bars(closes, half_range=0.1)


def _oversold_bars():
    """45 根平盘 + 10 根温和阴跌（-0.5/根）→ RSI(14)≈0，宽幅使 ATR 大。"""
    closes = [1800.0] * 45 + [1800.0 - 0.5 * k for k in range(1, 11)]
    return _wide_bars(closes)


def _overbought_bars():
    """45 根平盘 + 10 根温和上涨（+0.5/根）→ RSI(14)≈100。"""
    closes = [1800.0] * 45 + [1800.0 + 0.5 * k for k in range(1, 11)]
    return _wide_bars(closes)


def test_insufficient_history_returns_none():
    strat = MeanReversionStrategy()
    bars30 = _wide_bars([1800.0] * 30)
    assert strat.on_bar_close(bars30, bars30[-1]) is None
    # 默认 min_history = max(rsi+1, bb, sma, atr+1) = 50
    bars49 = _wide_bars([1800.0] * 49)
    assert strat.on_bar_close(bars49, bars49[-1]) is None
    assert strat._min_history == 50


def test_oversold_returns_long():
    strat = MeanReversionStrategy()
    bars = _oversold_bars()
    sig = strat.on_bar_close(bars, bars[-1])
    assert sig is not None
    assert sig.direction == +1


def test_overbought_returns_short():
    strat = MeanReversionStrategy()
    bars = _overbought_bars()
    sig = strat.on_bar_close(bars, bars[-1])
    assert sig is not None
    assert sig.direction == -1


def test_bollinger_lower_band_triggers_long_when_rsi_disabled():
    """布林下轨分支：把 RSI 阈值设为 0/100（严格不等号下永不触发），
    只剩 close < 下轨 能产生多单，证明 OR 的另一条腿独立生效。"""
    closes = [1800.0] * 45 + [1800.0 - 1.0 * k for k in range(1, 6)]
    bars = _wide_bars(closes)
    strat = MeanReversionStrategy(rsi_oversold=0.0, rsi_overbought=100.0)
    sig = strat.on_bar_close(bars, bars[-1])
    assert sig is not None
    assert sig.direction == +1


def test_strong_trend_gate_rejects_counter_trend_short():
    """强趋势门控：单调上涨（RSI=100 超买，但价格偏离 SMA50 约 20 个 ATR）
    时不得逆势做空；放开门控后同一根 bar 会发出空单（正对照）。"""
    bars = _tight_bars([1700.0 + 1.0 * k for k in range(60)])
    strat = MeanReversionStrategy()
    assert strat.on_bar_close(bars, bars[-1]) is None

    loose = MeanReversionStrategy(trend_dist_max=100.0)
    sig = loose.on_bar_close(bars, bars[-1])
    assert sig is not None
    assert sig.direction == -1


def test_no_signal_in_balanced_chop():
    """震荡区间：RSI≈50、价格在布林带内 -> 无信号。"""
    closes = [1800.0 + (0.5 if k % 2 == 0 else -0.5) for k in range(60)]
    bars = _wide_bars(closes)
    strat = MeanReversionStrategy()
    assert strat.on_bar_close(bars, bars[-1]) is None


def test_signal_metadata_and_hold_bars():
    strat = MeanReversionStrategy()
    bars = _oversold_bars()
    sig = strat.on_bar_close(bars, bars[-1])
    assert sig is not None
    assert sig.expert == "mean_reversion"
    assert sig.regime_weights == {"trend": 0.0, "mr": 1.0, "range": 0.0}
    assert sig.meta_p is None
    assert sig.l1_in_zone is True
    assert sig.atr0 > 0.0
    assert sig.entry_dist == pytest.approx(2.0 * sig.atr0)
    assert sig.price_ref == pytest.approx(1795.0)
    assert sig.bar_ts_utc == bars[-1].ts_utc
    assert sig.signal_id == (
        f"XAUUSD_{bars[-1].ts_utc.isoformat()}_mean_reversion_1")
    # 时间止损参数必须可被引擎/测试读取（默认 24）
    assert strat.max_hold_bars == 24


def test_signal_is_deterministic_given_same_history():
    strat = MeanReversionStrategy()
    bars = _oversold_bars()
    sig1 = strat.on_bar_close(bars, bars[-1])
    sig2 = strat.on_bar_close(list(bars), bars[-1])
    assert sig1 is not None
    assert sig2 is not None
    assert (sig1.signal_id, sig1.bar_ts_utc, sig1.direction, sig1.price_ref,
            sig1.atr0, sig1.entry_dist) == (
        sig2.signal_id, sig2.bar_ts_utc, sig2.direction, sig2.price_ref,
        sig2.atr0, sig2.entry_dist)


def test_history_containing_future_bar_is_rejected():
    strat = MeanReversionStrategy()
    bars = _oversold_bars()
    future = H.make_bar(200, open_=1795.0, high=1999.0, low=1700.0, close=1850.0)
    with pytest.raises(ValueError):
        strat.on_bar_close(bars + [future], bars[-1])


def test_all_strategies_returns_default_instances():
    from core.strategies import all_strategies

    instances = all_strategies()
    names = {f"{type(s).__module__}.{type(s).__name__}" for s in instances}
    assert names == {"core.strategies.trend_breakout.TrendBreakoutStrategy",
                     "core.strategies.mean_reversion.MeanReversionStrategy"}


class TestMRGuard:
    @pytest.mark.parametrize("bad", [1, 0, -2, 2.5, True])
    def test_period_rejects_non_int_or_too_small(self, bad):
        with pytest.raises(ValueError):
            MeanReversionStrategy(rsi_period=bad)

    @pytest.mark.parametrize("bad", [float("nan"), -1.0, 101.0])
    def test_rsi_bounds_reject_nonfinite_or_out_of_range(self, bad):
        with pytest.raises(ValueError):
            MeanReversionStrategy(rsi_oversold=bad, rsi_overbought=70.0)
        with pytest.raises(ValueError):
            MeanReversionStrategy(rsi_oversold=30.0, rsi_overbought=bad)

    @pytest.mark.parametrize("bad", [float("nan"), 0.0, -1.0])
    def test_positive_mult_rejects_nonfinite_or_nonpositive(self, bad):
        with pytest.raises(ValueError):
            MeanReversionStrategy(bb_sigma=bad)
        with pytest.raises(ValueError):
            MeanReversionStrategy(trend_dist_max=bad)
        with pytest.raises(ValueError):
            MeanReversionStrategy(entry_dist_mult=bad)

    @pytest.mark.parametrize("bad", [0, -1, 1.5, True])
    def test_max_hold_bars_rejects_non_int_or_too_small(self, bad):
        with pytest.raises(ValueError):
            MeanReversionStrategy(max_hold_bars=bad)


class TestBollingerGuards:
    _closes = [10, 11, 12, 13, 14, 15, 16, 17]

    def test_valid_bands_accepted(self):
        lower, mid, upper = bollinger_bands(self._closes, period=5, sigma=2.0)
        assert lower <= mid <= upper

    @pytest.mark.parametrize("bad", [1, 0, -2, 2.5, True])
    def test_period_must_be_int_ge_2(self, bad):
        with pytest.raises(ValueError):
            bollinger_bands(self._closes, period=bad)

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), 0.0, -1.0])
    def test_sigma_must_be_finite_positive(self, bad):
        with pytest.raises(ValueError):
            bollinger_bands(self._closes, sigma=bad)
