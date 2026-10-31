# 量化交易系统 · 错误日志（ERROR_LOG）

> 最后更新：2026-10-31 ｜ 状态：滚动登记
>
> 日志格式：`时间 | 错误类型 | 现象 | 根因 | 修复方案 | 预防措施 | 状态 | 证据链接`
>
> 本文件只登记**真实踩过的坑**，每条都有仓库证据或线上报错原文。新坑当天追加，不攒着。
> 严重级：P0 = 阻塞实盘/主流程不可用；P1 = 可用但有明显副作用；P2 = 体验或备份类。

---

## 一、汇总表

| 编号 | 日期 | 错误类型 | 一句话现象 | 严重级 | 状态 |
|------|------|----------|------------|--------|------|
| E001 | 2026-10-28 | 部署 / 认知偏差 | 手动 `docker rm` 后用官方镜像重启，自研 `account.py` / `okx_client.py` 路由全部 404 | P1 | 临时绕过（需 rebuild 镜像才真正闭环） |
| E002 | 2026-10-28 | 配置 / 环境变量 | `POSTGRES_PASSWORD` 与 `DATABASE_URL` 密码不一致，且 `backend.env` 实际是目录不是文件，后端连不上 DB | P0 | 待验证（仓库内已发现错位，未实测修复） |
| E003 | 2026-10-27 | 部署 / 配置 | 前端 nginx 反代 `backend:5000`，但容器网络里没有 `backend` DNS 别名，`/api/*` 全 502 | P0 | 临时绕过（根因已定位，compose 未改） |
| E004 | 2026-10-28 | 认知偏差 | 本地改了 `frontend-pro/index.html`，浏览器 :8888 看到的还是旧代码（前端容器静态镜像、没挂 volume） | P1 | 临时绕过（靠 `docker cp` + Ctrl+Shift+R） |
| E005 | 2026-10-28 | 代码契约 / 外部 API | OKX 下单返回 `"All operations failed"`，疑似 `tdMode` 硬编码 cash / 最小下单量 / clOrdId 问题 | P0 | 待验证（未用最小手数复现） |
| E006 | 2026-10-28 | 网络 | `git push origin` GitHub 超时 `curl 28 (Operation timed out)`，Gitee 正常 | P2 | ✅ 已修复（2026-10-31：merge 远程占位初始提交后 861dc24，GitHub+Gitee 双端一致） |
| E007 | 2026-10-28 | 网络 | 本地 `curl https://www.okx.com` 退出码 7 `CURLE_COULDNT_CONNECT`，不走代理直连被墙 | P0 | ✅ 已解除（2026-10-31：直连恢复 200；容器内经 Docker NAT 亦通） |
| E008 | 2026-10-31 | 网络 / 部署 | GitHub 远端存在无关 `Initial commit`（bd662ff）导致 `push rejected (fetch first)`；系统代理（127.0.0.1:7890）已启用但环境变量未设，使 curl/docker 误判"被墙" | P2 | ✅ 已修复（`--allow-unrelated-histories -X ours` merge 后双端一致；代理经 CONNECT 验证可转发 wss） |
| E009 | 2026-10-31 | 代码契约 / 认知偏差 | 自建后端 :5001 的 `/api/market/ticker`、`/market/kline` 404；前端 dev-token 假登录导致全部业务请求 401 → 自动登出，页面永远停登录页 | P1 | ✅ 已修复（容器 docker cp 全量同步本地 app 代码；前端改真实自动登录 + risk 路径改向） |

---

## 二、逐条详情

### E001 ｜ 手动 `docker rm` + 官方镜像重启，自研路由全丢

**现象（报错原文）**
- 后端容器起来后 `GET http://localhost:8000/health` 返回 200，`/api/health/db` 也正常。
- 前端调 `/api/okx/account`、`/api/okx/place-order` 一律 **404**。
- 本地 `python app.py` 跑同一份代码，路由是通的。
- `docker logs` 无 traceback，进程看起来完全健康。

**根因（5 Why）**
1. 为什么 404？→ 官方镜像里 `app/routers/` 是官方版本。
2. 为什么官方镜像里没有我们的路由？→ 我们之前手动 `docker stop` + `docker rm` 把自研容器删了，恢复时直接 `docker compose pull` 拉了 GHCR 官方镜像，**没有走本地 `docker compose build`**。
3. 为什么会以为拉官方镜像就行？→ 健康检查 `/health` 200、DB 连接 OK，"看起来好了"。
4. 为什么健康检查没拦住？→ 健康检查只验证进程活着 + DB 可连，**不验证业务路由是否注册**。
5. 为什么连验证步骤都没有？→ 没有一条"build 后必跑 openapi 路由清单"的铁律。
- **根**：把"容器进程健康"等同于"业务代码在跑"，健康检查覆盖面太窄。

