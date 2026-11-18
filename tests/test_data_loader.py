"""Data-pipeline tests: CSV parsing, UTC normalization, validation rules,
gap detection, quarantine isolation. Golden guard fixtures are not modified.
"""
from __future__ import annotations

import pandas as pd
import pytest

from core.data.bar import Bar, LookAheadError, ValidationError
from core.data.loader import load_bars
from core.data.splits import split_dataset
from core.data.validator import (assert_as_of, forbid_future_fill,
                                 validate_bars)


def test_load_mt5_csv_parses_columns_and_normalizes_utc(mt5_csv, eet_table):
    bars = load_bars(mt5_csv, "XAUUSD", 2.0, offset_table=eet_table)
    assert len(bars) == 5
    b0 = bars[0]
    # server 09:30 EET winter (UTC+2) -> ts_utc 07:30 UTC
    assert b0.ts_utc == pd.Timestamp("2024-01-02 07:30", tz="UTC")
    assert b0.ts_server == pd.Timestamp("2024-01-02 09:30")
    assert b0.server_offset_hours == 2.0
    assert b0.open_ == 2600.0 and b0.close == 2600.5
    assert b0.tick_volume == 100.0 and b0.spread_points == 15.0
    # strictly increasing UTC stamps
    ts = [b.ts_utc for b in bars]
    assert ts == sorted(ts)


def test_bar_rejects_naive_ts_utc():
    with pytest.raises(ValidationError, match="timezone-aware"):
        Bar(symbol="XAUUSD",
            ts_utc=pd.Timestamp("2024-01-02 07:30"),   # naive -> rejected
            ts_server=pd.Timestamp("2024-01-02 09:30"),
            server_offset_hours=2.0,
            open_=1, high=2, low=0.5, close=1.5, tick_volume=1.0)


def test_monotonic_violation_is_hard_failure(syn_bars):
    reversed_bars = list(reversed(syn_bars))
    with pytest.raises(ValidationError, match="not strictly increasing"):
        validate_bars(reversed_bars)


def test_bad_ohlc_is_isolated_not_deleted(syn_bars):
    bad = Bar(symbol=syn_bars[0].symbol,
              ts_utc=syn_bars[-1].ts_utc + pd.Timedelta(minutes=5),
              ts_server=syn_bars[-1].ts_server,
              server_offset_hours=0.0,
              open_=100.0, high=101.0, low=102.0, close=100.5,  # low > high: bad
              tick_volume=1.0)
    report = validate_bars(syn_bars + [bad])
    assert report.total_bars == len(syn_bars) + 1       # kept on record
    assert any(iso.reason == "bad_ohlc" for iso in report.isolated)


def test_gap_detection_lists_missing_bars_never_filled(syn_bars):
    # drop bars index 10 and 11 -> a 2-bar gap on the UTC grid
    kept = syn_bars[:10] + syn_bars[12:]
    report = validate_bars(kept)
    assert report.gap_count >= 1
    gap = report.gaps[0]
    assert gap.missing_bars == 2
    with pytest.raises(LookAheadError, match="forbidden"):
        forbid_future_fill(gap)


def test_duplicate_server_timestamp_deduped(tmp_path, eet_table):
    rows = []
    for ts in ["09:30", "09:30", "09:35"]:  # duplicate first two
        rows.append({"DATE": "2024.01.02", "TIME": ts,
                     "OPEN": 2600.0, "HIGH": 2601.0, "LOW": 2599.0,
                     "CLOSE": 2600.5, "TICKVOL": 100, "VOL": 0, "SPREAD": 15.0})
    p = tmp_path / "dup.csv"
    pd.DataFrame(rows).to_csv(p, index=False)
    bars = load_bars(str(p), "XAUUSD", 2.0, offset_table=eet_table)
    assert len(bars) == 2


