"""
K线形态识别模块（L5 Candlestick Patterns）

第一性原理：
- 经典K线形态是几百年交易经验的总结，有统计显著性
- 形态的可靠性取决于出现的位置（支撑/阻力位更有效）
- 多K线组合比单根K线更可靠

全球顶级机构实践：
- Steve Nison：K线形态之父，系统总结了经典形态
- 日本蜡烛图：起源于18世纪米市交易，实战检验几百年
- 现代量化：大样本回测验证形态有效性，过滤噪声

核心原则：
1. 位置决定意义 —— 同样的形态在高位和低位意义完全不同
2. 确认过滤假信号 —— 形态出现后等下一根K线确认
3. 多周期共振 —— 多时间周期同时出现形态，胜率更高
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from app.utils.logger import get_logger

logger = get_logger(__name__)


class CandlestickPattern(Enum):
    """经典K线形态枚举"""
    # 反转形态
    MORNING_STAR = "morning_star"                    # 早晨之星（底部反转）
    EVENING_STAR = "evening_star"                    # 黄昏之星（顶部反转）
    THREE_WHITE_SOLDIERS = "three_white_soldiers"    # 三只乌鸦（底部反转）
    THREE_BLACK_CROWS = "three_black_crows"          # 三只乌鸦（顶部反转）
    HAMMER = "hammer"                                  # 锤子线（底部反转）
    SHOOTING_STAR = "shooting_star"                  # 流星线（顶部反转）
    
    # 持续形态
    RISING_THREE_METHOD = "rising_three_method"      # 上升三法（持续上涨）
    FALLING_THREE_METHOD = "falling_three_method"    # 下降三法（持续下跌）
    
    # 其他
    NO_PATTERN = "no_pattern"                         # 无明显形态


@dataclass
class KlineFeatures:
    """K线特征（最近3根）"""
    # 最近3根K线
    k1: Dict[str, float] = field(default_factory=dict)  # 最新一根
    k2: Dict[str, float] = field(default_factory=dict)  # 中间一根
    k3: Dict[str, float] = field(default_factory=dict)  # 最早一根
    
    # 位置信息
    at_bottom: bool = False                          # 是否在底部区域
    at_top: bool = False                             # 是否在顶部区域
    trend_direction: str = "sideways"               # 当前趋势方向


@dataclass
class PatternResult:
    """K线形态识别结果"""
    pattern: CandlestickPattern
    type: str                                        # reversal / continuation
    direction: str                                   # bullish / bearish / neutral
    reliability: float                                # 形态可靠性 (0~1)
    description: str = ""
    reasons: List[str] = field(default_factory=list)


class CandlestickPatternDetector:
    """
    K线形态识别器（L5）
    
    输入：最近3根K线 + 位置信息
    输出：识别出的K线形态、类型、方向、可靠性
    """
    
    def __init__(self):
        self.body_threshold = 0.6        # 实体占比阈值
        self.wick_threshold = 2.0         # 影线比例阈值
        
    def detect(self, features: KlineFeatures) -> PatternResult:
        """
        识别K线形态
        
        Args:
            features: K线特征
            
        Returns:
            PatternResult: 识别结果
        """
        reasons = []
        
        # 1. 检查数据是否完整
        if not features.k1 or not features.k2 or not features.k3:
            return PatternResult(
                pattern=CandlestickPattern.NO_PATTERN,
                type="unknown",
                direction="neutral",
                reliability=0.0,
                description="K线数据不完整"
            )
        
        # 2. 识别形态
        pattern = self._identify_pattern(features)
        
        # 3. 判断类型和方向
        pattern_type = self._get_pattern_type(pattern)
        direction = self._get_direction(pattern)
        
        # 4. 计算可靠性
        reliability = self._calculate_reliability(pattern, features)
        
        # 5. 生成描述
        description = self._generate_description(pattern, features)
        
        return PatternResult(
            pattern=pattern,
            type=pattern_type,
            direction=direction,
            reliability=reliability,
            description=description,
            reasons=reasons
        )
    
    def _identify_pattern(self, features: KlineFeatures) -> CandlestickPattern:
        """识别具体K线形态"""
        k1, k2, k3 = features.k1, features.k2, features.k3
        
        # 计算每根K线的基本特征
        def get_kline_info(k):
            body = abs(k['close'] - k['open'])
            upper_wick = k['high'] - max(k['close'], k['open'])
            lower_wick = min(k['close'], k['open']) - k['low']
            total_range = k['high'] - k['low']
            body_ratio = body / total_range if total_range > 0 else 0
            is_bullish = k['close'] > k['open']
            return body, upper_wick, lower_wick, body_ratio, is_bullish
        
        b1, uw1, lw1, br1, bull1 = get_kline_info(k1)
        b2, uw2, lw2, br2, bull2 = get_kline_info(k2)
        b3, uw3, lw3, br3, bull3 = get_kline_info(k3)
        
        # 早晨之星（底部反转）
        morning_star = (
            not bull3 and br3 > 0.5 and                    # 第一根大阴线
            br2 < 0.3 and                                   # 第二根小实体（十字星）
            bull1 and br1 > 0.5 and                        # 第三根大阳线
            k1['close'] > (k2['open'] + k2['close']) / 2   # 第三根收盘价深入第一根实体
        )
        if morning_star and features.at_bottom:
            return CandlestickPattern.MORNING_STAR
        
        # 黄昏之星（顶部反转）
        evening_star = (
            bull3 and br3 > 0.5 and                        # 第一根大阳线
            br2 < 0.3 and                                   # 第二根小实体
            not bull1 and br1 > 0.5 and                    # 第三根大阴线
            k1['close'] < (k2['open'] + k2['close']) / 2   # 第三根收盘价深入第一根实体
        )
        if evening_star and features.at_top:
            return CandlestickPattern.EVENING_STAR
        
        # 三只白兵（底部反转）
        three_white_soldiers = (
            bull3 and bull2 and bull1 and                  # 连续三根阳线
            br3 > 0.5 and br2 > 0.5 and br1 > 0.5 and    # 都是大实体
            k2['close'] > k3['open'] and                    # 逐根创新高
            k1['close'] > k2['open']
        )
        if three_white_soldiers and features.at_bottom:
            return CandlestickPattern.THREE_WHITE_SOLDIERS
        
        # 三只乌鸦（顶部反转）
        three_black_crows = (
            not bull3 and not bull2 and not bull1 and      # 连续三根阴线
            br3 > 0.5 and br2 > 0.5 and br1 > 0.5 and    # 都是大实体
            k2['close'] < k3['open'] and                    # 逐根创新低
            k1['close'] < k2['open']
        )
        if three_black_crows and features.at_top:
            return CandlestickPattern.THREE_BLACK_CROWS
        
        return CandlestickPattern.NO_PATTERN
    
    def _get_pattern_type(self, pattern: CandlestickPattern) -> str:
        """判断形态类型（反转/持续）"""
        reversal_patterns = [
            CandlestickPattern.MORNING_STAR,
            CandlestickPattern.EVENING_STAR,
            CandlestickPattern.THREE_WHITE_SOLDIERS,
            CandlestickPattern.THREE_BLACK_CROWS,
            CandlestickPattern.HAMMER,
            CandlestickPattern.SHOOTING_STAR
        ]
        if pattern in reversal_patterns:
            return "reversal"
        else:
            return "continuation"
    
    def _get_direction(self, pattern: CandlestickPattern) -> str:
        """判断形态方向"""
        bullish_patterns = [
            CandlestickPattern.MORNING_STAR,
            CandlestickPattern.THREE_WHITE_SOLDIERS,
            CandlestickPattern.HAMMER,
            CandlestickPattern.RISING_THREE_METHOD
        ]
        bearish_patterns = [
            CandlestickPattern.EVENING_STAR,
            CandlestickPattern.THREE_BLACK_CROWS,
            CandlestickPattern.SHOOTING_STAR,
            CandlestickPattern.FALLING_THREE_METHOD
        ]
        
        if pattern in bullish_patterns:
            return "bullish"
        elif pattern in bearish_patterns:
            return "bearish"
        else:
            return "neutral"
    
    def _calculate_reliability(self, pattern: CandlestickPattern, 
                               features: KlineFeatures) -> float:
        """计算形态可靠性"""
        base_reliability = {
            CandlestickPattern.MORNING_STAR: 0.75,
            CandlestickPattern.EVENING_STAR: 0.75,
            CandlestickPattern.THREE_WHITE_SOLDIERS: 0.8,
            CandlestickPattern.THREE_BLACK_CROWS: 0.8,
            CandlestickPattern.HAMMER: 0.6,
            CandlestickPattern.SHOOTING_STAR: 0.6,
            CandlestickPattern.RISING_THREE_METHOD: 0.7,
            CandlestickPattern.FALLING_THREE_METHOD: 0.7,
            CandlestickPattern.NO_PATTERN: 0.0
        }.get(pattern, 0.0)
        
        # 位置加成
        if features.at_bottom and base_reliability > 0:
            base_reliability *= 1.1
        if features.at_top and base_reliability > 0:
            base_reliability *= 1.1
        
        return min(1.0, base_reliability)
    
    def _generate_description(self, pattern: CandlestickPattern, 
                             features: KlineFeatures) -> str:
        """生成形态描述"""
        descriptions = {
            CandlestickPattern.MORNING_STAR: "早晨之星，底部反转信号，看涨",
            CandlestickPattern.EVENING_STAR: "黄昏之星，顶部反转信号，看跌",
            CandlestickPattern.THREE_WHITE_SOLDIERS: "三只白兵，强势底部反转，看涨",
            CandlestickPattern.THREE_BLACK_CROWS: "三只乌鸦，强势顶部反转，看跌",
            CandlestickPattern.HAMMER: "锤子线，下档支撑强劲",
            CandlestickPattern.SHOOTING_STAR: "流星线，上档阻力强劲",
            CandlestickPattern.RISING_THREE_METHOD: "上升三法，上涨持续形态",
            CandlestickPattern.FALLING_THREE_METHOD: "下降三法，下跌持续形态",
            CandlestickPattern.NO_PATTERN: "无明显K线形态"
        }
        return descriptions.get(pattern, "")
    
    def get_summary(self, result: PatternResult) -> Dict[str, Any]:
        """获取识别结果摘要"""
        return {
            "pattern": result.pattern.value,
            "type": result.type,
            "direction": result.direction,
            "reliability": round(result.reliability, 2),
            "description": result.description
        }
