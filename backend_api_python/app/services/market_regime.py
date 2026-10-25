"""
市场状态识别模块（L1 Regime）

第一性原理：
- 不同的市场状态，适用完全不同的策略
- 趋势市 → 趋势跟踪策略赚钱
- 震荡市 → 均值回归策略赚钱
- 危机市 → 现金为王，不要交易

全球顶级机构实践：
- Renaissance：HMM隐马尔可夫模型自动划分regime
- Two Sigma：聚类算法发现人工想不到的市场状态
- Citadel：多模型集成 + 人工复核

核心原则：
1. 离线训练，在线推理 —— 模型参数在历史数据上训练好，实盘只做分类
2. 概率输出，不是非黑即白 —— 输出每个regime的概率分布
3. 平滑过渡，避免频繁切换 —— 有冷却期和持续性确认
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from app.utils.logger import get_logger

logger = get_logger(__name__)


class MarketRegime(Enum):
    """市场状态枚举"""
    STRONG_TREND_UP = "strong_trend_up"      # 强上升趋势
    WEAK_TREND_UP = "weak_trend_up"          # 弱上升趋势
    RANGE = "range"                           # 震荡市
    WEAK_TREND_DOWN = "weak_trend_down"      # 弱下降趋势
    STRONG_TREND_DOWN = "strong_trend_down"  # 强下降趋势
    HIGH_VOLATILITY_CRISIS = "crisis"        # 高波动危机


@dataclass
class RegimeFeatures:
    """市场状态特征"""
    # 趋势特征
    adx: float = 0.0               # ADX趋势强度
    trend_strength: float = 0.0   # 综合趋势强度 (-1 ~ +1)
    ma_alignment: float = 0.0     # 均线排列度 (-1 ~ +1)

    # 波动率特征
    atr_pct: float = 0.0          # ATR占价格百分比
    volatility_ratio: float = 0.0  # 波动率比（短期/长期）
    bollinger_width: float = 0.0   # 布林带宽度

    # 结构特征
    higher_highs: int = 0          # 连续高点数
    higher_lows: int = 0           # 连续低点数
    breakout_strength: float = 0.0 # 突破强度

    # 动量特征
    rsi: float = 50.0              # RSI
    momentum: float = 0.0          # 动量
    macd_histogram: float = 0.0   # MACD柱状图

    # 量价特征
    volume_ratio: float = 1.0      # 成交量比
    price_volume_trend: float = 0.0 # 量价趋势


@dataclass
class RegimePrediction:
    """市场状态预测结果"""
    timestamp: datetime
    current_regime: MarketRegime
    regime_probabilities: Dict[MarketRegime, float]  # 各状态概率
    confidence: float = 0.0         # 置信度 (0~1)
    features: RegimeFeatures = field(default_factory=RegimeFeatures)

    # 状态变化
    regime_changed: bool = False
    previous_regime: Optional[MarketRegime] = None
    time_in_regime_bars: int = 0    # 当前状态持续K线数


class MarketRegimeDetector:
    """
    市场状态检测器

    基于多因子规则 + 概率评分的混合模型
    （先用规则法，后续可以替换成HMM/ML模型）
    """

    # 各状态的特征阈值
    REGIME_THRESHOLDS = {
        MarketRegime.STRONG_TREND_UP: {
            "min_adx": 35,
            "min_trend_strength": 0.5,
            "min_ma_alignment": 0.3,
        },
        MarketRegime.WEAK_TREND_UP: {
            "min_adx": 20,
            "min_trend_strength": 0.2,
        },
        MarketRegime.RANGE: {
            "max_adx": 25,
            "max_trend_strength": 0.2,
        },
        MarketRegime.WEAK_TREND_DOWN: {
            "min_adx": 20,
            "max_trend_strength": -0.2,
        },
        MarketRegime.STRONG_TREND_DOWN: {
            "min_adx": 35,
            "max_trend_strength": -0.5,
            "max_ma_alignment": -0.3,
        },
        MarketRegime.HIGH_VOLATILITY_CRISIS: {
            "min_atr_pct": 5.0,
            "min_volatility_ratio": 1.5,
        },
    }

    def __init__(self):
        self.current_regime: Optional[MarketRegime] = None
        self.previous_regime: Optional[MarketRegime] = None
        self.regime_history: List[RegimePrediction] = []
        self.time_in_regime_bars: int = 0

        # 防抖动参数
        self.min_bars_per_regime: int = 5  # 状态至少持续多少根K线才允许切换
        self.regime_confidence_threshold: float = 0.6  # 置信度阈值

    def detect(self, features: RegimeFeatures) -> RegimePrediction:
        """检测当前市场状态"""
        timestamp = datetime.now(timezone.utc)

        # 计算各状态概率
        probabilities = self._calculate_regime_probabilities(features)

        # 找出最可能的状态
        predicted_regime = max(probabilities.items(), key=lambda x: x[1])[0]
        confidence = probabilities[predicted_regime]

        # 防抖动检查
        regime_changed = False
        if self.current_regime is not None and predicted_regime != self.current_regime:
            # 置信度不够，或者持续时间不够，不切换
            if (confidence < self.regime_confidence_threshold or
                self.time_in_regime_bars < self.min_bars_per_regime):
                predicted_regime = self.current_regime
                confidence = probabilities.get(predicted_regime, 0)
            else:
                regime_changed = True
                self.previous_regime = self.current_regime
                self.current_regime = predicted_regime
                self.time_in_regime_bars = 0
                logger.info(f"市场状态切换: {self.previous_regime.value} → {predicted_regime.value} (置信度: {confidence:.2f})")
        else:
            if self.current_regime is None:
                self.current_regime = predicted_regime
                self.time_in_regime_bars = 0
            else:
                self.time_in_regime_bars += 1

        prediction = RegimePrediction(
            timestamp=timestamp,
            current_regime=predicted_regime,
            regime_probabilities=probabilities,
            confidence=confidence,
            features=features,
            regime_changed=regime_changed,
            previous_regime=self.previous_regime,
            time_in_regime_bars=self.time_in_regime_bars,
        )

        self.regime_history.append(prediction)
        # 只保留最近100条
        if len(self.regime_history) > 100:
            self.regime_history = self.regime_history[-100:]

        return prediction

    def _calculate_regime_probabilities(self, features: RegimeFeatures) -> Dict[MarketRegime, float]:
        """计算各市场状态的概率"""
        probs = {}

        # 危机状态（优先判断）
        crisis_score = 0.0
        if features.atr_pct > 5.0:
            crisis_score += 0.4
        if features.volatility_ratio > 1.5:
            crisis_score += 0.3
        if features.rsi < 25 or features.rsi > 75:
            crisis_score += 0.2
        if features.bollinger_width > 3.0:
            crisis_score += 0.1
        probs[MarketRegime.HIGH_VOLATILITY_CRISIS] = min(1.0, crisis_score)

        # 趋势强度评分
        trend_score = features.trend_strength  # -1 ~ +1

        # ADX修正
        if features.adx < 20:
            trend_score *= 0.5  # ADX低，趋势不可靠

        # 强上升趋势
        strong_up = 0.0
        if trend_score > 0.5 and features.adx > 35:
            strong_up = min(1.0, (trend_score - 0.5) * 2 + (features.adx - 35) / 30)
        probs[MarketRegime.STRONG_TREND_UP] = strong_up

        # 弱上升趋势
        weak_up = 0.0
        if 0.2 < trend_score <= 0.5 and features.adx > 20:
            weak_up = min(1.0, (trend_score - 0.2) * 3)
        probs[MarketRegime.WEAK_TREND_UP] = weak_up

        # 震荡市
        range_score = 0.0
        if abs(trend_score) < 0.2 and features.adx < 25:
            range_score = min(1.0, 1.0 - abs(trend_score) * 5 - features.adx / 50)
        probs[MarketRegime.RANGE] = range_score

        # 弱下降趋势
        weak_down = 0.0
        if -0.5 <= trend_score < -0.2 and features.adx > 20:
            weak_down = min(1.0, (-trend_score - 0.2) * 3)
        probs[MarketRegime.WEAK_TREND_DOWN] = weak_down

        # 强下降趋势
        strong_down = 0.0
        if trend_score < -0.5 and features.adx > 35:
            strong_down = min(1.0, (-trend_score - 0.5) * 2 + (features.adx - 35) / 30)
        probs[MarketRegime.STRONG_TREND_DOWN] = strong_down

        # 归一化（除了危机状态，因为危机是额外叠加的）
        total = sum(probs.values())
        if total > 0:
            for k in probs:
                if k != MarketRegime.HIGH_VOLATILITY_CRISIS:
                    probs[k] = probs[k] / total * 0.8  # 留20%给危机

        return probs

    def get_recommended_strategies(self, regime: MarketRegime) -> List[str]:
        """根据市场状态推荐适用策略"""
        recommendations = {
            MarketRegime.STRONG_TREND_UP: [
                "trend_following_long",
                "momentum_long",
                "breakout_long",
            ],
            MarketRegime.WEAK_TREND_UP: [
                "pullback_long",
                "breakout_long",
                "momentum_long",
            ],
            MarketRegime.RANGE: [
                "mean_reversion",
                "range_trading",
                "oscillator_reversal",
            ],
            MarketRegime.WEAK_TREND_DOWN: [
                "pullback_short",
                "momentum_short",
            ],
            MarketRegime.STRONG_TREND_DOWN: [
                "trend_following_short",
                "momentum_short",
                "breakout_short",
            ],
            MarketRegime.HIGH_VOLATILITY_CRISIS: [
                "cash_only",  # 现金为王，不要交易
                "volatility_arbitrage",
                "hedge_strategy",
            ],
        }
        return recommendations.get(regime, [])

    def get_current_regime_summary(self) -> Dict[str, Any]:
        """获取当前市场状态摘要"""
        if self.current_regime is None:
            return {"status": "unknown"}

        return {
            "current_regime": self.current_regime.value,
            "previous_regime": self.previous_regime.value if self.previous_regime else None,
            "time_in_regime_bars": self.time_in_regime_bars,
            "recommended_strategies": self.get_recommended_strategies(self.current_regime),
        }


# 全局单例
_regime_detector: Optional[MarketRegimeDetector] = None


def get_regime_detector() -> MarketRegimeDetector:
    """获取市场状态检测器单例"""
    global _regime_detector
    if _regime_detector is None:
        _regime_detector = MarketRegimeDetector()
    return _regime_detector
