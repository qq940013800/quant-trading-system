# -*- coding: utf-8 -*-
"""core.regime.output —— RegimeOutput 不可变输出对象（审计快照的一部分）。

不变量：
- state 必须是三状态之一（规则层可解释硬状态）；
- probs 必须覆盖全部三状态且和为 1（供下游连续加权，决策 #8）；
- threshold_dataset 恒为 "CLEAN"（阈值来源集，硬规则 2 集合分离）；
- degraded=True 表示概率为降级产物（特征缺失 → 均匀分布，或 GMM 层不可用），
  调用方据此降置信，而不是假装模型完好。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from .rules import STATES


@dataclass(frozen=True)
class RegimeOutput:
    state: str
    probs: Dict[str, float]
    version: str
    threshold_dataset: str = "CLEAN"
    degraded: bool = False

    def __post_init__(self) -> None:
        if self.state not in STATES:
            raise ValueError(
                f"regime state must be one of {STATES}, got {self.state!r}")
        if set(self.probs.keys()) != set(STATES):
            raise ValueError(
                f"probs must cover exactly {STATES}, got {sorted(self.probs)}")
        if not all(0.0 <= v <= 1.0 for v in self.probs.values()):
            raise ValueError(f"probs out of [0,1]: {self.probs}")
        total = sum(self.probs.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"probs must sum to 1, got {total!r}")
