"""
市场趋势识别模块（L3 Trend）

第一性原理：
- 趋势是有生命周期的：萌芽 → 发展 → 成熟 → 衰竭
- 不同阶段的趋势，入场点和止损位完全不同
- 趋势强度决定了仓位大小和持仓时间

全球顶级机构实践：
- Darius Dale：结构化趋势阶段分析（累积→上升→分配→下降）
- Citadel：多时间框架趋势一致性检查
- AQR：动量因子的半衰期衰减

核心原则：
1. 多时间框架确认 —— 大周期定方向，小周期找入场点
2. 趋势强度量化 —— 不是"有趋势"或"没趋势"，而是有多强
3. 阶段识别 —— 现在是趋势的哪个阶段？该追还是该等？
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from app.utils.logger import get_logger

logger = get_logger(__name__)


class TrendStage(Enum):
    """趋势阶段枚举"""
    ACCUMULATION = "accumulation"       # 累积阶段（底部震荡）
    MARKUP = "markup"                   # 上升阶段（趋势发展中）
    DISTRIBUTION = "distribution"      # 分配阶段（顶部震荡）
    MARKDOWN = "markdown"               # 下降阶段（趋势下跌中）
    UNKNOWN = "unknown"                 # 无法判断


class TrendDirection(Enum):
    """趋势方向枚举"""
    UP = "up"
    DOWN = "down"
    SIDEWAYS = "sideways"


@dataclass
class TrendFeatures:
    """趋势特征"""
    # 方向特征
    ma_fast: float = 0.0           # 快速均线价格
    ma_slow: float = 0.0           # 慢速均线价格
    ma_alignment: float = 0.0      # 均线排列度 (-1 ~ +1)
    
    # 强度特征
    adx: float = 0.0               # ADX趋势强度 (0~100)
    trend_strength: float = 0.0   # 综合趋势强度 (-1 ~ +1)
    slope: float = 0.0             # 趋势线斜率
    
    # 阶段特征
    higher_highs: int = 0          # 连续高点数
    higher_lows: int = 0           # 连续低点数
    volume_trend: float = 0.0      # 成交量趋势 (-1 ~ +1)


@dataclass
class TrendPrediction:
    """趋势预测结果"""
    direction: TrendDirection
    stage: TrendStage
    strength: float                # 趋势强度 (0~1)
    confidence: float              # 置信度 (0~1)
    score: float                   # 综合得分 (-1 ~ +1)
    reasons: List[str] = field(default_factory=list)
    timestamp: str = ""


class MarketTrendDetector:
    """
    市场趋势识别器（L3）
    
    输入：K线数据（收盘价、最高价、最低价、成交量）
    输出：趋势方向、阶段、强度、置信度
    """
    
    def __init__(self):
        self.min_adx_threshold = 25.0      # ADX > 25 认为有趋势
        self.strong_adx_threshold = 40.0    # ADX > 40 认为强趋势
        self.min_slope_threshold = 0.001    # 最小斜率阈值
        
    def detect(self, features: TrendFeatures) -> TrendPrediction:
        """
        识别市场趋势
        
        Args:
            features: 趋势特征
            
        Returns:
            TrendPrediction: 趋势预测结果
        """
        reasons = []
        score = 0.0
        
        # 1. 判断方向
        direction = self._detect_direction(features)
        if direction == TrendDirection.UP:
            score += 0.3
            reasons.append("均线多头排列")
        elif direction == TrendDirection.DOWN:
            score -= 0.3
            reasons.append("均线空头排列")
        else:
            reasons.append("均线缠绕，方向不明")
            
        # 2. 判断强度
        strength = self._calculate_strength(features)
        if features.adx > self.strong_adx_threshold:
            reasons.append(f"ADX={features.adx:.1f}，强趋势")
        elif features.adx > self.min_adx_threshold:
            reasons.append(f"ADX={features.adx:.1f}，中等趋势")
        else:
            reasons.append(f"ADX={features.adx:.1f}，趋势较弱")
            
        # 3. 判断阶段
        stage = self._detect_stage(features, direction)
        if stage == TrendStage.MARKUP:
            reasons.append("上升趋势发展阶段")
        elif stage == TrendStage.DISTRIBUTION:
            reasons.append("顶部分配阶段，注意风险")
        elif stage == TrendStage.MARKDOWN:
            reasons.append("下降趋势阶段，空头主导")
        elif stage == TrendStage.ACCUMULATION:
            reasons.append("底部累积阶段，观察等待")
            
        # 4. 计算置信度
        confidence = min(1.0, strength * 1.5)
        
        return TrendPrediction(
            direction=direction,
            stage=stage,
            strength=strength,
            confidence=confidence,
            score=score,
            reasons=reasons,
            timestamp=""
        )
    
    def _detect_direction(self, features: TrendFeatures) -> TrendDirection:
        """判断趋势方向"""
        if features.ma_fast > features.ma_slow * 1.005:  # 快线上穿慢线0.5%以上
            return TrendDirection.UP
        elif features.ma_fast < features.ma_slow * 0.995:  # 快线下穿慢线0.5%以上
            return TrendDirection.DOWN
        else:
            return TrendDirection.SIDEWAYS
    
    def _calculate_strength(self, features: TrendFeatures) -> float:
        """计算趋势强度 (0~1)"""
        # ADX贡献最大
        adx_score = min(1.0, features.adx / 50.0)
        
        # 均线排列度
        ma_score = abs(features.ma_alignment)
        
        # 综合
        strength = 0.6 * adx_score + 0.4 * ma_score
        return min(1.0, max(0.0, strength))
    
    def _detect_stage(self, features: TrendFeatures, direction: TrendDirection) -> TrendStage:
        """判断趋势阶段"""
        if features.adx < 20:
            # ADX低，可能是累积或分配阶段
            if features.higher_highs <= 2 and features.higher_lows <= 2:
                return TrendStage.ACCUMULATION  # 底部震荡
            else:
                return TrendStage.DISTRIBUTION  # 顶部震荡
        
        # ADX高，趋势发展中
        if direction == TrendDirection.UP:
            return TrendStage.MARKUP
        elif direction == TrendDirection.DOWN:
            return TrendStage.MARKDOWN
        
        return TrendStage.UNKNOWN
    
    def get_trend_summary(self, prediction: TrendPrediction) -> Dict[str, Any]:
        """获取趋势摘要"""
        return {
            "direction": prediction.direction.value,
            "stage": prediction.stage.value,
            "strength": round(prediction.strength, 2),
            "confidence": round(prediction.confidence, 2),
            "score": round(prediction.score, 2),
            "reasons": prediction.reasons
        }