**修复步骤（PowerShell，照抄）**
```powershell
# 1. 不要再用官方镜像，本地 build 带自研路由的后端镜像
cd D:\Trader
docker compose -f docker-compose.build.yml build backend
docker compose -f docker-compose.build.yml up -d backend

# 2. build 完必跑：确认自研路由真的注册进容器
docker exec quantdinger-backend python -c "import urllib.request,json; d=json.load(urllib.request.urlopen('http://localhost:5000/openapi.json')); print([p for p in d['paths'] if 'okx' in p or 'account' in p])"
# 期望输出里能看到 /api/account/place-order、/api/okx/... 才算通过

# 3. 禁止 docker cp 临时补文件（重启就丢）
```

**预防措施（30 秒识别）**
- 任何一次 `docker compose pull` / 换镜像 / 重启后端后，第一件事：
  `curl http://localhost:5000/openapi.json | Select-String "okx"`
  没命中就是镜像里没我们的代码，**不要**去前端、不要去查 DB。

**关联文件**
- `../skills/quant-trading-expert/references/docker-okx-debug-2026-10.md`（第 2、4 节）
- `./frontend-bug-list-20261028.md`（第三节"已知限制"：`/api/okx/accounts` 404 是因为 account.py / okx_client.py 是自研、官方镜像没有）
- `../backend_api_python/app/routes/account.py`（第 150 行 `@bp.route('/account/place-order')`）

**证据等级**：【临时绕过】—— TODO.md 标记 ✅ 容器恢复，但根因（官方镜像缺自研路由）需要 rebuild 本地镜像才能真正闭环，未在仓库内见到 rebuild 后的 openapi 验证记录。

---

### E002 ｜ `POSTGRES_PASSWORD` 与 `DATABASE_URL` 错位 + `backend.env` 是目录

**现象（仓库实查到的错位）**
- 后端容器日志连 DB 报 `password authentication failed for user "quantdinger"`，或连不上 `postgres:5432`。
- 三个文件里的"密码"互相对不上：

| 文件 | 关键行 | 值 |
|------|--------|----|
| `D:\Trader\.env`（项目根） | `POSTGRES_PASSWORD=f0305a79f750eb324df59b8d2c483e55` | postgres 容器超级密码 = `f0305a79...` |
| `D:\Trader\backend_api_python\.env` | `DATABASE_URL=postgresql://quantdinger:quantdinger123@postgres:5432/quantdinger` | 后端连接串里密码 = `quantdinger123` |
| `docker-compose.ghcr.yml` 第 59 行 | `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-quantdinger123}` | postgres 容器默认密码 `quantdinger123`，可被根 `.env` 覆盖成 `f0305a79...` |

- 代码侧只读 `DATABASE_URL`，**根本不读 `POSTGRES_PASSWORD`**：
  - `backend_api_python/app/utils/db_postgres.py:81` → `return os.getenv('DATABASE_URL', '').strip()`
  - 同文件第 143 行：`raise RuntimeError("DATABASE_URL environment variable is not set.")`
- 另一个坑：`D:\Trader\backend.env` **不是文件，是目录**（里面只有 `env.example`）。而 `docker-compose.ghcr.yml` 第 176 行写的是 `- ./backend.env:/app/.env` —— Docker 把一个目录 bind-mount 到 `/app/.env`，会覆盖掉镜像里本来的 `.env` 文件内容。

**根因（5 Why）**
1. 为什么密码错？→ postgres 容器用了根 `.env` 的 `POSTGRES_PASSWORD=f0305a79...`，但后端 `DATABASE_URL` 写死 `quantdinger123`。
2. 为什么两个密码不一样？→ 根 `.env` 是手动改过的随机密码（看长度像 `secrets.token_hex`），`backend_api_python/.env` 是从 `env.example` 复制来的默认值，没人同步。
3. 为什么 `backend.env` 变成了目录？→ 之前某次 `curl -o backend.env ...` 失败或手滑 `mkdir backend.env`，没人发现；compose 文件却按"文件"去挂载。
4. 为什么没启动就报错？→ postgres 第一次初始化用 `f0305a79` 写进 `pg_data` volume，之后即使改 `.env`，已初始化的 postgres 不会改密码（PG 只在空数据目录时跑 initdb）。
5. 为什么没在 CI 起一个"变量一致性检查"？→ 仓库里有 `scripts/check_production_config.py`，但它只把 `quantdinger123` 当弱密码黑名单（第 15 行），**没有跨文件比对 `POSTGRES_PASSWORD` 和 `DATABASE_URL` 里的密码段**。

