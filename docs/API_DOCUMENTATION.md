# QuantDinger Pro API 文档（代码审计版）

> 审计日期：2026-11-08。审计方式：对 `backend_api_python` 做静态扫描（蓝图注册清单 + AST 解析路由装饰器与函数体），**未启动服务、未发送真实请求**。
> 覆盖范围：`app/routes`（人类端，含 `strategy_*` 子模块）、`app/routes/agent_v1`（Agent 网关）、`app/openapi/routes/health`。
> 边界：本版只为**已有路由**补文档，未新增/扩写任何公共 API，未改生产代码、交易/风控/下单/资金逻辑；未触碰 `configs/`、`registry.yaml`、`mt5/`、`secrets/`、`runtime/`、`ledger/`。

## 0. 图例与置信度

**动作分类**

| 标记 | 含义 |
|---|---|
| 🟢 只读 | GET 查询，不写库、不发单 |
| 🟡 写操作 | POST/PUT/PATCH/DELETE，写本地库或配置（非交易所资金动作） |
| 🧮 计算 | POST 但仅本地计算/校验，不下单、不划转资金 |
| 💳 积分扣减 | 回测/分析等计费侧效应（扣平台积分，非外部资金划转） |
| 💰 资金/权益 | 积分/VIP/会员订单/权益变更 |
| 🔴 交易动作 | 下单、平仓、撤单、熔断、停策略收口持仓 |

**置信度标注**

- `confirmed`：代码字面可证（路由装饰器、函数体内字典构造、`data.get(...)` 键名）。
- `inferred`：由命名、服务委托或前端约定推断，未在本次代码中逐字证实。
- `unknown`：代码无法证实，需到对应 service / schema / 运行时核对。

> 字段口径：下方清单“响应 data”只列**路由函数体内字面构造**的键；经服务层字典组装的列表/对象，路由层未展开，标 `unknown`，需核对对应 `services/*.py` 或 `openapi/schemas`。

---

## 1. 基础信息

| 项目 | 值 | 置信度 |
|---|---|---|
| Base URL | 同源 `/api`（主机由部署/反代决定；本地默认 `http://localhost:5000`） | inferred |
| 数据格式 | JSON，UTF-8 | confirmed |
| 鉴权体系 | 人类 JWT；Agent token（两套独立） | confirmed |

### 1.1 响应信封（三种，勿混用）

1. **人类标准** `{ "code": 1, "msg": "success", "data": {} }`：`code=1` 成功，`0` 失败；失败常附 HTTP 400/401/403/404/429/500，`data` 可为 `null`。confirmed
2. **旧版 / 券商 / 分析模块** `{ "success": true, "data": ..., "count"?: n }` 或 `{ "success": false, "error": ... }`：`account.py`、`alpaca.py`、`ibkr.py`、`p1_modules.py`、`p2_modules.py`、`risk.py`、`tca.py`。confirmed
3. **Agent 网关** 成功 `{ "code": 0, "message": "ok", "data": ... }`；错误 `{ "code": <int>, "message": ..., "details": ..., "retriable": bool, "data": null }`。confirmed
4. **健康/指标类**直接返回 schema 载荷，不经信封：`/`、`/health`、`/api/health*`、`/metrics`。confirmed
5. **SSE**（`text/event-stream`，非 JSON 信封）：`/api/indicator/aiGenerate`、`/api/ai/chat/message/stream`、`/api/agent/v1/jobs/<job_id>/stream`。confirmed

### 1.2 健康与系统端点（免鉴权）

| 方法 | 路径 | 响应 | 置信度 |
|---|---|---|---|
| GET | `/` | `{ name, version, status, timestamp }` | confirmed |
| GET | `/health` | `{ status, timestamp, role }` 存活探针 | confirmed |
| GET | `/api/health` | 同 `/health`（兼容路径，容器/反代探活） | confirmed |
| GET | `/api/health/ready` | 附加 `checks: { postgres, celery_broker }`；任一不可用返回 503 | confirmed |
| GET | `/api/health/workers` | 附加 `workers: [...]`（按角色统计 running/healthy/stale/last_heartbeat，读 `qd_worker_heartbeats`） | confirmed |
| GET | `/metrics` | Prometheus 文本指标（`text/plain`） | confirmed |

---

## 2. 鉴权

### 2.1 人类端

- 请求头：`Authorization: Bearer <JWT>`；前端存储于 localStorage `qd_token`（键名为前端实现）。confirmed（头格式）/ inferred（存储键）
- 装饰器：`@login_required` 登录即可；`@admin_required` 需 admin 角色；`@manager_required` 需 manager。无装饰器即公开。confirmed
- 失败：401 未认证；403 权限不足。

### 2.2 Agent 网关（`/api/agent/v1`）

- 请求头：`Authorization: Bearer qd_agent_...`；与人类 JWT 体系独立（`app/utils/agent_auth.py`，表 `qd_agent_tokens`）。confirmed
- 能力 scope：`R` 只读 / `W` 工作区写 / `B` 回测模拟 / `N` 通知副作用 / `C` 凭证(admin) / `T` 交易资金。confirmed
- 写类 scope 支持 `Idempotency-Key` 头做幂等；响应带 `X-RateLimit-Limit / Remaining / Reset` 头。confirmed
- `/api/agent/v1/health` 免 token；`/admin/*`、`/me/*` 走人类会话 JWT（admin），不走 Agent token。confirmed

---

## 3. 已核实登录契约（confirmed）

**POST** `/api/auth/login`

请求体（schema 绑定 `LoginRequestSchema`，路由内读取）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `username` 或 `account` | str | 用户名 / 邮箱 |
| `password` | str | 密码 |
| `turnstile_token` | str | 可选；开启 Turnstile 时必填 |
| `turnstile_clearance` | str | 可选；与 `turnstile_token` 二选一的清场凭证 |

成功响应 `code=1`，`data`：

| 字段 | 说明 |
|---|---|
| `token` | JWT |
| `userinfo` | `{ id, username, nickname, avatar, timezone, role: { id, permissions }, must_change_initial_password }` |

MFA 未完成：`code=1`，`data: { mfa_required: true, ...challenge }`。
失败：`code=0, msg=<原因>, data=null`；401 凭证无效 / 403 账号禁用或待激活 / 429 登录限流。

> 本地单用户模式示例账号 `admin/admin123` 仅为部署示例；生产以 `qd_users` 为准。inferred

**相关认证端点**

| 方法 | 路径 | 鉴权 | 口径 |
|---|---|---|---|
| GET | `/api/auth/security-config` | 公开 | 安全配置（Turnstile 开关等），data 由服务层构造，字段 unknown |
| POST | `/api/auth/turnstile-clearance` | 公开 | `data: { turnstile_clearance, expires_in }` |
| POST | `/api/auth/mfa/verify-login` | 公开 | MFA 校验通过返回 `data: { token, userinfo }` |
| POST | `/api/auth/login-code` | 公开 | body `{ email, code, referral_code? }`；写 `qd_users`；`data: { token, userinfo, is_new_user, mfa_required }` |
| POST | `/api/auth/send-code` | 公开 | body `{ email, type, turnstile_token?, turnstile_clearance? }` |
| POST | `/api/auth/register` | 公开 | schema 绑定；`data: { token, userinfo }`；写 `qd_users` |
| POST | `/api/auth/reset-password` | 公开 | 邮件验证码重置；字段 unknown |
| POST | `/api/auth/change-password` | JWT | 改当前用户密码；字段 unknown |
| GET | `/api/auth/info` | JWT | `data` 同 `userinfo` 结构 |
| GET | `/api/auth/oauth/google`、`/api/auth/oauth/github` | 公开 | 跳转授权；query `redirect` |
| GET | `/api/auth/oauth/google/callback`、`/api/auth/oauth/github/callback` | 公开 | 回调；query `code, error, state` |
| POST | `/api/auth/logout` | 公开 | 路由层未做服务端状态吊销（JWT 无状态），字段 unknown |

