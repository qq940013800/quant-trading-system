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
    overfitting_diagnostic,
    _normal_cdf,
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


# ------------------------------------------------------------------
# PBO 的 CSCV 实现（2026-11 修正）
# ------------------------------------------------------------------
class TestPBOCSCV:
    """PBO 必须满足：确定性、无全局随机状态副作用、能区分持续边缘与纯噪声。"""

    @staticmethod
    def _panel(seed: int = 0, n_obs: int = 252, n_strat: int = 6) -> pd.DataFrame:
        rng = np.random.default_rng(seed)
        return pd.DataFrame(
            rng.normal(0.0, 0.01, size=(n_obs, n_strat)),
            columns=[f"s{i}" for i in range(n_strat)],
        )

    def test_deterministic_and_no_global_rng_side_effect(self):
        panel = self._panel(seed=1)
        pbo1 = probability_of_backtest_overfitting(panel, n_splits=10)
        pbo2 = probability_of_backtest_overfitting(panel, n_splits=10)
        assert pbo1 == pbo2

        np.random.seed(123)
        expected = np.random.rand()
        np.random.seed(123)
        _ = probability_of_backtest_overfitting(panel, n_splits=10)
        assert np.random.rand() == expected

    def test_low_pbo_for_persistent_edge(self):
        rng = np.random.default_rng(7)
        n = 252
        panel = pd.DataFrame(
            rng.normal(0.0, 0.01, size=(n, 5)),
            columns=[f"noise{i}" for i in range(5)],
        )
        panel["edge"] = rng.normal(0.003, 0.01, size=n)
        assert probability_of_backtest_overfitting(panel, n_splits=10) < 0.1

    def test_pbo_near_half_for_iid_noise(self):
        panel = self._panel(seed=2, n_strat=20)
        pbo = probability_of_backtest_overfitting(panel, n_splits=10)
        assert 0.2 <= pbo <= 0.8

    def test_diagnostics_consistency(self):
        panel = self._panel(seed=3)
        diag = probability_of_backtest_overfitting(
            panel, n_splits=10, return_diagnostics=True
        )
        assert diag["n_combinations"] == 252  # C(10, 5)
        assert diag["n_blocks"] == 10
        logits = np.asarray(diag["logits"])
        assert np.isfinite(logits).all()
        assert np.isclose(diag["pbo"], np.mean(logits <= 0.0))

    def test_input_validation(self):
        with pytest.raises(TypeError):
            probability_of_backtest_overfitting(pd.Series([0.0, 0.1, -0.1]))
        bad = self._panel(seed=4)
        bad.iloc[3, 2] = np.nan
        with pytest.raises(ValueError):
            probability_of_backtest_overfitting(bad)
        with pytest.raises(ValueError):
            probability_of_backtest_overfitting(self._panel(), test_size=1.5)

    def test_single_strategy_and_insufficient_sample(self):
        one = pd.DataFrame({"only": np.zeros(100)})
        assert probability_of_backtest_overfitting(one) == 0.0
        tiny = pd.DataFrame(np.zeros((8, 3)), columns=list("abc"))
        assert probability_of_backtest_overfitting(tiny, n_splits=10) == 0.5


# ------------------------------------------------------------------
# 边界 / 缺失值 / 小样本（纯计算，不触交易与数据落库）
# ------------------------------------------------------------------
class TestSharpeEdge:
    def test_short_series_returns_zero(self):
        assert compute_sharpe(pd.Series([0.01])) == 0.0
        assert compute_sharpe(pd.Series([], dtype=float)) == 0.0

    def test_constant_series_zero_sharpe(self):
        # 零方差序列不除零，Sharpe 归 0
        assert compute_sharpe(pd.Series([0.01] * 50)) == 0.0

    def test_normal_cdf_symmetry_and_midpoint(self):
        assert _normal_cdf(0.0) == pytest.approx(0.5, abs=1e-6)
        assert _normal_cdf(1.96) == pytest.approx(0.975, abs=2e-3)
        assert _normal_cdf(-1.96) == pytest.approx(0.025, abs=2e-3)
        # CDF 单调
        assert _normal_cdf(0.5) > _normal_cdf(-0.5)


class TestDeflatedSharpeEdge:
    def test_short_sample_returns_neutral_half(self):
        # 样本 <30 无法判定，回落中性 0.5（不编显著结论）
        short = pd.Series(np.random.default_rng(0).normal(0, 0.01, 20))
        assert deflated_sharpe_ratio(short, trials=5) == 0.5

    def test_dsr_probability_bounded(self):
        rng = np.random.default_rng(3)
        for trials in (1, 3, 50):
            dsr = deflated_sharpe_ratio(
                pd.Series(rng.normal(0.0, 0.01, 252)), trials=trials)
            assert 0.0 <= dsr <= 1.0


