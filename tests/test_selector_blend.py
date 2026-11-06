# -*- coding: utf-8 -*-
"""tests/test_selector_blend.py —— RegimeBlendedStrategy 单测。

覆盖：
1. 因果守卫：history 不以当前已收盘 bar 结尾（混入未来 bar）→ 带上下文
   ValueError；同一 as_of 重放结果稳定；
2. 低置信无信号：|Σ w·dir| < min_strength → None，≥ 阈值 → 出信号；
3. 合成方向正确性：单专家优势场景，blend 方向 = 净方向，主导专家字段取值；
4. selection 快照字段齐全 + 审计 JSONL 落盘可回放。
"""
from __future__ import annotations

import pytest

import _bt_helpers as H
import core.selector.blend as blend_mod
from core.features.base import LookAheadError
from core.regime.output import RegimeOutput
from core.regime.rules import STATES
from core.selector import (DeadbandWeightState, RegimeBlendedStrategy,
                           read_selections, replay_selection)
from core.strategies.signal import StrategySignal


# --------------------------------------------------------------------------- #
# 测试替身
# --------------------------------------------------------------------------- #
class StubClassifier:
    """记录 predict 调用、并模拟 @as_of 前视守卫的 regime 分类器替身。"""

    version = "stub-regime-v1"
    threshold_dataset = "CLEAN"

    def __init__(self, probs=None, state="trend", degraded=False):
        self._probs = probs or {s: 1.0 / 3.0 for s in STATES}
        self._state = state
        self._degraded = degraded
        self.predict_calls: list = []

    def predict(self, history, as_of) -> RegimeOutput:
        for b in history:
            if b.ts_utc > as_of:
                raise LookAheadError({
                    "layer": "test.stub", "ts_utc": str(b.ts_utc),
                    "as_of": str(as_of), "detail": "future bar (stub guard)"})
        self.predict_calls.append((len(history), as_of))
        return RegimeOutput(state=self._state, probs=dict(self._probs),
                            version=self.version, degraded=self._degraded)


class StubExpert:
    """按工厂函数产出候选信号的专家替身。"""

    def __init__(self, name, factory=None):
        self.name = name
        self.strategy_version = f"{name}-v9"
        self._factory = factory

    def on_bar_close(self, history, bar):
        if self._factory is None:
            return None
        return self._factory(history, bar)


def _make_sig(bar, direction, *, expert, atr0=1.0):
    return StrategySignal(
        signal_id=f"{expert}_{bar.ts_utc.isoformat()}_{direction}",
        bar_ts_utc=bar.ts_utc, expert=expert, direction=direction,
        price_ref=float(bar.close), atr0=float(atr0),
        entry_dist=2.0 * float(atr0), l1_in_zone=True,
        regime_weights={}, meta_p=None)


@pytest.fixture
def bars():
    return H.make_bars([1800.0 + 0.15 * k for k in range(90)])


@pytest.fixture
def plug_experts(monkeypatch):
    """把 _build_expert 替换为替身工厂（白盒测试 seam）；专家预置便于挂信号。"""
    box = {"e_trend": StubExpert("e_trend"), "e_mr": StubExpert("e_mr")}
    monkeypatch.setattr(
        blend_mod, "_build_expert", lambda name, params: box[name])
    return box


def _build_blend(box, clf, *, min_strength=0.1, audit_path=None):
    ws = DeadbandWeightState(["e_trend", "e_mr"], alpha=1.0,
                             deadband=0.0, confirm_n=1)
    return RegimeBlendedStrategy(
        regime_classifier=clf,
        strategy_names=["e_trend", "e_mr"],
        expert_regime_map={"e_trend": "trend", "e_mr": "mean_reversion"},
        weight_state=ws, min_strength=min_strength, audit_path=audit_path)


