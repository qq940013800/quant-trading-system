# -*- coding: utf-8 -*-
"""core.control.rollout —— 灰度阶段晋升与回滚纯判定（fail-closed）。

蓝图 G11：影子 → 小资金 → 全量；指标越线一键回滚。本模块只做纯判定：
    - 各阶段绩效/风险门槛由调用方取数注入（sharpe、回撤绝对值、成本偏差）；
    - 判定当前应晋升、保持还是回滚；结果与输入写入 audit，便于事后还原依据。

边界与不变量：
- 纯函数：无 IO、不读库、不触网、不下单；不执行真实放量或回滚动作。
- 回滚优先于晋升：任一越线指标先判回滚，再谈阶段推进。
- 阈值由配置/调用方冻结注入，模块内不写死业务门槛、不做绩效寻优。
"""
from __future__ import annotations

from dataclasses import dataclass
import enum
import math
from typing import Any, Optional


class RolloutStage(str, enum.Enum):
    """灰度发布阶段。"""
    SHADOW = "shadow"      # 影子运行，0 资金
    SMALL = "small"        # 小资金试运行
    FULL = "full"          # 全量
    ROLLBACK = "rollback"  # 回滚到上一稳定版本


_NEXT_STAGE = {
    RolloutStage.SHADOW: RolloutStage.SMALL,
    RolloutStage.SMALL: RolloutStage.FULL,
}


def _finite(name: str, val: float) -> float:
    if isinstance(val, bool) or not isinstance(val, (int, float)) \
            or not math.isfinite(float(val)):
        raise ValueError(f"{name} 必须为有限数值，收到 {val!r}")
    return float(val)


def _nonneg_finite(name: str, val: float) -> float:
    v = _finite(name, val)
    if v < 0:
        raise ValueError(f"{name} 必须 >= 0，收到 {v!r}")
    return v


@dataclass(frozen=True)
class RolloutThresholds:
    """灰度晋升/回滚门槛（阈值由调用方冻结注入）。

    min_sharpe:           晋升所需最低夏普比率。
    max_drawdown:         回撤绝对值上限（非负）；超过即回滚。
    max_cost_deviation:    成本偏差上限（非负）；None 表示不按成本偏差回滚。
    """

    min_sharpe: float
    max_drawdown: float
    max_cost_deviation: Optional[float] = None

    def __post_init__(self) -> None:
        _finite("min_sharpe", self.min_sharpe)
        _nonneg_finite("max_drawdown", self.max_drawdown)
        if self.max_cost_deviation is not None:
            _nonneg_finite("max_cost_deviation", self.max_cost_deviation)


@dataclass(frozen=True)
class RolloutDecision:
    """灰度判定结果（纯结果，含审计字段）。"""

    stage: RolloutStage
    action: str  # advance / hold / rollback
    reason_code: str
    audit: dict[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.action, str) or self.action not in ("advance", "hold", "rollback"):
            raise ValueError(f"action 非法: {self.action!r}")
        if not isinstance(self.reason_code, str) or not self.reason_code.strip():
            raise ValueError("reason_code 必须为非空字符串")
        if not isinstance(self.audit, dict):
            raise ValueError("audit 必须为 dict")


def _coerce_stage(stage: Any) -> RolloutStage:
    if isinstance(stage, RolloutStage):
        return stage
    try:
        return RolloutStage(str(stage).strip().lower())
    except ValueError as e:
        raise ValueError(f"非法灰度阶段: {stage!r}") from e


def evaluate_rollout(
    *,
    stage: Any,
    sharpe: float,
    drawdown: float,
    cost_deviation: Optional[float] = None,
    thresholds: RolloutThresholds,
) -> RolloutDecision:
    """按当前阶段指标判定晋升 / 保持 / 回滚。

    Args:
        stage: 当前灰度阶段（``RolloutStage`` 或其字符串值）。
        sharpe: 影子/试运行期实测夏普比率（有限数值）。
        drawdown: 实测回撤绝对值（负值按绝对值处理）。
        cost_deviation: 实测成本相对偏差；None 表示不纳入回滚判定。
        thresholds: 晋升/回滚门槛。

    判定顺序：回滚优先（回撤越线 / 夏普不足 / 成本偏差越线）→ 达标晋升 → 未达标保持。
    """
    cur = _coerce_stage(stage)
    sharpe_v = _finite("sharpe", sharpe)
    dd_v = abs(_finite("drawdown", drawdown))
    cost_v: Optional[float] = None
    if cost_deviation is not None:
        cost_v = _nonneg_finite("cost_deviation", cost_deviation)

    audit: dict[str, Any] = {
        "stage": cur.value,
        "sharpe": sharpe_v,
        "drawdown": dd_v,
        "cost_deviation": cost_v,
        "thresholds": {
            "min_sharpe": thresholds.min_sharpe,
            "max_drawdown": thresholds.max_drawdown,
            "max_cost_deviation": thresholds.max_cost_deviation,
        },
    }

    # 1) 回滚优先：任一越线指标先判回滚。
    if dd_v > thresholds.max_drawdown:
        return RolloutDecision(
            RolloutStage.ROLLBACK, "rollback", "rollback_drawdown_excess", audit)
    if sharpe_v < thresholds.min_sharpe:
        return RolloutDecision(
            RolloutStage.ROLLBACK, "rollback", "rollback_sharpe_below", audit)
    if cost_v is not None and thresholds.max_cost_deviation is not None \
            and cost_v > thresholds.max_cost_deviation:
        return RolloutDecision(
            RolloutStage.ROLLBACK, "rollback", "rollback_cost_excess", audit)

    # 2) 达标：可沿 shadow → small → full 晋升；full 保持。
    qualified = sharpe_v >= thresholds.min_sharpe and dd_v <= thresholds.max_drawdown
    if cur is RolloutStage.FULL:
        return RolloutDecision(cur, "hold", "hold_full", audit)
    if qualified and cur in _NEXT_STAGE:
        nxt = _NEXT_STAGE[cur]
        code = "advance_to_small" if nxt is RolloutStage.SMALL else "advance_to_full"
        return RolloutDecision(nxt, "advance", code, audit)

    return RolloutDecision(cur, "hold", "hold_stage", audit)
