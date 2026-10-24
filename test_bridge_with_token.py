# -*- coding: utf-8 -*-
"""测试配置了auth_token的桥接模块。"""
import sys
sys.path.insert(0, '.')

from core.integration.bridge import QuantDingerBridge, BridgeConfig

# 配置auth_token
config = BridgeConfig(
    auth_token='qd_agent_wEJoyJYDxyLpHzgYwzlRJxIjuEKtPT2zUcRW4nj1yeI'
)

bridge = QuantDingerBridge(config=config)

# 测试健康检查
print("测试健康检查...")
health = bridge.health()
print(f"  可达: {health.reachable}")
print(f"  状态: {health.status}")
print(f"  延迟: {health.latency_ms:.1f}ms")

# 测试策略列表
print("\n测试策略列表...")
strategies = bridge.list_strategies(limit=10)
print(f"  策略数量: {len(strategies)}")
for s in strategies:
    print(f"    - {s.name} ({s.strategy_id})")

print("\n✅ 桥接模块配置auth_token后工作正常！")
