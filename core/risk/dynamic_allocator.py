# -*- coding: utf-8 -*-
"""core/risk/dynamic_allocator.py —— PM动态资金分配器。

基于第一性原理和Millennium实践：
    每个策略（PM）独立计算夏普比率、回撤、胜率。
    表现好的多给资金，表现差的少给或暂停。
    类似多臂老虎机：探索新策略 + 利用已验证策略。

核心逻辑：
    1. 每个策略计算综合得分（夏普40% + 回撤30% + 胜率20% + 稳定性10%）
    2. 根据得分动态分配资金权重
    3. 表现跌破阈值自动减仓，跌破红线自动暂停
    4. 新策略有探索期（小仓位验证）
"""
from __future__ import annotations

import logging
from typing import Optional, Dict, List
from dataclasses import dataclass, field
import numpy as np

logger = logging.getLogger("core.risk.allocator")


@dataclass
class StrategyPerformance:
    """单个策略的绩效指标。"""
    strategy_id: str
    name: str
    sharpe: float = 0.0           # 夏普比率
    max_drawdown: float = 0.0     # 最大回撤（绝对值，如0.15=15%）
    win_rate: float = 0.0          # 胜率（0-1）
    profit_factor: float = 1.0    # 盈利因子
    total_trades: int = 0          # 总交易数
    consecutive_losses: int = 0    # 连续亏损次数
    avg_r_multiple: float = 0.0    # 平均R倍数
    days_running: int = 0          # 运行天数


@dataclass
class AllocationResult:
    """资金分配结果。"""
    strategy_id: str
    score: float                   # 综合得分（0-100）
    weight: float                  # 资金权重（0-1）
    status: str                    # active / watch / suspended
    reason: str = ""               # 状态原因


class DynamicAllocator:
    """PM动态资金分配器。

    用法：
        allocator = DynamicAllocator()

        # 每个策略运行后更新绩效
        allocator.update_performance(strategy_perf)

        # 定期计算资金分配
        allocations = allocator.calculate_allocations(total_capital=1000000)
    """

    def __init__(self,
                 min_trades_for_score: int = 10,
                 explore_period_days: int = 30,
                 base_explore_weight: float = 0.05):
        """
        Args:
            min_trades_for_score: 计算综合得分所需的最少交易数
            explore_period_days: 新策略探索期天数
            base_explore_weight: 探索期基础权重
        """
        self.min_trades_for_score = min_trades_for_score
        self.explore_period_days = explore_period_days
        self.base_explore_weight = base_explore_weight
        self.performances: Dict[str, StrategyPerformance] = {}

    def update_performance(self, perf: StrategyPerformance) -> None:
        """更新策略绩效。"""
        self.performances[perf.strategy_id] = perf

    def calculate_allocations(self, total_capital: float) -> List[AllocationResult]:
        """计算所有策略的资金分配。

        Args:
            total_capital: 总资金

        Returns:
            各策略的资金分配结果列表
        """
        results = []
        raw_scores = {}

        for sid, perf in self.performances.items():
            score = self._calculate_composite_score(perf)
            raw_scores[sid] = score

            # 判断状态
            status, reason = self._determine_status(perf, score)
            results.append(AllocationResult(
                strategy_id=sid,
                score=score,
                weight=0.0,  # 后面归一化
                status=status,
                reason=reason,
            ))

        # 归一化权重（只给active的策略分配资金）
        active_total_score = sum(r.score for r in results if r.status == "active")

        if active_total_score > 0:
            for r in results:
                if r.status == "active":
                    r.weight = r.score / active_total_score
                elif r.status == "watch":
                    r.weight = self.base_explore_weight * 0.5  # 观察期半仓
                else:  # suspended
                    r.weight = 0.0

        # 调整：探索期新策略单独给基础权重
        for sid, perf in self.performances.items():
            if perf.days_running < self.explore_period_days and perf.total_trades < self.min_trades_for_score:
                # 新策略探索期
                for r in results:
                    if r.strategy_id == sid:
                        r.weight = self.base_explore_weight
                        r.status = "explore"
                        r.reason = f"新策略探索期（{perf.days_running}天）"

        return results

    def _calculate_composite_score(self, perf: StrategyPerformance) -> float:
        """计算综合得分（0-100）。

        权重分配：
            夏普比率 40%
            回撤控制 30%（回撤越小得分越高）
            胜率 20%
            稳定性 10%（连续亏损次数越少得分越高）
        """
        if perf.total_trades < self.min_trades_for_score:
            return 30.0  # 交易数不够，给基础分

        # 1. 夏普得分（满分40）：0以下0分，2以上满分
        sharpe_score = max(0, min(40, perf.sharpe * 20))

        # 2. 回撤得分（满分30）：0回撤满分，20%回撤0分
        dd_score = max(0, 30 * (1 - perf.max_drawdown / 0.20))

        # 3. 胜率得分（满分20）：40%胜率0分，70%以上满分
        win_score = max(0, min(20, (perf.win_rate - 0.40) / 0.30 * 20))

        # 4. 稳定性得分（满分10）：连续亏损0次满分，5次以上0分
        stability_score = max(0, 10 * (1 - perf.consecutive_losses / 5.0))

        total = sharpe_score + dd_score + win_score + stability_score
        return round(total, 1)

    def _determine_status(self, perf: StrategyPerformance, score: float) -> tuple:
        """判断策略状态。

        Returns:
            (status, reason)
            status: active / watch / suspended
        """
        # 红线：夏普<0或回撤>25%或连续亏损>8次 → 暂停
        if perf.sharpe < 0 or perf.max_drawdown > 0.25 or perf.consecutive_losses > 8:
            return "suspended", "触发暂停红线"

        # 黄线：夏普<0.5或回撤>15% → 观察
        if perf.sharpe < 0.5 or perf.max_drawdown > 0.15:
            return "watch", "进入观察期"

        # 交易数太少 → 探索/观察
        if perf.total_trades < self.min_trades_for_score:
            return "watch", "交易样本不足"

        # 正常运行
        return "active", "正常运行"

    def get_capital_for_strategy(self, strategy_id: str, total_capital: float) -> float:
        """获取某个策略的分配资金。"""
        allocations = self.calculate_allocations(total_capital)
        for a in allocations:
            if a.strategy_id == strategy_id:
                return total_capital * a.weight
        return 0.0


# ------------------------------------------------------------------
# 单例模式
# ------------------------------------------------------------------
_dynamic_allocator_instance: Optional[DynamicAllocator] = None


def get_dynamic_allocator() -> DynamicAllocator:
    """获取全局动态分配器单例。"""
    global _dynamic_allocator_instance
    if _dynamic_allocator_instance is None:
        _dynamic_allocator_instance = DynamicAllocator()
    return _dynamic_allocator_instance
