# -*- coding: utf-8 -*-
"""core.features.base —— as_of 因果装饰器、异常体系与特征面板构建器。

接口契约（docs/trading/AI_ML_SYSTEM_DESIGN.md 3.2 / IMPLEMENTATION_SPEC §4.1）：
    @as_of
    def feat_x(history: list[BarLike], as_of: pd.Timestamp, **kw) -> float | pd.Series

- `as_of` 必须是 tz-aware UTC 时间戳；naive 即 AsOfContractError；
- history 中任 bar.ts_utc > as_of → LookAheadError（前视守卫）；
- 特征函数只能在 history 切片上计算（history 已由装饰器保证全部 <= as_of）。

设计取舍：特征按"点在时间线上的可重算性"设计——同一 (history, as_of) 调用
必须得到同一结果，且 history 尾部追加未来 bar 后重算 as_of 处值不变
（黄金因果守卫 c01/c02 的正向断言，见 tests/test_features_causal.py）。
"""
from __future__ import annotations

import functools
import logging
from typing import Callable, Protocol, runtime_checkable

import numpy as np
import pandas as pd

logger = logging.getLogger("core.features")


class AsOfContractError(Exception):
    """as_of 契约违反（非前视类的其它契约错误：naive 时间戳、空 history、未排序等）。"""

    def __init__(self, context: dict):
        # 异常必须带 {"symbol","ts_utc","layer","detail"} 上下文（AGENTS.md 硬规则 9）
        self.context = context
        super().__init__(f"as_of contract violation: {context}")


class LookAheadError(AsOfContractError):
    """特征前视：history 中存在 bar.ts_utc > as_of 的 bar。"""


@runtime_checkable
class BarLike(Protocol):
    """Bar 结构协议（duck-typing，与 core/data/bar.py::Bar 字段对齐）。

    特征包不 import core.data（并行开发、避免运行时耦合）；只要对象具备
    以下属性即可通过——未来 core.data.Bar 落地后天然满足本协议。
    """

    symbol: str
    ts_utc: pd.Timestamp
    open_: float
    high: float
    low: float
    close: float
    tick_volume: float
    spread_points: float | None


def as_of(feature_func: Callable) -> Callable:
    """装饰器：强制 feature_func(history, as_of, ...) 的因果不变量。

    检查顺序：
      1. as_of 非空且 tz-aware UTC，否则 AsOfContractError；
      2. history 中所有 bar.ts_utc <= as_of，否则 LookAheadError；
      3. history 按 ts_utc 单调（非单调视为数据损坏，AsOfContractError）。
    """

    @functools.wraps(feature_func)
    def wrapper(history: list[BarLike], as_of: pd.Timestamp, *args, **kwargs):
        if as_of is None:
            raise AsOfContractError({"layer": "features", "ts_utc": None,
                                     "detail": "as_of is None"})
        ts = getattr(as_of, "tzinfo", None)
        if ts is None:
            raise AsOfContractError({"layer": "features", "ts_utc": str(as_of),
                                     "detail": "as_of must be tz-aware UTC"})
        prev_ts = None
        for bar in history:
            bts = bar.ts_utc
            if bts.tzinfo is None:
                raise AsOfContractError({"layer": "features", "ts_utc": str(bts),
                                         "detail": "bar.ts_utc must be tz-aware UTC"})
            if bts > as_of:
                raise LookAheadError({
                    "layer": "features",
                    "symbol": getattr(bar, "symbol", "?"),
                    "ts_utc": str(bts),
                    "as_of": str(as_of),
                    "detail": "bar.ts_utc > as_of (lookahead)",
                })
            if prev_ts is not None and bts <= prev_ts:
                raise AsOfContractError({
                    "layer": "features", "symbol": getattr(bar, "symbol", "?"),
                    "ts_utc": str(bts),
                    "detail": "history ts_utc not strictly increasing",
                })
            prev_ts = bts
        return feature_func(history, as_of, *args, **kwargs)

    return wrapper


# ---------------------------------------------------------------------------
# 内部工具：history -> numpy 数组（仅在装饰器放行后调用）
# ---------------------------------------------------------------------------

def _arrays(history: list[BarLike]) -> dict[str, np.ndarray]:
    closes = np.fromiter((b.close for b in history), dtype=np.float64, count=len(history))
    highs = np.fromiter((b.high for b in history), dtype=np.float64, count=len(history))
    lows = np.fromiter((b.low for b in history), dtype=np.float64, count=len(history))
    opens = np.fromiter((b.open_ for b in history), dtype=np.float64, count=len(history))
    return {"open_": opens, "high": highs, "low": lows, "close": closes}


def _wilder_ewma(values: np.ndarray, period: int) -> np.ndarray:
    """Wilder 平滑（RMA）：首值 = 前 period 个均值，其后 alpha=1/period。"""
    out = np.full_like(values, np.nan, dtype=np.float64)
    if len(values) < period:
        return out
    out[period - 1] = values[:period].mean()
    alpha = 1.0 / period
    for i in range(period, len(values)):
        out[i] = out[i - 1] * (1.0 - alpha) + values[i] * alpha
    return out


def expanding_percentile_rank(past_values: np.ndarray, current: float) -> float:
    """当前值在过去分布中的分位（0~1）：过去 <= current 的比例。

    阈值来自分布的基础构件——只用 `past_values`（全部 <= as_of），禁止全样本。
    """
    arr = np.asarray(past_values, dtype=np.float64)
    arr = arr[~np.isnan(arr)]
    if arr.size == 0:
        return np.nan
    return float((arr <= current).mean())


# ---------------------------------------------------------------------------
# 特征面板构建：逐 as_of 调用特征函数（因果 by construction）
# ---------------------------------------------------------------------------

def build_feature_panel(
    history: list[BarLike],
    features: dict[str, Callable],
    *,
    warmup_bars: int = 60,
) -> pd.DataFrame:
    """逐根已收盘 bar 计算特征面板。

    Parameters
    ----------
    history : 全部可用 bar（按 ts_utc 升序）；
    features : {特征名: feat_x(history, as_of, **kw)}，全部经 @as_of；
    warmup_bars : 前 N 根 bar 统计量不足，保留为 NaN 行（不猜未来）。

    Returns
    -------
    pd.DataFrame  index = ts_utc，附契约列 `available_at`（= 行 index 本身，
    因为特征只用 <= as_of 的已收盘 bar）。
    """
    n = len(history)
    rows: list[dict] = []
    for i in range(n):
        as_of = history[i].ts_utc
        row: dict = {"available_at": as_of}
        if i < warmup_bars:
            for name in features:
                row[name] = np.nan
        else:
            hist_slice = history[: i + 1]  # 只含 <= as_of 的 bar（装饰器双保险）
            for name, func in features.items():
                try:
                    row[name] = float(func(hist_slice, as_of))
                except (ValueError, ArithmeticError) as exc:
                    # 统计量不足等数值失败：记 NaN 并带上下文，禁止静默吞错
                    logger.warning("feature %s failed at %s: %s", name, as_of, exc)
                    row[name] = np.nan
        rows.append(row)
    df = pd.DataFrame(rows)
    df.index = pd.DatetimeIndex([b.ts_utc for b in history], name="ts_utc")
    return df
