"""CLEAN / KNOWN date-range labeling. The HELD_OUT (silent) set never enters
the pipeline — AGENTS.md forbids reading it; DATA_INGESTION.md §6 requires
explicit rejection on the code path.

Frozen signature (AI_ML_SYSTEM_DESIGN.md §3.2):
    split_dataset(bars, splits_path) -> {"CLEAN": [...], "KNOWN": [...], "HELD_OUT": [...]}
HELD_OUT is always returned as an empty list: bars whose dates fall in the
silent window are dropped here and never handed to any downstream stage.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import pandas as pd
import yaml

from .bar import Bar, DataLayerError, SilentSetAccessError

log = logging.getLogger("core.data.splits")

# Any splits file key that points at an actual silent-data file is forbidden:
# we only accept *date ranges*, never pointers to held-out data.
_FORBIDDEN_DATA_KEYS = (
    "held_out_data_path", "heldout_data_path",
    "silent_data_path", "silent_path",
    "held_out_csv", "held_out_parquet",
)


@dataclass(frozen=True)
class SplitConfig:
    clean: Tuple[date, date]     # half-open [start, end)
    known: Tuple[date, date]
    held_out: Tuple[date, date]   # forbidden window; bars here are rejected

    @classmethod
    def from_file(cls, path: str) -> "SplitConfig":
        text = Path(path).read_text(encoding="utf-8")
        cfg = json.loads(text) if path.endswith(".json") else yaml.safe_load(text)

        for key in _FORBIDDEN_DATA_KEYS:
            if key in cfg:
                raise SilentSetAccessError(
                    f"splits file references a held-out data file via {key!r}; "
                    f"the silent set may never be read",
                    {"layer": "data.splits", "splits_path": path, "detail": key},
                )

        try:
            def _d(v) -> date:
                if isinstance(v, datetime):
                    return v.date()
                if isinstance(v, date):
                    return v
                return date.fromisoformat(str(v))
            return cls(
                clean=( _d(cfg["clean"][0]),  _d(cfg["clean"][1])),
                known=( _d(cfg["known"][0]),  _d(cfg["known"][1])),
                held_out=(_d(cfg["held_out"][0]), _d(cfg["held_out"][1])),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise DataLayerError(
                "splits config must define clean/known/held_out [start, end) date pairs",
                {"layer": "data.splits", "splits_path": path, "detail": repr(exc)},
            ) from exc


def split_dataset(
    bars: Sequence[Bar],
    splits_path: str,
) -> Dict[str, List[Bar]]:
    """Partition bars by ts_utc date into CLEAN (statistics/thresholds) and
    KNOWN (structure). HELD_OUT bars are rejected and never returned.
    """
    cfg = SplitConfig.from_file(splits_path)
    clean: List[Bar] = []
    known: List[Bar] = []
    rejected_silent = 0
    for b in bars:
        d = b.ts_utc.date()
        if cfg.clean[0] <= d < cfg.clean[1]:
            clean.append(b)
        elif cfg.known[0] <= d < cfg.known[1]:
            known.append(b)
        elif cfg.held_out[0] <= d < cfg.held_out[1]:
            rejected_silent += 1   # silent window: drop, never expose
    if rejected_silent:
        log.warning("dropped %d bar(s) falling in the HELD_OUT silent window",
                    rejected_silent)
    return {"CLEAN": clean, "KNOWN": known, "HELD_OUT": []}
