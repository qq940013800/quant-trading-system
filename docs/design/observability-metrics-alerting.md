# 可观测指标清单与告警骨架（只读盘点 + 待评审契约）

> 状态：**待评审草稿**。本轮只产出文档，不实现生产代码，不接生产告警通道，不落地告警规则文件。
> 边界：不改交易路由 / 风控 gate / 下单平仓 / 资金计算；不碰 `configs/`、`registry.yaml`、`mt5/`、`secrets/`、`runtime/`、`ledger/`；不改 schema；不删文件。
> 阈值原则：**所有告警阈值先以占位形式文档化；正式阈值必须由 CLEAN 集分布校准（分位数/基线），禁止按绩效网格搜索产生**（对齐 `AGENTS.md` 不变量与 `docs/RULES.md` 过拟合防御铁律）。
> 证据等级：`confirmed`（代码/配置中直接读到落点或指标名）、`inferred`（由现有表/日志/事件结构推断，未在生产指标面直接暴露）、`unknown`（当前代码库无法确认口径或存在性）。

---

## 0. 本轮盘点范围与已读证据

| 类别 | 已读对象 | 路径 |
|---|---|---|
| 项目规则 | 不可协商不变量、硬规则、停止条件 | `AGENTS.md` |
| 既有监控文档 | 三层监控模型、黄金四指标、草稿告警规则 | `docs/MONITORING_ALERTING.md` |
| 后端可观测代码 | HTTP 中间件、Prometheus 指标、请求上下文 | `backend_api_python/app/observability/{__init__.py,http.py,metrics.py,context.py}` |
| 告警配置 | Prometheus 抓取/规则、Alertmanager | `ops/prometheus/prometheus.yml`、`ops/prometheus/alerts.yml`、`ops/rules.yml`、`ops/alertmanager.yml` |
| 日志基建 | 结构化/文本日志、轮转文件、request_id 注入 | `backend_api_python/app/utils/logger.py` |
| 交易/风控/订单链路 | 风控引擎、快捷交易错误归类、执行流事件、策略指令、权益快照、运行日志 | `app/services/risk_engine.py`、`app/services/quick_trade/errors.py`、`app/services/execution_streams/events.py`、`app/services/strategy_command_repository.py`、`app/services/strategy_daily_pnl.py`、`app/utils/strategy_runtime_logs.py` |
| 既有内存告警服务 | 进程内 Metric/Alert/AlertRule 单例 | `app/services/observability.py`、`app/routes/p2_modules.py` |

### 0.1 现有 Prometheus 指标（confirmed，`metrics.py`）

| 指标名 | 类型 | 标签 | 落点 | 证据 |
|---|---|---|---|---|
| `quantdinger_http_requests_total` | Counter | `method`, `route`, `status` | API 请求计数 | `observability/metrics.py:28-32`；中间件自增 `observability/http.py:40-45`；暴露于 `GET /metrics` `openapi/routes/health.py:115-123` |
| `quantdinger_http_request_duration_seconds` | Histogram | `method`, `route` | API 请求耗时分布 | `metrics.py:33-38`；`http.py:45` |
| `quantdinger_http_requests_in_progress` | Gauge | `method` | 进行中请求数 | `metrics.py:39-44`；`http.py:33,52` |
| `quantdinger_workers_healthy` | Gauge | `role` | 新鲜心跳 worker 数 | `metrics.py:45-50`；SQL 源表 `qd_worker_heartbeats` `metrics.py:81-101` |
| `quantdinger_workers_stale` | Gauge | `role` | 心跳过期 worker 数 | `metrics.py:51-56`；同上 |
| `quantdinger_strategy_commands` | Gauge | `status` | 近 24h 持久化指令计数 | `metrics.py:57-62`；SQL 源表 `qd_strategy_commands` `metrics.py:103-114` |
| `quantdinger_build_info` | Gauge | `version`, `role` | 构建/进程角色 | `metrics.py:63-69` |

### 0.2 现有告警规则（confirmed，`ops/prometheus/alerts.yml`）

| 告警名 | 表达式口径 | 级别 | 覆盖面 |
|---|---|---|---|
| `QuantDingerApiDown` | `up{job="quantdinger-api"} == 0` 持续 2m | critical | API 存活 |
| `QuantDingerWorkerMissing` | `quantdinger_workers_healthy{role=~"trading|scheduler|celery"} < 1` 持续 2m | critical | worker 存活 |
| `QuantDingerHighApiErrorRate` | 5m 内 5xx 请求占比 > 5%，持续 5m | warning | API 错误率 |
| `QuantDingerSlowApi` | P95 延迟 > 2s，持续 10m | warning | API 延迟 |
| `QuantDingerStrategyCommandFailures` | `quantdinger_strategy_commands{status="failed"} > 0`，持续 5m | warning | 持久化指令失败 |
| `QuantDingerPostgresExporterDown` | `up{job="postgres"} == 0` 持续 3m | warning | DB exporter |
| `QuantDingerRedisExporterDown` | `up{job=~"redis-cache|redis-jobs"} == 0` 持续 3m | warning | Redis exporter |

> 另有 `ops/rules.yml` 一条 `BackendDown`（`up{job="quantdinger-backend"} == 0`，1m，critical）；`prometheus.yml` 只挂载 `/etc/prometheus/alerts.yml`，`rules.yml` 是否被实际加载在当前配置中 **unknown**。
> `docs/MONITORING_ALERTING.md` 中的订单成功率、回撤、策略收益、滑点、保证金使用率等阈值（如 <95%、>5% 等）属于**概念稿/样例值**，未在 `alerts.yml` 落地，也未对应生产指标；**不视为已校准基线**。

