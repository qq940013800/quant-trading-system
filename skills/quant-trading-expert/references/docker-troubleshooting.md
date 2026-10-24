# Docker 容器排障实战手册

> 第一性原理：容器不会无缘无故挂，挂了一定有原因。从现象倒推根因，不要瞎猜。

## 目录

1. [排障第一原则](#排障第一原则)
2. [启动失败排查](#启动失败排查)
3. [运行异常排查](#运行异常排查)
4. [网络问题排查](#网络问题排查)
5. [性能问题排查](#性能问题排查)
6. [数据卷问题排查](#数据卷问题排查)
7. [日志分析技巧](#日志分析技巧)
8. [快速排障速查表](#快速排障速查表)

---

## 排障第一原则

### 不要猜，要看证据

```
现象 → 日志 → 进程 → 网络 → 资源 → 根因
```

每一步都有明确的证据，不要跳步。

### 黄金命令

```bash
# 1. 看容器状态
docker ps -a

# 2. 看日志（最重要）
docker logs --tail 100 quantdinger-backend
docker logs -f --since 10m quantdinger-backend  # 实时看最近10分钟

# 3. 进入容器内部
docker exec -it quantdinger-backend /bin/bash

# 4. 看容器资源占用
docker stats --no-stream

# 5. 看容器详细配置
docker inspect quantdinger-backend
```

---

## 启动失败排查

### 症状：容器启动后立刻退出

**排查步骤：**

```bash
# 第一步：看退出码
docker inspect quantdinger-backend --format='{{.State.ExitCode}}'
```

| 退出码 | 含义 | 常见原因 |
|--------|------|----------|
| 0 | 正常退出 | 主进程执行完就退出了（比如写了个脚本跑完就结束） |
| 1 | 通用错误 | 应用内部异常，看日志 |
| 137 | OOM被杀 | 内存超了，被Linux OOM Killer干掉 |
| 139 | 段错误 | 程序崩溃，native代码问题 |
| 143 | SIGTERM | 收到终止信号正常退出 |
| 255 | 未知错误 | SSH连接失败之类 |

### 症状：健康检查一直不通过

**排查步骤：**

```bash
# 1. 手动在容器内执行健康检查命令
docker exec quant_postgres pg_isready -U quant_super -d quant_db

# 2. 看健康检查日志
docker inspect quant_postgres --format='{{json .State.Health}}' | python -m json.tool

# 3. 常见原因：
#    - 依赖的服务还没起来（PostgreSQL还在初始化）
#    - 健康检查命令写错了
#    - 服务起来了但端口还没监听
#    - 认证失败
```

### 症状：环境变量没生效

**第一性原理：容器里的环境变量和宿主机不是一回事。**

```bash
# 进容器看真实的环境变量
docker exec quantdinger-backend env | grep DATABASE_URL

# 常见坑：
# 1. .env文件写错了位置
# 2. docker-compose.yml里environment覆盖了.env
# 3. Dockerfile里的ENV和运行时的ENV搞混了
# 4. 变量名打错了
```

---

## 运行异常排查

### 症状：后端连不上数据库

**第一性原理：网络问题要分层排查。**

```
容器内 → 容器网络 → 宿主机网络 → 目标容器
```

**排查步骤：**

```bash
# 第一步：进后端容器，测试网络
docker exec -it quantdinger-backend /bin/bash

# 在容器内：
ping postgres                    # DNS解析通不通
telnet postgres 5432             # 端口通不通
psql -h postgres -U quant_super  # 能不能连上
```

**常见原因：**

| 层级 | 问题 | 解决方案 |
|------|------|----------|
| DNS | 服务名解析失败 | 确认两个容器在同一个docker网络 |
| 网络 | 端口不通 | 确认postgres容器的expose配置 |
| 认证 | 密码不对 | 确认环境变量里的密码一致 |
| 状态 | 数据库还没就绪 | 加depends_on + healthcheck |
| 版本 | PostgreSQL版本不兼容 | 确认驱动版本和数据库版本匹配 |

### 症状：Redis连接超时

```bash
# 1. 确认Redis容器在运行
docker ps | grep redis

# 2. 确认在同一个网络
docker network inspect quant_internal

# 3. 在后端容器里测试
docker exec quantdinger-backend redis-cli -h redis ping
```

---

## 网络问题排查

### 症状：容器能访问外网，但访问不了某个API

**第一性原理：网络问题要分三层——容器内、Docker网络、宿主机。**

```bash
# 1. 容器内能不能DNS解析
docker exec quantdinger-backend nslookup api.binance.com

# 2. 容器内能不能连通
docker exec quantdinger-backend curl -I https://api.binance.com

# 3. 宿主机能不能连通
curl -I https://api.binance.com
```

**常见原因：**

- DNS配置问题 → 加`--dns 8.8.8.8`
- 代理问题 → 检查HTTP_PROXY环境变量
- 防火墙 → 宿主机防火墙挡了
- MTU问题 → Docker网络MTU和VPN冲突

### 症状：两个容器互相访问不了

**第一性原理：Docker网络是隔离的，不在同一个网络就互相看不见。**

```bash
# 看所有网络
docker network ls

# 看某个网络里有哪些容器
docker network inspect quant_internal

# 两个容器必须在同一个网络里
```

---

## 性能问题排查

### 症状：容器CPU占用高

```bash
# 1. 看哪个容器占CPU高
docker stats

# 2. 看容器里哪个进程占CPU高
docker exec quantdinger-backend top -b -n 1

# 3. 用py-spy抓Python进程的栈（如果是Python应用）
docker exec quantdinger-backend py-spy top -p 1
```

### 症状：容器内存持续增长

**第一性原理：内存泄漏不是"可能"，是"一定会有"，只是时间问题。**

```bash
# 1. 看内存趋势
docker stats

# 2. 看容器内存详情
docker inspect quantdinger-backend --format='{{.State.MemoryStats}}'

# 3. Python应用内存泄漏排查
docker exec quantdinger-backend python -m tracemalloc
```

**常见原因：**
- 内存泄漏：对象只创建不释放
- 缓存膨胀：Redis没设maxmemory
- 连接泄漏：数据库连接没关
- 日志膨胀：日志写到内存里了

### 症状：磁盘空间满了

```bash
# 1. 看Docker占了多少空间
docker system df

# 2. 清理无用资源（谨慎！）
docker system prune -a  # 删掉所有未运行的容器和镜像

# 3. 看哪个容器的日志最大
docker inspect --format='{{.LogPath}}' quantdinger-backend
```

---

## 数据卷问题排查

### 症状：数据没保存，容器重启后丢了

**第一性原理：Docker容器本身是临时的，数据必须挂载到数据卷。**

```bash
# 1. 看容器挂载了哪些卷
docker inspect quant_postgres --format='{{json .Mounts}}'

# 2. 确认数据卷是命名卷还是绑定挂载
# 命名卷：docker管理，存在/var/lib/docker/volumes/
# 绑定挂载：挂载宿主机的具体目录
```

### 症状：数据卷权限不对

**第一性原理：容器内的用户和宿主机的UID不是同一个人。**

```bash
# 常见错误：容器内用root创建的文件，宿主机普通用户读不了
# 解决方案：统一UID:GID，或者用named volume而不是bind mount
```

---

## 日志分析技巧

### 高效看日志

```bash
# 只看最近的错误
docker logs quantdinger-backend 2>&1 | grep -i error

# 实时跟踪，过滤关键字
docker logs -f quantdinger-backend 2>&1 | grep -E "error|warning|exception"

# 看时间范围内的日志
docker logs --since 2026-10-24T08:00:00 --until 2026-10-24T09:00:00 quantdinger-backend
```

### 日志太多怎么办

**第一性原理：日志是给人看的，不是给机器存的。太多了等于没有。**

1. 设日志大小限制：`max-size: "10m", max-file: "3"`
2. 用ELK/Loki收集集中日志
3. 分级日志：DEBUG/INFO/WARN/ERROR，生产环境只看WARN以上

---

## 快速排障速查表

| 症状 | 第一步 | 第二步 | 常见根因 |
|------|--------|--------|----------|
| 容器启动后立刻退出 | `docker logs <容器>` | `docker inspect`看退出码 | 环境变量缺失 / 配置错误 / 依赖没起来 |
| 健康检查不通过 | 手动执行健康检查命令 | 看服务端口是否监听 | 依赖服务未就绪 / 命令写错 |
| 连不上数据库 | `ping postgres` | `telnet postgres 5432` | 不在同一个网络 / 密码不对 / DB没就绪 |
| 连不上Redis | `redis-cli -h redis ping` | 看Redis容器状态 | 网络隔离 / 密码不对 |
| CPU飙高 | `docker stats` | `top`进容器看进程 | 死循环 / 突发流量 / 泄漏 |
| 内存飙高 | `docker stats` | 看内存趋势 | 内存泄漏 / 缓存膨胀 |
| 磁盘满 | `docker system df` | 看日志大小 | 日志没轮转 / 镜像堆积 |
| 网络不通 | `nslookup` | `curl`测试 | DNS / 代理 / 防火墙 |
| 数据丢了 | `docker inspect`看Mounts | 确认卷挂载 | 没挂卷 / 挂错路径 |
| 时间不对 | 进容器`date` | 看TZ环境变量 | 容器默认UTC，没设时区 |

---

## 思考清单

遇到问题过一遍：

- [ ] 先看日志了吗？
- [ ] 容器在同一个网络里吗？
- [ ] 环境变量都对吗？
- [ ] 依赖服务都起来了吗？
- [ ] 资源（CPU/内存/磁盘）够吗？
- [ ] 数据卷挂载对了吗？
- [ ] 时区设了吗？
