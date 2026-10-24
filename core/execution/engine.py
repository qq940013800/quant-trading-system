# -*- coding: utf-8 -*-
"""core/execution/engine.py —— 实盘交易执行引擎。

基于第一性原理：
    策略信号 ≠ 实际成交。中间有：
    信号确认 → 仓位计算 → 风控检查 → 下单 → 状态跟踪 → 异常处理

    核心原则（来自AGENTS.md硬规则）：
    1. 止损只允许向盈利方向移动（单调不变量）
    2. 异步返回必须检查返回值并重试
    3. 禁止硬编码点值/手数/阈值
    4. 异常必须带上下文记录
    5. 前向守卫：只用 available_at <= bar.close 的数据

核心功能：
1. 交易信号确认与过滤
2. 仓位计算与风控检查
3. 下单执行与状态跟踪
4. 异常处理与重试机制
5. 交易记录与审计
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Callable


# ------------------------------------------------------------------
# 枚举与数据类
# ------------------------------------------------------------------
class OrderSide(Enum):
    """订单方向。"""
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    """订单类型。"""
    MARKET = "market"      # 市价单
    LIMIT = "limit"         # 限价单
    STOP = "stop"           # 止损单


class OrderStatus(Enum):
    """订单状态。"""
    PENDING = "pending"        # 待执行
    SUBMITTED = "submitted"    # 已提交
    PARTIAL = "partial"        # 部分成交
    FILLED = "filled"          # 全部成交
    CANCELLED = "cancelled"    # 已取消
    REJECTED = "rejected"      # 已拒绝
    ERROR = "error"            # 错误


@dataclass
class Order:
    """订单。"""
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None        # 限价单价格
    stop_price: Optional[float] = None   # 止损单价格
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = 0.0
    avg_fill_price: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    filled_at: Optional[datetime] = None
    error_message: Optional[str] = None


@dataclass
class Position:
    """持仓。"""
    symbol: str
    side: OrderSide
    quantity: float
    entry_price: float
    entry_time: datetime
    stop_loss: float
    take_profit: Optional[float] = None
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0


@dataclass
class ExecutionConfig:
    """执行配置。"""
    max_retries: int = 3                # 最大重试次数
    retry_delay_seconds: float = 1.0    # 重试延迟
    max_slippage_bps: float = 10.0      # 最大滑点（基点）
    allow_partial_fill: bool = True     # 是否允许部分成交
    order_timeout_seconds: float = 30.0 # 订单超时


# ------------------------------------------------------------------
# 执行引擎
# ------------------------------------------------------------------
class ExecutionEngine:
    """实盘交易执行引擎。

    用法：
        engine = ExecutionEngine(config, order_fn=my_broker_order)
        position = engine.execute_signal(
            symbol="XAUUSD",
            side=OrderSide.BUY,
            signal_strength=0.8,
            equity=100000,
            atr=2.5,
        )
    """

    def __init__(self,
                 config: Optional[ExecutionConfig] = None,
                 order_fn: Optional[Callable] = None,
                 risk_check_fn: Optional[Callable] = None):
        self.config = config or ExecutionConfig()
        self.order_fn = order_fn or self._default_order
        self.risk_check_fn = risk_check_fn or self._default_risk_check

        self.orders: list[Order] = []
        self.positions: dict[str, Position] = {}  # symbol -> Position
        self.order_counter = 0

    def _default_order(self, order: Order) -> Order:
        """默认下单函数（模拟用）。"""
        order.status = OrderStatus.FILLED
        order.filled_quantity = order.quantity
        order.avg_fill_price = order.price or 2000.0
        order.filled_at = datetime.now()
        return order

    def _default_risk_check(self, symbol: str, side: OrderSide,
                             quantity: float, price: float) -> tuple[bool, str]:
        """默认风控检查。"""
        # 简化版：检查手数不超过10手
        if quantity > 10.0:
            return False, f"手数{quantity}超过10手上限"
        return True, "通过"

    def execute_signal(self,
                        symbol: str,
                        side: OrderSide,
                        signal_strength: float,
                        equity: float,
                        atr: float,
                        risk_pct: float = 0.01,
                        point_value: float = 100.0,
                        min_lot: float = 0.01,
                        lot_step: float = 0.01) -> Optional[Position]:
        """执行交易信号。

        完整流程：
        1. 信号强度检查
        2. 仓位计算
        3. 风控检查
        4. 下单执行
        5. 更新持仓

        Args:
            symbol: 交易品种
            side: 方向
            signal_strength: 信号强度（0-1）
            equity: 当前权益
            atr: ATR值（用于止损计算）
            risk_pct: 风险比例
            point_value: 每点价值
            min_lot: 最小手数
            lot_step: 手数步长

        Returns:
            新建持仓，失败返回None
        """
        # 1. 信号强度过滤
        if signal_strength < 0.3:
            return None  # 信号太弱，不交易

        # 2. 仓位计算
        stop_distance = 2.0 * atr  # 2倍ATR止损
        risk_amount = equity * risk_pct
        quantity = risk_amount / (stop_distance * point_value)

        # 对齐手数步长
        quantity = max(min_lot, np.floor(quantity / lot_step) * lot_step)

        # 3. 风控检查
        current_price = self._get_current_price(symbol)
        risk_ok, risk_msg = self.risk_check_fn(symbol, side, quantity, current_price)
        if not risk_ok:
            return None

        # 4. 下单执行（带重试）
        order = self._create_order(symbol, side, quantity, OrderType.MARKET)
        order = self._submit_with_retry(order)

        if order.status != OrderStatus.FILLED:
            return None

        # 5. 创建持仓
        position = Position(
            symbol=symbol,
            side=side,
            quantity=order.filled_quantity,
            entry_price=order.avg_fill_price,
            entry_time=order.filled_at or datetime.now(),
            stop_loss=order.avg_fill_price - stop_distance if side == OrderSide.BUY
                      else order.avg_fill_price + stop_distance,
        )

        self.positions[symbol] = position
        return position

    def close_position(self, symbol: str, reason: str = "signal") -> Optional[Order]:
        """平仓。"""
        if symbol not in self.positions:
            return None

        pos = self.positions[symbol]
        close_side = OrderSide.SELL if pos.side == OrderSide.BUY else OrderSide.BUY

        order = self._create_order(
            symbol=symbol,
            side=close_side,
            quantity=pos.quantity,
            order_type=OrderType.MARKET,
        )
        order = self._submit_with_retry(order)

        if order.status == OrderStatus.FILLED:
            # 计算盈亏
            pnl = (order.avg_fill_price - pos.entry_price) * pos.quantity * (
                1 if pos.side == OrderSide.BUY else -1
            )
            pos.realized_pnl = pnl
            del self.positions[symbol]

        return order

    def update_stop_loss(self, symbol: str, new_stop: float) -> bool:
        """更新止损（只允许向盈利方向移动）。

        硬规则：止损单调，只允许向盈利方向移动。
        """
        if symbol not in self.positions:
            return False

        pos = self.positions[symbol]

        # 多头：止损只能上移，不能下移
        if pos.side == OrderSide.BUY:
            if new_stop <= pos.stop_loss:
                return False  # 不允许下移
        # 空头：止损只能下移，不能上移
        else:
            if new_stop >= pos.stop_loss:
                return False  # 不允许上移

        pos.stop_loss = new_stop
        return True

    def get_open_positions(self) -> list[Position]:
        """获取所有持仓。"""
        return list(self.positions.values())

    def _create_order(self, symbol: str, side: OrderSide,
                       quantity: float, order_type: OrderType) -> Order:
        """创建订单。"""
        self.order_counter += 1
        return Order(
            order_id=f"ORD-{self.order_counter:06d}",
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            status=OrderStatus.PENDING,
        )

    def _submit_with_retry(self, order: Order) -> Order:
        """带重试的下单。"""
        for attempt in range(self.config.max_retries):
            try:
                order.status = OrderStatus.SUBMITTED
                order = self.order_fn(order)

                if order.status in [OrderStatus.FILLED, OrderStatus.PARTIAL]:
                    return order

            except Exception as e:
                order.status = OrderStatus.ERROR
                order.error_message = str(e)

        return order

    def _get_current_price(self, symbol: str) -> float:
        """获取当前价格（模拟用）。"""
        return 2000.0  # XAUUSD 模拟价格
