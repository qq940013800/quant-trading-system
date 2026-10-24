"""
策略源代码加载器 - 统一数据模型版本
基于第一性原理和全球最佳实践优化
"""
from typing import Any


class StrategySourceError(Exception):
    """策略源代码关联错误"""
    def __init__(
        self,
        message: str,
        missing_fields: list[str] = None,
        fix_hint: str = None,
        error_code: str = "strategyV2.sourceError"
    ):
        self.message = message
        self.missing_fields = missing_fields or []
        self.fix_hint = fix_hint
        self.error_code = error_code
        super().__init__(self.format_error())

    def format_error(self) -> str:
        lines = [f"[{self.error_code}] {self.message}"]
        if self.missing_fields:
            lines.append("缺少的字段：")
            for f in self.missing_fields:
                lines.append(f"  - {f}")
        if self.fix_hint:
            lines.append(f"修复建议：{self.fix_hint}")
        return "\n".join(lines)


def _load_source_unified(strategy: dict[str, Any]) -> tuple[int, int, str]:
    """
    统一的策略源代码加载器

    数据模型原则：
    1. source_version_id 是单一事实来源（新方式）
    2. trading_config.script_source_id 是向后兼容的冗余字段（旧方式）
    3. 优先使用新方式，自动同步到旧方式

    Returns:
        (source_id, source_version_id, code)
    """
    from app.services.script_source import get_script_source_service

    trading_config = _json_object(strategy.get("trading_config") or {})
    user_id = int(strategy.get("user_id") or 0)

    # ==========================================
    # 第一步：优先从 source_version_id 获取（新方式）
    # ==========================================
    source_version_id = int(strategy.get("source_version_id") or 0)

    if source_version_id > 0:
        # 从 source_version 表反查 source_id
        source_version = get_script_source_service().get_version(
            source_version_id,
            user_id=user_id
        )

        if source_version:
            source_id = int(source_version.get("source_id") or 0)
            code = str(source_version.get("code") or "").strip()

            # 自动同步到 trading_config（向后兼容）
            if trading_config.get("script_source_id") != source_id:
                trading_config["script_source_id"] = source_id
            if trading_config.get("script_source_version_id") != source_version_id:
                trading_config["script_source_version_id"] = source_version_id

            if not code:
                raise StrategySourceError(
                    message="策略源代码版本存在，但代码为空",
                    missing_fields=[f"qd_script_source_versions.code (version_id={source_version_id})"],
                    fix_hint="请编辑策略源代码并保存",
                    error_code="strategyV2.codeRequired"
                )

            return source_id, source_version_id, code

    # ==========================================
    # 第二步：兼容旧方式（从 trading_config 读取）
    # ==========================================
    source_id = int(trading_config.get("script_source_id") or 0)
    source_version_id = int(trading_config.get("script_source_version_id") or 0)

    if source_id > 0 and source_version_id > 0:
        # 验证版本存在
        source_version = get_script_source_service().get_version(
            source_version_id,
            user_id=user_id
        )

        if source_version:
            code = str(source_version.get("code") or "").strip()

            # 自动同步到 source_version_id 字段（新方式）
            strategy["source_version_id"] = source_version_id

            if not code:
                raise StrategySourceError(
                    message="策略源代码版本存在，但代码为空",
                    missing_fields=[f"qd_script_source_versions.code (version_id={source_version_id})"],
                    fix_hint="请编辑策略源代码并保存",
                    error_code="strategyV2.codeRequired"
                )

            return source_id, source_version_id, code

    # ==========================================
    # 第三步：都没有，抛出明确错误
    # ==========================================
    missing = []
    if source_version_id <= 0:
        missing.append("qd_strategies_trading.source_version_id")
    if source_id <= 0:
        missing.append("trading_config.script_source_id")
    if source_version_id <= 0:
        missing.append("trading_config.script_source_version_id")

    raise StrategySourceError(
        message="策略缺少源代码关联信息，无法启动",
        missing_fields=missing,
        fix_hint="创建策略时请通过正确的接口自动关联源代码，或手动设置上述字段",
        error_code="strategyV2.sourceRequired"
    )


def _json_object(value: Any) -> dict:
    """安全解析 JSON 对象"""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        import json
        try:
            return json.loads(value) if value else {}
        except:
            return {}
    return {}