### 0.3 现有日志与事件落点（confirmed / inferred）

| 落点 | 类型 | 说明 | 证据 |
|---|---|---|---|
| 进程结构化/文本日志 | 日志流 | `StreamHandler` + `RotatingFileHandler`（`logs/<role>.log`，10MB×5，UTF-8）；JSON 格式时带 `timestamp/level/logger/message/process_role/request_id/exception` | `utils/logger.py:38-83`；`request_id` 来自 `observability/context.py:6` |
| `qd_strategy_logs` | 数据库表 | 策略运行日志行（`strategy_id/level/message/timestamp`） | `utils/strategy_runtime_logs.py:13-26` |
| `qd_strategy_equity_snapshots` | 数据库表 | 逐策略权益快照（`equity/realized_pnl/unrealized_pnl/initial_capital/basis_reason/captured_at`），运行中 300s 采样、空闲 24h 采样 | `services/strategy_daily_pnl.py:28,260-308` |
| `qd_strategy_trades` / `qd_quick_trades` | 数据库表 | 策略成交事件 / 快捷交易成交记录 | `routes/dashboard.py:466-533`；`routes/agent_v1/trading_data.py:142,213` |
| `qd_execution_events` | 数据库表 | 执行流规范事件（`order_status/price/quantity/fee_status/occurred_at/raw_json`） | `services/execution_streams/repository.py:82-123`；事件模型 `events.py:67-116` |
| `qd_strategy_commands` | 数据库表 | 持久化指令，终态 `succeeded/failed/cancelled`，失败带 `error_message` | `services/strategy_command_repository.py:13,156-198` |
| 风控引擎内存告警 | 进程内列表 | `RiskAlert`（`level/alert_type/message/position_id/symbol/action_required`），经 `GET /api/risk/alerts` 暴露最近 50 条 | `services/risk_engine.py:117-126,567-585`；`routes/risk.py:74-99` |
| 内存可观测单例 | 进程内字典/列表 | `Metric`/`Alert`/`AlertRule`，仅保留最近 1000 点；经 `/api/p2/observability/golden-signals|alerts|summary` 暴露 | `services/observability.py:83-289`；`routes/p2_modules.py:77-111` |

---

## 1. 五类指标清单（现状盘点）

状态图例：**已有** = 指标/计数器在生产指标面或持久化事件中直接可读；**部分** = 有原始事件/日志/内存结构，但未聚合为 Prometheus 指标或缺少关键标签；**缺失** = 当前代码库无对应落点，需新增只读聚合契约（见第 2 节）。

### 1.1 账户权益变化

| # | 期望观测 | 现状状态 | 现有落点 / 指标名 | 证据等级与位置 | 缺口说明 |
|---|---|---|---|---|---|
| E1 | 账户/策略当前权益（gauge） | 部分 | `qd_strategy_equity_snapshots.equity`（逐策略，300s/24h 采样） | confirmed：`strategy_daily_pnl.py:285-308`；HTTP 侧 `total_equity` 为 best-effort 拼装 `routes/strategy_account_routes.py:90-111`、`routes/dashboard.py:594-716` | 未暴露为 Prometheus gauge；无统一账户级（跨凭证/跨策略）权益口径；`total_equity` 在部分路径是字符串 `$` 格式化值，不能直接做数值聚合 |
| E2 | 权益增量 / 日内已实现+未实现盈亏 | 部分 | `realized_pnl`、`unrealized_pnl`、`initial_capital`、`basis_reason` 列 | confirmed：`strategy_daily_pnl.py:285-307,335-360` | 无速率/增量指标；未区分真实 0 与缺值；账户级 PnL 未聚合 |
| E3 | 权益回撤（相对权益峰值） | 缺失 | 仅 `docs/MONITORING_ALERTING.md` 概念稿 `account_drawdown` | inferred：快照表可推导峰值与回撤，但代码中未见回撤指标计算或落库字段；`risk_engine.py` 有组合最大回撤强制平仓逻辑（`max_drawdown_hit` 告警类型），但其阈值判定在内存链路，未输出可被告警消费的回撤指标 | 需只读聚合：从快照序列计算运行期峰值权益与回撤；口径须区分回测/实盘，禁止混用 |
| E4 | 权益快照新鲜度（采样是否停滞） | 缺失 | 快照表 `captured_at` 存在 | inferred：可由 `NOW() - MAX(captured_at)` 计算；当前无指标、无停滞告警 | 与 E1 同源；属于可观测性自身的健康探针，不改交易链路 |
| E5 | 外部钱包/凭证权益对账差（内部记账 vs 交易所） | 缺失 | 未见对账表或对账差指标 | unknown：`live_trading/account_snapshot.py` 有错误收集与快照解析，但权益对账差口径当前代码库未确认 | 若后续落地，须只读比对，不触发补单/平仓动作 |

### 1.2 风控拦截计数

