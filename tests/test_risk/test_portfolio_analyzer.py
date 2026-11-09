# -*- coding: utf-8 -*-
"""tests.test_risk.test_portfolio_analyzer —— 组合层面风险诊断纯逻辑。

覆盖：双策略相关性矩阵、分散化收益、高相关伪分散化告警、单策略退化为
insufficient_strategies、缺省权重回落 1/n。纯内存计算，不触数据库/交易路由。
"""
from __future__ import annotations

import numpy as np
import pytest

from core.risk.portfolio_analyzer import (
    PortfolioAnalyzer,
    get_portfolio_analyzer,
)


def _returns(seed: int, n: int = 100) -> list[float]:
    rng = np.random.default_rng(seed)
    return rng.normal(0.001, 0.01, n).tolist()


class TestAnalyzePortfolio:
    def test_two_strategies_status_ok(self):
        pa = PortfolioAnalyzer()
        rep = pa.analyze_portfolio(
            {"a": _returns(1), "b": _returns(2)}, {"a": 0.5, "b": 0.5}
        )
        assert rep["status"] == "ok"
        assert rep["num_strategies"] == 2
        # 相关性矩阵 2×2，对角为 1
        matrix = rep["correlation_matrix"]["matrix"]
        assert len(matrix) == 2
        assert matrix[0][0] == pytest.approx(1.0)
        assert matrix[1][1] == pytest.approx(1.0)

    def test_single_strategy_returns_insufficient(self):
        pa = PortfolioAnalyzer()
        rep = pa.analyze_portfolio({"only": _returns(3)}, {"only": 1.0})
        assert rep["status"] == "insufficient_strategies"
        assert "至少需要2个" in rep["message"]

    def test_perfect_negative_correlation_max_diversification(self):
        pa = PortfolioAnalyzer()
        cycle = np.tile([0.01, -0.01], 50)
        rep = pa.analyze_portfolio(
            {"a": cycle.tolist(), "b": (-cycle).tolist()},
            {"a": 0.5, "b": 0.5},
        )
        corr = rep["correlation_matrix"]["matrix"][0][1]
        assert corr == pytest.approx(-1.0, abs=1e-6)
        # 完全负相关 → 波动率对冲，分散化收益上限 100%
        assert rep["diversification_benefit_pct"] == pytest.approx(100.0)

    def test_high_correlation_pair_flagged(self):
        rng = np.random.default_rng(7)
        x = rng.normal(0.0, 0.01, 100)
        b = x + 0.0001 * rng.normal(0.0, 0.001, 100)  # 与 a 近乎同向
        pa = PortfolioAnalyzer()
        rep = pa.analyze_portfolio(
            {"a": x.tolist(), "b": b.tolist()}, {"a": 0.5, "b": 0.5}
        )
        assert len(rep["high_correlation_warnings"]) == 1
        assert "伪分散化" in rep["high_correlation_warnings"][0]["warning"]

    def test_missing_weights_fall_back_to_equal(self):
        pa = PortfolioAnalyzer()
        rep = pa.analyze_portfolio({"a": _returns(4), "b": _returns(5)}, {})
        assert rep["status"] == "ok"
        # 缺省权重 1/n 时组合波动率仍为有限非负
        assert rep["portfolio_volatility"] >= 0.0

    def test_recommendations_list_present(self):
        pa = PortfolioAnalyzer()
        rep = pa.analyze_portfolio({"a": _returns(8), "b": _returns(9)},
                                   {"a": 0.5, "b": 0.5})
        assert isinstance(rep["recommendations"], list)

    def test_factory_singleton(self):
        assert get_portfolio_analyzer() is get_portfolio_analyzer()


class TestAnalyzerBoundary:
    def test_empty_strategies_insufficient(self):
        pa = PortfolioAnalyzer()
        rep = pa.analyze_portfolio({}, {})
        assert rep["status"] == "insufficient_strategies"

    def test_constant_returns_zero_variance_does_not_crash(self):
        """零方差序列：组合波动率为 0，分散化收益回落 0，不除零崩溃。"""
        pa = PortfolioAnalyzer()
        const = [0.01] * 50
        # 常数序列触发 corrcoef 除零 RuntimeWarning；degernate 输入下告警可忽略
        with np.errstate(invalid="ignore", divide="ignore"):
            rep = pa.analyze_portfolio({"a": const, "b": const},
                                       {"a": 0.5, "b": 0.5})
        assert rep["status"] == "ok"
        assert rep["portfolio_volatility"] == 0.0
        assert rep["diversification_benefit_pct"] == 0.0

    def test_three_strategies_matrix_is_three_by_three(self):
        pa = PortfolioAnalyzer()
        rep = pa.analyze_portfolio(
            {"a": [0.01, -0.02] * 25, "b": [0.02, -0.01] * 25,
             "c": [0.015, -0.015] * 25},
            {"a": 0.34, "b": 0.33, "c": 0.33},
        )
        assert rep["num_strategies"] == 3
        matrix = rep["correlation_matrix"]["matrix"]
        assert len(matrix) == 3
        assert all(len(row) == 3 for row in matrix)
        assert set(rep["risk_budget"].keys()) == {"a", "b", "c"}


