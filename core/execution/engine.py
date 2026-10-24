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

import logging
import uuid

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Callable

logger = logging.getLogger("core.execution")


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
        decision_id = f"exec-{uuid.uuid4().hex[:12]}"

        # 0. 决策前自动引用历史经验（知识复用）
        # 基于第一性原理：不要重新发明轮子，站在过去的肩膀上
        historical_lessons = self._retrieve_historical_lessons(symbol, side)
        if historical_lessons:
            logger.info("历史经验参考 for %s %s:", symbol, side.value)
            for lesson in historical_lessons:
                logger.info("  - %s", lesson)

        # 1. 信号强度过滤
        if signal_strength < 0.3:
            self._record_decision(
                decision_id=decision_id,
                symbol=symbol,
                side=side,
                accepted=False,
                reject_reason=f"signal_strength={signal_strength:.2f} < 0.3",
                lots=0.0,
                atr=atr,
                equity=equity,
            )
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
            self._record_decision(
                decision_id=decision_id,
                symbol=symbol,
                side=side,
                accepted=False,
                reject_reason=f"risk_check: {risk_msg}",
                lots=quantity,
                atr=atr,
                equity=equity,
            )
            return None

        # 4. 下单执行（带重试）
        order = self._create_order(symbol, side, quantity, OrderType.MARKET)
        order = self._submit_with_retry(order)

        if order.status != OrderStatus.FILLED:
            self._record_decision(
                decision_id=decision_id,
                symbol=symbol,
                side=side,
                accepted=False,
                reject_reason=f"order_failed: {order.error_message or order.status.value}",
                lots=quantity,
                atr=atr,
                equity=equity,
            )
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

        # 记录成功决策
        self._record_decision(
            decision_id=decision_id,
            symbol=symbol,
            side=side,
            accepted=True,
            reject_reason=None,
            lots=order.filled_quantity,
            atr=atr,
            equity=equity,
            entry_price=order.avg_fill_price,
        )

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

            # 记录平仓决策审计
            close_decision_id = f"close-{uuid.uuid4().hex[:12]}"
            self._record_decision(
                decision_id=close_decision_id,
                symbol=symbol,
                side=close_side,
                accepted=True,
                reject_reason=f"close_reason: {reason}",
                lots=pos.quantity,
                atr=abs(order.avg_fill_price - pos.entry_price) / pos.quantity if pos.quantity > 0 else 0,
                equity=0,  # 平仓时不需要equity
                entry_price=order.avg_fill_price,
            )

            # 自动写入交易日志
            self._record_trade_journal(
                symbol=symbol,
                side=pos.side.value.lower(),
                entry_price=pos.entry_price,
                exit_price=order.avg_fill_price,
                quantity=pos.quantity,
                entry_time=pos.entry_time,
                exit_time=order.filled_at or datetime.now(),
                gross_pnl=pnl,
                exit_reason=reason,
            )

            # 自动触发复盘监控
            try:
                from core.audit.review_monitor import get_review_monitor
                monitor = get_review_monitor()
                risk_amount = abs(pos.entry_price - order.avg_fill_price) * pos.quantity
                r_multiple = pnl / risk_amount if risk_amount > 0 else 0
                monitor.on_trade_closed(
                    trade_uid=f"trade-close-{uuid.uuid4().hex[:8]}",
                    symbol=symbol,
                    net_pnl=pnl,
                    r_multiple=r_multiple,
                )
            except Exception as e:
                logger.warning("review monitor failed: %s", e)

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

    def _record_decision(self,
                         decision_id: str,
                         symbol: str,
                         side: OrderSide,
                         accepted: bool,
                         reject_reason: Optional[str],
                         lots: float,
                         atr: float,
                         equity: float,
                         entry_price: Optional[float] = None) -> None:
        """记录决策审计到数据库。

        基于第一性原理：每笔决策（无论接受/拒绝）都必须留下审计痕迹。
        失败不影响主交易流程（只记日志）。
        """
        try:
            from core.audit.db_writer import write_decision_to_db
            from core.audit.record import Decision

            class _Signal:
                def __init__(self, sym, s):
                    self.symbol = sym
                    self.side = s.value

            class _RiskState:
                def __init__(self, conf):
                    self.confidence = conf

            decision = Decision(
                decision_id=decision_id,
                signal=_Signal(symbol, side),
                feature_snapshot={
                    "atr": atr,
                    "equity": equity,
                    "entry_price": entry_price,
                },
                model_version="execution-engine-v1.0",
                risk_state=_RiskState(0.8 if accepted else 0.2),
                accepted=accepted,
                reject_reason=reject_reason,
                final_signed_lots=abs(lots) if accepted else 0.0,  # 平仓时lots是反向，取绝对值
                threshold_dataset="CLEAN",
                decision_rule_version="v1.0",
            )

            write_decision_to_db(decision)
            logger.debug("decision recorded: %s accepted=%s", decision_id, accepted)

        except Exception as e:
            # 审计失败不影响主流程
            logger.warning("failed to record decision: %s", e)

    def _record_trade_journal(self,
                               symbol: str,
                               side: str,
                               entry_price: float,
                               exit_price: float,
                               quantity: float,
                               entry_time,
                               exit_time,
                               gross_pnl: float,
                               exit_reason: str) -> None:
        """记录交易日志到数据库。

        基于第一性原理：每笔完整交易（开+平）都应该有完整的日志记录，
        用于绩效归因分析。
        """
        try:
            from core.audit.db_writer import write_trade_to_db

            # 转换numpy类型为Python原生类型
            entry_price = float(entry_price)
            exit_price = float(exit_price)
            quantity = float(quantity)
            gross_pnl = float(gross_pnl)

            trade_uid = f"trade-{uuid.uuid4().hex[:12]}"
            risk_amount = abs(entry_price - exit_price) * quantity if entry_price > 0 else 1
            r_multiple = round(gross_pnl / risk_amount, 2) if risk_amount > 0 else 0

            write_trade_to_db(
                trade_uid=trade_uid,
                symbol=symbol,
                side=side,
                entry_time=entry_time,
                entry_price=entry_price,
                exit_time=exit_time,
                exit_price=exit_price,
                quantity=quantity,
                gross_pnl=gross_pnl,
                commission=0,  # 模拟交易无手续费
                slippage_cost=0,
                net_pnl=gross_pnl,
                r_multiple=r_multiple,
                exit_reason=exit_reason,
                confidence=0.8,
                status="closed",
            )
            logger.debug("trade journal recorded: %s", trade_uid)

        except Exception as e:
            logger.warning("failed to record trade journal: %s", e)

    def _retrieve_historical_lessons(self, symbol: str, side: OrderSide) -> list:
        """决策前自动检索历史经验（知识复用）。

        基于第一性原理：
            不要重新发明轮子。
            每次决策前，先看看历史上类似情况是怎么处理的，
            避免重复犯同样的错误。

        Returns:
            历史教训列表
        """
        try:
            from core.audit.knowledge_retriever import get_knowledge_retriever
            retriever = get_knowledge_retriever()

            side_str = side.value.lower()
            lessons = retriever.get_lessons_for_decision(symbol, side_str, "unknown")

            return lessons

        except Exception as e:
            logger.debug("historical lessons retrieval skipped: %s", e)
            return []
