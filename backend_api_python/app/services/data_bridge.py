"""
数据桥接模块（Data Bridge）

第一性原理：
- L1/L2模块现在都是"空转"——没有数据输入
- 需要一个桥接层，把原始K线数据转换成模块需要的特征
- 先跑通流程，再优化数据质量

工作流程：
1. 获取K线数据（OHLCV）
2. 计算技术指标（ATR、ADX、均线、波动率等）
3. 把特征喂给L1市场状态识别
4. 把K线喂给L2市场结构识别
5. 输出综合的市场分析结果

全球顶级机构实践：
- Renaissance：特征工程是核心竞争力，上千个特征
- Two Sigma：特征仓库（Feature Store）统一管理
- Citadel：实时特征计算，毫秒级延迟
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.utils.logger import get_logger
from app.services.market_regime import get_regime_detector, MarketRegime
from app.services.market_structure import get_structure_detector

logger = get_logger(__name__)


@dataclass
class KlineData:
    """K线数据"""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class MarketAnalysis:
    """综合市场分析结果"""
    symbol: str
    current_price: float
    timestamp: datetime
    
    # L1 市场状态
    regime: str
    regime_confidence: float
    regime_features: Dict[str, float]
    
    # L2 市场结构
    structure_bias: str          # bullish / bearish / neutral
    support_levels: List[float]
    resistance_levels: List[float]
    recent_swing_high: Optional[float]
    recent_swing_low: Optional[float]
    
    # 技术指标
    atr: float
    volatility: float
    trend_strength: float


class DataBridge:
    """
    数据桥接服务
    
    负责把原始K线数据转换成L1/L2模块需要的特征格式
    """
    
    def __init__(self):
        self.regime_detector = get_regime_detector()
        self.structure_detector = get_structure_detector()
        self.cache: Dict[str, MarketAnalysis] = {}
    
    def analyze_market(self, symbol: str, klines: List[KlineData]) -> MarketAnalysis:
        """
        综合市场分析：输入K线，输出L1+L2综合判断
        
        参数：
            symbol: 交易对，如 BTCUSDT
            klines: K线列表（至少50根）
        
        返回：
            MarketAnalysis 综合分析结果
        """
        if len(klines) < 20:
            logger.warning(f"{symbol} K线数据不足: {len(klines)}根")
            return self._empty_analysis(symbol)
        
        # 1. 计算技术指标
        closes = [k.close for k in klines]
        highs = [k.high for k in klines]
        lows = [k.low for k in klines]
        
        atr = self._calculate_atr(highs, lows, closes, period=14)
        volatility = self._calculate_volatility(closes, period=20)
        trend_strength = self._calculate_trend_strength(closes, period=20)
        
        # 2. L1 市场状态识别
        from app.services.market_regime import RegimeFeatures
        features = RegimeFeatures(
            adx=trend_strength * 100,  # 简化：用趋势强度近似ADX
            trend_strength=trend_strength,
            atr_pct=atr / closes[-1] * 100 if closes[-1] > 0 else 0,
            volatility_ratio=volatility * 100,
        )
        regime_result = self.regime_detector.detect(features)
        
        # 3. L2 市场结构识别（简化版，先跑通流程）
        # TODO: 等结构检测器接口稳定后再接入真实调用
        structure_bias = "bullish" if trend_strength > 0.2 else ("bearish" if trend_strength < -0.2 else "neutral")
        support_levels = [round(closes[-1] * 0.98, 2), round(closes[-1] * 0.95, 2)]
        resistance_levels = [round(closes[-1] * 1.02, 2), round(closes[-1] * 1.05, 2)]
        recent_swing_high = round(max(highs[-20:]), 2)
        recent_swing_low = round(min(lows[-20:]), 2)
        
        # 4. 组装结果
        result = MarketAnalysis(
            symbol=symbol,
            current_price=closes[-1],
            timestamp=klines[-1].timestamp,
            
            regime=regime_result.current_regime.value,
            regime_confidence=regime_result.confidence,
            regime_features={
                "adx": trend_strength * 100,
                "trend_strength": trend_strength,
                "volatility": volatility,
                "atr_ratio": atr / closes[-1] if closes[-1] > 0 else 0,
            },
            
            structure_bias=structure_bias,
            support_levels=support_levels,
            resistance_levels=resistance_levels,
            recent_swing_high=recent_swing_high,
            recent_swing_low=recent_swing_low,
            
            atr=atr,
            volatility=volatility,
            trend_strength=trend_strength,
        )
        
        self.cache[symbol] = result
        logger.info(f"{symbol} 市场分析完成: regime={result.regime}, bias={result.structure_bias}")
        
        return result
    
    def analyze_with_demo_data(self, symbol: str = "BTCUSDT") -> MarketAnalysis:
        """
        用演示数据跑通流程（没有真实数据时用这个）
        
        生成模拟K线数据，验证整个流程是否能跑通
        """
        import random
        
        # 生成模拟K线（随机游走 + 轻微上升趋势）
        klines = []
        base_price = 65000.0
        now = datetime.now(timezone.utc)
        
        for i in range(100):
            price = base_price * (1 + 0.001 * i + random.gauss(0, 0.01))
            high = price * (1 + abs(random.gauss(0, 0.005)))
            low = price * (1 - abs(random.gauss(0, 0.005)))
            open_price = price * (1 + random.gauss(0, 0.003))
            volume = random.uniform(100, 1000)
            
            klines.append(KlineData(
                timestamp=datetime.fromtimestamp(now.timestamp() - (100 - i) * 3600, tz=timezone.utc),
                open=open_price,
                high=high,
                low=low,
                close=price,
                volume=volume,
            ))
        
        return self.analyze_market(symbol, klines)
    
    def _calculate_atr(self, highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
        """计算ATR（平均真实波幅）"""
        if len(closes) < period + 1:
            return 0.0
        
        trs = []
        for i in range(1, len(closes)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            trs.append(tr)
        
        return sum(trs[-period:]) / period
    
    def _calculate_volatility(self, closes: List[float], period: int = 20) -> float:
        """计算波动率（收益率标准差）"""
        if len(closes) < period + 1:
            return 0.0
        
        returns = []
        for i in range(1, len(closes)):
            if closes[i-1] > 0:
                returns.append((closes[i] - closes[i-1]) / closes[i-1])
        
        if len(returns) < period:
            return 0.0
        
        recent_returns = returns[-period:]
        mean = sum(recent_returns) / len(recent_returns)
        variance = sum((r - mean) ** 2 for r in recent_returns) / len(recent_returns)
        
        return math.sqrt(variance) * math.sqrt(252)  # 年化
    
    def _calculate_trend_strength(self, closes: List[float], period: int = 20) -> float:
        """计算趋势强度（简化版：均线斜率归一化）"""
        if len(closes) < period:
            return 0.0
        
        # 短期均线 vs 长期均线
        short_ma = sum(closes[-10:]) / 10
        long_ma = sum(closes[-period:]) / period
        
        if long_ma == 0:
            return 0.0
        
        # 归一化到 -1 ~ +1
        ratio = (short_ma - long_ma) / long_ma
        return max(-1.0, min(1.0, ratio * 20))  # 放大20倍后截断
    
    def _empty_analysis(self, symbol: str) -> MarketAnalysis:
        """空分析结果（数据不足时）"""
        return MarketAnalysis(
            symbol=symbol,
            current_price=0.0,
            timestamp=datetime.now(timezone.utc),
            regime="unknown",
            regime_confidence=0.0,
            regime_features={},
            structure_bias="neutral",
            support_levels=[],
            resistance_levels=[],
            recent_swing_high=None,
            recent_swing_low=None,
            atr=0.0,
            volatility=0.0,
            trend_strength=0.0,
        )


# 单例
_data_bridge: Optional[DataBridge] = None

def get_data_bridge() -> DataBridge:
    global _data_bridge
    if _data_bridge is None:
        _data_bridge = DataBridge()
    return _data_bridge
