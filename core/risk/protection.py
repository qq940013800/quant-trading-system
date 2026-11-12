# -*- coding: utf-8 -*-
"""core.risk.protection —— 持仓保护裁决纯函数（吊灯退出 / 分批止盈 / 利润回吐）。

口径基准与 ``core.risk.stops`` 对齐：

- ``entry_atr``(atr0)、``entry_dist`` 入场冻结，R 倍数一律用冻结 ``entry_dist``；
- 止损只允许向盈利方向移动，单调性校验复用 ``stops.update_stop``；
- 本模块只产出「应把止损移到哪 / 减多少 / 是否清剩余」的裁决，
  不持有资金、不下单、不写库（对齐设计稿边界原则）。

阈值（``level_r`` / ``ratio`` / ``chandelier_atr_mult`` / ``retracement_pct``）
均由调用方按分布校准后传入；底座不写死经验数值（硬规则 3：阈值来自分布）。
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .stops import (
    StopState,
    StopConfig,
    evaluate_stops,
    compute_current_r,
    update_stop,
)


def _finite(name: str, val: float) -> float:
    v = float(val)
    if not math.isfinite(v):
        raise ValueError({"layer": "risk.protection", "detail":
                          f"{name} must be finite, got {val!r}"})
    return v


# ------------------------------------------------------------------
# 吊灯退出（Chandelier Exit）
# ------------------------------------------------------------------
def evaluate_chandelier(peak_price: float, direction: int, entry_atr: float,
                        chandelier_atr_mult: float, current_stop: float) -> float | None:
    """吊灯止损候选价：从峰值回撤 ``atr0 × chandelier_atr_mult``。

    - 多头：``peak - atr0×mult``；空头：``peak + atr0×mult``。
    - 仅当候选价比当前止损更优（向盈利方向收紧）才返回；否则返回 None，
      调用方不得据此放宽风险。
    - 激活态（跟踪止损是否已启动）由编排层判断，本函数不判断激活。

    Returns:
        候选止损价；不优于当前止损时返回 None。
    """
    peak = _finite("peak_price", peak_price)
    atr0 = _finite("entry_atr", entry_atr)
    mult = _finite("chandelier_atr_mult", chandelier_atr_mult)
    cur = _finite("current_stop", current_stop)
    if atr0 <= 0:
        raise ValueError({"layer": "risk.protection", "detail":
                          f"entry_atr must be > 0, got {atr0!r}"})
    if mult <= 0:
        raise ValueError({"layer": "risk.protection", "detail":
                          f"chandelier_atr_mult must be > 0, got {mult!r}"})
    if direction not in (+1, -1):
        raise ValueError({"layer": "risk.protection", "detail":
                          f"direction must be +1/-1, got {direction}"})

    dist = atr0 * mult
    if direction == +1:
        candidate = peak - dist
        return candidate if candidate > cur else None
    candidate = peak + dist
    return candidate if candidate < cur else None


# ------------------------------------------------------------------
# 分批止盈（Scale Out）
# ------------------------------------------------------------------
@dataclass(frozen=True)
class ScaleOutRule:
    """单档分批止盈规则：达到 ``level_r`` 平掉 ``ratio`` 比例仓位。"""
    level_r: float
    ratio: float

    def __post_init__(self) -> None:
        lr = _finite("level_r", self.level_r)
        rt = _finite("ratio", self.ratio)
        if lr < 0:
            raise ValueError({"layer": "risk.protection", "detail":
                              f"level_r must be >= 0, got {lr!r}"})
        if not (0 < rt <= 1):
            raise ValueError({"layer": "risk.protection", "detail":
                              f"ratio must be in (0, 1], got {rt!r}"})
        object.__setattr__(self, "level_r", lr)
        object.__setattr__(self, "ratio", rt)


@dataclass
class ScaleOutResult:
    """分批止盈裁决结果。"""
    triggered: bool
    level_r: float | None
    reduce_ratio: float
    remaining_ratio: float
    done: list[bool]


def evaluate_scale_out(r_current: float, rules: list[ScaleOutRule],
                       done: list[bool], remaining_ratio: float) -> ScaleOutResult:
    """分批止盈裁决：``r_current ≥ level_r`` 且未完成的首个级别触发。

    - 同一根 bar 只推进一个未完成级别；已完成级别跳过，不重复减仓。
    - 触发后新剩余比例 = ``remaining_ratio × (1 - ratio)``。

    Args:
        r_current: 当前浮动 R 倍数（冻结 entry_dist 口径）。
        rules: 分批规则，按 level_r 升序排列。
        done: 与 rules 等长的完成标记（会被复制后返回，不改入参）。
        remaining_ratio: 当前剩余仓位比例，∈ (0, 1]。
    """
    r = _finite("r_current", r_current)
    rem = _finite("remaining_ratio", remaining_ratio)
    if not (0 < rem <= 1):
        raise ValueError({"layer": "risk.protection", "detail":
                          f"remaining_ratio must be in (0, 1], got {rem!r}"})
    if len(done) != len(rules):
        raise ValueError({"layer": "risk.protection", "detail":
                          f"done length {len(done)} != rules length {len(rules)}"})

    done_copy = list(done)
    for i, rule in enumerate(rules):
        if done_copy[i]:
            continue
        if r >= rule.level_r:
            done_copy[i] = True
            new_rem = rem * (1 - rule.ratio)
            return ScaleOutResult(True, rule.level_r, rule.ratio, new_rem, done_copy)
    return ScaleOutResult(False, None, 0.0, rem, done_copy)


# ------------------------------------------------------------------
# 利润回吐保护（Profit Retracement）
# ------------------------------------------------------------------
def evaluate_profit_retracement(current_profit: float, peak_profit: float,
                                r_current: float, min_r: float,
                                retracement_pct: float) -> bool:
    """利润回吐保护：峰值利润回撤 ≥ ``retracement_pct`` 且当前仍盈利、r≥min_r 才触发清剩余。

    与后端 ``_check_profit_retracement`` 口径对齐：r 未达 ``min_r`` 不启用；
    峰值利润或当前利润非正不触发；回撤比例 = ``(peak - current) / peak``。
    """
    cp = _finite("current_profit", current_profit)
    pp = _finite("peak_profit", peak_profit)
    r = _finite("r_current", r_current)
    mr = _finite("min_r", min_r)
    pct = _finite("retracement_pct", retracement_pct)
    if mr < 0:
        raise ValueError({"layer": "risk.protection", "detail":
                          f"min_r must be >= 0, got {mr!r}"})
    if not (0 <= pct <= 1):
        raise ValueError({"layer": "risk.protection", "detail":
                          f"retracement_pct must be in [0, 1], got {pct!r}"})

    if pp <= 0 or cp <= 0 or r < mr:
        return False
    retracement = (pp - cp) / pp
    return retracement >= pct


# ------------------------------------------------------------------
# 统一保护决策快照（审计可回放）
# ------------------------------------------------------------------
@dataclass(frozen=True)
class ProtectionDecision:
    """持仓保护裁决的统一审计快照。

    Attributes:
        action: ``hold`` / ``move_stop`` / ``reduce`` / ``close``。
        source: 触发来源（chandelier / scale_out / profit_retracement / 既有止损类型）。
        new_stop: 建议的新止损价（仅 move_stop 时有值）。
        reduce_ratio: 本轮建议减仓比例（仅 reduce 时有值）。
        close: 是否建议清剩余仓位。
        audit: 可回放的上下文快照（入场冻结值、峰值、当前 R 等）。
    """
    action: str
    source: str | None
    new_stop: float | None
    reduce_ratio: float
    close: bool
    audit: dict

    def __post_init__(self) -> None:
        if self.action not in ("hold", "move_stop", "reduce", "close"):
            raise ValueError({"layer": "risk.protection", "detail":
                              f"invalid action {self.action!r}"})
        if not (0 <= self.reduce_ratio <= 1):
            raise ValueError({"layer": "risk.protection", "detail":
                              f"reduce_ratio must be in [0, 1], got {self.reduce_ratio!r}"})
        if not isinstance(self.close, bool):
            raise ValueError({"layer": "risk.protection", "detail":
                              f"close must be bool, got {self.close!r}"})


# ------------------------------------------------------------------
# 统一保护裁决编排入口
# ------------------------------------------------------------------
def decide_protection(
    state: StopState,
    config: StopConfig,
    current_price: float,
    signal_reversed: bool = False,
    *,
    peak_price: float | None = None,
    peak_profit: float | None = None,
    current_profit: float | None = None,
    chandelier_atr_mult: float | None = None,
    trailing_activated: bool = False,
    scale_rules: list[ScaleOutRule] | None = None,
    scale_done: list[bool] | None = None,
    remaining_ratio: float = 1.0,
    retracement_pct: float | None = None,
    retracement_min_r: float = 1.0,
    symbol: str = "",
    ts_utc: str = "",
) -> ProtectionDecision:
    """统一保护裁决编排：组合四级止损与吊灯/分批/回吐保护，输出审计快照。

    优先级（从高到低）：信号/时间止损平仓 > 利润回吐清剩余 > 分批止盈减仓
    > 吊灯/跟踪/保本收紧止损 > 持有。

    纯函数编排：止损判定与三类保护裁决全部复用既有纯函数；本函数不持有资金、
    不下单、不写库。跟踪/吊灯是否启用由编排层经 ``trailing_activated`` 与可选
    参数传入；阈值参数由调用方按分布校准，底座不写死经验数值。

    Args:
        state: 止损状态（``evaluate_stops`` 就地刷新 max_favorable_r/current_stop）。
        config: 止损配置（分布校准产物）。
        current_price: 当前已收盘 bar 价格。
        signal_reversed: 入场信号是否反转。
        peak_price: 持仓峰值价（吊灯用）；None 则不评估吊灯。
        peak_profit/current_profit: 峰值/当前浮动盈亏（回吐保护用）。
        chandelier_atr_mult: 吊灯 ATR 倍数；None 则不评估吊灯。
        trailing_activated: 跟踪止损是否已激活（吊灯启用前提）。
        scale_rules/scale_done/remaining_ratio: 分批规则、完成标记、剩余比例。
        retracement_pct: 回吐容忍比例；None 则不评估回吐保护。
        retracement_min_r: 回吐保护启用的最低 R。
    """
    should_exit, new_stop, stop_type = evaluate_stops(
        state, config, current_price, signal_reversed, symbol, ts_utc,
    )
    r_current = compute_current_r(
        state.entry_price, state.direction, current_price, state.entry_dist,
    )
    audit: dict = {
        "symbol": symbol,
        "ts_utc": str(ts_utc),
        "entry_price": state.entry_price,
        "direction": state.direction,
        "entry_atr": state.entry_atr,
        "entry_dist": state.entry_dist,
        "current_price": current_price,
        "r_current": r_current,
        "max_favorable_r": state.max_favorable_r,
        "bars_held": state.bars_held,
        "remaining_ratio": remaining_ratio,
    }
    stop_source = stop_type.value if stop_type is not None else "stop"

    # 1. 信号 / 时间止损：平仓（最高优先级）
    if should_exit:
        audit["stop_type"] = stop_source
        return ProtectionDecision(
            action="close", source=stop_source, new_stop=None,
            reduce_ratio=0.0, close=True, audit=audit,
        )

    # 2. 利润回吐保护：清剩余
    if retracement_pct is not None and peak_profit is not None \
            and current_profit is not None:
        if evaluate_profit_retracement(
            current_profit, peak_profit, r_current,
            retracement_min_r, retracement_pct,
        ):
            audit["peak_profit"] = peak_profit
            audit["current_profit"] = current_profit
            return ProtectionDecision(
                action="close", source="profit_retracement",
                new_stop=None, reduce_ratio=0.0, close=True, audit=audit,
            )

    # 3. 分批止盈：减仓（可与止损收紧并存，action 取 reduce）
    if scale_rules:
        done = list(scale_done) if scale_done else [False] * len(scale_rules)
        scale_result = evaluate_scale_out(
            r_current, scale_rules, done, remaining_ratio,
        )
        if scale_result.triggered:
            audit["new_remaining_ratio"] = scale_result.remaining_ratio
            audit["scale_out_done"] = scale_result.done
            return ProtectionDecision(
                action="reduce", source="scale_out",
                new_stop=new_stop,
                reduce_ratio=scale_result.reduce_ratio,
                close=False, audit=audit,
            )

    # 4. 吊灯退出（跟踪激活后；候选须优于既有止损才覆盖）
    existing_stop = new_stop if new_stop is not None else state.current_stop
    if trailing_activated and chandelier_atr_mult is not None \
            and peak_price is not None:
        cand = evaluate_chandelier(
            peak_price, state.direction, state.entry_atr,
            chandelier_atr_mult, existing_stop,
        )
        if cand is not None:
            cand = update_stop(existing_stop, cand, state.direction, symbol, ts_utc)
            state.current_stop = cand
            audit["peak_price"] = peak_price
            return ProtectionDecision(
                action="move_stop", source="chandelier",
                new_stop=cand, reduce_ratio=0.0, close=False, audit=audit,
            )

    # 5. 既有跟踪 / 保本止损收紧
    if new_stop is not None:
        audit["stop_type"] = stop_source
        return ProtectionDecision(
            action="move_stop", source=stop_source, new_stop=new_stop,
            reduce_ratio=0.0, close=False, audit=audit,
        )

    # 6. 持有
    return ProtectionDecision(
        action="hold", source=None, new_stop=None,
        reduce_ratio=0.0, close=False, audit=audit,
    )
