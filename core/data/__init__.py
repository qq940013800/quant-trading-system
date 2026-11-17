"""Data pipeline package: import, validate, UTC-normalize, split, synthesize.

Public contract (AI_ML_SYSTEM_DESIGN.md §3):
    load_bars / validate_bars / split_dataset / make_synthetic_bars
Exceptions: LookAheadError, ValidationError, SilentSetAccessError.
"""
from .bar import (
    Bar,
    DataLayerError,
    Gap,
    IsolatedBar,
    LookAheadError,
    Outlier,
    SilentSetAccessError,
    ValidationError,
    ValidationReport,
)
from .loader import load_bars
from .synthetic import make_synthetic_bars
from .splits import split_dataset
from .timezone import OffsetTable, to_utc
from .validator import assert_as_of, forbid_future_fill, validate_bars

__all__ = [
    "Bar",
    "DataLayerError",
    "Gap",
    "IsolatedBar",
    "LookAheadError",
    "Outlier",
    "SilentSetAccessError",
    "ValidationError",
    "ValidationReport",
    "OffsetTable",
    "to_utc",
    "load_bars",
    "validate_bars",
    "assert_as_of",
    "forbid_future_fill",
    "split_dataset",
    "make_synthetic_bars",
]
