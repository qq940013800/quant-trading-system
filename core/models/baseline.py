# -*- coding: utf-8 -*-
"""core.models.baseline —— 正则化线性基线（必须先打赢的候选）。

纯 numpy 实现：IRLS 逻辑回归（带 L2）+ 闭式 Ridge。不 import sklearn——
按设计文档⑤，即使 scikit-learn 安装失败本模块仍可用，测试全绿。
正则强度由调用方配置传入（非绩效网格）。
"""
from __future__ import annotations

import numpy as np


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -40.0, 40.0)))


class LogisticBaseline:
    """L2 正则逻辑回归（IRLS / Newton-Raphson）。version 随训练冻结。"""

    version = "baseline-logistic-irls-v1"

    def __init__(self, C: float = 1.0, max_iter: int = 50, tol: float = 1e-6):
        if C <= 0:
            raise ValueError("C must be > 0")
        self.C = C
        self.lam = 1.0 / C  # L2 强度；intercept 不正则化
        self.max_iter = max_iter
        self.tol = tol
        self.beta: np.ndarray | None = None

    @staticmethod
    def _add_intercept(X: np.ndarray) -> np.ndarray:
        return np.hstack([np.ones((X.shape[0], 1), dtype=np.float64), X])

    def fit(self, X: np.ndarray, y: np.ndarray, **_: object) -> "LogisticBaseline":
        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        if y.ndim != 1 or X.shape[0] != y.shape[0]:
            raise ValueError("X/y shape mismatch")
        classes = np.unique(y)
        if not set(classes.tolist()) <= {0, 1}:
            raise ValueError("LogisticBaseline supports binary labels in {0,1}")
        X1 = self._add_intercept(X)
        p = X1.shape[1]
        beta = np.zeros(p, dtype=np.float64)
        reg = np.full(p, self.lam, dtype=np.float64)
        reg[0] = 0.0  # intercept 不惩罚
        for i in range(self.max_iter):
            z = X1 @ beta
            pr = _sigmoid(z)
            W = np.clip(pr * (1.0 - pr), 1e-10, None)
            hess = (X1.T * W) @ X1 + np.diag(reg)
            grad = X1.T @ (pr - y) + reg * beta
            step = np.linalg.solve(hess, grad)
            beta = beta - step
            if np.max(np.abs(step)) < self.tol:
                break
        self.beta = beta
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if self.beta is None:
            raise RuntimeError("model not fitted")
        X1 = self._add_intercept(np.asarray(X, dtype=np.float64))
        p1 = _sigmoid(X1 @ self.beta)
        return np.column_stack([1.0 - p1, p1])


class RidgeBaseline:
    """L2 Ridge 回归（闭式解），用于 {-1,0,+1} 标签的回归基线。"""

    version = "baseline-ridge-v1"

    def __init__(self, alpha: float = 1.0):
        if alpha < 0:
            raise ValueError("alpha must be >= 0")
        self.alpha = alpha
        self.beta: np.ndarray | None = None

    def fit(self, X: np.ndarray, y: np.ndarray, **_: object) -> "RidgeBaseline":
        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        X1 = np.hstack([np.ones((X.shape[0], 1)), X])
        d = X1.shape[1]
        reg = np.eye(d) * self.alpha
        reg[0, 0] = 0.0  # intercept 不惩罚
        self.beta = np.linalg.solve(X1.T @ X1 + reg, X1.T @ y)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self.beta is None:
            raise RuntimeError("model not fitted")
        X1 = np.hstack([np.ones((X.shape[0], 1)), np.asarray(X, dtype=np.float64)])
        return X1 @ self.beta

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        # 回归输出经 sigmoid 映射为正类概率（仅作接口对齐；回归基线主要用 predict）
        score = self.predict(X)
        p1 = _sigmoid(score)
        return np.column_stack([1.0 - p1, p1])


def permutation_importance(model, X: np.ndarray, y: np.ndarray, *,
                           seed: int = 0, n_repeats: int = 5) -> np.ndarray:
    """OOS 特征可信度（permutation importance）：列打乱后准确率下降幅度。

    纯 numpy 实现；在测试集上评估——特征可信度来自 OOS 表现而非训练集拟合。
    """
    X = np.asarray(X, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    rng = np.random.default_rng(seed)
    base_pred = (model.predict_proba(X)[:, 1] >= 0.5).astype(np.float64)
    base_acc = float((base_pred == y).mean())
    imp = np.zeros(X.shape[1], dtype=np.float64)
    for j in range(X.shape[1]):
        drops = 0.0
        for _ in range(n_repeats):
            Xp = X.copy()
            Xp[:, j] = rng.permutation(Xp[:, j])
            pred = (model.predict_proba(Xp)[:, 1] >= 0.5).astype(np.float64)
            drops += base_acc - float((pred == y).mean())
        imp[j] = drops / n_repeats
    return imp
