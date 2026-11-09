# -*- coding: utf-8 -*-
"""core.backtest.overfitting —— 过拟合防御与统计验证。

基于第一性原理：回测好看不等于策略有效——你试了100次，挑最好的那个，
那不是策略能力，是运气。本模块提供严格的统计验证工具。

核心工具：
- Deflated Sharpe Ratio：修正多重检验偏差
- PBO (Probability of Backtest Overfitting)：回测过拟合概率
- CPCV (Combinatorial Purged Cross-Validation)：组合净化交叉验证

参考：Bailey & López de Prado 的过拟合防御框架。
"""
from __future__ import annotations

import math
from itertools import combinations

import numpy as np
import pandas as pd


def _finite(name: str, val: float) -> float:
    if not isinstance(val, (int, float)) or isinstance(val, bool) \
            or not np.isfinite(val):
        raise ValueError(f"{name} 必须为有限数值，收到 {val!r}")
    return float(val)


def _as_int(name: str, val: int) -> int:
    if isinstance(val, bool) or not isinstance(val, int):
        raise ValueError(f"{name} 必须为整数，收到 {val!r}")
    return val


def _min_int(name: str, val: int, lo: int) -> int:
    v = _as_int(name, val)
    if v < lo:
        raise ValueError(f"{name} 必须 >= {lo}，收到 {v}")
    return v


# ------------------------------------------------------------------
# 基础：Sharpe Ratio
# ------------------------------------------------------------------
def compute_sharpe(returns: pd.Series, bars_per_year: int = 252,
                   risk_free: float = 0.0) -> float:
    """计算年化夏普比率。

    Args:
        returns: 收益率序列
        bars_per_year: 每年 bar 数量
        risk_free: 无风险利率（年化）

    Returns:
        年化 Sharpe Ratio
    """
    bpy = _min_int("bars_per_year", bars_per_year, 1)
    _finite("risk_free", risk_free)
    if len(returns) < 2:
        return 0.0

    excess = returns - risk_free / bpy
    sd = excess.std(ddof=1)
    if sd == 0:
        return 0.0

    return float(excess.mean() / sd * np.sqrt(bpy))


# ------------------------------------------------------------------
# Deflated Sharpe Ratio (DSR)
# ------------------------------------------------------------------
def _normal_cdf(x: float) -> float:
    """标准正态分布 CDF（近似实现，不依赖 scipy）。"""
    # 使用 Abramowitz & Stegun 近似
    a1, a2, a3, a4, a5 = 0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429
    p = 0.3275911
    
    sign = 1 if x >= 0 else -1
    x = abs(x) / np.sqrt(2.0)
    t = 1.0 / (1.0 + p * x)
    y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * np.exp(-x * x)
    
    return 0.5 * (1.0 + sign * y)