def test_missing_spread_is_none_and_negative_spread_is_isolated(mt5_csv, eet_table):
    bars = load_bars(mt5_csv, "XAUUSD", 2.0, offset_table=eet_table)
    assert all(b.spread_points == 15.0 for b in bars)
    neg = Bar(symbol="XAUUSD",
              ts_utc=bars[-1].ts_utc + pd.Timedelta(minutes=5),
              ts_server=bars[-1].ts_server,
              server_offset_hours=2.0,
              open_=1, high=2, low=0.5, close=1.5,
              tick_volume=1.0, spread_points=-3.0)
    report = validate_bars(bars + [neg])
    assert any(iso.reason == "negative_spread" for iso in report.isolated)


def test_assert_as_of_blocks_future_bars(syn_bars):
    mid = syn_bars[30].ts_utc
    assert_as_of(syn_bars[:30], mid)          # exact boundary allowed
    with pytest.raises(LookAheadError):
        assert_as_of(syn_bars, mid)           # future bars inside -> raise


def test_split_dataset_rejects_silent_data_pointer(syn_bars, tmp_path):
    cfg = (
        "clean:\n  - 2023-12-01\n  - 2024-02-01\n"
        "known:\n  - 2024-02-01\n  - 2024-06-01\n"
        "held_out:\n  - 2025-01-01\n  - 2025-06-01\n"
        "held_out_data_path: data/silent/XAUUSD.csv\n"
    )
    p = tmp_path / "split_dates.yaml"
    p.write_text(cfg, encoding="utf-8")
    with pytest.raises(LookAheadError):
        split_dataset(syn_bars, str(p))


def test_split_dataset_partitions_and_never_returns_silent(syn_bars, tmp_path):
    cfg = (
        "clean:\n  - 2023-01-01\n  - 2023-06-01\n"      # excludes all synthetic bars
        "known:\n  - 2023-06-01\n  - 2024-06-01\n"      # covers all synthetic bars
        "held_out:\n  - 2025-01-01\n  - 2025-06-01\n"
    )
    p = tmp_path / "split_dates.yaml"
    p.write_text(cfg, encoding="utf-8")
    parts = split_dataset(syn_bars, str(p))
    assert len(parts["KNOWN"]) == len(syn_bars)
    assert parts["CLEAN"] == []
    assert parts["HELD_OUT"] == []   # silent set never returned


class TestNonFiniteBarIsolation:
    """Non-finite numeric fields must be quarantined, never used as clean bars.

    NaN slips past `low <= open <= high` because every comparison is False, and
    +inf passes the interval check outright; both would poison ATR / returns /
    cost models downstream.
    """

    @staticmethod
    def _append(syn_bars, **overrides):
        base = dict(symbol=syn_bars[0].symbol,
                    ts_utc=syn_bars[-1].ts_utc + pd.Timedelta(minutes=5),
                    ts_server=syn_bars[-1].ts_server,
                    server_offset_hours=0.0,
                    open_=100.0, high=101.0, low=99.0, close=100.5,
                    tick_volume=1.0)
        base.update(overrides)
        return Bar(**base)

    @pytest.mark.parametrize("field, value", [
        ("open_", float("nan")),
        ("high", float("nan")),
        ("low", float("-inf")),
        ("close", float("inf")),
        ("close", float("nan")),
        ("tick_volume", float("inf")),
        ("tick_volume", float("nan")),
    ])
    def test_non_finite_price_or_volume_is_isolated(self, syn_bars, field, value):
        bad = self._append(syn_bars, **{field: value})
        report = validate_bars(syn_bars + [bad])
        assert report.total_bars == len(syn_bars) + 1          # kept on record
        hits = [iso for iso in report.isolated
                if iso.reason == "non_finite_value"]
        assert len(hits) == 1
        assert hits[0].detail == field
        # the poisoned bar never becomes a clean bar
        assert report.total_bars - report.isolated_count == len(syn_bars)

    @pytest.mark.parametrize("value", [float("nan"), float("inf")])
    def test_non_finite_spread_is_isolated(self, syn_bars, value):
        bad = self._append(syn_bars, spread_points=value)
        report = validate_bars(syn_bars + [bad])
        hits = [iso for iso in report.isolated
                if iso.reason == "non_finite_value"]
        assert len(hits) == 1
        assert "spread_points" in hits[0].detail

    def test_non_finite_check_precedes_interval_check(self, syn_bars):
        # high=inf would satisfy low<=open<=high; must be flagged as non-finite,
        # not slip through as a clean bar.
        bad = self._append(syn_bars, high=float("inf"))
        report = validate_bars(syn_bars + [bad])
        assert [iso.reason for iso in report.isolated] == ["non_finite_value"]

    def test_finite_bars_are_not_flagged(self, syn_bars):
        report = validate_bars(syn_bars)
        assert report.isolated_count == 0
        assert not any(iso.reason == "non_finite_value" for iso in report.isolated)

    def test_existing_reasons_keep_empty_detail(self, syn_bars):
        bad = self._append(syn_bars, open_=100.0, high=101.0, low=102.0)
        report = validate_bars(syn_bars + [bad])
        iso = next(i for i in report.isolated if i.reason == "bad_ohlc")
        assert iso.detail == ""


