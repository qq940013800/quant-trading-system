# -*- coding: utf-8 -*-
"""core.backtest.tca —— 交易成本分析（TCA）纯判定底座。

蓝图 G7：实盘成交 vs 回测成本偏差日报。逐期把成本分解为
点差 / 滑点 / 市场冲击 / 佣金，对比回测预估成本，按相对偏差阈值判定是否告警。

纯函数：不读 DB、不触实盘下单路径；阈值由调用方冻结传入，函数内不做寻优。
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional


def _finite(name: str, val: float) -> float:
    if not isinstance(val, (int, float)) or isinstance(val, bool) \
            or not math.isfinite(val):
        raise ValueError(f"{name} 必须为有限数值，收到 {val!r}")
    return float(val)


def _nonneg_finite(name: str, val: float) -> float:
    v = _finite(name, val)
    if v < 0:
        raise ValueError(f"{name} 必须 >= 0，收到 {v!r}")
    return v


_COMPONENTS = ("spread", "slippage", "impact", "commission")


@dataclass(frozen=True)
class CostBreakdown:
    """单期成本四分量分解（价格单位或货币单位，口径由调用方统一）。"""
    spread: float
    slippage: float
    impact: float
    commission: float

    @property
    def total(self) -> float:
        return self.spread + self.slippage + self.impact + self.commission

    def components(self) -> dict[str, float]:
        return {"spread": self.spread, "slippage": self.slippage,
                "impact": self.impact, "commission": self.commission}

    def shares(self) -> dict[str, float]:
        """各分量占总成本比例；总成本为 0 时各项占比记 0（无可分摊口径）。"""
        total = self.total
        if total <= 0:
            return {k: 0.0 for k in _COMPONENTS}
        return {k: getattr(self, k) / total for k in _COMPONENTS}


def decompose_costs(*, spread: float, slippage: float, impact: float,
                    commission: float) -> CostBreakdown:
    """构造成本分解；各分量必须为非负有限值。"""
    return CostBreakdown(
        spread=_nonneg_finite("spread", spread),
        slippage=_nonneg_finite("slippage", slippage),
        impact=_nonneg_finite("impact", impact),
        commission=_nonneg_finite("commission", commission),
    )


@dataclass(frozen=True)
class CostDeviation:
    """实际成本 vs 回测预估成本的偏差判定（纯数据）。"""
    actual_total: float
    expected_total: float
    deviation: float
    deviation_ratio: Optional[float]
    breached: bool
    threshold: float
    flags: dict[str, float]

    def to_dict(self) -> dict:
        return {
            "actual_total": self.actual_total,
            "expected_total": self.expected_total,
            "deviation": self.deviation,
            "deviation_ratio": self.deviation_ratio,
            "breached": self.breached,
            "threshold": self.threshold,
            "flags": dict(self.flags),
        }


def assess_cost_deviation(actual: CostBreakdown, expected: CostBreakdown,
                          deviation_threshold: float) -> CostDeviation:
    """对比实际与预估成本，按相对偏差阈值判定是否超阈值告警。

    Args:
        actual: 实际成交成本分解。
        expected: 回测预估成本分解。
        deviation_threshold: 相对偏差绝对值上限（非负有限，比例）；
            0 表示任何超支都告警。

    口径：
        deviation = actual.total - expected.total
        expected.total > 0 时 ratio = deviation / |expected.total|；
        expected.total = 0 时无法归一，ratio 记 None；actual>0 即判 breached。
    """
    threshold = _nonneg_finite("deviation_threshold", deviation_threshold)
    actual_total = _nonneg_finite("actual.total", actual.total)
    expected_total = _nonneg_finite("expected.total", expected.total)

    deviation = actual_total - expected_total

    if expected_total > 0:
        ratio = deviation / abs(expected_total)
        breached = abs(ratio) > threshold
    else:
        ratio = None
        breached = actual_total > 0

    flags = {
        "actual_total": actual_total,
        "expected_total": expected_total,
        "deviation": deviation,
        "deviation_ratio": 0.0 if ratio is None else ratio,
        "threshold": threshold,
    }
    return CostDeviation(
        actual_total=actual_total,
        expected_total=expected_total,
        deviation=deviation,
        deviation_ratio=ratio,
        breached=breached,
        threshold=threshold,
        flags=flags,
    )
