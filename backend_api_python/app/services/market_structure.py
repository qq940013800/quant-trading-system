"""
市场结构识别模块（L2 Market Structure）

第一性原理：
- 价格不是随机走的，是沿着高低点结构前进的
- 趋势 = 更高的高点 + 更高的低点（多头趋势）
- 反转 = 打破前一个结构低点（CHoCH特征变化）
- 突破 = 突破前一个结构高点（BOS结构突破）

全球顶级机构实践：
- ICT (Inner Circle Trader)：Smart Money Concepts 核心框架
- Wyckoff Method：积累/趋势/分配三阶段理论
- 机构订单流：聪明钱总是在结构位置行动
- 顶级交易员：不看指标，先看结构

核心原则：
1. 因果单向 —— 只用已收盘的K线识别结构
2. 客观可重复 —— 同样的价格数据，识别结果一致
3. 概率思维 —— 结构不是预测，是概率分布
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from app.utils.logger import get_logger

logger = get_logger(__name__)


class StructureType(Enum):
    """结构类型"""
    SWING_HIGH = "swing_high"      # 摆动高点
    SWING_LOW = "swing_low"        # 摆动低点
    BOS_BULL = "bos_bull"          # 多头结构突破
    BOS_BEAR = "bos_bear"          # 空头结构突破
    CHOCH_BULL = "choch_bull"      # 多头特征变化（反转向上）
    CHOCH_BEAR = "choch_bear"      # 空头特征变化（反转向下）


class TrendPhase(Enum):
    """趋势阶段（Wyckoff）"""
    ACCUMULATION = "accumulation"    # 积累阶段
    MARKUP = "markup"                # 上涨趋势
    DISTRIBUTION = "distribution"    # 分配阶段
    MARKDOWN = "markdown"            # 下跌趋势


@dataclass
class SwingPoint:
    """摆动点（高低点）"""
    index: int                  # K线索引
    timestamp: datetime         # 时间
    price: float                # 价格
    type: StructureType         # swing_high 或 swing_low
    strength: float = 1.0       # 强度（确认了多少根K线）


@dataclass
class StructureEvent:
    """结构事件（BOS/CHoCH）"""
    index: int                  # 发生位置
    timestamp: datetime         # 时间
    type: StructureType         # BOS/CHoCH类型
    broken_level: float         # 被突破的价格位
    previous_swing_index: int    # 被突破的摆动点索引
    strength: float = 1.0       # 突破强度


@dataclass
class SupportResistance:
    """支撑阻力位"""
    price: float                # 价格位
    type: str                   # support / resistance
    touch_count: int = 1         # 触碰次数
    strength: float = 1.0        # 强度（触碰次数越多越强）
    last_touch: datetime = field(default_factory=datetime.now)


class MarketStructureDetector:
    """
    市场结构识别器
    
    识别流程：
    1. 第一步：识别摆动高低点（Swing High/Low）
    2. 第二步：识别结构突破（BOS）和特征变化（CHoCH）
    3. 第三步：绘制支撑阻力位
    4. 第四步：判断当前趋势阶段
    """
    
    def __init__(self, swing_lookback: int = 2):
        """
        参数：
            swing_lookback: 摆动点确认需要的左右K线数
                2 = 左侧2根+右侧2根都比它低，才确认是高点
                数值越大，摆动点越可靠，但也越滞后
        """
        self.swing_lookback = swing_lookback
        self.swing_points: List[SwingPoint] = []
        self.structure_events: List[StructureEvent] = []
        self.support_resistances: List[SupportResistance] = []
        self.current_trend: str = "range"  # up / down / range
        
    def detect_swing_points(self, highs: List[float], lows: List[float], 
                           timestamps: List[datetime]) -> List[SwingPoint]:
        """
        识别摆动高低点
        
        规则：
        - 高点：当前K线的最高价 > 左侧N根 + 右侧N根的最高价
        - 低点：当前K线的最低价 < 左侧N根 + 右侧N根的最低价
        
        注意：右侧N根需要已经收盘（因果性）
        """
        swings = []
        n = self.swing_lookback
        
        for i in range(n, len(highs) - n):
            # 检查是否是摆动高点
            is_high = True
            for j in range(1, n + 1):
                if highs[i] < highs[i-j] or highs[i] < highs[i+j]:
                    is_high = False
                    break
            
            if is_high:
                swings.append(SwingPoint(
                    index=i,
                    timestamp=timestamps[i],
                    price=highs[i],
                    type=StructureType.SWING_HIGH,
                    strength=n
                ))
            
            # 检查是否是摆动低点
            is_low = True
            for j in range(1, n + 1):
                if lows[i] > lows[i-j] or lows[i] > lows[i+j]:
                    is_low = False
                    break
            
            if is_low:
                swings.append(SwingPoint(
                    index=i,
                    timestamp=timestamps[i],
                    price=lows[i],
                    type=StructureType.SWING_LOW,
                    strength=n
                ))
        
        self.swing_points = swings
        return swings
    
    def detect_structure_breaks(self, closes: List[float]) -> List[StructureEvent]:
        """
        识别结构突破（BOS）和特征变化（CHoCH）
        
        定义：
        - BOS (Break of Structure)：趋势延续，突破前一个同向结构点
          - 多头BOS：价格突破前一个摆动高点（上升趋势延续）
          - 空头BOS：价格跌破前一个摆动低点（下降趋势延续）
        
        - CHoCH (Change of Character)：趋势反转，突破前一个反向结构点
          - 多头CHoCH：价格突破前一个摆动低点（下降趋势反转向上）
          - 空头CHoCH：价格跌破前一个摆动高点（上升趋势反转向下）
        """
        events = []
        swings = self.swing_points
        
        if len(swings) < 4:
            return events
        
        # 按索引排序
        sorted_swings = sorted(swings, key=lambda s: s.index)
        
        # 找最近的两个高点和两个低点
        recent_highs = [s for s in sorted_swings if s.type == StructureType.SWING_HIGH][-2:]
        recent_lows = [s for s in sorted_swings if s.type == StructureType.SWING_LOW][-2:]
        
        if len(recent_highs) < 2 or len(recent_lows) < 2:
            return events
        
        last_close = closes[-1]
        
        # 判断多头BOS：突破前一个高点
        prev_high = recent_highs[-2]
        current_high = recent_highs[-1]
        
        if last_close > current_high.price:
            # 突破了最新的高点
            if self.current_trend == "up":
                # 上升趋势延续 = BOS
                event_type = StructureType.BOS_BULL
            else:
                # 从下跌/震荡转上涨 = CHoCH
                event_type = StructureType.CHOCH_BULL
            
            events.append(StructureEvent(
                index=len(closes) - 1,
                timestamp=datetime.now(),
                type=event_type,
                broken_level=current_high.price,
                previous_swing_index=current_high.index,
                strength=1.0
            ))
            self.current_trend = "up"
        
        # 判断空头BOS：跌破前一个低点
        prev_low = recent_lows[-2]
        current_low = recent_lows[-1]
        
        if last_close < current_low.price:
            # 跌破了最新的低点
            if self.current_trend == "down":
                # 下降趋势延续 = BOS
                event_type = StructureType.BOS_BEAR
            else:
                # 从上涨/震荡转下跌 = CHoCH
                event_type = StructureType.CHOCH_BEAR
            
            events.append(StructureEvent(
                index=len(closes) - 1,
                timestamp=datetime.now(),
                type=event_type,
                broken_level=current_low.price,
                previous_swing_index=current_low.index,
                strength=1.0
            ))
            self.current_trend = "down"
        
        self.structure_events = events
        return events
    
    def calculate_support_resistance(self, tolerance_pct: float = 0.5) -> List[SupportResistance]:
        """
        计算支撑阻力位
        
        规则：
        - 收集所有摆动高点 → 阻力位
        - 收集所有摆动低点 → 支撑位
        - 相近的价位合并（容差范围内算同一个位）
        - 触碰次数越多，强度越高
        """
        levels = []
        tolerance = tolerance_pct / 100
        
        # 收集所有摆动高点作为阻力
        highs = sorted([s.price for s in self.swing_points if s.type == StructureType.SWING_HIGH])
        
        for price in highs:
            # 检查是否和已有的阻力位相近
            merged = False
            for level in levels:
                if level.type == "resistance":
                    diff_pct = abs(price - level.price) / level.price
                    if diff_pct < tolerance:
                        level.touch_count += 1
                        level.strength = 1.0 + level.touch_count * 0.5
                        merged = True
                        break
            
            if not merged:
                levels.append(SupportResistance(
                    price=round(price, 2),
                    type="resistance",
                    touch_count=1,
                    strength=1.5
                ))
        
        # 收集所有摆动低点作为支撑
        lows = sorted([s.price for s in self.swing_points if s.type == StructureType.SWING_LOW])
        
        for price in lows:
            merged = False
            for level in levels:
                if level.type == "support":
                    diff_pct = abs(price - level.price) / level.price
                    if diff_pct < tolerance:
                        level.touch_count += 1
                        level.strength = 1.0 + level.touch_count * 0.5
                        merged = True
                        break
            
            if not merged:
                levels.append(SupportResistance(
                    price=round(price, 2),
                    type="support",
                    touch_count=1,
                    strength=1.5
                ))
        
        # 按强度排序
        levels.sort(key=lambda x: x.strength, reverse=True)
        self.support_resistances = levels
        return levels
    
    def get_structure_summary(self) -> Dict[str, Any]:
        """获取市场结构摘要"""
        return {
            "current_trend": self.current_trend,
            "swing_points_count": len(self.swing_points),
            "structure_events_count": len(self.structure_events),
            "recent_swings": [
                {
                    "price": s.price,
                    "type": s.type.value,
                    "timestamp": s.timestamp.isoformat()
                }
                for s in self.swing_points[-6:]  # 最近6个摆动点
            ],
            "recent_events": [
                {
                    "type": e.type.value,
                    "broken_level": e.broken_level,
                    "timestamp": e.timestamp.isoformat()
                }
                for e in self.structure_events[-5:]  # 最近5个结构事件
            ],
            "key_levels": [
                {
                    "price": lvl.price,
                    "type": lvl.type,
                    "strength": lvl.strength,
                    "touch_count": lvl.touch_count
                }
                for lvl in self.support_resistances[:5]  # 最强的5个支撑阻力位
            ]
        }


# 全局单例
_detector: Optional[MarketStructureDetector] = None


def get_structure_detector() -> MarketStructureDetector:
    """获取市场结构识别器单例"""
    global _detector
    if _detector is None:
        _detector = MarketStructureDetector()
    return _detector
