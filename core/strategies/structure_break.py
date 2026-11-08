# -*- coding: utf-8 -*-
"""core.strategies.structure_break —— 市场结构突破（BOS / CHoCH）策略。

复用 core.features.structure.market_structure_at（@as_of 因果守卫入口，
内部委托 get_market_structure）：swing 点需左右各 k 根
确认 bar（confirmed_at 之后才可用），BOS=趋势延续突破同向 swing，
CHoCH=趋势反转突破反向 swing——结构检测本身因果 by construction。

触发纪律（避免重复出信号）：**当且仅当「最新结构突破发生在当前已收盘 bar」**
（``break.index == len(history) - 1``）才出信号；同一 history 重复调用
结果可重放（同一决策快照），下一根 bar 若无新突破则自然无信号。

方向取 break.direction：bullish → +1，bearish → -1。
"""
from __future__ import annotations

import numpy as np

from ..features.structure import market_structure_at
from .base import BaseStrategy


class StructureBreakStrategy(BaseStrategy):
    """BOS / CHoCH 结构突破趋势策略。"""

    expert = "structure_break"
    strategy_version = "structure_break-v1"
    PARAMS_SCHEMA = {
        "k": {"type": "int", "default": 3, "min": 1,
              "desc": "swing 确认窗口（左右各 k 根 bar）"},
        "atr_n": {"type": "int", "default": 14, "min": 2,
                  "desc": "ATR 周期（CLEAN 集分布校准）"},
        "entry_dist_mult": {"type": "float", "default": 2.0, "min": 0.1,
                            "desc": "入场到止损距离 = mult × ATR"},
        "symbol": {"type": "str", "default": "XAUUSD",
                   "desc": "signal_id 前缀"},
    }

    def requires_features(self) -> list[str]:
        return ["market_structure_at", "wilder_atr"]

    def on_bar_close(self, history: list, bar, **params):
        p = self._merged(history, bar, params)
        k = p["k"]
        # swing 检测至少需要 2k+1 根；结构趋势判断还需两对 swing 点
        if len(history) < 3 * k + 3:
            return None
        atr0 = self.atr(history, bar, p["atr_n"])
        if not np.isfinite(atr0) or atr0 <= 0:
            return None
        ms = market_structure_at(history, bar.ts_utc, k=k)
        n = len(history)
        fresh = [b for b in (ms.last_bos, ms.last_choch)
                 if b is not None and b.index == n - 1]
        if not fresh:
            return None
        break_event = max(fresh, key=lambda b: b.index)
        direction = 1 if break_event.direction == "bullish" else -1
        return self.make_signal(
            bar, direction=direction, price_ref=float(bar.close),
            atr0=atr0, entry_dist_mult=p["entry_dist_mult"],
            l1_in_zone=True,
            regime_weights={"trend": 1.0, "mr": 0.0, "range": 0.0},
            symbol=p["symbol"])


__all__ = ["StructureBreakStrategy"]
