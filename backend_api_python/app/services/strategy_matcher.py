"""
策略匹配规则引擎（Strategy Matching Engine）

第一性原理：
- 没有万能策略，只有适合当前市场状态的策略
- 趋势市 → 趋势跟踪策略赚钱
- 震荡市 → 均值回归策略赚钱
- 危机市 → 现金为王，不要交易
- 自动匹配 = 自动选对"车"，在对的"路况"用对的策略

全球顶级机构实践：
- Millennium Management：PM动态资金分配，优胜劣汰
- Renaissance：多策略集成，根据状态自动切换权重
- Two Sigma：策略组合优化，风险平价分配
- Citadel：实时策略调度，根据市场状态调整

核心原则：
1. 决策可解释 —— 为什么选这个策略？基于什么市场状态？
2. 动态调整 —— 市场变了，策略组合也要变
3. 防抖动 —— 不能一天换8次策略，要有冷却期
4. 风险预算 —— 不同策略分配不同的风险额度
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)


class MarketRegimeType(Enum):
    """市场状态类型（和market_regime对齐）"""
    STRONG_TREND_UP = "strong_trend_up"
    WEAK_TREND_UP = "weak_trend_up"
    RANGE = "range"
    WEAK_TREND_DOWN = "weak_trend_down"
    STRONG_TREND_DOWN = "strong_trend_down"
    CRISIS = "crisis"


class StrategyStatus(Enum):
    """策略状态"""
    ACTIVE = "active"           # 运行中
    WATCH = "watch"             # 观察中（降低仓位）
    SUSPENDED = "suspended"     # 暂停（不交易）


@dataclass
class Strategy:
    """策略"""
    strategy_id: str
    name: str
    strategy_type: str          # trend_following / mean_reversion / breakout / arbitrage
    risk_budget: float = 1.0     # 风险预算（占总风险的%）
    performance_score: float = 0.0  # 绩效得分（夏普40%+回撤30%+胜率20%+稳定性10%）
    status: StrategyStatus = StrategyStatus.ACTIVE
    preferred_regimes: List[MarketRegimeType] = field(default_factory=list)  # 擅长的市场状态


@dataclass
class StrategyMatch:
    """策略匹配结果"""
    strategy_id: str
    strategy_name: str
    match_score: float           # 匹配度（0~1）
    allocation_pct: float         # 资金分配比例（%）
    expected_risk_pct: float     # 预期风险贡献
    reason: str                  # 为什么匹配这个策略


class StrategyMatcher:
    """
    策略匹配引擎
    
    工作流程：
    1. 输入：当前市场状态 + 策略池
    2. 计算每个策略和当前市场状态的匹配度
    3. 根据匹配度分配资金和风险预算
    4. 输出：推荐的策略组合 + 资金分配
    """
    
    def __init__(self):
        self.strategies: Dict[str, Strategy] = {}
        self.match_history: List[Dict[str, Any]] = []
        self.last_match_time: Optional[datetime] = None
        self.cooldown_minutes: int = 60  # 策略切换冷却期（分钟）
        
    def register_strategy(self, strategy: Strategy):
        """注册策略到策略池"""
        self.strategies[strategy.strategy_id] = strategy
        logger.info(f"策略注册: {strategy.name} ({strategy.strategy_type})")
    
    def match_strategies(self, current_regime: MarketRegimeType) -> List[StrategyMatch]:
        """
        根据当前市场状态匹配策略
        
        算法：
        1. 每个策略有一个"擅长的市场状态"列表
        2. 如果当前状态在列表里，匹配度=1.0
        3. 如果是相近状态，匹配度=0.6~0.8
        4. 如果完全不适合，匹配度=0.2以下
        5. 按匹配度归一化分配资金
        """
        matches = []
        
        for strategy in self.strategies.values():
            if strategy.status == StrategyStatus.SUSPENDED:
                continue
            
            # 计算匹配度
            match_score = self._calculate_match_score(strategy, current_regime)
            
            # 计算资金分配（后面归一化）
            allocation = match_score * strategy.risk_budget * (strategy.performance_score / 100 + 0.5)
            
            matches.append(StrategyMatch(
                strategy_id=strategy.strategy_id,
                strategy_name=strategy.name,
                match_score=match_score,
                allocation_pct=allocation,
                expected_risk_pct=allocation * 0.02,  # 假设2%风险
                reason=self._get_match_reason(strategy, current_regime, match_score)
            ))
        
        # 按匹配度排序
        matches.sort(key=lambda x: x.match_score, reverse=True)
        
        # 归一化分配比例（总和=100%）
        total = sum(m.allocation_pct for m in matches)
        if total > 0:
            for m in matches:
                m.allocation_pct = round(m.allocation_pct / total * 100, 1)
        
        # 记录匹配历史
        self.match_history.append({
            "timestamp": datetime.now().isoformat(),
            "regime": current_regime.value,
            "matches": [
                {
                    "strategy_id": m.strategy_id,
                    "match_score": m.match_score,
                    "allocation_pct": m.allocation_pct
                }
                for m in matches
            ]
        })
        self.last_match_time = datetime.now()
        
        return matches
    
    def _calculate_match_score(self, strategy: Strategy, regime: MarketRegimeType) -> float:
        """计算单个策略和市场状态的匹配度"""
        
        # 完全匹配（在擅长列表里）
        if regime in strategy.preferred_regimes:
            return 1.0
        
        # 策略类型和市场状态的匹配规则
        type_match_map = {
            "trend_following": {
                MarketRegimeType.STRONG_TREND_UP: 1.0,
                MarketRegimeType.WEAK_TREND_UP: 0.8,
                MarketRegimeType.STRONG_TREND_DOWN: 0.9,
                MarketRegimeType.WEAK_TREND_DOWN: 0.7,
                MarketRegimeType.RANGE: 0.2,
                MarketRegimeType.CRISIS: 0.1,
            },
            "mean_reversion": {
                MarketRegimeType.RANGE: 1.0,
                MarketRegimeType.WEAK_TREND_UP: 0.5,
                MarketRegimeType.WEAK_TREND_DOWN: 0.5,
                MarketRegimeType.STRONG_TREND_UP: 0.2,
                MarketRegimeType.STRONG_TREND_DOWN: 0.2,
                MarketRegimeType.CRISIS: 0.1,
            },
            "breakout": {
                MarketRegimeType.STRONG_TREND_UP: 0.9,
                MarketRegimeType.STRONG_TREND_DOWN: 0.9,
                MarketRegimeType.RANGE: 0.6,  # 区间突破
                MarketRegimeType.WEAK_TREND_UP: 0.7,
                MarketRegimeType.WEAK_TREND_DOWN: 0.7,
                MarketRegimeType.CRISIS: 0.3,
            },
            "arbitrage": {
                MarketRegimeType.RANGE: 0.9,
                MarketRegimeType.CRISIS: 0.8,  # 危机时套利机会多
                MarketRegimeType.WEAK_TREND_UP: 0.7,
                MarketRegimeType.WEAK_TREND_DOWN: 0.7,
                MarketRegimeType.STRONG_TREND_UP: 0.6,
                MarketRegimeType.STRONG_TREND_DOWN: 0.6,
            }
        }
        
        type_scores = type_match_map.get(strategy.strategy_type, {})
        return type_scores.get(regime, 0.5)
    
    def _get_match_reason(self, strategy: Strategy, regime: MarketRegimeType, score: float) -> str:
        """生成匹配理由"""
        if score >= 0.9:
            return f"高度匹配：{strategy.strategy_type}策略在{regime.value}表现最佳"
        elif score >= 0.7:
            return f"良好匹配：{strategy.strategy_type}策略适合{regime.value}环境"
        elif score >= 0.5:
            return f"一般匹配：{strategy.strategy_type}策略在{regime.value}有一定机会"
        else:
            return f"低度匹配：{strategy.strategy_type}策略不适合当前{regime.value}，降低仓位"
    
    def should_rematch(self) -> bool:
        """检查是否需要重新匹配（冷却期检查）"""
        if self.last_match_time is None:
            return True
        
        elapsed = datetime.now() - self.last_match_time
        return elapsed.total_seconds() > self.cooldown_minutes * 60
    
    def get_match_summary(self) -> Dict[str, Any]:
        """获取匹配结果摘要"""
        if not self.match_history:
            return {"last_match": None, "strategy_count": len(self.strategies)}
        
        last = self.match_history[-1]
        return {
            "last_match_time": last["timestamp"],
            "current_regime": last["regime"],
            "top_strategies": last["matches"][:3],  # 前3名策略
            "total_strategies": len(last["matches"]),
            "cooldown_active": not self.should_rematch(),
            "cooldown_remaining_min": max(0, int((self.cooldown_minutes - (datetime.now() - datetime.fromisoformat(last["timestamp"])).total_seconds() / 60)))
        }


# 全局单例
_matcher: Optional[StrategyMatcher] = None


def get_strategy_matcher() -> StrategyMatcher:
    """获取策略匹配引擎单例"""
    global _matcher
    if _matcher is None:
        _matcher = StrategyMatcher()
    return _matcher
