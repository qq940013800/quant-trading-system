# Docker 后端恢复 与 OKX 联通排障沉淀（2026-10）

> 月份归档文件。记录 2026-10-28 前后 Docker 后端容器故障恢复、OKX API 网络被墙、
> 自定义路由未进官方镜像这一串踩坑，避免下次再花同样的时间。
>
> 关联：`project-todo-and-tech-debt.md` T6 / T7 / T8；`docs/RULES.md` Docker 运维铁律。

---

## 1. 事件摘要

1. 后端容器之前被手动搞挂过一次（root cause：手动 `docker rm` 而不是 compose down）。
2. 恢复时直接用了官方镜像，HTTP 200、PostgreSQL 连接正常，看起来"好了"。
3. 但前端开始报 OKX 相关接口 404 —— 才发现官方镜像里**没有我们自己写的 `account.py`、`okx_client.py`**。
4. 同时本地 `curl https://www.okx.com` 直接 `Failed to connect`（退出码 7），没有代理根本出不去。
5. 前端跑在独立容器 `quantdinger-frontend`（:8888）里，本地源码改动不会自动同步。

---

## 2. Docker 后端恢复步骤（本次实际走通的路径）

1. **不要手动 `docker rm` 正在运行的容器**。要恢复就用 `docker compose down` / `up -d`。
2. 容器挂掉后先 `docker logs <container>` 看最后 50 行，区分：
   - 进程崩了（看 traceback）
   - 数据库连不上（看 connection refused / timeout）
   - 端口被占（`netstat -ano | findstr :8000`）
3. 本次是直接用官方镜像拉起来：
   ```powershell
   docker compose pull
   docker compose up -d backend postgres redis
   docker compose ps
   curl http://localhost:8000/health   # 期望 200
   ```
4. 验证项（缺一不可）：
   - `/health` 返回 200
   - `/api/health/db` 返回数据库连接 OK
   - 前端容器 `quantdinger-frontend` 能访问后端（看浏览器 Network 面板）
5. **教训**：镜像"能起来"≠"我们的代码在里面"。健康检查只看进程和 DB，不看业务路由是否注册。

---

## 3. OKX API 被墙现象与排查思路

### 现象
```powershell
curl.exe -v https://www.okx.com/api/v5/public/time
# *   Trying ...
# * Failed to connect to www.okx.com port 443: Timed out / Connection refused
# curl: (7) Failed to connect ...
```
退出码 **7** = `CURLE_COULDNT_CONNECT`，不是 401 / 403 / DNS 错。

### 排查树
1. **先区分是 DNS 还是网络**：
   ```powershell
   nslookup www.okx.com        # 能解析 → DNS 没问题
   Test-NetConnection www.okx.com -Port 443
   ```
2. **换目标对比**：
   - `curl https://www.google.com` 也超时 → 整机出口受限
   - `curl https://www.baidu.com` 正常 → 只有境外站被墙
3. **代理是否生效**：
   ```powershell
   $env:HTTPS_PROXY="http://127.0.0.1:7890"
   curl.exe -v https://www.okx.com/api/v5/public/time
   ```
   走代理后能通 → 坐实是网络层被墙，不是代码问题。

### 处置方向
- 本地开发：走系统代理 / Clash 等，且必须让 Python `requests` 也读到 `HTTPS_PROXY`（不要只配浏览器）。
- 生产 / 服务器：把后端部署到能直连 OKX 的区域（如新加坡 / 美西），不要在国内机器上直连 OKX。
- 在代理没通之前，**不要在 TODO 里把"OKX 联通"标成 ✅**，否则下次换个网络环境就全是假阳性。

---

## 4. 自定义路由在官方镜像缺失（本次最大坑）

### 现象
- 后端容器起来了，`/health` 200。
- 前端调 `/api/okx/account`、`/api/okx/place-order` 一律 404。
- 本地 `python app.py` 跑同一份代码，路由是通的。

### 根因
- 我们直接 `pull` 了官方镜像，里面的 `app/routers/` 是官方版本，**没有我们新增的 `account.py` / `okx_client.py`**。
- 容器也没有挂 volume（`docker inspect` 看 `Mounts`），所以本地改文件不会进去。

### 正确做法（Dockerfile 必须满足）
```dockerfile
# 必须把我们自己写的 app/ 整体 COPY 进去，而不是只 COPY requirements.txt
COPY app/ /app/app/
# 路由注册在 app/register.py（或 blueprints 入口），确保 import 到我们的 okx 路由
```
### 验证步骤（下次 build 完必跑）
```powershell
docker exec <backend> python -c "from app.register import bp; print([r.path for r in bp.deferred_functions])"
# 或直接：
curl http://localhost:8000/openapi.json | Select-String "okx"
```
看到 `/api/okx/...` 才算路由真的注册了。

### 教训（写入 RULES）
- **"镜像健康"不等于"业务路由齐全"**。健康检查只看进程，不看业务面。
- 每次重新 build 镜像后，必须用 `openapi.json` 或 `docker exec` 列一下注册路由，对比本地有没有少。
- 不要在官方镜像上 `docker cp` 临时补文件 —— 重启就丢，必须走 Dockerfile。

---

## 5. 前端容器与本地源码同步问题

- 前端跑在 `quantdinger-frontend`（:8888）。
- 本地改 `index.html / js/app.js / css/main.css` 后，容器里的文件不会变。
- 三种处置（按推荐顺序）：
  1. **改 Dockerfile / docker-compose.yml 挂 volume**：`./frontend:/usr/share/nginx/html`，开发期热更新。
  2. **每次改完 rebuild 前端镜像**：`docker compose up -d --build frontend`。
  3. **临时 `docker cp`**：只应急，重启 / 重新 build 后会丢，不推荐。
- 浏览器端再强刷一次（Ctrl+Shift+R），别被旧 JS 缓存骗了。

---

## 6. 一句话复盘

> "Docker 容器起来了"和"我们写的代码在跑"是两件事；
> "API 在我机器上能通"和"API 在生产网络下能通"也是两件事。
> 任何一条没单独验证，都不能写进 ✅。
