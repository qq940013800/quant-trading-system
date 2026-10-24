# QuantDinger Pro 前后端差距分析与优化计划

> 基于第一性原理和全球最佳实践
> 分析日期: 2026-10-25

---

## 一、后端API盘点（已实现）

### 1. 认证模块 (auth)
- POST /api/auth/login - 登录
- POST /api/auth/register - 注册
- GET /api/auth/info - 用户信息
- POST /api/auth/logout - 登出
- OAuth: Google, GitHub

### 2. 凭证模块 (credentials)
- GET /api/credentials/list - 列出所有凭证
- POST /api/credentials/create - 创建凭证
- POST /api/credentials/test - 测试连接
- PUT /api/credentials/update-name - 更新名称
- DELETE /api/credentials/delete - 删除凭证
- GET /api/credentials/egress-ip - 获取出口IP

### 3. 仪表盘 (dashboard)
- GET /api/dashboard/summary - 汇总数据
- GET /api/dashboard/pendingOrders - 待处理订单
- DELETE /api/dashboard/pendingOrders/<id> - 取消订单

### 4. 策略管理 (strategy_*)
- 策略CRUD
- 策略启停
- 策略日志
- 策略持仓
- 策略偏差监控
- 策略复盘

### 5. 回测中心 (backtest_center)
- POST /api/backtest/run - 运行回测
- GET /api/backtest/history - 回测历史
- GET /api/backtest/get - 回测详情
- POST /api/backtest/tune - 参数优化
- 因子研究接口

### 6. 市场数据 (kline, market)
- K线数据获取
- 行情ticker
- 订单簿
- 交易对列表

### 7. 组合与持仓 (portfolio)
- 持仓列表
- 交易历史
- 绩效分析

### 8. 快速交易 (quick_trade)
- 下单接口
- 订单管理

### 9. AI对话 (ai_chat)
- AI助手对话
- 技能管理
- 记忆系统

---

## 二、前端现状分析

### 已实现 ✅
- [x] 三栏布局（左持仓 + 中图表 + 右下单）
- [x] 深色主题（对标Binance Pro）
- [x] 多页面视图切换（仪表盘/策略中心/回测/风险管理）
- [x] API服务层封装
- [x] 账户选择器（修复后的版本）
- [x] 策略编辑弹窗
- [x] 风险仪表盘卡片

### 缺失/不足 ❌
- [ ] 真实K线图（当前是占位符）
- [ ] 回测结果展示（权益曲线、交易列表）
- [ ] 订单簿实时数据
- [ ] 持仓实时更新
- [ ] WebSocket实时推送
- [ ] 策略详情页
- [ ] 绩效分析图表
- [ ] 错误处理和加载状态
- [ ] 响应式布局适配

---

## 三、优化优先级

### P0 - 核心功能（必须有）
1. **真实K线图** - 交易终端的核心
2. **回测结果展示** - 用户最关心的功能
3. **持仓实时数据** - 账户状态可见
4. **错误处理** - 接口失败要有提示

### P1 - 重要功能（应该有）
5. **订单簿展示** - 市场深度可见
6. **策略详情页** - 单个策略的完整信息
7. **绩效图表** - 收益曲线、回撤曲线
8. **加载状态** - 用户体验提升

### P2 - 增强功能（可以有）
9. **WebSocket实时推送** - 替代轮询
10. **响应式适配** - 平板/手机
11. **键盘快捷键** - 高频交易优化
12. **暗色/亮色主题切换**

---

## 四、技术选型

### K线图方案对比
| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| TradingView Lightweight Charts | 轻量、专业、开源 | 需要集成 | ⭐⭐⭐⭐⭐ |
| ECharts K线 | 中文文档好 | 交易专业度不够 | ⭐⭐⭐ |
| 自建Canvas | 完全可控 | 工作量大 | ⭐⭐ |

**结论：使用 TradingView Lightweight Charts**

### 图表库
- 主K线：TradingView Lightweight Charts
- 权益曲线：Lightweight Charts（同一库）
- 风险指标：原生CSS/SVG（轻量）

---

## 五、实施计划

### Phase 1: 核心K线图（今天）
1. 引入Lightweight Charts库
2. 创建K线图组件
3. 对接后端K线API
4. 添加时间周期切换

### Phase 2: 回测模块（明天）
1. 回测配置表单
2. 回测结果仪表盘
3. 权益曲线展示
4. 交易明细表

### Phase 3: 实时数据（后天）
1. 订单簿组件
2. 持仓实时更新
3. WebSocket连接（如果后端支持）
4. 错误处理和加载状态

---

## 六、前后端对齐检查清单

- [ ] K线数据格式是否匹配
- [ ] 回测API参数是否一致
- [ ] 持仓数据结构是否对齐
- [ ] 策略状态枚举是否统一
- [ ] 错误码格式是否一致
