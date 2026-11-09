# -*- coding: utf-8 -*-
"""tests.test_risk.test_dynamic_allocator —— PM 动态资金分配器纯逻辑。

覆盖：综合得分上下界、红线暂停 / 黄线观察 / 正常运行三态、探索期权重、
active 权重归一化、suspended/explore 权重口径。纯内存计算，不触交易路由、
下单、资金计算或数据库。
"""
from __future__ import annotations

import pytest

from core.risk.dynamic_allocator import (
    DynamicAllocator,
    StrategyPerformance,
    get_dynamic_allocator,
)


def _perf(**kw) -> StrategyPerformance:
    defaults = dict(
        strategy_id="s", name="s", sharpe=1.0, max_drawdown=0.05,
        win_rate=0.55, profit_factor=1.2, total_trades=50,
        consecutive_losses=1, avg_r_multiple=0.0, days_running=60,
    )
    defaults.update(kw)
    return StrategyPerformance(**defaults)


class TestCompositeScore:
    def test_score_extremes_map_to_top_and_bottom(self):
        alloc = DynamicAllocator(min_trades_for_score=10)
        best = _perf(sharpe=3.0, max_drawdown=0.0, win_rate=0.9,
                     consecutive_losses=0)
        worst = _perf(sharpe=-1.0, max_drawdown=0.30, win_rate=0.1,
                      consecutive_losses=9)
        # 满分 100（夏普40 + 回撤30 + 胜率20 + 稳定性10）；最差回落 0
        assert alloc._calculate_composite_score(best) == pytest.approx(100.0)
        assert alloc._calculate_composite_score(worst) == pytest.approx(0.0)

    def test_score_components_are_capped(self):
        alloc = DynamicAllocator(min_trades_for_score=10)
        # 超界的夏普/胜率/连亏被裁到分量上下限，不溢出 0-100
        over = _perf(sharpe=10.0, win_rate=1.2, consecutive_losses=20)
        score = alloc._calculate_composite_score(over)
        assert 0.0 <= score <= 100.0

    def test_insufficient_trades_get_base_score(self):
        alloc = DynamicAllocator(min_trades_for_score=10)
        few = _perf(total_trades=3, sharpe=2.0)
        # 样本不足不给高分，回落基础分（防小样本高估）
        assert alloc._calculate_composite_score(few) == 30.0


class TestStatus:
    def test_suspended_on_red_lines(self):
        alloc = DynamicAllocator()
        # 夏普 < 0
        alloc.update_performance(_perf(strategy_id="neg", sharpe=-0.2))
        res = {r.strategy_id: r for r in
               alloc.calculate_allocations(1_000_000)}
        assert res["neg"].status == "suspended"
        assert "暂停" in res["neg"].reason

    def test_suspended_on_deep_drawdown(self):
        alloc = DynamicAllocator()
        alloc.update_performance(_perf(strategy_id="dd", max_drawdown=0.30))
        res = alloc.calculate_allocations(1)[0]
        assert res.status == "suspended"

    def test_watch_on_yellow_line(self):
        alloc = DynamicAllocator()
        # 夏普 0.4 < 0.5 进观察
        alloc.update_performance(_perf(strategy_id="watch", sharpe=0.4,
                                       max_drawdown=0.10))
        res = alloc.calculate_allocations(1)[0]
        assert res.status == "watch"

    def test_active_on_healthy_strategy(self):
        alloc = DynamicAllocator()
        alloc.update_performance(_perf(strategy_id="ok"))
        res = alloc.calculate_allocations(1)[0]
        assert res.status == "active"


