# -*- coding: utf-8 -*-
"""core.control.dual_review —— 双人复核独立批准人纯校验（fail-closed）。

第一性原理（对照机构对不可逆/高风险动作的 two-person rule）：
    最高风险动作不能由同一个人既提议又批准。复核有效性取决于"独立批准人的数量"，
    而不是审批记录上出现过多少行——同一人重复签字、空标识、大小写/空白伪装成不同
    人都必须被去重识别。本模块只做纯判定：批准人标识归一化、去重、计数并与注入的
    所需人数比较；不读库、不触网、不发回调。

边界与不变量：
- 纯函数：无 IO、无数据库、不下单；批准人标识由适配器在调用前取数注入。
- fail-closed：无批准人、单人、重复签字、人数不足一律拒绝；所需人数非法（<1）抛错暴露配置。
- 所需人数 required_count 由配置/调用方注入，模块内不写死业务复核等级。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence


@dataclass(frozen=True)
class DualReviewResult:
    """双人复核判定结果（纯结果，含审计字段）。"""

    allowed: bool
    reason_code: str
    audit: dict[str, Any]


def evaluate_dual_review(
    approvers: Sequence[Any],
    *,
    required_count: int = 2,
) -> DualReviewResult:
    """判定独立批准人是否达到所需复核人数。

    Args:
        approvers: 批准人标识序列（用户 ID/账号名）；None、空白字符串视为空标识剔除。
        required_count: 所需独立批准人数，必须为 ≥1 的整数；不接受 bool。

    Returns:
        ``DualReviewResult``：放行码 ``dual_review_passed``；拒绝码
        ``no_approvers / single_reviewer / insufficient_reviewers``。
        ``audit`` 记录 required_count、去重后 unique_count 与保留顺序的独立批准人列表。
    """
    if isinstance(required_count, bool) or not isinstance(required_count, int):
        raise ValueError(
            f"required_count 必须为整数，收到 {type(required_count).__name__}"
        )
    if required_count < 1:
        raise ValueError(f"required_count 必须 ≥1，收到 {required_count!r}")

    if isinstance(approvers, (str, bytes, dict)):
        raise ValueError(f"approvers 必须为标识序列，收到 {type(approvers).__name__}")

    try:
        raw = list(approvers)
    except TypeError as exc:
        raise ValueError(f"approvers 不可迭代: {exc!r}") from exc

    unique: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if item is None:
            continue
        ident = str(item).strip()
        if not ident or ident in seen:
            continue
        seen.add(ident)
        unique.append(ident)

    n = len(unique)
    audit: dict[str, Any] = {
        "required_count": required_count,
        "unique_count": n,
        "unique_approvers": unique,
    }

    if n == 0:
        return DualReviewResult(False, "no_approvers", audit)
    if n < required_count:
        reason = "single_reviewer" if n == 1 else "insufficient_reviewers"
        return DualReviewResult(False, reason, audit)
    return DualReviewResult(True, "dual_review_passed", audit)
