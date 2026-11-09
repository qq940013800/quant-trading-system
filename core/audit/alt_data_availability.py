# -*- coding: utf-8 -*-
"""core.audit.alt_data_availability —— 另类数据因果可得性纯判定底座。

蓝图 G13：另类数据（新闻/舆情/宏观/资金流等）入模前须通过因果可得性验证。
不变量①因果单向：决策时点只能使用当时已发布的特征，即
``published_at <= decision_time``（decision_time 取对应 bar.close）。

边界：
- 纯函数：不接数据源、不读库、不联网；记录由调用方注入。
- 只判定"在该决策时点是否可得"，不评估特征质量或预测力。
- 时间支持 ISO 字符串、epoch 数值或 datetime；naive 时间按 UTC 处理。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional


class AvailabilityError(Exception):
    """可得性校验异常，携带上下文（硬规则 9）。"""

    def __init__(self, detail: str, layer: str = "audit.alt_data_availability"):
        self.context = {"layer": layer, "detail": detail}
        super().__init__(f"AvailabilityError: {self.context}")


def _as_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_ts(name: str, val: object) -> datetime:
    if isinstance(val, datetime):
        return _as_aware(val)
    if isinstance(val, bool):
        raise AvailabilityError(f"{name} 时间戳不能为布尔值，收到 {val!r}")
    if isinstance(val, (int, float)):
        try:
            return datetime.fromtimestamp(float(val), tz=timezone.utc)
        except (OverflowError, OSError, ValueError) as exc:
            raise AvailabilityError(f"{name} epoch 无法解析: {val!r}") from exc
    if isinstance(val, str):
        s = val.strip()
        if not s:
            raise AvailabilityError(f"{name} 时间戳为空字符串")
        try:
            return _as_aware(datetime.fromisoformat(s.replace("Z", "+00:00")))
        except ValueError as exc:
            raise AvailabilityError(f"{name} ISO 时间无法解析: {val!r}") from exc
    raise AvailabilityError(f"{name} 时间戳类型不支持: {type(val).__name__}")


def _nonempty_str(name: str, val: object) -> str:
    if not isinstance(val, str) or not val.strip():
        raise AvailabilityError(f"{name} 必须为非空字符串，收到 {val!r}")
    return val.strip()


@dataclass(frozen=True)
class AvailabilityViolation:
    """一条未来发布（决策时点尚不可得）的另类记录。"""

    feature_id: str
    source: str
    published_at: str
    decision_time: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "source": self.source,
            "published_at": self.published_at,
            "decision_time": self.decision_time,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class AvailabilityReport:
    """批量另类记录在给定决策时点的可得性评估结果。"""

    decision_time: str
    total: int
    available_count: int
    unavailable_count: int
    available: bool
    violations: tuple[AvailabilityViolation, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_time": self.decision_time,
            "total": self.total,
            "available_count": self.available_count,
            "unavailable_count": self.unavailable_count,
            "available": self.available,
            "violations": [v.to_dict() for v in self.violations],
        }


def assess_alt_data_availability(
    records: Iterable[Mapping[str, Any]],
    decision_time: object,
) -> AvailabilityReport:
    """判定每条另类记录在 ``decision_time`` 是否已经发布（因果可得）。

    Args:
        records: 记录序列；每条至少含 ``feature_id``、``source``、``published_at``；
            可选 ``value`` 不参与判定。
        decision_time: 决策时点（对应 bar.close），支持 ISO 字符串/epoch/datetime。

    Returns:
        ``AvailabilityReport``；``available`` 为 True 当且仅当全部记录可得。
    """
    dt = _parse_ts("decision_time", decision_time)
    dt_iso = dt.isoformat()

    violations: list[AvailabilityViolation] = []
    total = 0

    for idx, rec in enumerate(records):
        if not isinstance(rec, Mapping):
            raise AvailabilityError(f"第 {idx} 条记录必须为映射，收到 {type(rec).__name__}")
        feature_id = _nonempty_str("feature_id", rec.get("feature_id"))
        source = _nonempty_str("source", rec.get("source"))
        pub = _parse_ts(f"published_at[{feature_id}]", rec.get("published_at"))
        total += 1

        if pub > dt:
            violations.append(AvailabilityViolation(
                feature_id=feature_id,
                source=source,
                published_at=pub.isoformat(),
                decision_time=dt_iso,
                detail=f"published_at {pub.isoformat()} 晚于决策时点 {dt_iso}",
            ))

    unavailable = len(violations)
    return AvailabilityReport(
        decision_time=dt_iso,
        total=total,
        available_count=total - unavailable,
        unavailable_count=unavailable,
        available=unavailable == 0,
        violations=tuple(violations),
    )
