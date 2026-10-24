# -*- coding: utf-8 -*-
"""test_risk_circuit.py —— 日内权益熔断三态机 normal/breaker/cooldown。"""
from __future__ import annotations

import _bt_helpers as H  # noqa: F401
import pandas as pd

from core.risk.circuit import CircuitBreaker, CircuitState


def _day(day: int, minute: int = 0) -> pd.Timestamp:
    return pd.Timestamp(f"2021-01-0{day} {minute:02d}:00", tz="UTC")


def test_normal_to_breaker_on_loss():
    cb = CircuitBreaker(daily_loss_limit=0.03, cooldown_bars=3)
    assert cb.state == CircuitState.NORMAL
    cb.update(10_000, _day(4))           # 日初
    assert cb.update(9_600, _day(4, 5)) == "breaker"   # -4% 破限


def test_breaker_blocks_new_position():
    cb = CircuitBreaker(daily_loss_limit=0.03, cooldown_bars=3)
    cb.update(10_000, _day(4))
    cb.update(9_600, _day(4, 5))
    assert not cb.allows_new_position


def test_cooldown_after_lockout_bars():
    cb = CircuitBreaker(daily_loss_limit=0.03, cooldown_bars=2)
    cb.update(10_000, _day(4))
    cb.update(9_600, _day(4, 5))     # breaker
    assert cb.update(9_600, _day(4, 10)) == "breaker"
    assert cb.update(9_600, _day(4, 15)) == "cooldown"  # 冷却仍禁新开
    assert not cb.allows_new_position


def test_next_day_resets_to_normal():
    cb = CircuitBreaker(daily_loss_limit=0.03, cooldown_bars=1)
    cb.update(10_000, _day(4))
    cb.update(9_500, _day(4, 5))     # breaker
    # 次一交易日边界重置
    assert cb.update(9_500, _day(5)) == "normal"
    assert cb.allows_new_position


def test_mild_loss_stays_normal():
    cb = CircuitBreaker(daily_loss_limit=0.03, cooldown_bars=1)
    cb.update(10_000, _day(4))
    assert cb.update(9_900, _day(4, 5)) == "normal"   # -1% 不破限
