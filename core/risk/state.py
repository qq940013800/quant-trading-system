# -*- coding: utf-8 -*-
"""core.risk.state —— RiskState 快照（审计与持仓期风控状态）。

冻结字段（硬规则 4）：
- atr0 / entry_dist 在入场时冻结，持仓期不得重算；R 倍数一律用这两个冻结值。
- stop_price 只允许向盈利方向移动（由 stops.update_stop 强制）。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

_CIRCUIT_STATES = ("normal", "breaker", "cooldown")


def _finite(name: str, val: float) -> float:
    if isinstance(val, bool) or not isinstance(val, (int, float)) \
            or not math.isfinite(val):
        raise ValueError({"layer": "risk.state",
                          "detail": f"{name} 必须为有限数值，收到 {val!r}"})
    return float(val)


def _positive(name: str, val: float) -> float:
    f = _finite(name, val)
    if f <= 0:
        raise ValueError({"layer": "risk.state",
                          "detail": f"{name} 必须 > 0，收到 {f!r}"})
    return f


def _nonneg_int(name: str, val: int) -> int:
    if isinstance(val, bool) or not isinstance(val, int) or val < 0:
        raise ValueError({"layer": "risk.state",
                          "detail": f"{name} 必须为非负整数，收到 {val!r}"})
    return val


@dataclass
class RiskState:
    """单笔决策发生时刻的风控快照。

    与 AI_ML_SYSTEM_DESIGN.md 3.1 的 RiskState schema 逐字段对齐。
    该对象是可变的（equity 随成交变化），但 atr0/entry_dist 冻结。
    """

    equity: float                 # 当前账户权益（计价货币 USD）
    atr0: float                   # 入场时冻结 ATR（价格单位），持仓期不变
    entry_dist: float             # 入场到止损的冻结距离（价格单位），R 倍数分母
    stop_price: Optional[float]   # 当前止损价；None=裁决前尚未设置
    heat_units: int               # 同向累计单位数（上限由 config，CLEAN 集校准）
    circuit_state: str = "normal"  # "normal" | "breaker" | "cooldown"
    drawdown_tier: float = 1.0     # 回撤档位系数（海龟分级降档：每 -10% ×0.8）
    extra: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        _finite("equity", self.equity)
        _finite("atr0", self.atr0)
        _positive("entry_dist", self.entry_dist)
        if self.stop_price is not None:
            _finite("stop_price", self.stop_price)
        _nonneg_int("heat_units", self.heat_units)
        if self.circuit_state not in _CIRCUIT_STATES:
            raise ValueError({"layer": "risk.state",
                              "detail": f"circuit_state 必须为 {_CIRCUIT_STATES}，"
                                        f"收到 {self.circuit_state!r}"})
        _positive("drawdown_tier", self.drawdown_tier)
        if not isinstance(self.extra, dict):
            raise ValueError({"layer": "risk.state",
                              "detail": f"extra 必须为 dict，收到 {type(self.extra).__name__}"})

    def frozen_r_denominator(self) -> float:
        """R 倍数分母（价格单位）。强制使用入场冻结的 entry_dist，禁止重算。"""
        return float(self.entry_dist)
