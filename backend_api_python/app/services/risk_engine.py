"""
后端风控引擎 —— 止损强制执行 + 组合风险监控

第一性原理：
1. 人会"再等等"，真到止损的时候下不去手 → 止损必须在后端强制执行
2. 止损只允许向盈利方向移动（单调止损）→ 防止被来回打脸
3. R倍数用入场冻结的atr0/entryDist计算 → 保证盈亏比一致
4. 组合层面最大回撤控制 → 防止一次大亏毁掉十年复利

全球顶级机构实践：
- Citadel：风控前置，订单发出前就拦截
- Renaissance：严格的止损纪律，不允许人工干预
- Jane Street：风险限额系统，自动触发平仓
"""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.utils.logger import get_logger

logger = get_logger(__name__)


class RiskLevel(Enum):
    """风险等级"""
    GREEN = "green"      # 安全
    YELLOW = "yellow"    # 警告
    RED = "red"          # 危险


class StopLossType(Enum):
    """止损类型"""
    FIXED = "fixed"           # 固定价格止损
    ATR = "atr"               # ATR动态止损
    TRAILING = "trailing"     # 追踪止损
    BREAKEVEN = "breakeven"   # 保本止损


@dataclass
class Position:
    """持仓"""
    position_id: str
    strategy_id: int
    symbol: str
    side: str  # long / short
    entry_price: float
    quantity: float
    entry_time: datetime
    atr_at_entry: float = 0.0  # 入场时的ATR（冻结）
    entry_dist: float = 0.0     # 入场时的止损距离（冻结）

    # 止损配置
    stop_loss_price: float = 0.0
    stop_loss_type: StopLossType = StopLossType.ATR
    atr_multiplier: float = 2.0
    trailing_activated: bool = False
    trailing_activation_r: float = 1.0  # 达到1R后激活追踪止损
    trailing_distance_atr: float = 2.0  # 追踪距离（ATR倍数）

    # 当前状态
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    r_multiple: float = 0.0
    peak_price: float = 0.0  # 持仓期间最高/最低价（用于追踪止损）

    # 风控状态
    risk_level: RiskLevel = RiskLevel.GREEN
    stop_loss_hit: bool = False


@dataclass
class RiskConfig:
    """风控配置"""
    # 单笔交易风险
    max_risk_per_trade_pct: float = 1.0  # 单笔最大风险（占总资金%）

    # 组合层面风险
    max_drawdown_pct: float = 20.0       # 最大回撤阈值
    daily_loss_limit_pct: float = 5.0    # 单日亏损限制
    max_open_positions: int = 10          # 最大同时持仓数

    # 止损规则
    enable_stop_loss_enforcement: bool = True  # 是否启用止损强制执行
    stop_loss_check_interval_sec: float = 1.0  # 止损检查间隔（秒）
    max_slippage_pct: float = 0.1       # 最大滑点容忍

    # 追踪止损
    trailing_activation_r: float = 1.0   # 达到多少R后激活追踪止损
    trailing_atr_mult: float = 2.0       # 追踪距离ATR倍数


@dataclass
class RiskAlert:
    """风控告警"""
    alert_id: str
    timestamp: datetime
    level: RiskLevel
    alert_type: str  # stop_loss_hit / drawdown_warning / position_limit / etc.
    message: str
    position_id: Optional[str] = None
    symbol: Optional[str] = None
    action_required: str = ""  # close_position / reduce_position / monitor


