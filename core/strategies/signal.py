# -*- coding: utf-8 -*-
"""core.strategies.signal —— 统一策略信号 dataclass（引擎鸭子类型）。

字段与 core.backtest.engine._Signal 一一对应（引擎按属性鸭子消费，不 import
本模块），另加 ``strategy_version`` 以满足「决策可审计」不变量：每笔接受/
拒绝都能还原出自哪个策略实现版本。

校验（硬规则 9：异常带上下文 dict，禁止静默兜底）：
- direction 必须 +1/-1；
- atr0 / entry_dist 必须为正（入场冻结，R 倍数分母）；
- bar_ts_utc 必须 tz-aware UTC（硬规则 6：时区显式，不硬编码偏移）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class StrategySignal:
    """统一策略信号（可被 core.backtest.engine 鸭子消费）。"""

    signal_id: str
    bar_ts_utc: pd.Timestamp
    expert: str
    direction: int                 # +1 long / -1 short
    price_ref: float
    atr0: float                    # 入场冻结 ATR（持仓期不得重算）
    entry_dist: float              # 入场到初始止损的距离（入场冻结）
    l1_in_zone: bool
    regime_weights: dict
    meta_p: Optional[float] = None
    strategy_version: str = "v1"

    def __post_init__(self) -> None:
        ctx = {
            "layer": "strategies.signal",
            "expert": str(self.expert),
            "ts_utc": str(self.bar_ts_utc),
        }
        if int(self.direction) not in (1, -1):
            raise ValueError({**ctx,
                              "detail": f"direction must be +1/-1, got {self.direction!r}"})
        if not float(self.atr0) > 0:
            raise ValueError({**ctx,
                              "detail": f"atr0 must be > 0, got {self.atr0!r}"})
        if not float(self.entry_dist) > 0:
            raise ValueError({**ctx,
                              "detail": f"entry_dist must be > 0, got {self.entry_dist!r}"})
        if getattr(self.bar_ts_utc, "tzinfo", None) is None:
            raise ValueError({**ctx,
                              "detail": "bar_ts_utc must be tz-aware UTC"})


__all__ = ["StrategySignal"]
