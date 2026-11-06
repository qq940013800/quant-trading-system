# -*- coding: utf-8 -*-
"""tests/test_selector_weights.py —— 滞回权重状态机 / 参数收缩 / 合成强度单测。

覆盖（决策 #8/O06）：
1. 任意目标序列下权重和恒为 1；
2. 滞回防抖：deadband 内来回振荡时，带滞回版本的实际 EMA 应用次数显著
   少于无滞回版本（alpha/deadband/confirm_n 全 1）；
3. deadband 边界：|diff| <= deadband 不更新，严格 > deadband 才更新；
4. 连续 N bar 确认：方向反转即计数清零；
5. shrink_params 三点收缩（lam=1 全局 / lam=0 局部 / lam=0.5 中点）；
6. blend_strength 合成强度。
"""
from __future__ import annotations

import numpy as np
import pytest

from core.selector.weights import (DeadbandWeightState, WeightStateError,
                                   blend_strength, shrink_params)

KEYS = ("trend", "mean_reversion", "ranging")


def test_weights_always_sum_to_one():
    rng = np.random.default_rng(11)
    ws = DeadbandWeightState(KEYS, alpha=0.35, deadband=0.04, confirm_n=2)
    for _ in range(60):
        raw = rng.random(3)
        target = {k: float(v) for k, v in zip(KEYS, raw / raw.sum())}
        w = ws.update(target)
        assert set(w.keys()) == set(KEYS)
        assert abs(sum(w.values()) - 1.0) < 1e-9
        assert all(v >= -1e-12 for v in w.values())


def test_hysteresis_suppresses_updates_vs_naive():
    """目标在 deadband 边界两侧来回振荡（threshold whipsaw 场景）。"""
    smooth = DeadbandWeightState(KEYS, alpha=0.5, deadband=0.10, confirm_n=1)
    naive = DeadbandWeightState(KEYS, alpha=0.5, deadband=0.0, confirm_n=1)
    for i in range(40):
        if i % 2 == 0:
            t = {"trend": 0.55, "mean_reversion": 0.25, "ranging": 0.20}
        else:
            t = {"trend": 0.45, "mean_reversion": 0.35, "ranging": 0.20}
        smooth.update(t)
        naive.update(t)
    # 无滞回版本每根每键都可能 EMA；带滞回版本应用次数应显著更少
    assert smooth.applied_updates < naive.applied_updates
    assert smooth.applied_updates >= 1          # 不是永远冻结
    assert abs(sum(smooth.weights().values()) - 1.0) < 1e-9


def test_deadband_boundary():
    """|diff| == deadband 不更新（边界含在滞回带内），严格 > deadband 才更新。"""
    ws = DeadbandWeightState(("a", "b"), alpha=1.0, deadband=0.10, confirm_n=1)
    ws.update({"a": 0.55, "b": 0.45})   # diff 0.05 <= 0.10 → 冻结
    assert ws.weights()["a"] == pytest.approx(0.5)
    ws.update({"a": 0.60, "b": 0.40})    # diff 0.10 == deadband → 仍冻结
    assert ws.weights()["a"] == pytest.approx(0.5)
    ws.update({"a": 0.61, "b": 0.39})    # diff 0.11 > 0.10 → 更新
    assert ws.weights()["a"] == pytest.approx(0.61)
    assert ws.weights()["b"] == pytest.approx(0.39)


def test_confirmation_n_bars_and_direction_flip():
    ws = DeadbandWeightState(("a", "b"), alpha=1.0, deadband=0.0, confirm_n=3)
    ws.update({"a": 0.8, "b": 0.2})     # 计数=1，不应用
    assert ws.weights()["a"] == pytest.approx(0.5)
    ws.update({"a": 0.8, "b": 0.2})     # 计数=2，不应用
    assert ws.weights()["a"] == pytest.approx(0.5)
    ws.update({"a": 0.8, "b": 0.2})     # 计数=3，应用
    assert ws.weights()["a"] == pytest.approx(0.8)
    # 目标反向：计数从 1 重新开始，不立即应用
    ws.update({"a": 0.1, "b": 0.9})
    assert ws.weights()["a"] == pytest.approx(0.8)


def test_reset_restores_initial():
    ws = DeadbandWeightState(("a", "b"), alpha=1.0, deadband=0.0, confirm_n=1,
                             initial={"a": 0.9, "b": 0.1})
    ws.update({"a": 0.2, "b": 0.8})
    ws.reset()
    assert ws.weights()["a"] == pytest.approx(0.9)
    assert ws.applied_updates >= 0


def test_shrink_params_endpoints_and_midpoint():
    g = {"x": 1.0, "y": 2.0}
    loc = {"x": 3.0, "y": 0.0}
    assert shrink_params(g, loc, 1.0) == {"x": 1.0, "y": 2.0}   # 全全局默认
    assert shrink_params(g, loc, 0.0) == {"x": 3.0, "y": 0.0}   # 全局部估计
    mid = shrink_params(g, loc, 0.5)
    assert mid["x"] == pytest.approx(2.0)
    assert mid["y"] == pytest.approx(1.0)
    with pytest.raises(WeightStateError):
        shrink_params(g, {"x": 1.0}, 0.5)          # 键不一致
    with pytest.raises(WeightStateError):
        shrink_params(g, loc, 1.5)                 # lam 越界


def test_blend_strength():
    assert blend_strength({"a": 1, "b": -1},
                           {"a": 0.5, "b": 0.5}) == pytest.approx(0.0)
    assert blend_strength({"a": 1},
                          {"a": 0.7, "b": 0.3}) == pytest.approx(0.7)
    # 无候选信号 → 强度 0
    assert blend_strength({}, {"a": 0.7}) == pytest.approx(0.0)


def test_target_validation():
    ws = DeadbandWeightState(("a", "b"))
    with pytest.raises(WeightStateError):
        ws.update({"a": 0.7})                      # 缺键
    with pytest.raises(WeightStateError):
        ws.update({"a": 0.7, "b": 0.2})             # 和不为 1
    with pytest.raises(WeightStateError):
        DeadbandWeightState(("a", "b"), alpha=0.0)
    with pytest.raises(WeightStateError):
        DeadbandWeightState(("a", "b"), confirm_n=0)
