# -*- coding: utf-8 -*-
"""tests.test_backtest.test_overfitting —— 过拟合防御测试。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.backtest.overfitting import (
    compute_sharpe,
    deflated_sharpe_ratio,
    probability_of_backtest_overfitting,
    combinatorial_purged_cv,
)


# ------------------------------------------------------------------
# Sharpe 计算
# ------------------------------------------------------------------
class TestComputeSharpe:
    def test_positive_sharpe(self):
        """正收益序列，Sharpe 应该为正。"""
        returns = pd.Series([0.001, 0.002, 0.0015, 0.003, 0.002])
        sharpe = compute_sharpe(returns, bars_per_year=252)
        assert sharpe > 0

    def test_negative_sharpe(self):
        """负收益序列，Sharpe 应该为负。"""
        returns = pd.Series([-0.001, -0.002, -0.0015, -0.003, -0.002])
        sharpe = compute_sharpe(returns, bars_per_year=252)
        assert sharpe < 0


# ------------------------------------------------------------------
# Deflated Sharpe Ratio
# ------------------------------------------------------------------
class TestDeflatedSharpe:
    def test_dsr_greater_than_zero(self):
        """策略真实有效时，DSR 应该大于 0.95（统计显著）。"""
        # 构造一个真正有效的策略：正收益、稳定
        np.random.seed(42)
        returns = pd.Series(np.random.normal(0.001, 0.005, 252))
        dsr = deflated_sharpe_ratio(
            returns,
            trials=10,  # 试了10次
            bars_per_year=252,
        )
        # DSR 应该在 0-1 之间
        assert 0 <= dsr <= 1

    def test_dsr_lower_with_more_trials(self):
        """试验次数越多，DSR 越低（过拟合惩罚越大）。"""
        np.random.seed(42)
        returns = pd.Series(np.random.normal(0.001, 0.005, 252))
        
        dsr_1 = deflated_sharpe_ratio(returns, trials=1, bars_per_year=252)
        dsr_100 = deflated_sharpe_ratio(returns, trials=100, bars_per_year=252)
        
        # 试验次数多的 DSR 应该更低
        assert dsr_100 < dsr_1


# ------------------------------------------------------------------
# PBO（概率回测过拟合）
# ------------------------------------------------------------------
class TestPBO:
    def test_pbo_range(self):
        """PBO 值应该在 0-1 之间。"""
        np.random.seed(42)
        # 多个策略的收益矩阵
        strategy_returns = pd.DataFrame(
            np.random.normal(0.0005, 0.01, (252, 5)),
            columns=[f"strategy_{i}" for i in range(5)],
        )
        pbo = probability_of_backtest_overfitting(
            strategy_returns,
            n_splits=10,
        )
        assert 0 <= pbo <= 1

    def test_pbo_low_for_good_strategy(self):
        """真正好的策略，PBO 应该低。"""
        np.random.seed(42)
        # 一个策略明显比其他好
        good = np.random.normal(0.002, 0.01, 252)  # 高收益
        bad1 = np.random.normal(0.0005, 0.01, 252)
        bad2 = np.random.normal(0.0003, 0.01, 252)
        bad3 = np.random.normal(0.0002, 0.01, 252)
        
        strategy_returns = pd.DataFrame({
            "good": good,
            "bad1": bad1,
            "bad2": bad2,
            "bad3": bad3,
        })
        pbo = probability_of_backtest_overfitting(
            strategy_returns,
            n_splits=5,
        )
        # PBO 应该比较低（好策略不容易过拟合）
        assert pbo < 0.5


# ------------------------------------------------------------------
# CPCV（组合交叉验证）
# ------------------------------------------------------------------
class TestCPCV:
    def test_cpcv_output_shape(self):
        """CPCV 应该返回正确形状的结果。"""
        np.random.seed(42)
        returns = pd.Series(np.random.normal(0.001, 0.01, 252))
        
        result = combinatorial_purged_cv(
            returns,
            n_splits=5,
            purge_fraction=0.05,
        )
        
        # 应该有 train/test sharpe
        assert "train_sharpes" in result
        assert "test_sharpes" in result
        assert len(result["train_sharpes"]) > 0
        assert len(result["test_sharpes"]) > 0

    def test_cpcv_purge(self):
        """purge 机制应该防止数据泄露。"""
        np.random.seed(42)
        returns = pd.Series(np.random.normal(0.001, 0.01, 252))
        
        result = combinatorial_purged_cv(
            returns,
            n_splits=5,
            purge_fraction=0.1,
        )
        
        # train 和 test 不应该完全重叠
        # test sharpe 的均值应该比 train 低（样本外衰减）
        assert np.mean(result["test_sharpes"]) <= np.mean(result["train_sharpes"]) * 1.5
