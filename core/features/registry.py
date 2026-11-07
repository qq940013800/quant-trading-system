# -*- coding: utf-8 -*-
"""core.features.registry —— 中心化特征注册表（研究-生产同源，阶段 1）。

设计依据：docs/design/design-feature-store.md §4 阶段 1（代码内注册表 + 同源收口）。

第一性原理：
1. **同源**：离线面板（`build_feature_panel`）与在线推理只允许引用注册表内
   同一个函数，不允许存在第二份公式/归一化实现；
2. **集合分离可机检**：统计量类（ATR/波动率/Hurst/分位）登记为 CLEAN，只在
   CLEAN 集估计；结构/形态/供需区类登记为 KNOWN；HELD_OUT（静默集）永不进入
   任何计算输入，注册层直接拒绝；
3. **血缘可还原**：每条目带版本、上游字段、参数、窗长、口径与代码出处，可挂
   接到决策审计记录，还原"哪笔决策用了哪个特征版本"。

边界：本模块只做纯元数据与机检，不引入存储/服务；特征函数仍须经 `@as_of`
因果守卫（见 `core/features/base.py`），注册表不豁免前视纪律。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, Optional

from core.errors import FeatureLayerError

logger = logging.getLogger("core.features.registry")

# BarLike 协议允许的上游字段（与 core/data/bar.py::Bar 对齐）
ALLOWED_UPSTREAM_FIELDS = frozenset({
    "symbol", "ts_utc", "open_", "high", "low", "close",
    "tick_volume", "spread_points",
})

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class FeatureSet(str, Enum):
    """特征集合归属（硬规则 2：集合分离）。"""

    CLEAN = "clean"   # 统计量：ATR/vol/Hurst/分位，只在 CLEAN 集估计
    KNOWN = "known"   # 结构/形态/供需区：只用 KNOWN 集构建
    # HELD_OUT 刻意不入枚举：静默集永不作为任何特征的输入归属。


@dataclass(frozen=True)
class FeatureDefinition:
    """单条特征的不可变元数据快照。

    Attributes
    ----------
    name : 特征唯一标识（snake_case，注册表内唯一）；
    version : 语义化版本（如 "v1"），公式变更须升版本；
    func : 经 `@as_of` 装饰的特征函数 ``func(history, as_of, **params) -> float``；
    upstream_fields : 依赖的 Bar 字段（须为 ALLOWED_UPSTREAM_FIELDS 子集）；
    params : 窗长/倍数等配置参数快照（由调用方配置传入，非绩效网格）；
    window_bars : 满足统计量所需的最小 bar 数（warmup 需求）；None 表示无显式窗；
    set_owner : 集合归属（CLEAN / KNOWN）；
    available_at : 口径说明：取值在哪个时刻可用（默认 bar.close = ts_utc）；
    source : 代码出处（如 "core/features/atr.py::wilder_atr"）；
    description : 特征含义与方向说明。
    """

    name: str
    version: str
    func: Callable
    upstream_fields: tuple[str, ...]
    params: dict[str, Any] = field(default_factory=dict)
    window_bars: Optional[int] = None
    set_owner: FeatureSet = FeatureSet.CLEAN
    available_at: str = "bar.close (= ts_utc)"
    source: str = ""
    description: str = ""

    @property
    def qualified_name(self) -> str:
        """血缘标识：``name@version``。"""
        return f"{self.name}@{self.version}"

    def to_dict(self) -> dict[str, Any]:
        """可序列化元数据（不含可调用对象 func）。"""
        return {
            "name": self.name,
            "version": self.version,
            "qualified_name": self.qualified_name,
            "upstream_fields": list(self.upstream_fields),
            "params": dict(self.params),
            "window_bars": self.window_bars,
            "set_owner": self.set_owner.value,
            "available_at": self.available_at,
            "source": self.source,
            "description": self.description,
        }


def _validate(defn: FeatureDefinition) -> None:
    """注册前机检；违反契约抛 FeatureLayerError（尽早暴露，不静默放行）。"""
    if not isinstance(defn.name, str) or not _NAME_RE.match(defn.name):
        raise FeatureLayerError(
            "feature name must be snake_case", layer="features.registry",
            feature=defn.name)
    if not isinstance(defn.version, str) or not defn.version.strip():
        raise FeatureLayerError("feature version must be a non-empty string",
                                 layer="features.registry", feature=defn.name)
    if not callable(defn.func):
        raise FeatureLayerError("feature func must be callable",
                                layer="features.registry", feature=defn.name)
    if not defn.upstream_fields:
        raise FeatureLayerError("upstream_fields must be non-empty",
                                layer="features.registry", feature=defn.name)
    unknown = set(defn.upstream_fields) - ALLOWED_UPSTREAM_FIELDS
    if unknown:
        raise FeatureLayerError(
            "upstream_fields contain unknown Bar fields",
            layer="features.registry", feature=defn.name, unknown=sorted(unknown))
    if defn.window_bars is not None and (
            not isinstance(defn.window_bars, int) or defn.window_bars < 0):
        raise FeatureLayerError("window_bars must be >= 0 or None",
                                layer="features.registry", feature=defn.name)
    if not isinstance(defn.set_owner, FeatureSet):
        raise FeatureLayerError(
            "set_owner must be FeatureSet.CLEAN/KNOWN; HELD_OUT is forbidden",
            layer="features.registry", feature=defn.name)
    if not isinstance(defn.params, dict):
        raise FeatureLayerError("params must be a dict",
                                layer="features.registry", feature=defn.name)
    if not defn.source:
        raise FeatureLayerError("source (code origin) must be recorded for audit",
                                layer="features.registry", feature=defn.name)


class FeatureRegistry:
    """特征注册表：集中登记元数据，向面板/在线路径同源导出函数。"""

    def __init__(self) -> None:
        self._features: dict[str, FeatureDefinition] = {}

    def register(self, defn: FeatureDefinition) -> FeatureDefinition:
        """登记一条特征；同名重复或契约违反即拒绝。"""
        _validate(defn)
        if defn.name in self._features:
            raise FeatureLayerError(
                "feature already registered (duplicate name)",
                layer="features.registry", feature=defn.name)
        self._features[defn.name] = defn
        return defn

    def has(self, name: str) -> bool:
        return name in self._features

    def get(self, name: str) -> Optional[FeatureDefinition]:
        return self._features.get(name)

    def require(self, name: str) -> FeatureDefinition:
        defn = self._features.get(name)
        if defn is None:
            raise FeatureLayerError("feature not registered",
                                    layer="features.registry", feature=name)
        return defn

    def list_all(self) -> list[FeatureDefinition]:
        return list(self._features.values())

    def by_set(self, owner: FeatureSet) -> list[FeatureDefinition]:
        return [d for d in self._features.values() if d.set_owner == owner]

    def panel_features(self, names: Optional[Iterable[str]] = None) -> dict[str, Callable]:
        """导出 ``{name: func}`` 供 `build_feature_panel` 同源调用。

        names 为 None 时导出全部；否则只导出指定子集，未登记名称报错。
        """
        if names is None:
            selected = list(self._features.values())
        else:
            selected = [self.require(n) for n in names]
        return {d.name: d.func for d in selected}

    def feature_versions(self, names: Optional[Iterable[str]] = None) -> list[str]:
        """血缘标识列表 ``name@version``，供模型/策略版本快照记录。"""
        defs = list(self._features.values()) if names is None else [self.require(n) for n in names]
        return [d.qualified_name for d in defs]

    def to_dict(self) -> dict[str, Any]:
        return {"features": [d.to_dict() for d in self._features.values()]}


def build_default_registry() -> FeatureRegistry:
    """登记当前 `core/features/` 已落地的因果特征（基线目录）。

    集合归属按硬规则 2：统计量 → CLEAN；结构/形态 → KNOWN。
    新特征（P2-2）必须按同一流程在此或调用方注册表登记，方可进入面板/在线路径。
    未精读签名的特征不在此预登记，避免默认目录引入未核对的实现分叉。
    """
    from .atr import wilder_atr
    from .volatility import realized_vol
    from .structure import donchian_position

    registry = FeatureRegistry()

    registry.register(FeatureDefinition(
        name="atr_wilder",
        version="v1",
        func=wilder_atr,
        upstream_fields=("high", "low", "close"),
        params={"period": 14},
        window_bars=15,
        set_owner=FeatureSet.CLEAN,
        source="core/features/atr.py::wilder_atr",
        description="Wilder ATR(14)，波动尺度统计量（CLEAN 集估计）。",
    ))
    registry.register(FeatureDefinition(
        name="realized_vol",
        version="v1",
        func=realized_vol,
        upstream_fields=("close",),
        params={"window": 48},
        window_bars=48,
        set_owner=FeatureSet.CLEAN,
        source="core/features/volatility.py::realized_vol",
        description="滚动已实现波动率（CLEAN 集估计，expanding/rolling 口径）。",
    ))
    registry.register(FeatureDefinition(
        name="donchian_position",
        version="v1",
        func=donchian_position,
        upstream_fields=("high", "low", "close"),
        params={"window": 20},
        window_bars=20,
        set_owner=FeatureSet.KNOWN,
        source="core/features/structure.py::donchian_position",
        description="价格在 Donchian 通道中的相对位置（结构特征，KNOWN 集构建）。",
    ))
    return registry