| # | 期望观测 | 现状状态 | 现有落点 / 指标名 | 证据等级与位置 | 缺口说明 |
|---|---|---|---|---|---|
| R1 | 风控拦截/触发次数（按拦截类型） | 部分 | `RiskAlert.alert_type`：`stop_loss_hit / max_drawdown_hit / position_limit / trailing_activated / breakeven_stop / scale_out / profit_retracement`；内存列表 `engine.alerts` | confirmed：`risk_engine.py:281-557,567-585`；HTTP `GET /api/risk/alerts` `routes/risk.py:74-99` | 未输出 Counter；拦截类型、品种、策略、动作未作为标签持久化到可被 Prometheus 抓取的面；进程重启即丢失内存列表 |
| R2 | 下单前风控 gate 拒绝计数（限额/仓位/方向/预算） | 部分 | `live_trading/account_risk.py` 返回限额违规投影；`account_risk_limits` 读取策略配置 | confirmed：`services/live_trading/account_risk.py:101-114,217,270,281-283`；信号校验 `strategy_runtime/pipeline.py:19-23,55` 调用 `signal.validate()` | 拒绝发生时未见统一的拒绝事件计数器；违规原因散落在返回结构与异常消息中，未聚合为 `risk_gate_rejections_total{reason,...}` |
| R3 | 强制平仓动作结果（成功/失败） | 部分 | 日志 `强制执行平仓成功/失败`、`全部平仓触发`；`RiskAlert.action_required` | confirmed：`risk_engine.py:506-512,560-565,676` | 成功/失败未计数；失败原因未结构化；属风控动作结果观测，不改变止损判定逻辑 |
| R4 | 持仓漂移/封禁告警计数 | 部分 | `position_drift_blocked` / `drift_reason` / `STATUS_BLOCKED` | confirmed：`services/strategy_runtime/health.py:338-404` | 为健康快照字段，未做 Counter；漂移原因标签集合需评审 |

### 1.3 订单拒绝原因统计

| # | 期望观测 | 现状状态 | 现有落点 / 指标名 | 证据等级与位置 | 缺口说明 |
|---|---|---|---|---|---|
| O1 | 交易所拒单分类计数 | 部分 | `classify_exchange_order_error` 返回 `category`：`transport / insufficient_funds / order_size / account_configuration / exchange_rejected`，含 `retryable/http_status/raw` | confirmed：`services/pending_orders/error_classification.py:9-28`；快捷交易错误提示归类 `services/quick_trade/errors.py:9-138` | 分类结果用于 UI/日志，未见按类别自增的 Counter；`exchange_id/market_type/symbol` 标签未统一 |
| O2 | 订单终态计数（成交/部分/撤/拒/失败） | 部分 | 规范事件 `order_status` 归一化：`filled/partial/cancelled/open`（`rejected/failed/expired` 归入 `cancelled`） | confirmed：`execution_streams/events.py:30-40`；落库 `qd_execution_events.order_status` `repository.py:90-114` | 归一化把 `rejected` 并入 `cancelled`，**拒绝原因被压平**；Prometheus 侧无终态计数指标；原始 `raw_json` 保留可回溯 |
| O3 | 快捷交易拒单 hint 分布 | 部分 | `hint_key` 集合：`regionRestricted/okxAccountMode/insufficientBalance/invalidSize/invalidPrice/rateLimit/authError/positionConflict/networkError/exchangeMaintenance/ipWhitelist` | confirmed：`quick_trade/errors.py:9-73,92-138` | 仅在响应与提示层，无计数；hint 到指标标签的映射待评审 |
| O4 | 持久化指令失败原因 | 部分 | `qd_strategy_commands.error_message` + 终态 `failed`；现有 gauge `quantdinger_strategy_commands{status="failed"}` | confirmed：`strategy_command_repository.py:159-198`；`metrics.py:103-125` | 现有告警只看 `failed > 0`，未按错误类别/原因聚合；`error_message` 为自由文本，需先定类别映射再做标签 |
| O5 | 下单请求总量与成功率 | 缺失 | HTTP 层只统计 API 请求，不区分交易路由；成交/拒单在执行流与快捷交易表 | inferred：可由 `qd_execution_events` 与 `qd_quick_trades` 聚合；当前无 `orders_submitted_total` / `orders_filled_total` 指标 | 口径需明确：提交侧（请求）与接受侧（交易所回执）分开计数，避免把"未提交"算成"拒单" |

### 1.4 接口延迟

| # | 期望观测 | 现状状态 | 现有落点 / 指标名 | 证据等级与位置 | 缺口说明 |
|---|---|---|---|---|---|
| L1 | HTTP API 请求延迟分布（P50/P95/P99） | 已有 | `quantdinger_http_request_duration_seconds{method,route}` Histogram，桶 `0.01…60s` | confirmed：`metrics.py:33-38`；`http.py:36-45`；告警 `QuantDingerSlowApi` 用 P95 > 2s `alerts.yml:33-43` | 现有标签无 `status`；慢请求与错误请求不能在同一延迟切片下关联；`route="unmatched"` 为兜底槽位 |
| L2 | 接口请求量 / 进行中并发 | 已有 | `quantdinger_http_requests_total{method,route,status}`；`quantdinger_http_requests_in_progress{method}` | confirmed：`metrics.py:28-44`；`http.py:33,40-45,52` | 流量维度缺业务域（交易/行情/认证/回测）标签；可由 route 前缀派生，需评审 |
| L3 | 交易所下单/回执/成交等待延迟 | 缺失 | 执行流事件带 `occurred_at`；快捷交易与 pending order 有阶段函数 | inferred：`events.py:84` 时间戳；`pending_orders/live_order_phases.py:41,173,216,279` 分阶段；当前无跨阶段延迟 Histogram | 需只读阶段计时：信号→下单、下单→回执、回执→成交；不得改变下单/撤单控制流 |
| L4 | 外部数据源/行情往返延迟 | 部分 | 数据提供者异常经 `record_exception(scope=...)` 标记；未见延迟指标 | inferred：`data_sources/asia_stock_kline.py:256,464,598,655` 等调用 `record_exception`；`services/resource_guard.py:87-93` 只标记 FD 耗尽 | 缺按数据源/品种的延迟与超时计数；现有 scope 字符串未规范化为标签枚举 |
| L5 | 任务/worker 处理时长 | 缺失 | worker 心跳新鲜度（healthy/stale gauge） | confirmed：`metrics.py:72-101`；无任务耗时 Histogram；`qd_strategy_commands` 有 `created_at/updated_at` 可推导时长 | 可由指令时间戳派生排队时长与执行时长；口径待评审 |

