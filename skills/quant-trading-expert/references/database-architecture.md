# PostgreSQL 数据库架构与运维指南

> 量化交易系统的数据层：数据是策略的根基，数据错了再聪明的模型也没用。

## 目录

1. [为什么量化系统选择PostgreSQL](#为什么量化系统选择postgresql)
2. [核心表设计](#核心表设计)
3. [索引策略](#索引策略)
4. [时序数据优化](#时序数据优化)
5. [数据质量保障](#数据质量保障)
6. [连接池与性能](#连接池与性能)
7. [备份与恢复](#备份与恢复)
8. [监控指标](#监控指标)
9. [常见陷阱](#常见陷阱)

---

## 为什么量化系统选择PostgreSQL

### 第一性原理

量化交易的数据有什么特点？
1. **关系复杂**：策略 → 信号 → 订单 → 成交 → 日志，层层关联
2. **事务性强**：订单状态变更必须原子操作，不能半成功
3. **查询多样**：既要查时间序列（K线），又要做聚合统计（绩效分析）
4. **数据量大**：多年多品种的tick/K线数据，TB级
5. **一致性要求高**：资金账户、持仓数据不能错

### 为什么不是其他数据库

| 数据库 | 优点 | 为什么不适合 |
|--------|------|-------------|
| MongoDB | 灵活schema | 事务弱，复杂查询慢 |
| MySQL | 简单普及 | 复杂分析查询不如PG |
| InfluxDB | 时序专用 | 不适合订单/账户这类关系数据 |
| SQLite | 轻量 | 并发写入差，不能多进程 |
| ClickHouse | 分析快 | 事务弱，不适合写多的场景 |

**PostgreSQL的优势组合**：
- 完整ACID事务 → 订单/资金安全
- 丰富索引类型 → B-tree/GIN/BRIN
- 时序扩展 → TimescaleDB
- 强大查询能力 → CTE/窗口函数/聚合
- 成熟生态 → 工具链完善

---

## 核心表设计

### 量化系统的核心表清单

```
┌─────────────────────────────────────────────────────────┐
│                    数据层                                │
├─────────────┬─────────────┬─────────────┬─────────────┤
│ 市场数据表  │  策略表     │  交易表     │  审计日志表 │
├─────────────┼─────────────┼─────────────┼─────────────┤
│ kline_data  │ strategies  │ orders      │ audit_logs  │
│ tick_data   │ signals     │ trades      │ decision_trace│
│ funding_rate│ strategy_runs│ positions   │ drift_events│
└─────────────┴─────────────┴─────────────┴─────────────┘
```

### 1. K线数据表（时序数据）

```sql
CREATE TABLE kline_data (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,  -- 1m, 5m, 1h, 1d
    open_time TIMESTAMPTZ NOT NULL,
    open_price NUMERIC(20, 8) NOT NULL,
    high_price NUMERIC(20, 8) NOT NULL,
    low_price NUMERIC(20, 8) NOT NULL,
    close_price NUMERIC(20, 8) NOT NULL,
    volume NUMERIC(30, 8) NOT NULL,
    quote_volume NUMERIC(30, 8),
    trade_count INTEGER,
    
    -- 唯一约束：同品种同周期同时间不能重复
    UNIQUE(symbol, timeframe, open_time)
);

-- 索引：按品种+周期+时间倒序查最新数据
CREATE INDEX idx_kline_symbol_tf_time 
ON kline_data (symbol, timeframe, open_time DESC);
```

### 2. 策略注册表

```sql
CREATE TABLE strategies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    version VARCHAR(20) NOT NULL,
    class_path VARCHAR(200) NOT NULL,  -- Python类路径
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    -- draft → backtest → paper → live → retired
    
    -- 策略参数（JSON灵活存储）
    config JSONB NOT NULL DEFAULT '{}',
    
    -- 元数据
    description TEXT,
    author VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

**为什么用JSONB存配置？**
- 不同策略参数差异很大，用JSONB不需要ALTER TABLE
- JSONB支持索引，可以按参数查询
- 保留灵活性，同时有schema约束

### 3. 订单与成交表

```sql
CREATE TABLE orders (
    id BIGSERIAL PRIMARY KEY,
    strategy_id INTEGER REFERENCES strategies(id),
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,      -- buy/sell
    order_type VARCHAR(20) NOT NULL,  -- market/limit/stop
    quantity NUMERIC(20, 8) NOT NULL,
    price NUMERIC(20, 8),
    
    status VARCHAR(20) NOT NULL,
    -- pending → partial → filled / cancelled / rejected
    
    -- 风控信息
    stop_loss NUMERIC(20, 8),
    take_profit NUMERIC(20, 8),
    risk_r NUMERIC(10, 4),  -- R倍数
    
    broker_order_id VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE trades (
    id BIGSERIAL PRIMARY KEY,
    order_id BIGINT REFERENCES orders(id),
    strategy_id INTEGER REFERENCES strategies(id),
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,
    quantity NUMERIC(20, 8) NOT NULL,
    price NUMERIC(20, 8) NOT NULL,
    commission NUMERIC(20, 8) NOT NULL DEFAULT 0,
    
    -- 结算信息
    realized_pnl NUMERIC(20, 8),
    realized_r NUMERIC(10, 4),
    
    executed_at TIMESTAMPTZ NOT NULL
);
```

### 4. 决策审计日志

```sql
CREATE TABLE decision_trace (
    id BIGSERIAL PRIMARY KEY,
    strategy_id INTEGER NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    bar_time TIMESTAMPTZ NOT NULL,
    
    -- 8层决策链快照（JSONB完整记录）
    layer1_position JSONB,
    layer2_regime JSONB,
    layer3_trigger JSONB,
    layer4_size JSONB,
    layer5_stops JSONB,
    layer6_execution JSONB,
    
    -- 最终决策
    decision VARCHAR(20) NOT NULL,  -- enter_long/enter_flat/hold/reject
    confidence NUMERIC(5, 4),
    
    -- 为什么拒绝（如果拒绝了）
    reject_reason VARCHAR(200),
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 按策略+时间查询
CREATE INDEX idx_decision_strategy_time 
ON decision_trace (strategy_id, bar_time DESC);
```

**设计原则**：决策必须可审计——每笔交易都能还原"当时为什么这么做"。

---

## 索引策略

### 第一性原理：索引是用空间换时间

**什么时候需要索引？**
- 经常出现在WHERE/ORDER BY/GROUP BY中的列
- 关联查询的外键列
- 唯一性约束（自动创建唯一索引）

**什么时候不要索引？**
- 小表（全表扫描比索引还快）
- 频繁更新的列（索引维护成本高）
- 低基数列（性别、布尔值，区分度太低）

### BRIN索引：时序数据的秘密武器

K线表数据量大但时间连续，用BRIN索引比B-tree小100倍：

```sql
-- BRIN索引：块级索引，适合时序数据
CREATE INDEX idx_kline_time_brin 
ON kline_data USING BRIN (open_time) WITH (pages_per_range = 32);
```

**为什么BRIN适合？**
- 数据按时间顺序写入
- 每个数据块只记一个最小/最大值
- 索引体积极小（GB级数据索引才几MB）

### GIN索引：JSONB查询

```sql
-- JSONB参数查询索引
CREATE INDEX idx_strategies_config 
ON strategies USING GIN (config);

-- 查询示例：找所有atr_mult=2.0的策略
SELECT * FROM strategies WHERE config @> '{"atr_mult": 2.0}';
```

---

## 时序数据优化

### 什么时候需要TimescaleDB

| 数据量 | 方案 |
|--------|------|
| < 1000万行 | 原生PostgreSQL + BRIN索引足够 |
| 1000万~1亿行 | 分区表（按时间分区） |
| > 1亿行 | TimescaleDB扩展 |

### 分区表策略

```sql
-- 按月份分区K线数据
CREATE TABLE kline_data_2026_10 
PARTITION OF kline_data 
FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');
```

**分区的好处**：
- 老数据可以直接DROP分区，不用DELETE
- 查询只扫相关分区，速度快
- 备份可以按分区做

---

## 数据质量保障

### 第一性原理：垃圾进，垃圾出

量化交易最可怕的不是模型不准，而是**数据错了但你不知道**。

### 数据质量检查清单

```sql
-- 1. 时间连续性检查：有没有缺K线
SELECT symbol, timeframe, 
       COUNT(*) as bars,
       MIN(open_time) as first_bar,
       MAX(open_time) as last_bar
FROM kline_data
GROUP BY symbol, timeframe;
-- 对比理论应该有多少根K线

-- 2. 价格合理性检查
SELECT * FROM kline_data
WHERE high_price < low_price    -- 高点比低点还低
   OR open_price <= 0           -- 价格为负或0
   OR high_price < open_price;  -- 最高价比开盘价还低

-- 3. 成交量合理性
SELECT * FROM kline_data
WHERE volume < 0 OR volume IS NULL;

-- 4. 时间重叠检查
SELECT a.symbol, a.open_time, b.open_time
FROM kline_data a
JOIN kline_data b 
  ON a.symbol = b.symbol 
  AND a.timeframe = b.timeframe
  AND a.id < b.id
  AND a.open_time = b.open_time;
```

### 因果单向约束

数据库层面就要防止前视偏差：
- 信号表的`bar_time`必须 <= 订单表的`created_at`
- 回测系统只能查`open_time <= 当前bar`的数据
- 数据库视图可以做约束：`v_signals_past`只暴露历史数据

---

## 连接池与性能

### 为什么需要连接池

PostgreSQL每个连接都要fork一个进程，内存开销大（~10MB/连接）。
Web应用并发高时，不能每个请求都新建连接。

### 生产配置（psycopg2连接池）

```python
from psycopg2.pool import ThreadedConnectionPool

pool = ThreadedConnectionPool(
    minconn=5,      # 最小连接数
    maxconn=20,     # 最大连接数
    dsn="postgresql://..."
)
```

### 连接池大小怎么定

**公式**：`max_connections = (CPU核数 * 2) + 有效磁盘数`

实际经验：
- Web应用：10~20个连接足够
- 不要开太多，每个连接都消耗内存
- 前面加PgBouncer做连接池复用更高效

---

## 备份与恢复

### 第一性原理：备份不是为了"万一"，是为了"迟早"

**数据库一定会挂**：磁盘坏了、误删数据了、勒索病毒了、服务器丢了。

### 备份策略

| 备份类型 | 命令 | 频率 | 保留 |
|----------|------|------|------|
| 逻辑备份 | `pg_dump` | 每天 | 7天 |
| 连续归档 | WAL日志 | 实时 | 3天 |
| 全量物理备份 | `pg_basebackup` | 每周 | 4周 |

### pg_dump示例

```bash
# 导出整个数据库
pg_dump -U quant_super -d quant_db -F c -f quant_db_backup.dump

# 只导出某张表
pg_dump -U quant_super -d quant_db -t kline_data -F c -f kline.dump

# 恢复
pg_restore -U quant_super -d quant_db -c quant_db_backup.dump
```

### 恢复演练

**最重要的原则：备份不测试等于没备份。**

每季度做一次恢复演练：
1. 在测试库恢复最新备份
2. 验证数据完整性
3. 记录恢复时间（RTO：恢复时间目标）

---

## 监控指标

### 必须监控的PostgreSQL指标

| 指标 | 告警阈值 | 说明 |
|------|----------|------|
| 连接数使用率 | > 80% | 快打满了 |
| 慢查询数 | > 10/分钟 | 有SQL需要优化 |
| 锁等待时间 | > 1s | 有长事务阻塞 |
| 缓存命中率 | < 95% | 内存不够了 |
| 磁盘使用率 | > 80% | 快满了 |
| 复制延迟 | > 10s | 主从同步慢了 |

### 慢查询日志

```sql
-- postgresql.conf
log_min_duration_statement = 1000  -- 超过1秒的查询记录下来
log_statement = 'ddl'              -- 记录所有DDL操作
```

---

## 常见陷阱

| 陷阱 | 后果 | 正确做法 |
|------|------|----------|
| 用SELECT *查大表 | 内存爆掉 | 只查需要的列，加LIMIT |
| 事务太长不提交 | 锁表，阻塞 | 短事务，及时COMMIT |
| 缺索引 | 全表扫描，慢死 | EXPLAIN分析查询计划 |
| NUMERIC精度不够 | 价格误差 | 用NUMERIC(20,8)存价格 |
| 时区不统一 | 时间对不上 | 全部用TIMESTAMPTZ + UTC |
| 外键没索引 | 关联查询慢 | 外键列建索引 |
| VACUUM没跑 | 表膨胀 | 开autovacuum，定期检查 |
| 生产库直接ALTER TABLE | 锁表，业务停 | 用pg_repack或低峰期做 |

---

## 思考清单

上线前过一遍：

- [ ] 唯一约束加了吗？
- [ ] 核心查询的索引建了吗？
- [ ] 时区统一用TIMESTAMPTZ了吗？
- [ ] 连接池配了吗？
- [ ] 备份脚本跑过吗？
- [ ] 恢复演练做过吗？
- [ ] 慢查询日志开了吗？
- [ ] 监控告警配了吗？
- [ ] 数据质量检查脚本有了吗？
- [ ] 因果单向约束保证了吗？
