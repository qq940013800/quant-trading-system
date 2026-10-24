# -*- coding: utf-8 -*-
"""测试Agent Token访问策略列表。"""
import requests
import json

agent_token = 'qd_agent_wEJoyJYDxyLpHzgYwzlRJxIjuEKtPT2zUcRW4nj1yeI'

# 测试策略列表API
print("测试策略列表API...")
strategies_url = 'http://localhost:5000/api/agent/v1/strategies?limit=10'
headers = {'Authorization': f'Bearer {agent_token}'}
response = requests.get(strategies_url, headers=headers, timeout=10)
print(f"状态码: {response.status_code}")
result = response.json()
print(f"响应类型: {type(result).__name__}")

if isinstance(result, list):
    print(f"✅ 策略数量: {len(result)}")
    if len(result) > 0:
        print(f"第一个策略:")
        print(json.dumps(result[0], indent=2, ensure_ascii=False)[:500])
else:
    print(f"响应:")
    print(json.dumps(result, indent=2, ensure_ascii=False)[:500])

# 也测试一下健康检查API
print("\n\n测试健康检查API...")
health_url = 'http://localhost:5000/api/agent/v1/health'
response = requests.get(health_url, headers=headers, timeout=10)
print(f"状态码: {response.status_code}")
result = response.json()
print(f"响应: {json.dumps(result, indent=2, ensure_ascii=False)[:300]}")
