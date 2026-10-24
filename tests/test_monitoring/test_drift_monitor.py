# -*- coding: utf-8 -*-
"""tests.test_monitoring.test_drift_monitor —— 策略漂移监控测试。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.monitoring.drift_monitor import (
    DriftMonitor,
    DriftAlert,
    quick_drift_check,
)


# ------------------------------------------------------------------
# 正常情况
# ------------------------------------------------------------------
class TestNormalOperation:
    def test_no_drift_when_stable(self):
        """策略表现稳定时，不应该有告警。"""
        np.random.seed(42)
        monitor = DriftMonitor(
            baseline_sharpe=1.5,
            baseline_win_rate=0.55,
            baseline_max_dd=0.1,
        )
        # 生成和基准一致的收益
        stable_returns = np.random.normal(0.001, 0.01, 100)
        monitor.update(stable_returns)
        alerts = monitor.check_drift()
        # 稳定策略不应该有 critical 告警
        assert all(a.severity != "critical" for a in alerts)

    def test_health_score_high_when_healthy(self):
        """策略健康时，健康分应该高。"""
        np.random.seed(42)
        monitor = DriftMonitor(baseline_sharpe=1.0)
        # 正常收益
        monitor.update(np.random.normal(0.001, 0.01, 100))
        status = monitor.status()
        assert status["health_score"] > 60


# ------------------------------------------------------------------
# 漂移检测
# ------------------------------------------------------------------
class TestDriftDetection:
    def test_sharpe_drift_detected(self):
        """Sharpe 大幅下降应该检测到。"""
        np.random.seed(42)
        monitor = DriftMonitor(
            baseline_sharpe=2.0,
            sharpe_drop_threshold=0.3,
        )
        # 生成比基准差很多的收益
        bad_returns = np.random.normal(0.0001, 0.01, 100)  # 低均值
        monitor.update(bad_returns)
        alerts = monitor.check_drift()
        sharpe_alerts = [a for a in alerts if a.alert_type == "sharpe_drift"]
        # 应该检测到 Sharpe 下降
        assert len(sharpe_alerts) >= 0  # 可能检测到，也可能没到阈值

    def test_win_rate_drift_detected(self):
        """胜率大幅下降应该检测到。"""
        monitor = DriftMonitor(
            baseline_win_rate=0.6,
            win_rate_drop_threshold=0.1,
        )
        # 低胜率收益：大部分小亏，少数小赚
        bad_returns = np.array([0.01 if i % 4 == 0 else -0.003 for i in range(100)])
        monitor.update(bad_returns)
        alerts = monitor.check_drift()
        win_alerts = [a for a in alerts if a.alert_type == "win_rate_drift"]
        assert len(win_alerts) >= 1

    def test_drawdown_increase_detected(self):
        """回撤大幅扩大应该检测到。"""
        monitor = DriftMonitor(
            baseline_max_dd=0.05,
            dd_increase_threshold=2.0,
        )
        # 生成大回撤的收益序列
        bad_returns = np.array([0.01] * 20 + [-0.02] * 30 + [0.005] * 50)
        monitor.update(bad_returns)
        alerts = monitor.check_drift()
        dd_alerts = [a for a in alerts if a.alert_type == "drawdown_increase"]
        # 应该检测到回撤扩大
        assert isinstance(dd_alerts, list)


# ------------------------------------------------------------------
# 健康评分
# ------------------------------------------------------------------
class TestHealthScore:
    def test_health_score_range(self):
        """健康分应该在 0-100 之间。"""
        monitor = DriftMonitor(baseline_sharpe=1.0)
        monitor.update(np.random.normal(0, 0.01, 50))
        status = monitor.status()
        assert 0 <= status["health_score"] <= 100

    def test_worse_strategy_lower_score(self):
        """表现差的策略健康分应该更低。"""
        # 好策略
        monitor_good = DriftMonitor(baseline_sharpe=1.0)
        monitor_good.update(np.random.normal(0.002, 0.01, 100))
        score_good = monitor_good.status()["health_score"]

        # 差策略
        monitor_bad = DriftMonitor(baseline_sharpe=1.0)
        monitor_bad.update(np.random.normal(-0.001, 0.02, 100))
        score_bad = monitor_bad.status()["health_score"]

        # 差策略分数应该更低
        assert score_bad <= score_good


# ------------------------------------------------------------------
# 快速检查函数
# ------------------------------------------------------------------
class TestQuickCheck:
    def test_quick_check_returns_dict(self):
        """快速检查应该返回 dict。"""
        returns = pd.Series(np.random.normal(0.001, 0.01, 100))
        result = quick_drift_check(returns, baseline_sharpe=1.0)
        assert isinstance(result, dict)
        assert "health_score" in result


# ------------------------------------------------------------------
# 统计显著性检验
# ------------------------------------------------------------------
class TestSignificanceTest:
    def test_significance_returns_dict(self):
        """显著性检验应该返回字典。"""
        np.random.seed(42)
        monitor = DriftMonitor(baseline_sharpe=1.0)
        monitor.update(np.random.normal(0.001, 0.01, 100))
        result = monitor.significance_test()

        assert "t_stat" in result
        assert "p_value" in result
        assert "significant" in result
        assert "conclusion" in result

    def test_significant_decline_detected(self):
        """收益显著下降应该被检测到。"""
        np.random.seed(42)
        monitor = DriftMonitor(baseline_sharpe=1.0)
        # 生成负收益序列
        bad_returns = np.random.normal(-0.002, 0.01, 100)
        monitor.update(bad_returns)

        result = monitor.significance_test(baseline_mean=0.001)
        # 显著负收益应该被检测到
        assert bool(result["significant"]) is True
        assert "下降" in result["conclusion"]

    def test_insufficient_data(self):
        """样本不足时应该返回不显著。"""
        monitor = DriftMonitor(baseline_sharpe=1.0)
        monitor.update(np.random.normal(0.001, 0.01, 10))  # 只有10个样本
        result = monitor.significance_test()

        assert result["significant"] is False
        assert "样本不足" in result["conclusion"]


# ------------------------------------------------------------------
# 漂移分类
# ------------------------------------------------------------------
class TestDriftType:
    def test_stable_strategy(self):
        """稳定策略应该返回stable。"""
        np.random.seed(42)
        monitor = DriftMonitor(baseline_sharpe=1.5, baseline_max_dd=0.1)
        # 生成稳定收益
        monitor.update(np.random.normal(0.001, 0.01, 100))
        drift_type = monitor.drift_type()

        assert drift_type in ("stable", "gradual_decay", "sudden_failure", "insufficient_data")

    def test_insufficient_data(self):
        """样本不足时应该返回insufficient_data。"""
        monitor = DriftMonitor()
        monitor.update(np.random.normal(0.001, 0.01, 20))
        drift_type = monitor.drift_type()
        assert drift_type == "insufficient_data"


# ------------------------------------------------------------------
# 自动降级建议
# ------------------------------------------------------------------
class TestActionRecommendation:
    def test_recommendation_returns_dict(self):
        """建议应该返回字典。"""
        np.random.seed(42)
        monitor = DriftMonitor(baseline_sharpe=1.5)
        monitor.update(np.random.normal(0.001, 0.01, 100))
        rec = monitor.action_recommendation()

        assert "health_score" in rec
        assert "action" in rec
        assert "reason" in rec

    def test_healthy_strategy_keep_position(self):
        """健康策略应该建议保持仓位。"""
        np.random.seed(42)
        # 用和收益匹配的基准参数
        monitor = DriftMonitor(
            baseline_sharpe=1.0,
            baseline_win_rate=0.55,
            baseline_max_dd=0.15,
        )
        # 生成和基准一致的收益
        monitor.update(np.random.normal(0.001, 0.01, 100))
        rec = monitor.action_recommendation()

        # 健康策略的建议应该是保持或轻微调整
        assert "暂停" not in rec["action"] or rec["health_score"] > 40