class TestAllocationWeights:
    def test_active_weights_normalize_to_one(self):
        alloc = DynamicAllocator()
        alloc.update_performance(_perf(strategy_id="a", sharpe=1.5))
        alloc.update_performance(_perf(strategy_id="b", sharpe=0.8))
        res = alloc.calculate_allocations(1_000_000)
        active = [r.weight for r in res if r.status == "active"]
        assert sum(active) == pytest.approx(1.0, abs=1e-9)

    def test_suspended_gets_zero_weight(self):
        alloc = DynamicAllocator()
        alloc.update_performance(_perf(strategy_id="bad", sharpe=-1.0))
        res = alloc.calculate_allocations(1)[0]
        assert res.weight == 0.0

    def test_explore_period_base_weight(self):
        alloc = DynamicAllocator(min_trades_for_score=10,
                                 explore_period_days=30,
                                 base_explore_weight=0.05)
        new = _perf(strategy_id="new", days_running=5, total_trades=3)
        alloc.update_performance(new)
        res = alloc.calculate_allocations(1)[0]
        assert res.status == "explore"
        assert res.weight == pytest.approx(0.05)

    def test_capital_for_unknown_strategy_is_zero(self):
        alloc = DynamicAllocator()
        alloc.update_performance(_perf(strategy_id="a"))
        assert alloc.get_capital_for_strategy("missing", 1_000_000) == 0.0

    def test_capital_scales_with_weight(self):
        alloc = DynamicAllocator()
        alloc.update_performance(_perf(strategy_id="a"))
        capital = alloc.get_capital_for_strategy("a", 1_000_000)
        assert capital == pytest.approx(1_000_000.0)

    def test_factory_singleton(self):
        first = get_dynamic_allocator()
        second = get_dynamic_allocator()
        assert first is second


class TestAllocatorBoundary:
    def test_empty_performances_returns_empty(self):
        alloc = DynamicAllocator()
        assert alloc.calculate_allocations(1_000_000) == []

    def test_all_suspended_get_zero_weight(self):
        alloc = DynamicAllocator()
        alloc.update_performance(_perf(strategy_id="bad", sharpe=-1.0))
        res = alloc.calculate_allocations(1)[0]
        assert res.status == "suspended"
        assert res.weight == 0.0

    def test_watch_half_explore_weight_when_active_present(self):
        alloc = DynamicAllocator(base_explore_weight=0.05)
        alloc.update_performance(_perf(strategy_id="good"))
        alloc.update_performance(_perf(strategy_id="w", sharpe=0.4))
        res = {r.strategy_id: r for r in alloc.calculate_allocations(1)}
        # 观察期权重 = 探索基础权重的一半
        assert res["w"].status == "watch"
        assert res["w"].weight == pytest.approx(0.025)

    def test_explore_period_overrides_active_classification(self):
        alloc = DynamicAllocator(min_trades_for_score=10,
                                 explore_period_days=30,
                                 base_explore_weight=0.05)
        # 指标本可归入 active，但处于探索期 -> 强制 explore 状态/权重
        alloc.update_performance(_perf(strategy_id="new", days_running=5,
                                       total_trades=3, sharpe=2.0))
        res = alloc.calculate_allocations(1)[0]
        assert res.status == "explore"
        assert res.weight == pytest.approx(0.05)

    def test_suspended_on_loss_streak(self):
        alloc = DynamicAllocator()
        alloc.update_performance(_perf(strategy_id="cl", consecutive_losses=9))
        assert alloc.calculate_allocations(1)[0].status == "suspended"

    def test_watch_on_deep_drawdown(self):
        alloc = DynamicAllocator()
        alloc.update_performance(_perf(strategy_id="wd", max_drawdown=0.18,
                                       sharpe=1.0))
        assert alloc.calculate_allocations(1)[0].status == "watch"


class TestAllocatorGuards:
    @pytest.mark.parametrize("kw", [
        {"min_trades_for_score": 0}, {"min_trades_for_score": 5.0},
        {"min_trades_for_score": True},
        {"explore_period_days": 0}, {"explore_period_days": 30.0},
        {"explore_period_days": True},
        {"base_explore_weight": -0.1}, {"base_explore_weight": 1.2},
        {"base_explore_weight": float("nan")},
    ])
    def test_invalid_config_rejected(self, kw):
        with pytest.raises(ValueError):
            DynamicAllocator(**kw)

    def test_valid_config_accepted(self):
        alloc = DynamicAllocator(min_trades_for_score=10,
                                 explore_period_days=30,
                                 base_explore_weight=0.05)
        assert alloc.min_trades_for_score == 10
        assert alloc.explore_period_days == 30
        assert alloc.base_explore_weight == pytest.approx(0.05)

