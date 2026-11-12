# -*- coding: utf-8 -*-
"""core.experiment.retirement_arbitration —— 退役联合裁决纯编排接缝。

两条既有退役裁决线在此合并（纯函数，不读 DB / 不下单 / 不写库）：

1. **健康分阈值线**（registry 侧）：外部合成的健康分 ``health_score``（∈ [0,1]，
   越高越健康）低于 ``health_threshold`` 即硬退役；健康分落在观察带
   ``[threshold, warn_line)`` 记 watch。健康分由上游按 CLEAN 分布与蓝图准则计算
   后传入，本模块不自行从绩效快照合成，也不反推阈值。
2. **生命周期建议线**（lifecycle 侧）：``recommend_retirement`` 产出的
   ``keep / watch / retire`` 建议与原因码，经鸭子类型解耦传入。

合并规则（优先级从高到低）：
- ``retire``：健康分低于硬阈值，**或** 生命周期建议为 retire（硬 breach）。
- ``watch``：健康分落在观察带，**或** 生命周期建议为 watch。
- ``keep``：其余。

退役动作（状态机迁移 + 审计日志）仍由编排层调用
``StrategyRegistry.retire_if_health_below`` 落地；本模块只产出裁决结论与留痕，
不触碰注册表、不持有资金。

阈值（硬阈值 / 观察带上界）全部由调用方注入；模块内不写死业务默认值。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence


# 健康分线退役原因码（生命周期原因码由上游透传，不在此重复定义）
RETIRE_LOW_HEALTH = "retire_low_health"
WATCH_LOW_HEALTH = "watch_low_health"

DECISION_KEEP = "keep"
DECISION_WATCH = "watch"
DECISION_RETIRE = "retire"
_VALID_DECISIONS = (DECISION_KEEP, DECISION_WATCH, DECISION_RETIRE)


def _unit(name: str, val: object) -> float:
    if isinstance(val, bool) or not isinstance(val, (int, float)) \
            or not math.isfinite(float(val)):
        raise ValueError(f"{name} 必须为有限数值，收到 {val!r}")
    v = float(val)
    if not (0.0 <= v <= 1.0):
        raise ValueError(f"{name} 必须位于 [0,1] 内，收到 {val!r}")
    return v


def _dedup_preserve_order(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item is None:
            continue
        code = str(item).strip()
        if code and code not in seen:
            seen.add(code)
            out.append(code)
    return out


@dataclass(frozen=True)
class RetirementArbitration:
    """退役联合裁决（纯数据，供编排层落状态机 / 触发通知）。"""

    decision: str
    reasons: list[str] = field(default_factory=list)
    health_score: float = 0.0
    health_threshold: float = 0.0
    health_warn_line: Optional[float] = None
    lifecycle_recommendation: Optional[str] = None
    flags: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "reasons": list(self.reasons),
            "health_score": self.health_score,
            "health_threshold": self.health_threshold,
            "health_warn_line": self.health_warn_line,
            "lifecycle_recommendation": self.lifecycle_recommendation,
            "flags": dict(self.flags),
        }


def arbitrate_retirement(
    *,
    health_score: float,
    health_threshold: float,
    lifecycle_recommendation: Optional[str] = None,
    lifecycle_reasons: Optional[Sequence[str]] = None,
    health_warn_line: Optional[float] = None,
) -> RetirementArbitration:
    """合并健康分阈值线与生命周期建议线，输出统一退役裁决。

    Args:
        health_score: 外部合成的健康分，∈ [0,1]，越高越健康。
        health_threshold: 硬退役阈值，∈ [0,1]；``score < threshold`` 触发 retire。
        lifecycle_recommendation: 生命周期建议 ``keep/watch/retire``；None 表示
            未接入生命周期线。
        lifecycle_reasons: 生命周期建议原因码序列，原样透传并去重保序。
        health_warn_line: 观察带上界，∈ [0,1] 且须 ≥ ``health_threshold``；
            None 表示不设观察带（健康分未触硬阈值即不算 watch）。

    Returns:
        :class:`RetirementArbitration` 裁决快照。
    """
    score = _unit("health_score", health_score)
    cutoff = _unit("health_threshold", health_threshold)

    warn_line: Optional[float] = None
    if health_warn_line is not None:
        warn_line = _unit("health_warn_line", health_warn_line)
        if warn_line < cutoff:
            raise ValueError(
                f"health_warn_line({warn_line}) 不得小于 health_threshold({cutoff})"
            )

    if lifecycle_recommendation is not None:
        rec = str(lifecycle_recommendation).strip().lower()
        if rec not in _VALID_DECISIONS:
            raise ValueError(
                f"未知生命周期建议 '{lifecycle_recommendation}'；"
                f"支持: {_VALID_DECISIONS}"
            )
    else:
        rec = None

    reasons: list[str] = []
    below_threshold = score < cutoff
    in_warn_band = bool(
        warn_line is not None and not below_threshold and score < warn_line
    )

    if below_threshold:
        reasons.append(RETIRE_LOW_HEALTH)
    elif in_warn_band:
        reasons.append(WATCH_LOW_HEALTH)

    lifecycle_codes = _dedup_preserve_order(
        lifecycle_reasons if lifecycle_reasons else []
    )
    reasons.extend(lifecycle_codes)

    if below_threshold or rec == DECISION_RETIRE:
        decision = DECISION_RETIRE
    elif in_warn_band or rec == DECISION_WATCH:
        decision = DECISION_WATCH
    else:
        decision = DECISION_KEEP

    flags: dict[str, float] = {
        "below_threshold": 1.0 if below_threshold else 0.0,
        "in_warn_band": 1.0 if in_warn_band else 0.0,
    }

    return RetirementArbitration(
        decision=decision,
        reasons=reasons,
        health_score=score,
        health_threshold=cutoff,
        health_warn_line=warn_line,
        lifecycle_recommendation=rec,
        flags=flags,
    )


__all__ = [
    "RETIRE_LOW_HEALTH",
    "WATCH_LOW_HEALTH",
    "DECISION_KEEP",
    "DECISION_WATCH",
    "DECISION_RETIRE",
    "RetirementArbitration",
    "arbitrate_retirement",
]
