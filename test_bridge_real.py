"""测试桥接模块连接真实API。"""
from core.integration.bridge import QuantDingerBridge, BridgeConfig

AGENT_TOKEN = 'qd_agent_wEJoyJYDxyLpHzgYwzlRJxIjuEKtPT2zUcRW4nj1yeI'
config = BridgeConfig(auth_token=AGENT_TOKEN)
b = QuantDingerBridge(config=config)

print("=== 健康检查 ===")
h = b.health()
print(f"Reachable: {h.reachable}")
print(f"Status: {h.status}")
print(f"Latency: {h.latency_ms:.1f}ms")
print()

print("=== 策略列表 ===")
strategies = b.list_strategies(limit=10)
print(f"Strategies count: {len(strategies)}")
for s in strategies[:5]:
    print(f"  - {s.name} ({s.strategy_type}, {s.symbol})")
print()

print("=== 诊断报告 ===")
d = b.diagnose()
print(f"Bridge: {d['bridge']}")
print(f"Strategies count: {d['strategies_count']}")
print(f"Sample: {d['sample_strategies']}")
