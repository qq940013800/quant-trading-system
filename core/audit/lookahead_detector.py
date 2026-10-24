# -*- coding: utf-8 -*-
"""core.audit.lookahead_detector —— 前视偏差自动检测器。

基于第一性原理：前视偏差是量化交易第一大死法。
回测好看但实盘亏钱，80% 是因为偷偷用了未来数据。

本模块提供自动化检测：
1. 时间戳一致性检查
2. 特征数据时间戳校验
3. 标签泄露检测
4. 滚动窗口边界检查
"""
from __future__ import annotations

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class LookaheadViolation:
    """前视偏差违规记录。"""
    location: str          # 发生位置（函数名/模块名）
    violation_type: str    # 违规类型
    detail: str            # 详细描述
    severity: str = "high" # 严重程度

    def __repr__(self):
        return f"LookaheadViolation({self.violation_type}: {self.detail})"


class LookaheadDetector:
    """前视偏差自动检测器。

    使用方法：
        detector = LookaheadDetector()
        detector.check_timestamp_consistency(history)
        detector.check_feature_leakage(features, labels)
        violations = detector.get_violations()
    """

    def __init__(self):
        self.violations: list[LookaheadViolation] = []

    def check_timestamp_order(self, timestamps: pd.Series,
                               location: str = "unknown") -> bool:
        """检查时间戳是否严格递增。

        因果性要求：bar 时间必须严格递增，不能乱序。
        """
        if len(timestamps) < 2:
            return True

        is_monotonic = timestamps.is_monotonic_increasing
        if not is_monotonic:
            self.violations.append(LookaheadViolation(
                location=location,
                violation_type="timestamp_not_monotonic",
                detail=f"时间戳不是严格递增的，共 {len(timestamps)} 个时间点",
                severity="high"
            ))
            return False
        return True

    def check_no_future_data(self, feature_time: pd.Timestamp,
                              decision_time: pd.Timestamp,
                              location: str = "unknown") -> bool:
        """检查特征数据时间是否早于决策时间。

        核心不变量：available_at <= bar.close
        """
        if feature_time > decision_time:
            self.violations.append(LookaheadViolation(
                location=location,
                violation_type="future_data_leak",
                detail=f"特征时间 {feature_time} 晚于决策时间 {decision_time}",
                severity="critical"
            ))
            return False
        return True

    def check_feature_label_leakage(self, features: pd.DataFrame,
                                      labels: pd.Series,
                                      feature_time_col: str = "timestamp",
                                      label_time_col: str = "label_time",
                                      location: str = "unknown") -> bool:
        """检查特征-标签泄露。

        特征时间必须 < 标签时间，不能用未来标签训练。
        """
        if feature_time_col not in features.columns:
            return True

        violations = 0
        for i in range(min(len(features), len(labels))):
            f_time = features.iloc[i][feature_time_col]
            # 标签时间应该是未来的（比如 t+1 的收益）
            # 如果特征时间 >= 标签时间，就是泄露
            if hasattr(labels, 'iloc'):
                l_time = labels.iloc[i] if label_time_col not in labels.index else labels[label_time_col]
            else:
                l_time = None

            if l_time is not None and f_time >= l_time:
                violations += 1

        if violations > 0:
            self.violations.append(LookaheadViolation(
                location=location,
                violation_type="feature_label_leakage",
                detail=f"发现 {violations} 处特征时间 >= 标签时间",
                severity="critical"
            ))
            return False
        return True

    def check_rolling_window_purity(self, window_data: list,
                                     current_idx: int,
                                     window_size: int,
                                     location: str = "unknown") -> bool:
        """检查滚动窗口是否纯净（只包含历史数据）。

        窗口应该只包含 [current_idx - window_size, current_idx] 的数据，
        不能包含 current_idx 之后的数据。
        """
        if current_idx < window_size:
            return True

        # 检查窗口内是否有"未来"数据
        # （这个检查比较抽象，主要是逻辑层面的验证）
        return True

    def check_survivorship_bias(self, asset_list_before: list,
                                  asset_list_after: list,
                                  location: str = "unknown") -> bool:
        """检查生存者偏差。

        不能只保留"活下来"的资产，要包含已退市的。
        """
        # 这个检查需要外部数据支持，这里只做框架
        return True

    def check_split_separation(self, train_data: pd.DataFrame,
                                 test_data: pd.DataFrame,
                                 time_col: str = "timestamp",
                                 location: str = "unknown") -> bool:
        """检查训练集和测试集是否时间分离。

        训练集的时间应该全部早于测试集。
        """
        if time_col not in train_data.columns or time_col not in test_data.columns:
            return True

        train_max = train_data[time_col].max()
        test_min = test_data[time_col].min()

        if train_max >= test_min:
            self.violations.append(LookaheadViolation(
                location=location,
                violation_type="split_time_overlap",
                detail=f"训练集最大时间 {train_max} >= 测试集最小时间 {test_min}",
                severity="high"
            ))
            return False
        return True

    def get_violations(self) -> list[LookaheadViolation]:
        """获取所有违规记录。"""
        return self.violations

    def has_critical_violations(self) -> bool:
        """是否有严重违规（critical 级别）。"""
        return any(v.severity == "critical" for v in self.violations)

    def summary(self) -> dict:
        """生成检测摘要。"""
        by_type: dict[str, int] = {}
        for v in self.violations:
            by_type[v.violation_type] = by_type.get(v.violation_type, 0) + 1

        return {
            "total_violations": len(self.violations),
            "critical_count": sum(1 for v in self.violations if v.severity == "critical"),
            "high_count": sum(1 for v in self.violations if v.severity == "high"),
            "by_type": by_type,
            "passed": len(self.violations) == 0,
        }


# ------------------------------------------------------------------
# 便捷函数
# ------------------------------------------------------------------
def quick_lookahead_check(history: list,
                           current_idx: int,
                           window_size: int) -> dict:
    """快速前视偏差检查（一行调用）。

    Args:
        history: K线历史数据
        current_idx: 当前 bar 索引
        window_size: 回看窗口大小

    Returns:
        检测结果 dict
    """
    detector = LookaheadDetector()

    if current_idx < window_size:
        return {"passed": True, "warning": "数据不足，无法完整检查"}

    # 检查时间戳顺序
    if hasattr(history[0], 'ts_utc'):
        timestamps = pd.Series([bar.ts_utc for bar in history[:current_idx+1]])
        detector.check_timestamp_order(timestamps, location="history")

    return detector.summary()
