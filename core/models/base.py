# -*- coding: utf-8 -*-
"""core.models.base —— 模型协议（冻结接口，实现不得改签名）。

DL/DRL/LLM 方向第二阶段不做（IMPLEMENTATION_SPEC §5），此处只留 protocol 位。
"""
from __future__ import annotations

from typing import Protocol

import numpy as np


class Model(Protocol):
    version: str

    def fit(self, X: np.ndarray, y: np.ndarray, **kwargs) -> "Model": ...

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """返回 shape=(n,2) 的概率矩阵（列序 [负类, 正类]）。"""
        ...