### 1.5 异常错误计数

| # | 期望观测 | 现状状态 | 现有落点 / 指标名 | 证据等级与位置 | 缺口说明 |
|---|---|---|---|---|---|
| X1 | HTTP 5xx 错误率 | 已有 | `quantdinger_http_requests_total{status=~"5.."}`；告警 `QuantDingerHighApiErrorRate` > 5% | confirmed：`metrics.py:28-32`；`alerts.yml:21-31` | 4xx 未纳入错误率口径；错误率无按路由/业务域切片；异常类型未标签化 |
| X2 | 未捕获异常 / 异常分类计数 | 部分 | 日志 `exception` 栈（JSON 格式）；`logger.error/exception` 散见于路由与服务 | confirmed：`logger.py:25-27`；各 `routes/*.py` 的 `except Exception as e: logger.error(...)` | 异常未进入 Counter；异常类型/模块/scope 无规范标签；存在 `except Exception` 后仅记日志的路径（本轮不评判其控制流，仅记录观测缺口） |
| X3 | 外部交易所/数据源异常计数 | 部分 | 错误归类 `category` 与 `hint_key`；连接/超时异常落入日志 | confirmed：`pending_orders/error_classification.py:18-28`；`quick_trade/errors.py:64-69` | 未按 `category/exchange_id` 计数；网络超时、限流、鉴权、维护等类别需与 O1/O3 对齐同一枚举 |
| X4 | 资源耗尽（FD/内存/连接池）事件 | 部分 | FD 耗尽检测 `is_fd_exhaustion` / `mark_fd_exhausted` | confirmed：`utils/resource_guard.py:29,79-93` | 未暴露 Counter/gauge；内存/连接池耗尽当前代码库未见对应探针（unknown） |
| X5 | 数据库可达性 / 慢查询 | 部分 | `qd_worker_heartbeats` 等关键表 `SELECT 1` 探针；Postgres exporter 存活告警 | confirmed：`utils/db.py:34-44,163-201`；`alerts.yml:53-59` | 应用侧慢查询计数/语句标签未见；依赖 postgres-exporter 指标在当前代码库未验证（unknown 采集面） |

---

## 2. 缺口指标：只读聚合口径定义（待评审，未实现）

> 以下为**契约草案**：指标名、类型、标签、聚合来源（表/事件/日志）、计算口径。落地前需经评审 R1–R5（见第 5 节）；本轮不新增端点代码、不改 schema、不接告警通道。
> 命名沿用现有 `quantdinger_` 前缀；标签取值必须来自受控枚举，自由文本（如 `error_message`、`raw_json`）不得直接作为标签。

### 2.1 账户权益类

#### 2.1.1 `quantdinger_account_equity`
- **类型**：Gauge
- **标签**：`account_id`（凭证/账户隔离键，非 open_id 明文）、`strategy_id`、`venue`、`basis`（`snapshot` / `realtime_balance`）
- **聚合来源**：`qd_strategy_equity_snapshots`（最新一行 per `strategy_id`）；实时余额路径 `live_trading` balance 快照（best-effort，标注 `basis`）
- **口径**：数值取权益币种单位；缺值不上报该序列（不写 0 顶替缺值，对齐真实数据口径规则）；金额币种在评审后决定是否作为标签
- **不做**：不据此触发止损/减仓；不与回测权益混列

#### 2.1.2 `quantdinger_account_pnl_periodic`
- **类型**：Gauge（窗口内净盈亏）/ 派生 Counter 可选
- **标签**：`account_id`、`strategy_id`、`pnl_type`（`realized` / `unrealized`）、`window`（`today` / `running`）
- **聚合来源**：快照表相邻序列差分；`realized_pnl`、`unrealized_pnl` 列
- **口径**：`today` 以交易日边界（服务器时区，须与 Python `--tz` / MT5 偏移一致）；`running` 为策略生命周期累计；缺值返回空态，不填 0
- **依赖**：先拍板绩效口径统一（关联 TODO P1-13：逐笔净盈亏 vs 日收益年化）

#### 2.1.3 `quantdinger_account_drawdown_ratio`
- **类型**：Gauge（0–1，非百分数文本）
- **标签**：`account_id`、`strategy_id`、`basis`（`live` / `backtest`）
- **聚合来源**：快照权益序列
- **口径**：`drawdown = 1 - equity_t / max(equity_{<=t})`；峰值仅用 `available_at <= t` 的快照（因果单向）；回测序列与实盘序列分标签，不互算
- **注意**：阈值不在本轮设定；禁止用绩效网格搜索反推回撤线

#### 2.1.4 `quantdinger_equity_snapshot_staleness_seconds`
- **类型**：Gauge
- **标签**：`account_id`、`strategy_id`
- **聚合来源**：`NOW() - MAX(captured_at)`（快照表）
- **口径**：仅观测采样停滞；不等于权益本身；无快照记为 `unknown`（序列缺失），不报 0

### 2.2 风控拦截类

