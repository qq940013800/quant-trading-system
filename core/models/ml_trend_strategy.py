# -*- coding: utf-8 -*-
"""core.models.ml_trend_strategy —— AI/ML 增强趋势策略（meta-labeling 架构）。

基于第一性原理设计：
1. 第一级（初级信号）：趋势跟踪规则（海龟突破 / 均线交叉）—— 提供方向
2. 第二级（meta-label）：ML 模型判断"这个初级信号值不值得下注" —— 过滤假信号
3. 仓位：波动率目标 + 固定 R 倍数 —— 截断亏损，让利润奔跑

设计原则：
- 因果单向：所有特征只用 as_of 之前的数据
- 阈值来自分布：正则强度、决策阈值由 CLEAN 集校准，非绩效网格
- 可审计：每笔交易的决策路径可还原
- 纯 numpy 实现：不依赖 sklearn，保证最小依赖

参考：López de Prado《Advances in Financial Machine Learning》meta-labeling 架构。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from .baseline import LogisticBaseline


@dataclass
class StrategyConfig:
    """策略配置（全部参数冻结在实验前，禁止按绩效调参）。"""
    # === 初级信号：趋势跟踪 ===
    entry_period: int = 20          # 入场突破周期（海龟唐奇安通道）
    exit_period: int = 10           # 出场突破周期
    atr_period: int = 14             # ATR 周期

    # === meta-label：ML 过滤 ===
    meta_C: float = 1.0              # L2 正则强度（从 CLEAN 集校准）
    meta_threshold: float = 0.55     # 决策阈值（从验证集校准，非 0.5）
    min_prob: float = 0.45          # 最低概率（低于此直接不交易）

    # === 仓位与风控 ===
    risk_per_trade: float = 0.01    # 单笔风险占总资金 1%
    atr_stop_mult: float = 2.0      # 止损 = 2×ATR
    atr_trail_mult: float = 3.0     # 跟踪止盈 = 3×ATR

    # === 市场状态门控 ===
    use_regime_filter: bool = True   # 是否启用市场状态过滤
    min_trend_weight: float = 0.3   # 趋势权重低于此不做趋势策略


@dataclass
class TradeSignal:
    """单笔交易信号（可审计记录）。"""
    timestamp: pd.Timestamp
    direction: int                   # 1=做多, -1=做空, 0=无信号
    entry_price: float
    stop_loss: float
    take_profit: float | None = None
    position_size: float = 0.0
    meta_prob: float = 0.0          # ML meta-label 概率
    regime_weights: dict = field(default_factory=dict)
    reason: str = ""                 # 决策原因（可审计）


class MLTrendStrategy:
    """AI/ML 增强趋势策略。

    两层架构：
    1. 初级信号层：海龟突破规则 —— 产生方向信号
    2. Meta-label 层：逻辑回归 —— 判断信号质量，决定是否下注

    用法：
        strategy = MLTrendStrategy(config)
        strategy.fit(X_train, y_primary_train, y_meta_train)
        signal = strategy.predict(history, as_of, capital=100000)
    """

    version = "ml-trend-meta-label-v1"

    def __init__(self, config: StrategyConfig | None = None):
        self.config = config or StrategyConfig()
        self.model = LogisticBaseline(C=self.config.meta_C)
        self._fitted = False

    # ------------------------------------------------------------------
    # 初级信号：海龟唐奇安通道突破
    # ------------------------------------------------------------------
    def _primary_signal(self, history: list, as_of: pd.Timestamp) -> tuple[int, float]:
        """初级信号：唐奇安通道突破。

        Returns:
            (direction, atr_value)
            direction: 1=做多（突破上轨）, -1=做空（突破下轨）, 0=无信号
        """
        cfg = self.config
        n = len(history)
        if n < max(cfg.entry_period, cfg.atr_period) + 2:
            return 0, np.nan

        # 取截至 as_of 的数据
        df = pd.DataFrame(history)
        df = df[df["time"] <= as_of].reset_index(drop=True)
        if len(df) < max(cfg.entry_period, cfg.atr_period) + 2:
            return 0, np.nan

        high = df["high"].to_numpy()
        low = df["low"].to_numpy()
        close = df["close"].to_numpy()

        # 唐奇安通道（用前 N 根，不含当前根——避免前视）
        upper = high[-cfg.entry_period - 1:-1].max()
        lower = low[-cfg.entry_period - 1:-1].min()
        current_close = close[-1]

        # ATR
        prev_close = np.concatenate([[close[0]], close[:-1]])
        tr = np.maximum.reduce([
            high - low,
            np.abs(high - prev_close),
            np.abs(low - prev_close),
        ])
        atr = pd.Series(tr).rolling(cfg.atr_period).mean().values[-1]

        # 突破判断
        if current_close > upper:
            return 1, atr
        elif current_close < lower:
            return -1, atr
        else:
            return 0, atr

    # ------------------------------------------------------------------
    # 特征工程：为 meta-label 准备特征
    # ------------------------------------------------------------------
    def _build_features(self, history: list, as_of: pd.Timestamp) -> np.ndarray:
        """构建 meta-label 特征向量（全部因果）。

        特征列表：
        1. ADX（趋势强度）
        2. ATR%（波动率）
        3. RSI（超买超卖）
        4. 距离均线偏离度
        5. 成交量变化率
        6. 近期动量（5日收益率）
        """
        df = pd.DataFrame(history)
        df = df[df["time"] <= as_of].reset_index(drop=True)
        if len(df) < 30:
            return np.zeros(6)

        close = df["close"].values
        high = df["high"].values
        low = df["low"].values
        volume = df["volume"].values if "volume" in df.columns else np.ones(len(df))

        features = []

        # 1. 简化 ADX（趋势强度）
        delta_high = np.diff(high)
        delta_low = np.diff(low)
        plus_dm = np.where((delta_high > delta_low) & (delta_high > 0), delta_high, 0)
        minus_dm = np.where((delta_low > delta_high) & (delta_low > 0), delta_low, 0)
        atr_simple = pd.Series(high - low).rolling(14).mean().values[-1]
        if atr_simple > 0:
            plus_di = 100 * pd.Series(plus_dm).rolling(14).mean().values[-1] / atr_simple
            minus_di = 100 * pd.Series(minus_dm).rolling(14).mean().values[-1] / atr_simple
            di_sum = plus_di + minus_di
            adx_val = 100 * abs(plus_di - minus_di) / di_sum if di_sum > 0 else 20
        else:
            adx_val = 20
        features.append(adx_val / 100.0)  # 归一化到 0~1

        # 2. ATR%（波动率）
        atr_pct = atr_simple / close[-1] if close[-1] > 0 else 0.01
        features.append(atr_pct)

        # 3. RSI(14)
        delta = np.diff(close)
        gain = np.where(delta > 0, delta, 0)
        loss = np.where(delta < 0, -delta, 0)
        avg_gain = pd.Series(gain).rolling(14).mean().values[-1]
        avg_loss = pd.Series(loss).rolling(14).mean().values[-1]
        if avg_loss > 0:
            rs = avg_gain / avg_loss
            rsi = 100 - 100 / (1 + rs)
        else:
            rsi = 100
        features.append(rsi / 100.0)

        # 4. 距离 20 日均线偏离度
        ma20 = pd.Series(close).rolling(20).mean().values[-1]
        deviation = (close[-1] - ma20) / ma20 if ma20 > 0 else 0
        features.append(deviation)

        # 5. 成交量变化率
        vol_ma = pd.Series(volume).rolling(10).mean().values[-1]
        vol_change = volume[-1] / vol_ma if vol_ma > 0 else 1.0
        features.append(vol_change)

        # 6. 5日动量
        momentum = (close[-1] - close[-5]) / close[-5] if close[-5] > 0 else 0
        features.append(momentum)

        return np.array(features, dtype=np.float64)

    # ------------------------------------------------------------------
    # 训练
    # ------------------------------------------------------------------
    def fit(self, X: np.ndarray, y: np.ndarray) -> "MLTrendStrategy":
        """训练 meta-label 模型。

        Args:
            X: 特征矩阵 (n_samples, n_features)
            y: meta-label（1=初级信号盈利, 0=初级信号亏损）
        """
        self.model.fit(X, y)
        self._fitted = True
        return self

    # ------------------------------------------------------------------
    # 预测：完整决策流程
    # ------------------------------------------------------------------
    def predict(self, history: list, as_of: pd.Timestamp,
                capital: float = 100000.0,
                regime_weights: dict | None = None) -> TradeSignal:
        """完整决策流程：初级信号 → ML 过滤 → 仓位计算。

        Args:
            history: K线历史（按时间升序）
            as_of: 当前时间戳（因果截止点）
            capital: 当前资金
            regime_weights: 市场状态权重（可选，来自 regime_weights 函数）

        Returns:
            TradeSignal 交易信号
        """
        cfg = self.config
        signal = TradeSignal(
            timestamp=as_of,
            direction=0,
            entry_price=0.0,
            stop_loss=0.0,
        )

        # 第一步：初级信号（海龟突破）
        direction, atr = self._primary_signal(history, as_of)
        if direction == 0 or np.isnan(atr):
            signal.reason = "无初级信号（未突破唐奇安通道）"
            return signal

        # 第二步：市场状态门控
        if cfg.use_regime_filter and regime_weights:
            w_trend = regime_weights.get("w_trend", 0.5)
            if w_trend < cfg.min_trend_weight:
                signal.reason = f"趋势权重不足（{w_trend:.2f} < {cfg.min_trend_weight}）"
                return signal
            signal.regime_weights = regime_weights

        # 第三步：ML meta-label 过滤
        if self._fitted:
            features = self._build_features(history, as_of)
            prob = self.model.predict_proba(features.reshape(1, -1))[0, 1]
            signal.meta_prob = float(prob)

            if prob < cfg.min_prob:
                signal.reason = f"ML 概率过低（{prob:.2f} < {cfg.min_prob}）"
                return signal
            if prob < cfg.meta_threshold:
                # 概率不够高，半仓
                position_scale = 0.5
            else:
                position_scale = 1.0
        else:
            # 未训练时用默认权重
            signal.meta_prob = 0.5
            position_scale = 0.5

        # 第四步：计算仓位与止损
        df = pd.DataFrame(history)
        df = df[df["time"] <= as_of].reset_index(drop=True)
        entry_price = df["close"].values[-1]

        stop_loss = entry_price - direction * atr * cfg.atr_stop_mult
        risk_amount = capital * cfg.risk_per_trade * position_scale
        stop_distance = abs(entry_price - stop_loss)

        if stop_distance > 0:
            position_size = risk_amount / stop_distance
        else:
            position_size = 0.0

        # 填充信号
        signal.direction = direction
        signal.entry_price = entry_price
        signal.stop_loss = stop_loss
        signal.position_size = position_size
        signal.reason = (
            f"初级信号={'做多' if direction == 1 else '做空'} | "
            f"ML概率={signal.meta_prob:.2f} | "
            f"仓位比例={position_scale:.1f} | "
            f"止损={stop_loss:.2f}"
        )

        return signal

    # ------------------------------------------------------------------
    # 持仓管理：跟踪止盈
    # ------------------------------------------------------------------
    def update_trailing_stop(self, current_stop: float, current_price: float,
                             direction: int, atr: float) -> float:
        """更新跟踪止损（只向盈利方向移动）。

        规则：止损只允许向盈利方向移动，永不向亏损方向移动。
        """
        cfg = self.config
        new_stop = current_price - direction * atr * cfg.atr_trail_mult

        if direction == 1:  # 多头：止损上移
            return max(current_stop, new_stop)
        else:  # 空头：止损下移
            return min(current_stop, new_stop)


# ------------------------------------------------------------------
# 便捷函数：生成训练用的 meta-label 数据集
# ------------------------------------------------------------------
def build_meta_labels(history: list, entry_period: int = 20,
                      atr_period: int = 14, atr_mult: float = 2.0,
                      forward_window: int = 10) -> tuple[np.ndarray, np.ndarray]:
    """从历史数据生成初级信号 + meta-label 训练集。

    Args:
        history: K线历史（按时间升序）
        entry_period: 唐奇安通道周期
        atr_period: ATR 周期
        atr_mult: 止损 ATR 倍数
        forward_window: 前向观察窗口（多少根 K 线内决定胜负）

    Returns:
        X: 特征矩阵 (n_signals, n_features)
        y: meta-label（1=盈利, 0=亏损）
    """
    df = pd.DataFrame(history)
    n = len(df)
    if n < entry_period + atr_period + forward_window + 5:
        return np.zeros((0, 6)), np.zeros(0)

    close = df["close"].values
    high = df["high"].values
    low = df["low"].values

    signals_X = []
    signals_y = []

    strategy = MLTrendStrategy()

    # 遍历每个可能的信号点
    for i in range(entry_period + atr_period, n - forward_window):
        as_of = df["time"].values[i]
        hist_slice = df.iloc[:i+1].to_dict("records")

        # 初级信号
        direction, atr = strategy._primary_signal(hist_slice, as_of)
        if direction == 0 or np.isnan(atr):
            continue

        # 构建特征
        features = strategy._build_features(hist_slice, as_of)

        # 计算 meta-label：前向窗口内是否盈利
        entry_price = close[i]
        stop_loss = entry_price - direction * atr * atr_mult

        # 模拟前向 N 根 K 线
        outcome = 0  # 默认亏损
        for j in range(i + 1, min(i + forward_window + 1, n)):
            if direction == 1:  # 多头
                if low[j] <= stop_loss:
                    outcome = 0  # 止损
                    break
                if close[j] > entry_price + atr * atr_mult * 2:  # 2R 盈利
                    outcome = 1
                    break
            else:  # 空头
                if high[j] >= stop_loss:
                    outcome = 0
                    break
                if close[j] < entry_price - atr * atr_mult * 2:
                    outcome = 1
                    break

        signals_X.append(features)
        signals_y.append(outcome)

    if not signals_X:
        return np.zeros((0, 6)), np.zeros(0)

    return np.array(signals_X, dtype=np.float64), np.array(signals_y, dtype=np.float64)
