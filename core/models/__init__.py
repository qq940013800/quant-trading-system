# -*- coding: utf-8 -*-
"""core.models —— AI/ML 模型层（标签 → 基线 → GBM → meta-labeling → 漂移监控）。

纪律（设计文档②/IMPLEMENTATION_SPEC §5）：
- 禁随机 KFold；验证只走 purged walk-forward + embargo；
- 禁按 Sharpe 网格搜超参；阈值/分位一律来自 CLEAN 分布；
- lightgbm 不得成为 import 期硬依赖（缺失时本包其余部分必须可用）。
"""
from .base import Model
from .labels import triple_barrier_labels
from .cv import purged_walk_forward, PurgedCVError

__all__ = ["Model", "triple_barrier_labels", "purged_walk_forward", "PurgedCVError"]
