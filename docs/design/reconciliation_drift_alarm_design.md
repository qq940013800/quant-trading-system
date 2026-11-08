# 周期对账（本地成交/持仓 vs 交易所）+ 指标漂移告警 —— 设计草案

> 状态：**待评审草稿**。本轮只产出文档，不实现生产调度代码，不改任何阈值，不新增调度任务。
> 边界：不碰 `secrets/`、`runtime/`、`ledger/`、`configs/`、`registry.yaml`、`mt5/`；实盘资金路径（`live_trading/`、`quick_trade/`、`pending_orders/`、`native_protection`、凭证写库）只读调研，不改代码。
> 阈值原则：**所有告警/对账阈值先以占位形式文档化；正式阈值必须由 CLEAN/历史分布校准（分位数/基线），禁止按绩效网格搜索产生**（对齐 `AGENTS.md` 不变量 3 与 `docs/RULES.md` 过拟合防御铁律）。
> 证据等级：`confirmed`（代码/配置中直接读到落点或数值）、`inferred`（由现有结构推断，未在生产路径直接核对）、`unknown`（当前代码库无法确认口径或存在性）。

---

## 0. 本轮范围与已读证据

| 类别 | 已读对象 | 路径 |
|---|---|---|
| 对账核心模块 | 纯函数订单/持仓对账、容忍度、严重问题代码、KillSwitch 触发 | `core/execution/reconcile.py`（265 行，全量读过） |
| 漂移核心模块 | Sharpe/胜率/回撤漂移、显著性检验、漂移分型、健康分、降级建议 | `core/monitoring/drift_monitor.py`（287 行，全量读过） |
| 特征漂移模块 | PSI 分桶、滚动命中率（因果） | `core/models/drift.py`（41 行，全量读过） |
| 调度任务（维护类） | Celery Beat 周期任务、env 开关、重试模式 | `backend_api_python/app/tasks/maintenance.py`（78 行，全量读过） |
| 调度任务（持久化作业） | 按需 Agent 作业、状态机、队列路由 | `backend_api_python/app/tasks/agent_jobs.py`（68 行，全量读过） |
| 调度任务（AI 分析） | 按需快速分析任务委托 | `backend_api_python/app/tasks/fast_analysis.py`（7 行，全量读过） |
| 调度注册 | Beat schedule、队列路由、任务 imports | `backend_api_python/app/celery_app.py:45-81` |
| 现有调用链 | Engine 对账方法、漂移网关检查、KillSwitch 接口、启动期持仓同步、后端既有对账服务 | `core/execution/engine.py:393-401`、`core/integration/verification_middleware.py:313-354`、`core/control/kill_switch.py:117-158`、`backend_api_python/app/startup.py:190-210,240-249` |
| 既有测试 | 对账单测、漂移监控单测 | `tests/test_execution/test_reconcile.py`、`tests/test_monitoring/test_drift_monitor.py` |

### 0.1 本轮实测验证

- 运行命令：`.venv` 内 `python -m pytest tests/test_execution/test_reconcile.py tests/test_monitoring/test_drift_monitor.py -q`（Python 3.12.10）。
- 结果：**27 passed in 0.33s**（confirmed，本轮实测）。仅跑了这两个既有测试文件；全量 `pytest -q` 未在本轮执行。

---

## 1. 现状盘点（含证据等级）

### 1.1 对账模块现状

