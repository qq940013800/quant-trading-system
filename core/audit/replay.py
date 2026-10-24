# -*- coding: utf-8 -*-
"""core.audit.replay —— 审计回放：用快照重算并比对，证明可完整还原每笔决策。

验收点（设计⑦.D / 实现 spec 4.6）：replay 后必须能还原
    feature_snapshot / model_version / final_signed_lots / reject_reason 五要素。
"""
from __future__ import annotations

import json
from typing import Optional

from ..risk.sizing import target_lots


class ReplayMismatch(Exception):
    """回放重算与快照不一致。携带上下文（硬规则 9）。"""

    def __init__(self, detail: str, expected=None, actual=None):
        self.context = {"layer": "audit.replay", "detail": detail,
                        "expected": expected, "actual": actual}
        super().__init__(f"ReplayMismatch: {self.context}")


def read_decisions(path: str) -> list[dict]:
    """读取 JSONL 全部决策为 dict 列表（保留嵌套结构）。"""
    out: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ReplayMismatch(f"corrupted JSONL at line {ln}: {e}") from e
    return out


# 回放重算所需的、由引擎写入 feature_snapshot 的 sizing 输入键（契约）
_REQUIRED_KEYS = (
    "equity", "risk_pct", "stop_dist_price", "point_value",
    "min_lot", "lot_step", "kelly_cap", "vol_scale",
)


def replay_decision(rec: dict, tol: float = 1e-6) -> dict:
    """对单条 Decision dict 重算最终手数并比对快照。

    还原五要素：feature_snapshot / model_version / threshold_dataset /
                 final_signed_lots / reject_reason。
    返回 {ok, recomputed_lots, stored_lots, accepted, reject_reason}；不一致抛 ReplayMismatch。
    """
    fs = rec.get("feature_snapshot") or {}
    missing = [k for k in _REQUIRED_KEYS if k not in fs]
    if missing:
        raise ReplayMismatch(f"feature_snapshot missing sizing inputs: {missing}")

    # 用冻结签名重算手数（stop_dist_price 即冻结止损距离，作为 atr0 形参传入）
    recomputed = target_lots(
        equity=float(fs["equity"]),
        risk_pct=float(fs["risk_pct"]),
        atr0=float(fs["stop_dist_price"]),
        point_value=float(fs["point_value"]),
        min_lot=float(fs["min_lot"]),
        lot_step=float(fs["lot_step"]),
        kelly_cap=float(fs["kelly_cap"]),
    )
    recomputed *= float(fs.get("vol_scale", 1.0))

    stored_lots = float(rec.get("final_signed_lots", 0.0))
    accepted = bool(rec.get("accepted", False))
    reject_reason: Optional[str] = rec.get("reject_reason")

    # 拒绝单：快照手数必须为 0
    if not accepted:
        if stored_lots != 0.0:
            raise ReplayMismatch(
                "rejected record must have final_signed_lots==0",
                expected=0.0, actual=stored_lots)
        return {"ok": True, "recomputed_lots": 0.0, "stored_lots": stored_lots,
                "accepted": False, "reject_reason": reject_reason}

    # 接受单：重算手数必须与快照一致（拒绝单不占用 sizing）
    if abs(recomputed - stored_lots) > tol:
        raise ReplayMismatch(
            "accepted record lots mismatch",
            expected=stored_lots, actual=recomputed)
    return {"ok": True, "recomputed_lots": recomputed, "stored_lots": stored_lots,
            "accepted": True, "reject_reason": reject_reason}
