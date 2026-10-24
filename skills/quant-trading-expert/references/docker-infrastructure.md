# Docker 容器化部署与运维指南

> 量化交易系统的基础设施层：容器化是保证环境一致性、可复现性和快速灾备的关键。

## 目录

1. [为什么量化系统需要Docker](#为什么量化系统需要docker)
2. [核心服务架构](#核心服务架构)
3. [PostgreSQL 容器配置](#postgresql-容器配置)
4. [Redis 缓存配置](#redis-缓存配置)
5. [后端API容器](#后端api容器)
6. [网络与安全](#网络与安全)
7. [数据持久化](#数据持久化)
8. [健康检查与自愈](#健康检查与自愈)
9. [资源限制](#资源限制)
10. [常见问题速查](#常见问题速查)

---

## 为什么量化系统需要Docker

### 第一性原理

量化交易系统最危险的不是代码有bug，而是**"在我电脑上是好的"**——实盘环境和回测环境不一致导致策略表现完全不同。

Docker解决的核心问题：
1. **环境一致性**：开发、测试、生产环境完全一致
2. **快速灾备**：一台机器挂了，另一个地方几分钟就能拉起整套系统
3. **依赖隔离**：不同Python版本、不同库版本不冲突
4. **版本可追溯**：每个镜像有明确的版本标签

### 反模式

- ❌ 直接在本机装Python+PostgreSQL → 环境漂移，半年后谁也不知道装了什么
- ❌ 用虚拟机跑全套 → 太重，启动慢，资源浪费
- ❌ 手动配置每台服务器 → 不可复现，新人接手一脸懵

---

## 核心服务架构

### 标准量化系统的Docker服务清单

| 服务 | 镜像 | 用途 | 端口 | 必选 |
|------|------|------|------|------|
| PostgreSQL | postgres:16-alpine | 核心数据存储 | 5432（内部） | ✅ |
| Redis | redis:7-alpine | 行情缓存 + Celery broker | 6379（内部） | ✅ |
| 后端API | 自建Dockerfile | Flask业务逻辑 | 8000/5000 | ✅ |
| Celery Worker | 同后端镜像 | 异步任务执行 | — | 可选 |
| Celery Beat | 同后端镜像 | 定时任务调度 | — | 可选 |
| 前端Nginx | nginx:alpine | 静态文件 + 反向代理 | 80/443 | 可选 |
| Prometheus | prom/prometheus | 指标监控 | 9090 | 可选 |
| Grafana | grafana/grafana | 可视化看板 | 3000 | 可选 |

### 网络拓扑

```
                    ┌─────────────────┐
                    │   外部访问      │
                    │  (Nginx/HTTPS) │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   quant_internal │  ← 内部网络
                    │    bridge网      │
                    └──┬─────┬─────┬──┘
                       │     │     │
              ┌────────▼┐ ┌──▼───┐ ┌─▼────────┐
              │PostgreSQL│ │Redis │ │ 后端API   │
              │  :5432   │ │:6379 │ │  :8000   │
              └──────────┘ └──────┘ └──────────┘
```

**关键原则**：数据库端口只在内部网络暴露，不映射到主机端口。外部只能通过API网关访问。

---

## PostgreSQL 容器配置

### 生产级配置模板

```yaml
postgres:
  image: postgres:16-alpine
  container_name: quant_postgres
  restart: unless-stopped
  networks:
    - quant_internal
  volumes:
    - pg_data:/var/lib/postgresql/data
    - ./db/init:/docker-entrypoint-initdb.d:ro  # 初始化SQL
  environment:
    POSTGRES_DB: quant_db
    POSTGRES_USER: quant_super
    POSTGRES_PASSWORD: ${PG_SUPER_PASSWORD}
    TZ: Asia/Shanghai
  expose:
    - "5432"  # 只内部暴露，不映射到主机
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U quant_super -d quant_db"]
    interval: 10s
    timeout: 5s
    retries: 5
  deploy:
    resources:
      limits:
        cpus: '2'
        memory: 2G
  security_opt:
    - no-new-privileges:true
```

### 为什么用alpine版本

- 体积小：~80MB vs 完整版~400MB
- 启动快：秒级启动
- 安全攻击面小：安装的包少，漏洞少
- 性能足够：PostgreSQL本身性能瓶颈不在OS层

### 初始化脚本机制

`docker-entrypoint-initdb.d/` 目录下的SQL脚本会在**第一次启动时自动执行**。

注意：
- 只在数据卷为空时执行
- 按文件名顺序执行（数字前缀控制顺序）
- 生产环境用 `CREATE TABLE IF NOT EXISTS` 保证幂等

---

## Redis 缓存配置

### 量化系统的Redis用途

1. **行情数据缓存**：K线数据短期缓存，减少API调用
2. **Celery broker**：异步任务队列
3. **会话存储**：用户登录session
4. **实时状态**：策略运行状态、账户快照

### 生产配置

```yaml
redis:
  image: redis:7-alpine
  container_name: quant_redis
  restart: unless-stopped
  networks:
    - quant_internal
  volumes:
    - redis_data:/data
  expose:
    - "6379"
  command: >
    redis-server 
    --appendonly yes 
    --maxmemory 512mb 
    --maxmemory-policy allkeys-lru
  healthcheck:
    test: ["CMD", "redis-cli", "ping"]
    interval: 10s
    timeout: 3s
    retries: 5
```

### 关键参数说明

| 参数 | 值 | 说明 |
|------|-----|------|
| `appendonly` | yes | AOF持久化，重启不丢数据 |
| `maxmemory` | 512mb | 内存上限，防止OOM |
| `maxmemory-policy` | allkeys-lru | 内存满时LRU淘汰最久未用的key |

**为什么用allkeys-lru而不是noeviction？**
- 行情缓存是可重建的，不是核心数据
- Redis挂了最多慢一点，不能因为缓存满了就拒绝写入

---

## 网络与安全

### 网络设计原则

1. **内部网络隔离**：所有服务放在同一个内部bridge网络
2. **最小暴露面**：只有Nginx/API网关暴露端口
3. **数据库不暴露公网**：PostgreSQL/Redis只内部访问
4. **防火墙分层**：云安全组 → Docker网络 → 应用层认证

### 安全最佳实践

```yaml
# 所有容器统一加
security_opt:
  - no-new-privileges:true  # 禁止提权

# 不要用root用户跑容器
user: "1000:1000"

# 只读文件系统（如果支持）
read_only: true
tmpfs:
  - /tmp
```

---

## 数据持久化

### 数据卷设计

```yaml
volumes:
  pg_data:        # PostgreSQL数据文件
  redis_data:     Redis AOF持久化文件
  logs_data:      应用日志
```

### 备份策略（第一性原理）

**数据库备份的本质是：假设磁盘会坏，假设服务器会丢。**

| 备份类型 | 频率 | 保留 | 工具 |
|----------|------|------|------|
| 全量备份 | 每天 | 7天 | `pg_dump` |
| WAL归档 | 实时 | 3天 | PostgreSQL WAL |
| 配置备份 | 每次变更 | 永久 | Git仓库 |

**3-2-1原则**：
- 3份数据副本
- 2种不同介质
- 1份异地

---

## 健康检查与自愈

### 为什么需要健康检查

Docker的`restart: always`只是"进程挂了就重启"，但**进程活着不代表服务正常**。

健康检查的价值：
- 数据库连不上时，自动重启
- 依赖服务没起来时，延迟启动
- 编排系统可以基于健康状态做调度

### 三层健康检查

```
第一层：进程级 → 容器是否在运行（docker自动）
第二层：TCP级 → 端口是否在监听
第三层：应用级 → 真正能处理请求了吗
```

PostgreSQL的`pg_isready`就是第三层——它不仅检查端口，还真正执行了一次连接测试。

---

## 常见问题速查

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| 后端连不上数据库 | PostgreSQL还没启动完成 | 加healthcheck + depends_on condition |
| 容器启动后立刻退出 | 环境变量没设置 | 检查.env文件，用`:?`语法强制 |
| 数据卷权限错误 | 容器内用户和宿主机UID不匹配 | 统一用固定UID:GID |
| Docker Hub拉镜像慢 | 国内网络问题 | 配置镜像加速器 |
| 内存OOM | 没设资源限制 | deploy.resources.limits |
| 时区不对 | 容器默认UTC | 加TZ环境变量 |
| 初始化SQL没执行 | 数据卷不是空的 | 只有第一次启动才执行初始化 |
| Celery连不上Redis | 服务名不对 | 用服务名`redis`而不是`localhost` |

---

## 思考清单

部署前过一遍：

- [ ] 数据库端口只内部暴露了吗？
- [ ] SECRET_KEY是随机生成的吗？
- [ ] 数据卷挂载正确了吗？
- [ ] 健康检查配了吗？
- [ ] 资源限制设了吗？
- [ ] 时区设成Asia/Shanghai了吗？
- [ ] 备份策略想好了吗？
- [ ] 灾备方案有了吗？
