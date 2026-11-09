# -*- coding: utf-8 -*-
"""test_audit_alt_data_availability.py —— 另类数据因果可得性纯判定单测。"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.audit.alt_data_availability import (
    AvailabilityError,
    assess_alt_data_availability,
)

DECISION = "2026-01-01T10:00:00Z"


def _rec(feature_id, published_at, source="news"):
    return {"feature_id": feature_id, "source": source,
            "published_at": published_at, "value": 1.0}


def test_all_available():
    recs = [
        _rec("sentiment_a", "2026-01-01T09:30:00Z"),
        _rec("sentiment_b", "2026-01-01T09:59:00Z"),
    ]
    rep = assess_alt_data_availability(recs, DECISION)
    assert rep.total == 2
    assert rep.available_count == 2
    assert rep.unavailable_count == 0
    assert rep.available is True
    assert rep.violations == ()


def test_future_record_flagged():
    recs = [
        _rec("sentiment_a", "2026-01-01T09:30:00Z"),
        _rec("sentiment_b", "2026-01-01T10:30:00Z"),
    ]
    rep = assess_alt_data_availability(recs, DECISION)
    assert rep.available is False
    assert rep.unavailable_count == 1
    v = rep.violations[0]
    assert v.feature_id == "sentiment_b"
    assert "晚于决策时点" in v.detail


def test_equal_timestamp_is_available():
    rep = assess_alt_data_availability(
        [_rec("x", "2026-01-01T10:00:00Z")], DECISION)
    assert rep.available is True


def test_epoch_numeric_timestamp():
    decision = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc).timestamp()
    past = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc).timestamp()
    future = datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc).timestamp()
    rep_ok = assess_alt_data_availability([_rec("a", past)], decision)
    assert rep_ok.available is True
    rep_bad = assess_alt_data_availability([_rec("a", future)], decision)
    assert rep_bad.available is False


def test_empty_records_available():
    rep = assess_alt_data_availability([], DECISION)
    assert rep.total == 0
    assert rep.available is True


def test_report_to_dict_serializable():
    rep = assess_alt_data_availability(
        [_rec("a", "2026-01-01T10:30:00Z")], DECISION)
    d = rep.to_dict()
    assert d["available"] is False
    assert d["violations"][0]["feature_id"] == "a"


@pytest.mark.parametrize("bad", [123, "not-a-map", None])
def test_non_mapping_record_rejected(bad):
    with pytest.raises(AvailabilityError):
        assess_alt_data_availability([bad], DECISION)


def test_missing_feature_id_rejected():
    with pytest.raises(AvailabilityError):
        assess_alt_data_availability(
            [{"source": "news", "published_at": "2026-01-01T09:00:00Z"}],
            DECISION)


def test_missing_source_rejected():
    with pytest.raises(AvailabilityError):
        assess_alt_data_availability(
            [{"feature_id": "a", "published_at": "2026-01-01T09:00:00Z"}],
            DECISION)


@pytest.mark.parametrize("bad_pub", ["", "not-a-time", float("nan"), True])
def test_invalid_published_at_rejected(bad_pub):
    with pytest.raises(AvailabilityError):
        assess_alt_data_availability([_rec("a", bad_pub)], DECISION)


@pytest.mark.parametrize("bad_decision", ["", "nope", True])
def test_invalid_decision_time_rejected(bad_decision):
    with pytest.raises(AvailabilityError):
        assess_alt_data_availability([_rec("a", "2026-01-01T09:00:00Z")],
                                     bad_decision)