| # | 现状结论 | 等级 | 证据落点 |
|---|---|---|---|
| R1 | `reconcile()` 是纯函数比较，**不做网络 I/O**；输入为本地/经纪商两侧订单与持仓，输出 `ReconcileReport` | confirmed | `reconcile.py:8-11,206-213` |
| R2 | 订单按 `order_id` 匹配；比对字段为 `side` / `quantity` / `filled_quantity`；持仓按 `symbol` 匹配；比对字段为 `side` / `quantity` | confirmed | `reconcile.py:14-16,239-257,282-294` |
| R3 | 数量容忍度：绝对 `qty_abs=1e-6`、相对 `qty_rel=1e-4`，取较大者 | confirmed | `reconcile.py:26-39` |
| R4 | 八类严重问题代码：`ORDER_MISSING`、`ORDER_UNKNOWN`、`ORDER_DUPLICATE_LOCAL`、`ORDER_DUPLICATE_BROKER`、`ORDER_MISMATCH`、`POSITION_MISSING`、`POSITION_UNKNOWN`、`POSITION_MISMATCH`；报告 `is_clean` 以是否存在这些代码为准 | confirmed | `reconcile.py:82-101` |
| R5 | 侧别归一化：`buy/b/long/+1/1` → `buy`，`sell/s/short/-1` → `sell`；未知值原样小写 | confirmed | `reconcile.py:143-154` |
| R6 | 持仓为**净持仓模型**：同一 symbol 多条持仓在本地/经纪商侧均标记为数据错误 | confirmed | `reconcile.py:261-277` |
| R7 | `enforce(report, kill_switch, source)`：报告不干净即调用 `KillSwitch.trigger(reason, source, metadata={"codes": ...})`；返回原报告供记录 | confirmed | `reconcile.py:299-311` |
| R8 | Engine 已封装 `reconcile(broker_orders, broker_positions, *, tolerance, enforce_switch=True)`；不干净时按开关触发 KillSwitch | confirmed | `core/execution/engine.py:393-401` |
| R9 | `PositionView.entry_price` 字段被携带，但**当前比对口径未比较开仓价**；订单 `status` 字段同样未参与比对 | confirmed | `reconcile.py:54-62,163-170,282-294` |
| R10 | 后端 app 内**未发现**对 `core.execution.reconcile` 的 import（本切片定向 grep 0 命中）；核心对账目前只在 `core` 链路内被 Engine 调用 | confirmed | 检索路径 `backend_api_python/app`，模式 `execution.reconcile`；R8 为唯一已核对的核心内调用 |
| R11 | 后端已存在多条**独立的、本切片不改**的对账/同步路径：按需路由对账 `reconcile_strategy_vs_account`；worker 循环与启动后延迟同步 `_sync_positions_best_effort`；Alpaca 成交活动对账、资金费对账、手续费对账、网格台账对账 | confirmed（存在性）；其内部口径与触发频次未在本轮精读 | `live_trading/account_positions.py:184`、`routes/strategy_positions_routes.py:291`、`services/pending_order_position_sync.py:75`、`services/pending_order_worker.py:416,1763,2008`、`startup.py:205`、`live_trading/alpaca_activity_reconciliation.py`、`live_trading/funding_reconciliation.py`、`pending_orders/fee_reconciliation.py`、`grid/ledger_reconcile.py` |

### 1.2 漂移监控现状

| # | 现状结论 | 等级 | 证据落点 |
|---|---|---|---|
| D1 | `DriftMonitor` 输入为收益序列（`update(returns)`），内部保留最近 `window_size` 个收益；默认 `window_size=100` | confirmed | `drift_monitor.py:46-63,66-77` |
| D2 | 三项当前统计量：滚动 Sharpe（年化 `mean/std*sqrt(252)`）、胜率（收益>0 占比）、最大回撤；样本数 <20 时统计量回退为 0.0 / 0.5 / 0.0 | confirmed | `drift_monitor.py:79-104` |
| D3 | 三项漂移检查：Sharpe 偏离度、胜率差值、回撤倍数；告警类型 `sharpe_drift` / `win_rate_drift` / `drawdown_increase` | confirmed | `drift_monitor.py:106-158` |
| D4 | 告警严重度 `low/medium/high/critical`，由偏离度相对阈值与 critical 切点映射 | confirmed | `drift_monitor.py:23-34,160-169` |
| D5 | 显著性检验为单样本 t 检验（正态近似 p 值）；默认 `baseline_mean=0.0005`、`alpha=0.05`；样本 <30 返回「样本不足」；判定线 `|t|>1.96` | confirmed | `drift_monitor.py:206-268`（样本门槛 225 行；判定线 254 行） |
| D6 | 漂移分型 `stable / gradual_decay / sudden_failure / insufficient_data`；前后半段均值比较；样本 <50 返回 `insufficient_data` | confirmed | `drift_monitor.py:270-301` |
| D7 | 健康分 0–100；降级建议分四档：保持仓位 / 减仓 50% 观察 / 减仓至 25% 密切监控 / 暂停交易准备退役 | confirmed | `drift_monitor.py:183-204,303-336` |
| D8 | 构造器默认基线与阈值：`baseline_sharpe=1.0`、`baseline_win_rate=0.5`、`baseline_max_dd=0.15`、`sharpe_drop_threshold=0.3`、`win_rate_drop_threshold=0.1`、`dd_increase_threshold=2.0`。**这些是代码内默认占位值，本轮未发现由 CLEAN 分布校准的证据** | confirmed（数值存在）；`inferred`（尚未接入校准流程） | `drift_monitor.py:46-53` |
| D9 | 特征层另有 PSI 与因果滚动命中率；PSI 分桶边界取 reference 分布分位数；文档约定切点 `<0.1` 稳定、`0.1~0.25` 关注、`>0.25` 显著漂移（约定值，非本仓库回测校准产物） | confirmed（代码与文档字符串）；切点来源 `inferred`（行业惯例，未见仓库内校准记录） | `core/models/drift.py:4-25,28-40` |
| D10 | `DriftMonitor` 目前在核心链路的唯一核对到的调用点是网关前视/漂移检查 `_check_drift`：用基准收益算 baseline Sharpe/胜率，`recent_returns>=10` 才走真实检查，否则降级简化版 | confirmed | `core/integration/verification_middleware.py:313-354` |
| D11 | 后端 app 内**未发现**对 `core.monitoring.drift_monitor` 的 import；当前不存在面向生产策略的周期漂移扫描任务 | confirmed | 检索路径 `backend_api_python/app`，模式 `monitoring.drift_monitor` |
| D12 | 后端存在进程内 `ObservabilityService` 单例：`Metric` / `Alert` / `AlertRule` / `AlertSeverity`，支持告警回调注册；未见其持久化告警表 | confirmed（类与回调存在）；`unknown`（告警落库/跨进程可见性未核对） | `backend_api_python/app/services/observability.py:32-210` |

