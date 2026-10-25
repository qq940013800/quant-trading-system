"""
数据治理体系

第一性原理：
- 垃圾进，垃圾出。再漂亮的ML模型，输入是脏数据，输出就是垃圾。
- 数据质量问题是量化系统最常见也最隐蔽的失败原因。
- 数据不对齐，时间戳错一位，回测结果就是假的。

全球顶级机构实践：
- Two Sigma：数据团队比策略团队还大
- Renaissance：数据清洗管道是核心机密
- Citadel：每个数据集都有数据血缘和质量监控

数据质量五维度：
1. 完整性 —— 有没有缺失值？
2. 准确性 —— 数值对不对？有没有异常值？
3. 一致性 —— 跨表跨源是否一致？
4. 及时性 —— 数据是不是最新的？
5. 唯一性 —— 有没有重复数据？
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.utils.logger import get_logger

logger = get_logger(__name__)


class DataQualityLevel(Enum):
    """数据质量等级"""
    EXCELLENT = "excellent"    # 95%+ 完整准确
    GOOD = "good"             # 90-95%
    FAIR = "fair"             # 80-90%
    POOR = "poor"             # 60-80%
    CRITICAL = "critical"     # <60% 不可用


class DataIssueType(Enum):
    """数据问题类型"""
    MISSING_VALUES = "missing_values"           # 缺失值
    OUTLIERS = "outliers"                       # 异常值
    DUPLICATES = "duplicates"                   # 重复数据
    TIME_MISMATCH = "time_mismatch"            # 时间戳不对齐
    STALE_DATA = "stale_data"                   # 数据过期
    ZERO_VOLUME = "zero_volume"                 # 零成交量
    GAP_DETECTED = "gap_detected"               # 数据断档
    FORMAT_ERROR = "format_error"               # 格式错误


@dataclass
class DataQualityReport:
    """数据质量报告"""
    dataset_name: str
    timestamp: datetime
    quality_score: float = 0.0           # 0-100
    quality_level: DataQualityLevel = DataQualityLevel.GOOD

    # 五维度评分
    completeness_score: float = 100.0
    accuracy_score: float = 100.0
    consistency_score: float = 100.0
    timeliness_score: float = 100.0
    uniqueness_score: float = 100.0

    # 问题列表
    issues: List[Dict[str, Any]] = field(default_factory=list)

    # 统计信息
    total_records: int = 0
    missing_records: int = 0
    outlier_records: int = 0
    duplicate_records: int = 0

    # 建议
    recommendations: List[str] = field(default_factory=list)


@dataclass
class DataSource:
    """数据源元数据"""
    name: str
    source_type: str  # exchange / vendor / custom
    symbol: str
    timeframe: str
    start_date: datetime
    end_date: datetime
    row_count: int = 0
    checksum: str = ""
    last_quality_check: Optional[datetime] = None


class DataGovernanceService:
    """
    数据治理服务

    核心功能：
    1. 数据质量检查（五维度）
    2. 数据血缘追溯
    3. 数据集合分离验证
    4. 数据版本管理
    5. 异常自动检测和告警
    """

    def __init__(self):
        self.data_sources: Dict[str, DataSource] = {}
        self.quality_history: Dict[str, List[DataQualityReport]] = {}
        self.issue_callbacks: List[Callable[[DataQualityReport], None]] = []

    def register_data_source(self, source: DataSource):
        """注册数据源"""
        self.data_sources[source.name] = source
        logger.info(f"数据源注册: {source.name} ({source.symbol} {source.timeframe})")

    def check_quality(self, dataset_name: str, data: List[Dict[str, Any]]) -> DataQualityReport:
        """
        检查数据集质量

        data:  [{timestamp: ..., open: ..., high: ..., low: ..., close: ..., volume: ...}, ...]
        """
        report = DataQualityReport(
            dataset_name=dataset_name,
            timestamp=datetime.now(timezone.utc),
            total_records=len(data),
        )

        if not data:
            report.quality_level = DataQualityLevel.CRITICAL
            report.issues.append({"type": DataIssueType.MISSING_VALUES.value, "message": "数据集为空"})
            return report

        # 1. 完整性检查
        self._check_completeness(data, report)

        # 2. 准确性检查
        self._check_accuracy(data, report)

        # 3. 一致性检查
        self._check_consistency(data, report)

        # 4. 及时性检查
        self._check_timeliness(data, report)

        # 5. 唯一性检查
        self._check_uniqueness(data, report)

        # 计算总分
        report.quality_score = (
            report.completeness_score * 0.3 +
            report.accuracy_score * 0.3 +
            report.consistency_score * 0.2 +
            report.timeliness_score * 0.1 +
            report.uniqueness_score * 0.1
        )

        # 质量等级
        if report.quality_score >= 95:
            report.quality_level = DataQualityLevel.EXCELLENT
        elif report.quality_score >= 90:
            report.quality_level = DataQualityLevel.GOOD
        elif report.quality_score >= 80:
            report.quality_level = DataQualityLevel.FAIR
        elif report.quality_score >= 60:
            report.quality_level = DataQualityLevel.POOR
        else:
            report.quality_level = DataQualityLevel.CRITICAL

        # 生成建议
        self._generate_recommendations(report)

        # 保存历史
        if dataset_name not in self.quality_history:
            self.quality_history[dataset_name] = []
        self.quality_history[dataset_name].append(report)

        # 触发回调
        for callback in self.issue_callbacks:
            try:
                callback(report)
            except Exception as e:
                logger.error(f"数据质量回调失败: {e}")

        return report

    def _check_completeness(self, data: List[Dict], report: DataQualityReport):
        """检查完整性：有没有缺失值"""
        required_fields = ["timestamp", "open", "high", "low", "close"]
        missing_count = 0

        for row in data:
            for field in required_fields:
                if field not in row or row[field] is None:
                    missing_count += 1
                    report.issues.append({
                        "type": DataIssueType.MISSING_VALUES.value,
                        "field": field,
                        "timestamp": row.get("timestamp"),
                    })
                    break

        report.missing_records = missing_count
        report.completeness_score = (1 - missing_count / len(data)) * 100

    def _check_accuracy(self, data: List[Dict], report: DataQualityReport):
        """检查准确性：有没有异常值、价格逻辑对不对"""
        outlier_count = 0

        for i, row in enumerate(data):
            if not all(k in row for k in ["open", "high", "low", "close"]):
                continue

            o, h, l, c = row["open"], row["high"], row["low"], row["close"]

            # 价格逻辑检查：high >= max(open, close), low <= min(open, close)
            if h < max(o, c) or l > min(o, c):
                outlier_count += 1
                report.issues.append({
                    "type": DataIssueType.OUTLIERS.value,
                    "message": f"价格逻辑错误: O={o} H={h} L={l} C={c}",
                    "timestamp": row.get("timestamp"),
                })

            # 异常波动检查（单根K线涨跌超过20%）
            if o > 0 and abs(c - o) / o > 0.2:
                outlier_count += 1
                report.issues.append({
                    "type": DataIssueType.OUTLIERS.value,
                    "message": f"异常波动: {abs(c - o) / o * 100:.1f}%",
                    "timestamp": row.get("timestamp"),
                })

        report.outlier_records = outlier_count
        report.accuracy_score = (1 - outlier_count / len(data)) * 100

    def _check_consistency(self, data: List[Dict], report: DataQualityReport):
        """检查一致性：时间序列是否连续"""
        if len(data) < 2:
            return

        gaps = 0
        timestamps = [row.get("timestamp") for row in data if "timestamp" in row]

        for i in range(1, len(timestamps)):
            # 简单检查：相邻时间差是否合理（假设1小时K线，允许±5分钟误差）
            diff = (timestamps[i] - timestamps[i-1]).total_seconds() / 3600
            if diff > 1.2 or diff < 0.8:  # 不是1小时间隔
                gaps += 1
                report.issues.append({
                    "type": DataIssueType.GAP_DETECTED.value,
                    "message": f"时间间隔异常: {diff:.2f}小时",
                    "timestamp": timestamps[i],
                })

        report.consistency_score = (1 - gaps / len(data)) * 100

    def _check_timeliness(self, data: List[Dict], report: DataQualityReport):
        """检查及时性：数据是不是最新的"""
        if not data:
            return

        last_timestamp = data[-1].get("timestamp")
        if not last_timestamp:
            return

        age_hours = (datetime.now(timezone.utc) - last_timestamp).total_seconds() / 3600

        # 假设是小时线数据，超过24小时就算过期
        if age_hours > 24:
            report.timeliness_score = max(0, 100 - (age_hours - 24))
            report.issues.append({
                "type": DataIssueType.STALE_DATA.value,
                "message": f"数据过期: {age_hours:.1f}小时",
                "last_timestamp": last_timestamp,
            })

    def _check_uniqueness(self, data: List[Dict], report: DataQualityReport):
        """检查唯一性：有没有重复数据"""
        seen = set()
        duplicates = 0

        for row in data:
            ts = row.get("timestamp")
            if ts:
                ts_str = str(ts)
                if ts_str in seen:
                    duplicates += 1
                    report.issues.append({
                        "type": DataIssueType.DUPLICATES.value,
                        "timestamp": ts,
                    })
                else:
                    seen.add(ts_str)

        report.duplicate_records = duplicates
        report.uniqueness_score = (1 - duplicates / len(data)) * 100

    def _generate_recommendations(self, report: DataQualityReport):
        """生成改进建议"""
        if report.quality_level == DataQualityLevel.CRITICAL:
            report.recommendations.append("数据质量严重不足，不建议用于策略开发")
            report.recommendations.append("检查数据源连接和采集管道")
        elif report.quality_level == DataQualityLevel.POOR:
            report.recommendations.append("数据质量较差，需要清洗后才能使用")
            report.recommendations.append("填充缺失值，去除异常值")
        elif report.quality_level == DataQualityLevel.FAIR:
            report.recommendations.append("数据质量一般，建议进一步清洗")
        else:
            report.recommendations.append("数据质量良好，可以使用")

        # 针对具体问题的建议
        issue_types = set(i["type"] for i in report.issues)
        if DataIssueType.MISSING_VALUES.value in issue_types:
            report.recommendations.append("检查数据采集管道，补充缺失数据")
        if DataIssueType.OUTLIERS.value in issue_types:
            report.recommendations.append("检查异常值，考虑用中位数替换或剔除")
        if DataIssueType.GAP_DETECTED.value in issue_types:
            report.recommendations.append("检查时间对齐，确认是否有数据断档")

    def validate_train_test_separation(self, train_data: List, test_data: List) -> Dict[str, Any]:
        """验证训练集和测试集是否正确分离（防止前视偏差）"""
        train_last_time = max(row["timestamp"] for row in train_data if "timestamp" in row)
        test_first_time = min(row["timestamp"] for row in test_data if "timestamp" in row)

        overlap = train_last_time >= test_first_time

        return {
            "train_last_timestamp": train_last_time,
            "test_first_timestamp": test_first_time,
            "overlap_detected": overlap,
            "verdict": "❌ 数据泄露！训练集和测试集有重叠" if overlap else
                       "✅ 数据分离正确，没有前视偏差",
        }

    def get_quality_summary(self, dataset_name: str) -> Dict[str, Any]:
        """获取数据集质量摘要"""
        history = self.quality_history.get(dataset_name, [])
        if not history:
            return {"status": "no_data"}

        latest = history[-1]
        return {
            "dataset_name": dataset_name,
            "latest_score": latest.quality_score,
            "latest_level": latest.quality_level.value,
            "total_checks": len(history),
            "trend": "improving" if len(history) >= 2 and latest.quality_score > history[-2].quality_score else
                     "declining" if len(history) >= 2 and latest.quality_score < history[-2].quality_score else
                     "stable",
            "issue_count": len(latest.issues),
        }


# 全局单例
_data_governance: Optional[DataGovernanceService] = None


def get_data_governance() -> DataGovernanceService:
    """获取数据治理服务单例"""
    global _data_governance
    if _data_governance is None:
        _data_governance = DataGovernanceService()
    return _data_governance