---

## 4. 交易 / 资金动作端点（高风险，仅标注，未改动）

### 4.1 交易动作（下单 / 平仓 / 撤单 / 熔断 / 停策略收口）

| 方法 | 路径 | 鉴权 | 关键请求字段 | 数据源 / 备注 |
|---|---|---|---|---|
| POST | `/api/quick-trade/place-order` | JWT | `credential_id, symbol, side, order_type(market/limit), amount, price, leverage, market_type, tp_price, sl_price, source, margin_mode/marginMode` | 快速交易下单；成功/失败信封见快速交易模块 |
| POST | `/api/quick-trade/close-position` | JWT | `credential_id, symbol, market_type, size(0=全平), close_scope(full/system_tracked), position_side, source` | 平仓；写 `qd_quick_trades` |
| POST | `/api/strategies/<int:strategy_id>/stop` | JWT | 路径 `strategy_id` | 停策略并收口持仓（服务层 `close_position`） |
| POST | `/api/ibkr/order` | JWT | `symbol, side, quantity, marketType, orderType(market/limit), price` | IBKR 下单；success 信封 |
| DELETE | `/api/ibkr/order/<int:order_id>` | JWT | 路径 `order_id` | IBKR 撤单 |
| POST | `/api/alpaca/order` | JWT | `symbol, side, quantity, marketType, orderType, price, extendedHours` | Alpaca 下单；success 信封 |
| DELETE | `/api/alpaca/order/<order_id>` | JWT | 路径 `order_id` | Alpaca 撤单 |
| POST | `/api/account/place-order` | **无鉴权装饰器（遗留）** | `symbol, side, size, price` | 旧版 OKX DEMO 直连；凭证存内存 `_account_configs`；success 信封 |
| POST | `/api/agent/v1/quick-trade/orders` | Agent token · T | 见 Agent OpenAPI | 网关下单 |
| POST | `/api/agent/v1/quick-trade/kill-switch` | Agent token · T | — | 网关熔断 |
| POST | `/api/agent/v1/strategies/<int:strategy_id>/stop` | Agent token · T | 路径 `strategy_id` | 网关停策略 |

### 4.2 资金 / 权益 / 计费动作

| 方法 | 路径 | 鉴权 | 关键请求字段 | 口径 |
|---|---|---|---|---|
| POST | `/api/billing/usdt/create` | JWT | `plan(monthly/yearly/lifetime), chain?(TRC20/BEP20/ERC20/SOL)` | 创建 USDT 会员订单；`data` 由 `usdt_payment_service` 构造，字段 unknown |
| POST | `/api/community/indicators/<int:indicator_id>/purchase` | JWT | 路径 `indicator_id` | 购买指标：扣买方积分、记卖方积分（服务层） |
| POST | `/api/users/set-credits` | JWT+admin | schema 绑定，字段 unknown | 调整用户积分；`data: { credits }` |
| POST | `/api/users/set-vip` | JWT+admin | schema 绑定，字段 unknown | 设置 VIP；`data: { vip_expires_at }` |
| POST | `/api/users/admin-orders/<int:order_id>/manual-confirm` | JWT+admin | 路径 `order_id` | 人工确认 USDT 订单；写 `qd_usdt_orders`；`data` 含 `order_id, status, tx_hash, plan, user_id, manual_confirmed_by, admin_note, already_confirmed, billing_error` |
| POST | `/api/backtest/run` | JWT | 见回测清单 | 💳 扣回测积分；余额不足 402，`data.error_type=INSUFFICIENT_CREDITS` |
| POST | `/api/backtest/factor-research` | JWT | 见回测清单 | 💳 扣积分 |
| POST | `/api/backtest/tune` | JWT | 见回测清单 | 💳 扣积分 |
| POST | `/api/fast-analysis/analyze` | JWT | 见快速分析清单 | 💳 扣分析积分；不足 402，`data` 含 `required/current/shortage` |

---

## 5. 数据源适配器与决策链路（口径结论）

- **confirmed（导入层证据）**：情绪 / 新闻 / 宏观日历 / 商品 / 指数 / 机会 / 热力图等适配器聚合在 `app/services/global_market_data.py`（`data_providers` 下 commodities、crypto、forex、indices、opportunities、sentiment），仅供 `/api/global-market/*` 展示视图；**未被** `services/strategy_runtime`、`services/live_trading`、`services/execution_streams` 以及快速交易/券商下单服务导入。
- **结论**：自动下单 / 策略执行链路在导入层未消费这些外部情绪、新闻、宏观、商品、指数、热力图数据 → **confirmed 不进入该自动决策链**。
- **advisory 链路**：`ai_chat`、`fast_analysis`、`ai_skill_registry` 可消费部分宏观日历 / 情绪 / 新闻作为分析与打分输入（非直接下单）。
- `market_data_collector` 读取缓存情绪（vix / dxy / fear_greed）作为行情上下文；其是否进一步进入信号或下单判断，本次静态审计**未证实 → unknown**。
- 策略脚本 / 自定义工具能否在运行时读取上述数据源，本次**未证实 → unknown**。

---

## 6. 人类端全量路由清单

> 鉴权列：`JWT` = 人类登录；`JWT+admin` = 需 admin；“公开”= 无鉴权装饰器。请求/响应字段为空处为 schema 绑定或服务层委托，标 unknown。