# --------------------------------------------------------------------------- #
def test_future_bar_raises_and_replay_stable(plug_experts, bars):
    clf = StubClassifier()
    blend = _build_blend(plug_experts, clf)
    bar = bars[60]
    # 正常窗口：专家无信号 → None（不抛）
    assert blend.on_bar_close(bars[:61], bar) is None
    calls_before = len(clf.predict_calls)
    # 同一 as_of 重放：classifier 只被喂 <= as_of 的 history
    blend.on_bar_close(bars[:61], bar)
    assert len(clf.predict_calls) == calls_before + 1
    # 混入一根未来 bar、bar 仍是旧 bar → blend 自身守卫显式失败
    with pytest.raises(ValueError) as exc_info:
        blend.on_bar_close(bars[:62], bar)
    assert "no future bars" in str(exc_info.value)
    # classifier 未被污染（predict_calls 未增加）
    assert len(clf.predict_calls) == calls_before + 1


def test_low_confidence_suppressed(plug_experts, bars):
    experts = plug_experts
    experts["e_trend"]._factory = lambda h, b: _make_sig(b, +1, expert="e_trend")
    experts["e_mr"]._factory = lambda h, b: _make_sig(b, -1, expert="e_mr")
    # trend 概率 0.85 / mr 0.15 → 目标权重 (0.85, 0.15)
    # 净强度 = 0.85 - 0.15 = 0.70
    clf = StubClassifier(probs={"trend": 0.85, "mean_reversion": 0.15,
                                "ranging": 0.0})
    bar = bars[60]
    suppressed = _build_blend(experts, clf, min_strength=0.80)
    assert suppressed.on_bar_close(bars[:61], bar) is None
    passing = _build_blend(experts, clf, min_strength=0.50)
    sig = passing.on_bar_close(bars[:61], bar)
    assert sig is not None
    assert sig.direction == +1
    assert sig.expert == "regime_blend_v1"


def test_direction_and_dominant_expert_fields(plug_experts, bars):
    experts = plug_experts
    experts["e_trend"]._factory = lambda h, b: _make_sig(
        b, +1, expert="e_trend", atr0=2.5)
    experts["e_mr"]._factory = lambda h, b: _make_sig(
        b, -1, expert="e_mr", atr0=0.5)
    clf = StubClassifier(probs={"trend": 0.85, "mean_reversion": 0.15,
                                "ranging": 0.0})
    blend = _build_blend(experts, clf, min_strength=0.10)
    sig = blend.on_bar_close(bars[:61], bars[60])
    assert sig is not None
    assert sig.direction == +1
    # 主导专家 = 权重最高且有信号者（e_trend）
    assert sig.atr0 == pytest.approx(2.5)
    assert sig.entry_dist == pytest.approx(5.0)
    assert sig.l1_in_zone is True


def test_selection_snapshot_and_audit(plug_experts, bars, tmp_path):
    experts = plug_experts
    experts["e_trend"]._factory = lambda h, b: _make_sig(b, +1, expert="e_trend")
    clf = StubClassifier(probs={"trend": 0.80, "mean_reversion": 0.10,
                                "ranging": 0.10}, degraded=True)
    audit_file = tmp_path / "selection.jsonl"
    blend = _build_blend(experts, clf, min_strength=0.10,
                        audit_path=str(audit_file))
    sig = blend.on_bar_close(bars[:61], bars[60])
    assert sig is not None
    sel = sig.selection
    for k in ("state", "regime_probs", "strategy_weights", "expert_signals",
              "blend_strength", "strategy_versions", "degraded",
              "target_weights", "weight_state"):
        assert k in sel, f"selection missing {k}"
    assert sel["state"] == "trend"
    assert sel["degraded"] is True
    assert abs(sum(sel["strategy_weights"].values()) - 1.0) < 1e-9
    # 审计落盘 + 回放校验
    recs = read_selections(str(audit_file))
    assert len(recs) == 1
    assert recs[0].signal_id == sig.signal_id
    assert recs[0].degraded is True
    replay_selection(recs[0])   # 不抛 = 权重/强度自洽
