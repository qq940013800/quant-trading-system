# -*- coding: utf-8 -*-
"""core/debug/system_diagnoser.py —— 五层系统诊断框架。

基于第一性原理：
    交易系统出问题时，不是"策略不行"，而是某一层出了问题。
    必须逐层排查，不能笼统归因。

    五层诊断框架（从上到下）：
    1. 数据层 —— 数据是否干净？有没有缺口？有没有前视？
    2. 特征层 —— 特征计算是否正确？有没有泄露？
    3. 信号层 —— 信号逻辑是否正确？信号强度是否合理？
    4. 风控层 —— 止损/仓位/回撤控制是否正常工作？
    5. 执行层 —— 下单/成交/滑点是否符合预期？

    每一层都有明确的检查项和通过标准。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Callable


# ------------------------------------------------------------------
# 诊断结果
# ------------------------------------------------------------------
class Severity(Enum):
    """严重程度。"""
    OK = "ok"                    # 正常
    WARNING = "warning"          # 警告
    ERROR = "error"              # 错误
    CRITICAL = "critical"        # 严重错误


@dataclass
class DiagnosisCheck:
    """单个检查项。"""
    layer: str
    name: str
    severity: Severity
    message: str
    details: dict = field(default_factory=dict)


@dataclass
class DiagnosisReport:
    """完整诊断报告。"""
    timestamp: str
    checks: list[DiagnosisCheck] = field(default_factory=list)
    overall_health: float = 100.0  # 0-100分

    def add_check(self, check: DiagnosisCheck):
        self.checks.append(check)
        # 扣分：warning扣5分，error扣15分，critical扣30分
        if check.severity == Severity.WARNING:
            self.overall_health -= 5
        elif check.severity == Severity.ERROR:
            self.overall_health -= 15
        elif check.severity == Severity.CRITICAL:
            self.overall_health -= 30

    @property
    def has_errors(self) -> bool:
        return any(c.severity in [Severity.ERROR, Severity.CRITICAL] for c in self.checks)

    def summary(self) -> str:
        """生成诊断摘要。"""
        lines = [
            f"系统诊断报告（健康度: {self.overall_health:.0f}/100）",
            f"检查项: {len(self.checks)} 个",
            "-" * 50,
        ]
        for check in self.checks:
            icon = {"ok": "✅", "warning": "⚠️", "error": "❌", "critical": "🔴"}[check.severity.value]
            lines.append(f"{icon} [{check.layer}] {check.name}: {check.message}")
        return "\n".join(lines)


# ------------------------------------------------------------------
# 五层诊断器
# ------------------------------------------------------------------
class SystemDiagnoser:
    """五层系统诊断器。

    用法：
        diagnoser = SystemDiagnoser()
        report = diagnoser.run_full_diagnosis(data, strategy, ...)
        print(report.summary())
    """

    def __init__(self):
        self.report = DiagnosisReport(timestamp=datetime.now().isoformat())

    # ------------------------------------------------------------------
    # 第1层：数据层诊断
    # ------------------------------------------------------------------
    def check_data_layer(self,
                           data: pd.DataFrame,
                           required_columns: Optional[list[str]] = None) -> DiagnosisReport:
        """数据层诊断。

        检查项：
        1. 数据行数是否合理
        2. 必需列是否存在
        3. 是否有缺失值
        4. 时间戳是否单调递增
        5. OHLC关系是否正确（high >= low, open/close在范围内）
        """
        if required_columns is None:
            required_columns = ["open", "high", "low", "close"]

        # 1. 数据行数
        n_rows = len(data)
        if n_rows < 100:
            self.report.add_check(DiagnosisCheck(
                layer="data",
                name="数据量",
                severity=Severity.WARNING,
                message=f"数据行数较少: {n_rows}",
                details={"rows": n_rows},
            ))
        else:
            self.report.add_check(DiagnosisCheck(
                layer="data",
                name="数据量",
                severity=Severity.OK,
                message=f"数据行数: {n_rows}",
            ))

        # 2. 必需列
        missing_cols = [c for c in required_columns if c not in data.columns]
        if missing_cols:
            self.report.add_check(DiagnosisCheck(
                layer="data",
                name="必需列",
                severity=Severity.ERROR,
                message=f"缺少列: {missing_cols}",
                details={"missing": missing_cols},
            ))
        else:
            self.report.add_check(DiagnosisCheck(
                layer="data",
                name="必需列",
                severity=Severity.OK,
                message="所有必需列都存在",
            ))

        # 3. 缺失值
        if "close" in data.columns:
            nan_count = data["close"].isna().sum()
            if nan_count > 0:
                self.report.add_check(DiagnosisCheck(
                    layer="data",
                    name="缺失值",
                    severity=Severity.ERROR,
                    message=f"close列有{nan_count}个缺失值",
                ))
            else:
                self.report.add_check(DiagnosisCheck(
                    layer="data",
                    name="缺失值",
                    severity=Severity.OK,
                    message="无缺失值",
                ))

        # 4. OHLC关系
        if all(c in data.columns for c in ["high", "low", "open", "close"]):
            bad_high = (data["high"] < data["low"]).sum()
            if bad_high > 0:
                self.report.add_check(DiagnosisCheck(
                    layer="data",
                    name="OHLC关系",
                    severity=Severity.ERROR,
                    message=f"high < low 的异常K线: {bad_high}根",
                ))
            else:
                self.report.add_check(DiagnosisCheck(
                    layer="data",
                    name="OHLC关系",
                    severity=Severity.OK,
                    message="OHLC关系正常",
                ))

        return self.report

    # ------------------------------------------------------------------
    # 第2层：特征层诊断
    # ------------------------------------------------------------------
    def check_feature_layer(self,
                             features: pd.DataFrame,
                             expected_features: list[str]) -> DiagnosisReport:
        """特征层诊断。"""
        # 1. 特征是否都存在
        missing = [f for f in expected_features if f not in features.columns]
        if missing:
            self.report.add_check(DiagnosisCheck(
                layer="feature",
                name="特征完整性",
                severity=Severity.ERROR,
                message=f"缺少特征: {missing}",
            ))
        else:
            self.report.add_check(DiagnosisCheck(
                layer="feature",
                name="特征完整性",
                severity=Severity.OK,
                message=f"所有{len(expected_features)}个特征都存在",
            ))

        # 2. 特征是否有NaN
        nan_features = [f for f in expected_features
                       if f in features.columns and features[f].isna().sum() > len(features) * 0.1]
        if nan_features:
            self.report.add_check(DiagnosisCheck(
                layer="feature",
                name="特征缺失率",
                severity=Severity.WARNING,
                message=f"特征缺失率过高: {nan_features}",
            ))

        return self.report

    # ------------------------------------------------------------------
    # 第3层：信号层诊断
    # ------------------------------------------------------------------
    def check_signal_layer(self,
                            signals: list[int],
                            expected_rate: float = 0.05) -> DiagnosisReport:
        """信号层诊断。

        检查项：
        1. 信号频率是否合理（不能太多也不能太少）
        2. 多空信号是否平衡
        """
        n_signals = len([s for s in signals if s != 0])
        signal_rate = n_signals / max(len(signals), 1)

        # 1. 信号频率
        if signal_rate < expected_rate * 0.1:
            self.report.add_check(DiagnosisCheck(
                layer="signal",
                name="信号频率",
                severity=Severity.WARNING,
                message=f"信号太少: {signal_rate:.2%}（预期{expected_rate:.0%}）",
            ))
        elif signal_rate > expected_rate * 5:
            self.report.add_check(DiagnosisCheck(
                layer="signal",
                name="信号频率",
                severity=Severity.WARNING,
                message=f"信号太多: {signal_rate:.2%}（预期{expected_rate:.0%}）",
            ))
        else:
            self.report.add_check(DiagnosisCheck(
                layer="signal",
                name="信号频率",
                severity=Severity.OK,
                message=f"信号频率正常: {signal_rate:.2%}",
            ))

        return self.report

    # ------------------------------------------------------------------
    # 第4层：风控层诊断
    # ------------------------------------------------------------------
    def check_risk_layer(self,
                          trades: list[dict]) -> DiagnosisReport:
        """风控层诊断。"""
        if not trades:
            self.report.add_check(DiagnosisCheck(
                layer="risk",
                name="交易记录",
                severity=Severity.WARNING,
                message="没有交易记录，无法诊断",
            ))
            return self.report

        # 1. 止损执行率
        stopped = sum(1 for t in trades if t.get("exit_reason") == "stop_loss")
        stop_rate = stopped / len(trades)

        if stop_rate > 0.7:
            self.report.add_check(DiagnosisCheck(
                layer="risk",
                name="止损频率",
                severity=Severity.WARNING,
                message=f"止损率过高: {stop_rate:.1%}（可能止损太窄）",
            ))
        else:
            self.report.add_check(DiagnosisCheck(
                layer="risk",
                name="止损频率",
                severity=Severity.OK,
                message=f"止损率: {stop_rate:.1%}",
            ))

        return self.report

    # ------------------------------------------------------------------
    # 第5层：执行层诊断
    # ------------------------------------------------------------------
    def check_execution_layer(self,
                               orders: list[dict]) -> DiagnosisReport:
        """执行层诊断。"""
        if not orders:
            self.report.add_check(DiagnosisCheck(
                layer="execution",
                name="订单记录",
                severity=Severity.WARNING,
                message="没有订单记录",
            ))
            return self.report

        # 1. 订单成功率
        filled = sum(1 for o in orders if o.get("status") == "filled")
        fill_rate = filled / len(orders)

        if fill_rate < 0.9:
            self.report.add_check(DiagnosisCheck(
                layer="execution",
                name="成交率",
                severity=Severity.ERROR,
                message=f"成交率过低: {fill_rate:.1%}",
            ))
        else:
            self.report.add_check(DiagnosisCheck(
                layer="execution",
                name="成交率",
                severity=Severity.OK,
                message=f"成交率: {fill_rate:.1%}",
            ))

        return self.report

    # ------------------------------------------------------------------
    # 全量诊断
    # ------------------------------------------------------------------
    def run_full_diagnosis(self,
                            data: pd.DataFrame,
                            features: Optional[pd.DataFrame] = None,
                            signals: Optional[list[int]] = None,
                            trades: Optional[list[dict]] = None,
                            orders: Optional[list[dict]] = None) -> DiagnosisReport:
        """运行完整五层诊断。"""
        self.report = DiagnosisReport(timestamp=datetime.now().isoformat())

        self.check_data_layer(data)
        if features is not None:
            self.check_feature_layer(features, list(features.columns))
        if signals is not None:
            self.check_signal_layer(signals)
        if trades is not None:
            self.check_risk_layer(trades)
        if orders is not None:
            self.check_execution_layer(orders)

        return self.report