### 策略矩阵 Policy

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/policy/broker-market` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |

### 认证 Auth

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/auth/security-config` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/auth/turnstile-clearance` | 公开（无鉴权装饰器） | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: expires_in, turnstile_clearance | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| POST | `/api/auth/login` | 公开（无鉴权装饰器） | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: blocked, mfa_required, token, userinfo | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| POST | `/api/auth/mfa/verify-login` | 公开（无鉴权装饰器） | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: token, userinfo | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| POST | `/api/auth/login-code` | 公开（无鉴权装饰器） | 🟡 写操作（本地库/配置） | body: code, email, referral_code | code/msg/data 信封；data: is_new_user, mfa_required, token, userinfo | 表: qd_users | 路由 confirmed；请求字段 confirmed；响应字段 confirmed |
| POST | `/api/auth/send-code` | 公开（无鉴权装饰器） | 🟡 写操作（本地库/配置） | body: email, turnstile_clearance, turnstile_token, type | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| POST | `/api/auth/register` | 公开（无鉴权装饰器） | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: token, userinfo | 表: qd_users | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| POST | `/api/auth/reset-password` | 公开（无鉴权装饰器） | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/auth/change-password` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/auth/oauth/google` | 公开（无鉴权装饰器） | 🟢 只读 | query: redirect | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/auth/oauth/google/callback` | 公开（无鉴权装饰器） | 🟢 只读 | query: code, error, state | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/auth/oauth/github` | 公开（无鉴权装饰器） | 🟢 只读 | query: redirect | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/auth/oauth/github/callback` | 公开（无鉴权装饰器） | 🟢 只读 | query: code, error, state | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| POST | `/api/auth/logout` | 公开（无鉴权装饰器） | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/auth/info` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: avatar, email, id, must_change_initial_password, nickname, role, timezone, username | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |

### 用户与管理 Users

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/users/list` | Bearer JWT+admin | 🟢 只读 | query: page, page_size, search, user_id | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/users/export` | Bearer JWT+admin | 🟢 只读 | query: search, user_id | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/users/detail` | Bearer JWT+admin | 🟢 只读 | query: id | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| POST | `/api/users/create` | Bearer JWT+admin | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: id | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| PUT | `/api/users/update` | Bearer JWT+admin | 🟡 写操作（本地库/配置） | query: id | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| DELETE | `/api/users/delete` | Bearer JWT+admin | 🟡 写操作（本地库/配置） | query: id | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| POST | `/api/users/reset-password` | Bearer JWT+admin | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/users/roles` | Bearer JWT+admin | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: roles | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| POST | `/api/users/set-credits` | Bearer JWT+admin | 💰 资金/权益动作 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: credits | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| POST | `/api/users/set-vip` | Bearer JWT+admin | 💰 资金/权益动作 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: vip_expires_at | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| GET | `/api/users/credits-log` | Bearer JWT+admin | 🟢 只读 | query: page, page_size, user_id | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/users/login-logs` | Bearer JWT | 🟢 只读 | query: page, page_size | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/users/profile` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 表: qd_users | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| PUT | `/api/users/profile/update` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/users/mfa/status` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/users/mfa/setup/start` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/users/mfa/setup/confirm` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/users/mfa/disable` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/users/my-credits-log` | Bearer JWT | 🟢 只读 | query: page, page_size | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/users/my-referrals` | Bearer JWT | 🟢 只读 | query: page, page_size | code/msg/data 信封；data: list, page, page_size, referral_bonus, referral_code, register_bonus, total | 表: qd_users | 路由 confirmed；请求字段 confirmed；响应字段 confirmed |
| GET | `/api/users/notification-settings` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| PUT | `/api/users/notification-settings` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/users/chart-templates` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/users/chart-templates` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| DELETE | `/api/users/chart-templates` | Bearer JWT | 🟡 写操作（本地库/配置） | query: template_id | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| POST | `/api/users/notification-settings/test` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/users/change-password` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/users/system-strategies` | Bearer JWT+admin | 🟢 只读 | query: execution_mode, page, page_size, search, sort_by, sort_order, status, strategy_class, strategy_id, user_id | code/msg/data 信封；data: items, page, page_size, summary, total | 表: qd_script_sources, qd_strategies_trading, qd_strategy_broker_activities, qd_strategy_funding_fees, qd_strategy_positions, qd_strategy_trades, qd_users | 路由 confirmed；请求字段 confirmed；响应字段 confirmed |
| POST | `/api/users/system-strategies/toggle` | Bearer JWT+admin | 🟡 写操作（本地库/配置） | query: action, id | code/msg/data 信封；data: detail, id, status | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 confirmed |
| DELETE | `/api/users/system-strategies/delete` | Bearer JWT+admin | 🟡 写操作（本地库/配置） | query: id | code/msg/data 信封；data: id | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 confirmed |
| GET | `/api/users/admin-orders` | Bearer JWT+admin | 🟢 只读 | query: page, page_size, search, status | code/msg/data 信封；data: items, page, page_size, summary, total | 表: qd_usdt_orders, qd_users | 路由 confirmed；请求字段 confirmed；响应字段 confirmed |
| POST | `/api/users/admin-orders/<int:order_id>/manual-confirm` | Bearer JWT+admin | 💰 资金/权益动作 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: admin_note, already_confirmed, billing_error, manual_confirmed_by, order_id, plan, status, tx_hash, user_id | 表: qd_usdt_orders | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| GET | `/api/users/admin-ai-stats` | Bearer JWT+admin | 🟢 只读 | query: page, page_size, search | code/msg/data 信封；data: page, page_size, recent, recent_copilot, summary, user_stats, user_total | 表: qd_ai_copilot, qd_ai_copilot_messages, qd_ai_copilot_sessions, qd_analysis_memory, qd_analysis_tasks, qd_users | 路由 confirmed；请求字段 confirmed；响应字段 confirmed |
| GET | `/api/users/admin/stats` | Bearer JWT+admin | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |

### K线 Kline

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/indicator/kline` | 公开（无鉴权装饰器） | 🟢 只读 | query: beforeTime, before_time, exchangeId, exchange_id, instrumentId, instrument_id, limit, market, marketType, market_type, symbol, timeframe | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |

### 回测中心 Backtest

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| POST | `/api/backtest/run` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: billing, current, error_type, feature, required, runId, shortage | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| POST | `/api/backtest/factor-research` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: runId | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| GET | `/api/backtest/factor-research/history` | Bearer JWT | 🟢 只读 | query: limit, offset, sourceId | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/backtest/factor-research/get` | Bearer JWT | 🟢 只读 | query: runId | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| POST | `/api/backtest/tune` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: best, candidates, errors, method, totalCandidates | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| GET | `/api/backtest/history` | Bearer JWT | 🟢 只读 | query: limit, market, offset, sourceId, symbol, timeframe | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/backtest/get` | Bearer JWT | 🟢 只读 | query: runId | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |

### 市场数据 Market

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/market/config` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: models, qdt_cost | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| GET | `/api/market/types` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/market/menuFooterConfig` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/market/symbols/search` | 公开（无鉴权装饰器） | 🟢 只读 | query: exchangeId, exchange_id, keyword, limit, market, marketType, market_type | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/market/symbols/hot` | 公开（无鉴权装饰器） | 🟢 只读 | query: limit, market | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/market/watchlist/get` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/market/watchlist/add` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/market/watchlist/remove` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/market/watchlist/prices` | Bearer JWT | 🟢 只读 | query: watchlist | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/market/price` | 公开（无鉴权装饰器） | 🟢 只读 | query: exchangeId, exchange_id, market, marketType, market_type, symbol | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |

### 研究股票池 Universe

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/universes/` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/universes/` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/universes/<int:universe_id>/clone` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/universes/admin/overview` | Bearer JWT+admin | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/universes/admin/sync` | Bearer JWT+admin | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: as_of, errors, results | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| GET | `/api/universes/<int:universe_id>` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/universes/<int:universe_id>/members` | Bearer JWT | 🟢 只读 | query: asOf, as_of | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| PUT | `/api/universes/<int:universe_id>/members` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/universes/<int:universe_id>/snapshots` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |

### 因子 Factors

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/factors/` | Bearer JWT | 🟢 只读 | query: category, factor_type, provider, type | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/factors/<string:factor_id>` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/factors/research` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/factors/fundamentals/coverage` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/factors/fundamentals/sync` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |

### 市场模块 Market Modules

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/market-modules/` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: markets | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |

