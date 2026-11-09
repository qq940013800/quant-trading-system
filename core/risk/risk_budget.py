# -*- coding: utf-8 -*-
"""core.risk.risk_budget —— 风险预算分配与相关性熔断纯函数。

第一性原理（对照机构组合风控实践）：
- 绩效打分分配的是"资金权重"，本模块分配的是"风险预算"：波动越大的策略，
  分到的风险预算越低；目标是让各策略对组合风险的贡献趋于均衡，而不是按资金
  比例平均撒钱。
- 分散化必须是"不相关的分散"。当策略收益序列之间成对相关普遍偏高时，
  组合名义上有多策略，实质上暴露在同一风险因子上（伪分散化）。本模块据此
  提供相关性熔断纯判断：高相关对或平均成对相关越线即触发，交上层决策链处置。

边界与不变量：
- 纯函数：无 IO、无数据库、不发起下单或改仓；可被回测/研究/服务层复用。
- 阈值全部由调用方/配置注入，模块内不写业务阈值（AGENTS 硬规则 8）。
- 输入守卫：序列等长且长度 ≥2、元素有限；波动率非负有限；阈值落在 (0,1]。
"""
from __future__ import annotations

import math
from typing import Mapping, Sequence

import numpy as np


# ---------------------------------------------------------------------------
# 内部守卫
# ---------------------------------------------------------------------------
def _check_positive_finite(value: float, name: str) -> float:
    v = float(value)
    if not math.isfinite(v):
        raise ValueError(f"{name} 必须为有限数: {value!r}")
    if v < 0:
        raise ValueError(f"{name} 必须为非负: {value!r}")
    return v


def _check_threshold(value: float, name: str) -> float:
    v = float(value)
    if not math.isfinite(v) or not (0.0 < v <= 1.0):
        raise ValueError(f"{name} 必须落在 (0, 1]: {value!r}")
    return v


def _positive_int(name: str, val: int) -> int:
    if isinstance(val, bool) or not isinstance(val, int):
        raise ValueError(f"{name} 必须为整数，收到 {val!r}")
    if val < 1:
        raise ValueError(f"{name} 必须 >= 1，收到 {val}")
    return val


def _check_returns(returns: Mapping[str, Sequence[float]]) -> list[str]:
    if not isinstance(returns, Mapping) or len(returns) < 2:
        raise ValueError("returns 至少需要 2 个策略的收益序列")
    ids = list(returns.keys())
    length = None
    for sid in ids:
        series = list(returns[sid])
        if len(series) < 2:
            raise ValueError(f"策略 {sid!r} 收益序列长度必须 ≥2")
        if length is None:
            length = len(series)
        elif len(series) != length:
            raise ValueError("各策略收益序列必须等长")
        for x in series:
            if not math.isfinite(float(x)):
                raise ValueError(f"策略 {sid!r} 收益含非有限值: {x!r}")
    return ids


# ---------------------------------------------------------------------------
# 风险预算分配
# ---------------------------------------------------------------------------
def risk_budget_weights(volatilities: Mapping[str, float]) -> dict[str, float]:
    """按风险贡献倒数归一化分配风险预算。

    权重 ∝ 1/σ_i：波动越高，分到的风险预算越低。
    当某策略波动率为 0 时，其倒数按等权兜底处理，避免除零；全部为 0 时退化为等权。

    Args:
        volatilities: 策略ID → 波动率（非负有限数）。

    Returns:
        策略ID → 风险预算权重，归一到和为 1.0。
    """
    if not isinstance(volatilities, Mapping) or len(volatilities) == 0:
        raise ValueError("volatilities 不能为空")

    raw: dict[str, float] = {}
    for sid, vol in volatilities.items():
        raw[sid] = _check_positive_finite(vol, f"波动率({sid})")

    inv = {sid: (0.0 if v == 0 else 1.0 / v) for sid, v in raw.items()}
    total = sum(inv.values())
    if total <= 0:
        # 全部波动率为 0：退化为等权，保证可分配。
        n = len(raw)
        return {sid: 1.0 / n for sid in raw}
    return {sid: inv[sid] / total for sid in raw}


# ---------------------------------------------------------------------------
# 相关性计算与熔断
# ---------------------------------------------------------------------------
def _pearson(x: Sequence[float], y: Sequence[float]) -> float:
    n = len(x)
    mx = sum(x) / n
    my = sum(y) / n
    cov = 0.0
    vx = 0.0
    vy = 0.0
    for xi, yi in zip(x, y):
        dx = xi - mx
        dy = yi - my
        cov += dx * dy
        vx += dx * dx
        vy += dy * dy
    if vx <= 0 or vy <= 0:
        # 常数列：方差为 0，相关系数不可定义，按 0 容忍退化。
        return 0.0
    return cov / math.sqrt(vx * vy)


