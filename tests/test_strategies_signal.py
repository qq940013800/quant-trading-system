# -*- coding: utf-8 -*-
"""tests/test_strategies_signal.py —— StrategySignal 契约单测。

覆盖：引擎鸭子字段对齐 / direction 校验 / atr0、entry_dist 正值校验 /
tz-aware 时区校验 / strategy_version 默认值。
"""
from __future__ import annotations

import pandas as pd
import pytest

import _bt_helpers as H
from core.strategies.signal import StrategySignal


def _valid_signal(**overrides) -> StrategySignal:
    base = dict(
        signal_id="XAUUSD_2021-01-04T00:30:00+00:00_supply_demand_1",
        bar_ts_utc=pd.Timestamp("2021-01-04 00:30", tz="UTC"),
        expert="supply_demand",
        direction=1,
        price_ref=1800.0,
        atr0=2.5,
        entry_dist=5.0,
        l1_in_zone=True,
        regime_weights={"trend": 0.0, "mr": 0.0, "range": 1.0},
    )
    base.update(overrides)
    return StrategySignal(**base)


def test_engine_duck_fields_aligned():
    """引擎 _Signal 消费的全部字段必须在 StrategySignal 上同名存在。"""
    sig = _valid_signal()
    for attr in ("signal_id", "bar_ts_utc", "expert", "direction",
                 "price_ref", "atr0", "entry_dist", "l1_in_zone",
                 "regime_weights", "meta_p"):
        assert hasattr(sig, attr), f"missing engine-consumed field: {attr}"
    assert sig.meta_p is None
    assert sig.strategy_version == "v1"


def test_strategy_version_recorded_for_audit():
    sig = _valid_signal(strategy_version="supply_demand-v1")
    assert sig.strategy_version == "supply_demand-v1"


@pytest.mark.parametrize("bad_direction", [0, 2, -2])
def test_direction_must_be_pm_one(bad_direction):
    with pytest.raises(ValueError) as exc:
        _valid_signal(direction=bad_direction)
    assert "direction" in str(exc.value)


@pytest.mark.parametrize("bad_kwargs", [
    {"atr0": 0.0},
    {"atr0": -1.0},
    {"entry_dist": 0.0},
    {"entry_dist": -5.0},
])
def test_atr0_and_entry_dist_must_be_positive(bad_kwargs):
    with pytest.raises(ValueError) as exc:
        _valid_signal(**bad_kwargs)
    ctx = exc.value.args[0]
    assert "detail" in ctx


def test_naive_ts_rejected():
    with pytest.raises(ValueError) as exc:
        _valid_signal(bar_ts_utc=pd.Timestamp("2021-01-04 00:30"))
    assert "tz-aware" in str(exc.value)


def test_from_helper_bar_is_tz_aware():
    bar = H.make_bar(5, 1800, 1801, 1799, 1800)
    sig = _valid_signal(bar_ts_utc=bar.ts_utc)
    assert sig.bar_ts_utc == bar.ts_utc


class TestSignalGuards:
    @pytest.mark.parametrize("bad_kwargs", [
        {"signal_id": ""}, {"signal_id": None},
        {"expert": ""}, {"expert": None},
        {"strategy_version": ""},
        {"direction": True}, {"direction": False},
        {"price_ref": 0.0}, {"price_ref": -1.0},
        {"price_ref": float("nan")}, {"price_ref": float("inf")},
        {"atr0": float("nan")}, {"atr0": float("inf")},
        {"entry_dist": float("nan")}, {"entry_dist": float("inf")},
        {"meta_p": 1.2}, {"meta_p": -0.1}, {"meta_p": float("nan")},
        {"regime_weights": []},
    ])
    def test_invalid_fields_rejected(self, bad_kwargs):
        with pytest.raises(ValueError):
            _valid_signal(**bad_kwargs)

    def test_meta_p_optional_and_unit_interval(self):
        sig = _valid_signal(meta_p=0.6)
        assert sig.meta_p == 0.6
        assert _valid_signal(meta_p=None).meta_p is None