### AI 助手 Chat

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/ai/skills` | Bearer JWT | 🟢 只读 | query: include_disabled, language | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/ai/tools` | Bearer JWT+admin | 🟢 只读 | query: language | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| POST | `/api/ai/skills/install` | Bearer JWT+admin | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: skill | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| PATCH | `/api/ai/skills/<skill_id>` | Bearer JWT+admin | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| DELETE | `/api/ai/skills/<skill_id>` | Bearer JWT+admin | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: id | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| POST | `/api/ai/skills/<skill_id>/prompt` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: prompt, skill | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| GET | `/api/ai/agent/preflight` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/ai/agent/intent` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/ai/memory` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: items | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| POST | `/api/ai/memory` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: id | 表: qd_ai_user_memories | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| DELETE | `/api/ai/memory/<int:memory_id>` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: id | 表: qd_ai_user_memories | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| POST | `/api/ai/chat/message` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: actions, agent_intent, agent_usage, artifact, confidence, costs, intent, memory_candidates, message_id, reply, session_id | 表: qd_ai_copilot_sessions | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| POST | `/api/ai/chat/message/stream` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | SSE `text/event-stream`（非 JSON 信封） | 表: qd_ai_copilot_sessions | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/ai/chat/sessions` | Bearer JWT | 🟢 只读 | query: limit | code/msg/data 信封；data 由服务层构造，字段 unknown | 表: qd_ai_copilot_sessions | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| DELETE | `/api/ai/chat/sessions/<int:session_id>` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: session_id | 表: qd_ai_copilot_messages, qd_ai_copilot_sessions, qd_ai_copilot_tool_calls | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| GET | `/api/ai/chat/history` | Bearer JWT | 🟢 只读 | query: chatId, session_id | code/msg/data 信封；data: messages, session | 表: qd_ai_copilot_messages | 路由 confirmed；请求字段 confirmed；响应字段 confirmed |
| POST | `/api/ai/chat/message/local` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: message_id, session_id | 表: qd_ai_copilot_messages, qd_ai_copilot_sessions | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| POST | `/api/ai/chat/report/pdf` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/ai/chat/history/save` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |

### 指标编辑器 Indicator

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/indicator/getIndicators` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 表: qd_indicator_codes | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/indicator/saveIndicator` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: id, userid | 表: qd_indicator_codes | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| GET | `/api/indicator/versions` | Bearer JWT | 🟢 只读 | query: indicatorId, indicator_id | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/indicator/versions/<int:version_id>` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/indicator/versions/restore` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/indicator/deleteIndicator` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: unpublished | 表: qd_indicator_codes, qd_indicator_purchases | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| GET | `/api/indicator/getIndicatorParams` | Bearer JWT | 🟢 只读 | query: indicator_id | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| POST | `/api/indicator/chart-preview` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/indicator/aiGenerate` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/indicator/codeQualityHints` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: hints | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |

### 指标信号告警 Signal Alerts

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/indicator/signal-alerts` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/indicator/signal-alerts` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| PUT | `/api/indicator/signal-alerts/<int:task_id>` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| DELETE | `/api/indicator/signal-alerts/<int:task_id>` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/indicator/signal-alerts/<int:task_id>/pause` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/indicator/signal-alerts/<int:task_id>/resume` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/indicator/signal-alerts/<int:task_id>/test` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |

### 策略生命周期 Strategy

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/strategies` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/strategies/<int:strategy_id>` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/strategies` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| PUT | `/api/strategies/<int:strategy_id>` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| DELETE | `/api/strategies/<int:strategy_id>` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/strategies/<int:strategy_id>/start` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/strategies/<int:strategy_id>/stop` | Bearer JWT | 🔴 交易动作（停策略/收口持仓） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 券商/交易客户端（服务层） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/strategies/exchange/test` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/strategies/verify` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/strategies/generate` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |

### 交易所凭证 Credentials

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/credentials/desktop-brokers-policy` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: allow_local_desktop_brokers, disabled_message | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| GET | `/api/credentials/list` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: items | 表: qd_exchange_credentials | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| GET | `/api/credentials/egress-ip` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: ip, ipv4, ipv6 | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| POST | `/api/credentials/test` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: environment, market_scope, tested_markets | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| POST | `/api/credentials/create` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: id | 表: qd_exchange_credentials | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| PUT/PATCH | `/api/credentials/update-name` | Bearer JWT | 🟡 写操作（本地库/配置） | body: `id`（兼容 query `id`）, `name` | code/msg/data 信封；data 为更新后凭证行（`id, name, exchange_id, api_key_hint, created_at, updated_at`） | 表: qd_exchange_credentials | 路由 confirmed；请求字段 confirmed；响应字段 confirmed |
| DELETE | `/api/credentials/delete` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 表: qd_exchange_credentials | 路由 confirmed；请求字段 unknown；响应字段 unknown |

### 仪表盘 Dashboard

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/dashboard/summary` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: ai_strategy_count, calendar_months, current_positions, daily_pnl, daily_pnl_chart, hourly_distribution, monthly_returns, performance, recent_trades, running_bot_count, running_script_count, running_strategy_count, strategy_pnl_chart, strategy_stats, total_equity, total_pnl, total_realized_pnl, total_unrealized_pnl | 表: qd_quick_trades, qd_strategies_trading, qd_strategy_broker_activities, qd_strategy_funding_fees, qd_strategy_positions, qd_strategy_trades | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| GET | `/api/dashboard/pendingOrders` | Bearer JWT | 🟢 只读 | query: page, pageSize | code/msg/data 信封；data 由服务层构造，字段 unknown | 表: qd_strategies_trading | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| DELETE | `/api/dashboard/pendingOrders/<int:order_id>` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: id | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |

### 系统设置 Settings

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/settings/schema` | Bearer JWT+admin | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/settings/public-config` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: ccxt_default_exchange | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| GET | `/api/settings/brand-config` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/settings/values` | Bearer JWT+admin | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/settings/market-catalog` | Bearer JWT+admin | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/settings/market-catalog/sync` | Bearer JWT+admin | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/settings/save` | Bearer JWT+admin | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/settings/openrouter-balance` | Bearer JWT+admin | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: is_free_tier, label, limit, limit_remaining, rate_limit, usage | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| POST | `/api/settings/test-connection` | Bearer JWT+admin | 🟡 写操作（本地库/配置） | body: api_key, service | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |

### 组合与持仓 Portfolio

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/portfolio/positions` | Bearer JWT | 🟢 只读 | query: refresh | code/msg/data 信封；data 由服务层构造，字段 unknown | 表: qd_manual_positions | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| POST | `/api/portfolio/positions` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: id | 表: qd_manual_positions | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| PUT | `/api/portfolio/positions/<int:position_id>` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 表: qd_manual_positions | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| DELETE | `/api/portfolio/positions/<int:position_id>` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 表: qd_manual_positions | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/portfolio/summary` | Bearer JWT | 🟢 只读 | query: refresh | code/msg/data 信封；data 由服务层构造，字段 unknown | 表: qd_manual_positions | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/portfolio/monitors` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 表: qd_position_monitors | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/portfolio/monitors` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: id | 表: qd_position_monitors | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| PUT | `/api/portfolio/monitors/<int:monitor_id>` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 表: qd_position_monitors | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| DELETE | `/api/portfolio/monitors/<int:monitor_id>` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 表: qd_position_monitors | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/portfolio/monitors/<int:monitor_id>/run` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: message, status | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| GET | `/api/portfolio/alerts` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 表: qd_manual_positions, qd_position_alerts | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/portfolio/alerts` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: id | 表: qd_manual_positions, qd_position_alerts | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| PUT | `/api/portfolio/alerts/<int:alert_id>` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 表: qd_position_alerts | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| DELETE | `/api/portfolio/alerts/<int:alert_id>` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 表: qd_position_alerts | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/portfolio/groups` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: groups, ungrouped_count | 表: qd_manual_positions | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| POST | `/api/portfolio/groups/rename` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 表: qd_manual_positions | 路由 confirmed；请求字段 unknown；响应字段 unknown |

