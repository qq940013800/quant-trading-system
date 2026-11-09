# -*- coding: utf-8 -*-
"""core.registry.model_registry —— ML 模型版本注册中心（阶段 1，纯内存快照）。

设计依据：docs/design/design-mlops-experiment.md §4 阶段 1（注册表快照补强 +
实验纪律收口）。与 `core.registry.strategy_registry`（策略版本）区分：本注册中心
登记 **ML 模型产物元数据**——特征版本血缘、标签口径、数据区间、随机种子、代码
commit、OOS 指标、父版本与制品占位。

第一性原理：
1. **版本可还原**：任一注册版本可还原参数、特征版本、commit、数据区间、种子、
   基准指标与父版本；快照全部字段可序列化；
2. **阶段流转受控**：CANDIDATE → STAGED → PRODUCTION → ARCHIVED / RETIRED，
   非法转换拒绝；进入 STAGED 后关键快照冻结，不允许热改；
3. **制品留占位**：当前仓库无训练制品（无 .pkl/.joblib/.onnx/.pt），
   `artifact_uri` / `artifact_checksum` 为占位字段；出现真实产物后再挂制品库
   （阶段 3，见设计文档）。

边界：纯数据类，不连数据库、不写 `registry.yaml`；trials 计数与规则冻结由
实验脚本/审计账本负责（AGENTS.md 规则 11），本模块不替代实验纪律。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger("core.registry.model")


def _nonempty_str(name: str, val: object) -> str:
    if not isinstance(val, str) or not val.strip():
        raise ValueError(f"{name} 必须为非空字符串，收到 {val!r}")
    return val


def _opt_str(name: str, val: object) -> Optional[str]:
    if val is not None and not isinstance(val, str):
        raise ValueError(f"{name} 必须为字符串或 None，收到 {val!r}")
    return val


def _dict(name: str, val: object) -> dict:
    if not isinstance(val, dict):
        raise ValueError(f"{name} 必须为 dict，收到 {type(val).__name__}")
    return val


def _str_list(name: str, val: object) -> list:
    if not isinstance(val, list) or any(
            not isinstance(x, str) or not x.strip() for x in val):
        raise ValueError(f"{name} 必须为非空字符串列表，收到 {val!r}")
    return val


class ModelStage(Enum):
    """模型阶段状态机（严格流转，禁跨级跳实盘）。"""

    CANDIDATE = "candidate"      # 训练产出，未评审
    STAGED = "staged"            # paper/评审通过，待上线
    PRODUCTION = "production"    # 在线运行
    ARCHIVED = "archived"        # 下线归档（可回滚到 staged）
    RETIRED = "retired"          # 终态：永久退役

    @classmethod
    def can_transition(cls, from_stage: "ModelStage",
                       to_stage: "ModelStage") -> bool:
        valid = {
            cls.CANDIDATE: {cls.STAGED, cls.RETIRED},
            cls.STAGED: {cls.PRODUCTION, cls.CANDIDATE, cls.RETIRED},
            cls.PRODUCTION: {cls.ARCHIVED, cls.RETIRED},
            cls.ARCHIVED: {cls.STAGED, cls.RETIRED},
            cls.RETIRED: set(),
        }
        return to_stage in valid.get(from_stage, set())


# 冻结后不允许改写的关键快照字段（血缘/口径/超参/指标）
_FROZEN_FIELDS = (
    "feature_versions", "label_spec", "data_range", "seed",
    "code_commit", "hyperparams", "parent_version",
)


@dataclass
class ModelVersion:
    """模型版本完整快照（可序列化、可还原、可审计）。"""

    model_id: str
    version: str
    created_at: datetime
    parent_version: Optional[str] = None
    changelog: str = ""
    feature_versions: list[str] = field(default_factory=list)
    label_spec: dict[str, Any] = field(default_factory=dict)
    data_range: dict[str, Any] = field(default_factory=dict)
    seed: Optional[int] = None
    code_commit: Optional[str] = None
    hyperparams: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    artifact_uri: Optional[str] = None       # 制品占位（阶段 3 落地）
    artifact_checksum: Optional[str] = None  # 制品校验和占位
    stage: ModelStage = ModelStage.CANDIDATE
    _frozen: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        _nonempty_str("model_id", self.model_id)
        _nonempty_str("version", self.version)
        if not isinstance(self.created_at, datetime):
            raise ValueError(
                f"created_at 必须为 datetime，收到 {type(self.created_at).__name__}")
        if not isinstance(self.changelog, str):
            raise ValueError(
                f"changelog 必须为 str，收到 {type(self.changelog).__name__}")
        _str_list("feature_versions", self.feature_versions)
        _dict("label_spec", self.label_spec)
        _dict("data_range", self.data_range)
        _dict("hyperparams", self.hyperparams)
        _dict("metrics", self.metrics)
        _opt_str("parent_version", self.parent_version)
        _opt_str("code_commit", self.code_commit)
        _opt_str("artifact_uri", self.artifact_uri)
        _opt_str("artifact_checksum", self.artifact_checksum)
        if self.seed is not None:
            if isinstance(self.seed, bool) or not isinstance(self.seed, int) \
                    or self.seed < 0:
                raise ValueError(
                    f"seed 必须为非负整数或 None，收到 {self.seed!r}")

    # ------------------------------------------------------------------ 状态
    def freeze(self) -> None:
        """冻结关键快照（只有 CANDIDATE 可主动冻结）。"""
        if self.stage != ModelStage.CANDIDATE:
            raise ValueError(f"只有 CANDIDATE 可冻结，当前阶段: {self.stage.value}")
        self._frozen = True

    def is_frozen(self) -> bool:
        return self._frozen

    def transition(self, new_stage: ModelStage) -> None:
        """严格状态机流转；进入 STAGED 自动冻结快照。"""
        if not ModelStage.can_transition(self.stage, new_stage):
            raise ValueError(
                f"非法阶段转换: {self.stage.value} → {new_stage.value}")
        if new_stage == ModelStage.STAGED and not self._frozen:
            self.freeze()
        self.stage = new_stage

    def update_metrics(self, metrics: dict[str, Any]) -> None:
        """回填 OOS 指标；冻结后拒绝改写（防事后调标）。"""
        if self._frozen:
            raise ValueError("快照已冻结，不允许改写 metrics（防事后调标）")
        if not isinstance(metrics, dict):
            raise ValueError("metrics 必须为 dict")
        self.metrics = dict(metrics)

    # ---------------------------------------------------------------- 序列化
    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "version": self.version,
            "parent_version": self.parent_version,
            "changelog": self.changelog,
            "feature_versions": list(self.feature_versions),
            "label_spec": dict(self.label_spec),
            "data_range": dict(self.data_range),
            "seed": self.seed,
            "code_commit": self.code_commit,
            "hyperparams": dict(self.hyperparams),
            "metrics": dict(self.metrics),
            "artifact_uri": self.artifact_uri,
            "artifact_checksum": self.artifact_checksum,
            "stage": self.stage.value,
            "created_at": self.created_at.isoformat(),
            "frozen": self._frozen,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ModelVersion":
        """从序列化 dict 还原（阶段/时间戳/冻结态一并还原）。"""
        stage = ModelStage(raw["stage"])
        obj = cls(
            model_id=raw["model_id"],
            version=raw["version"],
            parent_version=raw.get("parent_version"),
            changelog=raw.get("changelog", ""),
            feature_versions=list(raw.get("feature_versions", [])),
            label_spec=dict(raw.get("label_spec", {})),
            data_range=dict(raw.get("data_range", {})),
            seed=raw.get("seed"),
            code_commit=raw.get("code_commit"),
            hyperparams=dict(raw.get("hyperparams", {})),
            metrics=dict(raw.get("metrics", {})),
            artifact_uri=raw.get("artifact_uri"),
            artifact_checksum=raw.get("artifact_checksum"),
            stage=stage,
            created_at=datetime.fromisoformat(raw["created_at"]),
        )
        obj._frozen = bool(raw.get("frozen", False))
        return obj

    def summary(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "version": self.version,
            "stage": self.stage.value,
            "frozen": self._frozen,
            "feature_versions": list(self.feature_versions),
            "metrics": dict(self.metrics),
        }


class ModelRegistry:
    """模型注册中心：登记、查询、阶段流转、序列化往返。"""

    def __init__(self) -> None:
        self._models: dict[str, ModelVersion] = {}

    @staticmethod
    def _key(model_id: str, version: str) -> str:
        return f"{model_id}:{version}"

    def register(self, model: ModelVersion) -> None:
        key = self._key(model.model_id, model.version)
        if key in self._models:
            raise ValueError(f"模型版本已存在: {key}")
        self._models[key] = model

    def get(self, model_id: str, version: str) -> Optional[ModelVersion]:
        return self._models.get(self._key(model_id, version))

    def get_latest(self, model_id: str) -> Optional[ModelVersion]:
        versions = [m for m in self._models.values() if m.model_id == model_id]
        if not versions:
            return None
        return max(versions, key=lambda m: m.created_at)

    def get_production(self) -> list[ModelVersion]:
        return [m for m in self._models.values() if m.stage == ModelStage.PRODUCTION]

    def list_all(self) -> list[ModelVersion]:
        return list(self._models.values())

    def list_by_stage(self, stage: ModelStage) -> list[ModelVersion]:
        return [m for m in self._models.values() if m.stage == stage]

    def transition(self, model_id: str, version: str,
                   new_stage: ModelStage) -> ModelVersion:
        model = self.get(model_id, version)
        if model is None:
            raise ValueError(f"找不到模型版本: {self._key(model_id, version)}")
        model.transition(new_stage)
        return model

    def to_dict(self) -> dict[str, Any]:
        return {"models": [m.to_dict() for m in self._models.values()]}

    def load_dict(self, raw: dict[str, Any]) -> int:
        """批量还原快照；返回还原条数。重复键拒绝覆盖。"""
        count = 0
        for item in raw.get("models", []):
            model = ModelVersion.from_dict(item)
            key = self._key(model.model_id, model.version)
            if key in self._models:
                raise ValueError(f"模型版本已存在，拒绝覆盖: {key}")
            self._models[key] = model
            count += 1
        return count