class RiskEngine:
    """
    后端风控引擎 —— 止损强制执行

    核心原则：
    1. 止损是硬规则，不是建议。到了就必须平，没有"再等等"。
    2. 止损只允许向盈利方向移动。
    3. R倍数用入场时冻结的ATR计算，不随当前ATR变化。
    4. 组合层面有总回撤控制，到了就全部平仓。
    """

    def __init__(self, config: Optional[RiskConfig] = None):
        self.config = config or RiskConfig()
        self.positions: Dict[str, Position] = {}
        self.alerts: List[RiskAlert] = []
        self.lock = threading.RLock()

        # 组合状态
        self.initial_equity: float = 100000.0  # 初始资金
        self.current_equity: float = 100000.0
        self.peak_equity: float = 100000.0
        self.current_drawdown: float = 0.0
        self.daily_pnl: float = 0.0
        self.last_reset_date: str = ""

        # 回调函数（由执行层注入）
        self._close_position_callback: Optional[Callable[[str, str, float], bool]] = None
        self._reduce_position_callback: Optional[Callable[[str, float, str], bool]] = None
        self._alert_callback: Optional[Callable[[RiskAlert], None]] = None

        # 运行状态
        self._running = False
        self._check_thread: Optional[threading.Thread] = None

    def set_close_position_callback(self, callback: Callable[[str, str, float], bool]):
        """设置平仓回调（由执行层注入）
        callback(position_id, reason, price) -> bool
        """
        self._close_position_callback = callback

    def set_reduce_position_callback(self, callback: Callable[[str, float, str], bool]):
        """设置减仓回调
        callback(position_id, ratio, reason) -> bool
        """
        self._reduce_position_callback = callback

    def set_alert_callback(self, callback: Callable[[RiskAlert], None]):
        """设置告警回调"""
        self._alert_callback = callback

    def register_position(self, position: Position):
        """注册新持仓"""
        with self.lock:
            # 初始化止损价
            if position.stop_loss_price == 0.0 and position.atr_at_entry > 0:
                position.stop_loss_price = self._calculate_initial_stop(position)

            # 初始化峰值
            if position.side == "long":
                position.peak_price = position.entry_price
            else:
                position.peak_price = position.entry_price

            self.positions[position.position_id] = position
            logger.info(f"持仓注册: {position.position_id} {position.symbol} {position.side} @ {position.entry_price}")

    def unregister_position(self, position_id: str):
        """注销持仓（已平仓）"""
        with self.lock:
            if position_id in self.positions:
                del self.positions[position_id]
                logger.info(f"持仓注销: {position_id}")

    def update_price(self, symbol: str, current_price: float):
        """更新市场价格"""
        with self.lock:
            for pos in self.positions.values():
                if pos.symbol == symbol:
                    pos.current_price = current_price
                    self._update_position_risk(pos)

    def _calculate_initial_stop(self, pos: Position) -> float:
        """计算初始止损价"""
        if pos.stop_loss_type == StopLossType.ATR:
            stop_dist = pos.atr_at_entry * pos.atr_multiplier
        else:
            stop_dist = pos.entry_dist

        if pos.side == "long":
            return pos.entry_price - stop_dist
        else:
            return pos.entry_price + stop_dist

    def _update_position_risk(self, pos: Position):
        """更新单个持仓的风险状态"""
        if pos.current_price == 0:
            return

        # 计算未实现盈亏
        if pos.side == "long":
            pos.unrealized_pnl = (pos.current_price - pos.entry_price) * pos.quantity
        else:
            pos.unrealized_pnl = (pos.entry_price - pos.current_price) * pos.quantity

        # 计算R倍数
        if pos.entry_dist > 0:
            pos.r_multiple = pos.unrealized_pnl / (pos.entry_dist * pos.quantity)

        # 更新峰值价格（追踪止损用）
        if pos.side == "long":
            if pos.current_price > pos.peak_price:
                pos.peak_price = pos.current_price
        else:
            if pos.current_price < pos.peak_price:
                pos.peak_price = pos.current_price

        # 更新追踪止损
        self._update_trailing_stop(pos)

        # 检查止损是否触发
        self._check_stop_loss_trigger(pos)

        # 更新风险等级
        self._update_risk_level(pos)

    def _update_trailing_stop(self, pos: Position):
        """更新追踪止损（只允许向盈利方向移动）"""
        if not self.config.enable_stop_loss_enforcement:
            return

        # 检查是否激活追踪止损
        if not pos.trailing_activated:
            if pos.r_multiple >= self.config.trailing_activation_r:
                pos.trailing_activated = True
                self._create_alert(
                    level=RiskLevel.YELLOW,
                    alert_type="trailing_activated",
                    message=f"追踪止损已激活: {pos.symbol} R={pos.r_multiple:.2f}",
                    position_id=pos.position_id,
                    symbol=pos.symbol,
                    action_required="monitor"
                )
            else:
                return

        # 计算新的止损价
        trail_dist = pos.atr_at_entry * self.config.trailing_atr_mult

        if pos.side == "long":
            new_stop = pos.peak_price - trail_dist
            # 止损只能上移，不能下移
            if new_stop > pos.stop_loss_price:
                old_stop = pos.stop_loss_price
                pos.stop_loss_price = new_stop
                logger.info(f"追踪止损上移: {pos.symbol} {old_stop:.2f} → {new_stop:.2f}")
        else:
            new_stop = pos.peak_price + trail_dist
            # 止损只能下移，不能上移
            if new_stop < pos.stop_loss_price:
                old_stop = pos.stop_loss_price
                pos.stop_loss_price = new_stop
                logger.info(f"追踪止损下移: {pos.symbol} {old_stop:.2f} → {new_stop:.2f}")

    def _check_stop_loss_trigger(self, pos: Position):
        """检查止损是否触发（硬规则）"""
        if not self.config.enable_stop_loss_enforcement:
            return

        if pos.stop_loss_hit:
            return

        triggered = False
        reason = ""

        if pos.side == "long":
            if pos.current_price <= pos.stop_loss_price:
                triggered = True
                reason = f"多头止损触发: 价格 {pos.current_price:.2f} ≤ 止损价 {pos.stop_loss_price:.2f}"
        else:
            if pos.current_price >= pos.stop_loss_price:
                triggered = True
                reason = f"空头止损触发: 价格 {pos.current_price:.2f} ≥ 止损价 {pos.stop_loss_price:.2f}"

        if triggered:
            pos.stop_loss_hit = True
            pos.risk_level = RiskLevel.RED

            # 创建告警
            self._create_alert(
                level=RiskLevel.RED,
                alert_type="stop_loss_hit",
                message=reason,
                position_id=pos.position_id,
                symbol=pos.symbol,
                action_required="close_position"
            )

            # 强制执行平仓（不等人）
            if self._close_position_callback:
                success = self._close_position_callback(
                    pos.position_id,
                    f"stop_loss_enforced: {reason}",
                    pos.current_price
                )
                if success:
                    logger.warning(f"强制执行平仓成功: {pos.position_id}")
                else:
                    logger.error(f"强制执行平仓失败: {pos.position_id}")

    def _update_risk_level(self, pos: Position):
        """更新持仓风险等级"""
        if pos.stop_loss_hit:
            pos.risk_level = RiskLevel.RED
        elif pos.r_multiple < -0.5:
            pos.risk_level = RiskLevel.YELLOW
        elif pos.r_multiple < -1.0:
            pos.risk_level = RiskLevel.RED
        else:
            pos.risk_level = RiskLevel.GREEN

    def check_portfolio_risk(self):
        """检查组合层面风险"""
        with self.lock:
            # 计算当前权益和回撤
            total_unrealized = sum(p.unrealized_pnl for p in self.positions.values())
            self.current_equity = self.initial_equity + total_unrealized

            # 更新峰值
            if self.current_equity > self.peak_equity:
                self.peak_equity = self.current_equity

            # 计算回撤
            if self.peak_equity > 0:
                self.current_drawdown = (self.peak_equity - self.current_equity) / self.peak_equity * 100

            # 检查最大回撤
            if self.current_drawdown >= self.config.max_drawdown_pct:
                self._create_alert(
                    level=RiskLevel.RED,
                    alert_type="max_drawdown_hit",
                    message=f"最大回撤触发: {self.current_drawdown:.2f}% ≥ {self.config.max_drawdown_pct}%",
                    action_required="close_all_positions"
                )
                # 全部平仓
                self._close_all_positions("max_drawdown_enforced")

            # 检查持仓数量
            if len(self.positions) > self.config.max_open_positions:
                self._create_alert(
                    level=RiskLevel.YELLOW,
                    alert_type="position_limit",
                    message=f"持仓数量超限: {len(self.positions)} > {self.config.max_open_positions}",
                    action_required="reduce_positions"
                )

    def _close_all_positions(self, reason: str):
        """全部平仓（组合层面风控触发）"""
        logger.critical(f"全部平仓触发: {reason}")
        for pos_id in list(self.positions.keys()):
            if self._close_position_callback:
                self._close_position_callback(pos_id, f"portfolio_risk: {reason}", 0.0)

    def _create_alert(self, level: RiskLevel, alert_type: str, message: str,
                      position_id: Optional[str] = None, symbol: Optional[str] = None,
                      action_required: str = "monitor"):
        """创建风控告警"""
        alert = RiskAlert(
            alert_id=f"alert_{int(time.time() * 1000)}",
            timestamp=datetime.now(timezone.utc),
            level=level,
            alert_type=alert_type,
            message=message,
            position_id=position_id,
            symbol=symbol,
            action_required=action_required
        )
        self.alerts.append(alert)

        logger.log(
            level=30 if level == RiskLevel.YELLOW else 40,
            msg=f"风控告警 [{level.value}] {alert_type}: {message}"
        )

        if self._alert_callback:
            try:
                self._alert_callback(alert)
            except Exception as e:
                logger.error(f"告警回调失败: {e}")

    def get_position_risk_summary(self) -> List[Dict[str, Any]]:
        """获取所有持仓的风险摘要"""
        with self.lock:
            return [
                {
                    "position_id": p.position_id,
                    "symbol": p.symbol,
                    "side": p.side,
                    "entry_price": p.entry_price,
                    "current_price": p.current_price,
                    "unrealized_pnl": p.unrealized_pnl,
                    "r_multiple": p.r_multiple,
                    "stop_loss_price": p.stop_loss_price,
                    "risk_level": p.risk_level.value,
                    "trailing_activated": p.trailing_activated,
                }
                for p in self.positions.values()
            ]

    def get_portfolio_risk_summary(self) -> Dict[str, Any]:
        """获取组合风险摘要"""
        with self.lock:
            return {
                "current_equity": self.current_equity,
                "peak_equity": self.peak_equity,
                "current_drawdown_pct": self.current_drawdown,
                "open_positions": len(self.positions),
                "max_drawdown_limit_pct": self.config.max_drawdown_pct,
                "risk_level": "red" if self.current_drawdown >= self.config.max_drawdown_pct * 0.8 else
                              "yellow" if self.current_drawdown >= self.config.max_drawdown_pct * 0.5 else "green",
            }

    def start_monitoring(self):
        """启动风控监控线程"""
        if self._running:
            return

        self._running = True
        self._check_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="risk-engine-monitor"
        )
        self._check_thread.start()
        logger.info("风控引擎监控线程已启动")

    def stop_monitoring(self):
        """停止风控监控"""
        self._running = False
        if self._check_thread:
            self._check_thread.join(timeout=5)
        logger.info("风控引擎监控线程已停止")

    def _monitor_loop(self):
        """监控循环"""
        while self._running:
            try:
                self.check_portfolio_risk()
                time.sleep(self.config.stop_loss_check_interval_sec)
            except Exception as e:
                logger.error(f"风控监控循环异常: {e}")
                time.sleep(1)


# 全局单例
_risk_engine: Optional[RiskEngine] = None
_engine_lock = threading.Lock()


def get_risk_engine() -> RiskEngine:
    """获取风控引擎单例"""
    global _risk_engine
    with _engine_lock:
        if _risk_engine is None:
            _risk_engine = RiskEngine()
        return _risk_engine