### IBKR 券商

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/ibkr/status` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/ibkr/connect` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/ibkr/disconnect` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/ibkr/account` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/ibkr/positions` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/ibkr/orders` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/ibkr/order` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data: avgPrice, filled, orderId, raw, status | 券商/交易客户端（服务层） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| DELETE | `/api/ibkr/order/<int:order_id>` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 券商/交易客户端（服务层） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/ibkr/quote` | Bearer JWT | 🟢 只读 | query: marketType, symbol | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |

### Alpaca 券商

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/alpaca/status` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/alpaca/connect` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/alpaca/disconnect` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/alpaca/account` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/alpaca/positions` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/alpaca/orders` | Bearer JWT | 🟢 只读 | query: limit, status | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| POST | `/api/alpaca/order` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data: avgPrice, filled, orderId, raw, status | 券商/交易客户端（服务层） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| DELETE | `/api/alpaca/order/<order_id>` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 券商/交易客户端（服务层） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/alpaca/quote/<symbol>` | Bearer JWT | 🟢 只读 | query: marketType | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |

### 全球市场 Global Market

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/global-market/overview` | Bearer JWT | 🟢 只读 | query: force | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/global-market/heatmap` | Bearer JWT | 🟢 只读 | query: force | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/global-market/news` | Bearer JWT | 🟢 只读 | query: force, lang | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/global-market/calendar` | Bearer JWT | 🟢 只读 | query: force | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/global-market/sentiment` | Bearer JWT | 🟢 只读 | query: force | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/global-market/adanos-sentiment` | Bearer JWT | 🟢 只读 | query: days, force, source, tickers | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/global-market/opportunities` | Bearer JWT | 🟢 只读 | query: force | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| POST | `/api/global-market/refresh` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |

### 指标社区 Community

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/community/indicators` | Bearer JWT | 🟢 只读 | query: asset_type, code_visibility, keyword, max_price, min_price, page, page_size, pricing_type, sort_by, vip_free | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/community/indicators/<int:indicator_id>` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/community/indicators/<int:indicator_id>/purchase` | Bearer JWT | 💰 资金/权益动作 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/community/indicators/<int:indicator_id>/sync` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/community/my-purchases` | Bearer JWT | 🟢 只读 | query: page, page_size | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/community/author/summary` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/community/author/published` | Bearer JWT | 🟢 只读 | query: page, page_size | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/community/author/sales` | Bearer JWT | 🟢 只读 | query: indicator_id, page, page_size | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| POST | `/api/community/author/indicators/<int:indicator_id>/unpublish` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/community/indicators/<int:indicator_id>/comments` | Bearer JWT | 🟢 只读 | query: page, page_size | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| POST | `/api/community/indicators/<int:indicator_id>/comments` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| PUT | `/api/community/indicators/<int:indicator_id>/comments/<int:comment_id>` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/community/indicators/<int:indicator_id>/my-comment` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/community/indicators/<int:indicator_id>/performance` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/community/admin/pending-indicators` | Bearer JWT | 🟢 只读 | query: asset_type, keyword, page, page_size, pricing_type, review_status, sort_by | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/community/admin/review-stats` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/community/admin/indicators/<int:indicator_id>/review` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/community/admin/indicators/<int:indicator_id>/unpublish` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| DELETE | `/api/community/admin/indicators/<int:indicator_id>` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |

### 快速分析 Fast Analysis

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| POST | `/api/fast-analysis/analyze` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: credits_charged, current, in_progress, market, memory_id, remaining_credits, required, shortage, status, symbol, task_id, timeframe | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| GET | `/api/fast-analysis/history` | Bearer JWT | 🟢 只读 | query: days, limit, market, symbol | code/msg/data 信封；data: items, total | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 confirmed |
| GET | `/api/fast-analysis/history/all` | Bearer JWT | 🟢 只读 | query: page, pagesize | code/msg/data 信封；data: list, page, pagesize, total | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 confirmed |
| DELETE | `/api/fast-analysis/history/<int:memory_id>` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/fast-analysis/feedback` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/fast-analysis/performance` | Bearer JWT | 🟢 只读 | query: days, market, symbol | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/fast-analysis/similar-patterns` | Bearer JWT | 🟢 只读 | query: market, symbol | code/msg/data 信封；data: current_indicators, patterns | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 confirmed |

### 计费 Billing

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/billing/plans` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: billing, plans | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| GET | `/api/billing/usdt/chains` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: billing_enabled, chains | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| POST | `/api/billing/usdt/create` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/billing/usdt/order/<int:order_id>` | Bearer JWT | 🟢 只读 | query: refresh | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |

### 快速交易 Quick Trade

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| POST | `/api/quick-trade/place-order` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: avg_price, exchange_order_id, filled, margin_amount, notional_amount, protection_error, protection_status, status, trade_id | 券商/交易客户端（服务层） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| GET | `/api/quick-trade/balance` | Bearer JWT | 🟢 只读 | query: credential_id, market_type | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/quick-trade/position` | Bearer JWT | 🟢 只读 | query: credential_id, market_type, symbol | code/msg/data 信封；data: positions | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 confirmed |
| POST | `/api/quick-trade/close-position` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: avg_price, close_scope, closed_size, exchange_order_id, filled, position_side, status, tracked_net_base, trade_id | 表: qd_quick_trades | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| GET | `/api/quick-trade/history` | Bearer JWT | 🟢 只读 | query: limit, offset | code/msg/data 信封；data: trades | 表: qd_quick_trades | 路由 confirmed；请求字段 confirmed；响应字段 confirmed |

### AI 验证层（硬编码演示数据）

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/validation/status` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: connected, healthy, modules, total | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| GET | `/api/validation/audit-logs` | 公开（无鉴权装饰器） | 🟢 只读 | query: limit | code/msg/data 信封；data: logs, total | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 confirmed |
| GET | `/api/validation/stress-test` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: overall_risk_score, risk_level, scenarios, summary, survived, total_scenarios | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |

### 风控与市场状态 Risk

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/risk/positions` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/risk/portfolio` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/risk/regime` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/risk/alerts` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/risk/let-profit-run/demo` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/risk/structure` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/risk/structure/demo` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |

### 交易成本与数据治理 TCA

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| POST | `/api/tca/estimate-cost` | 公开（无鉴权装饰器） | 🟡 写操作（本地库/配置） | body: order_type, price, quantity, side, symbol, volatility | success 信封；data: breakdown, cost_bps, order_id, total_cost | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 confirmed |
| GET | `/api/tca/cost-summary` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/tca/diagnose-gap` | 公开（无鉴权装饰器） | 🟡 写操作（本地库/配置） | body: backtest_returns, live_returns, total_trades | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| POST | `/api/tca/data-quality-check` | 公开（无鉴权装饰器） | 🟡 写操作（本地库/配置） | body: data, dataset_name | success 信封；data: dimensions, issue_count, quality_level, quality_score, recommendations | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 confirmed |

