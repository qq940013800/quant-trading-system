# -*- coding: utf-8 -*-
"""core.strategies.supply_demand —— 供需区策略（KNOWN 集构建、交易段使用）。

集合分离（AGENTS.md 硬规则 2，研究结论 K04：consolidation→impulse→回访）：
- **供需区只在 KNOWN 集上构建**。机制：通过 param ``known_end_ts`` 传入 KNOWN
  集最后一根 bar 的 tz-aware UTC 时间戳；任何 ``bar.ts_utc > known_end_ts``
  的位置一律只「使用」既有 zone 判定 l1_in_zone，绝不「构建」新 zone。
  ``known_end_ts=None``（schema 默认空串）表示当前整段都是 KNOWN 集
  （显式回测/测试用；真实交易段必须由调用方显式传入边界）。
- **结构**：consolidation（cons_bars 根窄幅盘整）→ impulse（幅度严格大于
  历史 |close-to-close| 位移分布 impulse_quantile 分位的单 bar 推动）。
  impulse 收盘当根完成 zone 构建；zone = 盘整段 [min low, max high]，
  方向由 impulse 阴阳决定（向上推动=需求 zone 做多，向下=供给 zone 做空）。
- **阈值来自分布**：impulse 幅度阈值 = 截至当前 bar 的过去位移 expanding
  分位（参数 impulse_quantile），不由绩效网格搜索产生（不变量 3）。
- **zone 有效期** zone_valid_bars：按调用计数过期，过期后自动失效。

因果（硬规则 1/5）：impulse 只能是「当前已收盘 bar」，consolidation 只取
当前 bar 之前的 history；ATR 经 @as_of 装饰，混入未来 bar 会抛
LookAheadError；基类另守卫 history 末元素 == 当前 bar。

状态账本：zone 列表保存在策略实例内（路径依赖，任务约定）——同一实例按
时间顺序喂同一段 bar 序列得到完全相同的 zone 账本；重放审计应从同一
快照实例开始（实例内 zone 不参与信号数值计算，仅做区域判定）。
"""
from __future__ import annotations

import numpy as np

from .base import BaseStrategy


class SupplyDemandStrategy(BaseStrategy):
    """盘整→推动→回访供需区策略。"""

    expert = "supply_demand"
    strategy_version = "supply_demand-v1"
    PARAMS_SCHEMA = {
        "cons_bars": {"type": "int", "default": 8, "min": 3,
                      "desc": "盘整段根数（impulse 之前）"},
        "impulse_quantile": {"type": "float", "default": 0.75, "min": 0.5,
                             "max": 0.99,
                             "desc": "impulse 幅度在过去位移分布中的分位阈值（分布派生）"},
        "zone_valid_bars": {"type": "int", "default": 48, "min": 1,
                            "desc": "zone 有效期（bar 计数）"},
        "atr_n": {"type": "int", "default": 14, "min": 2,
                  "desc": "ATR 周期（CLEAN 集分布校准）"},
        "entry_dist_mult": {"type": "float", "default": 2.0, "min": 0.1,
                            "desc": "入场到止损距离 = mult × ATR"},
        "symbol": {"type": "str", "default": "XAUUSD",
                   "desc": "signal_id 前缀"},
        "known_end_ts": {"type": "ts", "default": "",
                         "desc": "KNOWN 集边界（ISO 时间戳）；空=整段 KNOWN"},
    }

    def __init__(self, **params):
        super().__init__(**params)
        # zone 账本：[{bottom, top, side, build_len, build_ts}]，按构建顺序
        self.zones: list = []

    def requires_features(self) -> list[str]:
        return ["wilder_atr"]

    # ------------------------------------------------------------------ #
    # 内部
    # ------------------------------------------------------------------ #
    def _build_zone_if_impulse(self, history: list, bar, p: dict) -> None:
        """当前 bar 若构成 impulse，则在 KNOWN 纪律下登记新 zone。"""
        cons_bars = p["cons_bars"]
        if len(history) < cons_bars + 2:
            return
        closes = np.fromiter((float(b.close) for b in history),
                             dtype=np.float64, count=len(history))
        moves = np.abs(np.diff(closes))
        past = moves[:-1]
        if past.size < cons_bars:
            return
        cur_move = float(moves[-1])
        threshold = float(np.quantile(past, p["impulse_quantile"]))
        if not cur_move > threshold:   # 严格大于：平盘/微弱位移不构 impulse
            return
        # 「盘整→推动」几何签名：推动幅度必须明显大于盘整段自身波幅，
        # 否则连续上行的每根 bar 都会被误判成 impulse（zone 污染）。
        cons = history[-(cons_bars + 1):-1]
        cons_range = float(max(b.high for b in cons)
                           - min(b.low for b in cons))
        if not cons_range < cur_move:
            return
        # KNOWN 集纪律：impulse bar 与整个盘整段都必须在 KNOWN 边界内
        known_end = p["known_end_ts"]
        if known_end is not None:
            if bar.ts_utc > known_end:
                return
            for b in history[-(cons_bars + 1):-1]:
                if b.ts_utc > known_end:
                    return
        cons = history[-(cons_bars + 1):-1]
        zone = {
            "bottom": float(min(b.low for b in cons)),
            "top": float(max(b.high for b in cons)),
            "side": "demand" if closes[-1] > closes[-2] else "supply",
            "build_len": len(history),
            "build_ts": bar.ts_utc,
        }
        self.zones.append(zone)

    def _expire_zones(self, history_len: int, p: dict) -> None:
        valid = p["zone_valid_bars"]
        self.zones = [z for z in self.zones
                      if history_len - z["build_len"] <= valid]

    def _zone_at(self, price: float):
        """最近一个包含 price 的未过期 zone（无则 None）。"""
        for z in reversed(self.zones):
            if z["bottom"] <= price <= z["top"]:
                return z
        return None

    # ------------------------------------------------------------------ #
    # 统一接口
    # ------------------------------------------------------------------ #
    def on_bar_close(self, history: list, bar, **params):
        p = self._merged(history, bar, params)

        # 1. 构建 zone（仅 KNOWN 集；交易段只使用不构建）
        self._build_zone_if_impulse(history, bar, p)
        # 2. 过期清理
        self._expire_zones(len(history), p)
        # 3. 回访判定 + 信号（ATR 不足时只维护 zone，不出信号）
        atr0 = self.atr(history, bar, p["atr_n"])
        if not np.isfinite(atr0) or atr0 <= 0:
            return None
        price = float(bar.close)
        zone = self._zone_at(price)
        if zone is None:
            return None
        direction = 1 if zone["side"] == "demand" else -1
        return self.make_signal(
            bar, direction=direction, price_ref=price, atr0=atr0,
            entry_dist_mult=p["entry_dist_mult"], l1_in_zone=True,
            regime_weights={"trend": 0.0, "mr": 0.0, "range": 1.0},
            symbol=p["symbol"])


__all__ = ["SupplyDemandStrategy"]
