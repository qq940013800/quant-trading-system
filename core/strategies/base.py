# -*- coding: utf-8 -*-
"""core.strategies.base —— 统一策略接口（Protocol）与参数化基类。

契约（本分片对「策略自动匹配」模块的策略侧要求）：
- ``requires_features() -> list[str]``：声明依赖的 @as_of 特征名（供特征面板
  构建/审计使用）；
- ``params_schema() -> dict``：参数名 -> {type, default, min, max, desc}。
  默认值全部来自 schema（阈值来自分布/配置，禁止绩效网格硬编码，
  AGENTS.md 不变量 3）；
- ``on_bar_close(history, bar, **params) -> StrategySignal | None``：
  history == bars[:i+1] 已收盘序列，bar == history[-1]（已收盘）。

因果纪律（硬规则 1/5）：
1. 基类守卫 ``history[-1].ts_utc == bar.ts_utc``，否则抛带上下文 ValueError
   （混入未来 bar 显式失败，不静默）；
2. 数值统计量一律复用 core.features 的 @as_of 实现——装饰器对 history 中
   任何 ts > as_of 的 bar 抛 LookAheadError，双重兜底。
"""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

import pandas as pd

from ..features.atr import wilder_atr
from .signal import StrategySignal


@runtime_checkable
class Strategy(Protocol):
    """统一策略接口（鸭子类型，与 engine.Strategy 消费协议兼容）。"""

    def requires_features(self) -> list[str]: ...

    def params_schema(self) -> dict: ...

    def on_bar_close(self, history: list, bar, **params) -> Optional[StrategySignal]: ...


def check_closed_window(history: list, bar, *, layer: str) -> None:
    """因果守卫：history 必须以「当前已收盘 bar」结尾（不许混入未来 bar）。"""
    if not history:
        raise ValueError({"layer": layer, "detail": "empty history"})
    if history[-1].ts_utc != bar.ts_utc:
        raise ValueError({
            "layer": layer,
            "ts_utc": str(bar.ts_utc),
            "history_last_ts_utc": str(history[-1].ts_utc),
            "detail": "history must end at the current closed bar (no future bars)",
        })


class BaseStrategy:
    """参数化策略基类：schema 校验 + params 合并 + 共享 ATR/信号构建。

    子类需设置 ``expert`` / ``strategy_version`` / ``PARAMS_SCHEMA`` 并实现
    ``on_bar_close``（内部先调 ``self._merged(history, bar, params)``）。
    """

    expert: str = "base"
    strategy_version: str = "v1"
    PARAMS_SCHEMA: dict = {}

    def __init__(self, **params):
        self._params = self._validate(params, self.PARAMS_SCHEMA,
                                      layer=f"strategies.{self.expert}")

    # ------------------------------------------------------------------ #
    # schema / 校验
    # ------------------------------------------------------------------ #
    @classmethod
    def params_schema(cls) -> dict:
        """返回参数 schema 的浅拷贝（默认值即参数出处，禁止在逻辑里另写字面量）。"""
        return dict(cls.PARAMS_SCHEMA)

    def requires_features(self) -> list[str]:
        return []

    @staticmethod
    def _validate(raw: dict, schema: dict, *, layer: str) -> dict:
        unknown = set(raw) - set(schema)
        if unknown:
            raise ValueError({"layer": layer,
                              "detail": f"unknown params: {sorted(unknown)} "
                                         f"(known: {sorted(schema)})"})
        out: dict = {}
        for name, spec in schema.items():
            ctype = spec.get("type", "float")
            val = raw.get(name, spec.get("default"))
            if val is None:
                # ts 类型允许显式 None（= 无 KNOWN 边界）；其余类型缺值即报错
                if ctype == "ts":
                    out[name] = None
                    continue
                raise ValueError({"layer": layer,
                                  "detail": f"param '{name}' is required (no default)"})
            try:
                if ctype == "int":
                    val = int(val)
                elif ctype == "float":
                    val = float(val)
                elif ctype == "str":
                    val = str(val)
                elif ctype == "ts":
                    if val in ("", None):
                        val = None
                    else:
                        val = pd.Timestamp(val)
                else:
                    raise ValueError({"layer": layer, "param": name,
                                      "detail": f"unknown schema type {ctype!r}"})
            except (TypeError, ValueError) as exc:
                raise ValueError({"layer": layer, "param": name, "value": repr(val),
                                  "detail": f"param '{name}' expects {ctype}"}) from exc
            if ctype == "ts" and val is not None and val.tzinfo is None:
                raise ValueError({"layer": layer, "param": name,
                                  "detail": f"param '{name}' must be tz-aware UTC"})
            if "min" in spec and val < spec["min"]:
                raise ValueError({"layer": layer, "param": name, "value": val,
                                  "detail": f"param '{name}' must be >= {spec['min']}"})
            if "max" in spec and val > spec["max"]:
                raise ValueError({"layer": layer, "param": name, "value": val,
                                  "detail": f"param '{name}' must be <= {spec['max']}"})
            out[name] = val
        return out

    def _merged(self, history: list, bar, params: dict) -> dict:
        """因果守卫 + 合并构造参数与本次调用覆写参数（全量按 schema 重校验）。"""
        check_closed_window(history, bar, layer=f"strategies.{self.expert}")
        return self._validate({**self._params, **params}, self.PARAMS_SCHEMA,
                              layer=f"strategies.{self.expert}")

    # ------------------------------------------------------------------ #
    # 共享数值工具（复用 @as_of 特征：因果 by construction）
    # ------------------------------------------------------------------ #
    def atr(self, history: list, bar, period: int) -> float:
        """Wilder ATR（经 @as_of 装饰，未来 bar 会抛 LookAheadError）。

        历史不足时返回 NaN——调用方按「无信号」处理，绝不猜值。
        """
        return float(wilder_atr(history, bar.ts_utc, period=period))

    def make_signal(self, bar, *, direction: int, price_ref: float, atr0: float,
                    entry_dist_mult: float, l1_in_zone: bool,
                    regime_weights: dict,
                    meta_p: Optional[float] = None,
                    symbol: str = "XAUUSD") -> StrategySignal:
        """统一信号构造：entry_dist = entry_dist_mult × atr0（入场冻结）。"""
        return StrategySignal(
            signal_id=f"{symbol}_{bar.ts_utc.isoformat()}_{self.expert}_{direction}",
            bar_ts_utc=bar.ts_utc,
            expert=self.expert,
            direction=int(direction),
            price_ref=float(price_ref),
            atr0=float(atr0),
            entry_dist=float(entry_dist_mult) * float(atr0),
            l1_in_zone=bool(l1_in_zone),
            regime_weights=dict(regime_weights),
            meta_p=meta_p,
            strategy_version=self.strategy_version,
        )


__all__ = ["Strategy", "BaseStrategy", "check_closed_window"]