**修复步骤（PowerShell，照抄）**
```powershell
cd D:\Trader

# 1. 先看 backend.env 到底是文件还是目录（实测是目录）
Get-Item .\backend.env -Force | Select-Object Mode, FullName

# 2. 统一密码：让 DATABASE_URL 里的密码 = 根 .env 里的 POSTGRES_PASSWORD
#    假设统一用 f0305a79f750eb324df59b8d2c483e55，编辑 backend_api_python/.env：
#    DATABASE_URL=postgresql://quantdinger:f0305a79f750eb324df59b8d2c483e55@postgres:5432/quantdinger

# 3. 把 backend.env 目录改成真正的文件（或改用 ./backend_api_python/.env 挂载）
#    方案 A：直接让 ghcr.yml 挂 backend_api_python/.env（和 docker-compose - 副本.yml 一致）
#    方案 B：把 backend.env 目录里的 env.example 复制成 backend.env 文件

# 4. 如果 pg_data 已经用旧密码初始化过，必须清 volume 重建（会丢数据！先备份）
#    docker compose down -v postgres   # 危险操作，确认备份后再跑

# 5. 启动后验证
docker compose -f docker-compose.ghcr.yml up -d postgres backend
docker exec quantdinger-backend python -c "from app.utils.db_postgres import get_conn; print(get_conn().server_version)"
```

**预防措施（30 秒识别）**
- 启动后端后第一件事：
  `docker exec quantdinger-backend python -c "import os,u; print(os.getenv('DATABASE_URL','')[:40])"`
  看一眼连接串里的密码段是否和 `D:\Trader\.env` 的 `POSTGRES_PASSWORD` 一致。
- 把 `backend.env` 这个名字永远当**文件**用，看到 `Mode d----` 立刻报警。

**关联文件**
- `../.env`（根，POSTGRES_PASSWORD=f0305a79...）
- `../backend_api_python/.env`（DATABASE_URL=...quantdinger123...）
- `../docker-compose.ghcr.yml`（第 52–78 行 postgres 服务；第 176 行 `./backend.env:/app/.env`）
- `../backend_api_python/app/utils/db_postgres.py`（第 81、143 行只读 DATABASE_URL）
- `../backend_api_python/scripts/check_production_config.py`（第 15 行弱密码黑名单）

**证据等级**：【待验证】—— 仓库内已三处实查到密码错位 + `backend.env` 是目录，但未在本地跑通"改完后真的能连"。PG volume 是否需要 `down -v` 重建**未验证**。

---

### E003 ｜ Nginx upstream 502：前端容器里 `backend` 这个 DNS 名不存在

**现象（报错原文）**
- 浏览器 `http://localhost:8888` 打开，登录页骨架正常，但所有 `/api/*` 返回 502：
  ```
  GET /api/auth/security-config → 502 Bad Gateway
  POST /api/auth/login          → 502 Bad Gateway
  ```
- nginx 错误日志（`docker logs quantdinger-frontend --tail 50`）：
  ```
  2026/10/27 16:15:22 [error] 37#37: *438 backend could not be resolved (3: Host not found),
        client: 172.18.0.1, request: "GET /api/auth/security-config ..."
  ```
- 直连后端 `http://localhost:5000/api/health` 返回 200，后端本身没病。
- 前端容器内实测：
  - `docker exec quantdinger-frontend getent hosts quantdinger-backend` → `172.18.0.14` ✅
  - `docker exec quantdinger-frontend getent hosts backend` → 空 ❌

**根因（5 Why）**
1. 为什么 502？→ nginx 把 `proxy_pass http://backend:5000` 发给 Docker 内置 DNS（127.0.0.11），DNS 查不到 `backend` 这个名字。
2. 为什么查不到？→ nginx 镜像里 `default.conf` 写死 `set $backend_upstream http://backend:5000;`，设计假设是"同 compose 网络里 service 名就叫 backend"。
3. 为什么实际网络里没有 `backend`？→ 看 `docker-compose.ghcr.yml` 第 185 行，service key 确实叫 `backend`，正常情况下 compose 会自动把 service key 注册成 DNS 别名。但实际跑的容器网络是 `trader_quantdinger-network`（见 frontend-bug-list 第 17 行 `docker inspect`），不是 compose 文件里写的 `quantdinger-network`；且容器 `quantdinger-backend` 是单独 `docker run` 或被手动起过，没和 frontend 在同一个 compose project 里。
4. 为什么容器别名对不上？→ `container_name: quantdinger-backend` 是容器名，`backend` 是 compose service 名；只有两个容器由同一份 `docker compose up` 一起拉起，service 名才会进同一网络的 DNS。
5. 为什么没在前端容器里先 `getent hosts` 一下？→ 排障顺序错了，先去查后端代码，再查 nginx，最后才 DNS。

