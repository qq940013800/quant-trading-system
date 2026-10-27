# -*- coding: utf-8 -*-
"""tests/test_strategy_registry.py —— 策略权重路由单测。

验证：
1. 不同 regime 下权重分配正确（趋势策略在 trend 权重高，均值回归在 range 权重高）
2. 每个 regime 下权重和为 1
3. 未注册策略不在结果里
4. 非法 regime / 负权重 / 未知止损类型 被拒绝
5. 权重只包含 base_weight > 0 的策略（不泄漏零权重）
"""
from __future__ import annotations

import math

import pytest

from core.registry.strategy_router import (
    StrategyDescriptor,
    StrategyWeightRouter,
    SUPPORTED_REGIMES,
    STOP_TYPES,
    build_demo_router,
)


# ------------------------------------------------------------------
# 夹具
# ------------------------------------------------------------------
@pytest.fixture(scope="module")
def router() -> StrategyWeightRouter:
    return build_demo_router()


# ------------------------------------------------------------------
# 1. 权重和为 1
# ------------------------------------------------------------------
@pytest.mark.parametrize("regime", list(SUPPORTED_REGIMES))
def test_weights_sum_to_one(router, regime):
    w = router.route(regime)
    assert isinstance(w, dict)
    assert len(w) > 0
    assert math.isclose(sum(w.values()), 1.0, rel_tol=1e-9, abs_tol=1e-9), (
        f"regime={regime} 权重和={sum(w.values())} != 1"
    )


# ------------------------------------------------------------------
# 2. 不同 regime 下权重分配方向正确
# ------------------------------------------------------------------
def test_trend_regime_favors_trend_strategies(router):
    w = router.route("trend")
    # 趋势类策略（breakout + ml_trend）应占大头
    trend_total = w["demo_breakout"] + w["ml_trend_meta"]
    mean_rev = w["demo_mean_reversion"]
    assert trend_total > 0.85, f"trend 下趋势策略占比过低: {trend_total}"
    assert mean_rev < 0.15, f"trend 下均值回归权重过高: {mean_rev}"


def test_range_regime_favors_mean_reversion(router):
    w = router.route("range")
    mr = w["demo_mean_reversion"]
    breakout = w["demo_breakout"]
    assert mr > 0.6, f"range 下均值回归权重过低: {mr}"
    assert breakout < 0.2, f"range 下突破策略权重过高: {breakout}"


def test_volatile_regime_prefers_ml_filter(router):
    """高波动市下带 ML 过滤的策略应比纯突破权重高。"""
    w = router.route("volatile")
    assert w["ml_trend_meta"] > w["demo_breakout"], (
        f"volatile 下 ml_trend_meta({w['ml_trend_meta']}) 应 > demo_breakout({w['demo_breakout']})"
    )


def test_quiet_regime_mean_reversion_dominates(router):
    w = router.route("quiet")
    assert w["demo_mean_reversion"] > w["demo_breakout"], (
        f"quiet 下均值回归应 > 纯突破"
    )


# ------------------------------------------------------------------
# 3. 未注册策略不在结果里
# ------------------------------------------------------------------
def test_unregistered_strategy_absent(router):
    w = router.route("trend")
    assert "nonexistent_strategy" not in w
    assert "ghost" not in w


def test_registered_strategy_names(router):
    names = router.list_registered()
    assert "demo_breakout" in names
    assert "ml_trend_meta" in names
    assert "demo_mean_reversion" in names


def test_unregister_removes_strategy():
    r = StrategyWeightRouter()
    d = StrategyDescriptor(
        name="tmp",
        version="v0.0.1",
        regime_profile={"trend": 1.0},
    )
    r.register(d)
    assert "tmp" in r.list_registered()
    r.unregister("tmp")
    assert "tmp" not in r.list_registered()


# ------------------------------------------------------------------
# 4. 非法输入被拒绝
# ------------------------------------------------------------------
def test_unknown_regime_raises(router):
    with pytest.raises(ValueError, match="未知 regime"):
        router.route("bull_market")  # 不在 SUPPORTED_REGIMES


def test_descriptor_rejects_unknown_regime():
    with pytest.raises(ValueError, match="未知 regime"):
        StrategyDescriptor(
            name="bad",
            version="v0.0.1",
            regime_profile={"unknown": 0.5},
        )


def test_descriptor_rejects_negative_weight():
    with pytest.raises(ValueError, match="不能为负"):
        StrategyDescriptor(
            name="bad",
            version="v0.0.1",
            regime_profile={"trend": -0.1},
        )


def test_descriptor_rejects_unknown_stop_type():
    with pytest.raises(ValueError, match="未知止损类型"):
        StrategyDescriptor(
            name="bad",
            version="v0.0.1",
            regime_profile={"trend": 0.5},
            stop_loss_type="magic_stop",
        )


def test_duplicate_registration_raises():
    r = StrategyWeightRouter()
    d = StrategyDescriptor(
        name="dup",
        version="v0.0.1",
        regime_profile={"trend": 1.0},
    )
    r.register(d)
    with pytest.raises(ValueError, match="已注册"):
        r.register(d)


# ------------------------------------------------------------------
# 5. 零权重策略不出现
# ------------------------------------------------------------------
def test_zero_weight_strategy_excluded_from_result():
    r = StrategyWeightRouter()
    r.register(StrategyDescriptor(
        name="only_trend",
        version="v1",
        regime_profile={"trend": 1.0},  # 只在 trend 有权重
    ))
    r.register(StrategyDescriptor(
        name="only_range",
        version="v1",
        regime_profile={"range": 1.0},  # 只在 range 有权重
    ))
    w_trend = r.route("trend")
    assert "only_trend" in w_trend
    assert "only_range" not in w_trend, "range-only 策略不应出现在 trend 路由结果里"
    w_range = r.route("range")
    assert "only_range" in w_range
    assert "only_trend" not in w_range


def test_all_zero_regime_raises():
    r = StrategyWeightRouter()
    r.register(StrategyDescriptor(
        name="x",
        version="v1",
        regime_profile={"trend": 1.0},  # 只在 trend 有权重
    ))
    # quiet 下没有任何策略有权重 → 应抛错，不返回空 dict
    with pytest.raises(ValueError, match="均为 0"):
        r.route("quiet")


# ------------------------------------------------------------------
# 6. 路由表完整性（所有 regime 都可路由）
# ------------------------------------------------------------------
def test_all_supported_regimes_routable(router):
    table = router.route_all_regimes()
    for regime in SUPPORTED_REGIMES:
        assert regime in table
        assert len(table[regime]) > 0