def deflated_sharpe_ratio(returns: pd.Series, trials: int = 1,
                           bars_per_year: int = 252,
                           skewness: float | None = None,
                           kurtosis: float | None = None) -> float:
    """计算 Deflated Sharpe Ratio（修正多重检验偏差）。

    第一性原理：如果你试了 N 个策略，即使都是随机的，
    最好的那个也会有不错的 Sharpe。DSR 修正了这个偏差。

    Args:
        returns: 选中策略的收益率序列
        trials: 总共试验了多少次（包括失败的）
        bars_per_year: 每年 bar 数量
        skewness: 收益率偏度（自动计算如果为 None）
        kurtosis: 收益率峰度（自动计算如果为 None）

    Returns:
        DSR 值（0-1）：策略真实有效的概率
        - > 0.95：统计显著，策略可能真的有效
        - < 0.5：很可能是过拟合/运气
    """
    trials_v = _min_int("trials", trials, 1)
    bpy = _min_int("bars_per_year", bars_per_year, 1)
    if skewness is not None:
        _finite("skewness", skewness)
    if kurtosis is not None:
        _finite("kurtosis", kurtosis)
    if len(returns) < 30:
        return 0.5  # 样本太少，无法判断

    sr = compute_sharpe(returns, bpy)
    n = len(returns)
    
    # 计算偏度和峰度（pandas 的 kurtosis() 返回超额峰度；DSR 公式要求原始峰度 γ4）
    if skewness is None:
        skewness = float(returns.skew())  # type: ignore[arg-type]
    if kurtosis is None:
        kurtosis = float(returns.kurtosis()) + 3.0  # type: ignore[arg-type]
    
    # 期望值 Sharpe：在 null hypothesis 下（所有策略都是随机的）
    # 最好那个的期望 Sharpe
    # 近似：E[max SR] ≈ sqrt(Var(SR)) * (1 - γ) * Φ^(-1)(1 - 1/N) + γ * Φ^(-1)(1 - 1/(N*e))
    # 其中 γ ≈ 0.5772（Euler-Mascheroni 常数）
    
    # Sharpe 的方差估计
    # Var(SR) ≈ (1 - skewness*SR + (kurtosis-1)/4 * SR^2) / (n-1)
    sr_annual = sr
    sr_period = sr / np.sqrt(bpy)  # 周期 Sharpe
    
    var_sr = (1 - skewness * sr_period + (kurtosis - 1) / 4 * sr_period**2) / (n - 1)
    sd_sr = np.sqrt(var_sr) if var_sr > 0 else 0.001
    
    # 期望最大 Sharpe（多重检验修正）
    if trials_v > 1:
        # 用极值分布近似
        gamma = 0.5772  # Euler-Mascheroni
        # 近似计算 Φ^(-1)(1 - 1/N)
        # 简化：用经验公式
        expected_max_sr = sd_sr * (
            np.sqrt(2 * np.log(trials_v)) -
            (np.log(np.log(trials_v)) + np.log(4 * np.pi)) / (2 * np.sqrt(2 * np.log(trials_v)))
        )
    else:
        expected_max_sr = 0.0
    
    # Deflated Sharpe：真实 Sharpe 减去期望最大 Sharpe
    dsr_period = (sr_period - expected_max_sr) / sd_sr if sd_sr > 0 else 0.0
    
    # 转换为概率
    dsr_prob = _normal_cdf(dsr_period)
    
    return float(np.clip(dsr_prob, 0.0, 1.0))


# ------------------------------------------------------------------
# PBO (Probability of Backtest Overfitting)
# ------------------------------------------------------------------
# PBO (Probability of Backtest Overfitting) — CSCV 标准实现
# ------------------------------------------------------------------
def _sharpe_columns(block: np.ndarray) -> np.ndarray:
    """按列计算 Sharpe（周期口径；同一子集内排序时年化因子可约去）。"""
    mu = block.mean(axis=0)
    sd = block.std(axis=0, ddof=1)
    out = np.zeros(mu.shape, dtype=np.float64)
    ok = sd > 0
    out[ok] = mu[ok] / sd[ok]
    return out


def _contiguous_blocks(n_periods: int, n_blocks: int) -> list[np.ndarray]:
    """把时间序列切成 n_blocks 个连续块（保持时间顺序，禁止随机打乱）。"""
    edges = np.linspace(0, n_periods, n_blocks + 1).astype(int)
    return [np.arange(edges[i], edges[i + 1], dtype=np.int64)
            for i in range(n_blocks)]


def _cscv_combinations(n_blocks: int, n_oos: int,
                       max_combinations: int) -> list[tuple[int, ...]]:
    """枚举 OOS 块组合；超过上限时按固定步长确定性抽样（不引入随机性）。"""
    total = math.comb(n_blocks, n_oos)
    combos = list(combinations(range(n_blocks), n_oos))
    if total <= max_combinations:
        return combos
    stride = math.ceil(total / max_combinations)
    return combos[::stride]