**修复步骤（PowerShell，照抄）**
```powershell
# 方案 A（推荐）：在 frontend 容器里临时改 nginx，指向真实存在的容器别名
docker exec quantdinger-frontend sh -c "sed -i 's|http://backend:5000|http://quantdinger-backend:5000|g' /etc/nginx/conf.d/default.conf && nginx -t && nginx -s reload"

# 方案 B（根治）：在 docker-compose 给 backend 服务加 network alias，让 backend 这个名字永远能解析
#   在 backend 服务下加：
#   networks:
#     quantdinger-network:
#       aliases:
#         - backend
#   然后 docker compose up -d --force-recreate backend frontend

# 验证
docker exec quantdinger-frontend getent hosts backend   # 必须返回 IP
curl http://localhost:8888/api/auth/security-config    # 期望 200，不再是 nginx HTML
```

**预防措施（30 秒识别）**
- 前端 502 第一反应：`docker exec quantdinger-frontend getent hosts backend`
  - 空 → DNS/别名问题，不要去翻后端代码。
  - 有 IP 但还 502 → 再去看后端日志。

**关联文件**
- `./frontend-bug-list-20261028.md`（P0-1 完整复现 + nginx 日志原文）
- `./TODO.md`（2026-10-28 重排 P0-1：根因已定位，未修复）
- `../docker-compose.ghcr.yml`（第 185 行 `backend:` service；第 397 行 `BACKEND_URL=${BACKEND_URL:-http://backend:5000}`）
- `../docker-compose - 副本.yml`（同结构，第 185、446 行）

**证据等级**：【临时绕过】—— 根因已写进 TODO.md，但 compose 里没加 network alias，nginx 配置也没改；当前如果重启 frontend 容器，问题会复现。

---

### E004 ｜ 本地改了前端代码，浏览器 :8888 还是旧页面

**现象**
- 本地编辑 `D:\Trader\frontend-pro\index.html`、`js/app.js`、`css/main.css`，保存。
- 浏览器强刷 Ctrl+Shift+R，页面行为和旧版一模一样，新加的 div / 新函数不生效。
- `node --check js/app.js` 无语法错。

**根因（5 Why）**
1. 为什么浏览器看到旧代码？→ 前端容器 `quantdinger-frontend` 里的 `/usr/share/nginx/html/` 是**构建时烤进镜像的静态文件**，没有 volume 挂到本地 `./frontend-pro`。
2. 为什么没挂 volume？→ GHCR 官方前端镜像 `ghcr.io/openbyteinc/quantdinger-frontend` 是给生产用的，compose 里 frontend 服务段没有 `volumes:` 映射源码目录。
3. 为什么会以为"本地改了就生效"？→ 把 Docker 容器当成"运行中的本机进程"，忽略了容器文件系统是镜像快照。
4. 为什么连 `docker cp` 都不知道？→ 没有"改前端必须 docker cp 或 rebuild"的 SOP。
5. 为什么浏览器缓存还在叠 buff？→ 即使 docker cp 了，nginx 不发 `Cache-Control: no-cache`，浏览器继续用旧 JS。

**修复步骤（PowerShell，照抄）**
```powershell
cd D:\Trader

# 临时方案：把改好的文件拷进容器
docker cp frontend-pro/index.html quantdinger-frontend:/usr/share/nginx/html/pro/index.html
docker cp frontend-pro/js/app.js  quantdinger-frontend:/usr/share/nginx/html/pro/js/app.js
docker cp frontend-pro/css/main.css quantdinger-frontend:/usr/share/nginx/html/pro/css/main.css

# 浏览器端：Ctrl+Shift+R，或 DevTools → Network → Disable cache

# 根治方案（开发期）：在 docker-compose 的 frontend 服务下加 volume
#   volumes:
#     - ./frontend-pro:/usr/share/nginx/html/pro:ro
# 然后 docker compose up -d frontend
```

**预防措施（30 秒识别）**
- 改完前端代码，浏览器没变化 → 先 `docker exec quantdinger-frontend md5sum /usr/share/nginx/html/pro/index.html`，再 `Get-FileHash .\frontend-pro\index.html`，两个 md5 不一致就是没拷进去。

**关联文件**
- `../skills/quant-trading-expert/references/docker-okx-debug-2026-10.md`（第 5 节）
- `./frontend-debug-experience.md`（Step 2 明确写了 `docker cp index.html quantdinger-frontend:/usr/share/nginx/html/pro/index.html`）
- `./TODO.md`（"部署运维踩坑"第 2 条：Docker 容器内文件修改后不会自动同步，必须手动 docker cp）
- `../frontend-pro/index.html`（实测存在，163 KB）