### 1.3 调度现状

| # | 现状结论 | 等级 | 证据落点 |
|---|---|---|---|
| S1 | Celery Beat 已注册 5 个周期任务：reflection、ai-calibration、market-catalog-sync、worker-heartbeat、runtime-metadata-cleanup | confirmed | `celery_app.py:59-80` |
| S2 | 三个维护类周期任务的 env 开关与间隔下限/默认值：reflection（`ENABLE_REFLECTION_WORKER`；间隔下限 300s，默认 86400s）、ai_calibration（`ENABLE_OFFLINE_AI_CALIBRATION`；下限 3600s，默认 86400s）、market_catalog_sync（`MARKET_CATALOG_AUTO_SYNC`；下限 900s，默认 86400s）；心跳 10s；元数据清理 86400s | confirmed | `maintenance.py:11-12,44-98`；`celery_app.py:62,66,70,74,78` |
| S3 | 维护类任务重试模式：`autoretry_for=(Exception,)`、`retry_backoff=True`、`retry_jitter=True`、`max_retries=3`；开关关闭时返回 `{"skipped": True}` | confirmed | `maintenance.py:36-50,53-60,84-91` |
| S4 | 队列路由：`fast_analysis` → `ai`；`agent_job` → `jobs`；reflection / ai_calibration / market_catalog_sync / heartbeat / cleanup → `maintenance` | confirmed | `celery_app.py:50-58` |
| S5 | `execute_agent_job(job_id)` 是**按需持久化作业**（`acks_late=True`），不在 Beat schedule 中；当前 `SUPPORTED_KINDS={"backtest"}`；状态机：running → succeeded/failed/cancelled，进度经 `_publish_progress` 发布 | confirmed | `agent_jobs.py:13-17,34-84` |
| S6 | `execute_fast_analysis(*args, **kwargs)` 是**按需**任务（`acks_late=True`），不在 Beat schedule 中；委托 `services.fast_analysis_tasks.run_async_analysis_task` | confirmed | `fast_analysis.py:8-12` |
| S7 | 非 Celery 长驻调度器在 `_start_scheduler_services` 启动：portfolio_monitor 线程、usdt_order_worker、indicator_signal_alerts worker；portfolio_monitor 线程以 `_stop_event.wait(...)` 循环，冷却下限相关等待 30s | confirmed | `startup.py:240-249`；`portfolio_monitor.py:1755-1762,1825` |
| S8 | 既有持仓同步 worker 循环内调用 `_sync_positions_best_effort`；同步间隔 env `POSITION_SYNC_INTERVAL_SEC`，下限 30s | confirmed | `pending_order_worker.py:416`；`pending_orders/position_sync_cache.py:43-44` |

---

## 2. 设计目标与非目标

### 2.1 目标

1. **周期对账**：按可配置周期（档位占位，阈值待校准）拉取交易所侧订单/持仓快照，与本地账本经 `core.execution.reconcile` 同一口径比对，产出结构化对账报告与告警；不干净时按既有 `enforce` 路径触发 KillSwitch。
2. **指标漂移告警**：按周期对在跑策略的收益序列与（可选）特征分布做漂移扫描，复用 `DriftMonitor` 与 `core.models.drift`，输出告警、健康分与降级建议，供人工评审；不自动改仓位。
3. **可审计**：每轮对账/漂移扫描留存输入快照标识、时间戳、口径版本、指标值、告警代码与调用来源，满足「决策可审计」不变量。
4. **阈值分布化**：所有触发阈值走 CLEAN/历史分布校准路径（分位数/基线），文档内先占位，禁止绩效网格搜索。

### 2.2 非目标（本轮明确不做）

- 不新增 Celery Beat 条目、不写任务代码、不改调度拓扑。
- 不修改 `drift_monitor.py` / `reconcile.py` 的现有默认数值，不新增风控阈值常量。
- 不实现自动修复（自动补单、自动平仓、自动改仓位）；对账差异只报告与触发既有保护链路，处置动作走人工或既有授权流程。
- 不触碰实盘资金路径内部实现；本设计仅描述接入关系。
- 不设计新的绩效指标体系；不编制任何 Sharpe / 回撤 / 胜率目标值。

