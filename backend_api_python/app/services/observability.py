"""
可观测性与监控告警体系

第一性原理：
- 你不能改进你不能测量的东西
- 系统出问题了你得先知道，而且要比客户先知道
- 可观测性 = 指标 + 日志 + 链路追踪

全球顶级机构实践：
- Datadog/Grafana是行业标准
- 黄金四指标：延迟、流量、错误、饱和度
- 告警要可操作，不要狼来了

三大支柱：
1. 指标（Metrics）—— 量化数据，看趋势
2. 日志（Logs）—— 详细事件，排错用
3. 链路追踪（Traces）—— 请求路径，找瓶颈
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)


class AlertSeverity(Enum):
    """告警级别"""
    INFO = "info"            # 信息：通知即可
    WARNING = "warning"      # 警告：需要关注
    CRITICAL = "critical"    # 严重：需要立即处理
    EMERGENCY = "emergency"  # 紧急：必须马上响应


class MetricType(Enum):
    """指标类型"""
    COUNTER = "counter"      # 计数器：只增不减
    GAUGE = "gauge"          # 仪表盘：可增可减
    HISTOGRAM = "histogram"   # 直方图：分布统计


@dataclass
class Metric:
    """指标"""
    name: str
    value: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    labels: Dict[str, str] = field(default_factory=dict)
    metric_type: MetricType = MetricType.GAUGE


@dataclass
class Alert:
    """告警事件"""
    alert_id: str
    timestamp: datetime
    severity: AlertSeverity
    title: str
    message: str
    source: str
    resolved: bool = False
    resolved_at: Optional[datetime] = None


@dataclass
class AlertRule:
    """告警规则"""
    rule_id: str
    name: str
    metric_name: str
    condition: str  # >, <, ==
    threshold: float
    severity: AlertSeverity
    description: str = ""
    enabled: bool = True


class ObservabilityService:
    """
    可观测性服务

    核心功能：
    1. 指标收集和查询
    2. 告警规则配置和触发
    3. 黄金四指标监控
    4. 系统健康仪表盘
    """

    def __init__(self):
        self.metrics: Dict[str, List[Metric]] = {}
        self.alerts: List[Alert] = []
        self.alert_rules: Dict[str, AlertRule] = {}
        self._alert_callbacks: List[Callable[[Alert], None]] = []

        # 默认告警规则
        self._setup_default_rules()

    def _setup_default_rules(self):
        """设置默认告警规则"""
        default_rules = [
            AlertRule(
                rule_id="api_latency_high",
                name="API延迟过高",
                metric_name="api_request_duration",
                condition=">",
                threshold=1.0,  # 1秒
                severity=AlertSeverity.WARNING,
                description="API响应时间超过1秒",
            ),
            AlertRule(
                rule_id="error_rate_high",
                name="错误率过高",
                metric_name="error_rate",
                condition=">",
                threshold=0.05,  # 5%
                severity=AlertSeverity.CRITICAL,
                description="API错误率超过5%",
            ),
            AlertRule(
                rule_id="cpu_high",
                name="CPU使用率过高",
                metric_name="cpu_usage",
                condition=">",
                threshold=0.8,  # 80%
                severity=AlertSeverity.WARNING,
                description="CPU使用率超过80%",
            ),
            AlertRule(
                rule_id="memory_high",
                name="内存使用率过高",
                metric_name="memory_usage",
                condition=">",
                threshold=0.85,  # 85%
                severity=AlertSeverity.CRITICAL,
                description="内存使用率超过85%",
            ),
        ]

        for rule in default_rules:
            self.alert_rules[rule.rule_id] = rule

    def record_metric(self, name: str, value: float,
                      metric_type: MetricType = MetricType.GAUGE,
                      labels: Optional[Dict[str, str]] = None):
        """记录指标"""
        metric = Metric(
            name=name,
            value=value,
            metric_type=metric_type,
            labels=labels or {},
        )

        if name not in self.metrics:
            self.metrics[name] = []
        self.metrics[name].append(metric)

        # 只保留最近1000个数据点
        if len(self.metrics[name]) > 1000:
            self.metrics[name] = self.metrics[name][-1000:]

        # 检查告警规则
        self._check_alert_rules(name, value)

    def _check_alert_rules(self, metric_name: str, value: float):
        """检查是否触发告警规则"""
        for rule in self.alert_rules.values():
            if not rule.enabled:
                continue
            if rule.metric_name != metric_name:
                continue

            triggered = False
            if rule.condition == ">" and value > rule.threshold:
                triggered = True
            elif rule.condition == "<" and value < rule.threshold:
                triggered = True
            elif rule.condition == "==" and value == rule.threshold:
                triggered = True

            if triggered:
                self._trigger_alert(rule, value)

    def _trigger_alert(self, rule: AlertRule, current_value: float):
        """触发告警"""
        alert = Alert(
            alert_id=f"alert_{int(time.time() * 1000)}",
            timestamp=datetime.now(timezone.utc),
            severity=rule.severity,
            title=rule.name,
            message=f"{rule.description}，当前值: {current_value:.4f}，阈值: {rule.threshold}",
            source=rule.metric_name,
        )

        self.alerts.append(alert)

        log_level = 40 if rule.severity in (AlertSeverity.CRITICAL, AlertSeverity.EMERGENCY) else 30
        logger.log(log_level, f"🔔 告警 [{rule.severity.value}] {rule.name}: {rule.description}")

        for callback in self._alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"告警回调失败: {e}")

    def add_alert_callback(self, callback: Callable[[Alert], None]):
        """添加告警回调"""
        self._alert_callbacks.append(callback)

    def get_golden_signals(self) -> Dict[str, Any]:
        """获取黄金四指标（延迟、流量、错误、饱和度）"""
        return {
            "latency": {
                "p50": self._get_percentile("api_request_duration", 50),
                "p95": self._get_percentile("api_request_duration", 95),
                "p99": self._get_percentile("api_request_duration", 99),
            },
            "traffic": {
                "requests_per_minute": len(self.metrics.get("api_request_total", [])) if "api_request_total" in self.metrics else 0,
            },
            "errors": {
                "error_rate": self._get_latest("error_rate") or 0,
                "total_errors": len([
                    m for m in self.metrics.get("api_error_total", [])
                ]) if "api_error_total" in self.metrics else 0,
            },
            "saturation": {
                "cpu_usage": self._get_latest("cpu_usage") or 0,
                "memory_usage": self._get_latest("memory_usage") or 0,
            },
        }

    def _get_latest(self, metric_name: str) -> Optional[float]:
        """获取最新值"""
        if metric_name not in self.metrics or not self.metrics[metric_name]:
            return None
        return self.metrics[metric_name][-1].value

    def _get_percentile(self, metric_name: str, p: float) -> float:
        """获取百分位数"""
        if metric_name not in self.metrics or not self.metrics[metric_name]:
            return 0.0
        values = sorted([m.value for m in self.metrics[metric_name]])
        index = int(len(values) * p / 100)
        return values[min(index, len(values) - 1)]

    def get_recent_alerts(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取最近的告警"""
        return [
            {
                "alert_id": a.alert_id,
                "timestamp": a.timestamp.isoformat(),
                "severity": a.severity.value,
                "title": a.title,
                "message": a.message,
                "resolved": a.resolved,
            }
            for a in self.alerts[-limit:]
        ]

    def get_alert_summary(self) -> Dict[str, Any]:
        """获取告警汇总"""
        active = [a for a in self.alerts if not a.resolved]
        critical = [a for a in active if a.severity in (AlertSeverity.CRITICAL, AlertSeverity.EMERGENCY)]

        return {
            "total_alerts": len(self.alerts),
            "active_alerts": len(active),
            "critical_alerts": len(critical),
            "status": "critical" if len(critical) > 0 else
                      "warning" if len(active) > 0 else
                      "healthy",
        }


# 全局单例
_observability: Optional[ObservabilityService] = None


def get_observability() -> ObservabilityService:
    """获取可观测性服务单例"""
    global _observability
    if _observability is None:
        _observability = ObservabilityService()
    return _observability