def correlation_pairs(
    returns: Mapping[str, Sequence[float]], threshold: float
) -> list[dict[str, object]]:
    """返回相关系数严格大于 threshold 的策略对。

    Args:
        returns: 策略ID → 收益序列（等长、长度 ≥2、元素有限）。
        threshold: 高相关阈值，由调用方注入，落在 (0,1]。

    Returns:
        列表，每项含 ``pair``（"A vs B"）与 ``correlation``（保留 3 位小数）。
    """
    ids = _check_returns(returns)
    _check_threshold(threshold, "corr_threshold")
    pairs: list[dict[str, object]] = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            corr = _pearson(list(returns[ids[i]]), list(returns[ids[j]]))
            if corr > threshold:
                pairs.append(
                    {
                        "pair": f"{ids[i]} vs {ids[j]}",
                        "correlation": round(corr, 3),
                    }
                )
    return pairs


def average_pairwise_correlation(returns: Mapping[str, Sequence[float]]) -> float:
    """上三角成对相关系数的平均值；策略数 <2 时返回 0.0。"""
    ids = _check_returns(returns)
    n = len(ids)
    if n < 2:
        return 0.0
    total = 0.0
    count = 0
    for i in range(n):
        for j in range(i + 1, n):
            total += _pearson(list(returns[ids[i]]), list(returns[ids[j]]))
            count += 1
    return total / count if count else 0.0


def correlation_breaker(
    returns: Mapping[str, Sequence[float]],
    *,
    corr_threshold: float,
    max_avg_corr: float,
) -> tuple[bool, dict[str, object]]:
    """分散化熔断判断。

    触发条件（任一满足即熔断）：
    1. 存在相关系数 > ``corr_threshold`` 的高相关策略对；
    2. 平均成对相关 > ``max_avg_corr``。

    Args:
        returns: 策略ID → 收益序列（等长、长度 ≥2、元素有限）。
        corr_threshold: 单对高相关阈值，落在 (0,1]。
        max_avg_corr: 平均成对相关上限，落在 (0,1]。

    Returns:
        ``(triggered, report)``；``report`` 含策略列表、平均相关、高相关对与
        触发原因。熔断只给出判断与证据，不执行任何处置动作。
    """
    ids = _check_returns(returns)
    _check_threshold(corr_threshold, "corr_threshold")
    _check_threshold(max_avg_corr, "max_avg_corr")

    high_pairs = correlation_pairs(returns, corr_threshold)
    avg_corr = average_pairwise_correlation(returns)

    reasons: list[str] = []
    if high_pairs:
        reasons.append(f"存在 {len(high_pairs)} 对高相关策略（>{corr_threshold:.2f}）")
    if avg_corr > max_avg_corr:
        reasons.append(
            f"平均成对相关 {avg_corr:.3f} 超过上限 {max_avg_corr:.3f}"
        )

    triggered = bool(reasons)
    report: dict[str, object] = {
        "strategies": ids,
        "avg_correlation": round(avg_corr, 3),
        "high_correlation_pairs": high_pairs,
        "triggered": triggered,
        "reasons": reasons,
    }
    return triggered, report


