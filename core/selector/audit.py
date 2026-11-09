# -*- coding: utf-8 -*-
"""core.selector.audit —— 策略选择层审计快照（决策可审计，不变量 2）。

每一次 ``RegimeBlendedStrategy.on_bar_close`` 评估（无论最终是否出信号）
都落一条 SelectionRecord JSONL：当时的 regime 状态/概率、平滑后策略权重、
各专家候选信号摘要、合成强度、策略版本串、是否降级。

与 core.audit.record 的分工：
- ``core.audit.record.Decision`` 是引擎风控裁决层的快照（接受/拒绝/手数）；
- 本模块是**元层（选择层）快照**——回答「为什么这根 bar 出/没出这个方向」。
序列化思路参考 core.audit.record（单行 JSONL、NaN→null、时间戳 ISO），
但独立实现、不 import 其私有函数（解耦）。

replay 契约：``replay_selection(record)`` 从落盘 dict 还原权重与强度，
并用 ``blend_strength(expert_signals, strategy_weights)`` 重算强度做交叉校验——
任何手数/权重/强度的事后篡改都会被重算不一致或字段缺失抓到（带上下文 raise）。
"""
from __future__ import annotations

import dataclasses
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from .weights import blend_strength


class SelectionAuditError(ValueError):
    """审计快照构造/落盘/回放异常，携带上下文 dict（硬规则 9）。"""

    def __init__(self, context: dict):
        self.context = context
        super().__init__(f"SelectionAuditError: {context}")


@dataclass(frozen=True)
class SelectionRecord:
    """选择层快照（一行 = 一根已收盘 bar 的评估）。"""

    ts_utc: str                       # ISO8601 字符串（JSON 友好）
    state: str                        # regime 硬状态
    regime_probs: Dict[str, float]    # regime 原始概率（三键，和为 1）
    strategy_weights: Dict[str, float]  # 平滑后策略级权重（和为 1）
    expert_signals: Dict[str, dict]   # {name: {has_signal, direction, atr0, entry_dist}}
    blend_strength: float             # |Σ w_i·dir_i|
    strategy_versions: Dict[str, str]  # {name: version}
    degraded: bool                    # regime 分类器降级标志
    signal_id: Optional[str] = None   # 出信号时 = blend 信号 id；未出信号 None

    def __post_init__(self) -> None:
        ctx = {"layer": "selector.audit", "ts_utc": str(self.ts_utc)}
        if not isinstance(self.ts_utc, str) or not self.ts_utc:
            raise SelectionAuditError({**ctx, "detail": "ts_utc must be non-empty str"})
        if self.state is None:
            raise SelectionAuditError({**ctx, "detail": "state must not be None"})
        if not isinstance(self.regime_probs, dict) or not self.regime_probs:
            raise SelectionAuditError({**ctx, "detail": "regime_probs must be non-empty dict"})
        probs = list(self.regime_probs.values())
        if any(isinstance(v, bool) or not isinstance(v, (int, float))
               or not np.isfinite(v) or v < -1e-9 for v in probs):
            raise SelectionAuditError({**ctx,
                "detail": "regime_probs must be finite >= 0"})
        p_total = float(sum(probs))
        if abs(p_total - 1.0) > 1e-6:
            raise SelectionAuditError({**ctx,
                "detail": f"regime_probs must sum to 1, got {p_total!r}"})
        if not isinstance(self.strategy_weights, dict) or not self.strategy_weights:
            raise SelectionAuditError({**ctx, "detail": "strategy_weights must be non-empty dict"})
        if any(isinstance(v, bool) or not isinstance(v, (int, float))
               or not np.isfinite(v) for v in self.strategy_weights.values()):
            raise SelectionAuditError({**ctx,
                "detail": "strategy_weights must be finite"})
        w_total = float(sum(self.strategy_weights.values()))
        if abs(w_total - 1.0) > 1e-6:
            raise SelectionAuditError({**ctx,
                "detail": f"strategy_weights must sum to 1, got {w_total!r}"})
        if any(v < -1e-9 for v in self.strategy_weights.values()):
            raise SelectionAuditError({**ctx,
                "detail": "strategy_weights must be non-negative"})
        if not np.isfinite(self.blend_strength) or self.blend_strength < 0:
            raise SelectionAuditError({**ctx,
                "detail": f"blend_strength must be finite >= 0, got {self.blend_strength!r}"})


# --------------------------------------------------------------------------- #
# 序列化（参考 core.audit.record 思路，独立实现）
# --------------------------------------------------------------------------- #
def _to_jsonable(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, bool)):
        return obj
    if isinstance(obj, (int, float)):
        v = float(obj)
        return None if not np.isfinite(v) else v
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return None if not np.isfinite(v) else v
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    if dataclasses.is_dataclass(obj):
        return {f.name: _to_jsonable(getattr(obj, f.name))
                for f in dataclasses.fields(obj)}
    return str(obj)


