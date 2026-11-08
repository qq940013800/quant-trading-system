# -*- coding: utf-8 -*-
"""core.control.approval_gate —— 危险动作审批闸纯判定（fail-closed）。

第一性原理：
    工具注册表只描述"风险等级"，真正的放行/拒绝必须在执行边界由可执行判定
    强制。元数据里的 safety 文案不能替代闸口；未显式确认、权限不足或实盘条件
    不满足的危险动作一律拒绝。

本模块只做纯判定，不读库、不触网、不发回调：
    - 权限是否具备（scope_granted）、实盘开关是否满足（live_conditions_met）、
      是否模拟单（is_paper）都由适配器在调用前取数注入；
    - 审批结果与输入写入 audit，便于事后还原"为什么放行/拒绝"。

风险等级（对齐 ``app.services.ai_tool_registry`` 的 ``risk_level``）：
    - ``read``：只读，自动放行；
    - ``write_draft``：草稿/源码/指标草稿，不改运行时与资金，可回滚，放行；
    - ``write_config``：自选/告警/配置变更，需显式确认；
    - ``runtime_control``：停策略、紧急停等运行时控制，需确认 + 权限；
    - ``trading``：下单，需确认 + 权限；实盘还需 live 条件，模拟单豁免 live 条件。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

READ = "read"
WRITE_DRAFT = "write_draft"
WRITE_CONFIG = "write_config"
RUNTIME_CONTROL = "runtime_control"
TRADING = "trading"

_KNOWN_LEVELS = {READ, WRITE_DRAFT, WRITE_CONFIG, RUNTIME_CONTROL, TRADING}
_CONFIRMATION_REQUIRED = {WRITE_CONFIG, RUNTIME_CONTROL, TRADING}


@dataclass(frozen=True)
class ApprovalResult:
    """审批判定结果（纯结果，含审计字段）。"""

    allowed: bool
    reason_code: str
    audit: dict[str, Any]


def evaluate_approval(
    *,
    risk_level: str,
    read_only: bool = False,
    confirmed: bool = False,
    scope_granted: bool = True,
    live_conditions_met: bool = True,
    is_paper: bool = True,
) -> ApprovalResult:
    """按风险等级判定动作是否可执行；失败关闭，无默认放行。

    参数:
        risk_level: 注册表风险等级（read/write_draft/write_config/runtime_control/trading）。
        read_only: 注册表 ``read_only`` 标志；为真时按只读放行。
        confirmed: 调用方是否已取得显式确认（对应 body 中 ``confirm_* is True``）。
        scope_granted: 所需权限范围是否已具备（适配器按 token scope 判定）。
        live_conditions_met: 实盘条件是否满足（非 paper token + 服务器实盘开关等）。
        is_paper: 是否模拟/草稿单；仅在 trading 等级下豁免 live 条件。

    reason_code:
        ``read_only_allowed / draft_allowed / approved`` 为放行；
        ``unknown_risk_level / scope_required / confirmation_required /
        live_conditions_required`` 为拒绝。
    """
    level = str(risk_level or READ).strip().lower()
    audit: dict[str, Any] = {
        "risk_level": level,
        "read_only": bool(read_only),
        "confirmed": bool(confirmed),
        "scope_granted": bool(scope_granted),
        "live_conditions_met": bool(live_conditions_met),
        "is_paper": bool(is_paper),
    }

    if read_only or level == READ:
        return ApprovalResult(True, "read_only_allowed", audit)

    if level not in _KNOWN_LEVELS:
        return ApprovalResult(False, "unknown_risk_level", audit)

    if level == WRITE_DRAFT:
        return ApprovalResult(True, "draft_allowed", audit)

    if not scope_granted:
        return ApprovalResult(False, "scope_required", audit)

    if level in _CONFIRMATION_REQUIRED and not confirmed:
        return ApprovalResult(False, "confirmation_required", audit)

    if level == TRADING and not is_paper and not live_conditions_met:
        return ApprovalResult(False, "live_conditions_required", audit)

    return ApprovalResult(True, "approved", audit)
