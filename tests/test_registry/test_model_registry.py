# -*- coding: utf-8 -*-
"""tests.test_registry.test_model_registry —— 模型版本快照、状态机与序列化往返。

验证：
1. 注册/查询/按阶段筛选；唯一键冲突拒绝；
2. 阶段状态机合法/非法流转；进入 STAGED 自动冻结；
3. 冻结后拒改 metrics（防事后调标）；
4. to_dict/from_dict 与 load_dict 往返还原。
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from core.registry.model_registry import (
    ModelRegistry,
    ModelStage,
    ModelVersion,
)


def _make(model_id="ml_trend", version="v1.0.0", **kw) -> ModelVersion:
    base = dict(
        model_id=model_id,
        version=version,
        created_at=datetime(2026, 1, 1, tzinfo=None),
        parent_version=None,
        changelog="initial",
        feature_versions=["atr_wilder@v1", "realized_vol@v1"],
        label_spec={"tp_mult": 2.0, "sl_mult": 1.0, "max_holding_bars": 12},
        data_range={"bars_total": 480},
        seed=7,
        code_commit="abc1234",
        hyperparams={"C": 1.0},
        metrics={"accuracy": 0.58, "auc": 0.61},
    )
    base.update(kw)
    return ModelVersion(**base)


class TestRegisterQuery:
    def test_register_and_get(self):
        reg = ModelRegistry()
        reg.register(_make())
        m = reg.get("ml_trend", "v1.0.0")
        assert m is not None
        assert m.stage == ModelStage.CANDIDATE
        assert m.feature_versions == ["atr_wilder@v1", "realized_vol@v1"]

    def test_duplicate_key_rejected(self):
        reg = ModelRegistry()
        reg.register(_make())
        with pytest.raises(ValueError):
            reg.register(_make())

    def test_get_latest_picks_newest(self):
        reg = ModelRegistry()
        reg.register(_make(version="v1.0.0", created_at=datetime(2026, 1, 1)))
        reg.register(_make(version="v1.1.0", created_at=datetime(2026, 2, 1)))
        assert reg.get_latest("ml_trend").version == "v1.1.0"

    def test_list_by_stage_and_production(self):
        reg = ModelRegistry()
        reg.register(_make(version="v1"))
        prod = _make(version="v2")
        prod.transition(ModelStage.STAGED)
        prod.transition(ModelStage.PRODUCTION)
        reg.register(prod)
        assert {m.version for m in reg.list_by_stage(ModelStage.CANDIDATE)} == {"v1"}
        assert [m.version for m in reg.get_production()] == ["v2"]


class TestStageMachine:
    def test_valid_flow_candidate_to_production(self):
        m = _make()
        m.transition(ModelStage.STAGED)
        assert m.is_frozen()  # 进入 staged 自动冻结
        m.transition(ModelStage.PRODUCTION)
        assert m.stage == ModelStage.PRODUCTION

    def test_illegal_jump_rejected(self):
        m = _make()
        with pytest.raises(ValueError):
            m.transition(ModelStage.PRODUCTION)  # candidate 不可直上 production

    def test_retired_is_terminal(self):
        m = _make()
        m.transition(ModelStage.RETIRED)
        with pytest.raises(ValueError):
            m.transition(ModelStage.STAGED)

    def test_archived_can_go_back_to_staged(self):
        m = _make()
        m.transition(ModelStage.STAGED)
        m.transition(ModelStage.PRODUCTION)
        m.transition(ModelStage.ARCHIVED)
        m.transition(ModelStage.STAGED)
        assert m.stage == ModelStage.STAGED

    def test_frozen_metrics_rejected(self):
        m = _make()
        m.update_metrics({"accuracy": 0.55})
        m.transition(ModelStage.STAGED)
        with pytest.raises(ValueError):
            m.update_metrics({"accuracy": 0.70})  # 冻结后事后调标被拒


class TestSerialization:
    def test_round_trip(self):
        reg = ModelRegistry()
        m = _make()
        m.transition(ModelStage.STAGED)
        reg.register(m)
        raw = reg.to_dict()

        reg2 = ModelRegistry()
        n = reg2.load_dict(raw)
        assert n == 1
        restored = reg2.get("ml_trend", "v1.0.0")
        assert restored.stage == ModelStage.STAGED
        assert restored.is_frozen()
        assert restored.metrics == {"accuracy": 0.58, "auc": 0.61}
        assert restored.feature_versions == m.feature_versions
        assert restored.created_at == m.created_at

    def test_load_dict_duplicate_rejected(self):
        reg = ModelRegistry()
        reg.register(_make())
        raw = reg.to_dict()
        with pytest.raises(ValueError):
            reg.load_dict(raw)

    def test_from_dict_stage_enum(self):
        m = _make()
        m.transition(ModelStage.STAGED)
        m.transition(ModelStage.PRODUCTION)
        restored = ModelVersion.from_dict(m.to_dict())
        assert restored.stage == ModelStage.PRODUCTION
