"""Validation: monotonic UTC stamps, OHLC consistency, gaps, outliers, DST days.

Frozen signature (AI_ML_SYSTEM_DESIGN.md §3.2):
    validate_bars(bars) -> ValidationReport
Hard rule: a missing bar is reported as a Gap, never filled. Filling with
forward/backward information is a look-ahead route and must raise
LookAheadError wherever attempted.
"""
from __future__ import annotations

import logging
from typing import List, Sequence

import numpy as np
import pandas as pd

from .bar import (Bar, Gap, IsolatedBar, Outlier, LookAheadError,
                  ValidationError, ValidationReport)

log = logging.getLogger("core.data.validator")


def _pos_int(name: str, val: int) -> int:
    if isinstance(val, bool) or not isinstance(val, int) or val < 1:
        raise ValidationError(
            f"{name} 必须为 >=1 的整数",
            {"layer": "data.validator", name: val})
    return val


def _positive_finite(name: str, val: float) -> float:
    if isinstance(val, bool) or not isinstance(val, (int, float)) \
            or not np.isfinite(val) or val <= 0:
        raise ValidationError(
            f"{name} 必须为正的有限数值",
            {"layer": "data.validator", name: val})
    return float(val)


def assert_as_of(bars: Sequence[Bar], as_of: pd.Timestamp) -> None:
    """Data-layer causal guard: raise LookAheadError if any bar closes after as_of.

    Features later wrap this with the `as_of` decorator (core/features/base.py);
    the rule itself is enforced here so any data-layer misuse fails loudly.
    """
    offending = [b for b in bars if b.ts_utc > as_of]
    if offending:
        raise LookAheadError(
            f"{len(offending)} bar(s) close after as_of={as_of}",
            {"symbol": offending[0].symbol, "layer": "data.validator",
             "as_of": str(as_of),
             "first_offending_ts": str(offending[0].ts_utc)},
        )


def forbid_future_fill(gap: Gap) -> None:
    """Explicitly refuse any gap fill that uses information around the gap.

    Gap cleaning stays on the approved path (core/gap_normalizer.py -> human
    review -> configs). Calling this on a gap is the sanctioned way to
    document that auto-fill was rejected.
    """
    raise LookAheadError(
        "gap fill with future/adjacent data is forbidden; use gap_normalizer.py",
        {"layer": "data.validator", "gap_start": str(gap.start_utc),
         "gap_end": str(gap.end_utc), "missing_bars": gap.missing_bars},
    )


def validate_bars(
    bars: Sequence[Bar],
    bar_minutes: int = 5,
    outlier_window: int = 50,
    outlier_mult: float = 5.0,
) -> ValidationReport:
    """Validate a loaded bar feed. Parameters come from the caller (CLI/config),
    never from module-level literals (IMPLEMENTATION_SPEC §2)."""
    _pos_int("bar_minutes", bar_minutes)
    _pos_int("outlier_window", outlier_window)
    _positive_finite("outlier_mult", outlier_mult)

    symbol = bars[0].symbol if bars else "UNKNOWN"

    # --- rule 1: strictly increasing ts_utc; corrupt -> hard failure ----------
    prev: pd.Timestamp | None = None
    for b in bars:
        if prev is not None and b.ts_utc <= prev:
            raise ValidationError(
                "ts_utc not strictly increasing (corrupt feed)",
                {"symbol": symbol, "layer": "data.validator",
                 "prev_ts": str(prev), "bad_ts": str(b.ts_utc)},
            )
        prev = b.ts_utc

    # --- rule 2/3/7: isolate bad OHLC, non-positive price, negative spread ----
    isolated: List[IsolatedBar] = []
    usable: List[Bar] = []
    for b in bars:
        reason = None
        if not (b.low <= b.open_ <= b.high and b.low <= b.close <= b.high):
            reason = "bad_ohlc"
        elif b.close <= 0 or b.low < 0:
            reason = "nonpositive_price"
        elif b.spread_points is not None and b.spread_points < 0:
            reason = "negative_spread"
        if reason is None:
            usable.append(b)
        else:
            isolated.append(IsolatedBar(ts_utc=b.ts_utc, reason=reason))

    # --- rule 4: gaps on the UTC grid, detection only, no filling ------------
    gaps: List[Gap] = []
    if len(usable) >= 2:
        step = pd.Timedelta(minutes=bar_minutes)
        cursor = usable[0].ts_utc
        for b in usable[1:]:
            delta = b.ts_utc - cursor
            n_missing = int(round(delta / step)) - 1
            if n_missing > 0:
                gaps.append(Gap(start_utc=cursor, end_utc=b.ts_utc,
                                missing_bars=n_missing))
            cursor = b.ts_utc

    # --- rule 5: outliers from TRAILING rolling std (causal, past window only)
    outliers: List[Outlier] = []
    if len(usable) > outlier_window + 1:
        closes = np.array([b.close for b in usable], dtype=float)
        log_ret = np.log(closes[1:] / closes[:-1])
        # trailing window: std of log_ret[i-outlier_window:i] compared with
        # log_ret[i]; uses only bars strictly before i (no future data).
        for i in range(outlier_window, len(log_ret)):
            win = log_ret[i - outlier_window:i]
            sigma = float(win.std(ddof=1))
            move = float(log_ret[i])
            if sigma > 0 and abs(move) > outlier_mult * sigma:
                outliers.append(Outlier(ts_utc=usable[i + 1].ts_utc,
                                        move=move, threshold=outlier_mult * sigma))

    # --- DST transition days: offset changed between consecutive usable bars -
    dst_days: List[pd.Timestamp] = []
    for a, b in zip(usable, usable[1:]):
        if b.server_offset_hours != a.server_offset_hours:
            dst_days.append(b.ts_utc)

    report = ValidationReport(
        symbol=symbol,
        total_bars=len(bars),
        isolated=tuple(isolated),
        gaps=tuple(gaps),
        dst_transition_days=tuple(dst_days),
        outliers=tuple(outliers),
        duplicate_timestamps=0,  # deduped in loader; kept for report parity
    )
    log.info(
        "symbol=%s validated total=%d isolated=%d gaps=%d dst_days=%d outliers=%d",
        symbol, report.total_bars, report.isolated_count, report.gap_count,
        len(report.dst_transition_days), len(report.outliers),
    )
    return report
