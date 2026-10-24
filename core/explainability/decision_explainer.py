# -*- coding: utf-8 -*-
"""core/explainability/decision_explainer.py —— 决策可解释性模块。

基于第一性原理：
    黑箱模型最危险的不是"不准"，而是你不知道它什么时候会崩。
    交易系统的每一笔决策都应该能回答：
    1. 为什么做这个决策？（输入了什么？用了什么规则？）
    2. 哪个特征贡献最大？（正贡献/负贡献各是多少？）
    3. 如果某个特征变了，决策会怎样？（反事实解释）
    4. 这个决策的置信度有多高？（边界在哪？）

    这就是Level 4的可解释性——决策完全透明，任何人都能复盘还原。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ------------------------------------------------------------------
# 数据结构
# ------------------------------------------------------------------
class DecisionOutcome(Enum):
    """决策结果。"""
    GO_LONG = "go_long"
    GO_SHORT = "go_short"
    NO_TRADE = "no_trade"
    STOP_OUT = "stop_out"


@dataclass
class FeatureContribution:
    """单个特征的贡献分解。"""
    name: str
    value: float
    contribution: float  # 对最终信号的贡献（正/负）
    direction: str       # "pushes_long" / "pushes_short" / "neutral"
    explanation: str     # 人类可读的解释

    @property
    def abs_contribution(self) -> float:
        return abs(self.contribution)


@dataclass
class DecisionTrace:
    """完整决策链追踪——从数据到最终决策的每一步。"""
    timestamp: str
    strategy_name: str
    strategy_version: str
    
    # 第1层：输入数据
    data_inputs: dict = field(default_factory=dict)
    
    # 第2层：计算的特征
    features: dict = field(default_factory=dict)
    
    # 第3层：特征贡献分解（SHAP风格）
    feature_contributions: list[FeatureContribution] = field(default_factory=list)
    
    # 第4层：原始信号
    raw_signal: float = 0.0  # -1到+1
    
    # 第5层：风控过滤后的信号
    filtered_signal: float = 0.0
    risk_filter_reasons: list[str] = field(default_factory=list)
    
    # 第6层：最终决策
    final_decision: DecisionOutcome = DecisionOutcome.NO_TRADE
    confidence: float = 0.0  # 0-1
    
    # 第7层：人类可读解释
    explanation: str = ""
    
    # 第8层：反事实分析
    counterfactuals: list[dict] = field(default_factory=list)


# ------------------------------------------------------------------
# 决策解释器
# ------------------------------------------------------------------
class DecisionExplainer:
    """决策可解释性生成器。

    用法：
        explainer = DecisionExplainer()
        
        # 在策略决策时调用
        trace = explainer.build_trace(
            strategy_name="ml_trend",
            strategy_version="v1.2.0",
            data={"close": 2000.5, "atr": 2.3},
            features={"trend_strength": 0.75, "volatility": "normal"},
            feature_contributions=[...],
            raw_signal=0.65,
            risk_filters=["信号强度>0.5", "波动率正常"],
            final_decision=DecisionOutcome.GO_LONG,
        )
        
        # 生成人类可读解释
        print(explainer.humanize(trace))
    """

    def build_trace(self,
                    strategy_name: str,
                    strategy_version: str,
                    data: dict,
                    features: dict,
                    feature_contributions: list[FeatureContribution],
                    raw_signal: float,
                    risk_filter_reasons: list[str],
                    final_decision: DecisionOutcome,
                    confidence: float = 0.8) -> DecisionTrace:
        """构建完整决策链追踪。"""
        from datetime import datetime
        
        trace = DecisionTrace(
            timestamp=datetime.now().isoformat(),
            strategy_name=strategy_name,
            strategy_version=strategy_version,
            data_inputs=data,
            features=features,
            feature_contributions=feature_contributions,
            raw_signal=raw_signal,
            risk_filter_reasons=risk_filter_reasons,
            final_decision=final_decision,
            confidence=confidence,
        )
        
        # 计算过滤后的信号（风控会打折）
        trace.filtered_signal = raw_signal * (1.0 - len(risk_filter_reasons) * 0.1)
        
        # 生成人类可读解释
        trace.explanation = self._generate_explanation(trace)
        
        # 生成反事实分析
        trace.counterfactuals = self._generate_counterfactuals(trace)
        
        return trace

    def _generate_explanation(self, trace: DecisionTrace) -> str:
        """生成人类可读的决策解释。"""
        lines = []
        
        # 决策结果
        if trace.final_decision == DecisionOutcome.GO_LONG:
            lines.append(f"【做多决策】信号强度 {trace.raw_signal:.2f}，置信度 {trace.confidence:.0%}")
        elif trace.final_decision == DecisionOutcome.GO_SHORT:
            lines.append(f"【做空决策】信号强度 {trace.raw_signal:.2f}，置信度 {trace.confidence:.0%}")
        else:
            lines.append(f"【不交易】信号不足或风控拦截")
        
        # 贡献最大的特征
        sorted_features = sorted(trace.feature_contributions, 
                                 key=lambda x: x.abs_contribution, reverse=True)
        
        if sorted_features:
            lines.append("\n主要驱动因素（按影响排序）：")
            for i, fc in enumerate(sorted_features[:3], 1):
                direction = "利多" if fc.contribution > 0 else "利空"
                lines.append(f"  {i}. {fc.name}: {direction} {abs(fc.contribution):.2f} — {fc.explanation}")
        
        # 风控过滤
        if trace.risk_filter_reasons:
            lines.append(f"\n风控通过条件：{len(trace.risk_filter_reasons)}项")
            for reason in trace.risk_filter_reasons:
                lines.append(f"  ✓ {reason}")
        
        return "\n".join(lines)

    def _generate_counterfactuals(self, trace: DecisionTrace) -> list[dict]:
        """生成反事实分析——如果某个特征变了，决策会怎样？"""
        counterfactuals = []
        
        sorted_features = sorted(trace.feature_contributions, 
                                 key=lambda x: x.abs_contribution, reverse=True)
        
        # 对前2个最重要的特征做反事实分析
        for fc in sorted_features[:2]:
            if fc.contribution > 0:
                # 如果这个利多特征消失了会怎样？
                new_signal = trace.raw_signal - fc.contribution
                new_decision = "仍然做多" if new_signal > 0.3 else "转为观望"
                counterfactuals.append({
                    "feature": fc.name,
                    "scenario": f"如果{fc.name}消失（贡献归零）",
                    "original_signal": trace.raw_signal,
                    "new_signal": round(new_signal, 2),
                    "impact": f"信号从 {trace.raw_signal:.2f} → {new_signal:.2f}，决策{new_decision}",
                })
            else:
                # 如果这个利空特征消失了会怎样？
                new_signal = trace.raw_signal - fc.contribution
                new_decision = "可能做多" if new_signal > 0.5 else "仍然观望"
                counterfactuals.append({
                    "feature": fc.name,
                    "scenario": f"如果{fc.name}消失（利空消失）",
                    "original_signal": trace.raw_signal,
                    "new_signal": round(new_signal, 2),
                    "impact": f"信号从 {trace.raw_signal:.2f} → {new_signal:.2f}，决策{new_decision}",
                })
        
        return counterfactuals

    def humanize(self, trace: DecisionTrace) -> str:
        """生成完整的人类可读决策报告。"""
        lines = [
            "=" * 60,
            f"决策报告 — {trace.strategy_name} {trace.strategy_version}",
            f"时间: {trace.timestamp}",
            "=" * 60,
            "",
            trace.explanation,
            "",
        ]
        
        # 反事实分析
        if trace.counterfactuals:
            lines.append("-" * 40)
            lines.append("反事实分析（什么会改变决策？）：")
            for cf in trace.counterfactuals:
                lines.append(f"  • {cf['impact']}")
            lines.append("")
        
        # 输入数据快照
        lines.append("-" * 40)
        lines.append("输入数据快照：")
        for k, v in list(trace.data_inputs.items())[:5]:
            lines.append(f"  {k}: {v}")
        
        return "\n".join(lines)

    def explain_no_trade(self, strategy_name: str, strategy_version: str,
                          reasons: list[str]) -> str:
        """解释为什么不交易。"""
        lines = [
            f"【不交易原因】{strategy_name} {strategy_version}",
            "",
            "被以下条件拦截：",
        ]
        for i, reason in enumerate(reasons, 1):
            lines.append(f"  {i}. {reason}")
        
        return "\n".join(lines)