### P1 模块

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/p1/health` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/p1/health/report` | 公开（无鉴权装饰器） | 🟡 写操作（本地库/配置） | body: error_message, response_time_ms, service_name, status | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/p1/failures` | 公开（无鉴权装饰器） | 🟢 只读 | query: limit | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/p1/journal/analyze` | 公开（无鉴权装饰器） | 🟢 只读 | query: days, strategy_id | success 信封；data: behavioral_biases, expectancy, period, profit_factor, recommendations, total_pnl, total_trades, win_rate | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 confirmed |
| GET | `/api/p1/security/summary` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/p1/security/alerts` | 公开（无鉴权装饰器） | 🟢 只读 | query: limit | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/p1/strategy-matcher/summary` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/p1/strategy-matcher/match` | 公开（无鉴权装饰器） | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data: current_regime, matches | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| GET | `/api/p1/strategy-matcher/demo` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/p1/position-sizing/summary` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/p1/position-sizing/calculate` | 公开（无鉴权装饰器） | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data: method_used, position_pct, position_size, position_value, risk_amount, risk_pct | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| GET | `/api/p1/position-sizing/demo` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/p1/market-analysis/demo` | 公开（无鉴权装饰器） | 🟢 只读 | query: symbol | success 信封；data: atr, current_price, note, recent_swing_high, recent_swing_low, regime, regime_confidence, regime_features, resistance_levels, structure_bias, support_levels, symbol, timestamp, trend_strength, volatility | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 confirmed |
| GET | `/api/p1/market-layers/summary` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data: core_principle, layers, total | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| GET | `/api/p1/market-layers/demo` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/p1/optimizer/status` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/p1/optimizer/factors` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data: categories, factors, total | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| GET | `/api/p1/optimizer/history` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data: history, total | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| GET | `/api/p1/overfitting/status` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/p1/strategy-health/summary` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |

### P2 模块

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/p2/crowding/summary` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/p2/crowding/strategies` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/p2/crowding/update` | 公开（无鉴权装饰器） | 🟡 写操作（本地库/配置） | body: alpha_decay, sharpe_trend, signal_correlation, strategy_name, symbol, transaction_cost_change | success 信封；data: crowding_level, crowding_score, recommendation | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 confirmed |
| GET | `/api/p2/observability/golden-signals` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/p2/observability/alerts` | 公开（无鉴权装饰器） | 🟢 只读 | query: limit | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/p2/observability/summary` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/p2/cicd/status` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/p2/cicd/deployments` | 公开（无鉴权装饰器） | 🟢 只读 | query: limit | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/p2/websocket/status` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/p2/websocket/degradation` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| GET | `/api/p2/websocket/demo` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |

### 旧版账户（遗留 · success 信封）

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| POST | `/api/account/test-connection` | 公开（无鉴权装饰器） | 🟡 写操作（本地库/配置） | body: api_key, api_secret, exchange, passphrase | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| POST | `/api/account/save` | 公开（无鉴权装饰器） | 🟡 写操作（本地库/配置） | body: api_key, api_secret, exchange, name, passphrase, permissions | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/account/list` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data: accounts, total | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| GET | `/api/market/kline` | 公开（无鉴权装饰器） | 🟢 只读 | query: bar, limit, symbol | success 信封；data: bar, candles, count, symbol | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 confirmed |
| GET | `/api/market/ticker` | 公开（无鉴权装饰器） | 🟢 只读 | query: symbol | success 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| POST | `/api/account/place-order` | 公开（无鉴权装饰器） | 🔴 交易动作 | body: price, side, size, symbol | success 信封；data 由服务层构造，字段 unknown | 券商/交易客户端（服务层） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/account/positions` | 公开（无鉴权装饰器） | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | success 信封；data: count, positions, total_equity | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |

### 策略脚本源 Script Sources

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/strategies/script-templates` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: items | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| GET | `/api/strategies/script-sources` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: items | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| GET | `/api/strategies/script-sources/detail` | Bearer JWT | 🟢 只读 | query: id | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| POST | `/api/strategies/script-sources/create` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| PUT/POST | `/api/strategies/script-sources/update` | Bearer JWT | 🟡 写操作（本地库/配置） | query: id | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| POST | `/api/strategies/script-sources/compile` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: backtestRangePolicy, manifest | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| DELETE/POST | `/api/strategies/script-sources/delete` | Bearer JWT | 🟡 写操作（本地库/配置） | query: id | code/msg/data 信封；data: id | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 confirmed |
| GET | `/api/strategies/script-sources/versions` | Bearer JWT | 🟢 只读 | query: sourceId | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/strategies/script-sources/versions/<int:version_id>` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/strategies/script-sources/versions/restore` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: code_hidden, source_id | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| POST | `/api/strategies/script-sources/publish` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: requires_backtest, source_id | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |

### 策略账户连接

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/account/snapshot` | Bearer JWT | 🟢 只读 | query: credential_id | code/msg/data 信封；data: open_orders, spot_positions, swap_positions | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 confirmed |
| GET | `/api/account/positions` | Bearer JWT | 🟢 只读 | query: credential_id, market_type | code/msg/data 信封；data: items, positions, total_equity | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 confirmed |
| GET | `/api/account/exchange-connections` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/account/exchange-connections/test` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/account/exchange-connections/test-strategy` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |

### 策略资产

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/strategy-assets` | Bearer JWT | 🟢 只读 | query: assetType, keyword, q, type | code/msg/data 信封；data: counts, items | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 confirmed |

### 策略偏离

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/strategies/dry-run-deviation` | Bearer JWT | 🟢 只读 | query: id, limit | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |

### 策略执行器

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/strategies/executors/templates` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: items | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| POST | `/api/strategies/executors/preview` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/strategies/executors/generate` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: code, compatibility, market_category, market_type, metadata, strategy_name, strategy_type, symbol, template_key, timeframe, trade_direction, trading_config | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| POST | `/api/strategies/executors/create` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: id, source_id, strategy | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 confirmed |

### 策略网格

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/strategies/grid-resting-orders` | Bearer JWT | 🟢 只读 | query: id, lang, limit, status, sync | code/msg/data 信封；data: items, orders, summary | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 confirmed |

### 策略台账

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/strategies/trades` | Bearer JWT | 🟢 只读 | query: id, lang | code/msg/data 信封；data: cost_summary, items, trades | 表: qd_strategy_trades | 路由 confirmed；请求字段 confirmed；响应字段 confirmed |
| GET | `/api/strategies/equityCurve` | Bearer JWT | 🟢 只读 | query: id | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |
| GET | `/api/strategies/performance` | Bearer JWT | 🟢 只读 | query: id | code/msg/data 信封；data: equity_curve, initial_equity, latest_equity, max_drawdown, max_drawdown_pct, points, total_return, total_return_pct | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 confirmed |