#### 2.2.1 `quantdinger_risk_gate_rejections_total`
- **类型**：Counter（只增；含被拒绝的指令，与 `trials_N` 只增不减原则一致）
- **标签**：`gate`（`pre_order` / `stop_loss` / `drawdown` / `position_limit` / `breakeven` / `trailing` / `scale_out` / `profit_retracement` / `drift`）、`reason`（受控枚举，评审冻结）、`venue`、`symbol`、`strategy_id`
- **聚合来源**：风控引擎 `RiskAlert` 事件（R1）；下单前 gate 违规投影（R2）；漂移封禁记录（R4）
- **口径**：一次拒绝事件计一次；同一动作重试不重复计为新类别（重试在指令层另计）；`reason` 自由文本先映射到枚举再打标签
- **边界**：只观测拦截，不修改 gate 判定、不绕过风控

#### 2.2.2 `quantdinger_risk_action_executions_total`
- **类型**：Counter
- **标签**：`action`（`close_position` / `reduce_position` / `close_all_positions` / `monitor`）、`outcome`（`success` / `failed`）、`symbol`、`strategy_id`
- **聚合来源**：风控回调结果（R3 成功/失败日志与告警动作）
- **口径**：动作发起即记一次，结果按回调回执二次更新；失败原因映射到受控 `outcome_detail` 枚举（评审冻结）

### 2.3 订单拒绝类

#### 2.3.1 `quantdinger_orders_submitted_total`
- **类型**：Counter
- **标签**：`venue`、`market_type`、`symbol`、`side`、`source`（`quick_trade` / `strategy_runtime` / `grid`）
- **聚合来源**：下单请求发出点（只读埋点）；订单意图记录 `qd_strategy_commands` / pending order 记录
- **口径**：请求离开本系统即计数；与交易所回执无关；缺标签项填 `unknown` 枚举，不打裸空串

#### 2.3.2 `quantdinger_orders_rejected_total`
- **类型**：Counter
- **标签**：`venue`、`market_type`、`symbol`、`category`（沿用 `transport/insufficient_funds/order_size/account_configuration/exchange_rejected`，评审可扩充）、`retryable`（`true/false`）、`source`
- **聚合来源**：`classify_exchange_order_error` 分类结果（O1）；执行流 `order_status` 原始回执（O2，保留原始拒绝态而非并入 `cancelled` 的新只读投影）；快捷交易 hint（O3）映射
- **口径**：仅交易所/链路明确回执拒绝才计；本地参数校验拒绝归入 `order_size/account_configuration`；网络超时归 `transport`；分类器未命中归 `exchange_rejected` 并保留原始消息在日志（不入标签）

#### 2.3.3 `quantdinger_orders_terminal_total`
- **类型**：Counter
- **标签**：`venue`、`symbol`、`terminal`（`filled` / `partial` / `cancelled` / `rejected` / `expired` / `failed`）
- **聚合来源**：`qd_execution_events.order_status` + 原始 `raw_json` 回执
- **口径**：终态以交易所最终回执为准；当前归一化把 `rejected/failed/expired` 压平为 `cancelled`，新指标在只读投影层还原原始终态，**不改写入归一化函数**

#### 2.3.4 待评审只读聚合端点（契约，不实现）

**`GET /api/observability/order-rejections`**（只读）
- 鉴权：复用现有 Bearer 中间件；按 `user_id` 隔离
- 查询参数：`venue`、`category`、`source`、`window`（`1h` / `24h` / `7d`）、`strategy_id`（可选）
- 响应草案：
  ```json
  {
    "code": 1,
    "data": {
      "window": "24h",
      "total_submitted": 0,
      "total_rejected": 0,
      "by_category": [
        {"category": "insufficient_funds", "count": 0, "retryable": false}
      ],
      "data_kind": "real"
    }
  }
  ```
- 口径：聚合自上述只读来源；无数据返回空数组与 `data_kind:"real"` 空态，不返回演示数字
- **不做**：不下单、不平仓、不写交易库；端点归属待评审（P2 可观测面板数据源）

### 2.4 延迟类

#### 2.4.1 `quantdinger_exchange_order_latency_seconds`
- **类型**：Histogram
- **标签**：`venue`、`stage`（`signal_to_submit` / `submit_to_ack` / `ack_to_fill` / `submit_to_fill`）、`symbol`、`source`
- **聚合来源**：执行流/指令时间戳差（L3）；阶段边界须用已收盘/已回执时间戳，不得读取未来 bar
- **口径**：超时未回执计入 `stage` 超时槽（另见 2.4.3）；桶定义评审后冻结

#### 2.4.2 `quantdinger_external_data_latency_seconds`
- **类型**：Histogram
- **标签**：`provider`、`scope`（受控枚举，由 `record_exception` 的 scope 规范化）、`market_type`
- **聚合来源**：数据提供者往返计时（L4）
- **口径**：仅计时；失败同时记入 2.5.3，不在延迟 Histogram 里塞错误标签

#### 2.4.3 `quantdinger_task_duration_seconds`
- **类型**：Histogram
- **标签**：`role`（`trading` / `scheduler` / `celery`）、`task_type`、`outcome`（`success` / `failed` / `cancelled`）
- **聚合来源**：`qd_strategy_commands` 的 `created_at/claimed_at/updated_at` 时间差；心跳表辅助
- **口径**：排队时长与执行时长分桶标签 `stage`；失败任务时长仍计入，不剔除

### 2.5 错误类

#### 2.5.1 `quantdinger_app_exceptions_total`
- **类型**：Counter
- **标签**：`module`（受控枚举/路由域）、`exc_type`（异常类名，规范化）、`scope`、`http_status`（可空）
- **聚合来源**：未捕获/已捕获异常埋点（X2）；HTTP 状态由中间件补充
- **口径**：同一异常在请求边界记一次；`exc_type` 不取自由消息；栈信息留在日志与 `request_id` 关联

