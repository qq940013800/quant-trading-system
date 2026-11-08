"""Tests for core.risk.risk_budget —— 风险预算分配与相关性熔断纯函数。"""
from __future__ import annotations

import sys
from pathlib import Path

# 让测试可直接 import core 研究层（后端 pytest 默认只挂 backend 根）。
_TRADER_ROOT = Path(__file__).resolve().parents[2]
if str(_TRADER_ROOT) not in sys.path:
    sys.path.insert(0, str(_TRADER_ROOT))

import pytest

from core.risk.risk_budget import (
    average_pairwise_correlation,
    correlation_breaker,
    correlation_pairs,
    risk_budget_weights,
)


# ---------------------------------------------------------------------------
# 风险预算分配
# ---------------------------------------------------------------------------
def test_risk_budget_weights_inverse_volatility():
    weights = risk_budget_weights({"trend": 0.20, "meanrev": 0.10})
    assert abs(sum(weights.values()) - 1.0) < 1e-9
    # 波动高的策略分到更低风险预算
    assert weights["trend"] < weights["meanrev"]


def test_risk_budget_weights_zero_vol_falls_back_to_equal():
    weights = risk_budget_weights({"a": 0.0, "b": 0.0, "c": 0.0})
    assert abs(sum(weights.values()) - 1.0) < 1e-9
    assert all(abs(w - 1.0 / 3.0) < 1e-9 for w in weights.values())


def test_risk_budget_weights_single_strategy():
    weights = risk_budget_weights({"only": 0.15})
    assert weights["only"] == pytest.approx(1.0)


def test_risk_budget_weights_reject_nan_or_negative():
    with pytest.raises(ValueError):
        risk_budget_weights({"a": float("nan")})
    with pytest.raises(ValueError):
        risk_budget_weights({"a": -0.05})
    with pytest.raises(ValueError):
        risk_budget_weights({})


# ---------------------------------------------------------------------------
# 相关性计算
# ---------------------------------------------------------------------------
def test_pearson_perfect_positive():
    returns = {"a": [1.0, 2.0, 3.0, 4.0], "b": [1.0, 2.0, 3.0, 4.0]}
    pairs = correlation_pairs(returns, 0.9)
    assert len(pairs) == 1
    assert pairs[0]["correlation"] == pytest.approx(1.0, abs=1e-6)


def test_pearson_perfect_negative():
    returns = {"a": [1.0, 2.0, 3.0], "b": [-1.0, -2.0, -3.0]}
    pairs = correlation_pairs(returns, 0.9)
    assert pairs == []


def test_average_pairwise_correlation():
    returns = {"a": [1.0, 2.0, 3.0], "b": [1.0, 2.0, 3.0], "c": [1.0, -1.0, 0.0]}
    avg = average_pairwise_correlation(returns)
    assert -1.0 <= avg <= 1.0


def test_correlation_reject_mismatched_length():
    with pytest.raises(ValueError):
        correlation_pairs({"a": [1.0, 2.0], "b": [1.0, 2.0, 3.0]}, 0.5)


def test_correlation_reject_short_series():
    with pytest.raises(ValueError):
        correlation_pairs({"a": [1.0], "b": [1.0]}, 0.5)


def test_correlation_reject_non_finite():
    with pytest.raises(ValueError):
        correlation_pairs({"a": [1.0, float("inf")], "b": [1.0, 2.0]}, 0.5)


# ---------------------------------------------------------------------------
# 相关性熔断
# ---------------------------------------------------------------------------
def test_breaker_triggers_on_high_correlation_pair():
    returns = {"a": [1.0, 2.0, 3.0, 4.0], "b": [1.0, 2.0, 3.0, 4.0]}
    triggered, report = correlation_breaker(
        returns, corr_threshold=0.7, max_avg_corr=0.95
    )
    assert triggered is True
    assert report["high_correlation_pairs"]
    assert any("高相关" in r for r in report["reasons"])


def test_breaker_triggers_on_average_correlation():
    # 两对同向、一对弱相关，平均相关偏高但单对不一定超阈值时也应可触发平均项。
    returns = {
        "a": [1.0, 2.0, 3.0, 4.0],
        "b": [1.0, 2.0, 3.0, 4.0],
        "c": [1.0, 2.0, 3.0, 4.0],
    }
    triggered, report = correlation_breaker(
        returns, corr_threshold=0.99, max_avg_corr=0.30
    )
    assert triggered is True
    assert any("平均成对相关" in r for r in report["reasons"])


def test_breaker_allows_diversified_book():
    returns = {
        "a": [1.0, -1.0, 0.5, -0.5],
        "b": [-1.0, 1.0, -0.5, 0.5],
        "c": [0.2, 0.3, -0.1, 0.05],
    }
    triggered, report = correlation_breaker(
        returns, corr_threshold=0.8, max_avg_corr=0.6
    )
    assert triggered is False
    assert report["high_correlation_pairs"] == []
    assert report["reasons"] == []


def test_breaker_rejects_invalid_thresholds():
    returns = {"a": [1.0, 2.0], "b": [2.0, 1.0]}
    with pytest.raises(ValueError):
        correlation_breaker(returns, corr_threshold=0.0, max_avg_corr=0.5)
    with pytest.raises(ValueError):
        correlation_breaker(returns, corr_threshold=1.5, max_avg_corr=0.5)
    with pytest.raises(ValueError):
        correlation_breaker(returns, corr_threshold=0.5, max_avg_corr=float("nan"))
