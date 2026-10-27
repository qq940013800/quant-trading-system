# -*- coding: utf-8 -*-
"""core.registry —— 策略注册表模块。"""
from .strategy_registry import (
    StrategyRegistry,
    StrategyVersion,
    StrategyStatus,
    PerformanceSnapshot,
)
from .strategy_router import (
    StrategyDescriptor,
    StrategyWeightRouter,
    build_demo_router,
    SUPPORTED_REGIMES,
    STOP_TYPES,
)

__all__ = [
    "StrategyRegistry",
    "StrategyVersion",
    "StrategyStatus",
    "PerformanceSnapshot",
    "StrategyDescriptor",
    "StrategyWeightRouter",
    "build_demo_router",
    "SUPPORTED_REGIMES",
    "STOP_TYPES",
]