#### 2.5.2 `quantdinger_http_errors_total`
- **类型**：Counter（可由现有 `http_requests_total` 派生，不必新增抓取面）
- **标签**：`method`、`route`、`status_class`（`4xx` / `5xx`）
- **聚合来源**：`quantdinger_http_requests_total`
- **口径**：4xx 与 5xx 分开；错误率 = 错误类速率 / 全量速率，分母钳制避免除零（沿用 `alerts.yml:25` 的 `clamp_min` 思路）

#### 2.5.3 `quantdinger_external_errors_total`
- **类型**：Counter
- **标签**：`venue` / `provider`、`category`、`retryable`
- **聚合来源**：错误分类器（X3）；FD 耗尽标记（X4）
- **口径**：与 2.3.2 共享 `category` 枚举，避免两套拒绝/错误口径

#### 2.5.4 `quantdinger_resource_exhaustion_total`
- **类型**：Counter
- **标签**：`resource`（`fd` / `memory` / `connection_pool`，后两者当前 unknown）
- **聚合来源**：`resource_guard` 标记（X4）
- **口径**：进入耗尽保护即计数；探针本身不触发交易动作

---

## 3. 告警骨架（意图 + 占位阈值，未落地规则）

> 说明：以下每条只定义**告警意图、观测指标、建议分级与处理方向**。表达式用 PromQL 草案形式给出，**阈值为占位，须由 CLEAN 集分布校准后回填**；禁止按绩效（PnL/胜率）网格搜索定阈值。`for` 持续时间、静默/抑制策略同样待评审。本轮**不接** Alertmanager 通知通道（电话/短信/邮件/飞书/webhook 均不配置），**不写** `alerts.yml` 落地规则。
> 分级沿用既有 `critical / warning`（对齐 `alerts.yml`）；P0–P3 流程定义见 `docs/MONITORING_ALERTING.md`，本轮不改。

### 3.1 权益与回撤类

| 告警意图 | 观测指标（草案） | 占位表达式（阈值待校准） | 分级（待评审） | 处理方向（只读止血建议，非自动动作） | 阈值口径约束 |
|---|---|---|---|---|---|
| 权益回撤超基线 | `quantdinger_account_drawdown_ratio` | `max_over_time(quantdinger_account_drawdown_ratio{basis="live"}[15m]) > DD_WARN`；严重线 `DD_CRIT` | warning / critical | 人工核对快照连续性与持仓；确认是否止损链路已按纪律执行；不自动加仓/补仓 | `DD_WARN/DD_CRIT` 由 CLEAN 集回撤分布分位数确定；不得用历史绩效最佳区间反推；回测序列独立告警，不混入实盘 |
| 权益快照停滞 | `quantdinger_equity_snapshot_staleness_seconds` | `quantdinger_equity_snapshot_staleness_seconds > STALE_SEC` | warning | 检查 worker 心跳、快照任务、DB 写入；区分"无持仓空闲"与"采样卡死" | `STALE_SEC` 对照现有采样间隔（运行 300s / 空闲 24h）与心跳 45s 口径校准；空闲策略不纳入停滞告警 |
| 账户级 PnL 异常下行 | `quantdinger_account_pnl_periodic` | 短窗 PnL 相对同基线分布偏离超 `PNL_Z` 或跌破 `PNL_FLOOR` | warning | 核对成交、费用、未实现盈亏口径；与回撤告警联动抑制，避免重复轰炸 | 基线只用 CLEAN/历史稳定窗口；`PNL_FLOOR` 不等同止损线；止损判定仍由风控链路负责 |
| 权益对账差（若落地） | （E5，unknown） | 对账差绝对值 > `RECON_DIFF` | critical | 冻结新增同凭证开仓（人工确认）；核查记账与交易所快照时点 | 对账口径与时点差先评审；阈值按币种/波动率分层 |

### 3.2 风控拦截类

| 告警意图 | 观测指标（草案） | 占位表达式（阈值待校准） | 分级（待评审） | 处理方向 | 阈值口径约束 |
|---|---|---|---|---|---|
| 拦截计数突增 | `quantdinger_risk_gate_rejections_total` | `rate(quantdinger_risk_gate_rejections_total[5m]) > REJECT_RATE`；或相对基线倍数 `REJECT_MULT` | warning | 定位突增 `gate/reason`：行情异动、仓位超限、参数异常、凭证/接口异常 | 基线来自正常运行期 CLEAN 分布；突增判据用比率/分位，不用固定绩效结果；单策略 vs 组合分层 |
| 风控动作失败 | `quantdinger_risk_action_executions_total{outcome="failed"}` | `increase(quantdinger_risk_action_executions_total{outcome="failed"}[5m]) > 0` | critical | 人工核查强制平仓/减仓回执；核对下单通道与凭证；失败可重试须由既有执行链路负责 | 失败计数不含本地校验拒绝；重试次数与退避策略另属执行链路，本轮不定 |
| 漂移封禁集中出现 | `quantdinger_risk_gate_rejections_total{gate="drift"}` | `rate(...[10m]) > DRIFT_RATE` | warning | 核查持仓同步、凭证归属、在途订单与快照时点 | `drift_reason` 枚举先冻结再告警 |

### 3.3 订单拒绝类

