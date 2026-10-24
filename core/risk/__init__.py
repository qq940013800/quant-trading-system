# -*- coding: utf-8 -*-
"""core.risk —— 风控与资金管理包（第二阶段分片③）。

只依赖 numpy/pandas；不依赖 core/data、core/features、core/models（并行实现中）。
接口契约见 docs/trading/AI_ML_SYSTEM_DESIGN.md 第③章。
"""
from .state import RiskState
from .stops import StopWideningError, update_stop, initial_stop
from .sizing import target_lots, vol_target_scale, quantile_threshold
from .circuit import CircuitBreaker, CircuitState

__all__ = [
    "RiskState",
    "StopWideningError",
    "update_stop",
    "initial_stop",
    "target_lots",
    "vol_target_scale",
    "quantile_threshold",
    "CircuitBreaker",
    "CircuitState",
]
