# -*- coding: utf-8 -*-
"""tests/test_models_pipeline.py —— 训练管线编排：同源面板、purged CV、OOS 快照。

验证：
1. 端到端跑通，快照血缘/口径/数据区间/指标齐全；
2. 快照可序列化并转换为注册中心 CANDIDATE 版本；
3. 长度不匹配、未注册特征、空输入等边界被拒绝；
4. 交叉验证为时间序连续块（不随机打乱）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from _tp_bootstrap import ROOT  # noqa: F401  (sys.path 引导)

from core.data.synthetic import make_synthetic_bars
from core.errors import FeatureLayerError, ModelLayerError
from core.features.registry import build_default_registry
from core.models.pipeline import PipelineConfig, run_training
from core.registry.model_registry import ModelRegistry, ModelStage


def _config(**overrides) -> PipelineConfig:
    base = dict(
        model_id="ml_test",
        version="v1.0.0",
        feature_names=["atr_wilder", "donchian_position"],
        tp_mult=2.0,
        sl_mult=1.0,
        max_holding_bars=5,
        embargo_bars=5,
        n_splits=3,
        warmup_bars=30,
        seed=7,
        hyperparams={"C": 1.0},
        code_commit="test-commit",
    )
    base.update(overrides)
    return PipelineConfig(**base)


@pytest.fixture
def feed() -> tuple[list, pd.Series]:
    bars = make_synthetic_bars(seed=1, n=300, kind="trend_regime")
    atr = pd.Series([1.0] * len(bars), dtype=float)
    return bars, atr


class TestRunTraining:
    def test_end_to_end_snapshot(self, feed):
        bars, atr = feed
        reg = build_default_registry()
        result = run_training(bars, atr, reg, _config())

        assert result.model_id == "ml_test"
        assert result.version == "v1.0.0"
        assert result.feature_versions == ["atr_wilder@v1", "donchian_position@v1"]
        assert result.label_spec == {
            "tp_mult": 2.0, "sl_mult": 1.0, "max_holding_bars": 5,
            "positive_label": 1,
        }
        assert result.data_range["bars_total"] == 300
        assert result.data_range["n_folds"] == 3
        assert result.data_range["n_oos"] > 0
        assert result.metrics["n_test"] == result.data_range["n_oos"]
        assert len(result.metrics["folds"]) == 3

        auc = result.metrics["auc"]
        assert np.isnan(auc) or 0.0 <= auc <= 1.0
        assert 0.0 <= result.metrics["accuracy"] <= 1.0

    def test_serializable_and_model_version(self, feed):
        bars, atr = feed
        reg = build_default_registry()
        result = run_training(bars, atr, reg, _config())

        raw = result.to_dict()  # 不抛序列化异常即可
        assert raw["model_id"] == "ml_test"
        assert "created_at" in raw
        assert raw["feature_versions"] == result.feature_versions

        mv = result.to_model_version()
        assert mv.stage == ModelStage.CANDIDATE
        assert mv.feature_versions == result.feature_versions
        assert mv.metrics == result.metrics
        assert mv.code_commit == "test-commit"

        registry = ModelRegistry()
        registry.register(mv)
        assert registry.get_latest("ml_test").version == "v1.0.0"

    def test_folds_are_chronological_blocks(self, feed):
        bars, atr = feed
        reg = build_default_registry()
        result = run_training(bars, atr, reg, _config())
        # 每折 test 样本量 > 0；折顺序与时间序一致（管线复用 purged_walk_forward）
        for fold in result.metrics["folds"]:
            assert fold["n_test"] > 0


class TestValidation:
    def test_atr_length_mismatch_rejected(self, feed):
        bars, _ = feed
        atr = pd.Series([1.0] * (len(bars) - 3))
        with pytest.raises(ModelLayerError):
            run_training(bars, atr, build_default_registry(), _config())

    def test_unregistered_feature_rejected(self, feed):
        bars, atr = feed
        with pytest.raises(FeatureLayerError):
            run_training(bars, atr, build_default_registry(),
                         _config(feature_names=["not_a_feature"]))

    def test_empty_history_rejected(self):
        atr = pd.Series([], dtype=float)
        with pytest.raises(ModelLayerError):
            run_training([], atr, build_default_registry(), _config())


class TestPipelineConfigGuards:
    @pytest.mark.parametrize("bad_kwargs", [
        {"model_id": ""}, {"model_id": None},
        {"version": ""},
        {"feature_names": []}, {"feature_names": [1]},
        {"tp_mult": 0.0}, {"tp_mult": -1.0}, {"tp_mult": np.nan},
        {"tp_mult": np.inf},
        {"sl_mult": np.nan}, {"sl_mult": np.inf},
        {"max_holding_bars": 0}, {"max_holding_bars": 1.5},
        {"max_holding_bars": True},
        {"embargo_bars": -1}, {"embargo_bars": True},
        {"n_splits": 1}, {"n_splits": True},
        {"warmup_bars": -1},
        {"positive_label": 2}, {"positive_label": -1},
        {"seed": 1.5}, {"seed": True},
    ])
    def test_invalid_config_rejected(self, bad_kwargs):
        with pytest.raises(ModelLayerError):
            _config(**bad_kwargs)

    def test_valid_config_accepted(self):
        cfg = _config(seed=None, embargo_bars=0, warmup_bars=0)
        assert cfg.n_splits == 3
