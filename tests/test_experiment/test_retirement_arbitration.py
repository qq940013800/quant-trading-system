# -*- coding: utf-8 -*-
"""tests.test_experiment.test_retirement_arbitration —— 退役联合裁决接缝测试。"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.audit.evolution_rules import health_score_from_snapshot
from core.experiment.retirement_arbitration import (
    RETIRE_LOW_HEALTH,
    WATCH_LOW_HEALTH,
    DECISION_KEEP,
    DECISION_WATCH,
    DECISION_RETIRE,
    RetirementArbitration,
    arbitrate_retirement,
)


class TestArbitrateRetirement:
    def test_keep_when_healthy_and_lifecycle_keep(self):
        rec = arbitrate_retirement(
            health_score=0.85, health_threshold=0.5,
            lifecycle_recommendation=DECISION_KEEP,
        )
        assert rec.decision == DECISION_KEEP
        assert rec.reasons == []
        assert rec.flags["below_threshold"] == 0.0
        assert rec.flags["in_warn_band"] == 0.0

    def test_keep_when_no_lifecycle_line(self):
        rec = arbitrate_retirement(health_score=0.7, health_threshold=0.5)
        assert rec.decision == DECISION_KEEP
        assert rec.lifecycle_recommendation is None

    def test_retire_on_low_health(self):
        rec = arbitrate_retirement(
            health_score=0.30, health_threshold=0.5,
            lifecycle_recommendation=DECISION_KEEP,
        )
        assert rec.decision == DECISION_RETIRE
        assert RETIRE_LOW_HEALTH in rec.reasons
        assert rec.flags["below_threshold"] == 1.0

    def test_retire_on_lifecycle_recommend_even_if_healthy(self):
        rec = arbitrate_retirement(
            health_score=0.90, health_threshold=0.5,
            lifecycle_recommendation=DECISION_RETIRE,
            lifecycle_reasons=["retire_prolonged_decay"],
        )
        assert rec.decision == DECISION_RETIRE
        assert "retire_prolonged_decay" in rec.reasons
        # 健康分达标，不应附加低健康原因码
        assert RETIRE_LOW_HEALTH not in rec.reasons

    def test_watch_on_health_warn_band(self):
        rec = arbitrate_retirement(
            health_score=0.55, health_threshold=0.5,
            health_warn_line=0.7,
            lifecycle_recommendation=DECISION_KEEP,
        )
        assert rec.decision == DECISION_WATCH
        assert WATCH_LOW_HEALTH in rec.reasons
        assert rec.flags["in_warn_band"] == 1.0

    def test_watch_on_lifecycle_watch_even_if_healthy(self):
        rec = arbitrate_retirement(
            health_score=0.88, health_threshold=0.5,
            lifecycle_recommendation=DECISION_WATCH,
            lifecycle_reasons=["decay_sharpe_down"],
        )
        assert rec.decision == DECISION_WATCH
        assert "decay_sharpe_down" in rec.reasons

    def test_retire_outranks_watch(self):
        # 生命周期 retire 时，即使健康分处于观察带也判 retire
        rec = arbitrate_retirement(
            health_score=0.55, health_threshold=0.5,
            health_warn_line=0.7,
            lifecycle_recommendation=DECISION_RETIRE,
            lifecycle_reasons=["retire_structural_break"],
        )
        assert rec.decision == DECISION_RETIRE

    def test_reasons_dedup_preserve_order(self):
        rec = arbitrate_retirement(
            health_score=0.20, health_threshold=0.5,
            lifecycle_reasons=["decay_sharpe_down", "decay_sharpe_down",
                                "decay_drawdown_excess"],
        )
        assert rec.reasons == [
            RETIRE_LOW_HEALTH, "decay_sharpe_down", "decay_drawdown_excess",
        ]

    def test_to_dict_shape(self):
        rec = arbitrate_retirement(health_score=0.4, health_threshold=0.5)
        d = rec.to_dict()
        assert d["decision"] == DECISION_RETIRE
        assert d["health_score"] == 0.4
        assert d["health_threshold"] == 0.5
        assert "flags" in d and "reasons" in d


class TestArbitrationGuards:
    @pytest.mark.parametrize("score", [-0.1, 1.2, float("nan"), float("inf"), "x"])
    def test_invalid_health_score_raises(self, score):
        with pytest.raises(ValueError):
            arbitrate_retirement(health_score=score, health_threshold=0.5)

    @pytest.mark.parametrize("cutoff", [-0.2, 1.5, None, True])
    def test_invalid_threshold_raises(self, cutoff):
        with pytest.raises(ValueError):
            arbitrate_retirement(health_score=0.6, health_threshold=cutoff)

    def test_warn_line_below_threshold_raises(self):
        with pytest.raises(ValueError):
            arbitrate_retirement(
                health_score=0.6, health_threshold=0.5, health_warn_line=0.4,
            )

    def test_unknown_lifecycle_recommendation_raises(self):
        with pytest.raises(ValueError):
            arbitrate_retirement(
                health_score=0.7, health_threshold=0.5,
                lifecycle_recommendation="liquidate",
            )


class TestSnapshotToArbitrationChain:
    """纯函数链路串联：绩效快照 → 健康分桥接 → 联合裁决（不接线后端）。"""

    @staticmethod
    def _snap(wr: float, pf: float, avg_r: float) -> SimpleNamespace:
        return SimpleNamespace(win_rate=wr, profit_factor=pf, avg_r_multiple=avg_r)

    def test_low_health_snapshot_arbitrates_retire(self):
        score = health_score_from_snapshot(self._snap(0.30, 0.8, 0.2))
        rec = arbitrate_retirement(health_score=score, health_threshold=0.6)
        assert rec.decision == DECISION_RETIRE
        assert RETIRE_LOW_HEALTH in rec.reasons

    def test_healthy_snapshot_arbitrates_keep(self):
        score = health_score_from_snapshot(self._snap(0.58, 1.6, 1.6))
        rec = arbitrate_retirement(health_score=score, health_threshold=0.6)
        assert rec.decision == DECISION_KEEP

    def test_low_health_outranks_lifecycle_watch(self):
        score = health_score_from_snapshot(self._snap(0.30, 0.8, 0.2))
        rec = arbitrate_retirement(
            health_score=score, health_threshold=0.6,
            lifecycle_recommendation=DECISION_WATCH,
            lifecycle_reasons=["decay_sharpe_down"],
        )
        assert rec.decision == DECISION_RETIRE


class TestPackageExport:
    """包级导出闭环：core.experiment 顶层可引用新接缝公共 API。"""

    def test_package_exposes_arbitration_symbols(self):
        import core.experiment as pkg

        assert pkg.arbitrate_retirement is arbitrate_retirement
        assert pkg.RetirementArbitration is RetirementArbitration
        assert pkg.DECISION_KEEP == DECISION_KEEP
        assert pkg.DECISION_WATCH == DECISION_WATCH
        assert pkg.DECISION_RETIRE == DECISION_RETIRE
        assert pkg.RETIRE_LOW_HEALTH == RETIRE_LOW_HEALTH
        assert pkg.WATCH_LOW_HEALTH == WATCH_LOW_HEALTH

    def test_all_exports_resolve(self):
        import core.experiment as pkg

        for name in pkg.__all__:
            assert hasattr(pkg, name), name

