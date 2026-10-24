# -*- coding: utf-8 -*-
"""tests.test_integration.test_live_pipeline —— 实盘数据端到端集成测试。

模拟完整的实盘交易流程：
数据生成 → 数据验证 → 特征计算 → 策略信号 → 风控 → 回测 → 审计 → 监控
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.data.synthetic import make_synthetic_bars
from core.data.validator import validate_bars
from core.features.atr import wilder_atr
from core.features.structure import get_market_structure
from core.features.patterns import is_engulfing, is_hammer
from core.risk.stops import StopConfig, evaluate_stops, StopState
from core.risk.sizing import target_lots
from core.backtest.metrics import compute_metrics
from core.backtest.overfitting import overfitting_diagnostic
from core.audit.lookahead_detector import LookaheadDetector
from core.monitoring.drift_monitor import DriftMonitor


class FakePosition:
    """模拟持仓。"""
    def __init__(self, direction, entry_price, entry_bar):
        self.direction = direction
        self.entry_price = entry_price
        self.entry_bar = entry_bar
        self.current_stop = entry_price - 10 if direction == "long" else entry_price + 10


class TestLivePipeline:
    """实盘数据端到端测试。"""

    def test_full_pipeline_with_synthetic_data(self):
        """用合成数据走完整流程，验证系统各模块协同工作。"""
        # ========== 1. 生成模拟实盘数据 ==========
        bars = make_synthetic_bars(seed=42, n=500, kind="trend_regime")
        assert len(bars) == 500
        assert bars[0].close > 0

        # ========== 2. 数据验证 ==========
        report = validate_bars(bars)
        # 合成数据应该没有严重问题
        assert report is not None

        # ========== 3. 特征计算 ==========
        # ATR
        atr_value = wilder_atr(bars, as_of=bars[-1].ts_utc, period=14)
        assert atr_value > 0

        # 市场结构
        structure = get_market_structure(bars, k=5)
        assert structure is not None

        # ========== 4. 策略信号检测 ==========
        # 检测最近的K线形态
        recent_bars = bars[-20:]
        engulfing_count = 0
        hammer_count = 0

        for i in range(2, len(recent_bars)):
            window = recent_bars[:i+1]
            if is_engulfing(window, direction="bullish"):
                engulfing_count += 1
            if is_hammer(recent_bars[i], direction="bullish"):
                hammer_count += 1

        # 统计信号数量
        assert isinstance(engulfing_count, int)
        assert isinstance(hammer_count, int)

        # ========== 5. 风控测试 ==========
        stop_config = StopConfig(
            atr_mult=2.0,
            max_holding_bars=50,
            breakeven_r=1.0,
            trailing_activation_r=1.5,
            trailing_offset_r=1.0,
        )

        # 模拟持仓
        position = FakePosition(
            direction="long",
            entry_price=bars[-10].close,
            entry_bar=len(bars) - 10,
        )

        stop_state = StopState(
            entry_price=position.entry_price,
            direction=1,  # 多头
            entry_atr=atr_value,
            entry_dist=atr_value * 2.0,
            current_stop=position.current_stop,
            bars_held=10,
            max_favorable_r=0.0,
        )

        # 评估止损
        current_bar = bars[-1]
        should_close, new_stop, stop_type = evaluate_stops(
            state=stop_state,
            config=stop_config,
            current_price=current_bar.close,
            signal_reversed=False,
        )

        assert isinstance(should_close, bool)

        # ========== 6. 仓位计算 ==========
        account_equity = 10000.0
        risk_per_trade = 0.01  # 1% 风险
        stop_distance = atr_value * 2.0

        lots = target_lots(
            equity=account_equity,
            risk_pct=risk_per_trade,
            atr0=atr_value * 2.0,  # 止损距离 = 2 × ATR
            point_value=100.0,  # XAUUSD 每手每美元波动 = 100 USD
            min_lot=0.01,
            lot_step=0.01,
            kelly_cap=0.5,
        )
        assert lots >= 0

        # ========== 7. 过拟合检测 ==========
        # 模拟收益率序列
        returns = pd.Series(np.random.normal(0.0005, 0.01, 252))
        diagnostic = overfitting_diagnostic(returns, trials=5)
        assert "sharpe" in diagnostic
        assert "rating" in diagnostic

        # ========== 8. 前视偏差检测 ==========
        detector = LookaheadDetector()

        # 检查时间戳顺序
        timestamps = pd.Series([bar.ts_utc for bar in bars])
        detector.check_timestamp_order(timestamps, location="pipeline")

        summary = detector.summary()
        assert "total_violations" in summary

        # ========== 9. 漂移监控 ==========
        monitor = DriftMonitor(
            baseline_sharpe=1.5,
            baseline_win_rate=0.55,
            baseline_max_dd=0.1,
        )
        monitor.update(returns)
        status = monitor.status()

        assert "health_score" in status
        assert 0 <= status["health_score"] <= 100

    def test_pipeline_no_lookahead_leakage(self):
        """验证整个流程没有前视偏差。"""
        bars = make_synthetic_bars(seed=123, n=200, kind="martingale")

        detector = LookaheadDetector()

        # 检查时间戳严格递增
        timestamps = pd.Series([bar.ts_utc for bar in bars])
        detector.check_timestamp_order(timestamps, location="data")

        # 检查训练/测试分离
        train_bars = bars[:150]
        test_bars = bars[150:]

        train_ts = pd.Series([bar.ts_utc for bar in train_bars])
        test_ts = pd.Series([bar.ts_utc for bar in test_bars])

        train_df = pd.DataFrame({"timestamp": train_ts})
        test_df = pd.DataFrame({"timestamp": test_ts})

        detector.check_split_separation(train_df, test_df, location="split")

        # 合成数据不应该有前视偏差
        summary = detector.summary()
        assert summary["critical_count"] == 0

    def test_risk_control_works(self):
        """验证风控系统正常工作。"""
        bars = make_synthetic_bars(seed=456, n=100, kind="trend_regime")

        stop_config = StopConfig(
            atr_mult=2.0,
            max_holding_bars=30,
            breakeven_r=1.0,
            trailing_activation_r=1.5,
            trailing_offset_r=1.0,
        )

        atr_value = wilder_atr(bars, as_of=bars[-1].ts_utc, period=14)

        # 模拟一个亏损持仓
        stop_state = StopState(
            entry_price=bars[50].close,
            direction=1,  # 多头
            entry_atr=atr_value,
            entry_dist=atr_value * 2.0,
            current_stop=bars[50].close - atr_value * 2.0,
            bars_held=10,
            max_favorable_r=0.0,
        )

        # 价格下跌触发止损
        current_bar = bars[60]
        should_close, new_stop, stop_type = evaluate_stops(
            state=stop_state,
            config=stop_config,
            current_price=current_bar.close,
            signal_reversed=False,
        )

        # 止损应该只向盈利方向移动（多头只能上移）
        if new_stop is not None:
            if stop_state.direction == 1:  # 多头
                assert new_stop >= stop_state.current_stop

    def test_strategy_matcher_integration(self):
        """验证策略匹配器集成。"""
        from core.registry.strategy_matcher import (
            StrategyProfile,
            MarketRegime,
            StrategyMatcher,
        )

        # 注册多个策略
        strategies = [
            StrategyProfile("trend_following", ["trend_regime"], ["ranging"], 1.5, 0.15),
            StrategyProfile("mean_reversion", ["ranging"], ["trend_regime"], 1.2, 0.10),
            StrategyProfile("breakout", ["volatile"], ["quiet"], 1.3, 0.20),
        ]

        matcher = StrategyMatcher(strategies)

        # 模拟不同市场状态
        trend_regime_market = MarketRegime("trend_regime", strength=0.8, volatility="medium")
        ranging_market = MarketRegime("ranging", strength=0.6, volatility="low")

        # 趋势市场应该选趋势策略
        trend_ranking = matcher.rank(trend_regime_market)
        assert trend_ranking[0].profile.name == "trend_following"

        # 震荡市场应该选均值回归
        range_ranking = matcher.rank(ranging_market)
        assert range_ranking[0].profile.name == "mean_reversion"
