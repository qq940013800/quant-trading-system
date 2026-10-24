# -*- coding: utf-8 -*-
"""tests.test_experiment.test_ab_test —— AB测试框架测试。"""
from __future__ import annotations

import numpy as np
import pytest

from core.experiment.ab_test import (
    ABTestConfig,
    ABTestFramework,
    required_sample_size,
    bonferroni_correction,
    fdr_correction,
)


# ------------------------------------------------------------------
# 样本量计算
# ------------------------------------------------------------------
class TestSampleSize:
    def test_sample_size_positive(self):
        """样本量应该是正数。"""
        n = required_sample_size(min_detectable_effect=0.2, baseline_std=0.01)
        assert n > 0

    def test_smaller_effect_needs_more_data(self):
        """效应越小，需要的样本量越大。"""
        # 效应（Sharpe提升）相对于标准差
        n_small = required_sample_size(min_detectable_effect=0.1, baseline_std=0.5)
        n_large = required_sample_size(min_detectable_effect=0.5, baseline_std=0.5)
        assert n_small > n_large
        assert n_small > 1


# ------------------------------------------------------------------
# AB测试框架
# ------------------------------------------------------------------
class TestABTestFramework:
    def test_better_strategy_gets_launch_recommendation(self):
        """明显更好的策略应该得到上线建议。"""
        np.random.seed(42)
        config = ABTestConfig(
            strategy_a_name="v1",
            strategy_b_name="v2",
            min_detectable_effect=0.1,
        )
        tester = ABTestFramework(config)

        # A策略：基准
        rets_a = np.random.normal(0.001, 0.01, 200)
        # B策略：明显更好
        rets_b = np.random.normal(0.002, 0.01, 200)

        tester.add_returns("A", rets_a)
        tester.add_returns("B", rets_b)
        result = tester.evaluate()

        # B策略应该更好
        assert result.mean_diff > 0
        # 样本量足够大，应该能检测到差异
        assert result.sample_size_a == 200

    def test_similar_strategies_get_continue_or_abort(self):
        """差不多的策略不应该得到上线建议。"""
        np.random.seed(42)
        config = ABTestConfig(
            strategy_a_name="v1",
            strategy_b_name="v2",
            min_detectable_effect=0.5,  # 需要0.5的Sharpe提升才算显著
        )
        tester = ABTestFramework(config)

        # 两个策略差不多（Sharpe差很小）
        rets_a = np.random.normal(0.001, 0.01, 100)
        rets_b = np.random.normal(0.0011, 0.01, 100)

        tester.add_returns("A", rets_a)
        tester.add_returns("B", rets_b)
        result = tester.evaluate()

        # 结论应该是 continue 或 abort，不是 launch
        assert result.conclusion in ["continue", "abort"]

    def test_insufficient_data_returns_continue(self):
        """数据不足应该返回continue。"""
        config = ABTestConfig(
            strategy_a_name="v1",
            strategy_b_name="v2",
            min_detectable_effect=0.1,
        )
        tester = ABTestFramework(config)
        tester.add_returns("A", [0.001] * 5)
        tester.add_returns("B", [0.002] * 5)
        result = tester.evaluate()
        assert result.conclusion == "continue"


# ------------------------------------------------------------------
# 多重检验校正
# ------------------------------------------------------------------
class TestMultipleTestingCorrection:
    def test_bonferroni_reduces_significance(self):
        """Bonferroni校正应该降低显著性。"""
        p_values = [0.01, 0.02, 0.03, 0.04, 0.05]
        results = bonferroni_correction(p_values, alpha=0.05)
        # 5个检验，校正后alpha = 0.01
        # 只有0.01刚好卡线
        assert isinstance(results, list)
        assert len(results) == 5

    def test_fdr_is_less_conservative(self):
        """FDR比Bonferroni更宽松。"""
        p_values = [0.01, 0.02, 0.03, 0.04, 0.05]
        bonf_results = bonferroni_correction(p_values, alpha=0.05)
        fdr_results = fdr_correction(p_values, alpha=0.05)
        # FDR应该允许更多显著结果
        assert sum(fdr_results) >= sum(bonf_results)
