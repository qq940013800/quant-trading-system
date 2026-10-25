"""
价格行为识别模块（L4 Price Action）

第一性原理：
- K线本身就是信息，不需要指标
- 重要的是价格在关键位置的反应，而不是价格本身
- 经典价格形态经过几十年验证，有统计上的有效性

全球顶级机构实践：
- ICT Inner Circle Trader：订单块、流动性猎杀、公平价值缺口
- Sam Seiden：供应需求区价格行为交易法
- Al Brooks：价格行为圣经，逐K线分析

核心原则：
1. 位置比形态重要 —— 同样的形态在支撑位和阻力位意义完全不同
2. 确认比预测重要 —— 形态出现后等确认，不要抢跑
3. 组合比单个形态重要 —— 多个形态叠加胜率更高
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from app.utils.logger import get_logger

logger = get_logger(__name__)


class PriceActionPattern(Enum):
    """价格行为形态枚举"""
    BULLISH_ENGULFING = "bullish_engulfing"      # 看涨吞没
    BEARISH_ENGULFING = "bearish_engulfing"      # 看跌吞没
    BULLISH_PIN_BAR = "bullish_pin_bar"           # 看涨针形线（锤子线）
    BEARISH_PIN_BAR = "bearish_pin_bar"           # 看跌针形线（流星线）
    INSIDE_BAR = "inside_bar"                       # 内包线
    OUTSIDE_BAR = "outside_bar"                     # 外包线
    DOJI = "doji"                                    # 十字星
    NO_PATTERN = "no_pattern"                       # 无明显形态


@dataclass
class PriceActionFeatures:
    """价格行为特征"""
    # 当前K线
    open_price: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: float = 0.0
    
    # 前一根K线
    prev_open: float = 0.0
    prev_high: float = 0.0
    prev_low: float = 0.0
    prev_close: float = 0.0
    prev_volume: float = 0.0
    
    # 位置信息
    near_support: bool = False          # 是否在支撑位附近
    near_resistance: bool = False      # 是否在阻力位附近


@dataclass
class PriceActionResult:
    """价格行为识别结果"""
    pattern: PriceActionPattern
    direction: str                    # bullish / bearish / neutral
    strength: float                   # 形态强度 (0~1)
    confidence: float                  # 置信度 (0~1)
    description: str = ""
    reasons: List[str] = field(default_factory=list)


class PriceActionDetector:
    """
    价格行为识别器（L4）
    
    输入：当前K线 + 前一根K线 + 位置信息
    输出：识别出的价格形态、方向、强度、置信度
    """
    
    def __init__(self):
        self.body_ratio_threshold = 0.6    # 实体占比阈值
        self.wick_ratio_threshold = 2.0    # 影线比例阈值
        
    def detect(self, features: PriceActionFeatures) -> PriceActionResult:
        """
        识别价格行为形态
        
        Args:
            features: 价格行为特征
            
        Returns:
            PriceActionResult: 识别结果
        """
        reasons = []
        
        # 1. 计算K线基本特征
        body = abs(features.close - features.open)
        upper_wick = features.high - max(features.close, features.open)
        lower_wick = min(features.close, features.open) - features.low
        total_range = features.high - features.low
        
        if total_range == 0:
            return PriceActionResult(
                pattern=PriceActionPattern.NO_PATTERN,
                direction="neutral",
                strength=0.0,
                confidence=0.0,
                description="K线无波动"
            )
        
        body_ratio = body / total_range
        
        # 2. 识别形态
        pattern = self._identify_pattern(features, body_ratio, upper_wick, lower_wick)
        
        # 3. 判断方向
        direction = self._get_direction(pattern, features)
        
        # 4. 计算强度和置信度
        strength = self._calculate_strength(pattern, features, body_ratio)
        confidence = self._calculate_confidence(pattern, features, strength)
        
        # 5. 生成描述
        description = self._generate_description(pattern, features)
        
        return PriceActionResult(
            pattern=pattern,
            direction=direction,
            strength=strength,
            confidence=confidence,
            description=description,
            reasons=reasons
        )
    
    def _identify_pattern(self, features: PriceActionFeatures, body_ratio: float, 
                         upper_wick: float, lower_wick: float) -> PriceActionPattern:
        """识别具体形态"""
        
        # 十字星：实体很小
        if body_ratio < 0.1:
            return PriceActionPattern.DOJI
        
        # 吞没形态
        bullish_engulfing = (
            features.prev_close < features.prev_open and  # 前一根阴线
            features.close > features.open and            # 当前阳线
            features.open <= features.prev_close and       # 开盘价低于前收盘价
            features.close >= features.prev_open           # 收盘价高于前开盘价
        )
        if bullish_engulfing:
            return PriceActionPattern.BULLISH_ENGULFING
            
        bearish_engulfing = (
            features.prev_close > features.prev_open and  # 前一根阳线
            features.close < features.open and            # 当前阴线
            features.open >= features.prev_close and       # 开盘价高于前收盘价
            features.close <= features.prev_open           # 收盘价低于前开盘价
        )
        if bearish_engulfing:
            return PriceActionPattern.BEARISH_ENGULFING
        
        # 针形线（锤子线/流星线）
        if lower_wick > body * self.wick_ratio_threshold and upper_wick < body * 0.5:
            return PriceActionPattern.BULLISH_PIN_BAR  # 锤子线
            
        if upper_wick > body * self.wick_ratio_threshold and lower_wick < body * 0.5:
            return PriceActionPattern.BEARISH_PIN_BAR  # 流星线
        
        # 内包线
        inside_bar = (
            features.high < features.prev_high and
            features.low > features.prev_low
        )
        if inside_bar:
            return PriceActionPattern.INSIDE_BAR
        
        # 外包线
        outside_bar = (
            features.high > features.prev_high and
            features.low < features.prev_low
        )
        if outside_bar:
            return PriceActionPattern.OUTSIDE_BAR
        
        return PriceActionPattern.NO_PATTERN
    
    def _get_direction(self, pattern: PriceActionPattern, features: PriceActionFeatures) -> str:
        """判断形态方向"""
        bullish_patterns = [
            PriceActionPattern.BULLISH_ENGULFING,
            PriceActionPattern.BULLISH_PIN_BAR
        ]
        bearish_patterns = [
            PriceActionPattern.BEARISH_ENGULFING,
            PriceActionPattern.BEARISH_PIN_BAR
        ]
        
        if pattern in bullish_patterns:
            return "bullish"
        elif pattern in bearish_patterns:
            return "bearish"
        else:
            return "neutral"
    
    def _calculate_strength(self, pattern: PriceActionPattern, 
                           features: PriceActionFeatures, body_ratio: float) -> float:
        """计算形态强度"""
        base_strength = {
            PriceActionPattern.BULLISH_ENGULFING: 0.7,
            PriceActionPattern.BEARISH_ENGULFING: 0.7,
            PriceActionPattern.BULLISH_PIN_BAR: 0.6,
            PriceActionPattern.BEARISH_PIN_BAR: 0.6,
            PriceActionPattern.INSIDE_BAR: 0.4,
            PriceActionPattern.OUTSIDE_BAR: 0.5,
            PriceActionPattern.DOJI: 0.3,
            PriceActionPattern.NO_PATTERN: 0.0
        }.get(pattern, 0.0)
        
        # 成交量加成
        if features.volume > features.prev_volume * 1.5:
            base_strength *= 1.2  # 放量加成
        
        # 位置加成
        if features.near_support and base_strength > 0:
            base_strength *= 1.1  # 支撑位加成
        if features.near_resistance and base_strength > 0:
            base_strength *= 1.1  # 阻力位加成
        
        return min(1.0, base_strength)
    
    def _calculate_confidence(self, pattern: PriceActionPattern, 
                             features: PriceActionFeatures, strength: float) -> float:
        """计算置信度"""
        # 形态本身的可信度
        base_confidence = strength * 0.8
        
        # 位置加成
        if features.near_support or features.near_resistance:
            base_confidence *= 1.1
        
        return min(1.0, base_confidence)
    
    def _generate_description(self, pattern: PriceActionPattern, 
                             features: PriceActionFeatures) -> str:
        """生成形态描述"""
        descriptions = {
            PriceActionPattern.BULLISH_ENGULFING: "看涨吞没形态，多头力量强劲",
            PriceActionPattern.BEARISH_ENGULFING: "看跌吞没形态，空头力量强劲",
            PriceActionPattern.BULLISH_PIN_BAR: "锤子线，下档支撑强劲",
            PriceActionPattern.BEARISH_PIN_BAR: "流星线，上档阻力强劲",
            PriceActionPattern.INSIDE_BAR: "内包线，盘整蓄势",
            PriceActionPattern.OUTSIDE_BAR: "外包线，波动放大",
            PriceActionPattern.DOJI: "十字星，多空平衡",
            PriceActionPattern.NO_PATTERN: "无明显价格形态"
        }
        return descriptions.get(pattern, "")
    
    def get_summary(self, result: PriceActionResult) -> Dict[str, Any]:
        """获取识别结果摘要"""
        return {
            "pattern": result.pattern.value,
            "direction": result.direction,
            "strength": round(result.strength, 2),
            "confidence": round(result.confidence, 2),
            "description": result.description
        }
