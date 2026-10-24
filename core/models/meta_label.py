# -*- coding: utf-8 -*-
"""core.models.meta_label —— L3 二级过滤：候选信号 → (p, k)。

meta-labeling（López de Prado）：第一层方向骨架由规则层给出，本层只回答
"该候选该不该开仓、开多大"。
- p：二级模型预测该候选盈利的概率；
- k：仓位系数。k 由 p 在训练集经验分布上的分位映射导出（阈值来自分布）：
      k = clip((p - q_lo)/(q_hi - q_lo), 0, 1)，q_lo/q_hi = 训练集 p 的
      30/70 分位。不用固定 0.5 阈值（那是绩效拍脑袋），也不按 Sharpe 调。
"""
from __future__ import annotations

import numpy as np


class MetaLabeler:
    def __init__(self, base_model, q_lo: float = 0.30, q_hi: float = 0.70):
        if not 0.0 <= q_lo < q_hi <= 1.0:
            raise ValueError("require 0 <= q_lo < q_hi <= 1")
        self.base_model = base_model
        self.q_lo = q_lo
        self.q_hi = q_hi
        self._q_lo_val: float | None = None
        self._q_hi_val: float | None = None

    @property
    def version(self) -> str:
        return f"meta-{self.base_model.version}"

    def fit(self, X: np.ndarray, y_meta: np.ndarray, **kwargs) -> "MetaLabeler":
        """y_meta ∈ {0,1}：候选信号对应交易是否盈利。"""
        self.base_model.fit(X, y_meta, **kwargs)
        # 分位阈值来自训练 p 的经验分布（事后 OOS 才敢用——这里只用训练段）
        p_train = self.base_model.predict_proba(np.asarray(X, dtype=np.float64))[:, 1]
        self._q_lo_val = float(np.quantile(p_train, self.q_lo))
        self._q_hi_val = float(np.quantile(p_train, self.q_hi))
        if self._q_hi_val <= self._q_lo_val:
            self._q_hi_val = self._q_lo_val + 1e-6
        return self

    def predict(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """返回 (p, k)：p 开仓概率，k 仓位系数 ∈ [0,1]。"""
        if self._q_lo_val is None or self._q_hi_val is None:
            raise RuntimeError("MetaLabeler not fitted")
        p = self.base_model.predict_proba(np.asarray(X, dtype=np.float64))[:, 1]
        span = self._q_hi_val - self._q_lo_val
        k = np.clip((p - self._q_lo_val) / span, 0.0, 1.0)
        return p, k