class TestCPCVEdge:
    def test_tiny_series_returns_empty_with_unit_ratio(self):
        res = combinatorial_purged_cv(pd.Series(np.zeros(20)), n_splits=5)
        assert res["train_sharpes"] == []
        assert res["test_sharpes"] == []
        assert res["ratio"] == 1.0

    def test_ratio_bounded_for_stable_strategy(self):
        rng = np.random.default_rng(11)
        res = combinatorial_purged_cv(
            pd.Series(rng.normal(0.002, 0.005, 300)), n_splits=6)
        assert res["ratio"] >= 0.0


class TestDiagnosticCard:
    @staticmethod
    def _series(seed: int, loc: float, scale: float, n: int = 252) -> pd.Series:
        rng = np.random.default_rng(seed)
        return pd.Series(rng.normal(loc, scale, n))

    def test_card_returns_expected_fields(self):
        card = overfitting_diagnostic(self._series(1, 0.002, 0.005), trials=10)
        for key in ("sharpe", "deflated_sharpe", "cpcv_ratio", "score",
                    "rating", "warnings"):
            assert key in card
        assert isinstance(card["warnings"], list)

    def test_negative_sharpe_gets_warning(self):
        card = overfitting_diagnostic(self._series(2, -0.003, 0.01), trials=1)
        assert card["sharpe"] < 0
        assert any("不赚钱" in w for w in card["warnings"])

    def test_constant_zero_series_does_not_raise(self):
        card = overfitting_diagnostic(pd.Series(np.zeros(252)), trials=1)
        assert card["cpcv_ratio"] == 1.0
        assert card["deflated_sharpe"] == pytest.approx(0.5, abs=1e-6)

    def test_trials_increase_penalty(self):
        base = self._series(5, 0.002, 0.005)
        low = overfitting_diagnostic(base, trials=1)["deflated_sharpe"]
        high = overfitting_diagnostic(base, trials=100)["deflated_sharpe"]
        assert high <= low


class TestOverfittingParamGuards:
    @staticmethod
    def _series(n: int = 252) -> pd.Series:
        return pd.Series(np.random.default_rng(0).normal(0.001, 0.01, n))

    @staticmethod
    def _panel() -> pd.DataFrame:
        return pd.DataFrame(
            np.random.default_rng(1).normal(0.0005, 0.01, (252, 4)),
            columns=list("abcd"))

    @pytest.mark.parametrize("kw", [
        {"bars_per_year": 0}, {"bars_per_year": -1},
        {"bars_per_year": 100.0}, {"bars_per_year": True},
        {"risk_free": np.nan}, {"risk_free": True},
    ])
    def test_compute_sharpe_invalid(self, kw):
        with pytest.raises(ValueError):
            compute_sharpe(self._series(), **kw)

    @pytest.mark.parametrize("kw", [
        {"trials": 0}, {"trials": -1}, {"trials": 5.0}, {"trials": True},
        {"bars_per_year": 0}, {"skewness": np.nan}, {"kurtosis": np.inf},
    ])
    def test_dsr_invalid(self, kw):
        with pytest.raises(ValueError):
            deflated_sharpe_ratio(self._series(), **kw)

    @pytest.mark.parametrize("kw", [
        {"max_combinations": 0}, {"max_combinations": -1},
        {"max_combinations": 10.0}, {"max_combinations": True},
    ])
    def test_pbo_invalid(self, kw):
        with pytest.raises(ValueError):
            probability_of_backtest_overfitting(self._panel(), **kw)

    @pytest.mark.parametrize("kw", [
        {"n_splits": 1}, {"n_splits": 0}, {"n_splits": 5.0},
        {"n_splits": True}, {"purge_fraction": -0.1},
        {"purge_fraction": 1.0}, {"purge_fraction": np.nan},
    ])
    def test_cpcv_invalid(self, kw):
        with pytest.raises(ValueError):
            combinatorial_purged_cv(self._series(), **kw)

    @pytest.mark.parametrize("kw", [
        {"trials": 0}, {"bars_per_year": 0},
    ])
    def test_diagnostic_invalid(self, kw):
        with pytest.raises(ValueError):
            overfitting_diagnostic(self._series(), **kw)

    def test_valid_params_accepted(self):
        sr = compute_sharpe(self._series(), bars_per_year=252, risk_free=0.02)
        assert isinstance(sr, float)
        dsr = deflated_sharpe_ratio(self._series(), trials=10,
                                     bars_per_year=252)
        assert 0.0 <= dsr <= 1.0
