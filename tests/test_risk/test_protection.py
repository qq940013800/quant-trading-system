# -*- coding: utf-8 -*-
"""tests.test_risk.test_protection —— 吊灯/分批止盈/利润回吐保护裁决纯函数测试。"""
from __future__ import annotations

import pytest

from core.risk.protection import (
    evaluate_chandelier,
    evaluate_scale_out,
    evaluate_profit_retracement,
    decide_protection,
    ScaleOutRule,
    ProtectionDecision,
)
from core.risk.stops import StopState, StopConfig


# ------------------------------------------------------------------
# 吊灯退出
# ------------------------------------------------------------------
class TestChandelier:
    def test_long_chandelier_tightens_stop(self):
        # peak=105, atr0=2, mult=1.5 -> dist=3, candidate=102 > current 100
        stop = evaluate_chandelier(105.0, +1, 2.0, 1.5, 100.0)
        assert stop == pytest.approx(102.0)

    def test_short_chandelier_tightens_stop(self):
        # peak=95, atr0=2, mult=1.5 -> dist=3, candidate=98 < current 100
        stop = evaluate_chandelier(95.0, -1, 2.0, 1.5, 100.0)
        assert stop == pytest.approx(98.0)

    def test_chandelier_no_widen(self):
        # 多头候选 101 不优于当前止损 102 -> None，不放宽风险
        assert evaluate_chandelier(103.0, +1, 2.0, 1.0, 102.0) is None

    @pytest.mark.parametrize("atr0,mult,dirn", [(0.0, 1.5, +1), (2.0, 0.0, +1), (2.0, 1.5, 0)])
    def test_chandelier_guards(self, atr0, mult, dirn):
        with pytest.raises(ValueError):
            evaluate_chandelier(105.0, dirn, atr0, mult, 100.0)

    @pytest.mark.parametrize("bad", [float("nan"), float("inf")])
    def test_chandelier_rejects_nonfinite(self, bad):
        with pytest.raises(ValueError):
            evaluate_chandelier(bad, +1, 2.0, 1.5, 100.0)


# ------------------------------------------------------------------
# 分批止盈
# ------------------------------------------------------------------
RULES = [ScaleOutRule(level_r=2.0, ratio=0.5), ScaleOutRule(level_r=3.0, ratio=0.25)]


class TestScaleOut:
    def test_trigger_first_level(self):
        res = evaluate_scale_out(2.0, RULES, [False, False], 1.0)
        assert res.triggered is True
        assert res.level_r == pytest.approx(2.0)
        assert res.reduce_ratio == pytest.approx(0.5)
        assert res.remaining_ratio == pytest.approx(0.5)
        assert res.done == [True, False]

    def test_skip_done_level_and_trigger_next(self):
        # 首档已完成，r=3.2 触发第二档
        res = evaluate_scale_out(3.2, RULES, [True, False], 0.5)
        assert res.triggered is True
        assert res.level_r == pytest.approx(3.0)
        assert res.reduce_ratio == pytest.approx(0.25)
        assert res.remaining_ratio == pytest.approx(0.375)
        assert res.done == [True, True]

    def test_not_triggered_below_level(self):
        res = evaluate_scale_out(1.0, RULES, [False, False], 1.0)
        assert res.triggered is False
        assert res.reduce_ratio == 0.0
        assert res.remaining_ratio == pytest.approx(1.0)
        assert res.done == [False, False]

    def test_one_level_per_bar(self):
        # r=3.5 同时满足两档，同 bar 只推进首个未完成级别
        res = evaluate_scale_out(3.5, RULES, [False, False], 1.0)
        assert res.triggered is True
        assert res.level_r == pytest.approx(2.0)
        assert res.remaining_ratio == pytest.approx(0.5)
        assert res.done == [True, False]

    def test_done_length_mismatch_rejected(self):
        with pytest.raises(ValueError):
            evaluate_scale_out(3.0, RULES, [False], 1.0)

    @pytest.mark.parametrize("rem", [0.0, 1.5, -0.2])
    def test_remaining_ratio_guard(self, rem):
        with pytest.raises(ValueError):
            evaluate_scale_out(2.0, RULES, [False, False], rem)


# ------------------------------------------------------------------
# 利润回吐保护
# ------------------------------------------------------------------
class TestProfitRetracement:
    def test_triggers_on_deep_retracement(self):
        # 峰值 100，当前 65 -> 回撤 35% ≥ 30%，r=1.5 ≥ 1R
        assert evaluate_profit_retracement(65.0, 100.0, 1.5, 1.0, 0.30) is True

    def test_no_trigger_below_threshold(self):
        # 回撤 20% < 30%
        assert evaluate_profit_retracement(80.0, 100.0, 1.5, 1.0, 0.30) is False

    def test_no_trigger_below_min_r(self):
        assert evaluate_profit_retracement(65.0, 100.0, 0.5, 1.0, 0.30) is False

    @pytest.mark.parametrize("cp,pp", [(0.0, 100.0), (-5.0, 100.0), (65.0, 0.0)])
    def test_no_trigger_nonpositive_profit(self, cp, pp):
        assert evaluate_profit_retracement(cp, pp, 1.5, 1.0, 0.30) is False

    @pytest.mark.parametrize("pct,mr", [(-0.1, 1.0), (1.2, 1.0), (0.3, -0.5)])
    def test_guards(self, pct, mr):
        with pytest.raises(ValueError):
            evaluate_profit_retracement(65.0, 100.0, 1.5, mr, pct)


