# -*- coding: utf-8 -*-
"""core.features —— 因果特征工程包。

铁律（AGENTS.md 硬规则 1/2/5）：
- 所有特征函数经 `@as_of` 装饰：history 中任 bar.ts_utc > as_of 即抛 LookAheadError；
- 只用 available_at <= bar.close（= ts_utc <= as_of）的已收盘 bar；
- 归一化一律 rolling/expanding（只用过去），禁止全样本 z-score；
- ATR/vol/Hurst 等统计量只应在 CLEAN 集上估计（集合分离由调用方传入对应 history）。
"""
from .base import (
    AsOfContractError,
    LookAheadError,
    BarLike,
    as_of,
    build_feature_panel,
)

__all__ = [
    "AsOfContractError",
    "LookAheadError",
    "BarLike",
    "as_of",
    "build_feature_panel",
]
