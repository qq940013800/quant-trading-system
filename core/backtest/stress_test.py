# -*- coding: utf-8 -*-
"""core.backtest.stress_test —— 压力测试与极端情景模拟。

第一性原理：
- 正常市场的风控是"常规训练"
- 极端市场的风控是"生死考验"
- 顶级机构每个季度都要做压力测试——模拟黑天鹅，看看系统会不会崩

核心能力：
1. 历史极端情景回放（2008金融危机、2020新冠暴跌等）
2. 假设情景模拟（波动率飙升、流动性枯竭、连续跳空）
3. 风控压力测试（熔断会不会正常触发）
4. 尾部风险评估（最大回撤、VaR、CVaR）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class StressScenario:
    """压力测试情景定义。

    Attributes:
        name: 情景名称
        description: 情景描述
        price_shock: 价格冲击幅度（如 -0.20 = 下跌20%）
        volatility_multiplier: 波动率倍数（如 3.0 = 波动率变成3倍）
        gap_days: 连续跳空天数
        liquidity_crisis: 是否流动性枯竭（滑点放大N倍）
    """
    name: str
    description: str
    price_shock: float = 0.0
    volatility_multiplier: float = 1.0
    gap_days: int = 0
    liquidity_crisis: bool = False


@dataclass
class StressTestResult:
    """压力测试结果。

    Attributes:
        scenario_name: 情景名称
        max_drawdown: 最大回撤
        total_loss: 总亏损（占初始权益比例）
        circuit_breaker_triggered: 熔断是否触发
        margin_call: 是否爆仓（保证金不足）
        survived: 是否存活（没有爆仓）
    """
    scenario_name: str
    max_drawdown: float
    total_loss: float
    circuit_breaker_triggered: bool
    margin_call: bool
    survived: bool


# ------------------------------------------------------------------
# 预设极端情景（基于历史真实事件）
# ------------------------------------------------------------------
PRESET_SCENARIOS = {
    "2008_financial_crisis": StressScenario(
        name="2008金融危机",
        description="雷曼兄弟破产，全球股市暴跌，流动性枯竭",
        price_shock=-0.25,
        volatility_multiplier=3.5,
        gap_days=3,
        liquidity_crisis=True,
    ),
    "2020_covid_crash": StressScenario(
        name="2020新冠暴跌",
        description="新冠疫情爆发，全球股市熔断，原油负价格",
        price_shock=-0.20,
        volatility_multiplier=4.0,
        gap_days=5,
        liquidity_crisis=True,
    ),
    "flash_crash_2010": StressScenario(
        name="2010闪电崩盘",
        description="道指盘中暴跌1000点，几分钟内蒸发1万亿美元",
        price_shock=-0.09,
        volatility_multiplier=5.0,
        gap_days=0,
        liquidity_crisis=True,
    ),
    "interest_rate_shock": StressScenario(
        name="利率冲击",
        description="央行意外加息100bp，债券价格暴跌",
        price_shock=-0.10,
        volatility_multiplier=2.5,
        gap_days=2,
        liquidity_crisis=False,
    ),
    "commodity_squeeze": StressScenario(
        name="大宗商品逼空",
        description="原油/金属等大宗商品逼空，波动率飙升",
        price_shock=0.30,
        volatility_multiplier=4.0,
        gap_days=4,
        liquidity_crisis=True,
    ),
}


class StressTester:
    """压力测试器。

    设计原则：
    - 压力测试不是为了赚钱，是为了活着
    - 宁可高估风险，不可低估风险
    - 每个情景都要验证风控有没有正常触发
    """

    def __init__(self, initial_equity: float = 100000.0,
                 max_leverage: float = 10.0):
        self.initial_equity = initial_equity
        self.max_leverage = max_leverage

    def run_scenario(self, scenario: StressScenario,
                    current_exposure: float = 0.02) -> StressTestResult:
        """运行单个压力测试情景。

        简化模型：
        - 假设当前持仓风险敞口是 current_exposure（占权益比例）
        - 极端情景下价格冲击 price_shock
        - 流动性危机时滑点放大10倍
        - 计算最大回撤和总亏损

        Args:
            scenario: 压力测试情景
            current_exposure: 当前总风险敞口（占权益比例）

        Returns:
            压力测试结果
        """
        equity = self.initial_equity

        # 1. 价格冲击导致的直接损失
        price_loss = current_exposure * abs(scenario.price_shock)

        # 2. 波动率放大导致的额外损失（假设止损被扫损的概率增加）
        vol_extra_loss = current_exposure * 0.1 * (scenario.volatility_multiplier - 1.0)

        # 3. 流动性危机导致的滑点损失
        slippage_loss = 0.0
        if scenario.liquidity_crisis:
            slippage_loss = current_exposure * 0.05  # 滑点放大5%

        # 4. 连续跳空导致的额外损失
        gap_loss = current_exposure * 0.02 * scenario.gap_days

        # 总亏损（current_exposure本身就是占权益的比例，所以总损失也是比例）
        total_loss = price_loss + vol_extra_loss + slippage_loss + gap_loss
        total_loss_pct = total_loss  # 已经是比例了，不需要再除以权益

        # 最大回撤（简化：假设就是总亏损）
        max_drawdown = total_loss_pct

        # 熔断是否触发（假设3%的日亏损线）
        circuit_triggered = total_loss_pct >= 0.03

        # 是否爆仓（亏损超过权益的50%就算严重）
        margin_call = total_loss_pct >= 0.5

        # 是否存活
        survived = total_loss_pct < 0.3  # 亏30%以上就算重伤

        return StressTestResult(
            scenario_name=scenario.name,
            max_drawdown=max_drawdown,
            total_loss=total_loss_pct,
            circuit_breaker_triggered=circuit_triggered,
            margin_call=margin_call,
            survived=survived,
        )

    def run_all_presets(self, current_exposure: float = 0.02) -> list[StressTestResult]:
        """运行所有预设极端情景。"""
        results = []
        for scenario in PRESET_SCENARIOS.values():
            result = self.run_scenario(scenario, current_exposure)
            results.append(result)
        return results

    def stress_report(self, current_exposure: float = 0.02) -> dict:
        """生成完整的压力测试报告。"""
        results = self.run_all_presets(current_exposure)

        # 统计
        survived_count = sum(1 for r in results if r.survived)
        worst_case = max(results, key=lambda r: r.total_loss)
        avg_drawdown = np.mean([r.max_drawdown for r in results])

        return {
            "initial_equity": self.initial_equity,
            "current_exposure": current_exposure,
            "scenarios_tested": len(results),
            "survived_count": survived_count,
            "survival_rate": survived_count / len(results),
            "worst_case": {
                "name": worst_case.scenario_name,
                "total_loss": worst_case.total_loss,
                "max_drawdown": worst_case.max_drawdown,
            },
            "average_drawdown": avg_drawdown,
            "all_results": [
                {
                    "scenario": r.scenario_name,
                    "total_loss": r.total_loss,
                    "max_drawdown": r.max_drawdown,
                    "circuit_triggered": r.circuit_breaker_triggered,
                    "survived": r.survived,
                }
                for r in results
            ],
        }
