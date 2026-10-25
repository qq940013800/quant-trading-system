"""
交易成本分析 TCA (Transaction Cost Analysis)

第一性原理：
- 回测和实盘的差距，80%来自交易成本被低估
- 高频策略回测年化50%，扣完成本年化5%
- 成本不是"手续费"一个数字，是五部分组成的

全球顶级机构实践：
- Jane Street：做市商的核心就是精确计算成本
- Renaissance：每个策略上线前先算成本能不能覆盖
- Two Sigma：TCA是回测真实性的第一道门

成本五分解：
1. 佣金（Commission）—— 固定成本
2. 点差（Spread）—— 买卖价差成本
3. 滑点（Slippage）—— 预期成交和实际成交的差距
4. 市场冲击（Market Impact）—— 你的订单对价格的影响
5. 时机风险（Timing Risk）—— 等待成交期间的价格波动
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from app.utils.logger import get_logger

logger = get_logger(__name__)


class OrderType(Enum):
    """订单类型"""
    MARKET = "market"           # 市价单
    LIMIT = "limit"             # 限价单
    STOP = "stop"               # 止损单
    TWAP = "twap"               # 时间加权平均
    VWAP = "vwap"               # 成交量加权平均


class SlippageModel(Enum):
    """滑点模型分级"""
    NONE = "none"               # 无滑点（回测理想情况）
    FIXED = "fixed"             # 固定滑点（简单回测）
    LINEAR = "linear"           # 线性滑点（按订单大小）
    SQUARE_ROOT = "sqrt"        # 平方根模型（机构标准）
    FULL_IMPACT = "full"        # 完全冲击（极端情况）


@dataclass
class OrderCost:
    """单笔订单成本"""
    order_id: str
    symbol: str
    side: str  # buy / sell
    quantity: float
    expected_price: float       # 预期成交价格
    actual_price: float = 0.0   # 实际成交价格

    # 成本分解
    commission: float = 0.0     # 佣金
    spread_cost: float = 0.0    # 点差成本
    slippage_cost: float = 0.0  # 滑点成本
    market_impact: float = 0.0  # 市场冲击成本
    timing_risk: float = 0.0    # 时机风险成本

    total_cost: float = 0.0     # 总成本
    cost_bps: float = 0.0       # 成本占名义价值的bps

    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class TCAParams:
    """TCA参数配置"""
    # 佣金
    commission_rate: float = 0.0001  # 0.01% 每边
    min_commission: float = 1.0      # 最低佣金

    # 点差
    default_spread_bps: float = 2.0  # 默认点差 2bps
    high_volatility_spread_mult: float = 3.0  # 高波动时点差倍数

    # 滑点模型
    slippage_model: SlippageModel = SlippageModel.SQUARE_ROOT
    slippage_base_bps: float = 1.0   # 基础滑点 1bps

    # 市场冲击模型（平方根模型）
    impact_coefficient: float = 0.1  # 冲击系数
    daily_volume: float = 1000000    # 日均成交量（参考值）

    # 时机风险
    timing_risk_bps_per_min: float = 0.5  # 每分钟时机风险


class TransactionCostAnalyzer:
    """
    交易成本分析器

    核心功能：
    1. 估算订单的总交易成本
    2. 分解成本来源
    3. 诊断回测和实盘的差距
    4. 优化执行算法选择
    """

    def __init__(self, params: Optional[TCAParams] = None):
        self.params = params or TCAParams()
        self.order_history: List[OrderCost] = []

    def estimate_order_cost(self, symbol: str, side: str, quantity: float,
                            price: float, order_type: OrderType = OrderType.MARKET,
                            volatility: float = 0.0) -> OrderCost:
        """估算单笔订单的交易成本"""
        order_id = f"order_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        notional = quantity * price

        # 1. 佣金
        commission = max(notional * self.params.commission_rate, self.params.min_commission)

        # 2. 点差成本
        spread_bps = self.params.default_spread_bps
        if volatility > 0.03:  # 高波动
            spread_bps *= self.params.high_volatility_spread_mult
        spread_cost = notional * spread_bps / 10000

        # 3. 滑点成本
        slippage_cost = self._calculate_slippage(quantity, price, volatility)

        # 4. 市场冲击
        market_impact = self._calculate_market_impact(quantity, price)

        # 5. 时机风险
        timing_risk = 0.0
        if order_type in (OrderType.LIMIT, OrderType.TWAP, OrderType.VWAP):
            timing_risk = notional * self.params.timing_risk_bps_per_min / 10000

        # 汇总
        total_cost = commission + spread_cost + slippage_cost + market_impact + timing_risk
        cost_bps = total_cost / notional * 10000 if notional > 0 else 0

        order = OrderCost(
            order_id=order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            expected_price=price,
            actual_price=price + (slippage_cost / quantity if quantity > 0 else 0),
            commission=commission,
            spread_cost=spread_cost,
            slippage_cost=slippage_cost,
            market_impact=market_impact,
            timing_risk=timing_risk,
            total_cost=total_cost,
            cost_bps=cost_bps,
        )

        self.order_history.append(order)
        return order

    def _calculate_slippage(self, quantity: float, price: float, volatility: float) -> float:
        """计算滑点成本"""
        notional = quantity * price

        if self.params.slippage_model == SlippageModel.NONE:
            return 0.0
        elif self.params.slippage_model == SlippageModel.FIXED:
            return notional * self.params.slippage_base_bps / 10000
        elif self.params.slippage_model == SlippageModel.LINEAR:
            # 线性模型：滑点与订单大小成正比
            volume_ratio = quantity / self.params.daily_volume
            return notional * self.params.slippage_base_bps / 10000 * (1 + volume_ratio * 10)
        elif self.params.slippage_model == SlippageModel.SQUARE_ROOT:
            # 平方根模型（机构标准）
            # impact = sigma * sqrt(Q/V)
            volume_ratio = quantity / self.params.daily_volume
            sigma = volatility if volatility > 0 else 0.02
            impact_factor = sigma * math.sqrt(max(0.001, volume_ratio))
            return notional * impact_factor * self.params.impact_coefficient
        else:  # FULL_IMPACT
            volume_ratio = quantity / self.params.daily_volume
            sigma = volatility if volatility > 0 else 0.02
            return notional * sigma * volume_ratio

    def _calculate_market_impact(self, quantity: float, price: float) -> float:
        """计算市场冲击成本"""
        # 简化模型：大单冲击大，小单冲击小
        notional = quantity * price
        volume_ratio = quantity / self.params.daily_volume

        # 平方根冲击模型
        impact = notional * self.params.impact_coefficient * math.sqrt(max(0.001, volume_ratio))
        return impact * 0.5  # 市场冲击是滑点的一部分，这里单独计算

    def diagnose_backtest_vs_live_gap(self, backtest_returns: float,
                                       live_returns: float,
                                       total_trades: int) -> Dict[str, Any]:
        """诊断回测和实盘的收益差距"""
        gap = backtest_returns - live_returns
        gap_per_trade = gap / total_trades if total_trades > 0 else 0

        # 假设回测只算了佣金，没算其他成本
        estimated_cost_per_trade = gap_per_trade

        return {
            "backtest_returns": backtest_returns,
            "live_returns": live_returns,
            "gap_pct": gap,
            "gap_per_trade_bps": gap_per_trade * 10000,
            "estimated_cost_per_trade": estimated_cost_per_trade,
            "likely_causes": [
                "滑点被低估",
                "点差成本未计入",
                "市场冲击未建模",
                "流动性差时成交质量差",
            ],
            "recommendation": "使用平方根滑点模型重新回测，预期收益会下降30-50%",
        }

    def get_cost_summary(self) -> Dict[str, Any]:
        """获取成本汇总统计"""
        if not self.order_history:
            return {"status": "no_orders"}

        total_cost = sum(o.total_cost for o in self.order_history)
        total_notional = sum(o.quantity * o.expected_price for o in self.order_history)
        avg_cost_bps = total_cost / total_notional * 10000 if total_notional > 0 else 0

        # 成本分解占比
        commission_pct = sum(o.commission for o in self.order_history) / total_cost * 100
        spread_pct = sum(o.spread_cost for o in self.order_history) / total_cost * 100
        slippage_pct = sum(o.slippage_cost for o in self.order_history) / total_cost * 100
        impact_pct = sum(o.market_impact for o in self.order_history) / total_cost * 100
        timing_pct = sum(o.timing_risk for o in self.order_history) / total_cost * 100

        return {
            "total_orders": len(self.order_history),
            "total_cost": total_cost,
            "total_notional": total_notional,
            "avg_cost_bps": avg_cost_bps,
            "cost_breakdown_pct": {
                "commission": commission_pct,
                "spread": spread_pct,
                "slippage": slippage_pct,
                "market_impact": impact_pct,
                "timing_risk": timing_pct,
            },
            "verdict": "成本过高，需要优化执行算法" if avg_cost_bps > 10 else
                       "成本可控" if avg_cost_bps > 5 else
                       "成本很低，流动性很好",
        }


# 全局单例
_tca_analyzer: Optional[TransactionCostAnalyzer] = None


def get_tca_analyzer() -> TransactionCostAnalyzer:
    """获取TCA分析器单例"""
    global _tca_analyzer
    if _tca_analyzer is None:
        _tca_analyzer = TransactionCostAnalyzer()
    return _tca_analyzer
