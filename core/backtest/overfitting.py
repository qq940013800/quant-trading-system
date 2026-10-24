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

import numpy as np
import pandas as pd


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
    if len(returns) < 2:
        return 0.0
    
    excess = returns - risk_free / bars_per_year
    sd = excess.std(ddof=1)
    if sd == 0:
        return 0.0
    
    return float(excess.mean() / sd * np.sqrt(bars_per_year))


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
    if len(returns) < 30:
        return 0.5  # 样本太少，无法判断
    
    sr = compute_sharpe(returns, bars_per_year)
    n = len(returns)
    
    # 计算偏度和峰度
    if skewness is None:
        skewness = float(returns.skew())  # type: ignore[arg-type]
    if kurtosis is None:
        kurtosis = float(returns.kurtosis())  # type: ignore[arg-type]
    
    # 期望值 Sharpe：在 null hypothesis 下（所有策略都是随机的）
    # 最好那个的期望 Sharpe
    # 近似：E[max SR] ≈ sqrt(Var(SR)) * (1 - γ) * Φ^(-1)(1 - 1/N) + γ * Φ^(-1)(1 - 1/(N*e))
    # 其中 γ ≈ 0.5772（Euler-Mascheroni 常数）
    
    # Sharpe 的方差估计
    # Var(SR) ≈ (1 - skewness*SR + (kurtosis-1)/4 * SR^2) / (n-1)
    sr_annual = sr
    sr_period = sr / np.sqrt(bars_per_year)  # 周期 Sharpe
    
    var_sr = (1 - skewness * sr_period + (kurtosis - 1) / 4 * sr_period**2) / (n - 1)
    sd_sr = np.sqrt(var_sr) if var_sr > 0 else 0.001
    
    # 期望最大 Sharpe（多重检验修正）
    if trials > 1:
        # 用极值分布近似
        gamma = 0.5772  # Euler-Mascheroni
        # 近似计算 Φ^(-1)(1 - 1/N)
        # 简化：用经验公式
        expected_max_sr = sd_sr * (
            np.sqrt(2 * np.log(trials)) - 
            (np.log(np.log(trials)) + np.log(4 * np.pi)) / (2 * np.sqrt(2 * np.log(trials)))
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
def probability_of_backtest_overfitting(strategy_returns: pd.DataFrame,
                                        n_splits: int = 10,
                                        test_size: float = 0.5) -> float:
    """计算 PBO：回测过拟合概率。

    第一性原理：把数据分成训练集和测试集，
    在训练集上选最好的策略，看它在测试集上是不是还是最好的。
    如果经常不是，说明你在过拟合。

    Args:
        strategy_returns: 多个策略的收益率矩阵（列=策略，行=时间）
        n_splits: 交叉验证折数
        test_size: 测试集比例

    Returns:
        PBO 值（0-1）：
        - 越低越好（< 0.2 表示过拟合风险低）
        - 越高越危险（> 0.5 表示很可能过拟合）
    """
    n_periods = len(strategy_returns)
    n_strategies = len(strategy_returns.columns)
    
    if n_strategies < 2:
        return 0.0  # 只有一个策略，谈不上过拟合
    
    n_test = int(n_periods * test_size)
    n_train = n_periods - n_test
    
    if n_train < 30 or n_test < 30:
        return 0.5  # 样本太少
    
    # 多次随机分割，统计过拟合次数
    overfit_count = 0
    n_iterations = min(n_splits, 20)  # 计算成本控制
    
    np.random.seed(42)  # 可复现
    
    for _ in range(n_iterations):
        # 随机分割
        indices = np.random.permutation(n_periods)
        train_idx = indices[:n_train]
        test_idx = indices[n_train:]
        
        train_returns = strategy_returns.iloc[train_idx]
        test_returns = strategy_returns.iloc[test_idx]
        
        # 在训练集上计算每个策略的 Sharpe
        train_sharpes = train_returns.apply(
            lambda x: compute_sharpe(x, bars_per_year=252)
        )
        
        # 选训练集上最好的策略
        best_train_strategy = train_sharpes.idxmax()
        best_train_rank = train_sharpes.rank(ascending=False)[best_train_strategy]  # type: ignore[call-overload]
        
        # 在测试集上计算排名
        test_sharpes = test_returns.apply(
            lambda x: compute_sharpe(x, bars_per_year=252)
        )
        test_rank = test_sharpes.rank(ascending=False)[best_train_strategy]  # type: ignore[call-overload]
        
        # 过拟合定义：训练集最好的策略，在测试集排名掉到下半区
        if test_rank > n_strategies / 2:
            overfit_count += 1
    
    pbo = overfit_count / n_iterations
    return float(pbo)


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
    n = len(returns)
    fold_size = n // n_splits
    
    if fold_size < 30:
        return {"train_sharpes": [], "test_sharpes": [], "ratio": 1.0}
    
    purge_size = int(fold_size * purge_fraction)
    
    train_sharpes = []
    test_sharpes = []
    
    for i in range(n_splits):
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
    sr = compute_sharpe(returns, bars_per_year)
    dsr = deflated_sharpe_ratio(returns, trials, bars_per_year)
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
