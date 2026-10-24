# -*- coding: utf-8 -*-
"""core.risk.circuit —— 日内权益熔断三态机。

状态（设计①/⑥）：
    normal   正常交易
    breaker  当日回撤触及阈值：禁止新开仓，只允许平仓
    cooldown 熔断冷却：仍禁止新开仓，直到次一交易日边界重置回 normal

阈值来自 config（daily_loss_limit），不硬编码；当日基准权益按交易日边界记录。
"""
from __future__ import annotations

import enum
from dataclasses import dataclass


class CircuitState(str, enum.Enum):
    NORMAL = "normal"
    BREAKER = "breaker"
    COOLDOWN = "cooldown"


@dataclass
class CircuitBreaker:
    """日内权益熔断机。基于 bar 时间推进（回测）/ OnTimer（实盘 EA 等价）。

    参数（全部来自 config）：
        daily_loss_limit: 当日允许最大回撤（相对日初权益），如 0.03 = 3%
        cooldown_bars:    触发 breaker 后经过多少根 bar 进入 cooldown（冷却仍禁新开仓）
    """

    daily_loss_limit: float
    cooldown_bars: int = 12

    def __post_init__(self) -> None:
        if not 0.0 < self.daily_loss_limit < 1.0:
            raise ValueError({"layer": "risk.circuit", "detail":
                               f"daily_loss_limit out of (0,1): {self.daily_loss_limit}"})
        self._state = CircuitState.NORMAL
        self._day_key: object = None       # 当前交易日标识（日期）
        self._day_open_equity: float = 0.0
        self._bars_in_breaker: int = 0

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def state_name(self) -> str:
        return self._state.value

    @property
    def allows_new_position(self) -> bool:
        """熔断/冷却态一律禁止新开仓。"""
        return self._state == CircuitState.NORMAL

    def _trading_day(self, ts_utc) -> object:
        # 用 UTC 日期作为交易日键；实盘由经纪商服务器日边界配置覆盖（硬规则 6：偏移一致）
        return pd_ts_date(ts_utc)

    def update(self, equity: float, ts_utc) -> str:
        """每根已收盘 bar 调用一次，推进状态机。返回当前状态名。"""
        day = self._trading_day(ts_utc)

        # 次一交易日边界：重置回 normal（冷却/熔断跨日后自然解除）
        if self._day_key is None:
            self._day_key = day
            self._day_open_equity = float(equity)
        elif day != self._day_key:
            self._day_key = day
            self._day_open_equity = float(equity)
            self._state = CircuitState.NORMAL
            self._bars_in_breaker = 0

        dd = (float(equity) - self._day_open_equity) / self._day_open_equity \
            if self._day_open_equity > 0 else 0.0

        if self._state == CircuitState.NORMAL:
            if dd <= -self.daily_loss_limit:
                self._state = CircuitState.BREAKER
                self._bars_in_breaker = 0
        elif self._state == CircuitState.BREAKER:
            self._bars_in_breaker += 1
            if self._bars_in_breaker >= self.cooldown_bars:
                self._state = CircuitState.COOLDOWN
        elif self._state == CircuitState.COOLDOWN:
            # 冷却态继续禁止新开仓；直到交易日边界重置（上方）
            pass

        return self._state.value


def pd_ts_date(ts_utc):
    """取出 Timestamp 的日期部分作为交易日键（容忍 naive/aware）。"""
    return ts_utc.date() if hasattr(ts_utc, "date") else str(ts_utc)[:10]
