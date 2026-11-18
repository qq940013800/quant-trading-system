"""CSV -> list[Bar]. MT5 export column mapping, UTC normalization, dedup.

Frozen signature (AI_ML_SYSTEM_DESIGN.md §3.2):
    load_bars(csv_path, symbol, tz_offset_hours) -> list[Bar]
An optional `offset_table` kwarg was added (default None) so DST-aware
brokers need not lie about their offset being constant; the positional
contract is unchanged.
"""
from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import List, Optional

import pandas as pd

from .bar import Bar, ValidationError
from .timezone import OffsetTable, to_utc

log = logging.getLogger("core.data.loader")

# Broker wall-clock/UTC offsets are tiny integers in practice; every live venue
# sits inside ±14h. A non-finite or absurd value means a misconfigured --tz and
# would silently shift *every* UTC stamp (AGENTS.md hard rule 6).
_MAX_OFFSET_HOURS = 14.0


def _validate_constant_offset(value, symbol: str) -> float:
    """Effective constant broker offset, or ValidationError with context."""
    try:
        offset = float(value)
    except (TypeError, ValueError):
        raise ValidationError(
            "tz_offset_hours must be a finite number",
            {"symbol": symbol, "layer": "data.loader", "detail": repr(value)},
        )
    if not math.isfinite(offset) or abs(offset) > _MAX_OFFSET_HOURS:
        raise ValidationError(
            "tz_offset_hours out of broker range (|offset| <= 14h, finite)",
            {"symbol": symbol, "layer": "data.loader", "detail": repr(value)},
        )
    return offset

# MT5 history-center export header (order):
#   DATE TIME OPEN HIGH LOW CLOSE TICKVOL VOL SPREAD
# DATA_INGESTION.md §1 also allows a normalized `timestamp_server` column.
_REQUIRED = ("open", "high", "low", "close")


def _server_stamp(df: pd.DataFrame) -> pd.Series:
    """Resolve the bar server close-time column(s) to a naive datetime Series."""
    cols = {c.lower().strip(): c for c in df.columns}

    ts_col = next((cols[k] for k in ("timestamp_server", "datetime", "time_server")
                   if k in cols), None)
    if ts_col is not None:
        stamp = pd.to_datetime(df[ts_col], errors="raise")
    elif "date" in cols and "time" in cols:
        stamp = pd.to_datetime(
            df[cols["date"]].astype(str) + " " + df[cols["time"]].astype(str),
            format="%Y.%m.%d %H:%M", errors="raise",
        )
    else:
        raise ValidationError(
            "CSV has neither `timestamp_server` nor `DATE`+`TIME` columns",
            {"layer": "data.loader", "detail": f"columns={list(df.columns)}"},
        )

    if stamp.dt.tz is not None:
        raise ValidationError(
            "server timestamps must be naive broker wall-clock; normalize before ingest",
            {"layer": "data.loader"},
        )
    return stamp


def load_bars(
    csv_path: str,
    symbol: str,
    tz_offset_hours: float,
    offset_table: Optional[OffsetTable] = None,
) -> List[Bar]:
    """Read an MT5/normalized CSV into immutable bars on a UTC clock.

    tz_offset_hours: fallback constant offset used when offset_table is None
    (no-DST brokers). DST-aware brokers should pass offset_table; the per-bar
    offset then comes from the table, never from a single global constant.
    """
    path = Path(csv_path)
    if not path.exists():
        raise ValidationError(
            "input CSV not found", {"symbol": symbol, "layer": "data.loader",
                                    "detail": str(path)}
        )
    df = pd.read_csv(path)
    df.columns = [c.lower().strip() for c in df.columns]
    missing = [c for c in _REQUIRED if c not in df.columns]
    if missing:
        raise ValidationError(
            "CSV missing required OHLC columns",
            {"symbol": symbol, "layer": "data.loader", "detail": str(missing)},
        )

    stamp = _server_stamp(df)

    # Duplicate server timestamps: keep first, record count (DATA_INGESTION.md §4).
    dup_mask = stamp.duplicated(keep="first").to_numpy()
    n_dup = int(dup_mask.sum())
    if n_dup:
        log.warning("symbol=%s dropped %d duplicate server timestamps", symbol, n_dup)

    tick_col = "tickvol" if "tickvol" in df.columns else "tick_volume"
    if tick_col not in df.columns:
        raise ValidationError(
            "CSV missing tick_volume", {"symbol": symbol, "layer": "data.loader"}
        )
    spread_col = "spread" if "spread" in df.columns else None

    # Constant fallback offset is only meaningful without an offset table; guard
    # it once so one bad --tz cannot shift the whole feed silently.
    constant_offset = (None if offset_table is not None
                       else _validate_constant_offset(tz_offset_hours, symbol))

    bars: List[Bar] = []
    for i in range(len(df)):
        if dup_mask[i]:
            continue
        ts_server = stamp.iloc[i]
        offset = offset_table.offset_at(ts_server) if offset_table else constant_offset
        ts_utc = to_utc(ts_server, offset)

        spread_raw = df[spread_col].iloc[i] if spread_col else None
        spread: Optional[float]
        if spread_raw is None or pd.isna(spread_raw):
            spread = None
        else:
            spread = float(spread_raw)

        bars.append(Bar(
            symbol=symbol,
            ts_utc=ts_utc,
            ts_server=ts_server,          # naive wall-clock, audit only
            server_offset_hours=offset,
            open_=float(df["open"].iloc[i]),
            high=float(df["high"].iloc[i]),
            low=float(df["low"].iloc[i]),
            close=float(df["close"].iloc[i]),
            tick_volume=float(df[tick_col].iloc[i]),
            spread_points=spread,
        ))

    log.info("symbol=%s loaded=%d bars duplicates_dropped=%d source=%s",
             symbol, len(bars), n_dup, path.name)
    return bars
