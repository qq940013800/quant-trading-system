# -*- coding: utf-8 -*-
"""test_portfolio_analyzer.py —— 组合风险分析测试。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.risk.portfolio_analyzer import get_portfolio_analyzer
import numpy as np

# 模拟两个策略的收益率
np.random.seed(42)
trend_returns = np.random.normal(0.001, 0.02, 100).tolist()
mean_rev_returns = np.random.normal(-0.0005, 0.015, 100).tolist()

analyzer = get_portfolio_analyzer()

result = analyzer.analyze_portfolio(
    strategy_returns={
        "trend_following": trend_returns,
        "mean_reversion": mean_rev_returns,
    },
    strategy_weights={"trend_following": 0.6, "mean_reversion": 0.4}
)

print("=" * 60)
print("组合风险分析报告")
print("=" * 60)
print(f"策略数量: {result['num_strategies']}")
print(f"组合波动率: {result['portfolio_volatility']}")
print(f"平均波动率: {result['average_volatility']}")
print(f"分散化收益: {result['diversification_benefit_pct']}%")
print()
print("相关性矩阵:")
corr = result['correlation_matrix']
print(f"  平均相关性: {corr['avg_correlation']}")
print()
print("风险预算:")
for s, rb in result['risk_budget'].items():
    print(f"  {s}: {rb}%")
print()
print("建议:")
for rec in result['recommendations']:
    print(f"  {rec}")
print("=" * 60)
print("✅ 组合分析模块测试通过！")
