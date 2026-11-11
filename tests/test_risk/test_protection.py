# -*- coding: utf-8 -*-
"""tests.test_risk.test_protection —— 吊灯/分批止盈/利润回吐保护裁决纯函数测试。"""
from __future__ import annotations

import pytest

from core.risk.protection import (
    evaluate_chandelier,
    evaluate_scale_out,
    evaluate_profit_retracement,
    ScaleOutRule,
    ProtectionDecision,
)


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
