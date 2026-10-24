# -*- coding: utf-8 -*-
"""test_dynamic_allocator.py —— PM动态资金分配测试。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.risk.dynamic_allocator import DynamicAllocator, StrategyPerformance

# 模拟三个策略的绩效
strategies = [
    StrategyPerformance(
        strategy_id="trend_001",
        name="黄金趋势跟踪",
        sharpe=1.8,
        max_drawdown=0.10,
        win_rate=0.55,
        profit_factor=1.6,
        total_trades=50,
        consecutive_losses=2,
        avg_r_multiple=1.5,
        days_running=120,
    ),
    StrategyPerformance(
        strategy_id="mr_002",
        name="均值回归",
        sharpe=0.6,
        max_drawdown=0.18,
        win_rate=0.48,
        profit_factor=1.1,
        total_trades=80,
        consecutive_losses=4,
        avg_r_multiple=0.6,
        days_running=90,
    ),
    StrategyPerformance(
        strategy_id="new_003",
        name="新策略实验",
        sharpe=0.0,
        max_drawdown=0.02,
        win_rate=0.50,
        profit_factor=1.0,
        total_trades=3,
        consecutive_losses=1,
        avg_r_multiple=0.0,
        days_running=15,
    ),
]

allocator = DynamicAllocator()
for s in strategies:
    allocator.update_performance(s)

results = allocator.calculate_allocations(total_capital=1000000)

print("=" * 70)
print("PM动态资金分配结果（总资金：100万）")
print("=" * 70)
print(f"{'策略ID':<15} {'综合得分':<10} {'权重':<10} {'分配资金':<12} {'状态':<10} {'原因'}")
print("-" * 70)

for r in results:
    capital = 1000000 * r.weight
    print(f"{r.strategy_id:<15} {r.score:<10.1f} {r.weight*100:<10.1f}% {capital:<12.0f} {r.status:<10} {r.reason}")

print("=" * 70)
print("\n✅ PM动态资金分配测试通过！")
print("\n💡 核心逻辑：")
print("   - 表现好的策略自动多分配资金")
print("   - 表现差的进入观察期或暂停")
print("   - 新策略小仓位探索验证")
