# -*- coding: utf-8 -*-
"""core.models.gbm —— LightGBM 封装（import 期降级，不硬依赖）。

设计文档⑤：lightgbm 缺失时降级为"无 GBM 模式"——本模块 import 成功（只置
_HAS_LGBM=False），真正实例化 Wrapper 时才 raise。测试用 pytest.importorskip
隔离，无包环境全绿。

超参纪律：max_depth 限制 3-6、early stopping、subsample——结构约束写死，
具体取值由调用方配置传入；禁止按 Sharpe 网格搜参。
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np

try:  # pragma: no cover - 取决于环境
    import lightgbm as lgb

    _HAS_LGBM = True
except ImportError:  # pragma: no cover
    lgb = None  # type: ignore[assignment]
    _HAS_LGBM = False


def has_lightgbm() -> bool:
    return _HAS_LGBM


class LightGBMWrapper:
    version = "gbm-lgbm-v1"

    def __init__(self, *, max_depth: int = 4, learning_rate: float = 0.05,
                 n_estimators: int = 300, subsample: float = 0.8,
                 early_stopping_rounds: int = 30, random_state: int = 7):
        if not _HAS_LGBM:
            raise RuntimeError("lightgbm not installed; run without GBM mode")
        if not 3 <= max_depth <= 6:
            raise ValueError("max_depth must be within 3-6 (design constraint)")
        self.max_depth = max_depth
        self.params = {
            "objective": "binary",
            "max_depth": max_depth,
            "learning_rate": learning_rate,
            "subsample": subsample,
            "subsample_freq": 1,
            "verbose": -1,
            "random_state": random_state,
        }
        self.n_estimators = n_estimators
        self.early_stopping_rounds = early_stopping_rounds
        self.booster: Optional[Any] = None

    def fit(self, X: np.ndarray, y: np.ndarray, *,
            X_eval: np.ndarray, y_eval: np.ndarray) -> "LightGBMWrapper":
        dtrain = lgb.Dataset(np.asarray(X, dtype=np.float64), label=np.asarray(y, dtype=np.float64))
        deval = lgb.Dataset(np.asarray(X_eval, dtype=np.float64), label=np.asarray(y_eval, dtype=np.float64),
                            reference=dtrain)
        # early stopping 用"更晚的时间切片"作验证——禁随机切分
        self.booster = lgb.train(
            self.params, dtrain, num_boost_round=self.n_estimators,
            valid_sets=[deval],
            callbacks=[lgb.early_stopping(self.early_stopping_rounds, verbose=False)],
        )
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if self.booster is None:
            raise RuntimeError("model not fitted")
        p1 = self.booster.predict(np.asarray(X, dtype=np.float64))
        return np.column_stack([1.0 - p1, p1])
