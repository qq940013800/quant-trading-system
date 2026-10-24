"""XAUUSD M5 ingest entry point: MT5 CSV -> validate -> UTC-normalize -> CSV.

Usage (from D:\\Trader):
  python scripts/ingest_xauusd.py --data data/raw/mt5/XAUUSD_M5.csv --tz EET \
      --out data/clean/XAUUSD_M5.csv
  python scripts/ingest_xauusd.py --data in.csv --tz-offset-hours 2.0 \
      --out out.csv                       # no-DST broker, constant offset
  python scripts/ingest_xauusd.py --data in.csv --offset-table my_broker.json \
      --out out.csv                       # broker-calibrated DST table

Exit codes: 0 ok; 1 validation/corrupt data; 2 bad arguments.
The broker offset is ALWAYS read from --tz / --offset-table / --tz-offset-hours
— never hardcoded (AGENTS.md hard rule 6).
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.data.bar import DataLayerError, ValidationError  # noqa: E402
from core.data.loader import load_bars  # noqa: E402
from core.data.splits import split_dataset  # noqa: E402
from core.data.timezone import OffsetTable  # noqa: E402
from core.data.validator import validate_bars  # noqa: E402

log = logging.getLogger("scripts.ingest_xauusd")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Ingest XAUUSD M5 MT5 CSV into normalized UTC bars")
    p.add_argument("--data", required=True, help="raw MT5 export CSV path")
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--out", required=True, help="output normalized CSV path")
    p.add_argument("--tz", default="EET",
                   help="named broker profile: EET (UTC+2/+3 US-DST) or GMT0")
    p.add_argument("--offset-table", default=None,
                   help="broker-calibrated offset table JSON (overrides --tz)")
    p.add_argument("--tz-offset-hours", type=float, default=None,
                   help="constant fallback offset for no-DST brokers; required when "
                        "neither --tz nor --offset-table supplies one")
    p.add_argument("--splits", default=None,
                   help="optional split_dates.yaml/json: CLEAN/KNOWN partition")
    p.add_argument("--bar-minutes", type=int, default=5)
    p.add_argument("--outlier-window", type=int, default=50)
    p.add_argument("--outlier-mult", type=float, default=5.0)
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # --- offset resolution: table > profile > constant (never hardcoded) ------
    if args.offset_table:
        table = OffsetTable.from_json(args.offset_table)
        fallback = table.winter_offset_hours
    else:
        table = OffsetTable.from_profile(args.tz)
        fallback = args.tz_offset_hours if args.tz_offset_hours is not None \
            else table.winter_offset_hours

    try:
        bars = load_bars(args.data, args.symbol, fallback, offset_table=table)
        report = validate_bars(
            bars, bar_minutes=args.bar_minutes,
            outlier_window=args.outlier_window, outlier_mult=args.outlier_mult,
        )
    except ValidationError as exc:
        log.error("validation failed: %s", exc)
        return 1
    except DataLayerError as exc:
        log.error("data layer error: %s", exc)
        return 1

    print(f"[ingest] symbol={report.symbol} bars={report.total_bars} "
          f"isolated={report.isolated_count} gaps={report.gap_count} "
          f"dst_days={len(report.dst_transition_days)} "
          f"outliers={len(report.outliers)}")
    if report.gaps:
        first = report.gaps[0]
        print(f"[ingest] first gap: {first.start_utc} -> {first.end_utc} "
              f"({first.missing_bars} bars) — not filled; run gap_normalizer.py")
    if report.isolated:
        reasons = {}
        for iso in report.isolated:
            reasons[iso.reason] = reasons.get(iso.reason, 0) + 1
        print(f"[ingest] isolated: {reasons}")

    # --- optional CLEAN/KNOWN partition (silent set rejected inside) ----------
    if args.splits:
        parts = split_dataset(bars, args.splits)
        print(f"[ingest] split: CLEAN={len(parts['CLEAN'])} "
              f"KNOWN={len(parts['KNOWN'])} HELD_OUT=0 (never read)")

    # --- write normalized CSV (parquet needs pyarrow; absent in base env) ----
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({
        "ts_utc": [b.ts_utc for b in bars],
        "ts_server": [b.ts_server for b in bars],
        "server_offset_hours": [b.server_offset_hours for b in bars],
        "open": [b.open_ for b in bars],
        "high": [b.high for b in bars],
        "low": [b.low for b in bars],
        "close": [b.close for b in bars],
        "tick_volume": [b.tick_volume for b in bars],
        "spread_points": [b.spread_points for b in bars],
    })
    df.to_csv(out, index=False)
    print(f"[ingest] wrote {len(df)} rows -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
