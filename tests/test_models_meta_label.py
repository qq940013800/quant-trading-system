# -*- coding: utf-8 -*-
"""tests/test_models_meta_label.py —— MetaLabeler 分位参数守卫。"""
from __future__ import annotations

import pytest

from core.models.meta_label import MetaLabeler


class _Stub:
    version = "stub"


def _labeler(**kw):
    base = dict(base_model=_Stub(), q_lo=0.30, q_hi=0.70)
    base.update(kw)
    return MetaLabeler(**base)


@pytest.mark.parametrize("bad", [True, "0.3", None, float("nan"),
                                 float("inf"), 0.70, 1.0])
def test_rejects_bad_q_lo(bad):
    with pytest.raises(ValueError):
        _labeler(q_lo=bad)


@pytest.mark.parametrize("bad", [True, "0.7", None, float("nan"),
                                 float("inf"), 0.20, 1.5])
def test_rejects_bad_q_hi(bad):
    with pytest.raises(ValueError):
        _labeler(q_hi=bad)


def test_valid_quantiles_accepted():
    m = _labeler(q_lo=0.25, q_hi=0.75)
    assert m.q_lo == pytest.approx(0.25)
    assert m.q_hi == pytest.approx(0.75)
