"""
因子库基础框架（Factor Library）

第一性原理：
- 因子 = 预测未来收益的变量
- 单个因子可能很弱，但叠加很多弱因子就能形成显著Alpha
- 因子之间不能太相关，否则就是伪分散

全球顶级机构实践：
- Renaissance：收集成千上万个微弱的预测信号，叠加起来形成统计显著的Alpha
- Two Sigma：因子工厂，自动化挖掘新因子
- AQR：因子投资的先驱，价值/动量/质量/低波

核心原则：
1. 因子逻辑必须可解释 —— 不能是黑箱
2. 因子必须有经济意义 —— 为什么这个因子能预测收益？
3. 因子必须做样本外检验 —— 历史有效不代表未来有效
"""
from __future__ import annotations

import abc
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from app.utils.logger import get_logger

logger = get_logger(__name__)


class FactorCategory(Enum):
    """因子类别"""
    MOMENTUM = "momentum"           # 动量类
    VALUE = "value"                  # 价值类
    QUALITY = "quality"              # 质量类
    VOLATILITY = "volatility"        # 波动率类
    VOLUME = "volume"                # 成交量类
    TECHNICAL = "technical"          # 技术指标类
    SENTIMENT = "sentiment"          # 情绪类
    ALTERNATIVE = "alternative"      # 另类数据类


class FactorType(Enum):
    """因子方向"""
    BULLISH = "bullish"              # 因子值越高，未来收益越高
    BEARISH = "bearish"              # 因子值越高，未来收益越低
    NEUTRAL = "neutral"              # 中性因子


@dataclass
class FactorResult:
    """因子计算结果"""
    name: str
    category: FactorCategory
    values: pd.Series                 # 因子值序列
    ic: float = 0.0                  # 信息系数 (IC)
    icir: float = 0.0                # 信息系数比率 (ICIR)
    t_stat: float = 0.0              # t统计量
    win_rate: float = 0.0            # 胜率
    description: str = ""


class BaseFactor(abc.ABC):
    """因子基类"""
    
    name: str = "base_factor"
    category: FactorCategory = FactorCategory.TECHNICAL
    description: str = ""
    
    def __init__(self, **kwargs):
        self.params = kwargs
    
    @abc.abstractmethod
    def compute(self, data: pd.DataFrame) -> pd.Series:
        """
        计算因子值
        
        Args:
            data: K线数据，包含open/high/low/close/volume
            
        Returns:
            pd.Series: 因子值
        """
        pass
    
    def validate(self, data: pd.DataFrame) -> bool:
        """验证输入数据是否足够计算因子"""
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        return all(col in data.columns for col in required_columns)


class MomentumFactor(BaseFactor):
    """动量因子"""
    
    name = "momentum"
    category = FactorCategory.MOMENTUM
    description = "N日收益率动量"
    
    def __init__(self, period: int = 20):
        super().__init__(period=period)
        self.period = period
    
    def compute(self, data: pd.DataFrame) -> pd.Series:
        """计算N日动量"""
        close = data['close']
        momentum = close.pct_change(self.period)
        return momentum


class ReversalFactor(BaseFactor):
    """反转因子（短期反转）"""
    
    name = "reversal"
    category = FactorCategory.MOMENTUM
    description = "N日反转（涨多了会跌，跌多了会涨）"
    
    def __init__(self, period: int = 5):
        super().__init__(period=period)
        self.period = period
    
    def compute(self, data: pd.DataFrame) -> pd.Series:
        """计算短期反转因子"""
        close = data['close']
        reversal = -close.pct_change(self.period)  # 负号：跌多了看涨
        return reversal


class VolatilityFactor(BaseFactor):
    """波动率因子"""
    
    name = "volatility"
    category = FactorCategory.VOLATILITY
    description = "N日收益率波动率"
    
    def __init__(self, period: int = 20):
        super().__init__(period=period)
        self.period = period
    
    def compute(self, data: pd.DataFrame) -> pd.Series:
        """计算N日波动率"""
        returns = data['close'].pct_change()
        volatility = returns.rolling(self.period).std()
        return volatility


class VolumeRatioFactor(BaseFactor):
    """成交量比率因子"""
    
    name = "volume_ratio"
    category = FactorCategory.VOLUME
    description = "当前成交量 / N日均量"
    
    def __init__(self, period: int = 20):
        super().__init__(period=period)
        self.period = period
    
    def compute(self, data: pd.DataFrame) -> pd.Series:
        """计算成交量比率"""
        volume = data['volume']
        avg_volume = volume.rolling(self.period).mean()
        volume_ratio = volume / avg_volume
        return volume_ratio


class RSIFactor(BaseFactor):
    """RSI相对强弱指标"""
    
    name = "rsi"
    category = FactorCategory.TECHNICAL
    description = "RSI相对强弱指标（超买超卖）"
    
    def __init__(self, period: int = 14):
        super().__init__(period=period)
        self.period = period
    
    def compute(self, data: pd.DataFrame) -> pd.Series:
        """计算RSI"""
        close = data['close']
        delta = close.diff()
        
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        avg_gain = gain.rolling(self.period).mean()
        avg_loss = loss.rolling(self.period).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi


