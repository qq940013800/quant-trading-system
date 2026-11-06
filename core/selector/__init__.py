# -*- coding: utf-8 -*-
"""core.selector —— 策略自动匹配（元层）：带滞回的状态加权混合选择 + 审计。

研究依据（docs/trading/STRATEGY_AUTO_MATCHING_DEEP_DIVE.md）：
- 决策 #8 / O06：regime 连续概率 → EMA 慢更新 + 双向 deadband + 连续 N bar
  确认的加权混合，不硬切换（消弭 threshold whipsaw）；
- 决策 #9 / O07：alpha/deadband/confirm_n/min_strength 全部由调用方从
  CLEAN 分布校准后冻结传入；shrink_params 默认生产路径 lam=1（全局默认
  参数），禁止按 regime 绩效网格搜索局部参数；
- 不变量 2（决策可审计）：每根已收盘 bar 的 regime 判定、平滑权重、专家
  候选、合成强度都落 SelectionRecord JSONL，replay 可交叉校验。

不可协商的纪律（AGENTS.md）：
- 因果单向：只经已 fit 的 RegimeClassifier.predict(history, as_of) 取状态，
  history 含未来 bar 由 @as_of 特征层抛 LookAheadError；
- 阈值来自分布：本包不出现绩效网格字面量；
- 本包只读 core.regime / core.strategies，不修改其任何文件。
"""
from __future__ import annotations

from .audit import (SelectionAuditError, SelectionRecord, read_selections,
                    replay_selection, write_selection)
from .blend import BlendedSignal, BlendConfigError, RegimeBlendedStrategy
from .weights import (DeadbandWeightState, WeightStateError, blend_strength,
                     shrink_params)

__all__ = [
    "DeadbandWeightState", "WeightStateError", "shrink_params", "blend_strength",
    "RegimeBlendedStrategy", "BlendedSignal", "BlendConfigError",
    "SelectionRecord", "SelectionAuditError",
    "write_selection", "read_selections", "replay_selection",
]