def write_selection(path: str, record: SelectionRecord) -> None:
    """单行一条 JSONL 追加写盘（UTF-8），父目录不存在则创建。"""
    if not isinstance(record, SelectionRecord):
        raise SelectionAuditError({
            "layer": "selector.audit", "detail":
            f"expected SelectionRecord, got {type(record)}"})
    payload = _to_jsonable(record)
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    line = json.dumps(payload, ensure_ascii=False)
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError as exc:
        raise SelectionAuditError({
            "layer": "selector.audit", "path": str(path),
            "detail": f"write_selection failed: {exc!r}"}) from exc


def read_selections(path: str) -> List[SelectionRecord]:
    """读回全部 JSONL 记录；每行结构非法即抛带上下文错误（不静默跳过）。"""
    if not os.path.exists(path):
        return []
    out: List[SelectionRecord] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError as exc:
        raise SelectionAuditError({
            "layer": "selector.audit", "path": str(path),
            "detail": f"read_selections failed: {exc!r}"}) from exc
    for lineno, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SelectionAuditError({
                "layer": "selector.audit", "path": str(path),
                "lineno": lineno, "detail": f"invalid JSON: {exc!r}"}) from exc
        out.append(_record_from_dict(raw, lineno=lineno, path=path))
    return out


def _record_from_dict(raw: dict, *, lineno: int, path: str) -> SelectionRecord:
    """从 JSON dict 重建 SelectionRecord（缺字段/类型错 → 带上下文 raise）。"""
    required = {f.name for f in dataclasses.fields(SelectionRecord)}
    missing = required - set(raw.keys())
    if missing:
        raise SelectionAuditError({
            "layer": "selector.audit", "path": str(path), "lineno": lineno,
            "detail": f"missing field(s): {sorted(missing)}"})
    try:
        rec = SelectionRecord(
            ts_utc=raw["ts_utc"],
            state=raw["state"],
            regime_probs=raw["regime_probs"],
            strategy_weights=raw["strategy_weights"],
            expert_signals=raw["expert_signals"],
            blend_strength=raw["blend_strength"],
            strategy_versions=raw["strategy_versions"],
            degraded=bool(raw["degraded"]),
            signal_id=raw.get("signal_id"),
        )
    except (TypeError, ValueError, KeyError) as exc:
        raise SelectionAuditError({
            "layer": "selector.audit", "path": str(path), "lineno": lineno,
            "detail": f"record field invalid: {exc!r}"}) from exc
    return rec


def replay_selection(record) -> dict:
    """从落盘记录还原权重/强度，并重算强度做交叉校验。

    返回 ``{"strategy_weights": ..., "blend_strength": ..., "state": ...,
    "degraded": ..., "signal_id": ...}``。

    篡改检测：用 expert_signals 中的方向与 strategy_weights 重算
    ``|Σ w_i·dir_i|``，与记录值不一致（容差 1e-6）即抛带上下文错误——
    这意味着事后改权重/手数/强度都无法在回放时蒙混过关。
    """
    if isinstance(record, SelectionRecord):
        raw = {f.name: getattr(record, f.name)
               for f in dataclasses.fields(record)}
    elif isinstance(record, dict):
        raw = record
    else:
        raise SelectionAuditError({
            "layer": "selector.audit", "detail":
            f"replay_selection expects SelectionRecord|dict, got {type(record)}"})
    try:
        weights = {k: float(v) for k, v in raw["strategy_weights"].items()}
        claimed = float(raw["blend_strength"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SelectionAuditError({
            "layer": "selector.audit", "ts_utc": str(raw.get("ts_utc")),
            "detail": f"replay field missing/untyped: {exc!r}"}) from exc

    directions: Dict[str, int] = {}
    for name, sig in (raw.get("expert_signals") or {}).items():
        if not isinstance(sig, dict):
            raise SelectionAuditError({
                "layer": "selector.audit", "ts_utc": str(raw.get("ts_utc")),
                "expert": str(name),
                "detail": "expert_signals entry must be dict"})
        if sig.get("has_signal") and sig.get("direction") is not None:
            directions[name] = int(sig["direction"])

    recomputed = blend_strength(directions, weights)
    if abs(recomputed - claimed) > 1e-6:
        raise SelectionAuditError({
            "layer": "selector.audit", "ts_utc": str(raw.get("ts_utc")),
            "detail": f"blend_strength tampered: claimed={claimed!r} "
                      f"recomputed={recomputed!r}"})
    return {
        "strategy_weights": weights,
        "blend_strength": claimed,
        "state": raw.get("state"),
        "degraded": bool(raw.get("degraded", False)),
        "signal_id": raw.get("signal_id"),
    }


__all__ = ["SelectionRecord", "SelectionAuditError",
           "write_selection", "read_selections", "replay_selection"]