**证据等级**：【临时绕过】—— docker cp 每次重启容器都得重做；volume 挂载方案未在 compose 里落地。

---

### E005 ｜ OKX 下单返回 "All operations failed"

**现象（报错原文）**
- 前端点"买入 BTC"，后端 OKX 客户端返回：
  ```
  success=False, message="All operations failed"
  ```
- 连接测试、查余额（`$98,340.28`）、ticker（BTC $80,229）全部正常，**只有下单失败**。

**根因（仓库实查到的可疑点，未最终定位）**
1. `backend_api_python/app/services/okx_client.py:144` 硬编码：
   ```python
   body = {
       'instId': symbol,
       'tdMode': 'cash',   # ← 写死现货现金模式
       'side': side,
       'ordType': ord_type,
       'sz': str(size)
   }
   ```
   如果 OKX 账户实际是合约账户或保证金账户（cross/isolated），`tdMode=cashe` 会被拒。
2. `okx_client.py:147` `'sz': str(size)` 没有做 OKX 最小下单量 / lot size 校验。BTC-USDT 现货最小下单是 0.00001 BTC，USDT 计价市价买单最小 5 USDT；传 `0.0001` 这种边缘值可能被 OKX 拒。
3. `okx_client.py:159` `body['clOrdId'] = f"qd{int(time.time()*1000)}"` —— 毫秒时间戳，正常不会撞；但 OKX 要求 `clOrdId` 是字母数字且 ≤32 字符，`qd + 13 位数字` 是合法的，这个嫌疑小。
4. TODO.md P0-1 第 32 行明写："⏳ 下单失败排查（"All operations failed"，需查 tdMode 参数）"。
5. 代码里**搜不到** `"All operations failed"` 这个字符串 —— 说明这是 OKX REST 接口原样返回的 `data[].sCode` / `msg`，不是我们自己拼的。

**修复步骤（PowerShell，照抄，待复现）**
```powershell
# 1. 先确认账户模式（cash / cross / isolated）
docker exec quantdinger-backend python -c "
from app.services.okx_client import OKXClient
c = OKXClient()
ok, msg, data = c.get_account()
print(ok, msg, data)
"
# 看 data['data'][0]['acctLv']：1=简单现货，2=单币种保证金，3=跨币种保证金，4=组合保证金

# 2. 用最小手数（10 USDT）在 DEMO 账户复现
docker exec quantdinger-backend python -c "
from app.services.okx_client import OKXClient
c = OKXClient()
ok, msg, data = c.place_order('BTC-USDT', 'buy', 0.0001, tgt_ccy='quote_ccy')
print(ok, msg, data)
"
# 把 OKX 返回的完整 JSON 打出来，对照 https://www.okx.com/docs-v5/ 错误码表

# 3. 如果 acctLv != 1，把 okx_client.py:144 的 'cash' 改成从账户配置读 tdMode
```

**预防措施（30 秒识别）**
- 任何 OKX 下单失败，先打完整 `response.json()`，**不要**只看 `msg`；OKX 的 `data[0].sCode`（如 51001=账户余额不足、51008=最小下单量、51009=杠杆不存在）才是根因。

**关联文件**
- `../backend_api_python/app/services/okx_client.py`（第 124–170 行 place_order；第 144 行 tdMode='cash'）
- `../backend_api_python/app/routes/account.py`（第 150–171 行 `/account/place-order` 路由）
- `./TODO.md`（P0-1 第 32 行；技术债 T5）
- `../backend_api_python/app/services/live_trading/okx.py`（第 628、642、706、726 行另一份 OKX 实现，tdMode 可配，可对照）

**证据等级**：【待验证】—— 仓库内只看到可疑代码点（tdMode 硬编码 + 最小量未校验），未在 DEMO 账户复现、未对照 OKX 错误码表。**"All operations failed" 这串原文来自 TODO.md 描述，仓库代码里没有该字符串**。

---

### E006 ｜ `git push` GitHub 超时 curl 28

**现象（报错原文）**
```
git push origin main
# 正在推送到 https://github.com/OpenByteInc/QuantDinger.git
# fatal: unable to access '...': Failed to connect to github.com port 443: Timed out
# curl: (28) Operation timed out after ... milliseconds
```
- 同一时刻 `git push gitee main` 正常。
- `curl https://gitee.com` 正常，`curl https://github.com` 超时。

**根因**
- 中国大陆直连 GitHub 被墙，不是凭证问题、不是仓库权限问题。
- Gitee 在境内，所以正常。

**修复步骤（PowerShell，照抄）**
```powershell
# 方案 A：给 git 单独配代理（Clash 默认 7890）
cd D:\Trader
git config --global http.https://github.com.proxy http://127.0.0.1:7890
git config --global https.https://github.com.proxy http://127.0.0.1:7890
git push origin main

# 方案 B：临时只走 Gitee 备份，等网络环境恢复
git push gitee main
```

