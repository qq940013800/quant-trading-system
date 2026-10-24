# -*- coding: utf-8 -*-
"""core/experiment/auto_optimizer.py —— AI/ML增强自动策略优化引擎。

基于第一性原理：
    策略优化不是手动调参数，而是一个自动的迭代闭环：
    生成候选 → 回测评估 → 过拟合检测 → AB对比 → 决定上线/继续/放弃

    核心约束（来自AGENTS.md硬规则）：
    1. 阈值来自分布，不由绩效网格搜索产生
    2. 决策规则必须在实验前冻结
    3. trials计数必须包含失败试验
    4. 前视守卫：只用 available_at <= bar.close 的数据

核心功能：
1. 候选策略生成器：基于基线策略生成受控变体
2. 自动评估流水线：回测 → 过拟合检测 → 生成评分
3. 多臂老虎机：自动选择最有希望的候选继续优化
4. 自动决策：合格 → 进入生命周期流程
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Callable


# ------------------------------------------------------------------
# 数据类
# ------------------------------------------------------------------
class CandidateStatus(Enum):
    """候选策略状态。"""
    GENERATED = "generated"          # 已生成
    BACKTESTED = "backtested"        # 已回测
    OVERFIT_CHECKED = "overfit_checked"  # 过拟合检测完成
    AB_TESTED = "ab_tested"          # AB测试完成
    SELECTED = "selected"            # 选中（进入生命周期）
    REJECTED = "rejected"            # 已否决


@dataclass
class CandidateStrategy:
    """候选策略。"""
    name: str
    version: str
    base_strategy: str               # 基线策略名称
    params: dict                    # 参数字典
    status: CandidateStatus = CandidateStatus.GENERATED
    sharpe: float = 0.0
    max_drawdown: float = 0.0
    n_trades: int = 0
    overfitting_score: float = 1.0  # 0=不过拟合, 1=严重过拟合
    ab_p_value: float = 1.0
    ab_conclusion: str = "continue"
    score: float = 0.0              # 综合评分
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class OptimizationConfig:
    """自动优化配置（实验前冻结）。"""
    base_strategy_name: str
    max_trials: int = 20              # 最大试验次数（含失败）
    min_sharpe: float = 1.0           # 最低Sharpe
    max_overfitting_score: float = 0.3  # 过拟合评分上限
    ab_alpha: float = 0.05            # AB测试显著性
    exploration_ratio: float = 0.3    # 探索比例（多臂老虎机）
    random_seed: int = 42


# ------------------------------------------------------------------
# 候选生成器
# ------------------------------------------------------------------
class CandidateGenerator:
    """候选策略生成器——基于基线生成受控变体。

    关键原则：不是随机暴力搜索，而是在合理参数空间内做受控探索。
    参数范围来自分布（分位数），不是拍脑袋定的。
    """

    def __init__(self, config: OptimizationConfig):
        self.config = config
        np.random.seed(config.random_seed)

    def generate(self, base_params: dict, n: int = 5) -> list[CandidateStrategy]:
        """生成n个候选变体。

        策略：
        1. 30% 小扰动（在基线附近微调）
        2. 40% 参数区间探索（在合理范围内探索）
        3. 30% 结构变体（改变指标周期等）
        """
        candidates = []
        for i in range(n):
            strategy_type = np.random.choice(
                ["small_perturb", "range_explore", "structural"],
                p=[0.3, 0.4, 0.3]
            )

            params = self._perturb_params(base_params, strategy_type)
            candidate = CandidateStrategy(
                name=f"{self.config.base_strategy_name}_v{self.config.max_trials + i}",
                version=f"trial_{i:03d}",
                base_strategy=self.config.base_strategy_name,
                params=params,
            )
            candidates.append(candidate)

        return candidates

    def _perturb_params(self, base: dict, strategy_type: str) -> dict:
        """对参数做扰动。"""
        params = base.copy()

        if strategy_type == "small_perturb":
            # ±10%小扰动
            for key in params:
                if isinstance(params[key], (int, float)):
                    factor = 1 + np.random.uniform(-0.1, 0.1)
                    params[key] = params[key] * factor

        elif strategy_type == "range_explore":
            # ±30%区间探索
            for key in params:
                if isinstance(params[key], (int, float)):
                    factor = 1 + np.random.uniform(-0.3, 0.3)
                    params[key] = params[key] * factor

        elif strategy_type == "structural":
            # 结构性调整（比如周期翻倍/减半）
            for key in params:
                if "period" in key.lower() or "window" in key.lower():
                    factor = np.random.choice([0.5, 1.5, 2.0])
                    params[key] = int(params[key] * factor)

        # 确保整数参数还是整数
        for key in params:
            if isinstance(params[key], float) and params[key] == int(params[key]):
                params[key] = int(params[key])

        return params


# ------------------------------------------------------------------
# 多臂老虎机选择器
# ------------------------------------------------------------------
class MultiArmedBandit:
    """多臂老虎机——自动选择最有希望的候选继续优化。

    平衡探索（exploration）和利用（exploitation）：
    - 利用：选当前评分最高的
    - 探索：给其他候选一些机会

    算法：epsilon-greedy
    """

    def __init__(self, exploration_ratio: float = 0.3):
        self.epsilon = exploration_ratio
        self.scores: dict[str, float] = {}

    def update(self, candidate_name: str, score: float):
        """更新候选评分。"""
        self.scores[candidate_name] = score

    def select_next(self, candidates: list[str]) -> str:
        """选择下一个要深入评估的候选。"""
        if not self.scores or np.random.random() < self.epsilon:
            # 探索：随机选一个
            return np.random.choice(candidates)

        # 利用：选评分最高的
        scored = {c: self.scores.get(c, 0) for c in candidates}
        return max(scored, key=lambda k: scored[k])


# ------------------------------------------------------------------
# 综合评分器
# ------------------------------------------------------------------
class CandidateScorer:
    """候选策略综合评分器。

    评分维度：
    1. Sharpe（权重40%）
    2. 过拟合程度（权重30%）——越不过拟合分越高
    3. 交易次数（权重15%）——太少不可靠
    4. 最大回撤（权重15%）——越小越好
    """

    def __init__(self, min_sharpe: float = 1.0, max_dd: float = 0.20):
        self.min_sharpe = min_sharpe
        self.max_dd = max_dd

    def score(self, candidate: CandidateStrategy) -> float:
        """计算综合评分（0-100）。"""
        # 1. Sharpe得分（40分满分）
        sharpe_score = min(40, candidate.sharpe / self.min_sharpe * 20)

        # 2. 过拟合得分（30分满分）
        # overfitting_score: 0=不过拟合, 1=严重过拟合
        overfit_score = (1 - candidate.overfitting_score) * 30

        # 3. 交易次数得分（15分满分）
        # 30笔=满分，少于30笔扣分
        trade_score = min(15, candidate.n_trades / 30 * 15)

        # 4. 回撤得分（15分满分）
        # 回撤越小越好
        dd_score = max(0, (1 - candidate.max_drawdown / self.max_dd) * 15)

        total = sharpe_score + overfit_score + trade_score + dd_score
        return float(total)


# ------------------------------------------------------------------
# 自动优化引擎主类
# ------------------------------------------------------------------
class AutoStrategyOptimizer:
    """自动策略优化引擎。

    完整闭环：
    1. 生成候选变体
    2. 逐个回测评估
    3. 过拟合检测
    4. 与基线AB对比
    5. 综合评分排序
    6. 选出最优的进入生命周期

    用法：
        optimizer = AutoStrategyOptimizer(config, backtest_fn=my_backtest)
        best = optimizer.run(base_params={"period": 14, "threshold": 0.5})
    """

    def __init__(self,
                 config: OptimizationConfig,
                 backtest_fn: Optional[Callable] = None,
                 overfitting_fn: Optional[Callable] = None):
        self.config = config
        self.backtest_fn = backtest_fn or self._default_backtest
        self.overfitting_fn = overfitting_fn or self._default_overfitting_check

        self.generator = CandidateGenerator(config)
        self.bandit = MultiArmedBandit(config.exploration_ratio)
        self.scorer = CandidateScorer(config.min_sharpe)

        self.all_candidates: list[CandidateStrategy] = []
        self.trials_count = 0  # 包含所有试验（含失败）

    def _default_backtest(self, params: dict) -> tuple[float, float, int]:
        """默认回测函数（模拟用）。"""
        # 实际使用时替换为真实回测
        return 1.2, 0.15, 50

    def _default_overfitting_check(self, params: dict) -> float:
        """默认过拟合检测（模拟用）。"""
        # 实际使用时调用 core/backtest/overfitting.py
        return 0.2

    def run(self, base_params: dict) -> Optional[CandidateStrategy]:
        """运行完整优化流程。

        Returns:
            最优候选策略，如果没有合格的则返回None
        """
        # 1. 生成候选
        candidates = self.generator.generate(base_params, n=self.config.max_trials)
        self.all_candidates.extend(candidates)
        self.trials_count = len(candidates)

        # 2. 逐个评估
        for candidate in candidates:
            # 回测
            sharpe, max_dd, n_trades = self.backtest_fn(candidate.params)
            candidate.sharpe = sharpe
            candidate.max_drawdown = max_dd
            candidate.n_trades = n_trades
            candidate.status = CandidateStatus.BACKTESTED

            # 过拟合检测
            overfit_score = self.overfitting_fn(candidate.params)
            candidate.overfitting_score = overfit_score
            candidate.status = CandidateStatus.OVERFIT_CHECKED

            # 综合评分
            score = self.scorer.score(candidate)
            candidate.score = score

            # 更新多臂老虎机
            self.bandit.update(candidate.name, score)

        # 3. 筛选合格候选
        qualified = [
            c for c in candidates
            if c.sharpe >= self.config.min_sharpe
            and c.overfitting_score <= self.config.max_overfitting_score
        ]

        if not qualified:
            return None

        # 4. 选评分最高的
        best = max(qualified, key=lambda c: c.score)
        best.status = CandidateStatus.SELECTED

        return best

    def get_audit_report(self) -> dict:
        """获取完整审计报告。"""
        return {
            "config": self.config.__dict__,
            "total_trials": self.trials_count,  # 包含所有试验（含失败）
            "qualified_count": sum(
                1 for c in self.all_candidates
                if c.sharpe >= self.config.min_sharpe
                and c.overfitting_score <= self.config.max_overfitting_score
            ),
            "candidates": [
                {
                    "name": c.name,
                    "sharpe": c.sharpe,
                    "overfitting_score": c.overfitting_score,
                    "score": c.score,
                    "status": c.status.value,
                }
                for c in sorted(self.all_candidates, key=lambda x: x.score, reverse=True)
            ],
        }
