# -*- coding: utf-8 -*-
"""tests/test_strategies_base.py —— 统一策略接口（Protocol/基类）单测。

覆盖：
1. 既有 TrendBreakoutStrategy / MeanReversionStrategy 对统一 Protocol 鸭子兼容
   （既存实现一字未改，仅接口形状核验）；
2. BaseStrategy schema 校验：未知参数 / 越界 / 默认值合并；
3. 因果守卫：history 不以当前已收盘 bar 结尾 → 带上下文 ValueError；
4. 同一 history 重放结果可重放（审计可复现）。
"""
from __future__ import annotations

import pytest

import _bt_helpers as H
from core.strategies import BaseStrategy, Strategy
from core.strategies.mean_reversion import MeanReversionStrategy
from core.strategies.structure_break import StructureBreakStrategy
from core.strategies.supply_demand import SupplyDemandStrategy
from core.strategies.trend_breakout import TrendBreakoutStrategy


def test_legacy_strategies_duck_compatible_with_protocol():
    """既有旧实现只要有 on_bar_close(history, bar) 即满足引擎消费契约；
    统一 Protocol 要求的 requires_features/params_schema 为新策略侧扩展点。"""
    for inst in (TrendBreakoutStrategy(), MeanReversionStrategy()):
        assert callable(inst.on_bar_close)
    # 新策略满足 runtime Protocol
    assert isinstance(StructureBreakStrategy(), Strategy)
    assert isinstance(SupplyDemandStrategy(), Strategy)
    assert isinstance(StructureBreakStrategy(), BaseStrategy)


def test_schema_defaults_and_override():
    strat = StructureBreakStrategy(k=7)
    params = strat._params
    assert params["k"] == 7                 # 构造覆写生效
    assert params["atr_n"] == 14            # 未覆写取 schema 默认
    assert params["entry_dist_mult"] == 2.0
    schema = strat.params_schema()
    assert schema["k"]["min"] == 1
    assert schema["k"]["default"] == 3


def test_unknown_param_rejected():
    with pytest.raises(ValueError) as exc:
        StructureBreakStrategy(does_not_exist=1)
    assert "unknown params" in str(exc.value)


def test_out_of_range_param_rejected():
    with pytest.raises(ValueError) as exc:
        StructureBreakStrategy(k=0)
    ctx = exc.value.args[0]
    assert "k" in ctx["param"]
    assert ">= 1" in ctx["detail"]


def test_causal_guard_rejects_future_bar():
    bars = H.make_trend_bars(n=60)
    strat = StructureBreakStrategy()
    future = H.make_bar(500, open_=2000, high=2001, low=1999, close=2000)
    with pytest.raises(ValueError) as exc:
        strat.on_bar_close(list(bars) + [future], bars[-1])
    ctx = exc.value.args[0]
    assert "no future bars" in ctx["detail"]
    assert ctx["ts_utc"] == str(bars[-1].ts_utc)


def test_causal_guard_rejects_empty_history():
    strat = StructureBreakStrategy()
    bar = H.make_bar(0, 1800, 1801, 1799, 1800)
    with pytest.raises(ValueError) as exc:
        strat.on_bar_close([], bar)
    assert "empty history" in str(exc.value.args[0]["detail"])


def test_replay_determinism():
    bars = H.make_trend_bars(n=80, seed=7)
    strat = StructureBreakStrategy()
    sig1 = strat.on_bar_close(bars, bars[-1])
    strat2 = StructureBreakStrategy()
    sig2 = strat2.on_bar_close(list(bars), bars[-1])
    if sig1 is None:
        assert sig2 is None
    else:
        assert (sig1.signal_id, sig1.bar_ts_utc, sig1.direction,
                sig1.price_ref, sig1.atr0, sig1.entry_dist) == (
            sig2.signal_id, sig2.bar_ts_utc, sig2.direction,
            sig2.price_ref, sig2.atr0, sig2.entry_dist)