# ------------------------------------------------------------------
# 决策快照
# ------------------------------------------------------------------
class TestProtectionDecision:
    def test_valid_reduce_decision(self):
        d = ProtectionDecision(
            action="reduce", source="scale_out", new_stop=None,
            reduce_ratio=0.5, close=False, audit={"entry_price": 100.0},
        )
        assert d.action == "reduce"
        assert d.reduce_ratio == pytest.approx(0.5)
        assert d.close is False

    @pytest.mark.parametrize("action,ratio,close", [
        ("hold", 0.0, False),
        ("close", 0.0, True),
        ("move_stop", 0.0, False),
    ])
    def test_valid_actions(self, action, ratio, close):
        d = ProtectionDecision(action=action, source=None, new_stop=None,
                               reduce_ratio=ratio, close=close, audit={})
        assert d.action == action

    @pytest.mark.parametrize("action,ratio,close", [
        ("invalid", 0.0, False),
        ("reduce", 1.5, False),
        ("reduce", 0.0, "yes"),
    ])
    def test_invalid_decision_rejected(self, action, ratio, close):
        with pytest.raises(ValueError):
            ProtectionDecision(action=action, source=None, new_stop=None,
                               reduce_ratio=ratio, close=close, audit={})


# ------------------------------------------------------------------
# 统一编排入口 decide_protection
# ------------------------------------------------------------------
def _long_state(**over) -> StopState:
    kw = dict(entry_price=100.0, direction=+1, entry_atr=2.0, entry_dist=2.0,
              current_stop=98.0, bars_held=5, max_favorable_r=0.0)
    kw.update(over)
    return StopState(**kw)


class TestDecideProtection:
    def test_signal_stop_closes(self):
        d = decide_protection(_long_state(), StopConfig(), 101.0,
                              signal_reversed=True)
        assert d.action == "close"
        assert d.source == "signal"
        assert d.close is True
        assert d.new_stop is None

    def test_time_stop_closes(self):
        state = _long_state(bars_held=25, max_favorable_r=0.5)
        cfg = StopConfig(max_holding_bars=20, breakeven_r=1.0)
        d = decide_protection(state, cfg, 100.5)
        assert d.action == "close"
        assert d.source == "time"
        assert d.close is True

    def test_profit_retracement_closes(self):
        # r=1.5（price=103），峰值盈利 100 回撤到 65（35% ≥ 30%）
        d = decide_protection(
            _long_state(), StopConfig(), 103.0,
            peak_profit=100.0, current_profit=65.0,
            retracement_pct=0.30, retracement_min_r=1.0,
        )
        assert d.action == "close"
        assert d.source == "profit_retracement"
        assert d.close is True

    def test_scale_out_reduces(self):
        rules = [ScaleOutRule(level_r=2.0, ratio=0.5)]
        d = decide_protection(
            _long_state(), StopConfig(), 104.0,
            scale_rules=rules, scale_done=[False], remaining_ratio=1.0,
        )
        assert d.action == "reduce"
        assert d.source == "scale_out"
        assert d.reduce_ratio == pytest.approx(0.5)
        assert d.close is False
        assert d.audit["new_remaining_ratio"] == pytest.approx(0.5)

    def test_chandelier_moves_stop(self):
        d = decide_protection(
            _long_state(), StopConfig(), 103.0,
            peak_price=105.0, chandelier_atr_mult=1.5, trailing_activated=True,
        )
        assert d.action == "move_stop"
        assert d.source == "chandelier"
        # 105 - 2×1.5 = 102
        assert d.new_stop == pytest.approx(102.0)

    def test_trailing_moves_stop(self):
        # r=2.5（price=105），跟踪 offset 1R -> 100+(2.5-1.0)×2=103
        d = decide_protection(_long_state(), StopConfig(), 105.0)
        assert d.action == "move_stop"
        assert d.source == "trailing"
        assert d.new_stop == pytest.approx(103.0)

    def test_hold_when_no_condition(self):
        d = decide_protection(_long_state(), StopConfig(), 101.0)
        assert d.action == "hold"
        assert d.source is None
        assert d.new_stop is None
        assert d.reduce_ratio == 0.0
        assert d.close is False

    def test_retracement_outranks_scale_out(self):
        rules = [ScaleOutRule(level_r=2.0, ratio=0.5)]
        d = decide_protection(
            _long_state(), StopConfig(), 104.0,
            peak_profit=100.0, current_profit=65.0, retracement_pct=0.30,
            scale_rules=rules, scale_done=[False], remaining_ratio=1.0,
        )
        assert d.action == "close"
        assert d.source == "profit_retracement"

    def test_chandelier_inactive_falls_back_to_breakeven(self):
        d = decide_protection(
            _long_state(), StopConfig(), 103.0,
            peak_price=105.0, chandelier_atr_mult=1.5, trailing_activated=False,
        )
        # 未激活吊灯；r=1.5 走保本止损
        assert d.action == "move_stop"
        assert d.source == "breakeven"

    def test_audit_snapshot_carries_frozen_inputs(self):
        d = decide_protection(_long_state(), StopConfig(), 101.0)
        audit = d.audit
        assert audit["entry_price"] == pytest.approx(100.0)
        assert audit["direction"] == +1
        assert audit["entry_atr"] == pytest.approx(2.0)
        assert audit["entry_dist"] == pytest.approx(2.0)
        assert audit["current_price"] == pytest.approx(101.0)
        assert audit["r_current"] == pytest.approx(0.5)
        assert audit["remaining_ratio"] == pytest.approx(1.0)
