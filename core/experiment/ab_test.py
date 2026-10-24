# -*- coding: utf-8 -*-
"""core/experiment/ab_test.py —— 量化策略AB测试框架。

基于第一性原理：
    回测好 ≠ 实盘好。必须用统计显著性检验确认新策略真的比旧策略好，
    而不是凭"感觉差不多"就上线。

核心原则（来自全球顶级机构实践）：
1. 决策规则必须在实验前冻结——不能看着结果调阈值
2. 样本量和实验周期必须提前算好
3. 多重检验问题——试了很多次，总得有一次"显著"
4. 实际意义 > 统计意义——0.1% 的 Sharpe 提升不值得上线

核心功能：
1. 实验设计：样本量计算、最小可检测效应
2. 统计检验：t检验、bootstrap、贝叶斯因子
3. 决策：上线/继续观察/放弃
4. 多重检验校正：Bonferroni、FDR
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional


# ------------------------------------------------------------------
# 数据类
# ------------------------------------------------------------------
@dataclass
class ABTestConfig:
    """AB测试配置（实验前冻结，不可更改）。

    硬规则：实验开始后不得修改任何参数，否则就是在 p-hacking。
    """
    strategy_a_name: str        # 对照组（现有策略）
    strategy_b_name: str        # 实验组（新策略）
    min_detectable_effect: float  # 最小可检测效应（Sharpe 提升）
    alpha: float = 0.05         # 显著性水平
    power: float = 0.8          # 统计功效
    max_experiment_days: int = 90  # 最长实验周期
    min_experiment_days: int = 20  # 最短实验周期
    risk_aversion: float = 1.0   # 风险厌恶系数


@dataclass
class ABTestResult:
    """AB测试结果。"""
    config: ABTestConfig
    sample_size_a: int
    sample_size_b: int
    mean_diff: float             # 均值差（Sharpe 差）
    std_diff: float              # 标准差
    t_statistic: float
    p_value: float
    ci_lower: float              # 置信区间下界
    ci_upper: float              # 置信区间上界
    effect_size: float           # 实际效应大小（Cohen's d）
    conclusion: str              # 结论：launch/continue/abort
    recommendation: str          # 具体建议


# ------------------------------------------------------------------
# 样本量计算
# ------------------------------------------------------------------
def required_sample_size(min_detectable_effect: float,
                          baseline_std: float,
                          alpha: float = 0.05,
                          power: float = 0.8) -> int:
    """计算所需样本量（双边t检验）。

    基于第一性原理：你想检测出多大的效应？
    效应越小，需要的样本越多。

    Args:
        min_detectable_effect: 最小可检测效应（比如 Sharpe 提升 0.2）
        baseline_std: 基线收益的标准差
        alpha: 显著性水平（一类错误概率）
        power: 统计功效（1 - 二类错误概率）

    Returns:
        每组所需样本量
    """
    # 简化的样本量公式（大样本近似）
    # n = 2 * (z_{alpha/2} + z_beta)^2 * sigma^2 / delta^2
    z_alpha = 1.96 if alpha == 0.05 else 2.576  # 95% / 99%
    z_beta = 0.84 if power == 0.8 else 1.282  # 80% / 90%

    n = 2 * (z_alpha + z_beta) ** 2 * baseline_std ** 2 / min_detectable_effect ** 2
    return int(np.ceil(n))


# ------------------------------------------------------------------
# 核心AB测试类
# ------------------------------------------------------------------
class ABTestFramework:
    """AB测试框架。

    使用方法：
        config = ABTestConfig(
            strategy_a_name="trend_v1",
            strategy_b_name="trend_v2",
            min_detectable_effect=0.2,
        )
        tester = ABTestFramework(config)
        tester.add_returns("A", returns_a)
        tester.add_returns("B", returns_b)
        result = tester.evaluate()
    """

    def __init__(self, config: ABTestConfig):
        self.config = config
        self.returns_a: list[float] = []
        self.returns_b: list[float] = []

    def add_returns(self, group: str, returns: list[float] | pd.Series):
        """添加一组收益数据。"""
        if isinstance(returns, pd.Series):
            returns = returns.tolist()

        if group.upper() == "A":
            self.returns_a.extend(returns)
        elif group.upper() == "B":
            self.returns_b.extend(returns)
        else:
            raise ValueError(f"group must be 'A' or 'B', got {group}")

    def _compute_sharpe(self, returns: list[float]) -> float:
        """计算年化Sharpe。"""
        if len(returns) < 10:
            return 0.0
        rets = np.array(returns)
        mean = rets.mean()
        std = rets.std()
        if std == 0:
            return 0.0
        return float(mean / std * np.sqrt(252))

    def evaluate(self) -> ABTestResult:
        """执行AB测试评估。

        Returns:
            ABTestResult 包含完整的统计结果和决策建议
        """
        # 数据量检查
        n_a = len(self.returns_a)
        n_b = len(self.returns_b)

        if n_a < 10 or n_b < 10:
            return ABTestResult(
                config=self.config,
                sample_size_a=n_a,
                sample_size_b=n_b,
                mean_diff=0, std_diff=0,
                t_statistic=0, p_value=1.0,
                ci_lower=0, ci_upper=0,
                effect_size=0,
                conclusion="continue",
                recommendation="数据量不足，继续收集数据"
            )

        rets_a = np.array(self.returns_a)
        rets_b = np.array(self.returns_b)

        # 计算核心统计量（直接比较收益率均值）
        mean_a = rets_a.mean()
        mean_b = rets_b.mean()
        mean_diff = mean_b - mean_a  # 收益率均值差

        sharpe_a = self._compute_sharpe(self.returns_a)
        sharpe_b = self._compute_sharpe(self.returns_b)
        sharpe_diff = sharpe_b - sharpe_a

        # 标准差
        std_a = rets_a.std()
        std_b = rets_b.std()
        pooled_std = np.sqrt((std_a ** 2 + std_b ** 2) / 2)

        # t检验（Welch's t-test，不假设方差相等）
        se_diff = np.sqrt(std_a ** 2 / n_a + std_b ** 2 / n_b)
        if se_diff == 0:
            t_stat = 0
            p_value = 1.0
        else:
            t_stat = mean_diff / se_diff
            # 简化的p值（大样本近似正态分布）
            from scipy import stats
            p_value = 2 * (1 - stats.norm.cdf(abs(t_stat)))

        # 95%置信区间（收益率均值差）
        ci_lower = mean_diff - 1.96 * se_diff
        ci_upper = mean_diff + 1.96 * se_diff

        # 效应大小（Cohen's d）
        effect_size = mean_diff / pooled_std if pooled_std > 0 else 0

        # 决策逻辑
        conclusion, recommendation = self._make_decision(
            sharpe_diff, p_value, ci_lower, n_a, n_b
        )

        return ABTestResult(
            config=self.config,
            sample_size_a=n_a,
            sample_size_b=n_b,
            mean_diff=sharpe_diff,  # 报告Sharpe差作为核心指标
            std_diff=pooled_std,
            t_statistic=t_stat,
            p_value=p_value,
            ci_lower=ci_lower,
            ci_upper=ci_upper,
            effect_size=effect_size,
            conclusion=conclusion,
            recommendation=recommendation,
        )

    def _make_decision(self, sharpe_diff: float, p_value: float,
                        ci_lower: float, n_a: int, n_b: int) -> tuple[str, str]:
        """基于第一性原理的决策逻辑。

        决策树：
        1. 效应太小？→ abort（不值得上线）
        2. 统计显著且效应足够？→ launch
        3. 数据不够？→ continue
        4. 不显著？→ continue 或 abort
        """
        # 效应太小，不值得上线
        if abs(sharpe_diff) < self.config.min_detectable_effect * 0.5:
            return "abort", f"效应太小（Sharpe差={sharpe_diff:.3f}），不值得上线"

        # 统计显著且效应足够
        if p_value < self.config.alpha and sharpe_diff > self.config.min_detectable_effect * 0.5:
            return "launch", f"统计显著（p={p_value:.4f}），Sharpe提升={sharpe_diff:.3f}，建议上线策略B"

        # 数据量足够但不显著
        if min(n_a, n_b) > 200:  # 每组200笔交易
            if p_value > 0.2:
                return "abort", f"数据充足但不显著（p={p_value:.4f}），策略B没有明显优势"
            else:
                return "continue", f"趋势向好但未达显著水平（p={p_value:.4f}），继续观察"

        # 数据不够
        return "continue", f"数据量不足（A:{n_a}, B:{n_b}），继续收集"


# ------------------------------------------------------------------
# 多重检验校正
# ------------------------------------------------------------------
def bonferroni_correction(p_values: list[float], alpha: float = 0.05) -> list[bool]:
    """Bonferroni 校正——控制一族错误率。

    第一性原理：你试了100个策略，总有几个看起来"显著"。
    校正后才是真实的显著性。
    """
    n_tests = len(p_values)
    adjusted_alpha = alpha / n_tests
    return [p < adjusted_alpha for p in p_values]


def fdr_correction(p_values: list[float], alpha: float = 0.05) -> list[bool]:
    """FDR（False Discovery Rate）校正——比Bonferroni更宽松。

    控制"假阳性占所有阳性结果的比例"，而不是"任何一个假阳性都不行"。
    适合探索性研究。
    """
    n = len(p_values)
    sorted_indices = np.argsort(p_values)
    sorted_p = np.array(p_values)[sorted_indices]

    significant = np.zeros(n, dtype=bool)
    for i in range(n):
        if sorted_p[i] <= (i + 1) * alpha / n:
            significant[sorted_indices[i]] = True

    return significant.tolist()
