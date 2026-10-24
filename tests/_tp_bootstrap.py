# -*- coding: utf-8 -*-
"""测试共用引导：把项目根目录放上 sys.path，并提供确定性合成 bar 夹具工厂。

core.data.synthetic.make_synthetic_bars 契约（DATA_INGESTION §⑤）：
固定 seed 同结果；martingale=纯随机游走；trend_regime=两段 regime。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from core.data.synthetic import make_synthetic_bars  # noqa: E402

__all__ = ["make_synthetic_bars", "pd"]
