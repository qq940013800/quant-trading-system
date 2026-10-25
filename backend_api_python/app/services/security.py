"""
安全与合规体系

第一性原理：
- 一次安全事件，可能血本无归
- API密钥泄露、账户被黑、交易记录篡改——这些事一旦发生就是大事
- 安全不是事后补的，是系统设计的一部分

全球顶级机构实践：
- Citadel：军事级安全，每个系统都有安全审计
- Jane Street：最小权限原则，每个API密钥只能做特定操作
- Renaissance：安全团队比交易团队还大

安全威胁模型：
1. 认证安全 —— 谁能访问系统？
2. 授权安全 —— 能做什么操作？
3. 数据安全 —— 敏感数据会不会泄露？
4. 操作安全 —— 会不会误操作？
5. 审计安全 —— 出了事能不能追溯？
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from app.utils.logger import get_logger

logger = get_logger(__name__)


class SecurityLevel(Enum):
    """安全等级"""
    PUBLIC = "public"           # 公开信息
    INTERNAL = "internal"       # 内部信息
    CONFIDENTIAL = "confidential" # 机密信息
    RESTRICTED = "restricted"   # 绝密信息（API密钥等）


class AlertLevel(Enum):
    """告警等级"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class SecurityAlert:
    """安全告警"""
    alert_id: str
    timestamp: datetime
    level: AlertLevel
    category: str  # auth / permission / data / operation / audit
    message: str
    source_ip: str = ""
    user_id: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UserSession:
    """用户会话"""
    session_id: str
    user_id: str
    created_at: datetime
    expires_at: datetime
    ip_address: str = ""
    user_agent: str = ""
    permissions: Set[str] = field(default_factory=set)


@dataclass
class APIKey:
    """API密钥"""
    key_id: str
    name: str
    exchange: str
    permissions: Set[str] = field(default_factory=set)  # read / trade / withdraw
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_used: Optional[datetime] = None
    is_active: bool = True


