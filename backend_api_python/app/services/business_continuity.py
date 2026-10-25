"""
高可用与灾备体系

第一性原理：
- 实盘系统最怕的不是亏钱，是亏了你不知道，或者想跑跑不掉
- 交易所API挂了、网络断了、服务器宕机——这些事一定会发生
- 没有灾备的系统，就像没有安全带的赛车

全球顶级机构实践：
- Citadel：双活数据中心，RTO < 1分钟
- Jane Street：每个组件都有备份，故障自动切换
- Renaissance：监控系统比交易系统还大

核心指标：
- RTO (Recovery Time Objective)：故障后多久恢复
- RPO (Recovery Point Objective)：最多丢多少数据
- 可用性目标：99.99% = 全年 downtime < 53分钟
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)


class HealthStatus(Enum):
    """健康状态"""
    HEALTHY = "healthy"           # 正常
    DEGRADED = "degraded"         # 降级运行
    UNHEALTHY = "unhealthy"       # 故障
    UNKNOWN = "unknown"           # 未知


class FailureLevel(Enum):
    """故障等级"""
    P0_CRITICAL = "p0"            # 致命：交易系统完全不可用
    P1_MAJOR = "p1"               # 严重：核心功能受损
    P2_MINOR = "p2"               # 次要：非核心功能问题
    P3_INFO = "p3"                # 信息：不影响业务


@dataclass
class ServiceHealth:
    """服务健康状态"""
    service_name: str
    status: HealthStatus = HealthStatus.UNKNOWN
    last_check: Optional[datetime] = None
    response_time_ms: float = 0.0
    error_message: str = ""
    failover_count: int = 0


@dataclass
class FailureEvent:
    """故障事件"""
    event_id: str
    timestamp: datetime
    level: FailureLevel
    service: str
    description: str
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    resolution_time_sec: float = 0.0
    impact_description: str = ""


@dataclass
class DisasterRecoveryConfig:
    """灾备配置"""
    # RTO/RPO目标
    rto_minutes: float = 5.0       # 恢复时间目标
    rpo_minutes: float = 1.0       # 恢复点目标

    # 监控配置
    health_check_interval_sec: float = 10.0
    failure_threshold: int = 3      # 连续几次失败判定故障
    auto_failover: bool = True      # 是否自动切换

    # 备份配置
    backup_interval_hours: float = 6.0
    backup_retention_days: int = 30


class BusinessContinuityService:
    """
    业务连续性与灾备服务

    核心功能：
    1. 服务健康监控
    2. 故障自动检测和告警
    3. 自动故障切换
    4. 备份恢复管理
    5. 故障事件记录和复盘
    """

    def __init__(self, config: Optional[DisasterRecoveryConfig] = None):
        self.config = config or DisasterRecoveryConfig()
        self.services: Dict[str, ServiceHealth] = {}
        self.failure_events: List[FailureEvent] = []
        self.lock = threading.RLock()

        # 监控状态
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None

        # 回调
        self._failure_callback: Optional[Callable[[FailureEvent], None]] = None
        self._failover_callback: Optional[Callable[[str], None]] = None

        # 统计
        self.total_failures = 0
        self.total_failovers = 0
        self.avg_resolution_time_sec = 0.0

    def register_service(self, service_name: str):
        """注册需要监控的服务"""
        with self.lock:
            self.services[service_name] = ServiceHealth(service_name=service_name)
            logger.info(f"服务注册监控: {service_name}")

    def set_failure_callback(self, callback: Callable[[FailureEvent], None]):
        """设置故障告警回调"""
        self._failure_callback = callback

    def set_failover_callback(self, callback: Callable[[str], None]):
        """设置故障切换回调"""
        self._failover_callback = callback

    def report_health(self, service_name: str, status: HealthStatus,
                      response_time_ms: float = 0.0, error_message: str = ""):
        """上报服务健康状态"""
        with self.lock:
            if service_name not in self.services:
                self.register_service(service_name)

            service = self.services[service_name]
            old_status = service.status

            service.status = status
            service.last_check = datetime.now(timezone.utc)
            service.response_time_ms = response_time_ms
            service.error_message = error_message

            # 状态变化时触发告警
            if old_status != status:
                self._handle_status_change(service, old_status, status)

    def _handle_status_change(self, service: ServiceHealth,
                              old_status: HealthStatus, new_status: HealthStatus):
        """处理状态变化"""
        if new_status == HealthStatus.UNHEALTHY:
            # 服务故障
            event = FailureEvent(
                event_id=f"fail_{int(time.time() * 1000)}",
                timestamp=datetime.now(timezone.utc),
                level=FailureLevel.P1_MAJOR,
                service=service.service_name,
                description=f"服务故障: {service.error_message}",
                impact_description=f"{service.service_name} 不可用，可能影响交易执行",
            )
            self.failure_events.append(event)
            self.total_failures += 1

            logger.error(f"🔴 服务故障 [{service.service_name}]: {service.error_message}")

            if self._failure_callback:
                try:
                    self._failure_callback(event)
                except Exception as e:
                    logger.error(f"故障告警回调失败: {e}")

            # 自动故障切换
            if self.config.auto_failover:
                self._trigger_failover(service.service_name)

        elif new_status == HealthStatus.HEALTHY and old_status == HealthStatus.UNHEALTHY:
            # 服务恢复
            logger.info(f"🟢 服务恢复: {service.service_name}")

    def _trigger_failover(self, service_name: str):
        """触发故障切换"""
        logger.warning(f"🔄 触发故障切换: {service_name}")

        if service_name in self.services:
            self.services[service_name].failover_count += 1
            self.total_failovers += 1

        if self._failover_callback:
            try:
                self._failover_callback(service_name)
            except Exception as e:
                logger.error(f"故障切换回调失败: {e}")

    def get_system_health_summary(self) -> Dict[str, Any]:
        """获取系统健康总览"""
        with self.lock:
            total = len(self.services)
            healthy = sum(1 for s in self.services.values() if s.status == HealthStatus.HEALTHY)
            degraded = sum(1 for s in self.services.values() if s.status == HealthStatus.DEGRADED)
            unhealthy = sum(1 for s in self.services.values() if s.status == HealthStatus.UNHEALTHY)

            overall_status = HealthStatus.HEALTHY
            if unhealthy > 0:
                overall_status = HealthStatus.UNHEALTHY
            elif degraded > 0:
                overall_status = HealthStatus.DEGRADED

            return {
                "overall_status": overall_status.value,
                "total_services": total,
                "healthy": healthy,
                "degraded": degraded,
                "unhealthy": unhealthy,
                "availability_pct": healthy / total * 100 if total > 0 else 0,
                "rto_target_min": self.config.rto_minutes,
                "rpo_target_min": self.config.rpo_minutes,
                "total_failures": self.total_failures,
                "total_failovers": self.total_failovers,
                "services": [
                    {
                        "name": s.service_name,
                        "status": s.status.value,
                        "response_time_ms": s.response_time_ms,
                        "failover_count": s.failover_count,
                    }
                    for s in self.services.values()
                ],
            }

    def get_failure_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取故障历史"""
        with self.lock:
            events = self.failure_events[-limit:]
            return [
                {
                    "event_id": e.event_id,
                    "timestamp": e.timestamp.isoformat(),
                    "level": e.level.value,
                    "service": e.service,
                    "description": e.description,
                    "resolved": e.resolved,
                }
                for e in events
            ]


# 全局单例
_bc_service: Optional[BusinessContinuityService] = None


def get_business_continuity() -> BusinessContinuityService:
    """获取业务连续性服务单例"""
    global _bc_service
    if _bc_service is None:
        _bc_service = BusinessContinuityService()
    return _bc_service
