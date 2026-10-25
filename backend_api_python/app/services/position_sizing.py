"""
仓位管理引擎（Position Sizing Engine）

第一性原理：
- 仓位管理比选股重要100倍 —— 再好的策略，仓位过重也会死
- 风险是永久性资本损失的概率，不是波动率
- Kelly公式是理论最优，但实战用分数Kelly（1/4~1/2）
- 波动率目标：波动大的少做，波动小的多做，保持风险恒定

全球顶级机构实践：
- Renaissance：每个策略的风险贡献独立计算
- Two Sigma：风险平价分配，不是等权分配
- Citadel：实时仓位调整，根据波动率变化
- Millennium：PM对自己的仓位负责，公司层面风控兜底

核心原则：
1. 单笔风险固定 —— 每笔交易只冒总资金1%的风险
2. 波动率目标 —— 让组合的年化波动率保持在目标值
3. 分数Kelly —— 不用全Kelly，用1/4 Kelly，更安全
4. 风险平价 —— 不同策略/资产的风险贡献相等
5. 回撤调整 —— 回撤大了自动减仓，保护本金
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)


class SizingMethod(Enum):
    """仓位计算方法"""
    FIXED_RISK = "fixed_risk"           # 固定风险法（每笔冒X%风险）
    VOLATILITY_TARGET = "vol_target"    # 波动率目标法
    KELLY_FRACTION = "kelly_fraction"   # 分数Kelly法
    RISK_PARITY = "risk_parity"         # 风险平价法


@dataclass
class SizingConfig:
    """仓位配置"""
    # 基础风险参数
    max_risk_per_trade_pct: float = 1.0     # 单笔最大风险（占总资金%）
    max_portfolio_risk_pct: float = 6.0      # 组合最大风险（同时持仓总风险%）
    max_drawdown_reduce_pct: float = 10.0   # 回撤超过X%开始减仓
    
    # 波动率目标参数
    target_annual_volatility: float = 15.0  # 目标年化波动率（%）
    volatility_window_days: int = 20          # 波动率计算窗口
    
    # Kelly参数
    kelly_fraction: float = 0.25              # 分数Kelly（1/4 Kelly）
    
    # 仓位限制
    max_position_pct: float = 20.0           # 单个仓位最大占比
    min_position_pct: float = 0.5            # 单个仓位最小占比


@dataclass
class TradeSetup:
    """交易信号（用于计算仓位）"""
    symbol: str
    side: str                    # long / short
    entry_price: float
    stop_loss_price: float
    atr: float = 0.0             # 当前ATR
    historical_volatility: float = 0.0  # 历史波动率（年化%）
    win_rate: float = 0.5        # 历史胜率
    avg_win_loss_ratio: float = 2.0  # 平均盈亏比


@dataclass
class SizingResult:
    """仓位计算结果"""
    position_size: float          # 建议仓位（数量）
    position_value: float         # 建议仓位价值（金额）
    position_pct: float            # 占总资金比例（%）
    risk_amount: float            # 风险金额（止损亏多少）
    risk_pct: float               # 风险占总资金比例（%）
    method_used: str              # 使用的计算方法
    expected_r_multiple: float = 0.0  # 预期R倍数


class PositionSizingEngine:
    """
    仓位管理引擎
    
    支持多种仓位计算方法，根据市场环境选择最合适的：
    1. 固定风险法 —— 最简单，每笔冒固定风险
    2. 波动率目标法 —— 波动大的少做，波动小的多做
    3. 分数Kelly法 —— 根据胜率和盈亏比计算最优仓位
    4. 风险平价法 —— 多策略时平均分配风险贡献
    """
    
    def __init__(self, config: Optional[SizingConfig] = None):
        self.config = config or SizingConfig()
        self.current_equity: float = 100000.0  # 当前总资金
        self.peak_equity: float = 100000.0
        self.current_drawdown: float = 0.0  # 当前回撤%
        
    def calculate_position_size(self, setup: TradeSetup, method: SizingMethod = None) -> SizingResult:
        """
        计算建议仓位大小
        
        参数：
            setup: 交易信号
            method: 仓位计算方法（默认自动选择）
        
        返回：
            仓位计算结果
        """
        # 自动选择最合适的方法
        if method is None:
            method = self._select_best_method(setup)
        
        # 根据方法计算
        if method == SizingMethod.FIXED_RISK:
            result = self._calc_fixed_risk(setup)
        elif method == SizingMethod.VOLATILITY_TARGET:
            result = self._calc_vol_target(setup)
        elif method == SizingMethod.KELLY_FRACTION:
            result = self._calc_kelly(setup)
        else:
            result = self._calc_fixed_risk(setup)
        
        # 应用回撤调整（回撤大了自动减仓）
        result = self._apply_drawdown_adjustment(result)
        
        # 应用仓位上下限
        result = self._apply_position_limits(result, setup)
        
        # 计算预期R倍数
        if setup.stop_loss_price > 0:
            risk_dist = abs(setup.entry_price - setup.stop_loss_price)
            if setup.side == "long":
                result.expected_r_multiple = (setup.entry_price - setup.stop_loss_price) / risk_dist
            else:
                result.expected_r_multiple = (setup.stop_loss_price - setup.entry_price) / risk_dist
        
        logger.info(
            f"仓位计算: {setup.symbol} {result.position_pct:.1f}% "
            f"风险={result.risk_pct:.2f}% 方法={result.method_used}"
        )
        
        return result
    
    def _select_best_method(self, setup: TradeSetup) -> SizingMethod:
        """自动选择最合适的仓位计算方法"""
        # 如果有足够的历史数据（胜率、盈亏比），用分数Kelly
        if setup.win_rate > 0 and setup.avg_win_loss_ratio > 0:
            return SizingMethod.KELLY_FRACTION
        
        # 如果有波动率数据，用波动率目标
        if setup.historical_volatility > 0:
            return SizingMethod.VOLATILITY_TARGET
        
        # 默认用固定风险法（最安全）
        return SizingMethod.FIXED_RISK
    
    def _calc_fixed_risk(self, setup: TradeSetup) -> SizingResult:
        """固定风险法：每笔交易冒总资金X%的风险"""
        risk_amount = self.current_equity * self.config.max_risk_per_trade_pct / 100
        
        # 止损距离
        stop_distance = abs(setup.entry_price - setup.stop_loss_price)
        if stop_distance == 0:
            stop_distance = setup.entry_price * 0.01  # 默认1%
        
        # 仓位大小 = 风险金额 / 止损距离
        position_size = risk_amount / stop_distance
        position_value = position_size * setup.entry_price
        position_pct = position_value / self.current_equity * 100
        
        return SizingResult(
            position_size=round(position_size, 4),
            position_value=round(position_value, 2),
            position_pct=round(position_pct, 2),
            risk_amount=round(risk_amount, 2),
            risk_pct=self.config.max_risk_per_trade_pct,
            method_used="fixed_risk"
        )
    
    def _calc_vol_target(self, setup: TradeSetup) -> SizingResult:
        """波动率目标法：让仓位的风险贡献等于目标波动率"""
        if setup.historical_volatility == 0:
            return self._calc_fixed_risk(setup)
        
        # 目标风险金额 = 总资金 × 目标波动率 / √252（交易日）
        daily_target_vol = self.config.target_annual_volatility / math.sqrt(252)
        risk_amount = self.current_equity * daily_target_vol / 100
        
        # 实际波动率对应的风险
        actual_daily_vol = setup.historical_volatility / math.sqrt(252)
        risk_adjustment = daily_target_vol / actual_daily_vol
        
        # 调整后的风险金额
        adjusted_risk = risk_amount * risk_adjustment
        
        # 止损距离
        stop_distance = abs(setup.entry_price - setup.stop_loss_price)
        if stop_distance == 0:
            stop_distance = setup.entry_price * 0.01
        
        position_size = adjusted_risk / stop_distance
        position_value = position_size * setup.entry_price
        position_pct = position_value / self.current_equity * 100
        
        return SizingResult(
            position_size=round(position_size, 4),
            position_value=round(position_value, 2),
            position_pct=round(position_pct, 2),
            risk_amount=round(adjusted_risk, 2),
            risk_pct=round(adjusted_risk / self.current_equity * 100, 2),
            method_used="volatility_target"
        )
    
    def _calc_kelly(self, setup: TradeSetup) -> SizingResult:
        """分数Kelly法：根据胜率和盈亏比计算最优仓位"""
        win_rate = setup.win_rate
        win_loss_ratio = setup.avg_win_loss_ratio
        
        # Kelly公式：f* = (p*b - q) / b
        # p = 胜率，q = 败率 = 1-p，b = 盈亏比
        if win_loss_ratio == 0:
            return self._calc_fixed_risk(setup)
        
        kelly_f = (win_rate * win_loss_ratio - (1 - win_rate)) / win_loss_ratio
        
        # 用分数Kelly（1/4 Kelly），更安全
        kelly_f = kelly_f * self.config.kelly_fraction
        
        # 不能负的（负的就不做）
        if kelly_f <= 0:
            kelly_f = 0.01  # 最小1%
        
        # 仓位 = 总资金 × Kelly比例
        position_value = self.current_equity * kelly_f
        position_size = position_value / setup.entry_price
        position_pct = kelly_f * 100
        
        # 风险金额 = 仓位 × 止损距离比例
        stop_distance_pct = abs(setup.entry_price - setup.stop_loss_price) / setup.entry_price
        risk_amount = position_value * stop_distance_pct
        
        return SizingResult(
            position_size=round(position_size, 4),
            position_value=round(position_value, 2),
            position_pct=round(position_pct, 2),
            risk_amount=round(risk_amount, 2),
            risk_pct=round(risk_amount / self.current_equity * 100, 2),
            method_used="fractional_kelly"
        )
    
    def _apply_drawdown_adjustment(self, result: SizingResult) -> SizingResult:
        """回撤调整：回撤大了自动减仓"""
        if self.current_drawdown <= self.config.max_drawdown_reduce_pct:
            return result
        
        # 回撤超过阈值，按比例减仓
        # 回撤10% → 仓位打9折
        # 回撤20% → 仓位打8折
        # 回撤30% → 仓位打7折
        reduction_factor = max(0.5, 1.0 - self.current_drawdown / 100)
        
        result.position_size *= reduction_factor
        result.position_value *= reduction_factor
        result.position_pct *= reduction_factor
        result.risk_amount *= reduction_factor
        result.risk_pct *= reduction_factor
        
        logger.info(f"回撤调整: 回撤{self.current_drawdown:.1f}%，仓位调整为{reduction_factor:.1f}倍")
        
        return result
    
    def _apply_position_limits(self, result: SizingResult, setup: TradeSetup) -> SizingResult:
        """应用仓位上下限"""
        # 上限
        if result.position_pct > self.config.max_position_pct:
            result.position_pct = self.config.max_position_pct
            result.position_value = self.current_equity * self.config.max_position_pct / 100
            result.position_size = result.position_value / setup.entry_price
        
        # 下限
        if result.position_pct < self.config.min_position_pct:
            result.position_pct = self.config.min_position_pct
            result.position_value = self.current_equity * self.config.min_position_pct / 100
            result.position_size = result.position_value / setup.entry_price
        
        return result
    
    def get_sizing_summary(self) -> Dict[str, Any]:
        """获取仓位配置摘要"""
        return {
            "current_equity": self.current_equity,
            "current_drawdown_pct": self.current_drawdown,
            "config": {
                "max_risk_per_trade_pct": self.config.max_risk_per_trade_pct,
                "target_annual_volatility": self.config.target_annual_volatility,
                "kelly_fraction": self.config.kelly_fraction,
                "max_position_pct": self.config.max_position_pct,
            },
            "available_methods": [
                {"id": "fixed_risk", "name": "固定风险法", "best_for": "最简单最安全，新手默认"},
                {"id": "vol_target", "name": "波动率目标法", "best_for": "多策略组合，风险恒定"},
                {"id": "kelly_fraction", "name": "分数Kelly法", "best_for": "有历史数据，知道胜率盈亏比"},
            ]
        }


# 全局单例
_engine: Optional[PositionSizingEngine] = None


def get_sizing_engine() -> PositionSizingEngine:
    """获取仓位管理引擎单例"""
    global _engine
    if _engine is None:
        _engine = PositionSizingEngine()
    return _engine
