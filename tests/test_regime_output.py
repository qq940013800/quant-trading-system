# -*- coding: utf-8 -*-
"""tests/test_regime_output.py —— RegimeOutput 快照类型/有限性守卫。"""
from __future__ import annotations

import pytest

from core.regime.output import RegimeOutput
from core.regime.rules import STATES


def _output(**kw) -> RegimeOutput:
    probs = {s: 1.0 / 3.0 for s in STATES}
    base = dict(state=next(iter(STATES)), probs=probs, version="r-v1")
    base.update(kw)
    return RegimeOutput(**base)


class TestRegimeOutputGuard:
    @pytest.mark.parametrize("bad", ["", "  ", 123, None])
    def test_version_must_be_nonempty_str(self, bad):
        with pytest.raises(ValueError):
            _output(version=bad)

    @pytest.mark.parametrize("bad", ["", "  ", 42])
    def test_threshold_dataset_must_be_nonempty_str(self, bad):
        with pytest.raises(ValueError):
            _output(threshold_dataset=bad)

    @pytest.mark.parametrize("bad", [1, 0, "yes", None])
    def test_degraded_must_be_bool(self, bad):
        with pytest.raises(ValueError):
            _output(degraded=bad)

    def test_valid_output_accepted(self):
        out = _output(degraded=True, threshold_dataset="CLEAN")
        assert out.degraded is True
        assert out.threshold_dataset == "CLEAN"
