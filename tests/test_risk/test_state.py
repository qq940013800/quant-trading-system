# -*- coding: utf-8 -*-
"""tests.test_risk.test_state —— RiskState 冻结快照纯逻辑边界。

覆盖：R 倍数分母强制取冻结 entry_dist、默认字段、extra 字典实例隔离。
不触数据库/交易路由；atr0/entry_dist 入场冻结不变量（硬规则 4）。
"""
from __future__ import annotations

import pytest

from core.risk.state import RiskState


def _state(**kw) -> RiskState:
    defaults = dict(
        equity=100_000.0, atr0=2.5, entry_dist=5.0,
        stop_price=995.0, heat_units=1,
    )
    defaults.update(kw)
    return RiskState(**defaults)


class TestFrozenDenominator:
    def test_denominator_returns_frozen_entry_dist(self):
        st = _state(entry_dist=5.0)
        # 分母必须是入场冻结的 entry_dist，不允许被重算覆盖
        assert st.frozen_r_denominator() == 5.0
        assert isinstance(st.frozen_r_denominator(), float)

    def test_denominator_unchanged_when_fields_mutated(self):
        st = _state(entry_dist=5.0)
        # 持仓期仅允许 equity/stop_price 等可变字段变化；entry_dist 冻结
        st.equity = 90_000.0
        st.stop_price = 998.0
        assert st.frozen_r_denominator() == 5.0


class TestDefaults:
    def test_default_circuit_state_and_tier(self):
        st = _state()
        assert st.circuit_state == "normal"
        assert st.drawdown_tier == 1.0

    def test_extra_dict_is_isolated_per_instance(self):
        a = _state()
        b = _state()
        a.extra["note"] = "locked"
        assert "note" not in b.extra
        assert b.extra == {}

    def test_extra_accepts_mapping(self):
        st = _state(extra={"source": "CLEAN"})
        assert st.extra["source"] == "CLEAN"


class TestGuard:
    @pytest.mark.parametrize("bad", [0.0, float("nan"), float("inf"), -1.0])
    def test_entry_dist_must_be_positive_finite(self, bad):
        with pytest.raises(ValueError):
            _state(entry_dist=bad)

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), True])
    def test_equity_must_be_finite(self, bad):
        with pytest.raises(ValueError):
            _state(equity=bad)

    @pytest.mark.parametrize("bad", [-1, 1.5, True])
    def test_heat_units_must_be_nonneg_int(self, bad):
        with pytest.raises(ValueError):
            _state(heat_units=bad)

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), True])
    def test_stop_price_must_be_finite_when_set(self, bad):
        with pytest.raises(ValueError):
            _state(stop_price=bad)

    def test_stop_price_none_when_unset(self):
        st = _state(stop_price=None)
        assert st.stop_price is None

    def test_circuit_state_enforced(self):
        with pytest.raises(ValueError):
            _state(circuit_state="xxx")

    @pytest.mark.parametrize("bad", [0.0, float("nan"), -0.5])
    def test_drawdown_tier_must_be_positive_finite(self, bad):
        with pytest.raises(ValueError):
            _state(drawdown_tier=bad)

    def test_extra_must_be_dict(self):
        with pytest.raises(ValueError):
            _state(extra=["not", "dict"])

    def test_valid_breaker_state_accepted(self):
        st = _state(circuit_state="breaker", heat_units=0)
        assert st.circuit_state == "breaker"