| 告警意图 | 观测指标（草案） | 占位表达式（阈值待校准） | 分级（待评审） | 处理方向 | 阈值口径约束 |
|---|---|---|---|---|---|
| 拒单率升高 | `quantdinger_orders_rejected_total` / `quantdinger_orders_submitted_total` | `rate(rejected[5m]) / clamp_min(rate(submitted[5m]), 0.001) > REJECT_PCT` | warning | 按 `category/venue` 下钻：资金、手数、账户模式、限流、鉴权、网络 | 基线分 venue/source 分层；低样本窗口（提交量过小）不触发百分比告警，改用绝对增量兜底 |
| 资金/限额类拒单集中 | `orders_rejected_total{category="insufficient_funds"}` | `increase(...[10m]) > N_FUNDS` | warning | 核对可用余额/冻结挂单/钱包划转；不下调风控限额 | 计数阈值按 CLEAN 期低频事件分布设定 |
| 鉴权/IP/维护类外部拒单 | `orders_rejected_total{category=~"account_configuration\|exchange_rejected"}` + hint 映射 | 出现 `authError/ipWhitelist/exchangeMaintenance` 类别即告警 | critical / warning | 核对 API key、IP 白名单、交易所公告；必要时切换备用链路（人工） | 类别映射冻结后落地；原始错误消息只入日志 |
| 持久化指令失败增长 | `quantdinger_strategy_commands{status="failed"}`（已有）+ 失败类别（草案 2.3.4/2.5.3） | 现有 `> 0` 规则保留；细化为速率 `increase(...[30m]) > N_CMD_FAIL` | warning | 按 `error_message` 类别下钻；关联 worker 心跳告警 | 现有规则已落地，细化属后续评审；不手工改写 `registry.yaml` |

### 3.4 接口与延迟类

| 告警意图 | 观测指标（草案） | 占位表达式（阈值待校准） | 分级（待评审） | 处理方向 | 阈值口径约束 |
|---|---|---|---|---|---|
| API P95/P99 延迟升高 | `quantdinger_http_request_duration_seconds`（已有） | 现有 P95 > 2s 规则保留；新增 P99 与按路由切片 `histogram_quantile(0.99, ...) > P99_MAX` | warning | 下钻慢路由、外部依赖、DB 慢查询；区分行情长连接与普通请求 | 现有 2s 为落地值，**是否合理待 CLEAN 分布复核**；桶与分位数口径评审后固化 |
| 下单/成交链路延迟升高 | `quantdinger_exchange_order_latency_seconds` | `histogram_quantile(0.95, sum(rate(...[5m])) by (le, stage)) > EX_LAT` | warning | 按 `stage` 定位：下单接口、回执推送、成交回报 | 分阶段基线按 venue 分层；超时不计入正常延迟分位 |
| 外部数据源延迟/超时 | `quantdinger_external_data_latency_seconds` / `external_errors_total` | P95 > `DATA_LAT` 或 `rate(transport 错误) > DATA_ERR` | warning | 核对 provider 限流、网络、缓存熔断 | 基线按 provider/市场类型分层 |
| Worker 任务积压/超时 | `quantdinger_task_duration_seconds` + 心跳 gauge（已有） | 排队时长 P95 > `QUEUE_MAX`；或 `workers_stale > 0` | warning / critical | 核对调度器、Celery 队列、租约过期 | 与现有 `WorkerMissing` 告警联动抑制 |

### 3.5 错误与资源类

| 告警意图 | 观测指标（草案） | 占位表达式（阈值待校准） | 分级（待评审） | 处理方向 | 阈值口径约束 |
|---|---|---|---|---|---|
| API 5xx 错误率升高 | `quantdinger_http_requests_total`（已有） | 现有 > 5% 规则保留；细化 4xx 切片 `HTTP_4XX_PCT` | warning / critical | 按路由/异常类型下钻；关联发布版本 `build_info` | 5% 为现有落地值，待分布复核；低流量窗口不放大误报 |
| 应用异常突增 | `quantdinger_app_exceptions_total` | `rate(...[5m]) > EXC_RATE`，或同 `exc_type` 相对基线倍数 | warning | 按 `module/exc_type` 定位；保留 `request_id` 回溯链路 | 基线排除首次发布/冷启动窗口 |
| 外部依赖错误集中 | `quantdinger_external_errors_total` | 按 `category` 速率 > `EXT_ERR` | warning | 与拒单告警联动；核对网络/凭证/维护公告 | 与 3.3 共享枚举与基线 |
| 资源耗尽事件 | `quantdinger_resource_exhaustion_total` | FD/内存/连接池出现耗尽计数即告警 | critical | 检查进程、句柄、连接池配置；必要时滚动重启（人工执行） | 内存/连接池探针当前 unknown，落地前先补采集 |

### 3.6 告警编排原则（骨架，不落地）

1. **可执行**：每条告警必须对应一个明确的人工核查动作；无动作的提示性指标只上看板，不进告警。
2. **抑制与关联**：底层依赖故障（DB/Redis/exporter 宕机）抑制上层路由/交易告警；回撤与 PnL 下行互为相关，避免同一账户重复轰炸。
3. **低样本保护**：请求/成交样本低于最小门槛时，比率类告警退化为绝对增量阈值；缺值不按 0 处理。
4. **阈值留痕**：每条落地规则须记录基线集、分位数口径、校准日期与评审人；阈值变更走实验/评审流程，不允许在告警文件里直接按绩效结果改数。
5. **通道隔离**：本轮及后续落地前，生产告警通道（Alertmanager receiver / webhook / 通知）保持现状，不在草稿中配置真实接收人。

---

## 4. 现状证据与未决口径

