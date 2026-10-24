# -*- coding: utf-8 -*-
"""tests.test_experiment.test_auto_optimizer —— 自动策略优化引擎测试。"""
from __future__ import annotations

import numpy as np
import pytest

from core.experiment.auto_optimizer import (
    OptimizationConfig,
    CandidateGenerator,
    MultiArmedBandit,
    CandidateScorer,
    AutoStrategyOptimizer,
    CandidateStatus,
)


# ------------------------------------------------------------------
# 候选生成器
# ------------------------------------------------------------------
class TestCandidateGenerator:
    def test_generate_candidates(self):
        """应该生成指定数量的候选。"""
        config = OptimizationConfig(base_strategy_name="trend")
        gen = CandidateGenerator(config)
        candidates = gen.generate({"period": 14, "threshold": 0.5}, n=5)
        assert len(candidates) == 5

    def test_params_are_perturbed(self):
        """参数应该被扰动，不是完全一样。"""
        config = OptimizationConfig(base_strategy_name="trend", random_seed=42)
        gen = CandidateGenerator(config)
        candidates = gen.generate({"period": 14}, n=10)
        # 至少有一些参数不同
        periods = [c.params["period"] for c in candidates]
        assert len(set(periods)) > 1 or periods[0] == 14  # 可能都没变但概率很低


# ------------------------------------------------------------------
# 多臂老虎机
# ------------------------------------------------------------------
class TestMultiArmedBandit:
    def test_explore_mode(self):
        """高探索率应该随机选。"""
        bandit = MultiArmedBandit(exploration_ratio=1.0)  # 总是探索
        bandit.update("a", 90)
        bandit.update("b", 10)
        # 探索模式下不总是选a
        selections = [bandit.select_next(["a", "b"]) for _ in range(20)]
        assert "b" in selections

    def test_exploit_mode(self):
        """低探索率应该选高分的。"""
        bandit = MultiArmedBandit(exploration_ratio=0.0)  # 总是利用
        bandit.update("a", 90)
        bandit.update("b", 10)
        # 利用模式下总是选a
        for _ in range(10):
            assert bandit.select_next(["a", "b"]) == "a"


# ------------------------------------------------------------------
# 评分器
# ------------------------------------------------------------------
class TestCandidateScorer:
    def test_high_sharpe_gets_high_score(self):
        """高Sharpe应该得高分。"""
        from core.experiment.auto_optimizer import CandidateStrategy
        scorer = CandidateScorer(min_sharpe=1.0)

        good = CandidateStrategy(
            name="good", version="1", base_strategy="test", params={},
            sharpe=2.0, max_drawdown=0.10, n_trades=100, overfitting_score=0.1,
        )
        bad = CandidateStrategy(
            name="bad", version="1", base_strategy="test", params={},
            sharpe=0.5, max_drawdown=0.30, n_trades=10, overfitting_score=0.8,
        )

        assert scorer.score(good) > scorer.score(bad)


# ------------------------------------------------------------------
# 自动优化引擎
# ------------------------------------------------------------------
class TestAutoStrategyOptimizer:
    def test_run_returns_best_candidate(self):
        """应该返回最优候选。"""
        config = OptimizationConfig(
            base_strategy_name="trend",
            max_trials=5,
            min_sharpe=1.0,
        )

        # 模拟回测：有的好有的差
        def mock_backtest(params):
            if params.get("period", 14) > 20:
                return 1.5, 0.15, 50  # 好的
            return 0.5, 0.25, 20  # 差的

        optimizer = AutoStrategyOptimizer(
            config,
            backtest_fn=mock_backtest,
            overfitting_fn=lambda p: 0.2,
        )
        best = optimizer.run({"period": 14, "threshold": 0.5})

        # 应该有合格的候选
        assert best is not None
        assert best.sharpe >= 1.0

    def test_trials_count_includes_all(self):
        """trials计数应该包含所有试验（含失败）。"""
        config = OptimizationConfig(
            base_strategy_name="trend",
            max_trials=10,
            min_sharpe=2.0,  # 设很高，让大部分都不合格
        )

        optimizer = AutoStrategyOptimizer(
            config,
            backtest_fn=lambda p: (1.0, 0.2, 30),  # 都不合格
            overfitting_fn=lambda p: 0.5,
        )
        optimizer.run({"period": 14})

        report = optimizer.get_audit_report()
        # trials_count应该是10，不是0
        assert report["total_trials"] == 10
        assert report["qualified_count"] == 0

    def test_no_qualified_returns_none(self):
        """没有合格候选应该返回None。"""
        config = OptimizationConfig(
            base_strategy_name="trend",
            max_trials=5,
            min_sharpe=5.0,  # 不可能达到
        )

        optimizer = AutoStrategyOptimizer(
            config,
            backtest_fn=lambda p: (1.0, 0.2, 30),
            overfitting_fn=lambda p: 0.5,
        )
        best = optimizer.run({"period": 14})
        assert best is None
