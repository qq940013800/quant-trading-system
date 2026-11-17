"""Bar schema, data-layer exception hierarchy and ValidationReport.

Frozen contract: AI_ML_SYSTEM_DESIGN.md §3.1 / §3.3.
Bar is the smallest immutable unit of the data layer. ts_utc is the global
primary key and must be timezone-aware UTC (IMPLEMENTATION_SPEC §2).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

log = logging.getLogger("core.data.bar")


class DataLayerError(Exception):
    """Base for data-layer errors. Always carries a context dict
    (symbol / ts_utc / layer / detail) per hard rule 9."""

    def __init__(self, message: str, context: Optional[dict] = None):
        super().__init__(message)
        self.context: dict = dict(context or {})

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.args[0]} | context={self.context}"


class LookAheadError(DataLayerError):
    """A path that would read future data (ts_utc > as_of) was attempted.

    Raised explicitly wherever a future-data route exists (gap filling with
    forward information, feature history containing bars after as_of).
    """


class ValidationError(DataLayerError):
    """Hard data-validation failure (corrupt data, never auto-repaired)."""


class SilentSetAccessError(LookAheadError):
    """Attempt to read the held-out / silent dataset. Forbidden by AGENTS.md."""


@dataclass(frozen=True)
class Bar:
    """Immutable M5 bar. ts_utc is bar.close in UTC (primary key).

    Invariants: low <= open_, close <= high; ts_utc strictly increasing across
    a feed; available_at(bar) == ts_utc (features may only consume bars with
    ts_utc <= current bar ts_utc).
    """

    symbol: str                       # "XAUUSD"
    ts_utc: pd.Timestamp              # bar.close in UTC, timezone-aware
    ts_server: pd.Timestamp           # broker wall-clock (audit only, never computed on)
    server_offset_hours: float        # offset at this bar.close (DST-aware, per bar)
    open_: float                      # USD/oz, XAUUSD quoted to 2 decimals
    high: float
    low: float
    close: float
    tick_volume: float                # MT5 tick_volume: deal-count proxy, NOT real volume
    spread_points: Optional[float] = None  # spread in points; None when unknown

    def __post_init__(self) -> None:
        # Constructor-level hygiene only: naive stamps are forbidden.
        # OHLC consistency is NOT asserted here — invalid bars are isolated by
        # validator.validate_bars() rather than made unconstructible.
        if not isinstance(self.ts_utc, pd.Timestamp):
            raise ValidationError(
                "ts_utc must be a pandas Timestamp",
                {"symbol": self.symbol, "layer": "data.bar",
                 "detail": f"got {type(self.ts_utc)!r}"},
            )
        if self.ts_utc.tz is None:
            raise ValidationError(
                "ts_utc must be timezone-aware UTC (naive stamps are forbidden)",
                {"symbol": self.symbol, "ts_utc": str(self.ts_utc), "layer": "data.bar"},
            )

    @property
    def available_at(self) -> pd.Timestamp:
        """The moment this bar becomes usable by any downstream computation."""
        return self.ts_utc


@dataclass(frozen=True)
class Gap:
    """A missing M5 interval on the UTC grid. Never auto-filled (DATA_INGESTION.md §4)."""

    start_utc: pd.Timestamp
    end_utc: pd.Timestamp
    missing_bars: int


@dataclass(frozen=True)
class IsolatedBar:
    """A bar quarantined by validation (kept on record, excluded from clean use).

    reason: "non_finite_value" | "bad_ohlc" | "nonpositive_price" | "negative_spread"
    detail: 当 reason 需要定位具体字段时（如 non_finite_value）填写命中的字段名，
            逗号分隔；其余理由留空。
    """

    ts_utc: pd.Timestamp
    reason: str
    detail: str = ""


@dataclass(frozen=True)
class Outlier:
    """A bar whose move exceeds outlier_mult x trailing rolling std of log returns."""

    ts_utc: pd.Timestamp
    move: float
    threshold: float


@dataclass(frozen=True)
class ValidationReport:
    """validate_bars output: totals, quarantine list, gaps, DST days, outliers."""

    symbol: str
    total_bars: int
    isolated: tuple[IsolatedBar, ...]
    gaps: tuple[Gap, ...]
    dst_transition_days: tuple[pd.Timestamp, ...]
    outliers: tuple[Outlier, ...]
    duplicate_timestamps: int

    @property
    def isolated_count(self) -> int:
        return len(self.isolated)

    @property
    def gap_count(self) -> int:
        return len(self.gaps)