def _near_identical_pair() -> tuple[list[float], list[float]]:
    rng = np.random.default_rng(7)
    x = rng.normal(0.0, 0.01, 100)
    b = x + 0.0001 * rng.normal(0.0, 0.001, 100)
    return x.tolist(), b.tolist()


class TestHighCorrThreshold:
    def test_threshold_one_suppresses_warning(self):
        pa = PortfolioAnalyzer()
        a, b = _near_identical_pair()
        rep = pa.analyze_portfolio(
            {"a": a, "b": b}, {"a": 0.5, "b": 0.5},
            high_corr_threshold=1.0,
        )
        # 相关系数严格 < 1.0，阈值 1.0 不触发告警
        assert rep["high_correlation_warnings"] == []

    def test_low_threshold_flags_near_identical_pair(self):
        pa = PortfolioAnalyzer()
        a, b = _near_identical_pair()
        rep = pa.analyze_portfolio(
            {"a": a, "b": b}, {"a": 0.5, "b": 0.5},
            high_corr_threshold=0.3,
        )
        assert len(rep["high_correlation_warnings"]) == 1

    @pytest.mark.parametrize("bad", [0.0, 1.5, float("nan"), "not-a-number"])
    def test_invalid_threshold_falls_back_to_default(self, bad):
        pa = PortfolioAnalyzer()
        a, b = _near_identical_pair()
        rep = pa.analyze_portfolio(
            {"a": a, "b": b}, {"a": 0.5, "b": 0.5},
            high_corr_threshold=bad,
        )
        # 非法/越界阈值回退默认 0.7，近乎同向对仍告警，且不崩溃
        assert rep["status"] == "ok"
        assert len(rep["high_correlation_warnings"]) == 1


class TestAnalyzerInputGuards:
    def _pair(self):
        return {"a": _returns(1), "b": _returns(2)}, {"a": 0.5, "b": 0.5}

    def test_returns_must_be_dict(self):
        pa = PortfolioAnalyzer()
        with pytest.raises(ValueError):
            pa.analyze_portfolio(["a", "b"], {"a": 0.5})

    def test_weights_must_be_dict(self):
        pa = PortfolioAnalyzer()
        returns, _ = self._pair()
        with pytest.raises(ValueError):
            pa.analyze_portfolio(returns, [0.5, 0.5])

    @pytest.mark.parametrize("bad", ["not-a-seq", {"x": 1.0}])
    def test_returns_series_must_be_sequence(self, bad):
        pa = PortfolioAnalyzer()
        with pytest.raises(ValueError):
            pa.analyze_portfolio({"a": bad, "b": _returns(2)}, {"a": 0.5, "b": 0.5})

    @pytest.mark.parametrize("bad", [np.nan, np.inf, True, "0.01", None])
    def test_return_element_must_be_finite_num(self, bad):
        pa = PortfolioAnalyzer()
        with pytest.raises(ValueError):
            pa.analyze_portfolio({"a": [0.01, bad], "b": [0.02, -0.01]},
                                 {"a": 0.5, "b": 0.5})

    @pytest.mark.parametrize("bad", [np.nan, np.inf, True, "0.5"])
    def test_weight_must_be_finite_num(self, bad):
        pa = PortfolioAnalyzer()
        with pytest.raises(ValueError):
            pa.analyze_portfolio({"a": _returns(1), "b": _returns(2)},
                                {"a": bad, "b": 0.5})

    def test_weight_key_must_match_returns(self):
        pa = PortfolioAnalyzer()
        with pytest.raises(ValueError):
            pa.analyze_portfolio({"a": _returns(1), "b": _returns(2)},
                                 {"a": 0.5, "b": 0.5, "ghost": 0.2})
