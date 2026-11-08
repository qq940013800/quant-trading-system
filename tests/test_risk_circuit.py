# -*- coding: utf-8 -*-
"""test_risk_circuit.py —— 日内权益熔断三态机 normal/breaker/cooldown。"""
from __future__ import annotations

import _bt_helpers as H  # noqa: F401
import pandas as pd
import pytest

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


# ------------------------------------------------------------------
# 边界 / 状态迁移 / 异常路径补充
# ------------------------------------------------------------------
def test_invalid_loss_limit_rejected():
    for bad in (0.0, 1.0, -0.01, 1.5):
        with pytest.raises(ValueError):
            CircuitBreaker(daily_loss_limit=bad)


def test_nonfinite_loss_limit_rejected():
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError):
            CircuitBreaker(daily_loss_limit=bad)


def test_invalid_cooldown_bars_rejected():
    for bad in (-1, 0.5, True, "2"):
        with pytest.raises(ValueError):
            CircuitBreaker(daily_loss_limit=0.03, cooldown_bars=bad)


def test_breaker_does_not_auto_recover_same_day():
    """当日进入 breaker 后，权益回升也不能在同日回到 normal。"""
    cb = CircuitBreaker(daily_loss_limit=0.03, cooldown_bars=5)
    cb.update(10_000, _day(4))
    cb.update(9_600, _day(4, 5))          # breaker
    assert cb.update(10_000, _day(4, 10)) == "breaker"
    assert not cb.allows_new_position


def test_cooldown_persists_within_same_day():
    cb = CircuitBreaker(daily_loss_limit=0.03, cooldown_bars=2)
    cb.update(10_000, _day(4))
    cb.update(9_600, _day(4, 5))          # breaker
    cb.update(9_600, _day(4, 10))
    assert cb.update(9_600, _day(4, 15)) == "cooldown"
    assert cb.update(9_600, _day(4, 20)) == "cooldown"
    assert not cb.allows_new_position


def test_cooldown_resets_on_next_day():
    cb = CircuitBreaker(daily_loss_limit=0.03, cooldown_bars=1)
    cb.update(10_000, _day(4))
    cb.update(9_500, _day(4, 5))          # breaker
    cb.update(9_500, _day(4, 10))         # cooldown
    assert cb.update(9_500, _day(5)) == "normal"
    assert cb.allows_new_position


def test_exact_loss_limit_triggers_breaker():
    """回撤恰好等于 -limit（<= 口径）即触发。"""
    cb = CircuitBreaker(daily_loss_limit=0.03, cooldown_bars=1)
    cb.update(10_000, _day(4))
    assert cb.update(9_700, _day(4, 5)) == "breaker"


def test_zero_open_equity_guard_skips_division():
    """日初权益为 0 时回撤按 0 处理，不除零崩溃。"""
    cb = CircuitBreaker(daily_loss_limit=0.03)
    assert cb.update(0.0, _day(4)) == "normal"
    assert cb.update(1.0, _day(4, 5)) == "normal"


def test_state_name_property():
    cb = CircuitBreaker(daily_loss_limit=0.03)
    assert cb.state_name == "normal"
    cb.update(10_000, _day(4))
    cb.update(9_600, _day(4, 5))
    assert cb.state_name == "breaker"


def test_pd_ts_date_tolerates_naive_and_string():
    from core.risk.circuit import pd_ts_date
    import pandas as pd
    aware = pd.Timestamp("2021-01-04 09:30", tz="UTC")
    naive = pd.Timestamp("2021-01-04 09:30")
    assert pd_ts_date(aware) == pd_ts_date(naive)
    assert pd_ts_date("2021-01-04 09:30:00") == "2021-01-04"
