# -*- coding: utf-8 -*-
"""core.regime —— 市场状态分类器（规则硬状态 + GMM 软概率混合）。

决策映射（docs/trading/RESEARCH_MAPPING.md）：
- 决策 #8：regime 输出连续概率/分位分数，不用硬标签；deadband 加权混合而非硬切换；
- 决策 #9：阈值全部来自 CLEAN 集分布分位数（np.quantile），禁止按绩效网格搜索。

不可协商的纪律（AGENTS.md）：
- 因果单向：predict(history, as_of) 内部只调经 @as_of 装饰的特征函数，
  history 含 ts_utc > as_of 的 bar 时由特征层抛 LookAheadError；
- 集合分离：fit 只在调用方传入的 CLEAN 训练段上拟合/校准；predict 绝不重拟合；
- 阈值来自分布：adx/atr_pct 的 deadband 边全部是训练段经验分位，模块内无绩效字面量。
"""
from __future__ import annotations

from .output import RegimeOutput
from .rules import (
    STATE_MEAN_REVERSION,
    STATE_RANGING,
    STATE_TREND,
    STATES,
    RuleThresholds,
    derive_thresholds,
)
from .classifier import RegimeClassifier
from .gmm import GMMRegimeModel, has_gmm

__all__ = [
    "RegimeOutput",
    "RegimeClassifier",
    "GMMRegimeModel",
    "has_gmm",
    "STATE_TREND",
    "STATE_MEAN_REVERSION",
    "STATE_RANGING",
    "STATES",
    "RuleThresholds",
    "derive_thresholds",
]
