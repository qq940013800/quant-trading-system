# -*- coding: utf-8 -*-
"""core.registry —— 策略注册表与 ML 模型版本注册中心。"""
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
from .model_registry import (
    ModelRegistry,
    ModelVersion,
    ModelStage,
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
    "ModelRegistry",
    "ModelVersion",
    "ModelStage",
]
