# -*- coding: utf-8 -*-
"""core.strategies —— 生产用策略实现（回测引擎 Strategy 协议）。

契约（core/backtest/engine.py::Strategy）::

    on_bar_close(history: list, bar) -> Optional[Signal-like]

历史约定：history == bars[:i+1]，最后一个元素就是本根「已收盘」bar；
策略只允许读取 history（AGENTS.md 硬规则 1/5），不得访问未来 bar、
不得依赖跨 bar 的可变全局状态（否则同一 history 的重放结果不可复现）。

本包策略只产出「候选信号」（atr0 / entry_dist / regime_weights / meta_p），
手数一律交给 core.risk.sizing.target_lots 计算（硬规则 8：不硬编码手数）。
"""
from __future__ import annotations

from .mean_reversion import MeanReversionStrategy
from .trend_breakout import TrendBreakoutStrategy

# 本分片新增：统一接口层（Protocol / 信号 / 工厂注册器）与两个新策略实现。
# 既有 TrendBreakoutStrategy / MeanReversionStrategy 保持旧构造参数式接口，
# 不迁入统一 Protocol（鸭子兼容性由 tests/test_strategies_base.py 证明）。
from .base import BaseStrategy, Strategy, check_closed_window
from .registry import (get_strategy, list_strategies, register_strategy,
                       strategy_version)
from .signal import StrategySignal
from .structure_break import StructureBreakStrategy
from .supply_demand import SupplyDemandStrategy

__all__ = [
    "TrendBreakoutStrategy", "MeanReversionStrategy", "all_strategies",
    "Strategy", "BaseStrategy", "check_closed_window",
    "StrategySignal",
    "register_strategy", "get_strategy", "list_strategies", "strategy_version",
    "SupplyDemandStrategy", "StructureBreakStrategy",
]


def all_strategies() -> list:
    """返回默认参数的策略实例列表（供 registry / 回测批量登记使用）。

    每次调用都新建实例，避免调用方之间共享可变状态（因果可复现）。
    """
    return [TrendBreakoutStrategy(), MeanReversionStrategy()]
