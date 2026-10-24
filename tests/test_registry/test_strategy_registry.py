# -*- coding: utf-8 -*-
"""tests.test_registry —— 策略注册表单测。

验证：
1. 策略版本创建与状态转换
2. 参数冻结机制
3. 状态机合法性
4. 注册与查询
5. 版本对比
"""
from __future__ import annotations

from datetime import datetime

import pytest

from core.registry import (
    StrategyRegistry,
    StrategyVersion,
    StrategyStatus,
    PerformanceSnapshot,
)


# ------------------------------------------------------------------
# 测试：策略版本创建
# ------------------------------------------------------------------
class TestStrategyVersion:
    def test_create_draft(self):
        """创建草稿状态的策略。"""
        sv = StrategyVersion(
            strategy_id="trend_breakout",
            version="v1.0.0",
            created_at=datetime.now(),
            parameters={"entry_period": 20, "atr_mult": 2.0},
            description="海龟趋势突破策略",
        )
        assert sv.strategy_id == "trend_breakout"
        assert sv.version == "v1.0.0"
        assert sv.status == StrategyStatus.DRAFT
        assert not sv.is_frozen()

    def test_freeze_parameters(self):
        """冻结参数后不可修改。"""
        sv = StrategyVersion(
            strategy_id="test",
            version="v1.0.0",
            created_at=datetime.now(),
            parameters={"p1": 1.0},
        )
        sv.freeze_parameters()
        assert sv.is_frozen()

    def test_freeze_only_in_draft(self):
        """只有 draft 状态可以冻结参数。"""
        sv = StrategyVersion(
            strategy_id="test",
            version="v1.0.0",
            created_at=datetime.now(),
            parameters={},
        )
        sv.freeze_parameters()
        sv.update_status(StrategyStatus.BACKTEST)

        with pytest.raises(ValueError, match="只有 DRAFT 状态"):
            sv.freeze_parameters()


# ------------------------------------------------------------------
# 测试：状态机
# ------------------------------------------------------------------
class TestStateMachine:
    def test_valid_transitions(self):
        """合法的状态转换。"""
        sv = StrategyVersion(
            strategy_id="test",
            version="v1.0.0",
            created_at=datetime.now(),
            parameters={},
        )

        # draft → backtest
        sv.update_status(StrategyStatus.BACKTEST)
        assert sv.status == StrategyStatus.BACKTEST

        # backtest → paper
        sv.update_status(StrategyStatus.PAPER)
        assert sv.status == StrategyStatus.PAPER

        # paper → live
        sv.update_status(StrategyStatus.LIVE)
        assert sv.status == StrategyStatus.LIVE

        # live → paused
        sv.update_status(StrategyStatus.PAUSED)
        assert sv.status == StrategyStatus.PAUSED

    def test_invalid_transitions(self):
        """非法的状态转换应该报错。"""
        sv = StrategyVersion(
            strategy_id="test",
            version="v1.0.0",
            created_at=datetime.now(),
            parameters={},
        )

        # draft → live（非法）
        with pytest.raises(ValueError, match="非法状态转换"):
            sv.update_status(StrategyStatus.LIVE)

    def test_retired_is_terminal(self):
        """退役是终态，不可恢复。"""
        sv = StrategyVersion(
            strategy_id="test",
            version="v1.0.0",
            created_at=datetime.now(),
            parameters={},
        )
        sv.update_status(StrategyStatus.BACKTEST)
        sv.update_status(StrategyStatus.RETIRED)

        with pytest.raises(ValueError, match="非法状态转换"):
            sv.update_status(StrategyStatus.PAPER)

    def test_backtest_auto_freezes(self):
        """进入回测时自动冻结参数。"""
        sv = StrategyVersion(
            strategy_id="test",
            version="v1.0.0",
            created_at=datetime.now(),
            parameters={"p1": 1.0},
        )
        assert not sv.is_frozen()
        sv.update_status(StrategyStatus.BACKTEST)
        assert sv.is_frozen()