class TestValidatorGuards:
    @pytest.mark.parametrize("kwargs", [
        {"bar_minutes": 0}, {"bar_minutes": -1}, {"bar_minutes": 1.5},
        {"bar_minutes": True},
        {"outlier_window": 0}, {"outlier_window": -2}, {"outlier_window": 3.0},
        {"outlier_window": True},
        {"outlier_mult": 0.0}, {"outlier_mult": -1.0},
        {"outlier_mult": float("nan")}, {"outlier_mult": float("inf")},
        {"outlier_mult": True},
    ])
    def test_invalid_params_rejected(self, syn_bars, kwargs):
        with pytest.raises(ValidationError):
            validate_bars(syn_bars, **kwargs)

    def test_valid_params_accepted(self, syn_bars):
        report = validate_bars(syn_bars, bar_minutes=5,
                               outlier_window=20, outlier_mult=4.0)
        assert report.total_bars == len(syn_bars)


class TestBrokerOffsetGuards:
    """hard rule 6：券商偏移必须显式且合理，一个坏 --tz 不得静默平移整条序列。"""

    @pytest.mark.parametrize("bad", [
        float("nan"), float("inf"), float("-inf"), 99.0, -20.0, "abc",
    ])
    def test_constant_offset_rejected(self, mt5_csv, bad):
        with pytest.raises(ValidationError):
            load_bars(mt5_csv, "XAUUSD", bad)

    def test_constant_offset_in_range_accepted(self, mt5_csv):
        bars = load_bars(mt5_csv, "XAUUSD", 2.0)
        assert len(bars) == 5
        assert bars[0].server_offset_hours == 2.0

    def test_offset_table_wins_over_scalar(self, mt5_csv, eet_table):
        # 表存在时标量只是占位，不应被误拦（既有调用形态不变）
        bars = load_bars(mt5_csv, "XAUUSD", float("nan"), offset_table=eet_table)
        assert len(bars) == 5
        assert bars[0].ts_utc == pd.Timestamp("2024-01-02 07:30", tz="UTC")


class TestCliOffsetContract:
    """两个入口脚本的时区参数不得有默认值（曾经 run_live_data_test 默认 2.0）。"""

    @staticmethod
    def _load_script(name: str):
        import importlib.util
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location(
            f"_cli_contract_{name}", root / "scripts" / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_live_data_test_tz_is_required(self):
        mod = self._load_script("run_live_data_test")
        with pytest.raises(SystemExit):
            mod._build_parser().parse_args(["--csv", "a.csv", "--symbol", "XAUUSD"])
        args = mod._build_parser().parse_args(
            ["--csv", "a.csv", "--symbol", "XAUUSD", "--tz", "3.0"])
        assert args.tz == 3.0

    def test_ingest_has_no_timezone_default(self):
        mod = self._load_script("ingest_xauusd")
        args = mod._build_parser().parse_args(
            ["--data", "in.csv", "--out", "out.csv"])
        assert args.tz is None
        assert args.tz_offset_hours is None
        assert args.offset_table is None

    def test_ingest_without_offset_source_exits(self, tmp_path):
        mod = self._load_script("ingest_xauusd")
        with pytest.raises(SystemExit):
            mod.main(["--data", str(tmp_path / "missing.csv"),
                      "--out", str(tmp_path / "out.csv")])
