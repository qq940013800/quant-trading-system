# QuantDinger 前后端对齐分析报告

> 基于第一性原理和全球最佳实践的系统对齐

---

## 目录

1. [前后端API清单](#前后端api清单)
2. [数据模型对齐](#数据模型对齐)
3. [差距分析](#差距分析)
4. [优化优先级](#优化优先级)
5. [下一步行动计划](#下一步行动计划)

---

## 前后端API清单

### 后端已有API

| 模块 | 端点 | 方法 | 说明 |
|------|------|------|------|
| **认证** | /api/auth/login | POST | 用户登录 |
| | /api/auth/register | POST | 用户注册 |
| | /api/auth/me | GET | 当前用户信息 |
| **凭证** | /api/credentials/list | GET | 列出所有交易所凭证 |
| | /api/credentials/create | POST | 创建新凭证 |
| | /api/credentials/test | POST | 测试凭证连接 |
| | /api/credentials/delete | DELETE | 删除凭证 |
| **策略** | /api/strategy/list | GET | 策略列表 |
| | /api/strategy/create | POST | 创建策略 |
| | /api/strategy/update | PUT | 更新策略 |
| | /api/strategy/start | POST | 启动策略 |
| | /api/strategy/stop | POST | 停止策略 |
| | /api/strategy/positions | GET | 策略持仓 |
| **Dashboard** | /api/dashboard/summary | GET | 仪表盘汇总数据 |
| | /api/dashboard/pendingOrders | GET | 待处理订单 |
| **组合** | /api/portfolio/overview | GET | 组合概览 |
| | /api/portfolio/positions | GET | 组合持仓 |
| | /api/portfolio/pnl | GET | 盈亏分析 |
| **回测** | /api/backtest/run | POST | 运行回测 |
| | /api/backtest/results | GET | 回测结果 |
| **市场** | /api/market/kline | GET | K线数据 |
| | /api/market/ticker | GET | 实时行情 |
| **快速交易** | /api/quick_trade/order | POST | 快速下单 |

---

## 数据模型对齐

### 前端需要的数据结构

#### 1. 账户资产概览
```typescript
interface AccountSummary {
  totalEquity: number;        // 总权益
  todayPnl: number;            // 今日盈亏
  todayPnlPercent: number;     // 今日盈亏百分比
  availableBalance: number;    // 可用余额
  marginUsed: number;          // 已用保证金
  marginRatio: number;         // 保证金率
}
```

#### 2. 持仓列表
```typescript
interface Position {
  symbol: string;              // 交易对
  side: 'long' | 'short';      // 方向
  size: number;                // 数量
  entryPrice: number;          // 开仓价
  markPrice: number;           // 标记价
  pnl: number;                 // 未实现盈亏
  pnlPercent: number;         // 盈亏百分比
  leverage: number;            // 杠杆
}
```

#### 3. 策略列表
```typescript
interface Strategy {
  id: string;
  name: string;
  status: 'running' | 'stopped' | 'error';
  type: string;                // 策略类型
  market: string;              // 市场
  todayPnl: number;            // 今日盈亏
  totalReturn: number;         // 累计收益
  winRate: number;             // 胜率
  sharpe: number;              // 夏普比率
  maxDrawdown: number;        // 最大回撤
  credentialId: string;        // 绑定的账户ID
}
```

#### 4. 交易所凭证
```typescript
interface Credential {
  id: string;
  name: string;                // 账户名称
  exchangeId: string;          // 交易所ID (okx/binance/alpaca/ibkr)
  apiKeyHint: string;          // API密钥提示 (前4后4)
  status: 'connected' | 'disconnected' | 'error';
  createdAt: string;
}
```

---

## 差距分析

### 🔴 高优先级差距

| 问题 | 影响 | 修复方案 |
|------|------|---------|
| 前端新原型使用硬编码数据 | 无法真实使用 | 接入真实API |
| 策略编辑弹窗账户选择 | 用户无法绑定账户 | 修复compatibleCredentials过滤逻辑 |
| Dashboard数据为空 | 用户看不到真实数据 | 接入/api/dashboard/summary |
| 持仓列表为空 | 用户看不到持仓 | 接入/api/portfolio/positions |
| 凭证列表不显示 | 用户看不到已连接的账户 | 接入/api/credentials/list |

### 🟡 中优先级差距

| 问题 | 影响 | 修复方案 |
|------|------|---------|
| 没有实时价格图表 | 用户看不到K线 | 接入/api/market/kline + ECharts |
| 策略状态不实时更新 | 用户不知道策略是否运行 | WebSocket或定时轮询 |
| 没有交易历史 | 用户看不到历史交易 | 接入交易记录API |
| 没有通知中心 | 用户收不到策略告警 | 接入通知API |

### 🟢 低优先级差距

| 问题 | 影响 | 修复方案 |
|------|------|---------|
| 回测结果可视化 | 用户看不到回测详情 | 接入/api/backtest/results |
| 组合分析仪表盘 | 用户看不到组合风险 | 接入/api/portfolio/pnl |
| 风险压力测试 | 用户看不到极端场景 | 新增API |
| AI决策审计日志 | 用户看不到AI决策过程 | 接入审计API |

---

## 优化优先级

### Phase 1 - 数据接入（本周）
1. ✅ 创建前端原型
2. 🔲 接入/api/credentials/list - 显示真实账户列表
3. 🔲 接入/api/dashboard/summary - 显示真实资产数据
4. 🔲 接入/api/strategy/list - 显示真实策略列表
5. 🔲 接入/api/portfolio/positions - 显示真实持仓

### Phase 2 - 交互优化（下周）
1. 🔲 修复策略编辑弹窗账户选择
2. 🔲 添加实时价格图表
3. 🔲 策略状态实时更新
4. 🔲 交易历史时间线

### Phase 3 - 专业功能（2周内）
1. 🔲 组合分析仪表盘
2. 🔲 风险压力测试
3. 🔲 AI决策审计日志
4. 🔲 通知中心

---

## 下一步行动计划

### 立即执行
1. 继续完善前端原型
2. 添加API调用层
3. 接入第一个真实API（凭证列表）

### 本周完成
1. 所有核心数据接入
2. 策略编辑弹窗修复
3. 基本交互可用

### 长期目标
1. 完全替换原有前端
2. 对标Binance/OKX专业体验
3. AI增强的独特功能

---

**报告版本：** v1.0.0
**创建日期：** 2026-10-25
**基于：** 第一性原理 + 前后端对齐分析