---

## 3. 周期对账设计

### 3.1 触发点（设计描述，不落代码）

候选触发方式，按触发频率从高到低：

| 触发类型 | 说明 | 现状衔接 | 等级 |
|---|---|---|---|
| T1 定时轮询 | 按周期拉取交易所快照并对账；周期档位为占位，最终由运行基线（worker 负载、API 限速、既有同步间隔下限 30s，见 S8）与运维要求确定 | 新周期任务的候选落点见 §6；复用 S2 的 env 开关 + 间隔下限模式 | inferred |
| T2 事件后触发 | 关键事件后补一次对账：下单/成交回报后、worker 恢复后、策略重启恢复后 | 现状已有启动后延迟持仓同步线程（`startup.py:190-210`，S8）；设计上可作为事件钩子复用，不新建独立线程模型 | confirmed（既有事件同步存在）/ inferred（对账挂钩点未实现） |
| T3 按需人工触发 | 人工在评审/排障时发起一次对账，作为持久化作业或路由动作 | 现状 `reconcile_strategy_vs_account` 为按需路由对账（R11）；本设计不重复造路由 | confirmed |

约束：
- 对账只使用**已收盘/已回报**数据；快照时间戳与本地账本时间戳均需记录，晚于对账时刻的回报不纳入本轮（对齐 intra-bar 因果规则，`AGENTS.md` 硬规则 5）。
- 拉取层（网络 I/O）放在 core 之外；`reconcile()` 保持纯函数无 I/O（R1）。

### 3.2 比对口径

**复用现有口径**（不另起一套比对规则）：

- 订单：`order_id` 主键；`side` 归一化后比较；`quantity`、`filled_quantity` 在容忍度内视为一致（R2、R5）。
- 持仓：`symbol` 主键；净持仓模型；`side`、`quantity` 容忍度内比较（R2、R6）。
- 容忍度沿用 `Tolerance(qty_abs, qty_rel)`；当前默认 `1e-6 / 1e-4`（R3）。**是否需要按品种/经纪商调整容忍度，属待评审项；本轮不改默认值。**

**现状口径未覆盖、设计上列为待补缺口**（不预设数值）：

| 缺口 | 现状 | 设计建议 | 等级 |
|---|---|---|---|
| G1 开仓价未比对 | `entry_price` 携带但不参与比对（R9） | 评估是否纳入持仓比对；若纳入，需定义价格容忍度来源（品种最小变动价位，走 SymbolInfo/配置，不硬编码点值） | confirmed（缺口）/ inferred（建议） |
| G2 订单状态未比对 | `status` 字段未参与比对（R9） | 评估「本地 PENDING / 经纪商 FILLED」类状态不一致是否单独成码 | confirmed（缺口）/ inferred（建议） |
| G3 余额/权益未对账 | 现有对账只覆盖订单与持仓视图，未见账户余额/权益快照比对 | 列为二期候选；口径需对接既有账户快照服务（`live_trading/account_snapshot.py`，本轮未精读） | unknown |
| G4 费用/资金费 | 后端已有手续费对账、资金费对账等独立服务（R11） | 新周期对账**不重复实现**，只在报告中引用其最新结果标识；具体衔接待评审 | confirmed（服务存在）/ unknown（接口衔接） |

**对账报告结构**：沿用 `ReconcileReport.to_dict()` 的字段集（`is_clean`、`codes`、各缺失/多余/偏差列表、tolerance），周期任务在其外包裹一轮元数据：`run_id`、`strategy_id`（如适用）、`venue`、`snapshot_at`、`local_ledger_at`、`fetched_at`、`caller`、`tolerance_version`。

### 3.3 所需指标（对账面）

| 指标 | 口径 | 来源/依据 | 等级 |
|---|---|---|---|
| 对账是否干净 | `is_clean`（无严重代码） | R4 | confirmed |
| 各类严重代码计数 | 八类 code 各自出现条数 | R4 | confirmed |
| 订单/持仓偏差量 | 数量差 `delta = broker - local` | R2、`reconcile.py:250,256,293` | confirmed |
| 快照新鲜度 | `fetched_at - snapshot_at`、本地账本时间戳 | 设计新增元数据；字段口径待实现评审 | inferred |
| 连续不干净轮次 | 连续 N 轮 `is_clean=False` 计数；N 为待校准占位阈值 | 设计新增；阈值来源见 §5 | inferred |
| 拉取/比对失败次数与错误归类 | 网络/鉴权/解析/超时分类计数；异常带上下文记录（对齐 `AGENTS.md` 硬规则 9） | 设计新增；错误归类可参考 `live_trading/error_classification.py`（本轮未精读） | inferred |
| 对账耗时 | 本轮拉取+比对墙钟时间 | 设计新增；用于容量评估 | inferred |