# ------------------------------------------------------------------
# 测试：性能快照
# ------------------------------------------------------------------
class TestPerformance:
    def test_update_performance(self):
        """更新性能快照。"""
        sv = StrategyVersion(
            strategy_id="test",
            version="v1.0.0",
            created_at=datetime.now(),
            parameters={},
        )
        sv.update_status(StrategyStatus.BACKTEST)

        perf = PerformanceSnapshot(
            sharpe=1.5,
            max_drawdown=0.12,
            win_rate=0.45,
            profit_factor=1.8,
            total_trades=100,
        )
        sv.update_performance(perf)
        assert sv.performance is not None
        assert sv.performance.sharpe == 1.5

    def test_cannot_update_performance_in_draft(self):
        """草稿状态不能更新性能。"""
        sv = StrategyVersion(
            strategy_id="test",
            version="v1.0.0",
            created_at=datetime.now(),
            parameters={},
        )
        perf = PerformanceSnapshot()
        with pytest.raises(ValueError, match="不能更新性能"):
            sv.update_performance(perf)


# ------------------------------------------------------------------
# 测试：注册表
# ------------------------------------------------------------------
class TestRegistry:
    def test_register_and_get(self):
        """注册和查询策略。"""
        registry = StrategyRegistry()
        sv = StrategyVersion(
            strategy_id="trend",
            version="v1.0.0",
            created_at=datetime.now(),
            parameters={},
        )
        registry.register(sv)

        got = registry.get("trend", "v1.0.0")
        assert got is not None
        assert got.strategy_id == "trend"

    def test_duplicate_register_fails(self):
        """重复注册应该报错。"""
        registry = StrategyRegistry()
        sv = StrategyVersion(
            strategy_id="trend",
            version="v1.0.0",
            created_at=datetime.now(),
            parameters={},
        )
        registry.register(sv)
        with pytest.raises(ValueError, match="已存在"):
            registry.register(sv)

    def test_get_latest(self):
        """获取最新版本。"""
        registry = StrategyRegistry()

        sv1 = StrategyVersion(
            strategy_id="trend",
            version="v1.0.0",
            created_at=datetime(2024, 1, 1),
            parameters={},
        )
        sv2 = StrategyVersion(
            strategy_id="trend",
            version="v1.1.0",
            created_at=datetime(2024, 2, 1),
            parameters={},
        )
        registry.register(sv1)
        registry.register(sv2)

        latest = registry.get_latest("trend")
        assert latest.version == "v1.1.0"

    def test_get_live(self):
        """获取所有实盘策略。"""
        registry = StrategyRegistry()

        sv1 = StrategyVersion(
            strategy_id="trend",
            version="v1.0.0",
            created_at=datetime.now(),
            parameters={},
        )
        sv1.update_status(StrategyStatus.BACKTEST)

        sv2 = StrategyVersion(
            strategy_id="mr",
            version="v2.0.0",
            created_at=datetime.now(),
            parameters={},
        )
        sv2.update_status(StrategyStatus.BACKTEST)
        sv2.update_status(StrategyStatus.PAPER)
        sv2.update_status(StrategyStatus.LIVE)

        registry.register(sv1)
        registry.register(sv2)

        live = registry.get_live()
        assert len(live) == 1
        assert live[0].strategy_id == "mr"

    def test_compare_versions(self):
        """对比两个版本。"""
        registry = StrategyRegistry()

        sv1 = StrategyVersion(
            strategy_id="trend",
            version="v1.0.0",
            created_at=datetime.now(),
            parameters={"period": 20, "atr_mult": 2.0},
        )
        sv1.update_status(StrategyStatus.BACKTEST)
        sv1.update_performance(PerformanceSnapshot(sharpe=1.2, max_drawdown=0.15))

        sv2 = StrategyVersion(
            strategy_id="trend",
            version="v1.1.0",
            created_at=datetime.now(),
            parameters={"period": 25, "atr_mult": 2.5},
        )
        sv2.update_status(StrategyStatus.BACKTEST)
        sv2.update_performance(PerformanceSnapshot(sharpe=1.5, max_drawdown=0.12))

        registry.register(sv1)
        registry.register(sv2)

        diff = registry.compare_versions("trend", "v1.0.0", "trend", "v1.1.0")
        assert "period" in diff["parameter_diff"]
        assert "sharpe" in diff["performance_diff"]
        assert diff["performance_diff"]["sharpe"]["delta"] == pytest.approx(0.3)
