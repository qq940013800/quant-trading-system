# -*- coding: utf-8 -*-
"""tests.test_features.test_feature_registry —— 特征注册单机检与同源导出。

验证：
1. 合法条目登记、序列化与血缘标识；
2. 同名重复 / 命名 / 上游字段 / 集合归属等契约违反被拒绝；
3. CLEAN/KNOWN 分组与面板同源导出；
4. 默认目录集合归属正确。
"""
from __future__ import annotations

import pytest

from core.errors import FeatureLayerError
from core.features.registry import (
    FeatureDefinition,
    FeatureRegistry,
    FeatureSet,
    build_default_registry,
)


def _fake_func(history, as_of, **kw):
    return 0.0


def _make(**overrides) -> FeatureDefinition:
    base = dict(
        name="demo_feat",
        version="v1",
        func=_fake_func,
        upstream_fields=("close",),
        params={"period": 14},
        window_bars=15,
        set_owner=FeatureSet.CLEAN,
        source="core/features/demo.py::demo_feat",
        description="demo",
    )
    base.update(overrides)
    return FeatureDefinition(**base)


class TestRegisterValidation:
    def test_register_ok_and_serializable(self):
        reg = FeatureRegistry()
        reg.register(_make())
        defn = reg.require("demo_feat")
        assert defn.qualified_name == "demo_feat@v1"
        d = defn.to_dict()
        assert d["name"] == "demo_feat"
        assert d["set_owner"] == "clean"
        assert "func" not in d  # 序列化不含可调用对象

    def test_duplicate_name_rejected(self):
        reg = FeatureRegistry()
        reg.register(_make())
        with pytest.raises(FeatureLayerError):
            reg.register(_make(version="v2"))

    def test_invalid_name_rejected(self):
        with pytest.raises(FeatureLayerError):
            FeatureRegistry().register(_make(name="DemoFeat"))
        with pytest.raises(FeatureLayerError):
            FeatureRegistry().register(_make(name="1_demo"))

    def test_unknown_upstream_field_rejected(self):
        with pytest.raises(FeatureLayerError):
            FeatureRegistry().register(_make(upstream_fields=("close", "volume")))

    def test_non_callable_rejected(self):
        with pytest.raises(FeatureLayerError):
            FeatureRegistry().register(_make(func=123))

    def test_window_bars_negative_rejected(self):
        with pytest.raises(FeatureLayerError):
            FeatureRegistry().register(_make(window_bars=-1))

    def test_held_out_owner_forbidden(self):
        # HELD_OUT 不是 FeatureSet 成员；传入非法归属必须被机检拒绝。
        with pytest.raises(FeatureLayerError):
            FeatureRegistry().register(_make(set_owner="held_out"))  # type: ignore[arg-type]

    def test_source_required(self):
        with pytest.raises(FeatureLayerError):
            FeatureRegistry().register(_make(source=""))


class TestRegistryQuery:
    def test_by_set_partition(self):
        reg = FeatureRegistry()
        reg.register(_make(name="clean_a", set_owner=FeatureSet.CLEAN))
        reg.register(_make(name="known_a", set_owner=FeatureSet.KNOWN))
        assert {d.name for d in reg.by_set(FeatureSet.CLEAN)} == {"clean_a"}
        assert {d.name for d in reg.by_set(FeatureSet.KNOWN)} == {"known_a"}

    def test_panel_features_all_and_subset(self):
        reg = FeatureRegistry()
        reg.register(_make(name="a"))
        reg.register(_make(name="b"))
        all_panel = reg.panel_features()
        assert set(all_panel) == {"a", "b"}
        subset = reg.panel_features(["a"])
        assert set(subset) == {"a"}
        with pytest.raises(FeatureLayerError):
            reg.panel_features(["missing"])

    def test_feature_versions_lineage(self):
        reg = FeatureRegistry()
        reg.register(_make(name="a", version="v1"))
        reg.register(_make(name="b", version="v2"))
        assert reg.feature_versions() == ["a@v1", "b@v2"]
        assert reg.feature_versions(["b"]) == ["b@v2"]


class TestDefaultRegistry:
    def test_default_has_three_features(self):
        reg = build_default_registry()
        names = {d.name for d in reg.list_all()}
        assert names == {"atr_wilder", "realized_vol", "donchian_position"}

    def test_default_set_owners(self):
        reg = build_default_registry()
        clean = {d.name for d in reg.by_set(FeatureSet.CLEAN)}
        known = {d.name for d in reg.by_set(FeatureSet.KNOWN)}
        assert clean == {"atr_wilder", "realized_vol"}
        assert known == {"donchian_position"}

    def test_default_panel_callables(self):
        panel = build_default_registry().panel_features()
        assert all(callable(f) for f in panel.values())