class SecurityService:
    """
    安全与合规服务

    核心功能：
    1. 认证与会话管理
    2. 权限控制（RBAC）
    3. API密钥安全管理
    4. 操作审计日志
    5. 安全告警与异常检测
    """

    def __init__(self):
        self.sessions: Dict[str, UserSession] = {}
        self.api_keys: Dict[str, APIKey] = {}
        self.audit_logs: List[Dict[str, Any]] = []
        self.alerts: List[SecurityAlert] = []

        # 安全配置
        self.session_timeout_minutes = 60
        self.max_failed_logins = 5
        self.failed_login_attempts: Dict[str, int] = {}

        # 回调
        self._alert_callbacks: List[Callable[[SecurityAlert], None]] = []

    # ========== 认证管理 ==========

    def create_session(self, user_id: str, ip_address: str = "",
                       user_agent: str = "") -> UserSession:
        """创建用户会话"""
        session_id = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)

        session = UserSession(
            session_id=session_id,
            user_id=user_id,
            created_at=now,
            expires_at=now + timedelta(minutes=self.session_timeout_minutes),
            ip_address=ip_address,
            user_agent=user_agent,
            permissions={"read_dashboard", "view_positions"},  # 默认权限
        )

        self.sessions[session_id] = session
        self._audit("login", user_id, {"ip": ip_address})

        logger.info(f"用户登录: {user_id} session={session_id[:8]}...")
        return session

    def validate_session(self, session_id: str) -> Optional[UserSession]:
        """验证会话是否有效"""
        session = self.sessions.get(session_id)
        if not session:
            return None

        if datetime.now(timezone.utc) > session.expires_at:
            del self.sessions[session_id]
            return None

        return session

    def revoke_session(self, session_id: str):
        """注销会话"""
        if session_id in self.sessions:
            user_id = self.sessions[session_id].user_id
            del self.sessions[session_id]
            self._audit("logout", user_id, {})
            logger.info(f"用户注销: {user_id}")

    # ========== 权限控制 ==========

    def check_permission(self, session_id: str, required_permission: str) -> bool:
        """检查用户是否有某个权限"""
        session = self.validate_session(session_id)
        if not session:
            return False

        has_permission = required_permission in session.permission

        if not has_permission:
            self._create_alert(
                level=AlertLevel.WARNING,
                category="permission",
                message=f"权限不足: 用户{session.user_id}尝试访问{required_permission}",
                user_id=session.user_id,
            )

        return has_permission

    def grant_permission(self, session_id: str, permission: str):
        """授予权限"""
        session = self.sessions.get(session_id)
        if session:
            session.permissions.add(permission)
            self._audit("permission_grant", session.user_id, {"permission": permission})

    # ========== API密钥管理 ==========

    def register_api_key(self, name: str, exchange: str,
                         permissions: Set[str]) -> APIKey:
        """注册API密钥"""
        key_id = secrets.token_urlsafe(16)

        api_key = APIKey(
            key_id=key_id,
            name=name,
            exchange=exchange,
            permissions=permissions,
        )

        self.api_keys[key_id] = api_key
        self._audit("api_key_created", "system", {"name": name, "exchange": exchange})

        logger.info(f"API密钥创建: {name} ({exchange})")
        return api_key

    def validate_api_key(self, key_id: str, required_permission: str) -> bool:
        """验证API密钥权限"""
        api_key = self.api_keys.get(key_id)
        if not api_key or not api_key.is_active:
            return False

        if required_permission not in api_key.permissions:
            self._create_alert(
                level=AlertLevel.CRITICAL,
                category="auth",
                message=f"API密钥权限不足: {api_key.name}尝试{required_permission}",
            )
            return False

        api_key.last_used = datetime.now(timezone.utc)
        return True

    # ========== 审计日志 ==========

    def _audit(self, action: str, user_id: str, details: Dict[str, Any]):
        """记录审计日志"""
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "user_id": user_id,
            "details": details,
        }
        self.audit_logs.append(log_entry)

        # 只保留最近1000条
        if len(self.audit_logs) > 1000:
            self.audit_logs = self.audit_logs[-1000:]

    def log_operation(self, session_id: str, action: str, details: Dict[str, Any]):
        """记录用户操作"""
        session = self.sessions.get(session_id)
        user_id = session.user_id if session else "unknown"
        self._audit(action, user_id, details)

    # ========== 安全告警 ==========

    def _create_alert(self, level: AlertLevel, category: str,
                      message: str, user_id: str = "",
                      details: Optional[Dict[str, Any]] = None):
        """创建安全告警"""
        alert = SecurityAlert(
            alert_id=f"sec_{int(datetime.now(timezone.utc).timestamp() * 1000)}",
            timestamp=datetime.now(timezone.utc),
            level=level,
            category=category,
            message=message,
            user_id=user_id,
            details=details or {},
        )

        self.alerts.append(alert)

        log_level = 40 if level == AlertLevel.CRITICAL else 30 if level == AlertLevel.WARNING else 20
        logger.log(log_level, f"安全告警 [{level.value}] {category}: {message}")

        for callback in self._alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"安全告警回调失败: {e}")

    def add_alert_callback(self, callback: Callable[[SecurityAlert], None]):
        """添加告警回调"""
        self._alert_callbacks.append(callback)

    # ========== 状态查询 ==========

    def get_security_summary(self) -> Dict[str, Any]:
        """获取安全状态总览"""
        active_sessions = sum(
            1 for s in self.sessions.values()
            if datetime.now(timezone.utc) < s.expires_at
        )

        active_keys = sum(1 for k in self.api_keys.values() if k.is_active)

        critical_alerts = sum(1 for a in self.alerts if a.level == AlertLevel.CRITICAL)

        return {
            "active_sessions": active_sessions,
            "active_api_keys": active_keys,
            "total_audit_logs": len(self.audit_logs),
            "critical_alerts": critical_alerts,
            "security_level": "good" if critical_alerts == 0 else
                              "warning" if critical_alerts < 3 else
                              "critical",
        }

    def get_recent_alerts(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取最近的安全告警"""
        return [
            {
                "alert_id": a.alert_id,
                "timestamp": a.timestamp.isoformat(),
                "level": a.level.value,
                "category": a.category,
                "message": a.message,
            }
            for a in self.alerts[-limit:]
        ]


# 全局单例
_security_service: Optional[SecurityService] = None


def get_security_service() -> SecurityService:
    """获取安全服务单例"""
    global _security_service
    if _security_service is None:
        _security_service = SecurityService()
    return _security_service
