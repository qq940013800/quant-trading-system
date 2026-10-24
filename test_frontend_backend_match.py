"""
QuantDinger 前后端匹配检查脚本
基于第一性原理逐一检查前端功能与后端API的匹配情况
"""
import requests
import json
import sys

BASE_URL = "http://localhost:5000"

def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def test_health():
    """1. 健康检查"""
    print_section("1. 健康检查")
    try:
        r = requests.get(f"{BASE_URL}/api/health", timeout=5)
        print(f"  Status: {r.status_code}")
        print(f"  Response: {json.dumps(r.json(), indent=2, ensure_ascii=False)[:200]}")
        return True
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        return False

def test_login():
    """2. 登录认证"""
    print_section("2. 登录认证")
    try:
        login_data = {"username": "admin", "password": "Admin@2026"}
        r = requests.post(f"{BASE_URL}/api/auth/login", json=login_data, timeout=5)
        print(f"  Status: {r.status_code}")
        data = r.json()
        print(f"  Response keys: {list(data.keys())}")
        
        # 提取token
        token = None
        if "data" in data:
            if "access_token" in data["data"]:
                token = data["data"]["access_token"]
            elif "token" in data["data"]:
                token = data["data"]["token"]
        elif "access_token" in data:
            token = data["access_token"]
        
        if token:
            print(f"  ✅ Token获取成功: {token[:40]}...")
            return token
        else:
            print(f"  ❌ 未找到token")
            print(f"  Full response: {json.dumps(data, indent=2, ensure_ascii=False)[:300]}")
            return None
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        return None

def test_strategies(token):
    """3. 策略管理"""
    print_section("3. 策略管理API")
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(f"{BASE_URL}/api/strategies", headers=headers, timeout=5)
        print(f"  GET /api/strategies - Status: {r.status_code}")
        data = r.json()
        
        strategies = None
        if isinstance(data, dict) and "data" in data:
            strategies = data["data"]
        else:
            strategies = data
        
        if isinstance(strategies, list):
            print(f"  ✅ 策略数量: {len(strategies)}")
            for s in strategies[:5]:
                print(f"    - ID:{s.get('id')} {s.get('strategy_name')} [{s.get('status')}] {s.get('symbol')}")
        else:
            print(f"  Response: {json.dumps(data, indent=2, ensure_ascii=False)[:300]}")
        return True
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        return False

def test_agent_strategies(token):
    """4. Agent Gateway 策略API"""
    print_section("4. Agent Gateway 策略API")
    headers = {"Authorization": f"Bearer {token}"}
    try:
        # 用Agent Token测试
        agent_token = "qd_agent_wEJoyJYDxyLpHzgYwzlRJxIjuEKtPT2zUcRW4nj1yeI"
        agent_headers = {"Authorization": f"Bearer {agent_token}"}
        
        r = requests.get(f"{BASE_URL}/api/agent/v1/strategies", headers=agent_headers, timeout=5)
        print(f"  GET /api/agent/v1/strategies - Status: {r.status_code}")
        data = r.json()
        print(f"  Response: {json.dumps(data, indent=2, ensure_ascii=False)[:300]}")
        return True
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        return False

def test_account(token):
    """5. 账户信息"""
    print_section("5. 账户信息API")
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(f"{BASE_URL}/api/account/snapshot", headers=headers, timeout=5)
        print(f"  GET /api/account/snapshot - Status: {r.status_code}")
        print(f"  Response: {json.dumps(r.json(), indent=2, ensure_ascii=False)[:200]}")
        return True
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        return False

def test_markets(token):
    """6. 市场数据"""
    print_section("6. 市场数据API")
    agent_token = "qd_agent_wEJoyJYDxyLpHzgYwzlRJxIjuEKtPT2zUcRW4nj1yeI"
    agent_headers = {"Authorization": f"Bearer {agent_token}"}
    try:
        r = requests.get(f"{BASE_URL}/api/agent/v1/markets", headers=agent_headers, timeout=5)
        print(f"  GET /api/agent/v1/markets - Status: {r.status_code}")
        data = r.json()
        print(f"  Response: {json.dumps(data, indent=2, ensure_ascii=False)[:200]}")
        return True
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        return False

def test_ai_chat(token):
    """7. AI聊天"""
    print_section("7. AI聊天API")
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(f"{BASE_URL}/api/ai/chat/sessions", headers=headers, timeout=5)
        print(f"  GET /api/ai/chat/sessions - Status: {r.status_code}")
        print(f"  Response: {json.dumps(r.json(), indent=2, ensure_ascii=False)[:200]}")
        return True
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        return False

def main():
    print("=" * 60)
    print("  QuantDinger 前后端匹配检查")
    print("=" * 60)
    
    # 1. 健康检查
    health_ok = test_health()
    
    # 2. 登录
    token = test_login()
    
    if token:
        # 3. 策略管理
        test_strategies(token)
        
        # 4. Agent Gateway
        test_agent_strategies(token)
        
        # 5. 账户
        test_account(token)
        
        # 6. 市场
        test_markets(token)
        
        # 7. AI聊天
        test_ai_chat(token)
    
    print_section("检查完成")
    print("  请根据上述检查结果，对照前端页面验证功能匹配情况")

if __name__ == "__main__":
    main()
