# PostgreSQL 运维实战手册

> 第一性原理：数据库不会无缘无故慢，慢了一定有原因。从查询到索引到锁，逐层定位。

## 目录

1. [日常运维检查清单](#日常运维检查清单)
2. [慢查询排查](#慢查询排查)
3. [锁与阻塞排查](#锁与阻塞排查)
4. [连接数问题](#连接数问题)
5. [表膨胀与VACUUM](#表膨胀与vacuum)
6. [磁盘空间管理](#磁盘空间管理)
7. [备份恢复实战](#备份恢复实战)
8. [性能调优参数](#性能调优参数)
9. [快速排障速查表](#快速排障速查表)

---

## 日常运维检查清单

### 每天必看

```sql
-- 1. 数据库大小
SELECT pg_size_pretty(pg_database_size('quant_db'));

-- 2. 表大小TOP10
SELECT relname, pg_size_pretty(pg_total_relation_size(relid))
FROM pg_catalog.pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 10;

-- 3. 连接数使用率
SELECT count(*), (SELECT setting::int FROM pg_settings WHERE name='max_connections')
FROM pg_stat_activity;

-- 4. 慢查询数量（开启了log_min_duration_statement的话）
-- 直接看日志文件

-- 5. 锁等待
SELECT count(*) FROM pg_locks WHERE NOT granted;
```

---

## 慢查询排查

### 第一性原理：慢查询的本质是——要么没走索引，要么返回的数据量太大。

### 排查步骤

```sql
-- 第一步：开启慢查询日志（如果还没开）
-- postgresql.conf:
-- log_min_duration_statement = 1000  # 超过1秒的记录

-- 第二步：找到慢查询后，用EXPLAIN分析
EXPLAIN ANALYZE
SELECT * FROM kline_data 
WHERE symbol = 'BTCUSDT' 
  AND timeframe = '1h' 
  AND open_time >= '2026-01-01'
ORDER BY open_time DESC LIMIT 100;
```

### EXPLAIN输出怎么读

```
Seq Scan on kline_data  (cost=0.00..12345.00 rows=1000 width=56)
```

| 字段 | 含义 | 什么时候要注意 |
|------|------|----------------|
| Seq Scan | 全表扫描 | 应该走索引的时候出现，说明缺索引 |
| Index Scan | 索引扫描 | 正常 |
| cost=0.00..12345.00 | 预估成本 | 越大越慢 |
| rows=1000 | 预估返回行数 | 和实际差太多说明统计信息不准 |

### 常见慢查询原因

| 原因 | 现象 | 解决方案 |
|------|------|----------|
| 缺索引 | Seq Scan | 加合适的索引 |
| 索引没命中 | 有索引但没用 | 看WHERE条件，是不是函数包了列 |
| 返回行太多 | LIMIT 100000 | 分页/分批查 |
| 统计信息不准 | rows预估差10倍以上 | `ANALYZE 表名` |
| join太多 | 多层嵌套循环 | 简化查询/加连接索引 |
| 大表count(*) | 全表扫一遍 | 用估算值`reltuples` |

---

## 锁与阻塞排查

### 第一性原理：锁的本质是——两个事务同时改同一行，一个必须等另一个。

### 找阻塞源

```sql
-- 谁在堵谁？
SELECT 
    blocked_locks.pid AS blocked_pid,
    blocking_locks.pid AS blocking_pid,
    blocked_activity.query AS blocked_query,
    blocking_activity.query AS blocking_query
FROM pg_catalog.pg_locks blocked_locks
JOIN pg_catalog.pg_stat_activity blocked_activity 
  ON blocked_activity.pid = blocked_locks.pid
JOIN pg_catalog.pg_locks blocking_locks 
  ON blocking_locks.locktype = blocked_locks.locktype
  AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database
  AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
  AND blocking_locks.page IS NOT DISTINCT FROM blocked_locks.page
  AND blocking_locks.tuple IS NOT DISTINCT FROM blocked_locks.tuple
  AND blocking_locks.virtualxid != blocked_locks.virtualxid
JOIN pg_catalog.pg_stat_activity blocking_activity 
  ON blocking_activity.pid = blocking_locks.pid
WHERE NOT blocked_locks.granted;
```

### 杀阻塞源

```sql
-- 杀掉堵人的那个进程（PID从上一步查出来）
SELECT pg_terminate_backend(12345);
```

**注意：杀之前确认一下这个进程在干什么，别误杀了正常的业务。**

### 常见锁问题

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| 长事务不提交 | 事务开着不关 | 短事务，及时COMMIT |
| 大表ALTER TABLE | 锁全表 | 低峰期做 / 用pg_repack |
| VACUUM FULL | 锁全表 | 别用FULL，用普通VACUUM |
| 批量UPDATE | 一行一行锁 | 分批提交，别一个事务改10万行 |

---

## 连接数问题

### 症状：报"too many connections"

**第一性原理：每个连接都要占内存（~10MB），连接不是越多越好。**

```sql
-- 看当前连接数
SELECT count(*) FROM pg_stat_activity;

-- 看每个用户/数据库各有多少连接
SELECT usename, datname, count(*) 
FROM pg_stat_activity 
GROUP BY usename, datname
ORDER BY count(*) DESC;

-- 看最长连接时间
SELECT pid, now() - query_start AS duration, query
FROM pg_stat_activity
ORDER BY duration DESC
LIMIT 10;
```

### 解决方案

1. **加连接池**：PgBouncer放在应用和数据库中间，100个应用连接复用10个数据库连接
2. **杀闲置连接**：`SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND query_start < now() - interval '1 hour';`
3. **调整max_connections**：不是越大越好，根据内存算

### PgBouncer配置示例

```ini
[databases]
quant_db = host=postgres port=5432 dbname=quant_db

[pgbouncer]
pool_mode = transaction
max_client_conn = 200
default_pool_size = 20
```

---

## 表膨胀与VACUUM

### 第一性原理：PostgreSQL的DELETE不是真删除，是标记为死元组。时间长了表会越来越大。

```sql
-- 看哪些表膨胀严重
SELECT 
    relname,
    n_live_tup,
    n_dead_tup,
    round(n_dead_tup::numeric / NULLIF(n_live_tup, 0) * 100, 2) AS dead_ratio
FROM pg_stat_user_tables
WHERE n_dead_tup > 1000
ORDER BY n_dead_tup DESC;
```

### 什么时候需要手动VACUUM

```sql
-- 普通VACUUM（不锁表）
VACUUM kline_data;

-- VACUUM ANALYZE（顺便更新统计信息）
VACUUM ANALYZE kline_data;

-- 注意：VACUUM FULL 会锁表！大表别在业务高峰期做
```

### autovacuum调优

```ini
# postgresql.conf
autovacuum = on
autovacuum_naptime = 1min
autovacuum_vacuum_threshold = 50
autovacuum_vacuum_scale_factor = 0.1  # 10%死元组就触发
```

---

## 磁盘空间管理

### 看磁盘占用

```sql
-- 数据库总大小
SELECT pg_size_pretty(pg_database_size('quant_db'));

-- 各表大小（含索引）
SELECT relname, pg_size_pretty(pg_total_relation_size(relid))
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC;

-- WAL日志大小
SELECT pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), '0/0'));
```

### 磁盘满了怎么办

**第一性原理：磁盘满了数据库会直接挂，比慢查询严重多了。**

1. **删旧数据**：按时间分区，DROP旧分区
2. **清WAL**：检查归档是否正常，`SELECT * FROM pg_stat_archiver;`
3. **清日志**：pg_log目录下的旧日志
4. **VACUUM FULL**：回收空间，但会锁表

---

## 备份恢复实战

### 日常备份

```bash
# 全量备份（每天一次）
pg_dump -U quant_super -d quant_db -F c -f backup_$(date +%Y%m%d).dump

# 只备份某张表
pg_dump -U quant_super -d quant_db -t kline_data -F c -f kline.dump
```

### 恢复演练（最重要！）

**第一性原理：备份不测试等于没备份。**

```bash
# 恢复到测试库
createdb test_restore
pg_restore -U quant_super -d test_restore backup_20261024.dump

# 验证数据完整性
SELECT count(*) FROM kline_data;
SELECT max(open_time) FROM kline_data;
```

### PITR（时间点恢复）

如果开启了WAL归档，可以恢复到任意时间点：
1. 恢复最近的全量备份
2. 重放WAL日志到指定时间点

---

## 性能调优参数

### 基础配置（单机16G内存参考）

```ini
# 内存相关
shared_buffers = 4GB          # 数据库缓存，约25%内存
effective_cache_size = 12GB    # 操作系统缓存预估，约75%内存
work_mem = 64MB               # 排序/哈希用的内存
maintenance_work_mem = 512MB  # VACUUM/建索引用

# 连接相关
max_connections = 100

# WAL相关
wal_buffers = 16MB
checkpoint_completion_target = 0.9

# 查询规划
random_page_cost = 1.1        # SSD的话设低一点
effective_io_concurrency = 20 # SSD可以高一点
```

### 怎么判断参数对不对

**第一性原理：不要凭感觉调参数，要有测量。**

1. 开慢查询日志
2. 跑典型业务SQL
3. 调一个参数
4. 再跑一遍对比

一次只调一个参数，不然你不知道哪个起了作用。

---

## 快速排障速查表

| 症状 | 第一步 | 第二步 | 常见根因 |
|------|--------|--------|----------|
| too many connections | 看连接数 | 找长连接 | 连接泄漏 / 没配连接池 |
| 慢查询 | EXPLAIN ANALYZE | 看走没走索引 | 缺索引 / 统计信息不准 |
| 锁等待 | 找阻塞源 | 杀阻塞进程 | 长事务 / 批量更新没分批 |
| 表越来越大 | 看n_dead_tup | 手动VACUUM | autovacuum没跑 / 长事务挡住了 |
| 磁盘满了 | 看各表大小 | 删旧数据 | 没分区 / WAL没归档 |
| 查询结果不对 | 看时区 | 看时区设置 | 时区不统一 |
| 备份失败 | 看报错 | 看权限 | 用户没有备份权限 |
| 连接突然断了 | 看日志 | 看网络 | 连接超时 / OOM被杀 |

---

## 思考清单

日常巡检过一遍：

- [ ] 连接数正常吗？
- [ ] 有慢查询吗？
- [ ] 有锁等待吗？
- [ ] 表膨胀率高吗？
- [ ] 磁盘空间够吗？
- [ ] 备份跑了吗？
- [ ] 上次恢复演练什么时候？
- [ ] autovacuum正常工作吗？