**预防措施（30 秒识别）**
- `curl.exe -I https://github.com` 退出码 28 → 网络问题，不要去查 token、不要去查 remote URL。

**关联文件**
- `./TODO.md`（P0-4 第 50–52 行："Gitee 已同步，GitHub 连接被重置（curl 28）"）

**证据等级**：【已修复】—— 2026-10-31 网络恢复后，`git push github main` 直接推送被拒（远程存在无关的占位 `Initial commit` bd662ff），执行 `git merge github/main --allow-unrelated-histories -X ours` 合并后 `git push github main` 成功，`HEAD == github/main == gitee/main == 861dc24`。详见 E008。

---

### E007 ｜ 本地直连 OKX 被墙，curl 退出码 7

**现象（报错原文）**
```powershell
curl.exe -v https://www.okx.com/api/v5/public/time
# *   Trying ...
# * Failed to connect to www.okx.com port 443: Timed out / Connection refused
# curl: (7) Failed to connect ...
```
- 退出码 **7 = CURLE_COULDNT_CONNECT**（不是 401、不是 403、不是 DNS 错）。
- `nslookup www.okx.com` 能解析 → DNS 没病。
- `curl https://www.baidu.com` 正常 → 只有境外站被墙。
- 设 `$env:HTTPS_PROXY="http://127.0.0.1:7890"` 后立刻通。

**根因**
- 本地开发机在国内，OKX（www.okx.com）在大陆被墙。
- 后端容器即使能上网，Docker Desktop 的容器也**不继承** Windows 系统代理，必须显式传 `PROXY_URL=http://host.docker.internal:7890`（见 `backend_api_python/.env` 第 288 行 `PROXY_URL=` 留空）。

**修复步骤（PowerShell，照抄）**
```powershell
# 本地命令行走代理
$env:HTTPS_PROXY="http://127.0.0.1:7890"
$env:HTTP_PROXY="http://127.0.0.1:7890"
curl.exe -v https://www.okx.com/api/v5/public/time

# 后端容器走代理：编辑 backend_api_python/.env
#   PROXY_URL=http://host.docker.internal:7890
# 然后 docker compose up -d backend

# 生产环境：把后端部署到能直连 OKX 的区域（新加坡 / 美西），不要在国内机器上直连
```

**预防措施（30 秒识别）**
- `curl https://www.okx.com` 退出码 7 → 网络层被墙，**不要**在 TODO 里把"OKX 联通"标 ✅。
- 一定要先 `curl` 走代理测一次，再去查代码。

**关联文件**
- `../skills/quant-trading-expert/references/docker-okx-debug-2026-10.md`（第 3 节完整排查树）
- `./TODO.md`（P0-1 第 36 行；P0-5 第 197 行）
- `../backend_api_python/.env`（第 288 行 `PROXY_URL=` 当前为空）

**证据等级**：【已解除】—— 2026-10-31 复测：宿主机 `Invoke-WebRequest https://www.okx.com/api/v5/public/time` 直连 200；`docker exec quantdinger-backend` 容器内 `wget https://www.okx.com/api/v5/public/time` 返回 `{"code":"0",...}`；前端容器内 `wget https://api.binance.com/api/v3/ping` 返回 `{}`。直连与容器 NAT 均已恢复。代理 127.0.0.1:7890 仍可用作兜底（CONNECT 验证可转发 wss://stream.binance.com:9443）。

---

### E008 ｜ GitHub 远端无关初始提交 + 系统代理未设环境变量

**现象（报错原文）**
```text
git push github main
# ! [rejected] main -> main (fetch first)
# Updates were rejected because the remote contains work that you do not
# have locally. (unrelated histories)
```
- `git fetch github` 后发现远程 `main` 只有一个提交 `bd662ff Initial commit`（仅 2 行占位 README），与本地完整历史无公共祖先。
- 背景：系统 WinINET 代理 `127.0.0.1:7890` 一直启用且端口监听，但 `HTTP_PROXY`/`HTTPS_PROXY` 环境变量为空 → curl、git、docker 直连境外站超时，一度被误判为"被墙"。

**根因**
1. GitHub 推送被拒 → 远程仓库存在本地没有的无关提交（初始化空仓库时生成的占位 README），本地与远程历史完全无关。
2. "被墙"误判 → 代理配置在 WinINET（系统层）而非环境变量（进程层）：浏览器能翻墙，但 curl/git/python 等 CLI 进程不读 WinINET，直连被墙。