class MACDFactor(BaseFactor):
    """MACD因子"""
    
    name = "macd"
    category = FactorCategory.TECHNICAL
    description = "MACD柱状图（趋势动量）"
    
    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        super().__init__(fast=fast, slow=slow, signal=signal)
        self.fast = fast
        self.slow = slow
        self.signal = signal
    
    def compute(self, data: pd.DataFrame) -> pd.Series:
        """计算MACD"""
        close = data['close']
        
        ema_fast = close.ewm(span=self.fast).mean()
        ema_slow = close.ewm(span=self.slow).mean()
        
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=self.signal).mean()
        
        macd_hist = macd_line - signal_line
        
        return macd_hist


class BollingerBreadthFactor(BaseFactor):
    """布林带宽度因子"""
    
    name = "bollinger_breadth"
    category = FactorCategory.VOLATILITY
    description = "布林带宽度（波动率收缩/扩张）"
    
    def __init__(self, period: int = 20, std_dev: float = 2.0):
        super().__init__(period=period, std_dev=std_dev)
        self.period = period
        self.std_dev = std_dev
    
    def compute(self, data: pd.DataFrame) -> pd.Series:
        """计算布林带宽度"""
        close = data['close']
        
        ma = close.rolling(self.period).mean()
        std = close.rolling(self.period).std()
        
        upper = ma + std * self.std_dev
        lower = ma - std * self.std_dev
        
        breadth = (upper - lower) / ma  # 标准化宽度
        
        return breadth


class FactorLibrary:
    """
    因子库管理
    
    功能：
    1. 注册和管理因子
    2. 批量计算因子值
    3. 因子有效性检验
    4. 因子相关性分析
    """
    
    def __init__(self):
        self.factors: Dict[str, BaseFactor] = {}
        self._register_default_factors()
    
    def _register_default_factors(self):
        """注册默认因子"""
        default_factors = [
            MomentumFactor(period=20),
            MomentumFactor(period=60),
            ReversalFactor(period=5),
            ReversalFactor(period=10),
            VolatilityFactor(period=20),
            VolatilityFactor(period=60),
            VolumeRatioFactor(period=20),
            RSIFactor(period=14),
            MACDFactor(),
            BollingerBreadthFactor(),
        ]
        
        for factor in default_factors:
            self.register_factor(factor)
    
    def register_factor(self, factor: BaseFactor):
        """注册因子"""
        self.factors[factor.name] = factor
        logger.info(f"Registered factor: {factor.name}")
    
    def compute_all(self, data: pd.DataFrame) -> Dict[str, pd.Series]:
        """
        批量计算所有因子
        
        Args:
            data: K线数据
            
        Returns:
            Dict[str, pd.Series]: 因子名 → 因子值
        """
        results = {}
        
        for name, factor in self.factors.items():
            try:
                if factor.validate(data):
                    values = factor.compute(data)
                    results[name] = values
            except Exception as e:
                logger.warning(f"Failed to compute factor {name}: {e}")
        
        return results
    
    def evaluate_factor(self, factor_values: pd.Series, 
                       forward_returns: pd.Series,
                       method: str = 'spearman') -> Dict[str, float]:
        """
        评估因子有效性
        
        Args:
            factor_values: 因子值
            forward_returns: 未来N期收益
            method: 相关系数方法
            
        Returns:
            Dict: 因子评估指标
        """
        # 对齐数据
        aligned = pd.DataFrame({
            'factor': factor_values,
            'forward_return': forward_returns
        }).dropna()
        
        if len(aligned) < 30:
            return {'ic': 0.0, 'icir': 0.0, 't_stat': 0.0}
        
        # 计算IC（信息系数）
        ic = aligned['factor'].corr(aligned['forward_return'], method=method)
        
        # 计算IC时间序列（滚动IC）
        rolling_ic = aligned['factor'].rolling(60).corr(aligned['forward_return'])
        
        ic_mean = rolling_ic.mean()
        ic_std = rolling_ic.std()
        
        icir = ic_mean / ic_std if ic_std > 0 else 0
        
        # t统计量
        n = len(aligned)
        t_stat = ic * math.sqrt(n - 2) / math.sqrt(1 - ic**2) if abs(ic) < 1 else 0
        
        return {
            'ic': round(ic, 4),
            'icir': round(icir, 4),
            't_stat': round(t_stat, 4),
            'n_obs': n
        }
    
    def get_factor_summary(self) -> List[Dict[str, Any]]:
        """获取因子库摘要"""
        return [
            {
                'name': factor.name,
                'category': factor.category.value,
                'description': factor.description,
                'params': factor.params
            }
            for factor in self.factors.values()
        ]
