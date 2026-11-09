# -*- coding: utf-8 -*-
"""core.regime.rules —— 规则硬状态层 + 分布派生阈值。

可审计性：硬状态判定完全由 (adx, hurst, atr_pct) 三个可解释特征与
CLEAN 分布分位边决定，任何一笔都能还原判定路径（不变量 2）。

阈值纪律（决策 #9 / 硬规则 2）：
- adx_q_lo/adx_q_hi 与 atr_q_lo/atr_q_hi 一律由 `derive_thresholds` 在 CLEAN
  训练段经验分布上经 np.quantile 派生；本模块不出现任何按绩效网格搜索的字面量；
- MR_HURST_THRESHOLD = 0.5 是理论常量（R/S 理论：H=0.5 随机游走分界，
  H>0.5 趋势持续、H<0.5 反持续/均值回复），非绩效调参，特此注明来源。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger("core.regime")

STATE_TREND = "trend"
STATE_MEAN_REVERSION = "mean_reversion"
STATE_RANGING = "ranging"
STATES: tuple[str, str, str] = (STATE_TREND, STATE_MEAN_REVERSION, STATE_RANGING)

# 理论常量（R/S 分析理论分界）：Hurst=0.5 ⇔ 随机游走。不是绩效参数。
MR_HURST_THRESHOLD = 0.5

UNIFORM_PROBS: dict[str, float] = {s: 1.0 / 3.0 for s in STATES}


@dataclass(frozen=True)
class RuleThresholds:
    """由 CLEAN 训练段经验分布派生的阈值对象（fit 时落盘，predict 只读复用）。"""
    adx_q_lo: float
    adx_q_hi: float
    atr_q_lo: float
    atr_q_hi: float
    q_lo: float   # 使用的分位级别（如 0.30）——审计用
    q_hi: float

    def __post_init__(self) -> None:
        finite_fields = (("adx_q_lo", self.adx_q_lo), ("adx_q_hi", self.adx_q_hi),
                         ("atr_q_lo", self.atr_q_lo), ("atr_q_hi", self.atr_q_hi),
                         ("q_lo", self.q_lo), ("q_hi", self.q_hi))
        for name, v in finite_fields:
            if isinstance(v, bool) or not isinstance(v, (int, float)) \
                    or not np.isfinite(v):
                raise ValueError(
                    f"{name} 必须为有限数值，收到 {v!r}")
        if not self.adx_q_hi > self.adx_q_lo:
            raise ValueError(
                f"adx_q_hi({self.adx_q_hi}) 必须大于 adx_q_lo({self.adx_q_lo})")
        if not self.atr_q_hi > self.atr_q_lo:
            raise ValueError(
                f"atr_q_hi({self.atr_q_hi}) 必须大于 atr_q_lo({self.atr_q_lo})")
        if not (0.0 < self.q_lo < self.q_hi < 1.0):
            raise ValueError(
                f"分位级别必须满足 0 < q_lo < q_hi < 1，"
                f"收到 q_lo={self.q_lo!r} q_hi={self.q_hi!r}")


def _finite(values) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float64)
    return arr[np.isfinite(arr)]


def derive_thresholds(adx_values, atr_pct_values, *,
                      q_lo: float = 0.30, q_hi: float = 0.70) -> RuleThresholds:
    """从 CLEAN 训练段特征经验分布派生 deadband 边（决策 #9）。

    q_lo/q_hi 是分布描述口径（tercile 惯用法），不是按绩效搜索的参数。
    """
    if not (0.0 < q_lo < q_hi < 1.0):
        raise ValueError(
            f"quantile levels must satisfy 0 < q_lo < q_hi < 1, "
            f"got q_lo={q_lo!r} q_hi={q_hi!r}")
    adx = _finite(adx_values)
    atr_pct = _finite(atr_pct_values)
    if adx.size < 10 or atr_pct.size < 10:
        raise ValueError(
            "CLEAN segment too short for distribution thresholds: "
            f"adx finite n={adx.size}, atr_pct finite n={atr_pct.size} "
            f"(need >=10 each)")
    adx_lo = float(np.quantile(adx, q_lo))
    adx_hi = float(np.quantile(adx, q_hi))
    atr_lo = float(np.quantile(atr_pct, q_lo))
    atr_hi = float(np.quantile(atr_pct, q_hi))
    if not adx_hi > adx_lo:
        raise ValueError(
            f"ADX CLEAN distribution degenerate: q_hi({adx_hi}) <= q_lo({adx_lo})")
    if not atr_hi > atr_lo:
        raise ValueError(
            f"ATR_pct CLEAN distribution degenerate: q_hi({atr_hi}) <= q_lo({atr_lo})")
    return RuleThresholds(adx_lo, adx_hi, atr_lo, atr_hi, q_lo, q_hi)


def rule_state_and_soft_probs(feat: dict, thr: RuleThresholds):
    """规则层：返回 (硬状态, 软概率向量, degraded)。

    硬状态判定：
      - adx >= adx_q_hi            → trend（分布意义上的强趋势）；
      - hurst < 0.5 且 adx <= q_lo → mean_reversion（反持续 + 无趋势）；
      - 其余                        → ranging（灰区/deadband，决策 #8 不硬切）。

    软概率（单调、在 deadband 内连续过渡，供混合层加权）：
      w_trend = clip((adx - q_lo)/(q_hi - q_lo), 0, 1)
      w_mr    = clip(0.5 - hurst, 0, 1) * (1 - w_trend)
      w_range = clip((atr_pct - atr_q_lo)/atr_span, 0, 1) * (1 - w_trend)
      归一化使和为 1；三权重全塌 0 时退化为均匀分布（特征均在分布下沿的中性态）。
    """
    adx_v = feat["adx"]
    hurst_v = feat["hurst"]
    atr_v = feat["atr_pct"]
    if any(not np.isfinite(v) for v in (adx_v, hurst_v, atr_v)):
        # 特征不足（warmup 段）：中性 ranging + 显式均匀降级标注
        return STATE_RANGING, dict(UNIFORM_PROBS), True

    w_trend = float(np.clip(
        (adx_v - thr.adx_q_lo) / (thr.adx_q_hi - thr.adx_q_lo), 0.0, 1.0))
    w_mr = float(np.clip(MR_HURST_THRESHOLD - hurst_v, 0.0, 1.0)) * (1.0 - w_trend)
    atr_span = thr.atr_q_hi - thr.atr_q_lo
    w_vol = (float(np.clip((atr_v - thr.atr_q_lo) / atr_span, 0.0, 1.0))
             if atr_span > 0 else 0.0)
    w_range = w_vol * (1.0 - w_trend)

    total = w_trend + w_mr + w_range
    if total <= 0.0:
        probs = dict(UNIFORM_PROBS)
    else:
        probs = {
            STATE_TREND: w_trend / total,
            STATE_MEAN_REVERSION: w_mr / total,
            STATE_RANGING: w_range / total,
        }

    if adx_v >= thr.adx_q_hi:
        state = STATE_TREND
    elif hurst_v < MR_HURST_THRESHOLD and adx_v <= thr.adx_q_lo:
        state = STATE_MEAN_REVERSION
    else:
        state = STATE_RANGING
    return state, probs, False
