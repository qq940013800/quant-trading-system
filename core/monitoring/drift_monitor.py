# -*- coding: utf-8 -*-
"""core.monitoring.drift_monitor —— 策略漂移监控系统。

基于第一性原理：所有 Alpha 都会衰减。策略上线即衰减，
你需要提前知道它什么时候开始失效，而不是等亏了大钱才发现。

核心功能：
1. 性能漂移检测（Sharpe 衰减）
2. 胜率漂移检测
3. 最大回撤异常检测
4. 统计显著性检验（判断是真漂移还是随机波动）
5. 漂移分类（缓慢衰减 vs 突然失效）
6. 自动降级建议（减仓/暂停/退役）
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DriftAlert:
    """漂移告警记录。"""
    alert_type: str       # 告警类型
    current_value: float  # 当前值
    baseline_value: float # 基准值
    deviation: float      # 偏离度
    severity: str         # 严重程度（low/medium/high/critical）
    message: str          # 告警信息

    def __repr__(self):
        return f"DriftAlert({self.alert_type}: {self.message})"


class DriftMonitor:
    """策略漂移监控器。

    使用方法：
        monitor = DriftMonitor(baseline_sharpe=1.5, baseline_win_rate=0.55)
        monitor.update(returns)  # 定期更新
        alerts = monitor.check_drift()
    """

    def __init__(self,
                 baseline_sharpe: float = 1.0,
                 baseline_win_rate: float = 0.5,
                 baseline_max_dd: float = 0.15,
                 sharpe_drop_threshold: float = 0.3,  # Sharpe 下降 30% 告警
                 win_rate_drop_threshold: float = 0.1, # 胜率下降 10% 告警
                 dd_increase_threshold: float = 2.0, # 回撤扩大 2 倍告警
                 window_size: int = 100):  # 滑动窗口大小

        self.baseline_sharpe = baseline_sharpe
        self.baseline_win_rate = baseline_win_rate
        self.baseline_max_dd = baseline_max_dd
        self.sharpe_drop_threshold = sharpe_drop_threshold
        self.win_rate_drop_threshold = win_rate_drop_threshold
        self.dd_increase_threshold = dd_increase_threshold
        self.window_size = window_size

        self.recent_returns: list[float] = []
        self.alerts: list[DriftAlert] = []

    def update(self, returns: pd.Series | list[float]) -> None:
        """更新最新收益数据。"""
        if isinstance(returns, pd.Series):
            new_returns = returns.tolist()
        else:
            new_returns = list(returns)

        self.recent_returns.extend(new_returns)

        # 只保留最近 window_size 个
        if len(self.recent_returns) > self.window_size:
            self.recent_returns = self.recent_returns[-self.window_size:]

    def _current_sharpe(self) -> float:
        """计算当前滚动 Sharpe。"""
        if len(self.recent_returns) < 20:
            return 0.0
        rets = np.array(self.recent_returns)
        mean = rets.mean()
        std = rets.std()
        if std == 0:
            return 0.0
        return float(mean / std * np.sqrt(252))  # 年化

    def _current_win_rate(self) -> float:
        """计算当前胜率。"""
        if len(self.recent_returns) < 20:
            return 0.5
        wins = sum(1 for r in self.recent_returns if r > 0)
        return wins / len(self.recent_returns)

    def _current_max_dd(self) -> float:
        """计算当前最大回撤。"""
        if len(self.recent_returns) < 20:
            return 0.0
        cum = np.cumsum(self.recent_returns)
        running_max = np.maximum.accumulate(cum)
        dd = cum - running_max
        return float(abs(dd.min()))

    def check_drift(self) -> list[DriftAlert]:
        """检查是否有漂移。"""
        self.alerts = []

        if len(self.recent_returns) < 20:
            return self.alerts

        # 1. Sharpe 漂移检测
        current_sharpe = self._current_sharpe()
        sharpe_deviation = (self.baseline_sharpe - current_sharpe) / self.baseline_sharpe if self.baseline_sharpe > 0 else 0

        if sharpe_deviation > self.sharpe_drop_threshold:
            severity = self._severity(sharpe_deviation, self.sharpe_drop_threshold, 2.0)
            self.alerts.append(DriftAlert(
                alert_type="sharpe_drift",
                current_value=current_sharpe,
                baseline_value=self.baseline_sharpe,
                deviation=sharpe_deviation,
                severity=severity,
                message=f"Sharpe 从 {self.baseline_sharpe:.2f} 降至 {current_sharpe:.2f}（下降 {sharpe_deviation:.1%}）"
            ))

        # 2. 胜率漂移检测
        current_win_rate = self._current_win_rate()
        win_deviation = self.baseline_win_rate - current_win_rate

        if win_deviation > self.win_rate_drop_threshold:
            severity = self._severity(win_deviation, self.win_rate_drop_threshold, 0.2)
            self.alerts.append(DriftAlert(
                alert_type="win_rate_drift",
                current_value=current_win_rate,
                baseline_value=self.baseline_win_rate,
                deviation=win_deviation,
                severity=severity,
                message=f"胜率从 {self.baseline_win_rate:.1%} 降至 {current_win_rate:.1%}（下降 {win_deviation:.1%}）"
            ))

        # 3. 回撤异常检测
        current_dd = self._current_max_dd()
        dd_ratio = current_dd / self.baseline_max_dd if self.baseline_max_dd > 0 else 1.0

        if dd_ratio > self.dd_increase_threshold:
            severity = self._severity(dd_ratio, self.dd_increase_threshold, 3.0)
            self.alerts.append(DriftAlert(
                alert_type="drawdown_increase",
                current_value=current_dd,
                baseline_value=self.baseline_max_dd,
                deviation=dd_ratio,
                severity=severity,
                message=f"最大回撤从 {self.baseline_max_dd:.1%} 扩大至 {current_dd:.1%}（{dd_ratio:.1f} 倍）"
            ))

        return self.alerts

    def _severity(self, deviation: float, threshold: float, critical: float) -> str:
        """根据偏离度判断严重程度。"""
        if deviation >= critical:
            return "critical"
        elif deviation >= threshold * 1.5:
            return "high"
        elif deviation >= threshold:
            return "medium"
        else:
            return "low"

    def status(self) -> dict:
        """获取监控状态摘要。"""
        self.check_drift()
        return {
            "current_sharpe": self._current_sharpe(),
            "current_win_rate": self._current_win_rate(),
            "current_max_dd": self._current_max_dd(),
            "n_alerts": len(self.alerts),
            "critical_alerts": sum(1 for a in self.alerts if a.severity == "critical"),
            "health_score": self._health_score(),
        }

    def _health_score(self) -> float:
        """计算策略健康分（0-100）。"""
        score = 100.0

        # Sharpe 下降扣分
        current_sharpe = self._current_sharpe()
        if self.baseline_sharpe > 0:
            sharpe_ratio = current_sharpe / self.baseline_sharpe
            score -= (1 - sharpe_ratio) * 40  # 最多扣 40 分

        # 胜率下降扣分
        current_win_rate = self._current_win_rate()
        win_diff = self.baseline_win_rate - current_win_rate
        score -= win_diff * 100  # 最多扣 ~20 分

        # 回撤扩大扣分
        current_dd = self._current_max_dd()
        if self.baseline_max_dd > 0:
            dd_ratio = current_dd / self.baseline_max_dd
            score -= (dd_ratio - 1) * 20  # 最多扣 ~40 分

        return float(max(0, min(100, score)))

    def significance_test(self, baseline_mean: float = 0.0005,
                          alpha: float = 0.05) -> dict:
        """统计显著性检验：判断收益下降是不是真的。

        从第一性原理出发：随机波动也会导致收益下降，
        你需要用统计检验判断这是真漂移还是随机噪声。

        Args:
            baseline_mean: 基准日收益率（默认0.05%）
            alpha: 显著性水平（默认5%）

        Returns:
            {
                "t_stat": t统计量,
                "p_value": p值,
                "significant": 是否显著,
                "conclusion": 结论说明
            }
        """
        if len(self.recent_returns) < 30:
            return {
                "t_stat": 0.0,
                "p_value": 1.0,
                "significant": False,
                "conclusion": "样本不足，无法判断",
            }

        rets = np.array(self.recent_returns)
        n = len(rets)
        mean = rets.mean()
        std = rets.std()

        if std == 0:
            return {
                "t_stat": 0.0,
                "p_value": 1.0,
                "significant": False,
                "conclusion": "零方差，异常",
            }

        # 单样本t检验：H0: 均值 = baseline_mean
        t_stat = (mean - baseline_mean) / (std / np.sqrt(n))

        # 简化的p值估算（双侧检验，用正态近似）
        # |t| > 1.96 对应 p < 0.05
        p_value = 2 * (1 - 0.5 * (1 + np.sign(abs(t_stat)) *
                                   (1 - np.exp(-t_stat * t_stat / 2))))

        significant = abs(t_stat) > 1.96

        if significant and mean < baseline_mean:
            conclusion = "收益显著下降，真漂移"
        elif significant:
            conclusion = "收益显著上升，异常好"
        else:
            conclusion = "变化不显著，可能是随机波动"

        return {
            "t_stat": float(t_stat),
            "p_value": float(p_value),
            "significant": significant,
            "conclusion": conclusion,
        }

    def drift_type(self) -> str:
        """判断漂移类型：缓慢衰减 vs 突然失效。

        从第一性原理出发：
        - 缓慢衰减：策略正常生命周期，慢慢失效
        - 突然失效：市场结构突变，策略一下子不工作了

        Returns:
            "stable" / "gradual_decay" / "sudden_failure"
        """
        if len(self.recent_returns) < 50:
            return "insufficient_data"

        # 分成前后两半比较
        mid = len(self.recent_returns) // 2
        first_half = np.array(self.recent_returns[:mid])
        second_half = np.array(self.recent_returns[mid:])

        first_mean = first_half.mean()
        second_mean = second_half.mean()

        diff_ratio = abs(second_mean - first_mean) / abs(first_mean) if first_mean != 0 else 0

        # 健康分
        health = self._health_score()

        if health > 80:
            return "stable"
        elif diff_ratio > 0.5:  # 前后差异很大
            return "sudden_failure"
        else:
            return "gradual_decay"

    def action_recommendation(self) -> dict:
        """根据健康分给出自动降级建议。

        从第一性原理出发：告警只是第一步，关键是接下来怎么办。

        Returns:
            {
                "health_score": 健康分,
                "action": 建议操作,
                "reason": 原因说明
            }
        """
        health = self._health_score()
        drift_type = self.drift_type()

        if health >= 80:
            action = "保持当前仓位"
            reason = f"策略健康分 {health:.0f}，状态良好"
        elif health >= 60:
            action = "减仓50%观察"
            reason = f"策略健康分 {health:.0f}，有轻微漂移（{drift_type}）"
        elif health >= 40:
            action = "减仓至25%，密切监控"
            reason = f"策略健康分 {health:.0f}，明显漂移（{drift_type}）"
        else:
            action = "暂停交易，准备退役"
            reason = f"策略健康分 {health:.0f}，严重失效（{drift_type}）"

        return {
            "health_score": health,
            "drift_type": drift_type,
            "action": action,
            "reason": reason,
        }


# ------------------------------------------------------------------
# 便捷函数
# ------------------------------------------------------------------
def quick_drift_check(returns: pd.Series,
                       baseline_sharpe: float) -> dict:
    """快速漂移检查。"""
    monitor = DriftMonitor(baseline_sharpe=baseline_sharpe)
    monitor.update(returns)
    return monitor.status()
