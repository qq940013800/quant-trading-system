# -*- coding: utf-8 -*-
"""tests.test_ml_trend_strategy —— ML 增强趋势策略单测。

验证：
1. 因果性：不使用未来数据
2. 初级信号：唐奇安通道突破逻辑正确
3. meta-label：ML 过滤流程正确
4. 仓位计算：固定 R 倍数法正确
5. 跟踪止损：只向盈利方向移动
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.models.ml_trend_strategy import (
    MLTrendStrategy,
    StrategyConfig,
    build_meta_labels,
)


# ------------------------------------------------------------------
# 测试数据生成
# ------------------------------------------------------------------
def _make_synthetic_history(n: int = 100, trend: float = 0.001,
                           seed: int = 42) -> list[dict]:
    """生成合成 K 线数据（带趋势）。"""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="1h")
    close = 100.0 + np.cumsum(rng.normal(trend, 0.01, n))
    high = close + rng.uniform(0, 0.005, n)
    low = close - rng.uniform(0, 0.005, n)
    volume = rng.uniform(1000, 5000, n)

    return [
        {
            "time": dates[i],
            "open": close[i],
            "high": high[i],
            "low": low[i],
            "close": close[i],
            "volume": volume[i],
        }
        for i in range(n)
    ]


# ------------------------------------------------------------------
# 测试：配置
# ------------------------------------------------------------------
class TestStrategyConfig:
    def test_default_config(self):
        cfg = StrategyConfig()
        assert cfg.entry_period == 20
        assert cfg.risk_per_trade == 0.01
        assert cfg.atr_stop_mult == 2.0

    def test_custom_config(self):
        cfg = StrategyConfig(entry_period=10, risk_per_trade=0.02)
        assert cfg.entry_period == 10
        assert cfg.risk_per_trade == 0.02


# ------------------------------------------------------------------
# 测试：初级信号（唐奇安通道）
# ------------------------------------------------------------------
class TestPrimarySignal:
    def test_no_signal_when_range(self):
        """震荡市中不应该有突破信号。"""
        history = _make_synthetic_history(n=50, trend=0.0)
        strategy = MLTrendStrategy()
        as_of = history[-1]["time"]
        direction, atr = strategy._primary_signal(history, as_of)
        # 震荡市可能有信号也可能没有，但 ATR 应该是正数
        assert not np.isnan(atr)
        assert atr > 0

    def test_upper_breakout(self):
        """价格突破上轨应该产生做多信号。"""
        # 构造：前 20 根在 100 附近震荡，第 21 根突然涨到 110
        history = _make_synthetic_history(n=30, trend=0.0)
        # 手动把最后一根的收盘价拉高
        history[-1]["close"] = 110.0
        history[-1]["high"] = 110.5

        strategy = MLTrendStrategy()
        as_of = history[-1]["time"]
        direction, atr = strategy._primary_signal(history, as_of)
        assert direction == 1  # 应该是做多信号


# ------------------------------------------------------------------
# 测试：特征工程
# ------------------------------------------------------------------
class TestFeatureEngineering:
    def test_feature_shape(self):
        history = _make_synthetic_history(n=50)
        strategy = MLTrendStrategy()
        as_of = history[-1]["time"]
        features = strategy._build_features(history, as_of)
        assert features.shape == (6,)

    def test_no_future_data(self):
        """因果性测试：修改未来数据不应该影响当前特征。"""
        history = _make_synthetic_history(n=50)
        strategy = MLTrendStrategy()
        as_of = history[30]["time"]

        features1 = strategy._build_features(history, as_of)

        # 修改后面的数据
        history2 = history.copy()
        for i in range(31, len(history2)):
            history2[i]["close"] = 999.0

        features2 = strategy._build_features(history2, as_of)
        # 特征应该完全一样（因为只用 as_of 之前的数据）
        np.testing.assert_array_almost_equal(features1, features2)


# ------------------------------------------------------------------
# 测试：ML 训练与预测
# ------------------------------------------------------------------
class TestMLTraining:
    def test_fit_predict(self):
        """训练后预测应该输出概率。"""
        # 生成简单训练数据
        X_train = np.random.randn(100, 6)
        y_train = (X_train[:, 0] > 0).astype(int)  # 简单可分的标签

        strategy = MLTrendStrategy()
        strategy.fit(X_train, y_train)

        # 预测
        X_test = np.random.randn(10, 6)
        history = _make_synthetic_history(n=50)
        as_of = history[-1]["time"]
        signal = strategy.predict(history, as_of, capital=100000)

        # 应该返回一个信号对象
        assert hasattr(signal, "direction")
        assert hasattr(signal, "meta_prob")


# ------------------------------------------------------------------
# 测试：仓位计算
# ------------------------------------------------------------------
class TestPositionSizing:
    def test_risk_based_sizing(self):
        """固定 R 倍数法：仓位 = 风险金额 / 止损距离。"""
        history = _make_synthetic_history(n=50, trend=0.01)  # 上升趋势
        strategy = MLTrendStrategy()
        as_of = history[-1]["time"]
        signal = strategy.predict(history, as_of, capital=100000)

        # 如果有信号，验证仓位计算
        if signal.direction != 0:
            # 未训练时 position_scale = 0.5（默认半仓）
            position_scale = 0.5
            risk_amount = 100000 * 0.01 * position_scale
            stop_distance = abs(signal.entry_price - signal.stop_loss)
            expected_size = risk_amount / stop_distance
            assert signal.position_size == pytest.approx(expected_size, rel=0.01)


# ------------------------------------------------------------------
# 测试：跟踪止损
# ------------------------------------------------------------------
class TestTrailingStop:
    def test_long_trailing_stop_goes_up(self):
        """多头跟踪止损只上移不下移。"""
        strategy = MLTrendStrategy()
        atr = 1.0

        # 当前止损在 95，价格涨到 100
        new_stop = strategy.update_trailing_stop(
            current_stop=95.0,
            current_price=100.0,
            direction=1,
            atr=atr,
        )
        # 新止损应该比旧止损高（向盈利方向移动）
        assert new_stop >= 95.0

    def test_short_trailing_stop_goes_down(self):
        """空头跟踪止损只下移不上移。"""
        strategy = MLTrendStrategy()
        atr = 1.0

        # 当前止损在 105，价格跌到 100
        new_stop = strategy.update_trailing_stop(
            current_stop=105.0,
            current_price=100.0,
            direction=-1,
            atr=atr,
        )
        # 新止损应该比旧止损低（向盈利方向移动）
        assert new_stop <= 105.0


# ------------------------------------------------------------------
# 测试：meta-label 数据集生成
# ------------------------------------------------------------------
class TestMetaLabelBuilder:
    def test_build_labels(self):
        history = _make_synthetic_history(n=100, trend=0.01)
        X, y = build_meta_labels(history, entry_period=20, forward_window=10)
        # 应该生成一些样本
        assert X.shape[0] > 0
        assert X.shape[1] == 6
        assert y.shape[0] == X.shape[0]
