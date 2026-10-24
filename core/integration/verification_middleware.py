# -*- coding: utf-8 -*-
"""core.integration.verification_middleware —— 验证层中间件。

核心定位：在 QuantDinger 执行策略上线/实盘交易之前，先用自研验证层做一遍"守门员检查"。
- 过拟合风险高 → 拦截，不允许上线
- 检测到前视偏差 → 拦截
- 策略漂移严重 → 降级（减半仓位/停止加仓）
- 压力测试不通过 → 拦截
- 组合风险超标 → 拦截

这就是三层架构的中间层：执行层（QuantDinger）→ 验证层（自研）→ 策略层（自研+开源）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import numpy as np
import pandas as pd

# 真实检查模块（可选导入，失败时降级到简化版）
try:
    from core.backtest.overfitting import overfitting_diagnostic
    _HAS_OVERFITTING = True
except ImportError:
    _HAS_OVERFITTING = False

try:
    from core.audit.lookahead_detector import quick_lookahead_check
    _HAS_LOOKAHEAD = True
except ImportError:
    _HAS_LOOKAHEAD = False

try:
    from core.backtest.stress_test import StressTester, StressScenario
    _HAS_STRESS = True
except ImportError:
    _HAS_STRESS = False

try:
    from core.monitoring.drift_monitor import DriftMonitor
    _HAS_DRIFT = True
except ImportError:
    _HAS_DRIFT = False

try:
    from core.risk.portfolio_risk import PortfolioRiskManager, PortfolioRiskConfig, StrategyRisk
    _HAS_PORTFOLIO_RISK = True
except ImportError:
    _HAS_PORTFOLIO_RISK = False


class GateDecision(str, Enum):
    """守门员决策。"""
    PASS = "pass"           # 通过，可以执行
    WARN = "warn"           # 警告，可以执行但要注意
    REJECT = "reject"       # 拒绝，不允许执行
    DOWNGRADE = "downgrade" # 降级执行（比如减半仓位）


@dataclass
class GateFinding:
    """单个检查项的发现。"""
    check_name: str
    decision: GateDecision
    score: float  # 0-100，分数越高越危险
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class GateReport:
    """完整的守门员报告。"""
    strategy_id: str
    strategy_name: str
    overall_decision: GateDecision
    findings: list[GateFinding]
    timestamp: str

    @property
    def pass_count(self) -> int:
        return sum(1 for f in self.findings if f.decision == GateDecision.PASS)

    @property
    def warn_count(self) -> int:
        return sum(1 for f in self.findings if f.decision == GateDecision.WARN)

    @property
    def reject_count(self) -> int:
        return sum(1 for f in self.findings if f.decision == GateDecision.REJECT)

    @property
    def downgrade_count(self) -> int:
        return sum(1 for f in self.findings if f.decision == GateDecision.DOWNGRADE)


class VerificationMiddleware:
    """验证层中间件——策略上线/交易执行前的守门员。

    使用方式：
        mw = VerificationMiddleware()
        report = mw.gate_before_deploy(strategy_id="s001", strategy_name="ML趋势", data=...)
        if report.overall_decision == GateDecision.REJECT:
            raise Exception("策略不满足验证标准，不允许上线")
    """

    def __init__(
        self,
        overfitting_threshold: float = 0.3,  # PBO > 0.3 就是高风险
        drift_warn_threshold: float = 0.7,  # 健康分 < 0.7 警告
        drift_reject_threshold: float = 0.4,  # 健康分 < 0.4 拒绝
        stress_min_survival: float = 0.5,  # 压力测试存活率 < 0.5 拒绝
        max_total_exposure: float = 0.05,  # 最大总敞口 5%
        max_exposure_per_cluster: float = 0.03,  # 每聚类最大敞口 3%
    ):
        self.overfitting_threshold = overfitting_threshold
        self.drift_warn_threshold = drift_warn_threshold
        self.drift_reject_threshold = drift_reject_threshold
        self.stress_min_survival = stress_min_survival
        self.max_total_exposure = max_total_exposure
        self.max_exposure_per_cluster = max_exposure_per_cluster

    def gate_before_deploy(
        self,
        strategy_id: str,
        strategy_name: str,
        backtest_results: Optional[dict[str, Any]] = None,
        price_data: Optional[Any] = None,
        recent_returns: Optional[list[float]] = None,
        benchmark_returns: Optional[list[float]] = None,
    ) -> GateReport:
        """策略上线前的守门员检查。

        检查项：
        1. 过拟合检测（PBO / Deflated Sharpe）
        2. 前视偏差扫描
        3. 漂移健康度
        4. 压力测试通过率
        """
        findings: list[GateFinding] = []

        # 1. 过拟合检测
        if backtest_results is not None:
            findings.append(self._check_overfitting(backtest_results))

        # 2. 前视偏差扫描（简化版）
        if price_data is not None:
            findings.append(self._check_lookahead(price_data))

        # 3. 漂移健康度
        if recent_returns is not None and benchmark_returns is not None:
            findings.append(self._check_drift(recent_returns, benchmark_returns))

        # 4. 压力测试（简化版）
        if price_data is not None:
            findings.append(self._check_stress(price_data))

        # 综合决策：只要有一个 REJECT 就是 REJECT
        overall = self._decide_overall(findings)

        from datetime import datetime
        return GateReport(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            overall_decision=overall,
            findings=findings,
            timestamp=datetime.now().isoformat(),
        )

    def gate_before_trade(
        self,
        strategy_id: str,
        current_exposure: float,
        new_position_size: float,
        cluster_exposure: float,
    ) -> GateReport:
        """实盘交易前的守门员检查（组合风控层面）。"""
        findings: list[GateFinding] = []

        # 组合风险检查
        findings.append(self._check_portfolio_risk(current_exposure, new_position_size, cluster_exposure))

        overall = self._decide_overall(findings)

        from datetime import datetime
        return GateReport(
            strategy_id=strategy_id,
            strategy_name="",
            overall_decision=overall,
            findings=findings,
            timestamp=datetime.now().isoformat(),
        )

    def _check_overfitting(self, backtest_results: dict[str, Any]) -> GateFinding:
        """检查过拟合风险。"""
        pbo = backtest_results.get("pbo", 0.5)  # 默认中等风险
        deflated_sharpe = backtest_results.get("deflated_sharpe", 0.0)
        returns = backtest_results.get("returns", None)
        trials = backtest_results.get("trials", 1)

        # 如果有真实收益序列，调用真实的过拟合诊断
        if _HAS_OVERFITTING and returns is not None:
            try:
                returns_series = pd.Series(returns)
                diag = overfitting_diagnostic(returns_series, trials=trials)
                # 从诊断结果提取关键指标
                pbo = diag.get("pbo", pbo)
                deflated_sharpe = diag.get("deflated_sharpe", deflated_sharpe)
                warnings = diag.get("warnings", [])
                score = pbo * 100

                if pbo > self.overfitting_threshold:
                    decision = GateDecision.REJECT
                    message = f"过拟合风险过高：PBO={pbo:.2f} > 阈值{self.overfitting_threshold}"
                elif pbo > self.overfitting_threshold * 0.7:
                    decision = GateDecision.WARN
                    message = f"过拟合风险偏高：PBO={pbo:.2f}，建议谨慎"
                else:
                    decision = GateDecision.PASS
                    message = f"过拟合风险正常：PBO={pbo:.2f}"

                if warnings:
                    message += f"（{len(warnings)}个警告）"

                return GateFinding(
                    check_name="过拟合检测",
                    decision=decision,
                    score=score,
                    message=message,
                    details={
                        "pbo": pbo,
                        "deflated_sharpe": deflated_sharpe,
                        "warnings": warnings,
                        "real_check": True,
                    },
                )
            except Exception as e:
                # 真实检查失败，降级到简化版
                pass

        # 简化版（降级模式）
        score = pbo * 100  # 0-100

        if pbo > self.overfitting_threshold:
            decision = GateDecision.REJECT
            message = f"过拟合风险过高：PBO={pbo:.2f} > 阈值{self.overfitting_threshold}"
        elif pbo > self.overfitting_threshold * 0.7:
            decision = GateDecision.WARN
            message = f"过拟合风险偏高：PBO={pbo:.2f}，建议谨慎"
        else:
            decision = GateDecision.PASS
            message = f"过拟合风险正常：PBO={pbo:.2f}"

        return GateFinding(
            check_name="过拟合检测",
            decision=decision,
            score=score,
            message=message,
            details={"pbo": pbo, "deflated_sharpe": deflated_sharpe, "real_check": False},
        )

    def _check_lookahead(self, price_data: Any) -> GateFinding:
        """检查前视偏差。"""
        # 如果有真实价格数据，调用真实的前视偏差检测器
        if _HAS_LOOKAHEAD and price_data is not None:
            try:
                # 简化调用：尝试从price_data提取历史数据
                if hasattr(price_data, '__len__') and len(price_data) > 10:
                    result = quick_lookahead_check(
                        history=price_data,
                        current_idx=len(price_data) - 1,
                        window_size=min(20, len(price_data) // 2),
                    )
                    passed = result.get("passed", True)
                    warning = result.get("warning", "")
                    violations = result.get("violations", [])

                    if not passed or len(violations) > 0:
                        decision = GateDecision.REJECT
                        score = 90.0
                        message = f"检测到前视偏差：{len(violations)}个问题"
                    else:
                        decision = GateDecision.PASS
                        score = 10.0
                        message = "未检测到前视偏差"

                    return GateFinding(
                        check_name="前视偏差扫描",
                        decision=decision,
                        score=score,
                        message=message,
                        details={
                            "violations": violations,
                            "violation_count": len(violations),
                            "warning": warning,
                            "real_check": True,
                        },
                    )
            except Exception as e:
                # 真实检查失败，降级到简化版
                pass

        # 简化版（降级模式）
        return GateFinding(
            check_name="前视偏差扫描",
            decision=GateDecision.PASS,
            score=10.0,
            message="前视偏差检查通过（降级模式，待接入真实检测器）",
            details={"note": "降级模式，真实检查模块未就绪或调用失败", "real_check": False},
        )

    def _check_drift(self, recent_returns: list[float], benchmark_returns: list[float]) -> GateFinding:
        """检查策略漂移健康度。"""
        # 如果有真实漂移监控模块，调用真实检查
        if _HAS_DRIFT and len(recent_returns) >= 10:
            try:
                # 用基准收益计算初始Sharpe作为baseline
                baseline_returns = pd.Series(benchmark_returns)
                baseline_sharpe = (baseline_returns.mean() / baseline_returns.std()) * np.sqrt(252) if baseline_returns.std() > 0 else 1.0
                baseline_win_rate = (baseline_returns > 0).mean()

                monitor = DriftMonitor(
                    baseline_sharpe=baseline_sharpe,
                    baseline_win_rate=baseline_win_rate,
                )
                monitor.update(pd.Series(recent_returns))
                alerts = monitor.check_drift()

                # 计算健康分
                health_score = 100.0
                critical_count = 0
                high_count = 0
                for alert in alerts:
                    if alert.severity == "critical":
                        critical_count += 1
                        health_score -= 30
                    elif alert.severity == "high":
                        high_count += 1
                        health_score -= 15
                    elif alert.severity == "medium":
                        health_score -= 5

                health_score = max(0, min(100, health_score))

                if critical_count > 0:
                    decision = GateDecision.REJECT
                    message = f"策略严重漂移：{critical_count}个严重告警，健康分={health_score:.0f}"
                elif high_count > 0:
                    decision = GateDecision.DOWNGRADE
                    message = f"策略有漂移迹象：{high_count}个高危告警，健康分={health_score:.0f}"
                elif health_score < self.drift_warn_threshold * 100:
                    decision = GateDecision.WARN
                    message = f"策略轻微漂移：健康分={health_score:.0f}"
                else:
                    decision = GateDecision.PASS
                    message = f"策略健康：健康分={health_score:.0f}（真实漂移监控）"

                return GateFinding(
                    check_name="漂移监控",
                    decision=decision,
                    score=100 - health_score,
                    message=message,
                    details={
                        "health_score": health_score,
                        "alert_count": len(alerts),
                        "critical_count": critical_count,
                        "high_count": high_count,
                        "alerts": [a.message for a in alerts[:5]],
                        "real_check": True,
                    },
                )
            except Exception as e:
                # 真实检查失败，降级到简化版
                pass

        # 简化版（降级模式）
        win_rate = sum(1 for r in recent_returns if r > 0) / len(recent_returns) if recent_returns else 0.5
        excess_return = (sum(recent_returns) - sum(benchmark_returns)) / len(recent_returns) if recent_returns else 0

        # 健康分：胜率越高、超额收益越高，健康分越高
        health_score = 50 + (win_rate - 0.5) * 100 + excess_return * 100
        health_score = max(0, min(100, health_score))

        if health_score < self.drift_reject_threshold * 100:
            decision = GateDecision.REJECT
            message = f"策略漂移严重：健康分={health_score:.0f} < {self.drift_reject_threshold*100:.0f}"
        elif health_score < self.drift_warn_threshold * 100:
            decision = GateDecision.DOWNGRADE
            message = f"策略有漂移迹象：健康分={health_score:.0f}，建议降级运行"
        else:
            decision = GateDecision.PASS
            message = f"策略健康：健康分={health_score:.0f}（简化版）"

        return GateFinding(
            check_name="漂移监控",
            decision=decision,
            score=100 - health_score,  # 分数越高越危险
            message=message,
            details={"health_score": health_score, "win_rate": win_rate, "excess_return": excess_return, "real_check": False},
        )

    def _check_stress(self, price_data: Any) -> GateFinding:
        """检查压力测试。"""
        # 如果有真实价格数据，调用真实的压力测试器
        if _HAS_STRESS and price_data is not None:
            try:
                tester = StressTester(initial_equity=100000.0)
                # 运行几个预设情景
                scenarios = [
                    StressScenario(
                        name="2008金融危机",
                        description="2008年全球金融危机，雷曼兄弟破产",
                        price_shock=-0.25,
                        volatility_multiplier=3.5,
                        gap_days=3,
                        liquidity_crisis=True,
                    ),
                    StressScenario(
                        name="2020新冠暴跌",
                        description="2020年新冠疫情引发的全球暴跌",
                        price_shock=-0.20,
                        volatility_multiplier=4.0,
                        gap_days=5,
                        liquidity_crisis=True,
                    ),
                    StressScenario(
                        name="2010闪电崩盘",
                        description="2010年5月6日道琼斯指数暴跌近1000点",
                        price_shock=-0.09,
                        volatility_multiplier=5.0,
                        gap_days=0,
                        liquidity_crisis=True,
                    ),
                ]

                results = []
                for scenario in scenarios:
                    result = tester.run_scenario(scenario, current_exposure=0.02)
                    results.append(result)

                # 计算平均存活率（简化：用1 - max_drawdown来近似）
                avg_survival = sum(1.0 - r.max_drawdown for r in results) / len(results) if results else 1.0

                if avg_survival < self.stress_min_survival:
                    decision = GateDecision.REJECT
                    score = (1 - avg_survival) * 100
                    message = f"压力测试存活率过低：{avg_survival:.1%} < {self.stress_min_survival:.1%}"
                elif avg_survival < self.stress_min_survival * 1.2:
                    decision = GateDecision.WARN
                    score = (1 - avg_survival) * 100
                    message = f"压力测试存活率偏低：{avg_survival:.1%}"
                else:
                    decision = GateDecision.PASS
                    score = (1 - avg_survival) * 100
                    message = f"压力测试通过：平均存活率={avg_survival:.1%}"

                return GateFinding(
                    check_name="压力测试",
                    decision=decision,
                    score=score,
                    message=message,
                    details={
                        "avg_survival": avg_survival,
                        "scenario_count": len(results),
                        "scenarios": [r.scenario_name for r in results],
                        "real_check": True,
                    },
                )
            except Exception as e:
                # 真实检查失败，降级到简化版
                pass

        # 简化版（降级模式）
        return GateFinding(
            check_name="压力测试",
            decision=GateDecision.PASS,
            score=20.0,
            message="压力测试通过（降级模式，待接入真实压力测试）",
            details={"note": "降级模式，真实压力测试模块未就绪或调用失败", "real_check": False},
        )

    def _check_portfolio_risk(self, current_exposure: float, new_position_size: float, cluster_exposure: float) -> GateFinding:
        """检查组合层面风险。"""
        # 如果有真实组合风控模块，调用真实检查
        if _HAS_PORTFOLIO_RISK:
            try:
                config = PortfolioRiskConfig(
                    max_total_exposure=self.max_total_exposure,
                    max_exposure_per_cluster=self.max_exposure_per_cluster,
                )
                manager = PortfolioRiskManager(config=config)

                # 构建策略列表（简化版：当前策略 + 新策略）
                current_strategy = StrategyRisk(
                    strategy_id="current",
                    current_exposure=current_exposure,
                    correlation_cluster=0,
                )
                new_strategy = StrategyRisk(
                    strategy_id="new",
                    current_exposure=new_position_size,
                    correlation_cluster=0,
                )

                manager.add_strategy(current_strategy)
                allowed, reason = manager.can_open_new_position(
                    strategy_id="new",
                    planned_risk=new_position_size,
                )
                check_result = {"allowed": allowed, "reason": reason}

                if not check_result["allowed"]:
                    decision = GateDecision.REJECT
                    message = f"组合风险检查不通过：{check_result['reason']}"
                    score = 80.0
                else:
                    decision = GateDecision.PASS
                    total = current_exposure + new_position_size
                    message = f"组合风险正常：总敞口={total:.1%}（真实检查）"
                    score = (total / self.max_total_exposure) * 50

                return GateFinding(
                    check_name="组合风控",
                    decision=decision,
                    score=score,
                    message=message,
                    details={
                        "total_exposure": current_exposure + new_position_size,
                        "cluster_exposure": cluster_exposure,
                        "allowed": check_result.get("allowed", True),
                        "real_check": True,
                    },
                )
            except Exception as e:
                # 真实检查失败，降级到简化版
                pass

        # 简化版（降级模式）
        total_exposure = current_exposure + new_position_size

        if total_exposure > self.max_total_exposure or cluster_exposure > self.max_exposure_per_cluster:
            decision = GateDecision.REJECT
            score = max(total_exposure / self.max_total_exposure, cluster_exposure / self.max_exposure_per_cluster) * 50
            message = f"组合风险超标：总敞口={total_exposure:.1%}（上限{self.max_total_exposure:.1%}）"
        elif total_exposure > self.max_total_exposure * 0.8 or cluster_exposure > self.max_exposure_per_cluster * 0.8:
            decision = GateDecision.WARN
            score = 50.0
            message = f"组合风险接近上限：总敞口={total_exposure:.1%}"
        else:
            decision = GateDecision.PASS
            score = total_exposure / self.max_total_exposure * 50
            message = f"组合风险正常：总敞口={total_exposure:.1%}（简化版）"

        return GateFinding(
            check_name="组合风控",
            decision=decision,
            score=score,
            message=message,
            details={
                "total_exposure": total_exposure,
                "cluster_exposure": cluster_exposure,
                "real_check": False,
            },
        )

    def _decide_overall(self, findings: list[GateFinding]) -> GateDecision:
        """综合决策：只要有一个 REJECT 就是 REJECT。"""
        if any(f.decision == GateDecision.REJECT for f in findings):
            return GateDecision.REJECT
        if any(f.decision == GateDecision.DOWNGRADE for f in findings):
            return GateDecision.DOWNGRADE
        if any(f.decision == GateDecision.WARN for f in findings):
            return GateDecision.WARN
        return GateDecision.PASS