### 4.1 已确认（confirmed）
- Prometheus 抓取面仅 `GET /metrics` 一条；现有 7 个指标见 0.1。
- 现有告警规则 7 条 + `rules.yml` 1 条，覆盖 API/worker/错误率/延迟/exporter 存活；**无**权益、回撤、风控拦截、拒单原因、下单链路延迟的规则。
- 权益、成交、执行事件、策略日志均有数据库表作为原始来源；风控告警与可观测指标目前主要在进程内存，重启不持久。
- 日志支持 JSON 结构化与 `request_id` 关联；文件轮转 UTF-8。

### 4.2 推断（inferred，待落地验证）
- 快照表可推导回撤、增量 PnL、采样停滞；执行流时间戳可推导阶段延迟；指令时间戳可推导排队/执行时长。
- 错误分类器的 `category` 与快捷交易 `hint_key` 可对齐为受控标签枚举，但两套映射当前未统一。
- `docs/MONITORING_ALERTING.md` 的数值阈值（500ms/1%/3%/5%/10% 等）为概念样例，不代表生产基线。

### 4.3 未确认（unknown）
- `ops/rules.yml` 是否被 Prometheus 实际加载（`prometheus.yml` 的 `rule_files` 仅列 `alerts.yml`）。
- postgres-exporter / redis-exporter 在当前部署中是否真实在线、暴露哪些库级指标。
- 内存/连接池耗尽探针；账户级（跨凭证）权益与对账差口径。
- 生产日志是否已由日志收集器（Loki/ELK 等）采集；当前仓库只见本地轮转文件。
- `qd_execution_events` 中拒绝/失败回执的原始字段完整度（用于 2.3.3 还原终态），需只读抽样核实。

### 4.4 显式不做（本轮边界）
- 不新增/修改交易路由、风控 gate、下单平仓、资金计算逻辑。
- 不写新 metrics 生产代码、不新增持久化表或列、不改 schema。
- 不落地 Prometheus 规则、不配 Alertmanager 真实 receiver、不接通知通道。
- 不依据任何绩效数字设定正式阈值；不把演示/回测数值当生产基线。

---

## 5. 待评审问题（落地前拍板）

- **R1 口径统一**：账户/策略权益与 PnL 的币种、时点、交易日时区；逐笔净盈亏 vs 日收益年化口径（关联 TODO P1-13）。
- **R2 标签枚举冻结**：`gate/reason/category/hint_key/exc_type/scope` 受控枚举清单与映射表；自由文本不入标签。
- **R3 样本门槛**：比率类告警的最小样本量与低样本退化阈值；回测/实盘/演示数据分标签。
- **R4 采集边界**：新指标埋点位置（只读埋点 vs 定期只读聚合任务）；多进程下 Counter/Gauge 的 multiprocess 语义（复用 `PROMETHEUS_MULTIPROC_DIR`）。
- **R5 基线校准流程**：CLEAN 集范围、分位数选择、阈值复核周期；校准记录留档位置（ADR/评审单），不进入 `registry.yaml` 手工改写。

---

## 6. 拟登记 TODO 条目（仅列出，未写入 `docs/TODO.md`）

> 以下条目供评审后由人工登记到 `docs/TODO.md`；本轮不自行修改该文件。

| 拟编号 | 优先级 | 事项 | 依赖 / 阻塞点 | 验收要点 |
|---|---|---|---|---|
| OBS-1 | P1 | 落地账户权益/回撤只读指标（2.1.1–2.1.4），含快照新鲜度探针 | R1 口径拍板；复用快照表只读聚合 | 指标可在 `/metrics` 或只读端点查到；缺值空态不填 0；附单测覆盖因果时序与缺值 |
| OBS-2 | P1 | 落地风控拦截/动作计数 Counter（2.2.1–2.2.2），标签枚举先冻结 | R2 枚举评审；不改 gate 判定 | 一次拒绝/动作事件计数正确；进程重启后指标可由持久化事件重建或明确标注内存口径 |
| OBS-3 | P1 | 落地订单提交/拒绝/终态计数与只读聚合端点草案（2.3.1–2.3.4） | R2/R3；执行流原始回执字段核实（4.3） | 提交与接受分计；拒绝类别可下钻；端点响应带 `data_kind`，无演示数字 |
| OBS-4 | P2 | 落地下单链路与外部数据源延迟 Histogram（2.4.1–2.4.3） | R4 采集边界；阶段时间戳完备性核实 | 分阶段延迟可观测；超时单独归类；不改变控制流与重试逻辑 |
| OBS-5 | P2 | 落地异常/外部错误/资源耗尽 Counter（2.5.1–2.5.4） | R2 枚举；资源探针现状核实 | 异常按受控 `exc_type/scope` 计数；`request_id` 可回溯；栈信息留在日志 |
| OBS-6 | P2 | 告警规则从骨架转为落地规则，阈值由 CLEAN 分布校准（第 3 节） | OBS-1~OBS-5 指标就绪；R5 校准流程 | 每条规则附基线口径与评审记录；先接灰度/静默通道，再接真实 receiver；低样本保护生效 |
| OBS-7 | P2 | 核实 `rules.yml` 加载状态与 exporter 在线/指标面（4.3） | 部署环境只读核查 | 明确规则文件挂载关系；列出 postgres/redis exporter 实际可用指标清单 |
| OBS-8 | P3 | 日志归集与 `request_id` 链路追溯（异常/拒单/拦截按请求串起） | 现有 JSON 日志格式；采集器选型评审 | 同 `request_id` 可在日志与指标间关联；结构化字段稳定 |

---

**文档生成口径**：本轮为只读盘点 + 契约草案；所有指标名/表名/文件行号均来自当前代码库快照；未填入任何绩效数字作为基线。
