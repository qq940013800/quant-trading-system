"""Tests for core.execution.economics_gate —— 边际经济准入纯判断。"""
from __future__ import annotations

import sys
from pathlib import Path

_TRADER_ROOT = Path(__file__).resolve().parents[2]
if str(_TRADER_ROOT) not in sys.path:
    sys.path.insert(0, str(_TRADER_ROOT))

import pytest

from core.execution.economics_gate import economics_gate


def test_gate_passes_when_edge_exceeds_multiple():
    res = economics_gate(expected_edge=10.0, round_trip_cost=2.0,
                         min_edge_multiple=2.0)
    assert res.allowed is True
    assert res.edge_cost_ratio == pytest.approx(5.0)
    assert "≥" in res.reason


def test_gate_rejects_when_edge_below_multiple():
    res = economics_gate(expected_edge=3.0, round_trip_cost=2.0,
                         min_edge_multiple=2.0)
    assert res.allowed is False
    assert res.edge_cost_ratio == pytest.approx(1.5)
    assert "未达" in res.reason


def test_gate_rejects_negative_edge():
    res = economics_gate(expected_edge=-1.0, round_trip_cost=2.0,
                         min_edge_multiple=2.0)
    assert res.allowed is False


def test_gate_zero_cost_allows_positive_edge():
    res = economics_gate(expected_edge=1.0, round_trip_cost=0.0,
                         min_edge_multiple=2.0)
    assert res.allowed is True
    assert res.edge_cost_ratio is None


def test_gate_zero_cost_rejects_non_positive_edge():
    res = economics_gate(expected_edge=0.0, round_trip_cost=0.0,
                         min_edge_multiple=2.0)
    assert res.allowed is False


def test_gate_rejects_non_finite_edge():
    with pytest.raises(ValueError):
        economics_gate(expected_edge=float("nan"), round_trip_cost=2.0)


def test_gate_rejects_negative_cost():
    with pytest.raises(ValueError):
        economics_gate(expected_edge=5.0, round_trip_cost=-1.0)


def test_gate_rejects_multiple_below_one():
    with pytest.raises(ValueError):
        economics_gate(expected_edge=5.0, round_trip_cost=2.0,
                       min_edge_multiple=0.5)


def test_gate_rejects_non_finite_multiple():
    with pytest.raises(ValueError):
        economics_gate(expected_edge=5.0, round_trip_cost=2.0,
                       min_edge_multiple=float("inf"))
