"""Shared fixtures for the data-pipeline tests.

Fixtures here build tiny synthetic feeds in temp dirs; the golden causal
guard fixtures under tests/fixtures/causal_guard/ are never modified.
"""
from __future__ import annotations

import pandas as pd
import pytest

from core.data.bar import Bar
from core.data.synthetic import make_synthetic_bars
from core.data.timezone import OffsetTable


@pytest.fixture
def eet_table() -> OffsetTable:
    return OffsetTable.eet_default(years=[2024])


@pytest.fixture
def syn_bars() -> list[Bar]:
    return make_synthetic_bars(seed=42, n=60, kind="martingale")


def _mt5_row(ts_server: str, o: float, h: float, l: float, c: float,
             tv: int = 100, spread: float = 15.0) -> dict:
    d, t = ts_server.split(" ")
    return {"DATE": d, "TIME": t, "OPEN": o, "HIGH": h, "LOW": l,
            "CLOSE": c, "TICKVOL": tv, "VOL": 0, "SPREAD": spread}


@pytest.fixture
def mt5_csv(tmp_path) -> str:
    """A 5-bar MT5-format CSV, all bars in winter EET (UTC+2)."""
    rows = [
        _mt5_row("2024.01.02 09:30", 2600.0, 2601.0, 2599.5, 2600.5),
        _mt5_row("2024.01.02 09:35", 2600.5, 2602.0, 2600.0, 2601.5),
        _mt5_row("2024.01.02 09:40", 2601.5, 2602.5, 2601.0, 2602.0),
        _mt5_row("2024.01.02 09:45", 2602.0, 2603.0, 2601.5, 2602.5),
        _mt5_row("2024.01.02 09:50", 2602.5, 2603.5, 2602.0, 2603.0),
    ]
    path = tmp_path / "XAUUSD_M5_small.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return str(path)
