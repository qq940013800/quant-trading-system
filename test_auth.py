# -*- coding: utf-8 -*-
"""测试QuantDinger API认证。"""
import requests
import json

# 先登录获取token
login_url = 'http://localhost:5000/api/auth/login'
login_data = {'username': 'admin', 'password': 'Admin@2026'}
response = requests.post(login_url, json=login_data, timeout=10)
token = response.json()['data']['token']
print(f'获取token成功: {token[:30]}...')

# 用token访问策略列表
strategies_url = 'http://localhost:5000/api/agent/v1/strategies?limit=10'
headers = {'Authorization': f'Bearer {token}'}
response = requests.get(strategies_url, headers=headers, timeout=10)
print(f'策略列表状态码: {response.status_code}')
result = response.json()
print(f'响应类型: {type(result).__name__}')

if isinstance(result, list):
    print(f'策略数量: {len(result)}')
    if len(result) > 0:
        print(f'第一个策略: {json.dumps(result[0], indent=2, ensure_ascii=False)[:300]}')
else:
    print(f'响应: {json.dumps(result, indent=2, ensure_ascii=False)[:300]}')
