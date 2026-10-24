# -*- coding: utf-8 -*-
"""core/audit/fault_catcher.py —— 故障自动捕获与知识沉淀。

基于第一性原理：
    每次报错都是一次学习机会。
    如果报错只留在日志里，下次还会犯同样的错。
    自动捕获 = 把故障现象、根因、解决方案沉淀成知识库。
"""
from __future__ import annotations

import logging
import traceback
from typing import Optional

from .db_writer import write_fault_knowledge_to_db

logger = logging.getLogger("core.audit.fault")


# ------------------------------------------------------------------
# 故障分类映射
# ------------------------------------------------------------------
FAULT_CATEGORY_MAP = {
    "connection": "连接问题",
    "timeout": "超时",
    "permission": "权限问题",
    "data": "数据问题",
    "order": "下单问题",
    "risk": "风控问题",
    "config": "配置问题",
    "system": "系统问题",
}


# ------------------------------------------------------------------
# 核心故障捕获器
# ------------------------------------------------------------------
class FaultCatcher:
    """故障自动捕获器。

    用法：
        catcher = FaultCatcher()
        try:
            do_something()
        except Exception as e:
            catcher.capture(
                symptom="下单失败",
                exception=e,
                context={"symbol": "XAUUSD", "side": "buy"},
            )
    """

    def capture(self,
                symptom: str,
                exception: Exception,
                context: Optional[dict] = None,
                solution: str = "待分析",
                category: str = "system") -> Optional[int]:
        """捕获一次故障，自动写入知识库。

        Args:
            symptom: 故障现象描述
            exception: 异常对象
            context: 上下文信息（发生时的参数、状态等）
            solution: 初步解决方案（如果知道的话）
            category: 故障分类

        Returns:
            知识库记录ID，失败返回None
        """
        try:
            error_type = type(exception).__name__
            error_msg = str(exception)
            traceback_str = traceback.format_exc()

            # 智能分类
            auto_category = self._classify_error(error_type, error_msg)

            # 记录到日志
            logger.warning("fault captured: %s | %s: %s", symptom, error_type, error_msg)

            # 写入故障知识库
            record_id = write_fault_knowledge_to_db(
                title=f"{symptom}: {error_type}",
                symptom=f"{symptom}\n\n错误信息: {error_msg}\n\n上下文: {context or {}}",
                root_cause=f"错误类型: {error_type}\n\n堆栈:\n{traceback_str[:1000]}",
                solution=solution,
                category=auto_category,
                severity="P2",
            )

            if record_id:
                print(f"⚠️  故障已记录: {symptom}")
                print(f"   知识库ID={record_id}，待分析根因和解决方案。")

            return record_id

        except Exception as e:
            logger.warning("failed to capture fault: %s", e)
            return None

    def _classify_error(self, error_type: str, error_msg: str) -> str:
        """根据错误类型和信息自动分类。"""
        error_lower = error_msg.lower()

        if "connection" in error_lower or "connect" in error_lower:
            return "连接问题"
        if "timeout" in error_lower or "timed out" in error_lower:
            return "超时"
        if "permission" in error_lower or "denied" in error_lower:
            return "权限问题"
        if "data" in error_lower or "empty" in error_lower or "missing" in error_lower:
            return "数据问题"
        if "order" in error_lower or "trade" in error_lower:
            return "下单问题"
        if "risk" in error_lower or "margin" in error_lower:
            return "风控问题"
        if "config" in error_lower or "setting" in error_lower:
            return "配置问题"

        return "系统问题"


# ------------------------------------------------------------------
# 单例模式
# ------------------------------------------------------------------
_fault_catcher_instance: Optional[FaultCatcher] = None


def get_fault_catcher() -> FaultCatcher:
    """获取全局故障捕获器单例。"""
    global _fault_catcher_instance
    if _fault_catcher_instance is None:
        _fault_catcher_instance = FaultCatcher()
    return _fault_catcher_instance


# ------------------------------------------------------------------
# 装饰器用法（可选）
# ------------------------------------------------------------------
def auto_capture_fault(symptom: str, category: str = "system"):
    """装饰器：自动捕获函数执行中的异常。

    用法：
        @auto_capture_fault("下单失败")
        def place_order(symbol, side, quantity):
            ...
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                catcher = get_fault_catcher()
                catcher.capture(
                    symptom=symptom,
                    exception=e,
                    context={"args": args, "kwargs": kwargs},
                    category=category,
                )
                raise  # 仍然抛出异常，不吞掉
        return wrapper
    return decorator
