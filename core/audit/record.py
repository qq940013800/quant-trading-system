# -*- coding: utf-8 -*-
"""core.audit.record —— Decision 审计快照与 JSONL 落盘。

冻结接口（设计 3.2）：
    write_decision(path: str, decision: Decision) -> None   # JSONL 追加，单行一条

纪律（不变量 2 / 设计②审计行）：
- 每笔信号无论接受/拒绝都必须产生一条 Decision；拒绝信号不得省略。
- 快照含各层输入：feature_snapshot / model_version / threshold_dataset /
  risk_state / final_signed_lots / reject_reason。
- r_multiple_at_close 在出场后回填（事后归因），用入场冻结 entry_dist。
"""
from __future__ import annotations

import dataclasses
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd

log = logging.getLogger("core.audit")


class SignalLikeError(Exception):
    """审计快照构造/序列化异常，携带上下文（硬规则 9）。"""

    def __init__(self, detail: str, layer: str = "audit.record"):
        self.context = {"layer": layer, "detail": detail}
        super().__init__(f"SignalLikeError: {self.context}")


def _to_jsonable(obj: Any) -> Any:
    """递归把 dataclass / Timestamp / numpy 标量转成 JSON 可序列化结构。"""
    if obj is None or isinstance(obj, (str, bool)):
        return obj
    if isinstance(obj, (int, float)):
        # 处理 NaN/inf -> null（JSON 无 NaN）
        if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)):
            return None
        return obj
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return None if (np.isnan(v) or np.isinf(v)) else v
    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    if dataclasses.is_dataclass(obj):
        return {f.name: _to_jsonable(getattr(obj, f.name))
                for f in dataclasses.fields(obj)}
    # 兜底：__dict__（非 dataclass 的 Signal/RiskState 对象）
    if hasattr(obj, "__dict__"):
        return {k: _to_jsonable(v) for k, v in vars(obj).items()}
    return str(obj)


@dataclass(frozen=True)
class Decision:
    """审计快照。与设计 3.1 Decision schema 逐字段对齐。

    signal:        L3 Signal（frozen dataclass；本包不 import，鸭子序列化）。
    feature_snapshot: 各层输入特征值（as_of 时刻取值）。
    model_version: 模型版本（无模型时 "rules-vN"）。
    risk_state:    决策时刻的 RiskState 快照。
    accepted:      是否接受开仓。
    reject_reason: 拒绝原因（接受为 None），如 "meta_p<quantile_30"/"news_window"/"circuit_breaker"。
    final_signed_lots: 接受时最终手数（拒绝为 0）。
    threshold_dataset: 本决策阈值来源集 "CLEAN"|"KNOWN"。
    decision_rule_version: 冻结的决策规则版本。
    r_multiple_at_close: 出场后回填（事后归因）。
    """

    decision_id: str
    signal: object
    feature_snapshot: dict
    model_version: str
    risk_state: object
    accepted: bool
    reject_reason: Optional[str]
    final_signed_lots: float
    threshold_dataset: str
    decision_rule_version: str
    r_multiple_at_close: Optional[float] = None

    def __post_init__(self) -> None:
        if self.threshold_dataset not in ("CLEAN", "KNOWN"):
            raise SignalLikeError(
                f"threshold_dataset must be CLEAN|KNOWN, got {self.threshold_dataset}")
        if self.accepted and self.final_signed_lots <= 0:
            raise SignalLikeError(
                f"accepted decision must have lots>0, got {self.final_signed_lots}")
        if not self.accepted and self.final_signed_lots != 0:
            raise SignalLikeError(
                f"rejected decision must have lots==0, got {self.final_signed_lots}")


def decision_to_dict(decision: Decision) -> dict:
    """把 Decision 转成可 JSON 序列化的 dict（含嵌套 signal/risk_state）。"""
    if not isinstance(decision, Decision):
        raise SignalLikeError(f"expected Decision, got {type(decision)}")
    return _to_jsonable(decision)


def write_decision(path: str, decision: Decision) -> None:
    """单行一条 JSONL 追加写盘。父目录不存在则创建。"""
    rec = decision_to_dict(decision)
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    line = json.dumps(rec, ensure_ascii=False)
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError as e:
        raise SignalLikeError(f"write_decision failed: {e}") from e
    log.debug("decision recorded id=%s accepted=%s",
              decision.decision_id, decision.accepted)
