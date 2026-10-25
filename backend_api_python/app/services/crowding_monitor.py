"""
策略拥挤度监控

第一性原理：
- 任何Alpha都有生命周期：发现→验证→规模化→拥挤→衰减→失效
- 当太多人用同一个策略，收益会被摊薄
- 拥挤的信号还会导致踩踏：大家同时进场，同时出场

全球顶级机构实践：
- Renaissance：监控每个信号的拥挤度，提前预警衰减
- Two Sigma：另类数据的价值就在于别人还没用
- AQR：因子拥挤度是因子投资的核心风险

拥挤度信号：
1. 信号相关性上升 —— 大家开始用同一个信号
2. 交易成本上升 —— 大家都在交易同一个标的
3. 收益衰减 —— 信号预测能力下降
4. 持仓集中度上升 —— 大家持仓越来越像
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from app.utils.logger import get_logger

logger = get_logger(__name__)


class CrowdingLevel(Enum):
    """拥挤度等级"""
    LOW = "low"               # 低拥挤：蓝海，收益高
    MODERATE = "moderate"     # 中等拥挤：正常
    HIGH = "high"             # 高拥挤：预警，收益开始衰减
    EXTREME = "extreme"       # 极度拥挤：红海，即将踩踏


@dataclass
class StrategyCrowdingMetrics:
    """策略拥挤度指标"""
    strategy_name: str
    symbol: str

    # 拥挤度评分
    crowding_score: float = 0.0        # 0-100
    crowding_level: CrowdingLevel = CrowdingLevel.LOW

    # 信号维度
    signal_correlation: float = 0.0    # 与同类策略信号相关性
    signal_decay_rate: float = 0.0      # 信号衰减率

    # 交易维度
    transaction_cost_trend: float = 0.0  # 交易成本变化趋势（%）
    volume_share: float = 0.0           # 成交量占比

    # 持仓维度
    position_concentration: float = 0.0  # 持仓集中度
    herd_index: float = 0.0              # 羊群指数

    # 收益维度
    alpha_decay: float = 0.0            # Alpha衰减幅度
    sharpe_trend: float = 0.0           # 夏普比率变化趋势

    # 建议
    recommendation: str = ""


class CrowdingMonitorService:
    """
    策略拥挤度监控服务

    核心功能：
    1. 实时监控每个策略的拥挤度
    2. 拥挤度预警和自动降仓建议
    3. 信号衰减检测
    4. 踩踏风险预警
    """

    def __init__(self):
        self.strategies: Dict[str, StrategyCrowdingMetrics] = {}
        self.history: Dict[str, List[StrategyCrowdingMetrics]] = {}

    def register_strategy(self, strategy_name: str, symbol: str):
        """注册策略到拥挤度监控"""
        key = f"{strategy_name}_{symbol}"
        self.strategies[key] = StrategyCrowdingMetrics(
            strategy_name=strategy_name,
            symbol=symbol,
        )
        logger.info(f"策略拥挤度监控注册: {strategy_name} ({symbol})")

    def update_metrics(self, strategy_name: str, symbol: str,
                      signal_correlation: float = 0.0,
                      transaction_cost_change: float = 0.0,
                      alpha_decay: float = 0.0,
                      sharpe_trend: float = 0.0):
        """更新拥挤度指标"""
        key = f"{strategy_name}_{symbol}"

        if key not in self.strategies:
            self.register_strategy(strategy_name, symbol)

        metrics = self.strategies[key]
        metrics.signal_correlation = signal_correlation
        metrics.transaction_cost_trend = transaction_cost_change
        metrics.alpha_decay = alpha_decay
        metrics.sharpe_trend = sharpe_trend

        # 计算拥挤度评分
        metrics.crowding_score = self._calculate_crowding_score(metrics)

        # 判定拥挤度等级
        metrics.crowding_level = self._determine_crowding_level(metrics.crowding_score)

        # 生成建议
        metrics.recommendation = self._generate_recommendation(metrics)

        # 保存历史
        if key not in self.history:
            self.history[key] = []
        self.history[key].append(metrics)

        # 只保留最近30天
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        self.history[key] = [
            m for m in self.history[key]
            if True  # 简化：不按时间过滤
        ][-30:]

        # 拥挤度过高时告警
        if metrics.crowding_level in (CrowdingLevel.HIGH, CrowdingLevel.EXTREME):
            logger.warning(
                f"⚠️ 策略拥挤度预警: {strategy_name} ({symbol}) "
                f"score={metrics.crowding_score:.1f} level={metrics.crowding_level.value}"
            )

        return metrics

    def _calculate_crowding_score(self, m: StrategyCrowdingMetrics) -> float:
        """计算拥挤度综合评分（0-100）"""
        score = 0.0

        # 信号相关性（权重30%）
        # 相关性越高，越拥挤
        score += min(100, m.signal_correlation * 100) * 0.3

        # 交易成本上升（权重20%）
        score += min(100, max(0, m.transaction_cost_change * 10)) * 0.2

        # Alpha衰减（权重30%）
        score += min(100, max(0, m.alpha_decay * 100)) * 0.3

        # 夏普下降（权重20%）
        score += min(100, max(0, -m.sharpe_trend * 100)) * 0.2

        return score

    def _determine_crowding_level(self, score: float) -> CrowdingLevel:
        """根据评分判定拥挤度等级"""
        if score < 30:
            return CrowdingLevel.LOW
        elif score < 50:
            return CrowdingLevel.MODERATE
        elif score < 70:
            return CrowdingLevel.HIGH
        else:
            return CrowdingLevel.EXTREME

    def _generate_recommendation(self, m: StrategyCrowdingMetrics) -> str:
        """生成操作建议"""
        if m.crowding_level == CrowdingLevel.LOW:
            return "低拥挤度，可以正常加仓，蓝海机会"
        elif m.crowding_level == CrowdingLevel.MODERATE:
            return "中等拥挤度，正常运行，持续监控"
        elif m.crowding_level == CrowdingLevel.HIGH:
            return "高拥挤度预警，建议减仓30%，准备寻找新Alpha"
        else:  # EXTREME
            return "极度拥挤！建议立即减仓50%以上，警惕踩踏风险"

    def get_all_strategies_status(self) -> List[Dict[str, Any]]:
        """获取所有策略的拥挤度状态"""
        return [
            {
                "strategy_name": m.strategy_name,
                "symbol": m.symbol,
                "crowding_score": m.crowding_score,
                "crowding_level": m.crowding_level.value,
                "alpha_decay": m.alpha_decay,
                "recommendation": m.recommendation,
            }
            for m in self.strategies.values()
        ]

    def get_crowding_summary(self) -> Dict[str, Any]:
        """获取拥挤度汇总"""
        if not self.strategies:
            return {"status": "no_strategies"}

        levels = {}
        for m in self.strategies.values():
            level = m.crowding_level.value
            levels[level] = levels.get(level, 0) + 1

        avg_score = sum(m.crowding_score for m in self.strategies.values()) / len(self.strategies)

        return {
            "total_strategies": len(self.strategies),
            "avg_crowding_score": avg_score,
            "distribution": levels,
            "warning": "有策略拥挤度过高，需要关注" if levels.get("high", 0) + levels.get("extreme", 0) > 0 else "整体正常",
        }


# 全局单例
_crowding_monitor: Optional[CrowdingMonitorService] = None


def get_crowding_monitor() -> CrowdingMonitorService:
    """获取拥挤度监控服务单例"""
    global _crowding_monitor
    if _crowding_monitor is None:
        _crowding_monitor = CrowdingMonitorService()
    return _crowding_monitor