def probability_of_backtest_overfitting(
        strategy_returns: pd.DataFrame,
        n_splits: int = 10,
        test_size: float = 0.5,
        *,
        max_combinations: int = 5000,
        return_diagnostics: bool = False):
    """PBO（Bailey, Borwein, López de Prado & Zhu 2015）—— CSCV 实现。

    第一性原理：回测过拟合不是"曲线不好看"，而是"选择行为本身制造了
    虚假的样本内优势"。CSCV 把整条收益矩阵切成 S 个连续块，枚举一部分
    块作样本内（IS）、其余作样本外（OOS）：在 IS 上选表现最好的策略，
    看它在 OOS 的相对排名是否落到下半区。落到下半区的组合占比即 PBO。

    与旧实现的区别（旧实现已删除）：
    - 旧实现随机打乱时间轴，破坏时序结构，且对同一数据不可复现；
    - 旧实现用"测试集排名 > N/2"的粗判定，并使用全局随机种子污染调用方；
    - 新实现为确定性枚举（contiguous blocks + combinations），无随机数。

    Args:
        strategy_returns: 多个策略的收益率矩阵（行=时间，列=策略；列名即策略名）。
        n_splits: CSCV 块数 S；为奇数时向下取偶（S>=4 才有意义）。
        test_size: OOS 块占比，默认 0.5（标准 CSCV）。
        max_combinations: 组合数上限，超过则确定性等距抽样（结果可复现）。
        return_diagnostics: True 时返回诊断 dict，默认返回 PBO 浮点数。

    Returns:
        float 或 dict（见 return_diagnostics）。0 表示未观察到过拟合，
        0.5 附近表示选择行为接近随机，>0.5 表示样本内最优在样本外系统性失效。

    Raises:
        TypeError: strategy_returns 不是 DataFrame，或 n_splits 不是 int。
        ValueError: 含 NaN/Inf，或 test_size 不在 (0,1) 区间。
    """
    if not isinstance(strategy_returns, pd.DataFrame):
        raise TypeError("strategy_returns must be a pandas DataFrame")
    if not isinstance(n_splits, int):
        raise TypeError("n_splits must be int")
    if not 0.0 < float(test_size) < 1.0:
        raise ValueError(f"test_size must be in (0,1), got {test_size}")
    _min_int("max_combinations", max_combinations, 1)

    data = strategy_returns.to_numpy(dtype=np.float64)
    if data.ndim != 2 or data.shape[1] < 2:
        return 0.0  # 单一策略不存在"选择"问题
    if not np.isfinite(data).all():
        raise ValueError("strategy_returns contains NaN/Inf; clean data before PBO")

    n_periods, n_strategies = data.shape
    n_blocks = n_splits - (n_splits % 2)
    if n_blocks < 4 or n_periods // n_blocks < 2:
        # 样本不足以下结论：返回 0.5（最大不确定性），调用方应记录为"未判定"
        return 0.5

    n_oos = max(1, min(n_blocks - 1, int(round(n_blocks * float(test_size)))))
    blocks = _contiguous_blocks(n_periods, n_blocks)
    combos = _cscv_combinations(n_blocks, n_oos, max_combinations)

    logits: list[float] = []
    is_best: list[int] = []
    for combo in combos:
        combo_set = set(combo)
        oos_idx = np.concatenate([blocks[i] for i in combo])
        is_idx = np.concatenate([blocks[i] for i in range(n_blocks)
                                 if i not in combo_set])
        if oos_idx.size < 2 or is_idx.size < 2:
            continue
        is_perf = _sharpe_columns(data[is_idx])
        oos_perf = _sharpe_columns(data[oos_idx])
        best = int(np.argmax(is_perf))
        is_best.append(best)
        order = np.argsort(oos_perf, kind="stable")
        rank = np.empty(n_strategies, dtype=np.int64)
        rank[order] = np.arange(1, n_strategies + 1)
        omega = float(rank[best]) / (n_strategies + 1)
        logits.append(math.log(omega / (1.0 - omega)))

    if not logits:
        return 0.5
    arr = np.asarray(logits, dtype=np.float64)
    pbo = float(np.mean(arr <= 0.0))
    if return_diagnostics:
        return {
            "pbo": pbo,
            "n_combinations": int(arr.size),
            "n_blocks": n_blocks,
            "n_strategies": n_strategies,
            "mean_logit": float(arr.mean()),
            "median_logit": float(np.median(arr)),
            "is_best_counts": {strategy_returns.columns[i]: is_best.count(i)
                               for i in range(n_strategies)},
            "logits": arr.tolist(),
        }
    return pbo


