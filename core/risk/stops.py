# -*- coding: utf-8 -*-
"""core.risk.stops —— 四级止损体系 + 止损单调不变量（硬规则 4）。

四级止损（基于第一性原理：不同失败模式需要不同止损）：
1. 时间止损：入场后 N 根 K 线没按预期走，时间成本也是成本
2. 价格止损（ATR）：核心止损，控制单笔风险
3. 信号止损：入场信号反转，逻辑失效就走
4. 跟踪止损：盈利后，止损随价格移动（锁定利润）

止损单调不变量：
- 多头：止损只允许上移（new_stop >= current_stop）；下移即放宽风险，抛 StopWideningError。
- 空头：止损只允许下移（new_stop <= current_stop）；上移即放宽风险，抛 StopWideningError。
- 入场止损由 frozen atr0/entry_dist 派生；R 倍数一律用入场冻结值。

对应黄金夹具 c03_stop_widen（反例：多头把 pos.stop 改到更低值 -> FAIL，必须被拒）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class StopWideningError(Exception):
    """止损被请求向放宽风险的方向移动。携带上下文，禁止裸抛/空 except（硬规则 9）。"""

    def __init__(self, current_stop: float, new_stop: float, direction: int,
                 symbol: str = "", ts_utc: str = "", detail: str = ""):
        self.current_stop = float(current_stop)
        self.new_stop = float(new_stop)
        self.direction = int(direction)
        self.context = {
            "layer": "risk.stops",
            "symbol": symbol,
            "ts_utc": str(ts_utc),
            "current_stop": self.current_stop,
            "new_stop": self.new_stop,
            "direction": self.direction,
            "detail": detail or "stop requested in risk-widening direction",
        }
        super().__init__(f"StopWidening: {self.context}")


class StopType(Enum):
    """止损类型（四级止损体系）。"""
    TIME = "time"           # 时间止损
    PRICE_ATR = "price_atr" # ATR 价格止损
    SIGNAL = "signal"       # 信号止损（入场逻辑反转）
    TRAILING = "trailing"   # 跟踪止损


@dataclass
class StopConfig:
    """止损配置参数（全部来自分布，非绩效调参——硬规则 3）。

    Attributes:
        atr_mult: ATR 倍数（价格止损距离 = atr_mult × ATR）
        max_holding_bars: 最大持有 K 线数（时间止损）
        breakeven_r: 达到多少 R 后移到保本
        breakeven_offset_r: 保本偏移（比如 +0.1R）
        trailing_activation_r: 达到多少 R 后启动跟踪止损
        trailing_offset_r: 跟踪止损偏移（比如 1.5R 跟踪在 1R 位置）
    """
    atr_mult: float = 2.0
    max_holding_bars: int = 20
    breakeven_r: float = 1.0
    breakeven_offset_r: float = 0.1
    trailing_activation_r: float = 2.0
    trailing_offset_r: float = 1.0


@dataclass
class StopState:
    """止损状态机（每笔交易的止损跟踪状态）。

    Attributes:
        entry_price: 入场价（冻结，不可变）
        direction: 方向（+1 多，-1 空）
        entry_atr: 入场时 ATR（冻结，不可变）
        entry_dist: 入场距离（冻结，= atr_mult × entry_atr）
        current_stop: 当前止损价
        bars_held: 已持有 K 线数
        max_favorable_r: 最大有利 R 倍数（跟踪止损用）
        stop_type: 当前生效的止损类型
    """
    entry_price: float
    direction: int
    entry_atr: float
    entry_dist: float
    current_stop: float
    bars_held: int = 0
    max_favorable_r: float = 0.0
    stop_type: StopType = StopType.PRICE_ATR

    def current_r(self) -> float:
        """当前浮动盈亏的 R 倍数。"""
        # 这个方法需要传入当前价格，在外部调用时计算
        raise NotImplementedError("Use compute_current_r instead")


def compute_current_r(entry_price: float, direction: int,
                      current_price: float, entry_dist: float) -> float:
    """计算当前浮动盈亏的 R 倍数。

    R = (当前价 - 入场价) × direction / entry_dist
    """
    return (current_price - entry_price) * direction / entry_dist


def initial_stop(entry_price: float, direction: int, entry_dist: float) -> float:
    """由入场价与冻结距离派生初始止损。

    direction=+1 多头：止损在 entry - entry_dist；direction=-1 空头：entry + entry_dist。
    entry_dist 必须是入场冻结值，禁止调用方传入重算后的 ATR。
    """
    if entry_dist <= 0:
        raise ValueError({"layer": "risk.stops", "detail":
                           f"entry_dist must be > 0, got {entry_dist}"})
    if direction not in (+1, -1):
        raise ValueError({"layer": "risk.stops", "detail":
                           f"direction must be +1/-1, got {direction}"})
    return float(entry_price) - float(direction) * float(entry_dist)


def update_stop(current_stop: float, new_stop: float, direction: int,
                symbol: str = "", ts_utc: str = "") -> float:
    """更新止损，只允许向盈利方向移动；放宽方向抛 StopWideningError。

    冻结接口（设计 3.2）：
        update_stop(current_stop, new_stop, direction) -> float
    额外的 symbol/ts_utc 仅用于异常上下文（硬规则 9），不改变判定语义。
    """
    cur = float(current_stop)
    new = float(new_stop)
    if direction == +1:
        # 多头：止损只能上移（抬高止损 = 锁定更多利润 / 缩小风险）
        if new < cur:
            raise StopWideningError(cur, new, direction, symbol, ts_utc,
                                   detail="long stop lowered (risk widened)")
    elif direction == -1:
        # 空头：止损只能下移（压低止损 = 锁定更多利润 / 缩小风险）
        if new > cur:
            raise StopWideningError(cur, new, direction, symbol, ts_utc,
                                   detail="short stop raised (risk widened)")
    else:
        raise ValueError({"layer": "risk.stops", "detail":
                           f"direction must be +1/-1, got {direction}"})
    return new


# ------------------------------------------------------------------
# 四级止损：时间止损
# ------------------------------------------------------------------
def check_time_stop(state: StopState, config: StopConfig) -> bool:
    """检查时间止损是否触发。

    规则：持有超过 max_holding_bars，且没达到 breakeven_r，就时间止损。
    逻辑：时间成本也是成本，资金不能浪费在不赚钱的交易上。

    Returns:
        True = 触发时间止损，应该平仓
    """
    return state.bars_held >= config.max_holding_bars and \
           state.max_favorable_r < config.breakeven_r


# ------------------------------------------------------------------
# 四级止损：信号止损
# ------------------------------------------------------------------
def check_signal_stop(direction: int, signal_reversed: bool) -> bool:
    """检查信号止损是否触发。

    规则：入场信号反转（比如看涨吞没后出现看跌吞没），就平仓。
    逻辑：入场的逻辑基础没了，就不要恋战。

    Args:
        direction: 持仓方向（+1 多，-1 空）
        signal_reversed: 信号是否反转

    Returns:
        True = 触发信号止损，应该平仓
    """
    return signal_reversed


# ------------------------------------------------------------------
# 四级止损：保本止损（盈利后移到保本）
# ------------------------------------------------------------------
def update_breakeven_stop(state: StopState, config: StopConfig) -> float | None:
    """盈利达到 breakeven_r 后，把止损移到保本价。

    规则：
    - 当前 R >= breakeven_r 时，止损移到 entry + breakeven_offset_r × entry_dist
    - 这样即使止损被扫，也不亏钱（或者小赚）

    Returns:
        新的止损价；如果还没达到保本条件，返回 None
    """
    current_r = state.max_favorable_r
    if current_r >= config.breakeven_r:
        # 止损移到保本价 + 偏移
        new_stop = state.entry_price + state.direction * config.breakeven_offset_r * state.entry_dist
        return new_stop
    return None


# ------------------------------------------------------------------
# 四级止损：跟踪止损（盈利后跟踪）
# ------------------------------------------------------------------
def update_trailing_stop(state: StopState, config: StopConfig) -> float | None:
    """盈利达到 trailing_activation_r 后，启动跟踪止损。

    规则：
    - 当前 R >= trailing_activation_r 时，启动跟踪
    - 跟踪止损 = 当前最高价 - trailing_offset_r × entry_dist（多头）
    - 跟踪止损 = 当前最低价 + trailing_offset_r × entry_dist（空头）

    Returns:
        新的止损价；如果还没达到跟踪条件，返回 None
    """
    current_r = state.max_favorable_r
    if current_r >= config.trailing_activation_r:
        # 跟踪止损：在最大有利位置往后退 trailing_offset_r
        new_stop = state.entry_price + state.direction * \
                   (state.max_favorable_r - config.trailing_offset_r) * state.entry_dist
        return new_stop
    return None


# ------------------------------------------------------------------
# 综合止损决策入口
# ------------------------------------------------------------------
def evaluate_stops(state: StopState, config: StopConfig,
                   current_price: float, signal_reversed: bool = False,
                   symbol: str = "", ts_utc: str = "") -> tuple[bool, float | None, StopType | None]:
    """综合评估四级止损，返回平仓决策和新止损价。

    优先级（从高到低）：
    1. 信号止损（逻辑失效，最优先）
    2. 时间止损（资金效率）
    3. 跟踪止损（锁定利润）
    4. 保本止损（不亏钱）
    5. ATR 价格止损（基础保护）

    Returns:
        (should_exit, new_stop, stop_type)
        - should_exit: 是否应该平仓
        - new_stop: 新的止损价（如果有更新）
        - stop_type: 触发的止损类型
    """
    # 更新最大有利 R
    current_r = compute_current_r(state.entry_price, state.direction,
                                  current_price, state.entry_dist)
    state.max_favorable_r = max(state.max_favorable_r, current_r)

    # 1. 信号止损（最高优先级）
    if check_signal_stop(state.direction, signal_reversed):
        return True, None, StopType.SIGNAL

    # 2. 时间止损
    if check_time_stop(state, config):
        return True, None, StopType.TIME

    # 3. 跟踪止损（先算，因为它可能是最新的止损）
    trailing_stop = update_trailing_stop(state, config)
    if trailing_stop is not None:
        new_stop = update_stop(state.current_stop, trailing_stop, state.direction,
                              symbol, ts_utc)
        state.current_stop = new_stop
        state.stop_type = StopType.TRAILING
        return False, new_stop, StopType.TRAILING

    # 4. 保本止损
    breakeven_stop = update_breakeven_stop(state, config)
    if breakeven_stop is not None:
        new_stop = update_stop(state.current_stop, breakeven_stop, state.direction,
                              symbol, ts_utc)
        state.current_stop = new_stop
        state.stop_type = StopType.PRICE_ATR  # 还是价格止损的一种
        return False, new_stop, StopType.PRICE_ATR

    # 5. 基础 ATR 价格止损（不需要更新，保持原样）
    return False, None, StopType.PRICE_ATR
