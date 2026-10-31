# QuantDinger 前端联调 Bug 清单

- 测试时间：2026-10-28 (Asia/Shanghai)
- 被测环境：http://localhost:8888 （Docker 容器 `quantdinger-frontend`，nginx/1.25.5）
- 后端直连：http://localhost:5000 （Docker 容器 `quantdinger-backend`，Up 6 min）
- 测试方式：Chrome + 浏览器自动化（bu plane），人工核对 nginx 与后端日志
- 测试范围说明：本次只做测试与记录，**未修改任何前端/后端代码，未重启任何容器，未删除任何文件**。

---

## 一、环境基线（已验证）

| 项 | 状态 | 证据 |
|---|---|---|
| 前端容器 `quantdinger-frontend` | Up 4h (healthy)，127.0.0.1:8888->80 | `docker ps` |
| 后端容器 `quantdinger-backend` | Up 6 min，127.0.0.1:5000->5000 | `docker ps` |
| 前后端同 Docker 网络 | `trader_quantdinger-network`，前端 172.18.0.7，后端 172.18.0.14 | `docker inspect` |
| 后端直连健康检查 | `GET http://localhost:5000/api/health` → 200 `{"status":"healthy",...}` | PowerShell Invoke-WebRequest |
| 后端直连公开配置 | `/api/auth/security-config`、`/api/settings/brand-config`、`/api/policy/broker-market` → 200 | 同上 |
| 静态资源（JS/CSS/Logo） | 全部 200 | 浏览器 network_requests |
| 登录页骨架渲染 | 正常（Logo、表单、Legal Disclaimer、语言切换均可见） | 截图 `_shot_login.png` |

---

## 二、Bug 清单

### P0-1　前端 nginx upstream 主机名 `backend` 无法解析，所有 /api 请求 502（阻塞）

- **严重程度**：P0 阻塞。前端登录、已鉴权页面、核心引擎、K线图全部不可用。
- **复现步骤**：
  1. 打开 http://localhost:8888 ，页面自动跳到 `/#/user/login?redirect=%2F`。
  2. 打开 DevTools Network，观察 `GET /api/auth/security-config`、`/api/settings/brand-config`、`/api/policy/broker-market`。
  3. 用任意账号密码（实测 `admin / Admin@2026`）点击 Login，观察 `POST /api/auth/login`。
- **控制台报错原文**（关键行）：
  ```
  error | Failed to load resource: the server responded with a status of 502 (Bad Gateway)
  error | Failed to load security config: AxiosError: <html>
        <head><title>502 Bad Gateway</title></head>
        <body><center><h1>502 Bad Gateway</h1></center><hr>
        <center>nginx/1.25.5</center></body></html>
  warning | LoadBrandConfig failed, falling back to defaults: AxiosError: <html>...
  warning | LoadBrokerMarketPolicy failed, falling back to defaults: AxiosError: <html>...
  ```
- **涉及的 API 路径与返回码**（通过前端 nginx :8888）：
  | 路径 | 方法 | 返回 |
  |---|---|---|
  | `/api/auth/security-config` | GET | 502 |
  | `/api/settings/brand-config` | GET | 502 |
  | `/api/policy/broker-market` | GET | 502 |
  | `/api/auth/login` | POST | 502 |

  对比：同一批路径直接打后端 `http://localhost:5000` 全部 200（除 `/api/auth/login` 直连 GET 返回 405，属正常方法不允许）。
- **nginx 错误日志**（`docker logs quantdinger-frontend --tail 50`）：
  ```
  2026/10/27 16:15:22 [error] 37#37: *438 backend could not be resolved (3: Host not found),
        client: 172.18.0.1, server: localhost,
        request: "GET /api/auth/security-config?_t=... HTTP/1.1", host: "localhost:8888"
  ```
- **根因定位**：
  - 前端容器内 nginx 配置（`/etc/nginx/conf.d/default.conf`）使用：
    ```nginx
    set $backend_upstream http://backend:5000;
    proxy_pass $backend_upstream;
    ```
  - 但 Docker 网络 `trader_quantdinger-network` 中，后端容器 `quantdinger-backend` 的 DNS 别名只有 `quantdinger-backend`（以及容器短 ID `d852e7f1b1cc`），**没有 `backend` 这个别名**。
  - 实测在前端容器内：
    - `getent hosts quantdinger-backend` → `172.18.0.14` ✅
    - `getent hosts backend` → 空 ❌（这就是 nginx 报 Host not found 的直接原因）
- **初步判断**：**部署/配置问题（P0，非前端代码 bug）**。修复方向（仅供参考，本次未执行）：
  - 方案 A：在 `docker-compose.yml` 给后端服务加 network alias `backend`；
  - 方案 B：把 nginx 配置里的 `backend:5000` 改成 `quantdinger-backend:5000`；
  - 方案 C：在 `proxy_pass` 用变量的前提下，用 `resolver 127.0.0.11 valid=30s;` 配合 Docker 内置 DNS（当前配置已经用了 `set` 变量方式，但主机名本身不存在，所以 resolver 也救不了）。
- **建议优先级**：立即修。这是本次联调唯一的阻塞项，修完之后才能继续测后续模块。

---

### P1-1　登录失败时把 nginx 502 HTML 原文渲染进错误提示框（前端容错缺失）

