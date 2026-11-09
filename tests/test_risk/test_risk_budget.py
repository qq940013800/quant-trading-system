# -*- coding: utf-8 -*-
"""tests.test_risk.test_risk_budget —— 风险预算 / ERC 风险平价纯逻辑。

覆盖：逆波动风险预算权重、等风险贡献（ERC）权重的归一化、RC 均衡性、
零方差退化兜底与入参守卫。纯内存计算，不触数据库/交易路由。
"""
from __future__ import annotations

import numpy as np
import pytest

from core.risk.risk_budget import (
    risk_budget_weights,
    risk_parity_weights,
)


def _series(seed: int, n: int = 200, scale: float = 0.01) -> list[float]:
    rng = np.random.default_rng(seed)
    return (rng.normal(0.001, scale, n)).tolist()


def _rc_share(weights: dict[str, float], returns: dict[str, list[float]]) -> np.ndarray:
    ids = list(weights.keys())
    matrix = np.array([returns[s] for s in ids], dtype=float)
    cov = np.cov(matrix, ddof=1)
    w = np.array([weights[s] for s in ids])
    mrc = cov @ w
    port_var = float(w @ mrc)
    return (w * mrc) / port_var


class TestRiskBudgetWeights:
    def test_inverse_volatility_lower_weight_for_higher_vol(self):
        w = risk_budget_weights({"a": 0.01, "b": 0.03})
        assert w["b"] < w["a"]
        assert pytest.approx(sum(w.values())) == 1.0

    def test_zero_vol_fallback_equal(self):
        w = risk_budget_weights({"a": 0.0, "b": 0.0})
        assert w == pytest.approx({"a": 0.5, "b": 0.5})


class TestRiskParityWeights:
    def test_weights_sum_to_one_and_nonneg(self):
        returns = {"a": _series(1), "b": _series(2)}
        w = risk_parity_weights(returns)
        assert set(w.keys()) == set(returns.keys())
        assert pytest.approx(sum(w.values())) == 1.0
        assert all(x >= 0.0 for x in w.values())

    def test_equal_risk_contribution_balanced(self):
        returns = {"a": _series(3), "b": _series(4), "c": _series(5)}
        w = risk_parity_weights(returns)
        share = _rc_share(w, returns)
        assert np.max(np.abs(share - 1.0 / 3.0)) < 0.05

    def test_equal_vol_zero_corr_near_half(self):
        returns = {"a": _series(6), "b": _series(7)}
        w = risk_parity_weights(returns)
        assert w["a"] == pytest.approx(0.5, abs=0.12)
        assert w["b"] == pytest.approx(0.5, abs=0.12)

    def test_higher_volatility_gets_lower_weight(self):
        # 零相关近似：ERC 闭式解 w_i ∝ 1/σ_i，高波动列权重应更低。
        returns = {"a": _series(8, scale=0.01), "b": _series(9, scale=0.03)}
        w = risk_parity_weights(returns)
        assert w["b"] < w["a"]

    def test_constant_returns_fallback_equal(self):
        returns = {"a": [0.001] * 100, "b": [0.002] * 100}
        w = risk_parity_weights(returns)
        assert w == pytest.approx({"a": 0.5, "b": 0.5})

    @pytest.mark.parametrize("bad_returns", [
        {"only": _series(10)},
        {"a": _series(11, n=50), "b": _series(12, n=60)},
        {"a": [1.0, np.nan], "b": [0.2, 0.3]},
        {"a": [1.0, np.inf], "b": [0.2, 0.3]},
    ])
    def test_invalid_returns_rejected(self, bad_returns):
        with pytest.raises(ValueError):
            risk_parity_weights(bad_returns)

    @pytest.mark.parametrize("bad", [0, -1, 1.5, True, "100"])
    def test_invalid_max_iter_rejected(self, bad):
        with pytest.raises(ValueError):
            risk_parity_weights({"a": _series(13), "b": _series(14)}, max_iter=bad)

    @pytest.mark.parametrize("bad", [0.0, -0.1, np.nan, np.inf, "tol"])
    def test_invalid_tol_rejected(self, bad):
        with pytest.raises(ValueError):
            risk_parity_weights({"a": _series(15), "b": _series(16)}, tol=bad)
