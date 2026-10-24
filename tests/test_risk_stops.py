# -*- coding: utf-8 -*-
"""test_risk_stops.py —— 止损单调不变量（硬规则 4 / 夹具 c03_stop_widen）。"""
from __future__ import annotations

import _bt_helpers as H  # noqa: F401  (sys.path bootstrap)
import pytest

from core.risk.stops import (StopWideningError, initial_stop, update_stop)


def test_long_stop_only_moves_up():
    # 多头：抬高止损（向盈利方向）允许
    assert update_stop(100.0, 101.0, +1) == 101.0
    assert update_stop(100.0, 100.0, +1) == 100.0  # 不动允许


def test_long_stop_lower_raises():
    # c03 反例：多头把止损改到更低值 -> 必须拒绝
    with pytest.raises(StopWideningError) as ei:
        update_stop(100.0, 99.0, +1, symbol="XAUUSD", ts_utc="2021-01-04")
    assert ei.value.context["direction"] == +1
    assert ei.value.context["current_stop"] == 100.0


def test_short_stop_only_moves_down():
    assert update_stop(100.0, 99.0, -1) == 99.0


def test_short_stop_raise_raises():
    with pytest.raises(StopWideningError):
        update_stop(100.0, 101.0, -1)


def test_initial_stop_long_short():
    assert initial_stop(1800.0, +1, 10.0) == 1790.0
    assert initial_stop(1800.0, -1, 10.0) == 1810.0


def test_initial_stop_rejects_bad_dist():
    with pytest.raises(ValueError):
        initial_stop(1800.0, +1, 0.0)