### 3.4 结果分级与处置

- **clean**：记录一轮成功对账（含快照标识），不触发告警。
- **non-clean**：
  1. 报告完整落审计（字段见 §3.2）；
  2. 经 `enforce(report, kill_switch, source=...)` 既有路径触发 KillSwitch（R7）；`source` 标识周期对账调用方，便于审计溯源；
  3. 告警分级复用现有严重度语义（D4）；对账类不一致默认高于一般漂移告警，具体级别映射待评审。
- **处置边界**：周期对账**不自动补单/平仓/改仓**；幽灵持仓、漏单、重复单的处置走既有授权流程与人工评审（对齐 R11 既有服务边界）。

---

## 4. 指标漂移告警设计

### 4.1 触发点（设计描述，不落代码）

| 触发类型 | 说明 | 现状衔接 | 等级 |
|---|---|---|---|
| M1 周期复盘扫描 | 按周期汇总在跑策略的已实现收益序列，喂入 `DriftMonitor.check_drift()`；频率档位占位，由校准与运维基线确定 | 现状 `DriftMonitor` 仅在网关检查时构造（D10）；生产周期扫描不存在（D11） | confirmed（现状缺口）/ inferred（设计） |
| M2 特征分布扫描 | 对模型/信号特征做 PSI 与滚动命中率跟踪；reference 分布取自训练/CLEAN 段 | 复用 `core.models.drift`（D9）；特征采集口未在本切片核对 | confirmed（工具存在）/ unknown（接入口） |
| M3 事件后评估 | 策略上线、参数变更、市场结构突变后补一次基线对照 | 设计候选；现状无对应钩子 | inferred |

约束：
- 漂移基线（baseline Sharpe / 胜率 / 回撤）必须取自 **CLEAN/训练段**或策略上线时冻结的基线，禁止用近期表现反推基线后再宣布漂移；统计量只使用当前及历史数据（因果顺序，对齐 `AGENTS.md` 硬规则 1、3）。
- 漂移告警只产出建议与告警；**仓位调整建议**（D7 的四档）须经人工/既有风控链路执行，周期扫描本身不下单。

### 4.2 比对口径

- **绩效漂移**：滚动窗口收益 → 当前 Sharpe / 胜率 / 最大回撤，与冻结基线比较；偏离度口径沿用 `DriftMonitor` 现有算法（D2、D3）。
- **显著性区分**：样本达标时跑显著性检验，区分「真漂移」与「随机波动」；样本不足时不给显著/不显著结论（D5）。
- **漂移分型**：前后半段均值对比 + 健康分 → `stable / gradual_decay / sudden_failure`（D6）。
- **特征漂移**：PSI 分桶按 reference 分布分位数（D9）；滚动命中率为因果滚动窗口，只用当前及历史样本（`core/models/drift.py:36-40`）。
- **基线冻结与版本**：每轮扫描记录 baseline 来源（数据集/区间/版本）、窗口长度、样本数；baseline 更新须走独立评审，不在周期任务内自更新。

### 4.3 所需指标（漂移面）

| 指标 | 口径 | 来源/依据 | 等级 |
|---|---|---|---|
| 滚动 Sharpe / 胜率 / 最大回撤 | 当前窗口统计量；样本 <20 回退（D2） | D2 | confirmed |
| 基线值与偏离度 | baseline 与当前值、偏离比例/差值/倍数 | D3 | confirmed |
| 告警列表 | 类型、当前值、基线值、偏离度、严重度、消息 | D4 | confirmed |
| 显著性 | t 统计量、p 值、是否显著、结论；样本 <30 判样本不足 | D5 | confirmed |
| 漂移分型 | stable / gradual_decay / sudden_failure / insufficient_data；样本 <50 判不足 | D6 | confirmed |
| 健康分与建议档位 | 0–100 健康分；四档降级建议 | D7 | confirmed |
| PSI / 滚动命中率 | 特征分布稳定性；命中率相对训练段偏移 | D9 | confirmed |
| 样本充足性标记 | 收益条数、特征有效条数是否达门槛 | D2、D5、D6 | confirmed |

### 4.4 现有阈值与校准状态（如实标注）

