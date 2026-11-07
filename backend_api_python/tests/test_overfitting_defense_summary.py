"""Offline unit tests for the overfitting defense summary endpoint contract.

Run in the backend container or a populated venv; the host interpreter may
lack numpy. These tests cover the empty-sample fallback (frontend renders "--")
and the nested PBO/CPCV/DSR structure returned once a return series is present.
"""
import numpy as np

from app.services.overfitting_defense import (
    OverfittingDefense,
    get_overfitting_defense,
    overfitting_defense,
)


def test_none_and_short_returns_yield_empty_summary():
    defense = OverfittingDefense()

    for sample in (None, [], [0.01], np.array([0.01])):
        summary = defense.get_defense_summary(sample)
        assert summary["has_sample"] is False
        assert summary["overall_pass"] is None
        assert summary["overall_risk_level"] == "unknown"
        assert summary["pbo"]["pbo"] is None
        assert summary["pbo"]["is_overfitted"] is None
        assert summary["cpcv"]["is_stable"] is None
        assert summary["dsr"]["deflated_sharpe"] is None
        assert summary["dsr"]["is_significant"] is None


def test_summary_with_sample_returns_nested_validation_structure():
    rng = np.random.default_rng(42)
    returns = rng.normal(0.0005, 0.01, 120)

    summary = OverfittingDefense().get_defense_summary(returns)

    assert summary["has_sample"] is True
    assert isinstance(summary["overall_pass"], bool)
    assert {"pbo", "cpcv", "dsr", "recommendation"} <= set(summary)

    pbo, cpcv, dsr = summary["pbo"], summary["cpcv"], summary["dsr"]
    assert 0.0 <= pbo["pbo"] <= 1.0
    assert isinstance(pbo["is_overfitted"], bool)
    assert isinstance(cpcv["is_stable"], bool)
    assert isinstance(dsr["deflated_sharpe"], float)
    assert isinstance(dsr["is_significant"], bool)


def test_factory_returns_global_singleton():
    assert get_overfitting_defense() is overfitting_defense