### 策略日志

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/strategies/logs` | Bearer JWT | 🟢 只读 | query: id, limit | code/msg/data 信封；data 由服务层构造，字段 unknown | 表: qd_strategy_logs | 路由 confirmed；请求字段 confirmed；响应字段 unknown |

### 策略通知

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/strategies/notifications` | Bearer JWT | 🟢 只读 | query: id, limit, since_id | code/msg/data 信封；data: items | 表: qd_strategy_notifications | 路由 confirmed；请求字段 confirmed；响应字段 confirmed |
| GET | `/api/strategies/notifications/unread-count` | Bearer JWT | 🟢 只读 | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data: unread | 表: qd_strategy_notifications | 路由 confirmed；请求字段 unknown；响应字段 confirmed |
| POST | `/api/strategies/notifications/read` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 表: qd_strategies_trading, qd_strategy_notifications | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| POST | `/api/strategies/notifications/read-all` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 表: qd_strategies_trading, qd_strategy_notifications | 路由 confirmed；请求字段 unknown；响应字段 unknown |
| DELETE | `/api/strategies/notifications/clear` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 表: qd_strategies_trading, qd_strategy_notifications | 路由 confirmed；请求字段 unknown；响应字段 unknown |

### 策略持仓

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/strategies/positions` | Bearer JWT | 🟢 只读 | query: id | code/msg/data 信封；data: account_reconciliation, account_risk, exchange_snapshot, items, position_meta, positions | 表: qd_strategy_positions | 路由 confirmed；请求字段 confirmed；响应字段 confirmed |

### 策略持仓归属

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| GET | `/api/strategies/position-ownership` | Bearer JWT | 🟢 只读 | query: id | code/msg/data 信封；data: advanced_coexistence_available, credential_id, items, market_type, status | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 confirmed |
| POST | `/api/strategies/position-ownership/repair` | Bearer JWT | 🟡 写操作（本地库/配置） | 见对应 Schema；路由层未字面解析（unknown） | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 unknown；响应字段 unknown |

### 策略复盘

| 方法 | 路径 | 鉴权 | 动作 | 请求参数 / Body | 响应 data | 数据源 / 口径 | 置信度 |
|---|---|---|---|---|---|---|---|
| POST | `/api/strategies/review-report` | Bearer JWT | 🟡 写操作（本地库/配置） | query: id, include_ai, lang, lookback_days | code/msg/data 信封；data: current, detail, error_type, feature, required, shortage | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 confirmed |
| GET | `/api/strategies/review-report/history` | Bearer JWT | 🟢 只读 | query: id, limit, report_id, strategy_id | code/msg/data 信封；data 由服务层构造，字段 unknown | 服务层/内存缓存（路由层未见表名） | 路由 confirmed；请求字段 confirmed；响应字段 unknown |

## 7. Agent 网关路由清单（`/api/agent/v1`）

> 独立 Agent token 鉴权；scope 含义见 §2.2。`/admin/*`、`/me/*` 为人类会话 JWT。字段结构以 `agent-openapi.json` 与 `services` 为准。

| 方法 | 路径 | 鉴权 scope | 动作 | 口径 |
|---|---|---|---|---|
| POST | `/api/agent/v1/admin/tokens` | JWT+admin（人类会话） | 🟡 写/副作用 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/admin/tokens` | JWT+admin（人类会话） | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| DELETE | `/api/agent/v1/admin/tokens/<int:token_id>` | JWT+admin（人类会话） | 🟡 写/副作用 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/admin/audit` | JWT+admin（人类会话） | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| POST | `/api/agent/v1/backtest/run` | Agent token · B 回测/模拟 | 🟡 写/副作用 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/health` | 公开(health) | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/whoami` | Agent token · R 只读 | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/indicators/authoring-contract` | Agent token · R 只读 | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/indicators` | Agent token · R 只读 | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/indicators/<int:indicator_id>` | Agent token · R 只读 | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| POST | `/api/agent/v1/indicators/validate` | Agent token · R 只读 | 🧮 计算（R scope） | 服务层委托；字段详见 agent-openapi.json |
| POST | `/api/agent/v1/indicators` | Agent token · W 工作区写 | 🟡 写/副作用 | 服务层委托；字段详见 agent-openapi.json |
| POST | `/api/agent/v1/indicators/link-config` | Agent token · W 工作区写 | 🟡 写/副作用 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/jobs` | Agent token · R 只读 | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/jobs/<job_id>` | Agent token · R 只读 | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| POST | `/api/agent/v1/jobs/<job_id>/cancel` | Agent token · B 回测/模拟 | 🟡 写/副作用 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/jobs/<job_id>/stream` | Agent token · R 只读 | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/markets` | Agent token · R 只读 | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/markets/<market>/symbols` | Agent token · R 只读 | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/klines` | Agent token · R 只读 | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/price` | Agent token · R 只读 | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/me/tokens/policy` | JWT（人类会话） | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| POST | `/api/agent/v1/me/tokens` | JWT（人类会话） | 🟡 写/副作用 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/me/tokens` | JWT（人类会话） | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| DELETE | `/api/agent/v1/me/tokens/<int:token_id>` | JWT（人类会话） | 🟡 写/副作用 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/me/audit` | JWT（人类会话） | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/notifications/signal-alerts` | Agent token · N 通知副作用 | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| POST | `/api/agent/v1/notifications/signal-alerts` | Agent token · N 通知副作用 | 🟡 写/副作用 | 服务层委托；字段详见 agent-openapi.json |
| PATCH | `/api/agent/v1/notifications/signal-alerts/<int:task_id>` | Agent token · N 通知副作用 | 🟡 写/副作用 | 服务层委托；字段详见 agent-openapi.json |
| DELETE | `/api/agent/v1/notifications/signal-alerts/<int:task_id>` | Agent token · N 通知副作用 | 🟡 写/副作用 | 服务层委托；字段详见 agent-openapi.json |
| POST | `/api/agent/v1/notifications/signal-alerts/<int:task_id>/status` | Agent token · N 通知副作用 | 🟡 写/副作用 | 服务层委托；字段详见 agent-openapi.json |
| POST | `/api/agent/v1/notifications/signal-alerts/<int:task_id>/run` | Agent token · N 通知副作用 | 🟡 写/副作用 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/portfolio/positions` | Agent token · R 只读 | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/portfolio/paper-orders` | Agent token · R 只读 | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| POST | `/api/agent/v1/quick-trade/orders` | Agent token · T 交易/资金 | 🔴 交易/资金 | 服务层委托；字段详见 agent-openapi.json |
| POST | `/api/agent/v1/quick-trade/kill-switch` | Agent token · T 交易/资金 | 🔴 交易/资金 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/research/universes` | Agent token · R 只读 | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/research/universes/<int:universe_id>` | Agent token · R 只读 | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/research/universes/<int:universe_id>/members` | Agent token · R 只读 | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/research/factors` | Agent token · R 只读 | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/research/factors/<factor_id>` | Agent token · R 只读 | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/research/watchlist` | Agent token · R 只读 | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| POST | `/api/agent/v1/research/watchlist` | Agent token · W 工作区写 | 🟡 写/副作用 | 服务层委托；字段详见 agent-openapi.json |
| DELETE | `/api/agent/v1/research/watchlist` | Agent token · W 工作区写 | 🟡 写/副作用 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/runtime/overview` | Agent token · R 只读 | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| POST | `/api/agent/v1/strategies/<int:strategy_id>/stop` | Agent token · T 交易/资金 | 🔴 交易/资金 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/strategies` | Agent token · R 只读 | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/strategies/<int:strategy_id>` | Agent token · R 只读 | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| POST | `/api/agent/v1/strategies` | Agent token · W 工作区写 | 🟡 写/副作用 | 服务层委托；字段详见 agent-openapi.json |
| PATCH | `/api/agent/v1/strategies/<int:strategy_id>` | Agent token · W 工作区写 | 🟡 写/副作用 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/strategy-sources/authoring-contract` | Agent token · R 只读 | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/strategy-sources/templates` | Agent token · R 只读 | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| POST | `/api/agent/v1/strategy-sources/compile` | Agent token · R 只读 | 🧮 计算（R scope） | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/strategy-sources` | Agent token · R 只读 | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/strategy-sources/<int:source_id>` | Agent token · R 只读 | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| POST | `/api/agent/v1/strategy-sources` | Agent token · W 工作区写 | 🟡 写/副作用 | 服务层委托；字段详见 agent-openapi.json |
| PATCH | `/api/agent/v1/strategy-sources/<int:source_id>` | Agent token · W 工作区写 | 🟡 写/副作用 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/strategy-sources/<int:source_id>/versions` | Agent token · R 只读 | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| POST | `/api/agent/v1/strategy-sources/<int:source_id>/versions/<int:version_id>/restore` | Agent token · W 工作区写 | 🟡 写/副作用 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/trading/accounts` | Agent token · R 只读 | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/trading/accounts/<int:credential_id>/snapshot` | Agent token · R 只读 | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/trading/accounts/<int:credential_id>/positions` | Agent token · R 只读 | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/trading/strategies/<int:strategy_id>/positions` | Agent token · R 只读 | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/trading/strategies/<int:strategy_id>/trades` | Agent token · R 只读 | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/trading/strategies/<int:strategy_id>/pending-orders` | Agent token · R 只读 | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |
| GET | `/api/agent/v1/trading/quick-trades` | Agent token · R 只读 | 🟢 只读 | 服务层委托；字段详见 agent-openapi.json |


---

## 8. 未挂载 / 遗留 / 演示数据端点

### 8.1 未挂载（代码存在但蓝图未注册，不可达）

`app/routers/market_analysis.py` 的 `bp` 未被任何 `register_blueprint` 引用，以下路由在当前装配下**不可达**（遗留代码）：

- GET `/api/market-analysis/demo`
- GET `/api/market-analysis/layers`

### 8.2 旧版遗留端点（`account.py`，success 信封，无鉴权装饰器）

- POST `/api/account/test-connection`：body `{ exchange, api_key, api_secret, passphrase }`；成功 `{ success, message, data: balance_data }`
- POST `/api/account/save`：body `{ name, exchange, api_key, api_secret, passphrase, permissions }`；凭证存内存 `_account_configs`（DEMO）
- GET `/api/account/list`：`data: { accounts, total }`
- GET `/api/market/kline`：query `symbol, bar, limit`；`data: { symbol, bar, candles, count }`
- GET `/api/market/ticker`：query `symbol`；`data: ticker`
- POST `/api/account/place-order`：见 4.1
- GET `/api/account/positions`：`data: { total_equity, positions, count }`

### 8.3 硬编码演示 / 模拟数据（非真实计算，confirmed）

- `validation.py` 全部：`/status`、`/audit-logs`、`/stress-test`（模块内硬编码列表与数值）。
- `risk.py`：`/let-profit-run/demo`、`/structure/demo`（硬编码阶段/概念数据）。
- `p1_modules.py`：`/strategy-matcher/demo`、`/position-sizing/demo`、`/market-analysis/demo`、`/market-layers/demo`、`/strategy-health/summary`（注入 `demo_strategies`）。
- `p2_modules.py`：`/websocket/demo`。
- `p1_modules.py` `/market-layers/demo` 用 `random.uniform` 生成随机 K 线（复核到 `p1_modules.py` 内 `random.uniform(-0.015, 0.015)` 与成交量随机数）。confirmed

---

## 9. 旧文档勘误（原 `API_DOCUMENTATION.md` 与代码不符）

| 旧文档写法 | 代码真实情况 | 置信度 |
|---|---|---|
| 登录 body 含 `captcha`；响应 `data.user` | 无 `captcha`；真实 `turnstile_token` / `turnstile_clearance`；响应为 `data.userinfo`（结构见 §3） | confirmed |
| `POST /api/strategy/create`、`GET /api/strategy/list`、`PUT /api/strategy/update/<id>`、`POST /api/strategy/start/<id>`、`POST /api/strategy/stop/<id>`、`DELETE /api/strategy/delete/<id>` | 真实为 `POST /api/strategies`、`GET /api/strategies`、`PUT /api/strategies/<id>`、`POST /api/strategies/<id>/start`、`POST /api/strategies/<id>/stop`、`DELETE /api/strategies/<id>` | confirmed |
| `/api/market/symbols`、`/ticker/<symbol>`、`/orderbook/<symbol>`、`/kline/<symbol>` | 这些 HTTP 路由不存在；真实 `/api/market/symbols/search`、`/api/market/symbols/hot`、`/api/market/price`、`/api/indicator/kline` | confirmed |
| `/api/portfolio/overview`、`/api/portfolio/trades`、`/api/portfolio/performance` | 不存在；真实 `/api/portfolio/summary`；交易/绩效在 `/api/strategies/trades`、`/api/strategies/performance` | confirmed |
| `POST /api/quick-trade/order` | 真实 `POST /api/quick-trade/place-order` | confirmed |
| `ws://localhost:5000/ws` 及 ticker/positions/orders/signals 订阅频道 | 代码中**无 Flask WebSocket 服务端路由**；出站 WS 仅用于连接交易所行情/私有频道。该浏览器 WS 订阅契约 unknown | confirmed（无服务端 WS 路由）/ unknown（前端实际来源） |
| 限流数值（认证 10 / 查询 100 / 交易 30 次每分钟）、业务错误码 1001–2002 | 代码未证实 | unknown |
| 旧文档示例绩效（sharpe 1.85、max_drawdown -15.2、win_rate 55.6 等） | 为占位数字，非代码输出；本版不再保留 | confirmed |

---

## 10. 未验证项

1. 所有标 `unknown` 的 `data` 子字段未逐一展开到 service / dataclass / schema；需二次核对 `services/*.py` 与 `openapi/schemas`。
2. 静态提取器对 `data = request.get_json() or {}` 这类 `BinOp` 解构的 body 键覆盖不全；相应行请求字段标 unknown，需对照源码（已人工复核 `credentials/update-name`）。
3. 未启动服务、未发真实请求；HTTP 状态码、限流响应头、MFA `challenge` 具体字段、USDT 订单 `data` 结构以运行时为准。
4. 前端实际请求字段与后端 schema 的逐条一致性，不在本次后端审计范围内。
5. 券商/交易所差异、实盘下单、经纪商连接冒烟、DEMO→实盘切换：**未验证**。
6. 策略脚本运行时能否读取外部情绪/新闻/宏观数据源：unknown（见 §5）。