| 参数 | 代码内默认值 | 现状性质 | 证据 |
|---|---|---|---|
| Sharpe 下降告警线 | 0.3（下降 30%） | 代码默认占位；未见分布校准记录 | `drift_monitor.py:50,117` |
| 胜率下降告警线 | 0.1（10 个百分点） | 同上 | `drift_monitor.py:51,132` |
| 回撤扩大告警线 | 2.0（2 倍） | 同上 | `drift_monitor.py:52,147` |
| 滚动窗口 | 100 | 代码默认；窗口长度属统计口径，需按样本频率与基线评审 | `drift_monitor.py:53,76-77` |
| 基线 Sharpe / 胜率 / 回撤 | 1.0 / 0.5 / 0.15 | 构造器默认；生产基线应由 CLEAN 段计算（参照 D10 网关做法：基准收益算 baseline） | `drift_monitor.py:47-49`；`verification_middleware.py:319-326` |
| 显著性基线日收益 / alpha | 0.0005 / 0.05 | 代码默认；alpha 为检验水平约定值；baseline_mean 应来自基线分布 | `drift_monitor.py:206-207` |
| PSI 切点 | 0.1 / 0.25 | 文档字符串约定值；本仓库未见回测校准 | `core/models/drift.py:4-5` |
| 样本门槛 | 20（统计量）/ 30（检验）/ 50（分型） | 代码内硬性最小样本数；属统计充分性门槛，非绩效阈值，是否调整需评审 | `drift_monitor.py:81,92,99,110,225,280` |

> 说明：本轮**不编制**任何目标 Sharpe、目标回撤、目标胜率；上表数值全部来自代码读取，未做绩效推断。

---

## 5. 阈值分布化原则（对齐不变量 3）

1. **校准来源**：漂移告警阈值（偏离比例、回撤倍数、PSI 切点等）应在 CLEAN 集上以分布分位数/基线波动带确定；基线统计量（Sharpe/胜率/回撤/日收益均值）由 CLEAN 或上线冻结段计算。集合分离约束沿用 `AGENTS.md` 硬规则 2；`core/data/splits.py`、`core/data/validator.py` 为现有划分落点（confirmed 存在，本轮未精读其内部口径）。
2. **禁止事项**：不得用回测 PnL 网格搜索挑选告警阈值；不得在周期任务内用最近表现自校准基线；不得触碰静默集做阈值或基线估计。
3. **占位与转正流程**：设计期阈值以占位形式记录来源与待校准状态；正式阈值经校准脚本/评审后落入受控配置（`configs/` 变更需人工确认，见 `AGENTS.md` 停止条件），本草案不写具体数值。
4. **对账容忍度**：数量容忍度优先来自品种合约规格（最小变动/步进，走 SymbolInfo 与配置）；默认 `1e-6 / 1e-4`（R3）是否沿用待评审，本轮不改。
5. **告警去抖**：连续 N 轮确认、冷却/静默时长等参数同样走分布/运维基线校准；设计上预留「连续不干净轮次」与「告警冷却」字段（§3.3、§6.3），数值待校准。

> 备注：`AGENTS.md` 引用的 `docs/data_splits.md` 路径在本轮实测**不存在**（MISSING）；三分集（CLEAN/KNOWN/静默集）的文字定义见 `docs/ANTI_FRAGILE.md:28-32,58`，正式划分文档缺失一项，列入剩余风险。

---

## 6. 与现有调度的接入点（仅设计描述，不落代码）

### 6.1 接入点总览

```
                        ┌─────────────────────────────────────────────┐
                        │                Celery Beat                  │
                        │  celery_app.py:59-80 beat_schedule          │
                        └───────────────┬─────────────────────────────┘
                                        │ 周期触发（候选，本轮不注册）
            ┌───────────────────────────┼───────────────────────────┐
            ▼                           ▼                             ▼
  maintenance.py 风格任务        非 Celery 长驻线程             既有 worker 循环
  （env 开关/重试/队列）         （startup._start_scheduler_    （pending_order_worker
   §6.2                          services，S7）                 既有持仓同步，S8）
            │                           │                             │
            └───────────────┬───────────┴───────────────┬─────────────┘
                            ▼                           ▼
                 拉取交易所快照（core 外）        读取本地账本/收益序列
                            └───────────────┬───────────┘
                                            ▼
                  core.execution.reconcile（纯函数，R1）
                  core.monitoring.drift_monitor / core.models.drift
                                            ▼
                        报告/告警 → 审计记录；non-clean → KillSwitch（R7）
```

### 6.2 `maintenance.py`（维护类周期任务）—— 候选主接入点

- **现状调用关系**：Beat 按 `celery_app.py:59-80` 调度 → `maintenance.py` 中带 `@celery_app.task` 的任务；任务先经 `_enabled(env)` 开关判定，再委托对应 Service；反射/校准/目录同步三类带退避重试（S2、S3）；队列归 `maintenance`（S4）。
- **设计衔接**（待评审，本轮不改）：
  - 周期对账与周期漂移扫描若走 Celery，可沿用同一模式：env 开关、`max_retries=3` + backoff/jitter、结果返回结构化 dict、失败带上下文记录。
  - 新任务名、Beat 条目、env 变量名、间隔档位均属后续实现评审项；本草案不命名具体任务，不写注册代码。
  - 对账任务与漂移扫描任务建议独立注册、独立开关：对账偏安全闭环（失败倾向保守，见 §7），漂移扫描偏观测（失败倾向告警漏报但需记录）。