# ------------------------------------------------------------------
# CPCV (Combinatorial Purged Cross-Validation)
# ------------------------------------------------------------------
def combinatorial_purged_cv(returns: pd.Series, n_splits: int = 6,
                              purge_fraction: float = 0.05) -> dict:
    """组合净化交叉验证（CPCV）。

    第一性原理：传统交叉验证有数据泄露问题——
    训练集和测试集边界的数据互相影响。
    CPCV 通过"净化"（purge）和" embargo"来防止泄露。

    Args:
        returns: 收益率序列
        n_splits: 分成多少折
        purge_fraction: 边界净化比例

    Returns:
        dict:
            - train_sharpes: 各折训练集 Sharpe
            - test_sharpes: 各折测试集 Sharpe
            - ratio: test/train Sharpe 比值（样本外衰减）
    """
    n_splits_v = _min_int("n_splits", n_splits, 2)
    pf = _finite("purge_fraction", purge_fraction)
    if pf < 0.0 or pf >= 1.0:
        raise ValueError(f"purge_fraction 必须位于 [0,1)，收到 {pf!r}")
    n = len(returns)
    fold_size = n // n_splits_v
    
    if fold_size < 30:
        return {"train_sharpes": [], "test_sharpes": [], "ratio": 1.0}
    
    purge_size = int(fold_size * pf)

    train_sharpes = []
    test_sharpes = []

    for i in range(n_splits_v):
        # 测试集：第 i 折
        test_start = i * fold_size
        test_end = test_start + fold_size
        
        # 训练集：除了测试集，还要净化边界
        train_mask = np.ones(n, dtype=bool)
        train_mask[test_start:test_end] = False
        
        # 净化：测试集前后的 purge_size 个点也从训练集去掉
        purge_start = max(0, test_start - purge_size)
        purge_end = min(n, test_end + purge_size)
        train_mask[purge_start:purge_end] = False
        
        train_returns = returns[train_mask]
        test_returns = returns.iloc[test_start:test_end]
        
        if len(train_returns) < 30 or len(test_returns) < 10:
            continue
        
        train_sr = compute_sharpe(train_returns, bars_per_year=252)
        test_sr = compute_sharpe(test_returns, bars_per_year=252)
        
        train_sharpes.append(train_sr)
        test_sharpes.append(test_sr)
    
    # 计算衰减比
    if train_sharpes and test_sharpes:
        avg_train = np.mean(train_sharpes)
        avg_test = np.mean(test_sharpes)
        ratio = avg_test / avg_train if avg_train > 0 else 1.0
    else:
        ratio = 1.0
    
    return {
        "train_sharpes": train_sharpes,
        "test_sharpes": test_sharpes,
        "ratio": float(ratio),
    }


# ------------------------------------------------------------------
# 综合诊断：策略过拟合评分卡
# ------------------------------------------------------------------
def overfitting_diagnostic(returns: pd.Series, trials: int = 1,
                            bars_per_year: int = 252) -> dict:
    """综合过拟合诊断评分卡。

    Args:
        returns: 策略收益率序列
        trials: 试验次数
        bars_per_year: 每年 bar 数

    Returns:
        诊断结果 dict
    """
    trials_v = _min_int("trials", trials, 1)
    bpy = _min_int("bars_per_year", bars_per_year, 1)
    sr = compute_sharpe(returns, bpy)
    dsr = deflated_sharpe_ratio(returns, trials_v, bpy)
    cpcv_result = combinatorial_purged_cv(returns)
    
    # 综合判断
    score = 0
    warnings = []
    
    if sr < 0:
        warnings.append("Sharpe 为负，策略根本不赚钱")
        score -= 2
    elif sr > 2:
        warnings.append("Sharpe 太高，可能过拟合（警惕）")
        score -= 1
    
    if dsr < 0.5:
        warnings.append(f"DSR={dsr:.2f} 过低，很可能是运气/过拟合")
        score -= 2
    elif dsr > 0.95:
        score += 2
    
    if cpcv_result["ratio"] < 0.5:
        warnings.append(f"CPCV test/train ratio={cpcv_result['ratio']:.2f} 过低，样本外衰减严重")
        score -= 2
    elif cpcv_result["ratio"] > 0.8:
        score += 1
    
    # 评级
    if score >= 3:
        rating = "A - 策略可能真的有效"
    elif score >= 1:
        rating = "B - 有一定潜力，需更多验证"
    elif score >= -1:
        rating = "C - 存疑，过拟合风险中等"
    else:
        rating = "D - 很可能过拟合，不要上线"
    
    return {
        "sharpe": float(sr),
        "deflated_sharpe": float(dsr),
        "cpcv_ratio": cpcv_result["ratio"],
        "score": score,
        "rating": rating,
        "warnings": warnings,
    }
