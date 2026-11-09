# -*- coding: utf-8 -*-
"""test_audit_data_manifest.py —— 数据集 manifest 与内容指纹纯底座单测。"""
from __future__ import annotations

import pytest

from core.audit.data_manifest import (
    DatasetManifest,
    ManifestError,
    build_manifest,
)


def _kwargs(**over):
    base = dict(
        dataset_name="train_xaum5",
        symbol="XAUUSD",
        timeframe="M5",
        n_bars=10_000,
        columns=["time", "open", "high", "low", "close", "volume"],
        first_bar_time="2026-01-01T00:00:00Z",
        last_bar_time="2026-02-01T00:00:00Z",
        source="XAUUSD_M5.csv",
        content_digest="abc123",
    )
    base.update(over)
    return base


def test_build_manifest_fields_and_dict():
    m = build_manifest(**_kwargs())
    assert isinstance(m, DatasetManifest)
    assert m.dataset_name == "train_xaum5"
    assert m.symbol == "XAUUSD"
    assert m.n_bars == 10_000
    assert len(m.columns) == 6
    assert len(m.fingerprint) == 32
    d = m.to_dict()
    assert d["fingerprint"] == m.fingerprint
    assert d["columns"] == list(m.columns)


def test_fingerprint_stable_for_same_input():
    a = build_manifest(**_kwargs())
    b = build_manifest(**_kwargs())
    assert a.fingerprint == b.fingerprint


def test_fingerprint_changes_with_input():
    a = build_manifest(**_kwargs())
    b = build_manifest(**_kwargs(n_bars=9_000))
    assert a.fingerprint != b.fingerprint


def test_content_digest_changes_fingerprint():
    a = build_manifest(**_kwargs(content_digest="abc123"))
    b = build_manifest(**_kwargs(content_digest="def456"))
    assert a.fingerprint != b.fingerprint


def test_columns_dedup_preserves_order():
    m = build_manifest(**_kwargs(columns=["close", "open", "close", "high"]))
    assert m.columns == ("close", "open", "high")


def test_optional_fields_default_none():
    m = build_manifest(
        dataset_name="x", symbol="XAUUSD", timeframe="M5", n_bars=10,
        columns=["close"])
    assert m.first_bar_time is None
    assert m.last_bar_time is None
    assert m.source is None
    assert m.content_digest is None
    assert m.fingerprint


@pytest.mark.parametrize("field", ["dataset_name", "symbol", "timeframe"])
def test_nonempty_string_rejected(field):
    with pytest.raises(ManifestError):
        build_manifest(**_kwargs(**{field: "  "}))


@pytest.mark.parametrize("bad_bars", [-1, True, 1.5, "100", None])
def test_nonneg_int_bars_rejected(bad_bars):
    with pytest.raises(ManifestError):
        build_manifest(**_kwargs(n_bars=bad_bars))


@pytest.mark.parametrize("bad_cols", [[], ["", "close"], "close", 123])
def test_columns_rejected(bad_cols):
    with pytest.raises(ManifestError):
        build_manifest(**_kwargs(columns=bad_cols))


@pytest.mark.parametrize("field", ["first_bar_time", "last_bar_time", "source", "content_digest"])
def test_optional_string_rejected_when_non_str(field):
    with pytest.raises(ManifestError):
        build_manifest(**_kwargs(**{field: 123}))
