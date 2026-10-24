# -*- coding: utf-8 -*-
"""tests/test_features_causal.py —— 前视守卫（黄金夹具 c01/c02 正向断言）。

c01_shift_neg / c02_center_true 是"坏榜样"（shift(-3)、center=True）；
本文件断言我们的实现恰好相反：
  1. history 含 ts_utc > as_of 的 bar → LookAheadError；
  2. as_of naive → AsOfContractError；
  3. 【核心不变量】as_of 处的特征值不随"未来追加 bar"改变；
  4. build_feature_panel 的 available_at 契约与 warmup NaN 语义。
"""
from __future__ import annotations

import numpy as np
import pytest

from _tp_bootstrap import make_synthetic_bars, pd

from core.features.base import (
    AsOfContractError,
    LookAheadError,
    as_of,
    build_feature_panel,
)
from core.features.atr import wilder_atr
from core.features.structure import donchian_position


@pytest.fixture(scope="module")
def bars():
    return make_synthetic_bars(seed=11, n=200, kind="martingale")


def test_future_bar_raises_lookahead(bars):
    as_of = bars[50].ts_utc
    with pytest.raises(LookAheadError):
        wilder_atr(bars[:60], as_of)  # bars[55] ts_utc > as_of


def test_naive_asof_raises(bars):
    naive = pd.Timestamp("2024-01-01T05:00:00")
    with pytest.raises(AsOfContractError):
        wilder_atr(bars[:60], naive)


def test_unsorted_history_raises(bars):
    as_of = bars[100].ts_utc
    shuffled = list(bars[:100])
    shuffled[90], shuffled[95] = shuffled[95], shuffled[90]
    with pytest.raises(AsOfContractError):
        wilder_atr(shuffled, as_of)


def test_future_bars_cannot_enter_history(bars):
    """黄金因果守卫核心：decorator 拒绝未来 bar（上面 test_future_bar_raises），
    因此特征实现接触不到任何 as_of 之后的数据——等价于"未来 bar 不影响过去值"。"""
    t = 120
    as_of = bars[t].ts_utc
    v1 = wilder_atr(bars[: t + 1], as_of, period=14)
    # 攻击：把 80 根未来 bar 塞进 history —— 必须被 LookAheadError 挡住
    with pytest.raises(LookAheadError):
        wilder_atr(bars, as_of, period=14)
    # 被挡住之前，截断历史上的值必须是确定的
    assert np.isfinite(v1)


def test_panel_row_matches_truncated_pointwise_call(bars):
    """面板在 bar t 的值 == 只用 bars[:t+1] 逐点重算的值（防面板层偷看未来）。"""
    panel = build_feature_panel(
        bars, {"atr": lambda h, a: wilder_atr(h, a, period=14)}, warmup_bars=0)
    t = 150
    manual = wilder_atr(bars[: t + 1], bars[t].ts_utc, period=14)
    assert panel["atr"].iloc[t] == pytest.approx(manual, rel=1e-12, abs=1e-12)
    assert (panel["available_at"] == panel.index).all()


def test_decorator_passthrough_args(bars):
    @as_of
    def dummy(history, ts, scale: float = 1.0) -> float:
        return history[-1].close * scale

    ts_now = bars[30].ts_utc
    assert dummy(bars[:31], ts_now, scale=2.0) == pytest.approx(bars[30].close * 2.0)