**修复步骤（PowerShell，照抄）**
```powershell
$git = "C:\Program Files\Git\bin\git.exe"
cd D:\Trader
# 1. 合并无关历史：保留本地完整 README，吸收远程占位提交
& $git merge github/main --allow-unrelated-histories -X ours -m "merge: 吸收 GitHub 占位初始提交, 保留本地完整 README"
# 2. 双端推送
& $git push github main
& $git push gitee main
# 3. 核对三处提交 ID 一致
& $git rev-parse HEAD 'github/main' 'gitee/main'   # 应输出同一 SHA

# 工具链走代理（进程层）：设置环境变量或按工具单独配置
$env:HTTPS_PROXY="http://127.0.0.1:7890"; $env:HTTP_PROXY="http://127.0.0.1:7890"
# git 单独配代理
& $git config --global http.https://github.com.proxy http://127.0.0.1:7890
```

**预防措施（30 秒识别）**
- `git push` 被拒先 `git fetch` 看远程历史，判断是否 unrelated histories，不要直接 `push -f`（会丢远程内容）。
- CLI 工具"被墙"时先查 `$env:HTTPS_PROXY`，再查 WinINET（注册表 `ProxyEnable/ProxyServer`），不要只凭浏览器能上网就断定"网络没问题"。
- Docker 容器不继承 Windows 系统代理，需要显式传 `PROXY_URL=http://host.docker.internal:7890`（E007 关联 `.env` 第 288 行）。

**证据等级**：【已修复】—— merge 提交 `861dc24` 已推送成功，`HEAD == github/main == gitee/main`；代理 CONNECT 转发 wss 已验证 200 OK。

---

### E009 ｜ 自建后端 ticker/kline 404 误判为"前端路径错"；dev-token 假登录导致 401 循环登出

**现象（报错原文）**
```text
GET /api/market/ticker?symbol=BTC-USDT  → 404（此前曾据此要改前端路径）
GET /api/market/kline?...               → 404
控制台 20 条 401/404 + 4 条「未登录或Token过期」，页面永远停在登录页
```
- 用官方镜像起的后端 :5000 上 `market/ticker`、`market/kline` 404；本地源码 `app/routes/account.py` 明明有这两个路由（第 100 行 kline、第 126 行 ticker），bp 注册前缀为 `/api`（register.py 第 121 行 `(account_bp, "/api")`）。

**根因**
1. **镜像代码旧，不是前端路径错**：镜像里缺 `app/routes/account.py` 及 services 26 个新文件 → 404 根因是后端缺路由。前端路径本就正确，若当时"按 404 改前端"就改错了方向。
2. **dev-token 假登录 + 真实鉴权后端 = 401 死循环**：前端初始化写入假 token `dev-token-2026`，自建后端 `utils/auth.py` 未开 `SKIP_AUTH`（`FLASK_ENV` 非 development）→ 全局 fetch 拦截器自动带 Bearer 假 token → 首个业务请求 401 → 拦截器触发 `Auth.logout()` 清 token 回登录页 → 页面永远停在登录页。

**修复步骤**
```powershell
# 1. 后端：本地 app 全量 docker cp 进容器并重启（消灭镜像旧代码）
docker cp D:\Trader\backend_api_python\app\{routes,routers,openapi,services,utils} qdpro-backend:/app/app/
docker restart qdpro-backend
# 2. 前端：初始化改真实自动登录（admin/admin123，开发模式），登录成功后才启动轮询
#    app.js 1897-1927：dev-token 假登录 → async IIFE 真实 Auth.login
# 3. 前端：risk 路径改向 /api/risk/dashboard → /api/risk/portfolio（后端无 dashboard 路由，真实结构 success:true）
# 4. 前端：credentials/list 返回 {code:1,data:{items:[...]}} → 取 data.items（data 是对象非数组）
# 5. 前端：favicon 404 用 <link rel="icon" href="data:,"> 抑制
# 6. 反代：scripts/serve_frontend_pro.py BACKEND :8888 → :5001，重启 serve
```

**预防措施（30 秒识别）**
- 404/401 先分层定位：`docker exec qdpro-backend grep -n route /app/app/routes/*.py` 确认容器内代码版本，再决定改前端还是改后端——**容器代码 ≠ 本地代码**（docker cp 后才一致）。
- 前端假 token 与后端真实鉴权必然冲突：开发模式要么后端开 `SKIP_AUTH=1`，要么前端真实登录，禁止写死假 token。
- 前端判据与后端结构逐接口核对：`success:true` vs `code:1`；`data` 是数组 vs `data.items`——先 curl 实测再写前端。
- 改动后端后必须 `docker restart` 且浏览器 `Ctrl+Shift+R` 强制刷新（静态资源缓存，E004）。

