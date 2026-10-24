"""Timezone/DST tests: offsets come from the table, DST switch dates are
correct, UTC normalization is aware and unambiguous.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from core.data.timezone import OffsetTable, to_utc, us_dst_switch


def test_eet_winter_offset_is_2h(eet_table):
    ts = pd.Timestamp("2024-01-15 10:00")   # winter
    assert eet_table.offset_at(ts) == 2.0


def test_eet_summer_offset_is_3h(eet_table):
    ts = pd.Timestamp("2024-07-15 10:00")   # summer
    assert eet_table.offset_at(ts) == 3.0


def test_us_dst_switch_2024_dates():
    start, end = us_dst_switch(2024)
    assert str(start) == "2024-03-10"   # second Sunday of March
    assert str(end) == "2024-11-03"     # first Sunday of November


def test_offset_changes_on_switch_boundary(eet_table):
    before = pd.Timestamp("2024-03-09 12:00")   # just before switch
    after = pd.Timestamp("2024-03-10 12:00")    # switch day
    assert eet_table.offset_at(before) == 2.0
    assert eet_table.offset_at(after) == 3.0
    assert eet_table.is_switch_day(after)
    assert not eet_table.is_switch_day(before)


def test_offset_comes_from_table_not_hardcoded(tmp_path):
    # A custom broker with weird offsets: result must follow the table,
    # proving no constant 2/3 is baked into lookup logic.
    cfg = {
        "profile": "TEST-BROKER",
        "winter_offset_hours": 4.5,
        "summer_offset_hours": 5.5,
        "transitions": {"2024": ["2024-03-10", "2024-11-03"]},
    }
    p = tmp_path / "broker.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    table = OffsetTable.from_json(str(p))
    assert table.offset_at(pd.Timestamp("2024-01-01 00:00")) == 4.5
    assert table.offset_at(pd.Timestamp("2024-07-01 00:00")) == 5.5


def test_to_utc_is_aware_and_subtracts_offset():
    out = to_utc(pd.Timestamp("2024-01-02 09:30"), 2.0)
    assert out == pd.Timestamp("2024-01-02 07:30", tz="UTC")
    assert out.tz is not None


def test_to_utc_rejects_aware_input():
    with pytest.raises(ValueError):
        to_utc(pd.Timestamp("2024-01-02 09:30", tz="UTC"), 2.0)


def test_flat_profile_no_dst():
    t = OffsetTable.flat("GMT0", 0.0)
    assert t.offset_at(pd.Timestamp("2024-01-01")) == 0.0
    assert t.offset_at(pd.Timestamp("2024-07-01")) == 0.0
