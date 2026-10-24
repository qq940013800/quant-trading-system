# -*- coding: utf-8 -*-
"""core.backtest —— 事件驱动回测引擎（第二阶段分片③）。

只在已收盘 bar 触发信号与退出决策；成本三档（平静/新闻±15min/跳空）+ 滑点 + 佣金。
"""
from .costs import CostModel, spread_at, slippage_points, is_news_time
from .broker import simulate_fill, Fill
from .metrics import compute_metrics
from .engine import (
    BacktestResult,
    BarLike,
    Position,
    run_backtest,
    DemoBreakoutStrategy,
)

__all__ = [
    "CostModel", "spread_at", "slippage_points", "is_news_time",
    "simulate_fill", "Fill",
    "compute_metrics",
    "BacktestResult", "BarLike", "Position", "run_backtest",
    "DemoBreakoutStrategy",
]