# ---------------------------------------------------------------------------
# 等风险贡献（ERC / 风险平价）
# ---------------------------------------------------------------------------
def risk_parity_weights(returns: Mapping[str, Sequence[float]],
                       *, max_iter: int = 1000, tol: float = 1e-9
                       ) -> dict[str, float]:
    """等风险贡献（ERC，风险平价）权重。

    与 :func:`risk_budget_weights`（逆波动，忽略策略间相关性）不同，本函数
    基于收益协方差矩阵迭代求解，使各策略对组合方差的风险贡献占比趋于相等；
    相关结构高、风险重叠大的策略自动分到更低权重。纯函数：无 IO、不下单、
    不做参数寻优，阈值由调用方注入。

    Args:
        returns: 策略ID → 收益序列（等长、长度 ≥2、元素有限）。
        max_iter: 迭代上限（正整数）。
        tol: 风险贡献占比偏离 1/n 的收敛容差（正数）。

    Returns:
        策略ID → ERC 权重，归一到和为 1.0。协方差退化（全部零方差或非
        有限）时退化为等权。
    """
    ids = _check_returns(returns)
    max_iter = _positive_int("max_iter", max_iter)
    tol = _check_positive_finite(tol, "tol")
    if tol <= 0.0:
        raise ValueError(f"tol 必须 > 0，收到 {tol!r}")
    n = len(ids)
    if n == 1:
        return {ids[0]: 1.0}

    matrix = np.array([list(returns[s]) for s in ids], dtype=float)
    cov = np.atleast_2d(np.cov(matrix, ddof=1))
    vols = np.sqrt(np.diag(cov))

    zero_vol = 1e-12
    if not np.all(np.isfinite(cov)) or np.all(vols < zero_vol):
        return {sid: 1.0 / n for sid in ids}

    safe_vol = np.where(vols > zero_vol, vols, 1.0)
    inv = np.where(vols > zero_vol, 1.0 / safe_vol, 1.0)
    w = inv / inv.sum()

    target = 1.0 / n
    for _ in range(max_iter):
        mrc = cov @ w
        port_var = float(w @ mrc)
        if port_var < 1e-24 or not math.isfinite(port_var):
            return {sid: 1.0 / n for sid in ids}
        share = (w * mrc) / port_var
        if float(np.max(np.abs(share - target))) < tol:
            break
        adj = np.where(share > 1e-12, (target / share) ** 0.5, 1.0)
        w = np.clip(w * adj, 1e-12, None)
        w = w / w.sum()

    return {sid: float(w[i]) for i, sid in enumerate(ids)}


# ---------------------------------------------------------------------------
# 相关性时序突变（当前窗口 vs 基准窗口）
# ---------------------------------------------------------------------------
def correlation_regime_shift(
    current_returns: Mapping[str, Sequence[float]],
    baseline_returns: Mapping[str, Sequence[float]],
    *,
    corr_jump: float,
    min_factor: float = 0.5,
) -> tuple[bool, dict[str, object]]:
    """检测策略间相关性相对基准窗口的时序突变。

    与 :func:`correlation_breaker`（横截面：当前窗口内相关是否偏高）不同，
    本函数比较当前窗口与基准窗口的平均成对相关，识别相关结构"突变跃升"。
    纯函数：只给判定与证据，不执行任何降仓/降杠杆处置动作。

    Args:
        current_returns: 当前窗口 策略ID → 收益序列（等长、≥2、有限）。
        baseline_returns: 基准/历史窗口 策略ID → 收益序列，策略集合须与当前一致。
        corr_jump: 平均相关绝对跃升阈值（非负有限）；``delta > corr_jump`` 判突变。
        min_factor: 突变时建议杠杆系数的下限，落在 (0,1]。

    Returns:
        ``(shifted, report)``；``report`` 含策略、当前/基准平均相关、相关增量、
        是否突变、建议杠杆系数与触发原因。
    """
    cur_ids = _check_returns(current_returns)
    base_ids = _check_returns(baseline_returns)
    if set(cur_ids) != set(base_ids):
        raise ValueError(
            "当前窗口与基准窗口策略集合不一致: "
            f"current={cur_ids}, baseline={base_ids}")

    def _real(name: str, val: object) -> float:
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise ValueError(f"{name} 必须为数值，收到 {val!r}")
        return _check_positive_finite(val, name)

    jump = _real("corr_jump", corr_jump)
    if isinstance(min_factor, bool) or not isinstance(min_factor, (int, float)):
        raise ValueError(f"min_factor 必须为数值，收到 {min_factor!r}")
    _check_threshold(min_factor, "min_factor")

    cur_avg = average_pairwise_correlation(current_returns)
    base_avg = average_pairwise_correlation(baseline_returns)
    delta = cur_avg - base_avg
    shifted = delta > jump

    reasons: list[str] = []
    if shifted:
        reasons.append(
            f"平均成对相关由 {base_avg:.3f} 升至 {cur_avg:.3f}，"
            f"跃升 {delta:.3f} 超过阈值 {jump:.3f}")

    if shifted:
        # 相关跃升越多，杠杆系数越低；跌幅不缩；下限 min_factor 兜底。
        factor = max(min_factor, min(1.0, 1.0 - max(delta, 0.0)))
    else:
        factor = 1.0

    report: dict[str, object] = {
        "strategies": cur_ids,
        "current_avg_correlation": round(cur_avg, 3),
        "baseline_avg_correlation": round(base_avg, 3),
        "corr_delta": round(delta, 3),
        "shifted": shifted,
        "suggested_leverage_factor": round(factor, 4),
        "reasons": reasons,
    }
    return shifted, report