- **约束**：任务内不得直接读静默集；基线/统计量计算遵守因果与集合分离规则。

### 6.3 `agent_jobs.py`（按需持久化作业）—— 候选人工触发通道

- **现状调用关系**：外部触发 → `execute_agent_job(job_id)`（acks_late，队列 `jobs`）→ `agent_jobs.get_job_for_worker` 取行 → 状态置 running → `_execute(kind, payload, on_progress)` → 成功/失败回写并发布进度；当前仅支持 `backtest`（S5）。
- **设计衔接**：
  - 一次性人工对账/漂移评审可作为新 kind 走持久化作业模型（状态机、进度发布、结果落库可复用）；**不建议**用它承担高频周期对账（其模型是按需、单作业生命周期）。
  - 新增 kind 属于实现变更，需后续评审；本草案不扩展 `SUPPORTED_KINDS`。

### 6.4 `fast_analysis.py`（按需 AI 分析）—— 报告呈现层候选，不承担对账

- **现状调用关系**：`execute_fast_analysis(*args, **kwargs)`（acks_late，队列 `ai`）→ `services.fast_analysis_tasks.run_async_analysis_task`（S6）。
- **设计衔接**：
  - 漂移扫描产出的结构化结果（健康分、分型、告警列表）可复用既有 AI 分析的结果落库/呈现通道生成复盘视图；对账原始差异不经过 AI 分析通道，避免安全闭环依赖模型可用性。
  - 本任务为按需触发，不在 Beat 周期链路内；不承担周期扫描。

### 6.5 非 Celery 调度与既有 worker —— 现状衔接，避免重复

- `startup.py:_start_scheduler_services` 启动 portfolio_monitor、usdt_order_worker、indicator_signal_alerts 三个长驻线程（S7）；新增周期服务若走线程模型，应与现有 `_stop_event` 生命周期模式对齐，但**优先评估**是否应归入 Celery Beat 以统一重试/队列/可观测性（选型待评审）。
- `pending_order_worker` 循环既有 `_sync_positions_best_effort`（S8）；周期对账应在其同步结果之上做账本 vs 交易所比对，**不另起一份持仓拉取**；两次拉取之间的状态漂移需在报告中以快照时间戳标注（§3.2）。
- 后端既有按需对账 `reconcile_strategy_vs_account`（R11）与周期对账的分工：按需路由面向单次排障/页面刷新，周期任务面向持续闭环；两者共享同一比对口径，不复制逻辑。

### 6.6 告警落点候选

- 进程内：`ObservabilityService` 的 Metric/Alert/AlertRule 与回调（D12）；`AlertSeverity` 枚举可承接严重度映射。
- 持久化：本轮**未发现**对账/漂移告警专用表（unknown，未穷举 DB schema）；告警是否落库、落在哪张表、是否接入 `ops/prometheus` 既有规则体系（见 `docs/design/observability-metrics-alerting.md` §0.2），属后续评审项。
- KillSwitch：对账 non-clean 经既有 `enforce` 路径触发（R7）；漂移告警**不直接**触发 KillSwitch，仅输出建议，避免观测性问题直接切断交易（分级策略待评审）。

---

## 7. 失败降级矩阵

| 场景 | 降级行为 | 倾向 | 依据/等级 |
|---|---|---|---|
| 交易所快照拉取失败（网络/超时/鉴权） | 本轮标记「对账未完成」，不产出 clean 结论；记录错误归类与上下文；按重试策略退避重试；连续失败达占位阈值后上报告警 | **fail-closed 倾向**：在未能核对交易所状态前，不宣称账本一致 | R1 纯函数边界；S3 重试模式；`inferred`（连续失败阈值待校准） |
| 本地账本读取失败 | 同上，本轮不判定；异常带策略/账本标识上下文记录 | fail-closed | 硬规则 9（异常必须带上下文）；`inferred` |
| 收益序列样本不足（<20 / <30 / <50） | 对应统计量/检验/分型返回样本不足标记，不产生显著漂移结论；不据此降仓 | fail-open（观测类）：样本不足不告警为漂移 | D2、D5、D6 confirmed |
| 特征分布 reference 缺失或有效样本不足 | PSI/命中率返回 NaN/不足标记，跳过特征层告警 | fail-open（观测类） | `core/models/drift.py:18-20,33-39` confirmed |
| 漂移计算抛异常 | 记录异常上下文，本轮扫描标记失败；不把异常误判为漂移；不触发仓位动作 | fail-open（观测类），但失败本身需可被监控发现 | inferred；对齐硬规则 9 |
| 告警通道/持久化不可用 | 核心对账报告先落本地审计日志（可用性优先）；告警上送失败进入重试/死信候选；不阻塞对账主流程 | 报告优先于告警 | inferred；D12 进程内告警的持久性 unknown |
| KillSwitch 已触发状态下重复对账 | 不重复触发同一 reason；审计追加记录；复位需授权（operator + reason + 审计） | 沿用既有 KillSwitch 语义 | `core/control/kill_switch.py:117-158` confirmed |
| 经纪商/适配器字段缺失 | 归一化层对未知侧别原样小写（R5）；缺字段的视图进入 mismatch/unknown 分类，不静默跳过 | 显式失败优于静默一致 | R5 confirmed；`inferred`（缺字段归类细则） |

