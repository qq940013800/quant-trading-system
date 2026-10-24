# -*- coding: utf-8 -*-
"""tests.test_audit.test_lookahead_detector —— 前视偏差检测器测试。"""
from __future__ import annotations

import pandas as pd
import pytest

from core.audit.lookahead_detector import (
    LookaheadDetector,
    LookaheadViolation,
    quick_lookahead_check,
)


# ------------------------------------------------------------------
# 时间戳顺序检查
# ------------------------------------------------------------------
class TestTimestampOrder:
    def test_monotonic_increasing_passes(self):
        """严格递增的时间戳应该通过。"""
        detector = LookaheadDetector()
        timestamps = pd.Series(pd.date_range("2024-01-01", periods=10, freq="D"))
        result = detector.check_timestamp_order(timestamps, location="test")
        assert result is True
        assert len(detector.get_violations()) == 0

    def test_non_monotonic_fails(self):
        """非递增的时间戳应该检测到违规。"""
        detector = LookaheadDetector()
        timestamps = pd.Series([
            pd.Timestamp("2024-01-01"),
            pd.Timestamp("2024-01-03"),
            pd.Timestamp("2024-01-02"),  # 乱序
            pd.Timestamp("2024-01-04"),
        ])
        result = detector.check_timestamp_order(timestamps, location="test")
        assert result is False
        assert len(detector.get_violations()) > 0


# ------------------------------------------------------------------
# 未来数据泄露检查
# ------------------------------------------------------------------
class TestFutureDataLeak:
    def test_feature_before_decision_passes(self):
        """特征时间早于决策时间应该通过。"""
        detector = LookaheadDetector()
        feature_time = pd.Timestamp("2024-01-01 10:00")
        decision_time = pd.Timestamp("2024-01-01 10:01")
        result = detector.check_no_future_data(feature_time, decision_time, "test")
        assert result is True

    def test_feature_after_decision_fails(self):
        """特征时间晚于决策时间应该检测到泄露。"""
        detector = LookaheadDetector()
        feature_time = pd.Timestamp("2024-01-01 10:02")  # 未来
        decision_time = pd.Timestamp("2024-01-01 10:01")
        result = detector.check_no_future_data(feature_time, decision_time, "test")
        assert result is False
        assert detector.has_critical_violations() is True


# ------------------------------------------------------------------
# 数据集分离检查
# ------------------------------------------------------------------
class TestSplitSeparation:
    def test_train_before_test_passes(self):
        """训练集时间全部早于测试集应该通过。"""
        detector = LookaheadDetector()
        train = pd.DataFrame({"timestamp": pd.date_range("2024-01-01", periods=10)})
        test = pd.DataFrame({"timestamp": pd.date_range("2024-01-11", periods=5)})
        result = detector.check_split_separation(train, test, location="test")
        assert result is True

    def test_overlapping_split_fails(self):
        """训练集和测试集时间重叠应该检测到违规。"""
        detector = LookaheadDetector()
        train = pd.DataFrame({"timestamp": pd.date_range("2024-01-01", periods=15)})
        test = pd.DataFrame({"timestamp": pd.date_range("2024-01-10", periods=5)})  # 重叠
        result = detector.check_split_separation(train, test, location="test")
        assert result is False


# ------------------------------------------------------------------
# 检测摘要
# ------------------------------------------------------------------
class TestDetectorSummary:
    def test_clean_data_summary(self):
        """干净的数据应该返回 passed=True。"""
        detector = LookaheadDetector()
        timestamps = pd.Series(pd.date_range("2024-01-01", periods=10, freq="D"))
        detector.check_timestamp_order(timestamps)
        summary = detector.summary()
        assert summary["passed"] is True
        assert summary["total_violations"] == 0

    def test_dirty_data_summary(self):
        """有问题的数据应该返回详细统计。"""
        detector = LookaheadDetector()
        feature_time = pd.Timestamp("2024-01-01 10:02")
        decision_time = pd.Timestamp("2024-01-01 10:01")
        detector.check_no_future_data(feature_time, decision_time)
        summary = detector.summary()
        assert summary["passed"] is False
        assert summary["critical_count"] > 0


# ------------------------------------------------------------------
# 快速检查函数
# ------------------------------------------------------------------
class TestQuickCheck:
    def test_quick_check_returns_dict(self):
        """快速检查应该返回 dict。"""
        result = quick_lookahead_check([], current_idx=0, window_size=10)
        assert isinstance(result, dict)
        assert "passed" in result
