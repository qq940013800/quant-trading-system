"""
交易日志与绩效归因分析

第一性原理：
- 你赚了钱，是因为策略好，还是因为运气？
- 你亏了钱，是策略失效，还是执行问题？
- 不知道原因，就没法改进。

全球顶级机构实践：
- AQR：每笔交易都做归因分析
- Renaissance：交易日志是核心资产
- Two Sigma：绩效归因五维模型

绩效归因五维模型：
1. 收益分解 —— 赚的钱从哪来？
2. 因子归因 —— 哪个因子贡献最大？
3. 成本归因 —— 交易成本吃掉了多少？
4. 尾部风险 —— 极端情况损失多少？
5. 行为偏差 —— 人在关键时刻犯了什么错？
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.utils.logger import get_logger

logger = get_logger(__name__)


class TradeResult(Enum):
    """交易结果"""
    WINNER = "winner"
    LOSER = "loser"
    BREAKEVEN = "breakeven"


@dataclass
class TradeJournalEntry:
    """交易日志条目"""
    trade_id: str
    timestamp: datetime
    strategy_id: int
    strategy_name: str
    symbol: str
    side: str  # long / short

    # 入场
    entry_price: float
    entry_time: datetime
    entry_reason: str = ""  # 为什么入场？

    # 出场
    exit_price: float = 0.0
    exit_time: Optional[datetime] = None
    exit_reason: str = ""  # 为什么出场？

    # 结果
    quantity: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    r_multiple: float = 0.0
    result: TradeResult = TradeResult.BREAKEVEN

    # 成本
    commission: float = 0.0
    slippage: float = 0.0
    total_cost: float = 0.0

    # 决策质量
    decision_quality_score: float = 0.0  # 0-100
    was_plan_followed: bool = True
    emotional_state: str = "neutral"  # calm / greedy / fearful / revenge

    # 备注
    notes: str = ""


@dataclass
class PerformanceAttribution:
    """绩效归因结果"""
    period: str

    # 总体指标
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    average_win: float = 0.0
    average_loss: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0

    # 五维归因
    returns_breakdown: Dict[str, float] = field(default_factory=dict)
    factor_attribution: Dict[str, float] = field(default_factory=dict)
    cost_attribution: Dict[str, float] = field(default_factory=dict)
    tail_risk_metrics: Dict[str, float] = field(default_factory=dict)
    behavioral_biases: List[Dict[str, Any]] = field(default_factory=list)

    # 改进建议
    recommendations: List[str] = field(default_factory=list)


class TradeJournalService:
    """
    交易日志与绩效归因服务

    核心功能：
    1. 记录每笔交易的完整决策链
    2. 绩效五维归因分析
    3. 行为偏差识别
    4. 交易复盘标准化流程
    """

    def __init__(self):
        self.journal: List[TradeJournalEntry] = []
        self._callbacks: List[Callable[[TradeJournalEntry], None]] = []

    def log_trade(self, entry: TradeJournalEntry):
        """记录一笔交易"""
        self.journal.append(entry)
        logger.info(
            f"交易记录: {entry.trade_id} {entry.symbol} {entry.side} "
            f"PnL={entry.pnl:.2f} R={entry.r_multiple:.2f}"
        )

        for callback in self._callbacks:
            try:
                callback(entry)
            except Exception as e:
                logger.error(f"交易日志回调失败: {e}")

    def add_callback(self, callback: Callable[[TradeJournalEntry], None]):
        """添加交易记录回调"""
        self._callbacks.append(callback)

    def analyze_performance(self, strategy_id: Optional[int] = None,
                           days: int = 30) -> PerformanceAttribution:
        """
        绩效归因分析

        strategy_id: 指定策略，None=全部
        days: 最近多少天
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        # 筛选交易
        trades = [
            t for t in self.journal
            if t.exit_time and t.exit_time >= cutoff
        ]
        if strategy_id:
            trades = [t for t in trades if t.strategy_id == strategy_id]

        attribution = PerformanceAttribution(period=f"最近{days}天")

        if not trades:
            attribution.recommendations.append("没有足够的交易数据进行分析")
            return attribution

        # 基本统计
        attribution.total_trades = len(trades)
        winners = [t for t in trades if t.result == TradeResult.WINNER]
        losers = [t for t in trades if t.result == TradeResult.LOSER]

        attribution.winning_trades = len(winners)
        attribution.losing_trades = len(losers)
        attribution.win_rate = len(winners) / len(trades) * 100 if trades else 0

        # 收益统计
        attribution.total_pnl = sum(t.pnl for t in trades)
        attribution.average_win = sum(t.pnl for t in winners) / len(winners) if winners else 0
        attribution.average_loss = sum(t.pnl for t in losers) / len(losers) if losers else 0

        # 盈利因子和期望值
        total_wins = sum(t.pnl for t in winners)
        total_losses = abs(sum(t.pnl for t in losers))
        attribution.profit_factor = total_wins / total_losses if total_losses > 0 else 0
        attribution.expectancy = (
            attribution.win_rate / 100 * attribution.average_win +
            (1 - attribution.win_rate / 100) * attribution.average_loss
        )

        # 1. 收益分解
        attribution.returns_breakdown = self._calculate_returns_breakdown(trades)

        # 2. 成本归因
        attribution.cost_attribution = self._calculate_cost_attribution(trades)

        # 3. 尾部风险
        attribution.tail_risk_metrics = self._calculate_tail_risk(trades)

        # 4. 行为偏差分析
        attribution.behavioral_biases = self._analyze_behavioral_biases(trades)

        # 生成建议
        attribution.recommendations = self._generate_recommendations(attribution)

        return attribution

    def _calculate_returns_breakdown(self, trades: List[TradeJournalEntry]) -> Dict[str, float]:
        """收益分解：赚的钱从哪来？"""
        by_strategy = {}
        by_symbol = {}

        for t in trades:
            by_strategy[t.strategy_name] = by_strategy.get(t.strategy_name, 0) + t.pnl
            by_symbol[t.symbol] = by_symbol.get(t.symbol, 0) + t.pnl

        return {
            "by_strategy": by_strategy,
            "by_symbol": by_symbol,
            "total_pnl": sum(t.pnl for t in trades),
        }

    def _calculate_cost_attribution(self, trades: List[TradeJournalEntry]) -> Dict[str, float]:
        """成本归因：交易成本吃掉了多少？"""
        total_commission = sum(t.commission for t in trades)
        total_slippage = sum(t.slippage for t in trades)
        total_gross_pnl = sum(t.pnl + t.total_cost for t in trades)
        total_net_pnl = sum(t.pnl for t in trades)

        cost_ratio = total_commission + total_slippage / abs(total_gross_pnl) * 100 if total_gross_pnl != 0 else 0

        return {
            "total_commission": total_commission,
            "total_slippage": total_slippage,
            "total_cost": total_commission + total_slippage,
            "cost_ratio_pct": cost_ratio,
            "gross_pnl": total_gross_pnl,
            "net_pnl": total_net_pnl,
        }

    def _calculate_tail_risk(self, trades: List[TradeJournalEntry]) -> Dict[str, float]:
        """尾部风险：极端情况损失多少？"""
        pnls = sorted([t.pnl for t in trades])

        return {
            "worst_trade": pnls[0] if pnls else 0,
            "best_trade": pnls[-1] if pnls else 0,
            "worst_5pct": pnls[int(len(pnls) * 0.05)] if len(pnls) > 20 else pnls[0],
            "average_loss": sum(t.pnl for t in trades if t.pnl < 0) / max(1, sum(1 for t in trades if t.pnl < 0)),
            "max_consecutive_losses": self._max_consecutive_losses(trades),
        }

    def _max_consecutive_losses(self, trades: List[TradeJournalEntry]) -> int:
        """最大连续亏损次数"""
        max_streak = 0
        current_streak = 0

        for t in sorted(trades, key=lambda x: t.timestamp):
            if t.pnl < 0:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 0

        return max_streak

    def _analyze_behavioral_biases(self, trades: List[TradeJournalEntry]) -> List[Dict[str, Any]]:
        """行为偏差分析"""
        biases = []

        # 检查1：处置效应（赚的太早跑，亏的死扛）
        winners = [t for t in trades if t.result == TradeResult.WINNER]
        losers = [t for t in trades if t.result == TradeResult.LOSER]

        if winners and losers:
            avg_win_r = sum(t.r_multiple for t in winners) / len(winners)
            avg_loss_r = abs(sum(t.r_multiple for t in losers) / len(losers))

            if avg_win_r < avg_loss_r * 0.8:
                biases.append({
                    "type": "处置效应",
                    "description": f"平均盈利{avg_win_r:.2f}R < 平均亏损{avg_loss_r:.2f}R，赚的太早跑了",
                    "severity": "high",
                })

        # 检查2：复仇交易（连续亏损后加大仓位）
        consecutive_loss_streak = 0
        revenge_trades = 0

        for t in sorted(trades, key=lambda x: x.timestamp):
            if t.pnl < 0:
                consecutive_loss_streak += 1
            else:
                if consecutive_loss_streak >= 3 and t.emotional_state == "revenge":
                    revenge_trades += 1
                consecutive_loss_streak = 0

        if revenge_trades > 0:
            biases.append({
                "type": "复仇交易",
                "description": f"连续亏损后进行了{revenge_trades}笔复仇交易",
                "severity": "high",
            })

        # 检查3：计划外交易
        unplanned = sum(1 for t in trades if not t.was_plan_followed)
        if unplanned > len(trades) * 0.2:
            biases.append({
                "type": "计划外交易",
                "description": f"{unplanned}/{len(trades)}笔交易没有按计划执行",
                "severity": "medium",
            })

        return biases

    def _generate_recommendations(self, attribution: PerformanceAttribution) -> List[str]:
        """生成改进建议"""
        recommendations = []

        if attribution.win_rate < 40:
            recommendations.append("胜率偏低，考虑优化入场信号或减少交易频率")

        if attribution.profit_factor < 1.5:
            recommendations.append("盈利因子偏低，盈亏比不够，需要提升平均盈利/平均亏损比")

        if attribution.cost_attribution.get("cost_ratio_pct", 0) > 20:
            recommendations.append("交易成本占比过高，考虑降低换手或优化执行算法")

        for bias in attribution.behavioral_biases:
            recommendations.append(f"行为偏差-{bias['type']}: {bias['description']}")

        if not recommendations:
            recommendations.append("整体表现良好，继续保持")

        return recommendations


# 全局单例
_journal_service: Optional[TradeJournalService] = None


def get_trade_journal() -> TradeJournalService:
    """获取交易日志服务单例"""
    global _journal_service
    if _journal_service is None:
        _journal_service = TradeJournalService()
    return _journal_service
