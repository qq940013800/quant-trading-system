# QuantDinger Pro API 文档

> 基于第一性原理和全球最佳实践的企业级量化交易系统 API
> 版本: v2.0.0 | 更新日期: 2026-10-25

---

## 目录

1. [概述](#概述)
2. [认证机制](#认证机制)
3. [核心 API 端点](#核心-api-端点)
4. [错误码规范](#错误码规范)
5. [WebSocket 实时数据](#websocket-实时数据)
6. [限流与配额](#限流与配额)
7. [SDK 示例](#sdk-示例)

---

## 概述

### 基础信息

| 项目 | 值 |
|------|-----|
| Base URL | `http://localhost:5000/api` |
| 协议 | HTTP/HTTPS |
| 数据格式 | JSON |
| 字符编码 | UTF-8 |
| 认证方式 | Bearer Token (JWT) |

### 统一响应格式

```json
{
  "code": 1,
  "msg": "success",
  "data": {}
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| code | int | 1=成功, 0=失败 |
| msg | string | 提示信息 |
| data | any | 业务数据 |

---

## 认证机制

### 登录认证

**POST** `/api/auth/login`

请求体:
```json
{
  "username": "string",
  "password": "string",
  "captcha": "string"
}
```

响应:
```json
{
  "code": 1,
  "msg": "success",
  "data": {
    "token": "eyJhbGciOiJIUzI1NiIs...",
    "expires_in": 86400,
    "user": {
      "id": 1,
      "username": "trader",
      "email": "trader@example.com"
    }
  }
}
```

### 请求头规范

所有需要认证的接口必须携带:
```
Authorization: Bearer <token>
Content-Type: application/json
```

---

## 核心 API 端点

### 1. 仪表盘 Dashboard

#### GET `/api/dashboard/summary`
获取仪表盘汇总数据

**响应数据:**
```json
{
  "total_equity": 10234.56,
  "daily_pnl": 123.45,
  "daily_pnl_pct": 1.21,
  "total_pnl": 234.56,
  "win_rate": 66.7,
  "sharpe": 1.85,
  "max_drawdown": -3.2,
  "total_trades": 128
}
```

#### GET `/api/dashboard/pendingOrders`
获取待处理订单

**参数:**
- page: 页码 (默认1)
- pageSize: 每页条数 (默认20)

#### DELETE `/api/dashboard/pendingOrders/<order_id>`
取消待处理订单

---

### 2. 交易所凭证 Credentials

#### GET `/api/credentials/list`
列出所有交易所凭证

**响应:**
```json
{
  "code": 1,
  "data": [
    {
      "id": 1,
      "name": "OKX-DEMO",
      "exchange_id": "okx",
      "api_key_hint": "8a12...0cf2",
      "is_active": true,
      "created_at": "2026-10-20T10:00:00Z"
    }
  ]
}
```

#### POST `/api/credentials/create`
创建新的交易所凭证

**请求体:**
```json
{
  "name": "OKX-Main",
  "exchange_id": "okx",
  "api_key": "your_api_key",
  "api_secret": "your_api_secret",
  "passphrase": "your_passphrase"
}
```

#### POST `/api/credentials/test`
测试连接

#### PUT `/api/credentials/update-name`
更新凭证名称

#### DELETE `/api/credentials/delete`
删除凭证

#### GET `/api/credentials/egress-ip`
获取服务器出口 IP (用于交易所白名单)

---

### 3. 策略管理 Strategy

#### GET `/api/strategy/list`
获取策略列表

**响应:**
```json
{
  "code": 1,
  "data": [
    {
      "id": 1,
      "name": "ML增强趋势策略",
      "description": "基于机器学习的趋势跟踪策略",
      "status": "running",
      "execution_mode": "live",
      "market_category": "Crypto",
      "market_type": "swap",
      "credential_id": 1,
      "initial_capital": 1000,
      "sharpe": 1.85,
      "max_drawdown": -5.2,
      "total_trades": 45,
      "created_at": "2026-10-01T00:00:00Z"
    }
  ]
}
```

#### POST `/api/strategy/create`
创建新策略

#### PUT `/api/strategy/update/<id>`
更新策略配置

#### POST `/api/strategy/start/<id>`
启动策略

#### POST `/api/strategy/stop/<id>`
停止策略

#### DELETE `/api/strategy/delete/<id>`
删除策略

---

### 4. 回测中心 Backtest

#### POST `/api/backtest/run`
运行回测

**请求体:**
```json
{
  "strategy_id": 1,
  "symbol": "BTC/USDT",
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "initial_capital": 10000,
  "commission": 0.001,
  "slippage": 0.0001
}
```

**响应:**
```json
{
  "code": 1,
  "data": {
    "backtest_id": 5,
    "total_return": 67.97,
    "annual_return": 67.97,
    "sharpe": 1.85,
    "max_drawdown": -15.2,
    "win_rate": 55.6,
    "profit_factor": 1.85,
    "total_trades": 128,
    "equity_curve": [...]
  }
}
```

#### GET `/api/backtest/history`
获取回测历史

#### GET `/api/backtest/get`
获取回测详情

#### POST `/api/backtest/tune`
参数优化

---

### 5. 组合与持仓 Portfolio

#### GET `/api/portfolio/positions`
获取当前持仓

**响应:**
```json
{
  "code": 1,
  "data": [
    {
      "symbol": "BTC/USDT",
      "side": "long",
      "amount": 0.5,
      "entry_price": 42000,
      "current_price": 42469.12,
      "pnl": 234.56,
      "pnl_pct": 1.11
    }
  ]
}
```

#### GET `/api/portfolio/overview`
组合概览

#### GET `/api/portfolio/trades`
历史交易记录

#### GET `/api/portfolio/performance`
绩效分析

---

### 6. 市场数据 Market

#### GET `/api/market/symbols`
获取交易对列表

#### GET `/api/market/ticker/<symbol>`
获取实时行情

#### GET `/api/market/orderbook/<symbol>`
获取订单簿

#### GET `/api/market/kline/<symbol>`
获取K线数据

**参数:**
- interval: 时间周期 (1m/5m/15m/1h/4h/1d)
- limit: 条数 (默认100)

---

### 7. 快速交易 Quick Trade

#### POST `/api/quick-trade/order`
快速下单

**请求体:**
```json
{
  "symbol": "BTC/USDT",
  "side": "buy",
  "type": "limit",
  "price": 42000,
  "amount": 0.1,
  "credential_id": 1
}
```

---

### 8. 因子研究 Factors

#### GET `/api/factors`
获取因子列表

#### GET `/api/factors/<factor_id>`
获取因子详情

#### POST `/api/factors/research`
因子研究

---

## 错误码规范

| 错误码 | 说明 | 处理建议 |
|--------|------|---------|
| 1 | 成功 | - |
| 0 | 失败 | 查看msg字段 |
| 401 | 未认证 | 重新登录获取token |
| 403 | 无权限 | 检查账户权限 |
| 404 | 资源不存在 | 检查URL和ID |
| 429 | 请求过于频繁 | 降低请求频率 |
| 500 | 服务器错误 | 联系管理员 |

### 业务错误码

| 错误码 | 说明 |
|--------|------|
| 1001 | 账户凭证无效 |
| 1002 | 交易所连接失败 |
| 1003 | 策略运行中无法删除 |
| 1004 | 余额不足 |
| 1005 | 风控触发熔断 |
| 2001 | 回测参数错误 |
| 2002 | 数据不足无法回测 |

---

## WebSocket 实时数据

### 连接地址

```
ws://localhost:5000/ws?token=<your_token>
```

### 订阅频道

#### 行情数据
```json
{
  "action": "subscribe",
  "channel": "ticker",
  "symbol": "BTC/USDT"
}
```

#### 持仓更新
```json
{
  "action": "subscribe",
  "channel": "positions"
}
```

#### 订单更新
```json
{
  "action": "subscribe",
  "channel": "orders"
}
```

#### 策略信号
```json
{
  "action": "subscribe",
  "channel": "signals",
  "strategy_id": 1
}
```

---

## 限流与配额

| 接口类型 | 限制 |
|---------|------|
| 认证接口 | 10次/分钟 |
| 查询接口 | 100次/分钟 |
| 交易接口 | 30次/分钟 |
| WebSocket | 单连接最多订阅20个频道 |

---

## SDK 示例

### Python

```python
import requests

class QuantDingerClient:
    def __init__(self, base_url, token):
        self.base_url = base_url
        self.headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
    
    def get_dashboard_summary(self):
        r = requests.get(f'{self.base_url}/dashboard/summary', headers=self.headers)
        return r.json()
    
    def list_strategies(self):
        r = requests.get(f'{self.base_url}/strategy/list', headers=self.headers)
        return r.json()
    
    def create_strategy(self, name, symbol, capital):
        data = {
            'name': name,
            'symbol': symbol,
            'initial_capital': capital
        }
        r = requests.post(f'{self.base_url}/strategy/create', 
                         json=data, headers=self.headers)
        return r.json()
```

### JavaScript

```javascript
class QuantDingerAPI {
  constructor(baseUrl, token) {
    this.baseUrl = baseUrl;
    this.headers = {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    };
  }
  
  async getDashboardSummary() {
    const r = await fetch(`${this.baseUrl}/dashboard/summary`, {
      headers: this.headers
    });
    return r.json();
  }
  
  async listCredentials() {
    const r = await fetch(`${this.baseUrl}/credentials/list`, {
      headers: this.headers
    });
    return r.json();
  }
}
```

---

## 变更日志

### v2.0.0 (2026-10-25)
- 新增完整的API文档
- 统一响应格式
- 新增WebSocket实时数据频道
- 完善错误码规范

### v1.0.0 (2026-10-01)
- 初始版本
- 基础CRUD接口