**证据等级**：【已修复】——自建后端 qdpro-backend（:5001）login/ticker/kline/p1/validation/risk/account/dashboard/credentials/strategies 全 200；:8899 自建前端 Chrome 复测控制台 **0 错误**，主界面真实行情 K 线、策略列表、账户资产全部渲染。

---

## 三、错误分类统计

| 分类 | 编号 | 计数 | 占比 |
|------|------|------|------|
| 环境部署类（Docker / compose / 容器编排） | E001、E003 | 2 | 25% |
| 网络类（GFW / GitHub / 代理配置） | E006、E007、E008 | 3 | 37.5% |
| 代码契约类（变量名 / 外部 API 协议） | E002、E005 | 2 | 25% |
| 认知偏差类（以为部署了其实没部署） | E004 | 1 | 12.5% |

**一句话洞察**：8 个坑里有 **3 个（E001/E003/E004）本质都是"我以为容器跑的是我以为的东西"** —— 镜像、DNS、文件系统三层都和本地心智模型错位；E006/E007/E008 三个"网络坑"里，真正被墙的只有 E006/E007 前半段，其余是代理配置分层（WinINET vs 环境变量）与远程历史分叉的认知问题。真正的纯代码 bug 是 0 个。

---

## 四、根因模式 Top 3（跨错误归纳）

1. **健康检查只看进程，不看业务面**（E001、E003）
   `/health` 200 + DB 连通 ≠ 路由注册 + 上游可达。每次 build / 换镜像 / 重启容器后，必须用 `openapi.json` 和 `getent hosts` 各验一次业务面，不能只看进程。

2. **容器 ≠ 本机文件系统，容器 ≠ 本机网络栈**（E001、E004、E007）
   本地改文件不进容器（没挂 volume）；本地配代理不进容器（Docker Desktop 隔离）；本地 `docker rm` 换镜像会丢自研代码。任何"我本地明明改了"都要先 `docker exec` 进容器 md5sum 确认。

3. **跨文件配置没有一致性校验**（E002、E005）
   密码散落在 `.env` / `backend_api_python/.env` / compose 默认值三处；`tdMode` 硬编码在代码里，没有从账户配置读。`scripts/check_production_config.py` 只查弱密码黑名单，没做"POSTGRES_PASSWORD == DATABASE_URL 里密码段"这种跨文件比对。

---

## 五、预防 SOP（每次改完代码 / 重启容器 / 换网络后必跑）

把下面 5 条存成 `scripts/post_change_check.ps1`，每次改动后无脑跑一遍：

```powershell
cd D:\Trader

# 1. 业务路由在容器里真的注册了吗？（防 E001）
$routes = curl.exe -s http://localhost:5000/openapi.json | Select-String "okx|account/place-order"
if (-not $routes) { Write-Host "[FAIL] 容器里没有 okx/account 路由，镜像里没我们的代码" -ForegroundColor Red }

# 2. 前端容器能解析后端吗？（防 E003）
$dns = docker exec quantdinger-frontend getent hosts backend 2>$null
if (-not $dns) { Write-Host "[FAIL] 前端容器解析不到 backend，nginx 会 502" -ForegroundColor Red }

# 3. 前端文件 md5 和本地一致吗？（防 E004）
$localMd5  = (Get-FileHash .\frontend-pro\index.html -Algorithm MD5).Hash
$dockerMd5 = docker exec quantdinger-frontend md5sum /usr/share/nginx/html/pro/index.html 2>$null
if ($localMd5 -and $dockerMd5 -notmatch $localMd5) { Write-Host "[FAIL] 前端容器里 index.html 是旧版，需要 docker cp" -ForegroundColor Red }

# 4. 后端连得上 DB 吗？（防 E002）
docker exec quantdinger-backend python -c "from app.utils.db_postgres import get_conn; get_conn().close(); print('DB OK')" 2>&1

# 5. 出网到 OKX 通吗？（防 E007）
curl.exe -s -o $null -w "okx_http=%{http_code} exit=%{exitcode}`n" --max-time 5 https://www.okx.com/api/v5/public/time
# 期望 exit=0；如果 exit=7，先 $env:HTTPS_PROXY=http://127.0.0.1:7890 再测
```

---

## 六、新错误登记模板

每次踩坑**当天**追加一行到下面的空表里，不要攒着：

| 编号 | 日期 | 错误类型 | 一句话现象 | 严重级 | 状态 | 证据链接 |
|------|------|----------|------------|--------|------|----------|
| E008 | YYYY-MM-DD | 环境/部署/网络/代码/配置 |  | P0/P1/P2 | 已修复/临时绕过/待验证 |  |

然后在本文件第二节"逐条详情"里补一段 E008，至少写：现象原文、根因（5 Why）、修复命令、30 秒识别口诀、关联文件、证据等级。