---

## 8. 审计与可追溯要求（设计约束）

1. 每轮留存：`run_id`、任务/调用方标识、策略与品种、venue、两侧快照时间戳、口径与容忍度版本、指标原始值、告警代码/严重度、结论、失败归类。
2. 对账报告与漂移告警均须可回溯到当次输入快照；快照保留周期与存储位置属后续评审项（不触碰 `ledger/` 既有数据）。
3. 所有阈值/基线记录来源（数据集、区间、版本、校准方式）；占位值与已校准值在记录中显式区分。
4. 决策可审计：周期扫描输出的建议不得直接改写执行层状态；任何接受/拒绝建议的动作须另行留痕。

---

## 9. 未自动验证项与剩余风险

### 9.1 本轮未自动验证（显式标注「未验证」）

| 项 | 状态 | 说明 |
|---|---|---|
| 实盘对账冒烟 | **未验证** | 未连接任何实盘/模拟交易所，未跑真实快照比对；仅静态阅读核心模块与既有测试。 |
| 经纪商/适配器差异 | **未验证** | `live_trading/` 下多适配器（okx/binance/bybit/bitget/htx/alpaca/spot 变体等）的订单/持仓字段口径未在本切片精读；不同 venue 的成交回报、部分成交、手续费口径差异 unknown。 |
| 容器内调度拓扑 | **未验证** | 未读 `docker-compose*.yml` 与部署配置；Beat/worker/API 进程角色划分、新周期任务在容器内的可达性 unknown。 |
| 告警持久化与通知通道 | **未验证** | 进程内 `ObservabilityService` 存在（D12），但告警落库表、通知渠道（站内/邮件/webhook 等）未核对。 |
| 后端既有对账服务内部口径 | **未验证** | `account_positions.reconcile_strategy_vs_account`、`pending_order_position_sync`、activity/funding/fee/ledger 对账仅核对存在性与调用点，未精读其比对规则。 |
| 全量测试 | **未执行** | 本轮仅跑对账+漂移两个测试文件（27 passed）；`pytest -q` 全量未跑。 |

### 9.2 剩余风险

1. **口径缺口**：开仓价、订单状态、余额/权益尚未纳入比对（G1–G3）；周期对账上线后仍可能存在「订单持仓一致但价格/权益偏离」的盲区。
2. **阈值未校准**：漂移监控现有默认值均为占位（D8、§4.4）；直接投入生产可能出现误报/漏报，须经 CLEAN 分布校准后转正。
3. **基线污染风险**：若周期任务误用近期表现刷新基线，会造成漂移感知钝化；设计上要求基线冻结与版本留痕（§4.2），实现时需有守卫。
4. **重复对账风险**：后端已存在多条对账/同步链路（R11）；新周期任务若不复用既有拉取与口径，可能产生双重状态与不一致结论。
5. **文档缺口**：`docs/data_splits.md` 被 `AGENTS.md` 引用但实测缺失；划分口径需以 `core/data/splits.py` 与 `ANTI_FRAGILE.md` 为准，建议补齐该文档。
6. **进程内告警易失**：`ObservabilityService` 为内存结构（D12），进程重启后历史告警可见性 unknown；周期对账的审计留痕不能仅依赖该单例。

---

## 10. 后续评审清单（不属本轮实现）

- [ ] 周期对账与漂移扫描的触发周期、队列归属、开关 env 命名（§6.2）。
- [ ] 对账是否纳入开仓价/订单状态/余额比对（G1–G3）。
- [ ] 基线与告警阈值的 CLEAN 集校准方案、占位值转正流程（§5）。
- [ ] 告警落库表与通知通道选型；与 Prometheus/Alertmanager 既有规则的衔接（§6.6）。
- [ ] 与既有按需对账、持仓同步、费用/资金费对账服务的接口边界（R11）。
- [ ] 容器部署拓扑下新周期任务的进程角色与故障转移（§9.1）。
