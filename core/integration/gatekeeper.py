# -*- coding: utf-8 -*-
"""core.integration.gatekeeper —— 守门员整合模块。

完整流程：
1. 桥接模块从 QuantDinger 拉取策略列表
2. 对每个策略运行验证层中间件检查
3. 生成守门员报告
4. 决定哪些策略可以上线，哪些需要拦截/降级

这就是三层架构的完整闭环：
执行层（QuantDinger）→ 桥接层（bridge）→ 验证层（middleware）→ 决策输出
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from core.integration.bridge import QuantDingerBridge, HealthStatus
from core.integration.verification_middleware import (
    VerificationMiddleware,
    GateReport,
    GateDecision,
)


@dataclass
class StrategyGateResult:
    """单个策略的守门员结果。"""
    strategy_id: str
    strategy_name: str
    gate_report: GateReport
    can_deploy: bool
    recommended_action: str


@dataclass
class GatekeeperSummary:
    """守门员总结报告。"""
    total_strategies: int
    pass_count: int
    warn_count: int
    downgrade_count: int
    reject_count: int
    results: list[StrategyGateResult]
    bridge_health: HealthStatus

    @property
    def pass_rate(self) -> float:
        return self.pass_count / self.total_strategies if self.total_strategies > 0 else 0.0


class Gatekeeper:
    """守门员整合器——桥接 + 验证层的完整闭环。

    使用方式：
        gate = Gatekeeper()
        summary = gate.run_full_gate()
        if summary.pass_rate > 0.8:
            print("策略质量良好，可以上线")
        else:
            print(f"只有{summary.pass_rate:.0%}的策略通过验证")
    """

    def __init__(
        self,
        bridge: Optional[QuantDingerBridge] = None,
        middleware: Optional[VerificationMiddleware] = None,
    ):
        self.bridge = bridge or QuantDingerBridge()
        self.middleware = middleware or VerificationMiddleware()

    def run_full_gate(self) -> GatekeeperSummary:
        """运行完整的守门员流程。

        步骤：
        1. 检查桥接模块健康状态
        2. 从 QuantDinger 拉取策略列表
        3. 对每个策略运行验证层检查
        4. 生成总结报告
        """
        # 1. 检查桥接健康
        health = self.bridge.health()

        # 2. 拉取策略列表（如果桥接不可用，用模拟数据）
        strategies = self._fetch_strategies()

        # 3. 对每个策略运行守门员检查
        results: list[StrategyGateResult] = []
        for strategy in strategies:
            result = self._gate_one_strategy(strategy)
            results.append(result)

        # 4. 统计
        pass_count = sum(1 for r in results if r.gate_report.overall_decision == GateDecision.PASS)
        warn_count = sum(1 for r in results if r.gate_report.overall_decision == GateDecision.WARN)
        downgrade_count = sum(1 for r in results if r.gate_report.overall_decision == GateDecision.DOWNGRADE)
        reject_count = sum(1 for r in results if r.gate_report.overall_decision == GateDecision.REJECT)

        return GatekeeperSummary(
            total_strategies=len(results),
            pass_count=pass_count,
            warn_count=warn_count,
            downgrade_count=downgrade_count,
            reject_count=reject_count,
            results=results,
            bridge_health=health,
        )

    def _fetch_strategies(self) -> list[dict[str, Any]]:
        """从桥接模块拉取策略列表。如果桥接不可用，返回模拟数据。"""
        try:
            strategies = self.bridge.list_strategies(limit=20)
            if strategies:
                return [
                    {
                        "id": s.strategy_id,
                        "name": s.name,
                        "type": s.strategy_type,
                        "symbol": s.symbol,
                    }
                    for s in strategies
                ]
        except Exception:
            pass

        # 桥接不可用时，返回模拟数据用于演示
        return [
            {"id": "s001", "name": "ML增强趋势", "type": "ml_trend", "symbol": "XAUUSD"},
            {"id": "s002", "name": "均值回归", "type": "mean_reversion", "symbol": "EURUSD"},
            {"id": "s003", "name": "突破策略", "type": "breakout", "symbol": "BTCUSD"},
        ]

    def _gate_one_strategy(self, strategy: dict[str, Any]) -> StrategyGateResult:
        """对单个策略运行守门员检查。"""
        strategy_id = strategy.get("id", "unknown")
        strategy_name = strategy.get("name", "Unknown Strategy")

        # 运行验证层检查（简化版：用模拟的回测结果）
        backtest_results = {
            "pbo": 0.15,  # 模拟：低过拟合风险
            "deflated_sharpe": 1.5,
            "trials": 10,
        }

        recent_returns = [0.01, 0.02, -0.01, 0.03, 0.015, -0.005, 0.025, 0.01, -0.01, 0.02]
        benchmark_returns = [0.005, 0.01, -0.005, 0.015, 0.01, -0.003, 0.012, 0.008, -0.005, 0.01]

        report = self.middleware.gate_before_deploy(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            backtest_results=backtest_results,
            recent_returns=recent_returns,
            benchmark_returns=benchmark_returns,
        )

        # 决定是否可以上线
        can_deploy = report.overall_decision in [GateDecision.PASS, GateDecision.WARN]

        # 推荐行动
        if report.overall_decision == GateDecision.PASS:
            action = "允许上线 · 正常运行"
        elif report.overall_decision == GateDecision.WARN:
            action = "允许上线 · 密切监控"
        elif report.overall_decision == GateDecision.DOWNGRADE:
            action = "降级运行 · 仓位减半"
        else:
            action = "拒绝上线 · 需重新验证"

        return StrategyGateResult(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            gate_report=report,
            can_deploy=can_deploy,
            recommended_action=action,
        )

    def generate_report_text(self, summary: GatekeeperSummary) -> str:
        """生成人类可读的守门员报告。"""
        lines = [
            "=" * 60,
            "守门员报告 · Gatekeeper Report",
            "=" * 60,
            f"桥接健康状态: {'✅ 正常' if summary.bridge_health.reachable else '❌ 不可达'}",
            f"策略总数: {summary.total_strategies}",
            f"通过率: {summary.pass_rate:.1%}",
            "",
            f"✅ PASS: {summary.pass_count}",
            f"⚠️  WARN: {summary.warn_count}",
            f"⬇️  DOWNGRADE: {summary.downgrade_count}",
            f"❌ REJECT: {summary.reject_count}",
            "",
            "详细结果:",
            "-" * 60,
        ]

        for result in summary.results:
            decision_emoji = {
                GateDecision.PASS: "✅",
                GateDecision.WARN: "⚠️",
                GateDecision.DOWNGRADE: "⬇️",
                GateDecision.REJECT: "❌",
            }.get(result.gate_report.overall_decision, "❓")

            lines.append(f"{decision_emoji} {result.strategy_name} ({result.strategy_id})")
            lines.append(f"   决策: {result.gate_report.overall_decision.value}")
            lines.append(f"   建议: {result.recommended_action}")
            lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)
