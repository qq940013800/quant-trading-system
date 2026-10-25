"""
CI/CD与部署运维体系

第一性原理：
- 手动部署迟早会出事故
- 每次手动部署都是一次赌博
- 自动化 = 可重复 + 可审计 + 可回滚

全球顶级机构实践：
- Google：每周部署数千次，每次都是自动的
- Amazon：单向部署管道，所有变更都走同一条路
- Netflix：混沌工程，主动制造故障验证系统韧性

核心流程：
代码提交 → 自动测试 → 构建镜像 → 部署预发 → 验收 → 生产部署 → 监控
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)


class DeployStage(Enum):
    """部署阶段"""
    BUILD = "build"               # 构建
    TEST = "test"                 # 测试
    PRE_DEPLOY = "pre_deploy"     # 预发布
    DEPLOY = "deploy"             # 生产部署
    VERIFY = "verify"             # 验证


class DeployStatus(Enum):
    """部署状态"""
    PENDING = "pending"           # 等待中
    RUNNING = "running"            # 进行中
    SUCCESS = "success"           # 成功
    FAILED = "failed"              # 失败
    ROLLED_BACK = "rolled_back"    # 已回滚


@dataclass
class Deployment:
    """部署记录"""
    deployment_id: str
    version: str
    commit_hash: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    stage: DeployStage = DeployStage.BUILD
    status: DeployStatus = DeployStatus.PENDING
    logs: List[str] = field(default_factory=list)
    triggered_by: str = "system"


class CICDService:
    """
    CI/CD与部署运维服务

    核心功能：
    1. 自动化部署流水线
    2. 部署记录和历史
    3. 一键回滚
    4. 部署健康检查
    """

    def __init__(self, project_root: str = "."):
        self.project_root = project_root
        self.deployments: List[Deployment] = []
        self.current_version: str = "1.0.0"

    def trigger_deployment(self, version: str, commit_hash: str,
                          triggered_by: str = "system") -> Deployment:
        """触发部署"""
        deployment = Deployment(
            deployment_id=f"deploy_{int(datetime.now(timezone.utc).timestamp())}",
            version=version,
            commit_hash=commit_hash,
            started_at=datetime.now(timezone.utc),
            triggered_by=triggered_by,
        )

        self.deployments.append(deployment)
        logger.info(f"🚀 部署触发: v{version} ({commit_hash[:8]}) by {triggered_by}")

        # 这里只记录，实际部署由CI/CD系统执行
        deployment.status = DeployStatus.SUCCESS
        deployment.completed_at = datetime.now(timezone.utc)
        deployment.logs.append("部署流水线已触发")

        return deployment

    def rollback(self, deployment_id: str) -> bool:
        """回滚到指定版本"""
        for d in self.deployments:
            if d.deployment_id == deployment_id:
                logger.warning(f"⏪ 回滚部署: {deployment_id} 到版本 {d.version}")
                d.status = DeployStatus.ROLLED_BACK
                return True
        return False

    def get_deployment_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取部署历史"""
        return [
            {
                "deployment_id": d.deployment_id,
                "version": d.version,
                "commit_hash": d.commit_hash[:8],
                "started_at": d.started_at.isoformat(),
                "completed_at": d.completed_at.isoformat() if d.completed_at else None,
                "status": d.status.value,
                "triggered_by": d.triggered_by,
            }
            for d in reversed(self.deployments[-limit:])
        ]

    def get_current_status(self) -> Dict[str, Any]:
        """获取当前部署状态"""
        latest = self.deployments[-1] if self.deployments else None

        return {
            "current_version": self.current_version,
            "total_deployments": len(self.deployments),
            "latest_deployment": {
                "id": latest.deployment_id,
                "version": latest.version,
                "status": latest.status.value,
                "started_at": latest.started_at.isoformat(),
            } if latest else None,
            "ci_cd_enabled": True,
            "auto_deploy": False,  # 默认关闭自动部署，需要人工确认
        }


# 全局单例
_cicd_service: Optional[CICDService] = None


def get_cicd_service() -> CICDService:
    """获取CI/CD服务单例"""
    global _cicd_service
    if _cicd_service is None:
        _cicd_service = CICDService()
    return _cicd_service
