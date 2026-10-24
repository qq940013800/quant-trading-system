# -*- coding: utf-8 -*-
"""core.backtest.integration —— 压力测试与回测引擎深度集成。

第一性原理：
- 压力测试不能是独立工具，必须是回测流程的一部分
- 回测完一个策略，自动告诉你它在极端行情下会亏多少
- 这样你不需要单独跑压力测试，回测报告里直接包含极端风险评估

核心能力：
1. 回测后自动压力测试
2. 极端情景风险评分
3. 回测报告自动补充压力测试结果
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .stress_test import StressTester, PRESET_SCENARIOS, StressTestResult


@dataclass
class IntegratedReport:
    """集成报告：回测结果 + 压力测试结果。

    Attributes:
        backtest_metrics: 回测指标（Sharpe、最大回撤等）
        stress_results: 压力测试结果列表
        risk_score: 综合风险评分（0-100，越高越安全）
        risk_level: 风险等级（low/medium/high/critical）
        worst_case_loss: 最差情景下的损失
    """
    backtest_metrics: dict
    stress_results: list[StressTestResult]
    risk_score: float
    risk_level: str
    worst_case_loss: float


class BacktestStressIntegration:
    """回测与压力测试的集成器。

    使用方法：
        integration = BacktestStressIntegration()
        report = integration.analyze(backtest_metrics, current_exposure=0.02)
    """

    def __init__(self, initial_equity: float = 100000.0):
        self.initial_equity = initial_equity
        self.tester = StressTester(initial_equity=initial_equity)

    def analyze(self, backtest_metrics: dict,
                current_exposure: float = 0.02) -> IntegratedReport:
        """分析回测结果，自动运行压力测试。

        Args:
            backtest_metrics: 回测引擎输出的指标字典
            current_exposure: 当前策略的总风险敞口

        Returns:
            集成报告
        """
        # 1. 运行所有预设压力情景
        stress_results = self.tester.run_all_presets(current_exposure)

        # 2. 找出最差情景
        worst = max(stress_results, key=lambda r: r.total_loss)

        # 3. 计算综合风险评分
        risk_score = self._calc_risk_score(backtest_metrics, stress_results)

        # 4. 判断风险等级
        risk_level = self._risk_level(risk_score)

        return IntegratedReport(
            backtest_metrics=backtest_metrics,
            stress_results=stress_results,
            risk_score=risk_score,
            risk_level=risk_level,
            worst_case_loss=worst.total_loss,
        )

    def _calc_risk_score(self, backtest_metrics: dict,
                         stress_results: list[StressTestResult]) -> float:
        """计算综合风险评分（0-100，越高越安全）。

        评分维度：
        - 回测最大回撤（占40%）：回撤越小越好
        - 压力测试存活率（占40%）：压力测试中存活的比例
        - 最差情景损失（占20%）：最差情景的损失越小越好
        """
        score = 100.0

        # 1. 回测最大回撤扣分（最多扣40分）
        max_dd = backtest_metrics.get("max_drawdown", 0.15)
        dd_penalty = min(40, max_dd * 200)  # 10%回撤扣20分
        score -= dd_penalty

        # 2. 压力测试存活率扣分（最多扣40分）
        survived_count = sum(1 for r in stress_results if r.survived)
        survival_rate = survived_count / len(stress_results)
        survival_penalty = (1 - survival_rate) * 40
        score -= survival_penalty

        # 3. 最差情景损失扣分（最多扣20分）
        worst_loss = max(r.total_loss for r in stress_results)
        loss_penalty = min(20, worst_loss * 100)  # 20%损失扣20分
        score -= loss_penalty

        return float(max(0, min(100, score)))

    def _risk_level(self, risk_score: float) -> str:
        """根据风险评分判断风险等级。"""
        if risk_score >= 80:
            return "low"
        elif risk_score >= 60:
            return "medium"
        elif risk_score >= 40:
            return "high"
        else:
            return "critical"

    def quick_analyze(self, sharpe: float = 1.0,
                      max_drawdown: float = 0.15,
                      current_exposure: float = 0.02) -> dict:
        """快速分析：只输入关键指标，不需要完整回测结果。"""
        fake_metrics = {
            "sharpe": sharpe,
            "max_drawdown": max_drawdown,
        }
        report = self.analyze(fake_metrics, current_exposure)

        return {
            "risk_score": report.risk_score,
            "risk_level": report.risk_level,
            "worst_case_loss": report.worst_case_loss,
            "scenarios_tested": len(report.stress_results),
            "survival_rate": sum(1 for r in report.stress_results if r.survived) / len(report.stress_results),
        }
