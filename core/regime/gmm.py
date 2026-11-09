# -*- coding: utf-8 -*-
"""core.regime.gmm —— GMM 软概率层（import 期隔离，缺失时降级为规则软映射）。

纪律：
- 只在 CLEAN 训练段上 fit（调用方负责传入对应 history）；predict 只读不重拟合；
- 特征先按训练段均值/方差标准化（统计量本身来自 CLEAN，非全样本）；
- 3 个 GMM 分量 → 三状态的对齐规则是确定性、可审计的：
  分量按质心 adx 排序，adx 最高者 → trend；其余两个中 hurst 最低（最反持续）
  者 → mean_reversion；剩余 → ranging。
- sklearn 不可用时 __init__ 抛带上下文的 RuntimeError（非裸 except）；
  降级路径由 classifier 走规则软概率，见 tests/test_regime_classifier.py。
"""
from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger("core.regime")

try:  # pragma: no cover - 取决于环境
    from sklearn.mixture import GaussianMixture

    _HAS_GMM = True
    _IMPORT_NOTE = ""
except ImportError as exc:  # pragma: no cover
    GaussianMixture = None  # type: ignore[assignment]
    _HAS_GMM = False
    _IMPORT_NOTE = repr(exc)

from .rules import STATE_MEAN_REVERSION, STATE_RANGING, STATE_TREND, STATES

GMM_FEATURES = ("adx", "hurst", "atr_pct")
MIN_FIT_ROWS = 20  # 低于此行数 GMM 不稳定（经验下限，审计用；非绩效阈值）


def has_gmm() -> bool:
    return _HAS_GMM


def _int_param(name: str, val, *, minimum: int) -> int:
    if isinstance(val, bool) or not isinstance(val, int) or val < minimum:
        raise ValueError(
            f"regime.gmm: {name} must be an integer >= {minimum}, got {val!r}")
    return val


class GMMRegimeModel:
    version = "regime-gmm-v1"

    def __init__(self, *, n_components: int = 3, random_state: int = 7,
                 n_init: int = 2) -> None:
        if not _HAS_GMM:
            raise RuntimeError(
                f"sklearn GaussianMixture unavailable ({_IMPORT_NOTE}); "
                "classifier will degrade to rule-only soft mapping")
        if n_components != 3:
            raise ValueError("n_components must be 3 (aligned to trend/mr/ranging)")
        self.n_components = n_components
        self.random_state = _int_param("random_state", random_state, minimum=0)
        self.n_init = _int_param("n_init", n_init, minimum=1)
        self._mean: np.ndarray | None = None
        self._std: np.ndarray | None = None
        self._gmm = None
        self._comp_state: dict[int, str] | None = None

    def fit(self, X: np.ndarray) -> "GMMRegimeModel":
        """X: shape (n, 3)，行 = CLEAN 训练段逐 bar 因果特征快照。"""
        X = np.asarray(X, dtype=np.float64)
        if X.ndim != 2 or X.shape[1] != len(GMM_FEATURES):
            raise ValueError(
                f"X must have shape (n, {len(GMM_FEATURES)}), got {X.shape}")
        if X.shape[0] < MIN_FIT_ROWS:
            raise ValueError(
                f"GMM fit needs >= {MIN_FIT_ROWS} CLEAN rows, got {X.shape[0]}")
        # 标准化统计量：全部来自 CLEAN 训练段（非全样本）
        self._mean = X.mean(axis=0)
        self._std = X.std(axis=0, ddof=0)
        self._std = np.where(self._std > 1e-12, self._std, 1.0)
        Z = (X - self._mean) / self._std
        try:
            self._gmm = GaussianMixture(
                n_components=self.n_components,
                random_state=self.random_state,
                n_init=self.n_init,
                covariance_type="full",
            )
            labels = self._gmm.fit_predict(Z)
        except ValueError as exc:
            raise ValueError(
                f"GMM fit failed on CLEAN feature matrix: {exc!r}") from exc

        comp_adx = np.array([
            Z[labels == k, 0].mean() if (labels == k).any() else np.nan
            for k in range(self.n_components)])
        comp_hurst = np.array([
            Z[labels == k, 1].mean() if (labels == k).any() else np.nan
            for k in range(self.n_components)])
        # 确定性对齐（审计可还原）：adx 最高分量 → trend；
        # 剩余分量中 hurst 最低者 → mean_reversion；最后一个 → ranging。
        trend_comp = int(np.nanargmax(comp_adx))
        rest = [c for c in range(self.n_components) if c != trend_comp]
        mr_comp = int(min(rest, key=lambda c: comp_hurst[c]))
        range_comp = [c for c in rest if c != mr_comp][0]
        self._comp_state = {trend_comp: STATE_TREND,
                            mr_comp: STATE_MEAN_REVERSION,
                            range_comp: STATE_RANGING}
        return self

    def predict_probs(self, row) -> dict[str, float] | None:
        """单行特征 → 三状态后验概率；含 NaN 时返回 None（调用方降级处理）。"""
        if self._gmm is None or self._comp_state is None or self._mean is None:
            raise RuntimeError("GMMRegimeModel not fitted")
        x = np.asarray(row, dtype=np.float64)
        if x.shape != (len(GMM_FEATURES),) or not np.isfinite(x).all():
            return None
        z = (x - self._mean) / self._std
        post = self._gmm.predict_proba(z.reshape(1, -1))[0]
        probs = {s: 0.0 for s in STATES}
        for comp, p in enumerate(post):
            probs[self._comp_state[comp]] += float(p)
        total = sum(probs.values())
        if total <= 0 or not np.isfinite(total):
            return None
        return {s: v / total for s, v in probs.items()}
