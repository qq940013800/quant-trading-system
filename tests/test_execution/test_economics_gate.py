# -*- coding: utf-8 -*-
"""tests.test_execution.test_economics_gate —— 边际经济准入纯判断单测。"""
from __future__ import annotations

import math

import pytest

from core.execution.economics_gate import economics_gate


def test_pass_when_edge_meets_multiple():
    r = economics_gate(expected_edge=20.0, round_trip_cost=5.0, min_edge_multiple=2.0)
    assert r.allowed is True
    assert r.edge_cost_ratio == pytest.approx(4.0)
    assert r.expected_edge == pytest.approx(20.0)
    assert r.round_trip_cost == pytest.approx(5.0)
    assert r.reason


def test_reject_when_below_multiple():
    r = economics_gate(expected_edge=8.0, round_trip_cost=5.0, min_edge_multiple=2.0)
    assert r.allowed is False
    assert r.edge_cost_ratio == pytest.approx(1.6)


def test_exact_boundary_allowed():
    # edge == multiple*cost，按 >= 边界放行
    r = economics_gate(expected_edge=10.0, round_trip_cost=5.0, min_edge_multiple=2.0)
    assert r.allowed is True
    assert r.edge_cost_ratio == pytest.approx(2.0)


def test_zero_cost_allows_positive_edge():
    r = economics_gate(expected_edge=1.0, round_trip_cost=0.0)
    assert r.allowed is True
    assert r.edge_cost_ratio is None


def test_zero_cost_rejects_nonpositive_edge():
    assert economics_gate(expected_edge=0.0, round_trip_cost=0.0).allowed is False
    assert economics_gate(expected_edge=-1.0, round_trip_cost=0.0).allowed is False


@pytest.mark.parametrize("edge", [math.nan, math.inf, -math.inf])
def test_rejects_nonfinite_edge(edge):
    with pytest.raises(ValueError):
        economics_gate(expected_edge=edge, round_trip_cost=5.0)


@pytest.mark.parametrize("cost", [-1.0, math.nan, math.inf, -math.inf])
def test_rejects_negative_or_nonfinite_cost(cost):
    with pytest.raises(ValueError):
        economics_gate(expected_edge=20.0, round_trip_cost=cost)


@pytest.mark.parametrize("multiple", [0.5, 0.0, math.nan, math.inf])
def test_rejects_multiple_below_one_or_nonfinite(multiple):
    with pytest.raises(ValueError):
        economics_gate(
            expected_edge=20.0, round_trip_cost=5.0, min_edge_multiple=multiple,
        )
