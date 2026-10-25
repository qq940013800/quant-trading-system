"""
策略健康度监控系统
健康度三级 + 自动退役机制

对标 Millennium Management 的多策略生命周期管理：
- 绿区（Active）：正常运行，资金充足
- 黄区（Watch）：需要关注，减少仓位
- 红区（Suspended）：暂停运行，准备退役

任何 Alpha 都有生命周期：发现 → 验证 → 规模化 → 拥挤 → 衰减 → 失效 → 退役
"""
import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta


@dataclass
class StrategyHealth:
    """策略健康度"""
    strategy_id: str
    strategy_name: str
    status: str  # active / watch / suspended
    health_score: float  # 0-100
    
    # 核心指标
    recent_sharpe: float  # 近30天夏普
    recent_drawdown: float  # 近30天最大回撤 (%)
    win_rate: float  # 近30天胜率 (%)
    trade_count: int  # 近30天交易次数
    
    # 衰减指标
    sharpe_decay: float  # 夏普衰减率（vs 上线时）
    performance_trend: str  # improving / stable / declining
    
    # 建议
    recommendation: str
    next_review: str  # 下次复检时间
    
    def to_dict(self):
        return asdict(self)


class StrategyHealthMonitor:
    """策略健康度监控器"""
    
    def __init__(self):
        # 阈值配置（基于行业最佳实践）
        self.sharpe_green = 1.0
        self.sharpe_watch = 0.5
        self.sharpe_red = 0.0
        
    def evaluate_health(self, strategy_id: str, 
                       strategy_name: str,
                       recent_returns: np.ndarray,
                       baseline_sharpe: float = 1.5) -> StrategyHealth:
        """评估策略健康度"""
        if len(recent_returns) < 10:
            return self._insufficient_data_health(strategy_id, strategy_name)
        
        # 夏普比率
        if np.std(recent_returns) > 0:
            recent_sharpe = np.mean(recent_returns) / np.std(recent_returns) * np.sqrt(252)
        else:
            recent_sharpe = 0
        
        # 最大回撤
        cumulative = np.cumprod(1 + recent_returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - running_max) / running_max
        recent_drawdown = abs(np.min(drawdown)) * 100  # 转为百分比
        
        # 胜率
        win_rate = np.sum(recent_returns > 0) / len(recent_returns) * 100
        
        # 交易次数（近似）
        trade_count = len(recent_returns)
        
        # 夏普衰减率
        sharpe_decay = (1 - recent_sharpe / baseline_sharpe) * 100 if baseline_sharpe > 0 else 0
        
        # 趋势判断
        if len(recent_returns) >= 20:
            recent_half = recent_returns[-10:]
            previous_half = recent_returns[:-10]
            recent_avg = np.mean(recent_half)
            previous_avg = np.mean(previous_half)
            
            if recent_avg > previous_avg * 1.2:
                performance_trend = "improving"
            elif recent_avg < previous_avg * 0.8:
                performance_trend = "declining"
            else:
                performance_trend = "stable"
        else:
            performance_trend = "stable"
        
        # 综合健康评分
        health_score = self._calculate_health_score(
            recent_sharpe, recent_drawdown, win_rate, 
            sharpe_decay, performance_trend
        )
        
        # 确定状态
        status = self._determine_status(health_score, recent_sharpe, recent_drawdown)
        
        # 生成建议
        recommendation = self._generate_recommendation(
            status, health_score, sharpe_decay, performance_trend
        )
        
        # 下次复检时间
        next_review = self._next_review_date(status)
        
        return StrategyHealth(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            status=status,
            health_score=round(health_score, 1),
            recent_sharpe=round(recent_sharpe, 2),
            recent_drawdown=round(recent_drawdown, 2),
            win_rate=round(win_rate, 1),
            trade_count=trade_count,
            sharpe_decay=round(sharpe_decay, 1),
            performance_trend=performance_trend,
            recommendation=recommendation,
            next_review=next_review
        )
    
    def _calculate_health_score(self, sharpe: float, drawdown: float,
                               win_rate: float, decay: float,
                               trend: str) -> float:
        """计算综合健康评分 0-100"""
        score = 50
        
        # 夏普贡献
        if sharpe > 2.0:
            score += 25
        elif sharpe > 1.0:
            score += 15
        elif sharpe > 0.5:
            score += 5
        elif sharpe < 0:
            score -= 25
        
        # 回撤贡献
        if drawdown < 5:
            score += 10
        elif drawdown < 10:
            score += 0
        elif drawdown < 20:
            score -= 10
        else:
            score -= 20
        
        # 胜率贡献
        if win_rate > 60:
            score += 10
        elif win_rate > 50:
            score += 5
        elif win_rate < 40:
            score -= 10
        
        # 衰减贡献
        if decay < 20:
            score += 5
        elif decay < 40:
            score -= 5
        else:
            score -= 15
        
        # 趋势贡献
        if trend == "improving":
            score += 5
        elif trend == "declining":
            score -= 5
        
        return max(0, min(100, score))
    
    def _determine_status(self, health_score: float, 
                         sharpe: float, drawdown: float) -> str:
        """确定策略状态"""
        if drawdown > 15:
            return "suspended"
        if sharpe < 0:
            return "suspended"
        
        if health_score >= 70:
            return "active"
        elif health_score >= 40:
            return "watch"
        else:
            return "suspended"
    
    def _generate_recommendation(self, status: str, score: float,
                                decay: float, trend: str) -> str:
        """生成建议"""
        if status == "active":
            if trend == "improving":
                return "✅ 策略表现优异，趋势向上，可以考虑增加仓位"
            else:
                return "✅ 策略正常运行，保持当前仓位"
        elif status == "watch":
            if decay > 30:
                return "⚠️ 夏普衰减明显，建议减少30%仓位，密切关注"
            elif trend == "declining":
                return "⚠️ 近期表现下滑，建议减少20%仓位，一周后复检"
            else:
                return "⚠️ 策略进入观察期，保持仓位但不新增资金"
        else:
            if score < 20:
                return "❌ 策略严重失效，建议立即平仓并准备退役"
            else:
                return "❌ 策略暂停运行，等待复检决定是否退役"
    
    def _next_review_date(self, status: str) -> str:
        """下次复检日期"""
        days = {
            "active": 30,
            "watch": 7,
            "suspended": 3
        }
        next_date = datetime.now() + timedelta(days=days.get(status, 7))
        return next_date.strftime("%Y-%m-%d")
    
    def _insufficient_data_health(self, strategy_id: str, strategy_name: str) -> StrategyHealth:
        """数据不足时的健康状态"""
        return StrategyHealth(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            status="watch",
            health_score=50,
            recent_sharpe=0,
            recent_drawdown=0,
            win_rate=0,
            trade_count=0,
            sharpe_decay=0,
            performance_trend="stable",
            recommendation="⏳ 数据不足，等待更多交易记录后评估",
            next_review=(datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
        )
    
    def check_retirement_candidates(self, strategies: List[StrategyHealth]) -> List[Dict]:
        """检查应该退役的策略"""
        retirement_candidates = []
        
        for s in strategies:
            should_retire = False
            reasons = []
            
            if s.status == "suspended":
                should_retire = True
                reasons.append("策略已进入红区暂停状态")
            
            if s.recent_sharpe < 0:
                should_retire = True
                reasons.append(f"夏普为负 ({s.recent_sharpe:.2f})")
            
            if s.recent_drawdown > 20:
                should_retire = True
                reasons.append(f"回撤超过20% ({s.recent_drawdown:.1f}%)")
            
            if s.sharpe_decay > 50:
                should_retire = True
                reasons.append(f"夏普衰减超过50% ({s.sharpe_decay:.1f}%)")
            
            if should_retire:
                retirement_candidates.append({
                    "strategy_id": s.strategy_id,
                    "strategy_name": s.strategy_name,
                    "health_score": s.health_score,
                    "reasons": reasons,
                    "action": "建议退役，释放资金给新策略"
                })
        
        return retirement_candidates
    
    def get_portfolio_overview(self, strategies: List[StrategyHealth]) -> Dict:
        """获取组合整体概览"""
        if not strategies:
            return {"total": 0, "active": 0, "watch": 0, "suspended": 0}
        
        active = sum(1 for s in strategies if s.status == "active")
        watch = sum(1 for s in strategies if s.status == "watch")
        suspended = sum(1 for s in strategies if s.status == "suspended")
        
        avg_health = np.mean([s.health_score for s in strategies])
        
        return {
            "total": len(strategies),
            "active": active,
            "watch": watch,
            "suspended": suspended,
            "avg_health_score": round(avg_health, 1),
            "healthy_ratio": round(active / len(strategies) * 100, 1)
        }


# 单例
health_monitor = StrategyHealthMonitor()
