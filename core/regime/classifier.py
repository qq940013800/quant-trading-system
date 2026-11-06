# -*- coding: utf-8 -*-
"""core.regime.classifier —— RegimeClassifier：规则硬状态 + GMM 软概率混合。

契约（本分片设计）：
- fit(history_train, as_of_end=None)：只在传入的 CLEAN 训练段上，逐根已收盘 bar
  经 @as_of 特征函数计算快照 → np.quantile 派生 deadband 阈值 → 拟合 GMM。
  as_of_end 给定时只取 ts_utc <= as_of_end 的 bar（fit 本身也不得偷看训练段之外）。
- predict(history, as_of)：只读已收盘数据；内部特征函数本身带 @as_of 守卫，
  history 含未来 bar 即抛 LookAheadError；predict 绝不重拟合（阈值对象只读复用）。
- 混合：规则软概率与 GMM 后验按冻结权重做几何池化（p_s ∝ p_rule^w_rule · p_gmm^w_gmm
  再归一），w_rule/w_gmm 是构造时冻结的混合权重（决策 #8 deadband 加权混合），
  不按绩效搜索。
"""
from __future__ import annotations

import logging

import numpy as np

from core.features.atr import wilder_atr
from core.features.base import AsOfContractError
from core.features.regime import adx, hurst_exponent

from .gmm import GMMRegimeModel, has_gmm
from .output import RegimeOutput
from .rules import (
    STATES,
    RuleThresholds,
    derive_thresholds,
    rule_state_and_soft_probs,
)

logger = logging.getLogger("core.regime")

FEATURE_KEYS = ("adx", "hurst", "atr_pct")


class RegimeClassifier:
    version = "regime-rules-gmm-v1"
    threshold_dataset = "CLEAN"

    def __init__(self, *,
                 adx_period: int = 14,
                 hurst_window: int = 256,
                 hurst_min_window: int = 64,
                 q_lo: float = 0.30,
                 q_hi: float = 0.70,
                 w_rule: float = 0.5,
                 w_gmm: float = 0.5,
                 min_train_rows: int = 60,
                 random_state: int = 7,
                 use_gmm: bool = True) -> None:
        # w_rule/w_gmm 是冻结的混合权重（config/params 传入），和必须为 1
        if w_rule < 0.0 or w_gmm < 0.0 or abs((w_rule + w_gmm) - 1.0) > 1e-9:
            raise ValueError(
                f"mixing weights must be non-negative and sum to 1, "
                f"got w_rule={w_rule!r} w_gmm={w_gmm!r}")
        self.adx_period = adx_period
        self.hurst_window = hurst_window
        self.hurst_min_window = hurst_min_window
        self.q_lo = q_lo
        self.q_hi = q_hi
        self.w_rule = w_rule
        self.w_gmm = w_gmm
        self.min_train_rows = min_train_rows
        self.random_state = random_state
        self.use_gmm = use_gmm
        self._thr: RuleThresholds | None = None
        self._gmm: GMMRegimeModel | None = None
        self._gmm_active: bool = False

    # ------------------------------------------------------------------ fit
    def _snapshot(self, history, as_of) -> dict:
        """在 as_of 处的特征快照（@as_of 函数自身执行前视守卫）。"""
        adx_v = float(adx(history, as_of, period=self.adx_period))
        hurst_v = float(hurst_exponent(
            history, as_of, window=self.hurst_window,
            min_window=self.hurst_min_window))
        atr_v = wilder_atr(history, as_of, period=self.adx_period)
        close = history[-1].close
        atr_pct = float(atr_v) / float(close) if (
            np.isfinite(atr_v) and close and close > 0) else np.nan
        return {"adx": adx_v, "hurst": hurst_v, "atr_pct": atr_pct}

    def fit(self, history_train, as_of_end=None) -> "RegimeClassifier":
        if as_of_end is not None and getattr(as_of_end, "tzinfo", None) is None:
            raise AsOfContractError({
                "layer": "regime", "ts_utc": str(as_of_end),
                "detail": "as_of_end must be tz-aware UTC"})
        if as_of_end is not None:
            train = [b for b in history_train if b.ts_utc <= as_of_end]
            if not train:
                raise AsOfContractError({
                    "layer": "regime", "ts_utc": str(as_of_end),
                    "detail": "no CLEAN bars <= as_of_end"})
        else:
            train = list(history_train)

        rows = [self._snapshot(train[: i + 1], train[i].ts_utc)
                for i in range(len(train))]
        cols = {k: np.array([r[k] for r in rows], dtype=np.float64)
                for k in FEATURE_KEYS}

        # 阈值：只从 CLEAN 训练段经验分布派生（决策 #9）
        self._thr = derive_thresholds(
            cols["adx"], cols["atr_pct"], q_lo=self.q_lo, q_hi=self.q_hi)

        mask = np.logical_and.reduce([np.isfinite(cols[k]) for k in FEATURE_KEYS])
        X = np.column_stack([cols[k][mask] for k in FEATURE_KEYS])
        if X.shape[0] < self.min_train_rows:
            raise ValueError(
                f"CLEAN finite feature rows {X.shape[0]} < min_train_rows "
                f"{self.min_train_rows}; extend CLEAN segment or relax warmup")

        self._gmm = None
        self._gmm_active = False
        if self.use_gmm:
            if has_gmm():
                try:
                    model = GMMRegimeModel(random_state=self.random_state)
                    model.fit(X)
                    self._gmm = model
                    self._gmm_active = True
                except ValueError as exc:
                    # 数值失败带上下文记录，降级为规则软映射（非裸 except）
                    logger.warning(
                        "GMM fit failed on CLEAN segment, degrade to "
                        "rule-only soft mapping: %r", exc)
            else:
                logger.info(
                    "sklearn GaussianMixture unavailable; rule-only regime mode")
        return self

    # --------------------------------------------------------------- predict
    def predict(self, history, as_of) -> RegimeOutput:
        if self._thr is None:
            raise RuntimeError(
                "RegimeClassifier not fitted: call fit(history_train) on the "
                "CLEAN segment before predict")
        snap = self._snapshot(history, as_of)  # LookAheadError 由 @as_of 守卫抛出
        state, rule_probs, rule_degraded = rule_state_and_soft_probs(
            snap, self._thr)

        gmm_probs = None
        if self._gmm_active and self._gmm is not None:
            gmm_probs = self._gmm.predict_probs(
                [snap[k] for k in FEATURE_KEYS])

        if gmm_probs is None:
            probs = rule_probs
            # 请求了 GMM 但不可用/含 NaN 无法打分 → 显式标注降级
            degraded = rule_degraded or self.use_gmm
        else:
            combined = {s: (rule_probs[s] ** self.w_rule)
                        * (gmm_probs[s] ** self.w_gmm)
                        for s in STATES}
            total = sum(combined.values())
            if total <= 0.0 or not np.isfinite(total):
                probs = rule_probs
                degraded = rule_degraded
            else:
                probs = {s: combined[s] / total for s in STATES}
                degraded = rule_degraded

        layer = "gmm" if self._gmm_active else "rules-only"
        return RegimeOutput(
            state=state,
            probs=probs,
            version=f"{self.version}/{layer}",
            threshold_dataset=self.threshold_dataset,
            degraded=degraded,
        )
