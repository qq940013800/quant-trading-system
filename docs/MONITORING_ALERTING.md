# QuantDinger Pro 系统监控与告警配置

> 基于第一性原理和全球最佳实践的企业级可观测性方案
> 版本: v1.0.0 | 更新日期: 2026-10-25

---

## 目录

1. [监控体系架构](#监控体系架构)
2. [黄金四指标](#黄金四指标)
3. [业务监控指标](#业务监控指标)
4. [系统监控指标](#系统监控指标)
5. [告警规则配置](#告警规则配置)
6. [告警分级与处理流程](#告警分级与处理流程)
7. [Dashboard 设计](#dashboard-设计)

---

## 监控体系架构

### 三层监控模型

```
┌─────────────────────────────────────────┐
│         业务层 (Business Metrics)        │  ← 交易盈亏、策略绩效、订单执行
├─────────────────────────────────────────┤
│         应用层 (Application Metrics)     │  ← API响应时间、错误率、队列长度
├─────────────────────────────────────────┤
│         系统层 (Infrastructure Metrics)  │  ← CPU、内存、磁盘、网络、数据库
└─────────────────────────────────────────┘
```

### 监控原则

1. **RED 原则**：Rate（请求量）、Errors（错误率）、Duration（响应时间）
2. **USE 原则**：Utilization（利用率）、Saturation（饱和度）、Errors（错误）
3. **告警可执行**：每条告警都必须有明确的处理动作
4. **减少告警疲劳**：合理设置阈值和静默期

---

## 黄金四指标

| 指标 | 说明 | 采集方式 |
|------|------|---------|
| 延迟 (Latency) | 请求处理时间分布 | API中间件 |
| 流量 (Traffic) | 请求QPS | API中间件 |
| 错误 (Errors) | 错误率和异常数 | 日志+异常捕获 |
| 饱和度 (Saturation) | 系统资源利用率 | node_exporter |

---

## 业务监控指标

### 1. 交易执行指标

| 指标名称 | 说明 | 告警阈值 |
|---------|------|---------|
| 订单成功率 | 成交订单/发送订单 | <95% 警告, <90% 严重 |
| 平均执行延迟 | 从信号到成交的时间 | >5s 警告, >30s 严重 |
| 滑点偏离 | 实际成交 vs 预期价格 | >0.1% 警告, >0.5% 严重 |
| 拒单率 | 交易所拒绝的订单比例 | >5% 警告, >10% 严重 |

### 2. 策略绩效指标

| 指标名称 | 说明 | 告警阈值 |
|---------|------|---------|
| 策略日收益率 | 当日策略盈亏百分比 | <-3% 警告, <-5% 严重 |
| 策略最大回撤 | 从最高点回撤幅度 | >10% 警告, >20% 严重 |
| 夏普比率衰减 | 滚动Sharpe下降幅度 | 下降>30% 警告 |
| 胜率异常 | 胜率突然大幅下降 | 下降>20% 警告 |

### 3. 组合风险指标

| 指标名称 | 说明 | 告警阈值 |
|---------|------|---------|
| 账户总回撤 | 账户权益从最高点回撤 | >5% 警告, >10% 严重 |
| 单策略风险敞口 | 单策略占总资金比例 | >30% 警告, >50% 严重 |
| 相关性风险 | 持仓间平均相关性 | >0.7 警告 |
| 保证金使用率 | 已用保证金/总权益 | >50% 警告, >80% 严重 |

---

## 系统监控指标

### 1. API 服务

| 指标 | 警告阈值 | 严重阈值 |
|------|---------|---------|
| API 响应时间 P95 | >500ms | >2000ms |
| API 错误率 | >1% | >5% |
| API QPS | >100 | >500 |
| 服务可用性 | <99.9% | <99% |

### 2. 数据库

| 指标 | 警告阈值 | 严重阈值 |
|------|---------|---------|
| 连接数使用率 | >70% | >90% |
| 慢查询数量 | >10/min | >50/min |
| 数据库复制延迟 | >1s | >10s |
| 表膨胀率 | >20% | >50% |

### 3. 基础设施

| 指标 | 警告阈值 | 严重阈值 |
|------|---------|---------|
| CPU 使用率 | >70% | >90% |
| 内存使用率 | >75% | >90% |
| 磁盘使用率 | >80% | >95% |
| 网络延迟 | >50ms | >200ms |
| Docker 容器状态 | 非运行状态 | 连续3次重启 |

### 4. 数据管道

| 指标 | 警告阈值 | 严重阈值 |
|------|---------|---------|
| 数据延迟 | >1min | >5min |
| 数据缺失率 | >0.1% | >1% |
| 数据校验失败 | >5次/小时 | >20次/小时 |

---

## 告警规则配置

### 告警级别定义

| 级别 | 颜色 | 响应时间 | 说明 |
|------|------|---------|------|
| P0 - 紧急 | 红色 | 5分钟内 | 系统不可用、资金风险、数据丢失 |
| P1 - 严重 | 橙色 | 30分钟内 | 核心功能异常、性能严重下降 |
| P2 - 警告 | 黄色 | 4小时内 | 非核心功能异常、资源接近阈值 |
| P3 - 提示 | 蓝色 | 24小时内 | 信息性通知、趋势预警 |

### 告警通道

| 级别 | 通知方式 |
|------|---------|
| P0 | 电话 + 短信 + 邮件 + 飞书 |
| P1 | 短信 + 邮件 + 飞书 |
| P2 | 邮件 + 飞书 |
| P3 | 飞书 |

### 具体告警规则

```yaml
# alert_rules.yaml

groups:
  - name: trading_system
    rules:
      # 交易执行告警
      - alert: OrderSuccessRateLow
        expr: order_success_rate < 0.95
        for: 5m
        labels:
          severity: P1
        annotations:
          summary: "订单成功率低于95%"
          description: "当前成功率 {{ $value | humanizePercentage }}"

      - alert: StrategyDailyLoss
        expr: strategy_daily_return < -0.03
        for: 1m
        labels:
          severity: P1
        annotations:
          summary: "策略日亏损超过3%"
          description: "策略 {{ $labels.strategy }} 当日亏损 {{ $value | humanizePercentage }}"

      - alert: AccountDrawdownHigh
        expr: account_drawdown > 0.05
        for: 1m
        labels:
          severity: P0
        annotations:
          summary: "账户回撤超过5%"
          description: "账户当前回撤 {{ $value | humanizePercentage }}"

      # API 服务告警
      - alert: APIHighLatency
        expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 0.5
        for: 5m
        labels:
          severity: P2
        annotations:
          summary: "API P95响应时间超过500ms"

      - alert: APIHighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.01
        for: 5m
        labels:
          severity: P1
        annotations:
          summary: "API错误率超过1%"

      # 基础设施告警
      - alert: HighCPUUsage
        expr: avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) by (instance) < 0.3
        for: 10m
        labels:
          severity: P2
        annotations:
          summary: "CPU使用率超过70%"

      - alert: HighMemoryUsage
        expr: (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) > 0.75
        for: 10m
        labels:
          severity: P2
        annotations:
          summary: "内存使用率超过75%"

      - alert: DiskSpaceLow
        expr: (node_filesystem_avail_bytes / node_filesystem_size_bytes) < 0.2
        for: 5m
        labels:
          severity: P1
        annotations:
          summary: "磁盘空间不足20%"

      # 数据库告警
      - alert: HighDBConnections
        expr: db_connections_in_use / db_connections_max > 0.7
        for: 5m
        labels:
          severity: P2
        annotations:
          summary: "数据库连接数超过70%"

      - alert: SlowQueries
        expr: rate(db_slow_queries_total[5m]) > 10
        for: 10m
        labels:
          severity: P2
        annotations:
          summary: "慢查询数量异常"
```

---

## 告警分级与处理流程

### P0 - 紧急告警处理流程

1. **立即响应**（5分钟内）
   - 确认告警真实性
   - 启动故障应急响应
   - 通知所有相关人员

2. **临时止血**（15分钟内）
   - 必要时停止交易策略
   - 降级非核心服务
   - 保护资金安全

3. **根因分析**（1小时内）
   - 定位问题根因
   - 评估影响范围
   - 制定修复方案

4. **恢复验证**
   - 修复后验证系统
   - 逐步恢复服务
   - 确认问题解决

5. **事后复盘**（24小时内）
   - 编写事故报告
   - 总结经验教训
   - 改进监控和告警

### 告警静默与抑制

- **维护窗口**：计划维护期间自动静默相关告警
- **告警抑制**：P0告警触发时，自动抑制关联的P2/P3告警
- **重复告警**：相同告警在30分钟内不重复通知
- **依赖抑制**：底层服务故障时，自动抑制上层服务告警

---

## Dashboard 设计

### 1. 总览仪表盘

- 系统健康状态总览
- 关键指标卡片
- 最近告警列表
- 交易概览

### 2. 交易监控仪表盘

- 实时持仓和盈亏
- 订单执行统计
- 策略运行状态
- 风险敞口分布

### 3. 性能监控仪表盘

- API响应时间分布
- 请求量趋势
- 错误率趋势
- 资源使用率

### 4. 数据库监控仪表盘

- 连接数趋势
- 慢查询列表
- 表空间使用
- 复制延迟

---

## 最佳实践

### 告警设计原则

1. **少而精**：宁可漏报，不可滥报
2. **可执行**：每条告警都必须有对应的处理动作
3. **分级**：不同级别对应不同响应方式
4. **关联**：避免告警风暴，做好关联和抑制
5. **持续优化**：定期回顾告警有效性，调整阈值

### 常见反模式

- ❌ 告警阈值太敏感 → 告警疲劳
- ❌ 只有系统指标告警，没有业务告警
- ❌ 告警没有处理流程 → 收到告警不知道做什么
- ❌ 没有静默和抑制 → 维护时告警轰炸
- ❌ 告警只通知不追踪 → 问题没有闭环

---

## 配置文件位置

| 文件 | 路径 |
|------|------|
| 告警规则 | `configs/alert_rules.yaml` |
| 监控配置 | `configs/monitoring.yaml` |
| Dashboard配置 | `configs/dashboards/` |
