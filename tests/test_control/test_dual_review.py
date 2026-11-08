# -*- coding: utf-8 -*-
"""tests.test_control.test_dual_review —— 双人复核独立批准人纯校验单测。"""
from __future__ import annotations

import pytest

from core.control.dual_review import evaluate_dual_review


def test_two_distinct_pass():
    res = evaluate_dual_review(["alice", "bob"])
    assert res.allowed is True
    assert res.reason_code == "dual_review_passed"
    assert res.audit["unique_count"] == 2


def test_single_reviewer_rejected():
    res = evaluate_dual_review(["alice"])
    assert not res.allowed
    assert res.reason_code == "single_reviewer"


def test_no_approvers_rejected():
    res = evaluate_dual_review([])
    assert not res.allowed
    assert res.reason_code == "no_approvers"
    assert res.audit["unique_count"] == 0


def test_duplicates_and_blank_collapse_to_one():
    res = evaluate_dual_review(["alice", "alice", "  alice  "])
    assert not res.allowed
    assert res.reason_code == "single_reviewer"
    assert res.audit["unique_approvers"] == ["alice"]


def test_none_and_blank_filtered():
    res = evaluate_dual_review([None, "", "   ", "bob"])
    assert not res.allowed
    assert res.reason_code == "single_reviewer"
    assert res.audit["unique_approvers"] == ["bob"]


def test_insufficient_for_three_required():
    res = evaluate_dual_review(["a", "b"], required_count=3)
    assert not res.allowed
    assert res.reason_code == "insufficient_reviewers"


def test_required_count_one_single_passes():
    res = evaluate_dual_review(["a"], required_count=1)
    assert res.allowed is True
    assert res.reason_code == "dual_review_passed"


def test_audit_preserves_unique_order():
    res = evaluate_dual_review(["bob", "alice", "bob"])
    assert res.audit["unique_approvers"] == ["bob", "alice"]


@pytest.mark.parametrize("bad_count", [0, -1, True, 2.5, "2"])
def test_invalid_required_count_raises(bad_count):
    with pytest.raises(ValueError):
        evaluate_dual_review(["a", "b"], required_count=bad_count)


@pytest.mark.parametrize("bad_input", ["alice", {"a": 1}, 12345])
def test_non_sequence_rejected(bad_input):
    with pytest.raises(ValueError):
        evaluate_dual_review(bad_input)
