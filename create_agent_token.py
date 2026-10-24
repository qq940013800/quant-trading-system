# -*- coding: utf-8 -*-
"""创建Agent Token并配置到桥接模块。"""
import requests
import json

# Step 1: 登录获取JWT token
print("Step 1: 登录获取JWT token...")
login_url = 'http://localhost:5000/api/auth/login'
login_data = {'username': 'admin', 'password': 'Admin@2026'}
response = requests.post(login_url, json=login_data, timeout=10)
jwt_token = response.json()['data']['token']
print(f"  ✅ JWT token获取成功: {jwt_token[:30]}...")

# Step 2: 用JWT token创建Agent Token
print("\nStep 2: 用JWT token创建Agent Token...")
create_token_url = 'http://localhost:5000/api/agent/v1/me/tokens'
headers = {'Authorization': f'Bearer {jwt_token}', 'Content-Type': 'application/json'}
token_data = {
    'name': '验证层守门员桥接',
    'scopes': ['R', 'B'],  # Read + Backtest权限，足够了
    'paper_only': True,  # 只允许模拟交易，安全第一
    'rate_limit_per_minute': 60,
}
response = requests.post(create_token_url, headers=headers, json=token_data, timeout=10)
print(f"  状态码: {response.status_code}")
result = response.json()
print(f"  响应: {json.dumps(result, indent=2, ensure_ascii=False)[:500]}")

if response.status_code == 200 and 'token' in result.get('data', {}):
    agent_token = result['data']['token']
    print(f"\n  ✅ Agent Token创建成功: {agent_token[:30]}...")
    
    # Step 3: 用Agent Token测试策略列表API
    print("\nStep 3: 用Agent Token测试策略列表API...")
    strategies_url = 'http://localhost:5000/api/agent/v1/strategies?limit=10'
    agent_headers = {'Authorization': f'Bearer {agent_token}'}
    response = requests.get(strategies_url, headers=agent_headers, timeout=10)
    print(f"  状态码: {response.status_code}")
    result = response.json()
    if isinstance(result, list):
        print(f"  ✅ 策略数量: {len(result)}")
        if len(result) > 0:
            print(f"  第一个策略: {json.dumps(result[0], indent=2, ensure_ascii=False)[:300]}")
    else:
        print(f"  响应: {json.dumps(result, indent=2, ensure_ascii=False)[:300]}")
    
    # Step 4: 保存token到配置
    print(f"\nStep 4: Agent Token: {agent_token}")
    print("  (请把这个token配置到桥接模块的BridgeConfig.auth_token里)")
else:
    print("\n  ❌ Agent Token创建失败")
    print("  可能原因: /me/tokens端点也需要Agent Token认证，而不是JWT")
