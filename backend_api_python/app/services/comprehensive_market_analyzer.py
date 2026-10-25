"""
综合市场分析模块（L1-L5五层整合）

第一性原理：
- 市场分析是从宏观到微观的层层递进
- L1 市场状态 → 决定用什么策略
- L2 市场结构 → 决定在哪里入场止损
- L3 市场趋势 → 决定方向和仓位
- L4 价格行为 → 决定精确入场时机
- L5 K线形态 → 决定最终入场信号

全球顶级机构实践：
- Jane Street：多层级决策体系，每层都有否决权
- Renaissance：弱信号叠加，每层贡献一点alpha
- Two Sigma：特征工程，把所有层级的特征都喂给模型

核心原则：
1. 从上到下过滤 —— 上层否决了，下层不用看
2. 多层共振才入场 —— 五层都指向同一个方向，胜率最高
3. 每层独立判断 —— 不要让下层影响上层的判断
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.services.market_regime import MarketRegimeDetector, RegimeFeatures, MarketRegime
from app.services.market_structure import MarketStructureDetector
from app.services.market_trend import MarketTrendDetector, TrendFeatures, TrendDirection
from app.services.price_action import PriceActionDetector, PriceActionFeatures
from app.services.candlestick_patterns import CandlestickPatternDetector, KlineFeatures
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class MarketAnalysisResult:
    """综合市场分析结果"""
    # L1 市场状态
    regime: str = ""
    regime_score: float = 0.0
    
    # L2 市场结构
    structure: str = ""
    support: float = 0.0
    resistance: float = 0.0
    
    # L3 市场趋势
    trend_direction: str = ""
    trend_strength: float = 0.0
    trend_stage: str = ""
    
    # L4 价格行为
    price_action_pattern: str = ""
    price_action_direction: str = ""
    
    # L5 K线形态
    candlestick_pattern: str = ""
    candlestick_direction: str = ""
    
    # 综合判断
    overall_direction: str = ""          # bullish / bearish / neutral
    confidence: float = 0.0              # 综合置信度 (0~1)
    entry_zone: str = ""                 # 建议入场区域
    stop_loss: float = 0.0               # 建议止损位
    reasons: List[str] = field(default_factory=list)


class ComprehensiveMarketAnalyzer:
    """
    综合市场分析器（L1-L5五层整合）
    
    输入：K线数据 + 技术指标
    输出：综合市场分析结果
    """
    
    def __init__(self):
        self.regime_detector = MarketRegimeDetector()
        self.structure_detector = MarketStructureDetector()
        self.trend_detector = MarketTrendDetector()
        self.price_action_detector = PriceActionDetector()
        self.pattern_detector = CandlestickPatternDetector()
        
    def analyze(self, kline_data: List[Dict[str, float]]) -> MarketAnalysisResult:
        """
        综合市场分析
        
        Args:
            kline_data: K线数据列表，最新一根在最后
            
        Returns:
            MarketAnalysisResult: 综合分析结果
        """
        result = MarketAnalysisResult()
        
        if len(kline_data) < 50:
            result.reasons.append("K线数据不足，无法分析")
            return result
        
        # 提取最新数据
        latest = kline_data[-1]
        prev = kline_data[-2]
        
        # ========== L1 市场状态识别 ==========
        try:
            regime_features = self._extract_regime_features(kline_data)
            regime_result = self.regime_detector.detect(regime_features)
            result.regime = regime_result.current_regime.value
            result.regime_score = regime_result.confidence
            result.reasons.append(f"L1 市场状态: {result.regime}")
        except Exception as e:
            logger.warning(f"L1 市场状态识别失败: {e}")
            result.regime = "unknown"
        
        # ========== L2 市场结构识别 ==========
        try:
            closes = [k['close'] for k in kline_data]
            highs = [k['high'] for k in kline_data]
            lows = [k['low'] for k in kline_data]
            
            self.structure_detector.detect_swing_points(highs, lows, closes)
            self.structure_detector.detect_structure_breaks(closes)
            sr = self.structure_detector.calculate_support_resistance()
            
            result.support = sr.get('support', 0.0)
            result.resistance = sr.get('resistance', 0.0)
            result.structure = "bullish" if closes[-1] > closes[-20] else "bearish"
            result.reasons.append(f"L2 市场结构: 支撑={result.support:.2f}, 阻力={result.resistance:.2f}")
        except Exception as e:
            logger.warning(f"L2 市场结构识别失败: {e}")
        
        # ========== L3 市场趋势识别 ==========
        try:
            trend_features = self._extract_trend_features(kline_data)
            trend_result = self.trend_detector.detect(trend_features)
            result.trend_direction = trend_result.direction.value
            result.trend_strength = trend_result.strength
            result.trend_stage = trend_result.stage.value
            result.reasons.append(f"L3 市场趋势: {result.trend_direction}, 强度={result.trend_strength:.2f}")
        except Exception as e:
            logger.warning(f"L3 市场趋势识别失败: {e}")
        
        # ========== L4 价格行为识别 ==========
        try:
            pa_features = PriceActionFeatures(
                open_price=latest['open'],
                high=latest['high'],
                low=latest['low'],
                close=latest['close'],
                volume=latest['volume'],
                prev_open=prev['open'],
                prev_high=prev['high'],
                prev_low=prev['low'],
                prev_close=prev['close'],
                prev_volume=prev['volume'],
                near_support=latest['close'] < result.support * 1.01,
                near_resistance=latest['close'] > result.resistance * 0.99
            )
            pa_result = self.price_action_detector.detect(pa_features)
            result.price_action_pattern = pa_result.pattern.value
            result.price_action_direction = pa_result.direction
            result.reasons.append(f"L4 价格行为: {result.price_action_pattern}")
        except Exception as e:
            logger.warning(f"L4 价格行为识别失败: {e}")
        
        # ========== L5 K线形态识别 ==========
        try:
            kline_features = KlineFeatures(
                k1=kline_data[-1],
                k2=kline_data[-2],
                k3=kline_data[-3],
                at_bottom=latest['close'] < result.support * 1.02,
                at_top=latest['close'] > result.resistance * 0.98,
                trend_direction=result.trend_direction
            )
            pattern_result = self.pattern_detector.detect(kline_features)
            result.candlestick_pattern = pattern_result.pattern.value
            result.candlestick_direction = pattern_result.direction
            result.reasons.append(f"L5 K线形态: {result.candlestick_pattern}")
        except Exception as e:
            logger.warning(f"L5 K线形态识别失败: {e}")
        
        # ========== 综合判断 ==========
        result.overall_direction, result.confidence = self._calculate_overall_direction(result)
        
        # 建议入场区域和止损
        if result.overall_direction == "bullish":
            result.entry_zone = f"接近支撑位 {result.support:.2f} 附近"
            result.stop_loss = result.support * 0.99  # 支撑位下方1%
        elif result.overall_direction == "bearish":
            result.entry_zone = f"接近阻力位 {result.resistance:.2f} 附近"
            result.stop_loss = result.resistance * 1.01  # 阻力位上方1%
        
        return result
    
    def _extract_regime_features(self, kline_data: List[Dict]) -> RegimeFeatures:
        """提取市场状态特征"""
        # 简化版，实际应该计算真实指标
        closes = [k['close'] for k in kline_data]
        returns = [closes[i]/closes[i-1] - 1 for i in range(1, len(closes))]
        
        avg_return = sum(returns[-20:]) / 20
        volatility = (sum([(r - avg_return)**2 for r in returns[-20:]]) / 20) ** 0.5
        
        return RegimeFeatures(
            adx=30.0,  # 简化值
            trend_strength=avg_return * 100,
            ma_alignment=0.5,
            atr_pct=volatility * 100,
            volatility_ratio=1.0
        )
    
    def _extract_trend_features(self, kline_data: List[Dict]) -> TrendFeatures:
        """提取趋势特征"""
        closes = [k['close'] for k in kline_data]
        
        ma_fast = sum(closes[-10:]) / 10
        ma_slow = sum(closes[-30:]) / 30
        
        return TrendFeatures(
            ma_fast=ma_fast,
            ma_slow=ma_slow,
            ma_alignment=(ma_fast - ma_slow) / ma_slow,
            adx=30.0,
            trend_strength=(ma_fast - ma_slow) / ma_slow,
            slope=0.001,
            higher_highs=3,
            higher_lows=3,
            volume_trend=0.0
        )
    
    def _calculate_overall_direction(self, result: MarketAnalysisResult) -> tuple:
        """计算综合方向和置信度"""
        bullish_score = 0
        bearish_score = 0
        
        # L1 市场状态
        if result.regime in ["strong_trend_up", "weak_trend_up"]:
            bullish_score += 2
        elif result.regime in ["strong_trend_down", "weak_trend_down"]:
            bearish_score += 2
        
        # L3 趋势方向
        if result.trend_direction == "up":
            bullish_score += 2
        elif result.trend_direction == "down":
            bearish_score += 2
        
        # L4 价格行为
        if result.price_action_direction == "bullish":
            bullish_score += 1
        elif result.price_action_direction == "bearish":
            bearish_score += 1
        
        # L5 K线形态
        if result.candlestick_direction == "bullish":
            bullish_score += 1
        elif result.candlestick_direction == "bearish":
            bearish_score += 1
        
        # 综合判断
        total = bullish_score + bearish_score
        if total == 0:
            return "neutral", 0.0
        
        confidence = abs(bullish_score - bearish_score) / total
        
        if bullish_score > bearish_score:
            return "bullish", confidence
        elif bearish_score > bullish_score:
            return "bearish", confidence
        else:
            return "neutral", 0.0
    
    def get_summary(self, result: MarketAnalysisResult) -> Dict[str, Any]:
        """获取分析结果摘要"""
        return {
            "l1_regime": result.regime,
            "l2_structure": result.structure,
            "l3_trend": result.trend_direction,
            "l4_price_action": result.price_action_pattern,
            "l5_candlestick": result.candlestick_pattern,
            "overall_direction": result.overall_direction,
            "confidence": round(result.confidence, 2),
            "support": round(result.support, 2),
            "resistance": round(result.resistance, 2),
            "entry_zone": result.entry_zone,
            "stop_loss": round(result.stop_loss, 2),
            "reasons": result.reasons
        }
