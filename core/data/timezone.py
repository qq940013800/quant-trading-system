"""UTC normalization and broker offset table (DST-aware).

Hard rule 6: the MT5 server offset must come from config / parameters, never
from a hardcoded runtime constant. DATA_INGESTION.md §2: EET brokers run
UTC+2 in winter / UTC+3 in summer, following the US DST switch dates; the
switch-date table must be calibrated per year from the broker's documentation
or the imported feed. This module provides:
  * the deterministic US-DST switch-date rule (second Sunday of March ->
    first Sunday of November),
  * OffsetTable: loaded from a JSON calibration file or a named profile,
  * to_utc(): ts_utc = ts_server - offset, always timezone-aware UTC.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, Tuple

import pandas as pd

log = logging.getLogger("core.data.timezone")

# Real broker offsets are small integers; ±14h covers every live venue.
_MAX_OFFSET_HOURS = 14.0


def _nth_sunday(year: int, month: int, n: int) -> date:
    """Date of the n-th Sunday of a given month."""
    d = date(year, month, 1)
    offset = (6 - d.weekday()) % 7  # days until first Sunday
    return d + timedelta(days=offset + 7 * (n - 1))


def us_dst_switch(year: int) -> Tuple[date, date]:
    """US DST window for a year: second Sunday of March .. first Sunday of November.

    Broker EST/EET server clocks follow this window even though the broker
    sits in Europe; this is the documented convention, not a hardcoded offset.
    """
    start = _nth_sunday(year, 3, 2)
    end = _nth_sunday(year, 11, 1)
    return start, end


class OffsetTable:
    """Per-bar broker offset (hours) between wall-clock server time and UTC.

    The offset is NOT a global constant: it flips on DST switch days. Build
    one from a calibration JSON file (production) or a named profile
    (EET default / GMT0 flat).
    """

    def __init__(
        self,
        profile: str,
        winter_offset_hours: float,
        summer_offset_hours: float,
        transitions: Dict[int, Tuple[date, date]],
    ):
        self.profile = profile
        self.winter_offset_hours = _offset_hours(
            "winter_offset_hours", winter_offset_hours, profile)
        self.summer_offset_hours = _offset_hours(
            "summer_offset_hours", summer_offset_hours, profile)
        # year -> (dst_start, dst_end); [start, end) summer window
        self.transitions = dict(transitions)

    # ------------------------------------------------------------------ build
    @classmethod
    def eet_default(cls, years=None) -> "OffsetTable":
        """Default EET profile (UTC+2 winter / UTC+3 summer, US-DST rule).

        This is a *profile default* for convenience; production ingest must
        point --offset-table at a broker-calibrated JSON (hard rule 6).
        """
        years = list(years) if years is not None else list(range(2023, 2028))
        return cls(
            profile="EET",
            winter_offset_hours=2.0,
            summer_offset_hours=3.0,
            transitions={y: us_dst_switch(y) for y in years},
        )

    @classmethod
    def flat(cls, profile: str, offset_hours: float) -> "OffsetTable":
        """No-DST broker: single constant offset all year."""
        return cls(profile=profile, winter_offset_hours=offset_hours,
                   summer_offset_hours=offset_hours, transitions={})

    @classmethod
    def from_profile(cls, name: str) -> "OffsetTable":
        n = name.strip().upper()
        if n == "EET":
            return cls.eet_default()
        if n in ("GMT0", "UTC", "FLAT0"):
            return cls.flat("GMT0", 0.0)
        raise ValueError(
            f"unknown broker profile {name!r}; use --offset-table for custom brokers"
        )

    @classmethod
    def from_json(cls, path: str) -> "OffsetTable":
        """Load a calibrated table:
        {"profile": "EET-CUSTOM",
         "winter_offset_hours": 2, "summer_offset_hours": 3,
         "transitions": {"2024": ["2024-03-10", "2024-11-03"], ...}}
        """
        cfg = json.loads(Path(path).read_text(encoding="utf-8"))
        missing = {"profile", "winter_offset_hours", "summer_offset_hours"} - set(cfg)
        if missing:
            raise ValueError(f"offset table {path} missing keys: {sorted(missing)}")
        transitions = {}
        for year_s, win in cfg.get("transitions", {}).items():
            y = int(year_s)
            transitions[y] = (
                date.fromisoformat(win[0]),
                date.fromisoformat(win[1]),
            )
        table = cls(
            profile=cfg["profile"],
            winter_offset_hours=cfg["winter_offset_hours"],
            summer_offset_hours=cfg["summer_offset_hours"],
            transitions=transitions,
        )
        log.info("offset table loaded: profile=%s years=%d",
                 table.profile, len(transitions))
        return table

    # ------------------------------------------------------------------ query
    def offset_at(self, ts_server: pd.Timestamp) -> float:
        """Offset (hours) valid at broker wall-clock time ts_server."""
        d = ts_server.date()
        win = self.transitions.get(d.year)
        if win is not None and win[0] <= d < win[1]:
            return self.summer_offset_hours
        return self.winter_offset_hours

    def is_switch_day(self, ts_server: pd.Timestamp) -> bool:
        """True if ts_server falls on a DST start/end calendar day."""
        d = ts_server.date()
        return any(d in win for win in self.transitions.values())


def _offset_hours(field: str, value, profile: str | None = None) -> float:
    """Broker offset guard: must be a finite hour count within ±14h.

    Every live venue sits inside ±14h; a non-finite or absurd value means a
    misconfigured table/profile and would silently shift every UTC stamp
    (AGENTS.md hard rule 6). Fail loudly with the offending field instead.
    """
    try:
        offset = float(value)
    except (TypeError, ValueError):
        raise ValueError(
            f"{field} must be a finite number of hours, got {value!r}"
            + (f" (profile={profile})" if profile is not None else "")
        )
    if not math.isfinite(offset) or abs(offset) > _MAX_OFFSET_HOURS:
        raise ValueError(
            f"{field} out of broker range (|offset| <= 14h, finite), got {value!r}"
            + (f" (profile={profile})" if profile is not None else "")
        )
    return offset


def to_utc(ts_server: pd.Timestamp, offset_hours: float) -> pd.Timestamp:
    """Normalize broker wall-clock (naive) to aware UTC: ts_utc = ts_server - offset.

    Raises if ts_server is already timezone-aware (ambiguous input).
    """
    if ts_server.tz is not None:
        raise ValueError(
            "ts_server must be naive broker wall-clock time",
        )
    offset_hours = _offset_hours("offset_hours", offset_hours)
    return (ts_server - pd.Timedelta(hours=offset_hours)).tz_localize("UTC")