- **严重程度**：P1 功能/UX 异常。不影响数据，但用户体验极差、误导排查。
- **复现步骤**：
  1. 在登录页输入任意账号密码，点击 Login。
  2. 等待 `POST /api/auth/login` 返回 502。
  3. 观察表单上方的红色错误提示框。
- **现象**：错误提示框里直接展示了整段 nginx 默认 HTML 错误页，包括重复了 6 次的 `<!-- a padding to disable MSIE and Chrome friendly error page -->` 注释（见截图 `_shot_login_result.png`）。
- **控制台报错原文**：
  ```
  error | Failed to load resource: the server responded with a status of 502 (Bad Gateway)
  （HTTP 响应体是 text/html，不是 JSON，前端没有拦截）
  ```
- **涉及 API**：`POST /api/auth/login` → 502 nginx HTML。
- **初步判断**：**前端问题**。axios 拦截器在登录错误处理分支里，没有对 `Content-Type: text/html` 或非 2xx 非 JSON 的响应做 fallback，直接 `message.error(err.response.data)` 或类似调用，把 HTML 字符串塞进了 antd 的 message/alert。
- **建议修复**：在响应拦截器里统一判断 `if (!/json/.test(contentType)) { msg = '服务暂时不可用 (HTTP 5xx)，请稍后重试' }`，同时避免把整段 HTML 暴露给终端用户。

---

### P2-1　登录错误提示在路由切换/表单重置后未清空

- **严重程度**：P2 视觉/状态残留。
- **复现步骤**：
  1. 在登录页触发一次登录失败（出现 P1-1 的红色错误框）。
  2. 直接改地址栏跳到 `http://localhost:8888/#/user/register`。
  3. 路由守卫把未登录用户重定向回 `/#/user/login?redirect=%2Fuser%2Fregister`。
- **现象**：重定向回登录页后，上一次的 502 HTML 错误提示**仍然挂在表单上方**，没有被清空（截图 `_shot_register.png`）。表单本身（用户名/密码）也没有被重置。
- **初步判断**：**前端问题**。登录页组件在 `onMounted` 或路由参数变化时，没有 reset 错误 state。
- **建议修复**：在登录页 `watch` 到 `redirect` 参数变化或 `onMounted` 时，清空 `errorMessage` / 表单字段。

---

### Info-1　密码输入框缺少 autocomplete 属性（antd 警告）

- **严重程度**：Info（不影响功能）。
- **控制台原文**：
  ```
  [DOM] Input elements should have autocomplete attributes (suggested: "current-password"):
  (More info: https://goo.gl/9p2vKq)
  ```
- **初步判断**：前端表单小问题。给密码 `<a-input-password>` 加 `autocomplete="current-password"` 即可消除警告。

---

## 三、已知限制（不计入 Bug，但记录在案）

| 项 | 说明 |
|---|---|
| OKX 相关路由 404 | `/api/okx/accounts`、`/api/okx/positions`、`/api/account/balance` 直连 :5000 返回 404。这是因为 `account.py` / `okx_client.py` 是我们自己写的，**官方镜像里没有**。用户已说明此为已知问题，不视为前端 bug。 |
| 本地直连 OKX API 被墙 | 后端若直接访问 `www.okx.com` 会 curl 退出码 7（connection refused/timeout），与前端无关。 |
| `quantdinger-scheduler-worker`、`quantdinger-trading-worker` 容器 unhealthy | 后端基础设施问题，不在前端联调范围。 |
| `POST /api/auth/login` 直连 GET 返回 405 | 正常方法不允许（login 只接受 POST），不是 bug。 |
| `/api/dashboard/summary` 直连返回 401 | 正常未鉴权，不是 bug。 |

---

## 四、未能测试的项（因 P0-1 阻塞）

以下模块**本次未测**，原因均为无法登录（nginx 502 导致 `/api/auth/login` 失败，拿不到 token）：

- [ ] 登录成功后的首页/工作台（核心引擎面板渲染）
- [ ] K线图表组件（`/api/market/kline` 走 nginx 也 502，无法观察图表渲染）
- [ ] 侧边栏 / 顶部导航的各个菜单项（策略、回测、因子、组合、订单、设置等）
- [ ] 已鉴权 API 的 401/403 处理是否正常
- [ ] WebSocket / SSE 实时通道是否建立
- [ ] 移动端 `quantdinger-mobile`（:8889）未在本次任务范围

> 建议：先修 P0-1（nginx upstream 主机名），重启前端容器后再跑一遍本清单的"未测"部分。预计修完 P0 后，本次列出的 P1-1、P2-1 也能在真实登录流程里复测一遍。

---

## 五、测试产物（截图证据）

均位于 `D:\Trader\docs\`：
- `_shot_login.png` —— 登录页首次加载（此时 security-config / brand-config / broker-market 三个 GET 已 502，但页面骨架正常）
- `_shot_after_login_click.png` —— 点击 Login 后按钮进入 loading，请求 inflight
- `_shot_login_result.png` —— 登录失败，红色错误框内显示 nginx 502 HTML 原文（P1-1 证据）
- `_shot_register.png` —— 跳到 /#/user/register 被守卫重定向回登录页，旧错误提示残留（P2-1 证据）
