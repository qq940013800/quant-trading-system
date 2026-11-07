# -*- coding: utf-8 -*-
"""core.models.pipeline —— 训练管线编排（面板 → 标签 → purged CV → OOS 评估 → 快照）。

设计依据：docs/design/design-feature-store.md §4 阶段 1（同源收口）与
docs/design/design-mlops-experiment.md §4 阶段 1（版本快照补强）。

阶段门（纯逻辑、内存内执行，不持久化权重二进制、不连数据库）：
    1. 同源特征面板：只取注册表内特征函数，经 `build_feature_panel` 因果计算；
    2. triple-barrier 标签：未来路径函数，因果纪律由 purge + embargo 兜底；
    3. 对齐与清洗：按位置对齐面板/标签，丢弃特征 NaN 行（warmup 或统计量不足）；
    4. purged walk-forward + embargo：禁随机 KFold，train 全在 test 之前；
    5. 折内拟合：模型后端走 `Model` protocol 注入（默认纯 numpy 逻辑基线）；
    6. OOS 汇总：accuracy / AUC（Mann-Whitney，纯 numpy）/ 正类概率；
    7. 可序列化训练快照：血缘、标签口径、数据区间、种子、commit、指标、父版本。

边界：
- 不引入 sklearn/lightgbm 硬依赖；GBM 后端仍由 `core.models.gbm` import 期降级；
- 过拟合三重验证（PBO/CPCV/DSR）在 `core/backtest/overfitting.py`，本管线只预留
  指标槽位，不替代实验账本与 trials 计数（AGENTS.md 规则 11）；
- 管线不产交易收益序列；Sharpe/回撤等策略层指标不在此计算。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd

from core.errors import ModelLayerError
from core.features.base import build_feature_panel
from core.features.registry import FeatureRegistry
from core.models.base import Model
from core.models.baseline import LogisticBaseline
from core.models.cv import purged_walk_forward
from core.models.labels import triple_barrier_labels

logger = logging.getLogger("core.models.pipeline")


def _default_model_factory() -> Model:
    """默认模型后端：纯 numpy L2 逻辑基线（无 sklearn 硬依赖）。"""
    return LogisticBaseline(C=1.0)


# ---------------------------------------------------------------------------
# 配置与快照
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PipelineConfig:
    """一次训练运行的冻结配置（实验前确定，不在训练后回填）。"""

    model_id: str
    version: str
    feature_names: list[str]
    # 标签口径
    tp_mult: float
    sl_mult: float
    max_holding_bars: int
    positive_label: int = 1
    # 交叉验证
    embargo_bars: int = 12
    n_splits: int = 4
    warmup_bars: int = 60
    seed: int = 7
    # 模型后端工厂：返回实现 Model protocol 的实例
    model_factory: Callable[[], Model] = field(
        default_factory=lambda: _default_model_factory)
    hyperparams: dict[str, Any] = field(default_factory=dict)
    code_commit: Optional[str] = None
    parent_version: Optional[str] = None
    changelog: str = ""


@dataclass
class TrainingResult:
    """训练产出的可序列化快照（不含权重二进制；模型实例仅供诊断引用）。"""

    model_id: str
    version: str
    feature_versions: list[str]
    label_spec: dict[str, Any]
    data_range: dict[str, Any]
    seed: Optional[int]
    code_commit: Optional[str]
    hyperparams: dict[str, Any]
    metrics: dict[str, Any]
    parent_version: Optional[str] = None
    changelog: str = ""
    artifact_uri: Optional[str] = None
    artifact_checksum: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)

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
            "created_at": self.created_at.isoformat(),
        }

    def to_model_version(self) -> "ModelVersion":  # noqa: F821 (延迟导入)
        """转换为注册中心 `ModelVersion`（CANDIDATE，待评审后流转）。"""
        from core.registry.model_registry import ModelVersion
        return ModelVersion(
            model_id=self.model_id,
            version=self.version,
            created_at=self.created_at,
            parent_version=self.parent_version,
            changelog=self.changelog,
            feature_versions=list(self.feature_versions),
            label_spec=dict(self.label_spec),
            data_range=dict(self.data_range),
            seed=self.seed,
            code_commit=self.code_commit,
            hyperparams=dict(self.hyperparams),
            metrics=dict(self.metrics),
            artifact_uri=self.artifact_uri,
            artifact_checksum=self.artifact_checksum,
        )


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

def _auc_mann_whitney(y: np.ndarray, p: np.ndarray) -> float:
    """AUC（Mann-Whitney U，ties 取平均秩），纯 numpy；不可分返回 NaN。"""
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    n1 = int((y == 1).sum())
    n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return float("nan")
    order = np.argsort(p, kind="mergesort")
    sorted_p = p[order]
    ranks_sorted = np.arange(1, len(p) + 1, dtype=float)
    i = 0
    while i < len(sorted_p):  # ties 平均秩
        j = i
        while j + 1 < len(sorted_p) and sorted_p[j + 1] == sorted_p[i]:
            j += 1
        avg = (ranks_sorted[i] + ranks_sorted[j]) / 2.0
        ranks_sorted[i:j + 1] = avg
        i = j + 1
    ranks = np.empty_like(ranks_sorted)
    ranks[order] = ranks_sorted
    rank_pos = ranks[y == 1].sum()
    u = rank_pos - n1 * (n1 + 1) / 2.0
    return float(u / (n1 * n0))


def _fold_metrics(y_true: np.ndarray, p1: np.ndarray) -> dict[str, float]:
    pred = (p1 >= 0.5).astype(int)
    acc = float((pred == y_true).mean()) if len(y_true) else float("nan")
    return {
        "accuracy": acc,
        "auc": _auc_mann_whitney(y_true, p1),
        "mean_positive_prob": float(np.mean(p1)) if len(p1) else float("nan"),
        "n_test": int(len(y_true)),
    }


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def run_training(
    history: list,
    atr: pd.Series,
    registry: FeatureRegistry,
    config: PipelineConfig,
) -> TrainingResult:
    """执行一次训练运行并返回快照（不写库、不保存权重文件）。

    Parameters
    ----------
    history : 已收盘 bar 升序列表（tz-aware UTC）；
    atr : 与 history 位置对齐的 ATR 序列（须由 CLEAN 集估计，集合分离由调用方保证）；
    registry : 特征注册表；特征血缘从注册表取，禁止内联第二份公式；
    config : 冻结训练配置。
    """
    n = len(history)
    if n == 0:
        raise ModelLayerError("history is empty", layer="models.pipeline")
    if len(atr) != n:
        raise ModelLayerError(
            "atr/history length mismatch", layer="models.pipeline",
            atr_len=len(atr), history_len=n)

    # 1. 同源特征面板（因果 by construction）
    panel = registry.panel_features(config.feature_names)
    panel_df = build_feature_panel(history, panel, warmup_bars=config.warmup_bars)
    X = panel_df[config.feature_names].to_numpy(dtype=float)

    # 2. triple-barrier 标签（未来路径；泄漏由 purge/embargo 隔离）
    labels = triple_barrier_labels(
        history, atr,
        tp_mult=config.tp_mult, sl_mult=config.sl_mult,
        max_holding_bars=config.max_holding_bars,
    )
    y3 = labels.to_numpy()
    if len(y3) != n:
        raise ModelLayerError("label/history length mismatch", layer="models.pipeline")
    y = (y3 == config.positive_label).astype(int)

    # 3. 对齐与清洗：丢弃特征含 NaN 的行（warmup / 统计量不足）
    finite = np.all(np.isfinite(X), axis=1)
    x_valid = X[finite]
    y_valid = y[finite]
    n_valid = int(x_valid.shape[0])
    dropped = n - n_valid
    if n_valid < config.n_splits + 1:
        raise ModelLayerError(
            "not enough valid samples after NaN drop", layer="models.pipeline",
            n_valid=n_valid, dropped=dropped)

    # 4. purged walk-forward + embargo（禁随机切分）
    folds = purged_walk_forward(
        n=n_valid,
        embargo_bars=config.embargo_bars,
        n_splits=config.n_splits,
        label_window_bars=config.max_holding_bars,
    )

    # 5/6. 折内拟合并收集 OOS 预测
    oos_y: list[np.ndarray] = []
    oos_p: list[np.ndarray] = []
    fold_reports: list[dict[str, Any]] = []
    for fold_idx, (train_idx, test_idx) in enumerate(folds):
        model = config.model_factory()
        model.fit(x_valid[train_idx], y_valid[train_idx])
        proba = model.predict_proba(x_valid[test_idx])
        p1 = proba[:, 1]
        oos_y.append(y_valid[test_idx])
        oos_p.append(p1)
        report = {"fold": fold_idx, "n_train": int(len(train_idx)),
                  **_fold_metrics(y_valid[test_idx], p1)}
        fold_reports.append(report)

    y_oos = np.concatenate(oos_y)
    p_oos = np.concatenate(oos_p)
    overall = _fold_metrics(y_oos, p_oos)

    ts_first = getattr(history[0], "ts_utc", None)
    ts_last = getattr(history[-1], "ts_utc", None)
    data_range = {
        "bars_total": int(n),
        "n_valid": n_valid,
        "dropped_nan": int(dropped),
        "n_oos": int(len(y_oos)),
        "n_folds": len(folds),
        "start_utc": ts_first.isoformat() if ts_first is not None else None,
        "end_utc": ts_last.isoformat() if ts_last is not None else None,
    }

    metrics = {
        **overall,
        "folds": fold_reports,
    }

    logger.info(
        "training run done model=%s version=%s n_valid=%d n_oos=%d "
        "n_folds=%d auc=%s accuracy=%s",
        config.model_id, config.version, n_valid, len(y_oos),
        len(folds), overall["auc"], overall["accuracy"],
    )

    return TrainingResult(
        model_id=config.model_id,
        version=config.version,
        feature_versions=registry.feature_versions(config.feature_names),
        label_spec={
            "tp_mult": config.tp_mult,
            "sl_mult": config.sl_mult,
            "max_holding_bars": config.max_holding_bars,
            "positive_label": config.positive_label,
        },
        data_range=data_range,
        seed=config.seed,
        code_commit=config.code_commit,
        hyperparams=dict(config.hyperparams),
        metrics=metrics,
        parent_version=config.parent_version,
        changelog=config.changelog,
    )
