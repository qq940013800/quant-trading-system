# -*- coding: utf-8 -*-
"""core.risk —— 风控与资金管理包（第二阶段分片③）。

只依赖 numpy/pandas；不依赖 core/data、core/features、core/models（并行实现中）。
接口契约见 docs/trading/AI_ML_SYSTEM_DESIGN.md 第③章。
"""
from .state import RiskState
from .stops import StopWideningError, update_stop, initial_stop
from .sizing import target_lots, vol_target_scale, quantile_threshold, assess_vol_target_tracking
from .circuit import CircuitBreaker, CircuitState
from .risk_budget import (
    risk_budget_weights,
    risk_parity_weights,
    correlation_pairs,
    average_pairwise_correlation,
    correlation_breaker,
    correlation_regime_shift,
)
from .return_profile import describe_returns
from .drawdown_tier import drawdown_tier_factor
from .protection import (
    evaluate_chandelier,
    evaluate_scale_out,
    evaluate_profit_retracement,
    decide_protection,
    ScaleOutRule,
    ScaleOutResult,
    ProtectionDecision,
)

__all__ = [
    "RiskState",
    "StopWideningError",
    "update_stop",
    "initial_stop",
    "target_lots",
    "vol_target_scale",
    "assess_vol_target_tracking",
    "quantile_threshold",
    "CircuitBreaker",
    "CircuitState",
    "risk_budget_weights",
    "risk_parity_weights",
    "correlation_pairs",
    "average_pairwise_correlation",
    "correlation_breaker",
    "correlation_regime_shift",
    "describe_returns",
    "drawdown_tier_factor",
    "evaluate_chandelier",
    "evaluate_scale_out",
    "evaluate_profit_retracement",
    "decide_protection",
    "ScaleOutRule",
    "ScaleOutResult",
    "ProtectionDecision",
]
