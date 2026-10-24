# -*- coding: utf-8 -*-
"""tests.test_explainability.test_decision_explainer —— 决策可解释性测试。"""
from __future__ import annotations

import pytest

from core.explainability.decision_explainer import (
    DecisionExplainer,
    DecisionOutcome,
    FeatureContribution,
)


class TestDecisionExplainer:
    def test_build_long_trace(self):
        """构建做多决策追踪。"""
        explainer = DecisionExplainer()
        
        contributions = [
            FeatureContribution(
                name="trend_strength",
                value=0.75,
                contribution=0.4,
                direction="pushes_long",
                explanation="趋势强度较高，利多",
            ),
            FeatureContribution(
                name="atr_normal",
                value=2.3,
                contribution=0.2,
                direction="pushes_long",
                explanation="波动率正常，适合入场",
            ),
            FeatureContribution(
                name="volume_low",
                value=0.3,
                contribution=-0.1,
                direction="pushes_short",
                explanation="成交量偏低，轻微利空",
            ),
        ]
        
        trace = explainer.build_trace(
            strategy_name="ml_trend",
            strategy_version="v1.2.0",
            data={"close": 2000.5, "atr": 2.3},
            features={"trend_strength": 0.75, "volatility": "normal"},
            feature_contributions=contributions,
            raw_signal=0.5,
            risk_filter_reasons=["信号强度>0.5", "波动率正常"],
            final_decision=DecisionOutcome.GO_LONG,
            confidence=0.8,
        )
        
        assert trace.final_decision == DecisionOutcome.GO_LONG
        assert trace.raw_signal == 0.5
        assert len(trace.feature_contributions) == 3
        assert "做多决策" in trace.explanation

    def test_humanize_output(self):
        """人类可读输出包含关键信息。"""
        explainer = DecisionExplainer()
        
        contributions = [
            FeatureContribution(
                name="market_structure",
                value=1,
                contribution=0.35,
                direction="pushes_long",
                explanation="市场结构突破，利多",
            ),
        ]
        
        trace = explainer.build_trace(
            strategy_name="ml_trend",
            strategy_version="v1.2.0",
            data={"close": 2000.5},
            features={},
            feature_contributions=contributions,
            raw_signal=0.35,
            risk_filter_reasons=[],
            final_decision=DecisionOutcome.GO_LONG,
            confidence=0.7,
        )
        
        report = explainer.humanize(trace)
        
        assert "决策报告" in report
        assert "ml_trend" in report
        assert "主要驱动因素" in report
        assert "反事实分析" in report

    def test_no_trade_explanation(self):
        """不交易的解释。"""
        explainer = DecisionExplainer()
        
        report = explainer.explain_no_trade(
            strategy_name="ml_trend",
            strategy_version="v1.2.0",
            reasons=["信号强度0.2 < 阈值0.5", "波动率过高"],
        )
        
        assert "不交易原因" in report
        assert "信号强度" in report
        assert "波动率" in report

    def test_counterfactual_analysis(self):
        """反事实分析生成。"""
        explainer = DecisionExplainer()
        
        contributions = [
            FeatureContribution(
                name="trend_strength",
                value=0.75,
                contribution=0.4,
                direction="pushes_long",
                explanation="趋势强度高",
            ),
        ]
        
        trace = explainer.build_trace(
            strategy_name="ml_trend",
            strategy_version="v1.2.0",
            data={},
            features={},
            feature_contributions=contributions,
            raw_signal=0.4,
            risk_filter_reasons=[],
            final_decision=DecisionOutcome.GO_LONG,
            confidence=0.7,
        )
        
        assert len(trace.counterfactuals) > 0
        assert "如果" in trace.counterfactuals[0]["scenario"]
