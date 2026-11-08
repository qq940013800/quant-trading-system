# 设计草稿：知识沉淀与复用管道（决策审计 · 复盘归因 · 生命周期 · 故障/实验/Playbook · 检索与 API）

> 状态：**待评审草稿**（切片 #159 落地设计）。本轮只新增本文件，不改任何实现代码、不新建 DB 表、不写迁移。
> 边界：不触碰 `configs/`、`registry.yaml`、`mt5/`、`secrets/`、`runtime/`、`ledger/`；实盘资金路径（`live_trading/`、`quick_trade/`、`pending_orders/`、`native_protection`、`strategy_runtime/`、`strategy_v2/deployment.py`、凭证写库）本轮只读勘察，不改代码。
> 不变量约束（`AGENTS.md`）：因果单向（只用 `available_at <= bar.close` 的数据）、决策可审计（每笔接受/拒绝可还原各层输入与判断）、阈值来自分布（不由绩效网格搜索产生）；硬规则 1（前视守卫）、2（集合分离：ATR/vol/Hurst 只在 CLEAN 集估计；供需区只用 KNOWN 集构建）、3（L1 位置 → L2 状态 → L3 触发，禁止 L3 反哺 L1）、5（intra-bar：信号与退出决策只在已收盘 bar 调用）、9（异常必须带上下文记录）、10（改动附单测，黄金集断言不放宽）。
> 证据分级：**confirmed** = 本轮只读核对到代码/DDL 落点；**inferred** = 由已核对结构推断，未在生产路径直接验证；**unknown** = 本轮未核对或无法判定。
> 术语对齐：决策链 `L1 位置 → L2 状态 → L3 触发 → 仓位 → 风控 → 执行`（`docs/knowledge/04_ai_ml_systems.md:20`，confirmed）；既有设计口径见 `live-trading-gates-and-reconciliation-design.md`（下称「闸门草案」）、`reconciliation_drift_alarm_design.md`（下称「对账草案」），本文不重复其结论。
> 草案来源：飞书《知识沉淀与复用管道架构》revision 4（只读锚点，非已实现现状）；现状落点以本地代码复核为准。

## 0. 本轮范围与现状勘察

### 0.1 任务覆盖

| # | 主题 | 本文小节 |
|---|---|---|
| K1 | 决策审计日志四段结构（signal / risk_check / execution / outcome）与订单流追踪链路 | §1 |
| K2 | 复盘归因：运气 vs 策略贡献拆分、因子预测力口径、样本门槛 | §2 |
| K3 | 生命周期八阶段状态机与拥挤/衰减/退役检测阈值原则 | §3 |
| K4 | 故障库 / 实验追踪 / Playbook 条目结构 | §4 |
| K5 | 检索机制：全文 + 标签基线；向量语义检索标注推断 | §5 |
| K6 | API 契约草案（读/写形状、三入口复用关系） | §6 |
| K7 | 单测计划：纯函数可测点、I/O 注入桩、既有骨架复用 | §7 |
| K8 | 建表 DDL 与实盘接线「待人工确认」；未验证项清单 | §8 |

### 0.2 已核对的现状落点（confirmed，除标注外）

| # | 现状结论 | 落点 | 分级 |
|---|---|---|---|
| A1 | `Decision` 冻结快照含：`decision_id / signal / feature_snapshot / model_version / risk_state / accepted / reject_reason / final_signed_lots / threshold_dataset(CLEAN\|KNOWN) / decision_rule_version / r_multiple_at_close`；构造不变量：接受单手数 >0，拒绝单手数 =0 | `core/audit/record.py:65-102` | confirmed |
| A2 | 决策快照单行 JSONL 追加写盘；NaN/inf 序列化为 null；序列化异常 `SignalLikeError` 携带 layer/detail 上下文 | `core/audit/record.py:36-62,112-125` | confirmed |
| A3 | 决策写库目标表 `qd_ai_decisions`，字段映射：decision_uid/source_type/symbol/action/market_type/model/decision/allowed/confidence/reason/fallback_reason/probabilities_json/checks_json/request_snapshot/billing_json/latency_ms；写库失败只记日志返回 False，不阻断主流程 | `core/audit/db_writer.py:60-97,103-141` | confirmed（代码路径）；**unknown**（该表 CREATE DDL 未在 `migrations/` 与 `scripts/*.sql` 中定位到，见 §8.1） |
| A4 | 成交/持仓级日志写 `qd_trade_journal`：trade_uid、symbol、side、entry/exit 时间与价格、quantity、stop/tp、gross/commission/slippage/net pnl、r_multiple、strategy_id、`decision_id`、market_regime、entry/exit_reason、confidence、status(open/closed)；开仓先写 open，平仓回填 exit 字段 | `core/audit/db_writer.py:247-339`；`scripts/trade_journal_init.sql:7-49` | confirmed |
| A5 | 实验记录 `qd_experiment_logs`：start 写 hypothesis/experiment_type/control/treatment/sample_size/duration/strategy_id，`decision_rule_frozen=true`、`freeze_at`、`trials_count=1`、status=running；end 回填 metrics_json/result_json/p_value/effect_size/conclusion/decision/decision 取值 `promote_to_production/pivot/abandon` | `core/audit/experiment_logger.py:54-118,120-181` | confirmed |
| A6 | 故障捕获：分类映射 connection/timeout/permission/data/order/risk/config/system；`capture(symptom, exception, context, solution, category)` 落 `qd_fault_knowledge`，初始 `verified=false`、`confidence_score=0.5`、severity 默认 P2；装饰器 `auto_capture_fault` 捕获后 **re-raise**，不吞异常 | `core/audit/fault_catcher.py:23-32,53-100,141-163` | confirmed |
| A7 | 复盘自动触发：占位阈值 单笔 `-3.0R`、连续亏损 5 笔、单日亏损 5%；触发类型 `single_big_loss / consecutive_losses / daily_big_loss`；自动写一条 open 复盘记录，根因/教训留「待人工分析」 | `core/audit/review_monitor.py:27-31,50-110` | confirmed（阈值为代码默认占位，未见 CLEAN 校准记录，**inferred** 未接校准流程） |
| A8 | 策略健康诊断：closed 成交 <10 笔返回 `insufficient_data`；三级 green/yellow/red；指标 win_rate / profit_factor / avg_r；代码默认切点 胜率 0.50/0.45、PF 1.3/1.1、avgR 1.0/0.5；健康分基础 50 | `core/audit/strategy_health_monitor.py:37-49,50-90,134-165` | confirmed（切点为行业经验默认值，未见分布校准记录，**inferred**） |
| A9 | 知识检索基线：PostgreSQL `ILIKE` 关键词全文匹配 + category 过滤；故障库 `qd_fault_knowledge`（仅 `verified=true`），复盘库 `qd_post_mortems`（仅 `status='closed'`）；决策前教训聚合 `get_lessons_for_decision(symbol, side, signal_type)`；统计接口返回三类记录计数 | `core/audit/knowledge_retriever.py:40-91,93-134,136-167,169-211` | confirmed |
| A10 | 审计回放：`feature_snapshot` 必需 sizing 输入键 `equity/risk_pct/stop_dist_price/point_value/min_lot/lot_step/kelly_cap/vol_scale`；用冻结签名重算手数与快照比对；拒绝单手数必须为 0；不一致抛 `ReplayMismatch` | `core/audit/replay.py:40-43,46-89` | confirmed |
| A11 | 前视检测器：时间戳严格递增、`feature_time <= decision_time`、特征-标签泄露、滚动窗口纯净度、训练/测试时间分离；违规分级 high/critical | `core/audit/lookahead_detector.py:46-81,83-116,144-166` | confirmed |
| A12 | 生命周期状态机：`DRAFT→BACKTESTING→AB_TESTING→PAPER_TRADING→LIVE_SMALL→LIVE_FULL→MONITORING→RETIRED`，另 `REJECTED`；`VALID_TRANSITIONS` 白名单；`LifecycleEvent(timestamp, from_state, to_state, reason, metrics)`；`LaunchCriteria` 默认 min_sharpe 1.0 / max_dd 0.20 / min_trades 30 / ab_alpha 0.05 / max_overfit 0.3 / min_live_days 7 | `core/experiment/strategy_lifecycle.py:26-50,56-63,150-158` | confirmed（LaunchCriteria 数值为代码默认占位，未见 CLEAN 校准记录，**inferred**） |
| A13 | 结构化审计日志：级别 DEBUG/INFO/WARNING/ERROR/CRITICAL；分类 DATA/FEATURE/SIGNAL/RISK/EXECUTION/STRATEGY/MONITOR/SYSTEM；`LogEntry(timestamp, level, category, message, strategy_name/version, symbol, pnl, extra)`；`log_decision(layer, decision, inputs, outputs)` | `core/logging/audit_logger.py:32-50,53-67,205-224` | confirmed |
| A14 | 后端既有路由：`POST /strategies/review-report`（入参 id/lookback_days/include_ai/language；计费与不足额 402；返回 `{code,msg,data}`）；`GET /strategies/review-report/history`；`GET /strategies/logs`（strategy_id/limit） | `backend_api_python/app/routes/strategy_review_routes.py:87-171,174-217`；`strategy_logs_routes.py:29-83` | confirmed |
| A15 | 分析记忆服务：`store/get_recent/get_all_history/delete_history/create_pending_task/finalize_pending_task/fail_pending_task/record_feedback/validate_past_decisions`；相似形态为**规则加权**匹配（RSI±15 权重 0.3、MACD 精确 0.3、MA 趋势 0.25、波动档位 0.15；sim<0.25 过滤；仅取 `validated_at` 非空且 `was_correct` 非空） | `backend_api_python/app/services/analysis_memory.py:172-230,506-577,579-600` | confirmed |
| A16 | 订单流既有链路（DDL 核对）：`strategy_order_intents`（idempotency_key、client_order_id、exchange_order_id、status、payload_json）→ `strategy_order_fills`（order_intent_id、exchange_order_id、exchange_fill_id、fee）→ `qd_strategy_trades`（execution_event_id、exchange_fill_id）/ `qd_execution_events`（event_key 唯一、client/exchange order id、exchange_fill_id、order_status、price/qty/cumulative、realized_pnl、raw_json、processed_at）；费用组件 `qd_execution_fee_components`；归属投影 `qd_execution_owner_projections` | `migrations/init.sql:1750-1822,1852-1912` | confirmed |
| A17 | 故障/复盘/实验三表 DDL 与两个统计视图已存在于脚本；`qd_post_mortems` 含五层次复盘字段（what_happened/why_it_happened/what_we_learned/how_to_improve/how_to_harden）、action_items_json、status open/in_progress/closed、severity P0–P3；`qd_fault_knowledge` 含 prevention、tags_json(GIN)、occurrence_count、verified、status active/archived/deprecated、related 引用；`qd_experiment_logs` 含防过拟合字段 | `scripts/knowledge_pipeline_init.sql:8-121,125-226` | confirmed |
| A18 | 向量语义检索：在 `core/` 与 `backend_api_python/` 全仓检索 `embedding / pgvector / faiss / sentence_transformers / cosine_similarity / vector_store` **0 命中** | 本轮定向 grep | confirmed（无实现证据）；向量检索能力本身 **unknown** |
| A19 | 既有测试：`tests/test_audit_record.py`、`tests/test_audit_replay.py`、`tests/test_experiment/test_strategy_lifecycle.py`、`tests/test_logging/test_audit_logger.py` | 本轮目录核对 | confirmed（存在性；内容未逐行复核） |

---

## 1. K1 决策审计日志四段结构与订单流追踪链路

### 1.1 第一性原理目标

- **一笔决策一条根记录**：接受/拒绝都必须落一条 Decision（对齐 A1 纪律：拒绝信号不得省略）；四段快照挂在同一 `decision_id` 下，按时间先后异步补齐，禁止用后段结果回填前段判断。
- **因果单向**：signal 段只使用 `available_at <= bar.close` 的已收盘数据；risk_check 段只消费 signal 段输出与当前已拉取快照；execution/outcome 是事后段，其价格、盈亏、R 倍数**不得反哺** signal/risk_check 的因子取值或阈值（硬规则 3、5）。
- **可还原**：事后回放能还原五要素 `feature_snapshot / model_version / threshold_dataset / final_signed_lots / reject_reason`（A10），并沿订单流链路追到成交腿与最终盈亏。

### 1.2 四段字段口径（设计草案，不写实现代码）

根标识：`decision_id`（幂等键）、`strategy_id / strategy_run_id`、`symbol`、`venue/credential_id`（引用，不落敏感凭证）、`caller_entry`（`strategy_auto | manual | quick_ai`）、`created_at`、`rule_version`。

#### 段 S1 — signal（信号层，决策时刻冻结）

| 字段 | 口径 | 来源/对齐 |
|---|---|---|
| `side` / `signal_type` | 方向 buy/sell；触发规则族（breakout/trend/range/meta_label 等） | A1 `signal` 鸭子序列化 |
| `bar_ts_utc` / `available_at` | 信号所依据的已收盘 bar 时间戳；数据可用时刻；二者关系须满足 `available_at <= bar.close` | A11 `check_no_future_data` |
| `l1` | 位置层快照：区域/结构标识、`l1_in_zone`、区域构建所用数据集（KNOWN） | 硬规则 2；`mean_reversion.py` 信号字段 |
| `l2` | 状态层快照：regime 权重、ATR 分位、ADX/Hurst 等；统计量数据集（CLEAN） | 硬规则 2；`docs/knowledge/04_ai_ml_systems.md:24` |
| `l3` | 触发层快照：触发规则、专家/策略标识、是否经 meta-label 过滤 | 硬规则 3 |
| `factors` | 决策时刻因子值 dict（as_of 取值）；不允许含出场后才可知的字段 | A1 `feature_snapshot` |
| `confidence` / `model_version` | 信号置信度；模型/规则版本（无模型记 `rules-vN`） | A1 |
| `threshold_dataset` | 本决策阈值来源集 `CLEAN\|KNOWN`；构造即校验 | A1 `__post_init__` |
| `decision_rule_version` | 冻结的决策规则版本；实验场景与 `qd_experiment_logs.decision_rule_frozen/freeze_at` 对齐 | A5、A1 |

#### 段 S2 — risk_check（风控闸段，下单前冻结）

| 字段 | 口径 | 来源/对齐 |
|---|---|---|
| `risk_state` | 决策时刻风险快照：equity、atr0、entry_dist、stop_price、heat_units、circuit_state | A1 `risk_state` |
| `proposed_lots` | 提议手数；接受单 >0、拒绝单 =0 的不变量沿用 A1 | A1 |
| `stop_loss` / `risk_pct` / `risk_score` | 止损价（冻结 entry_dist 派生）、风险占比、风险评分；点值/手数来自 SymbolInfo 与配置，不硬编码 | 硬规则 8；闸门草案 §2.3 |
| `checks[]` | 逐项闸口记录：`check_name / passed / input_refs / reason_code / detail`；复用闸门草案 violation 码（账户暴露类、归属类、数据完整性类） | 闸门草案 §2.3、§2.4 |
| `limits_version` / `ownership` | 限额版本与归属结论透传；策略上下文缺失时归属检查跳过、暴露闸仍生效 | 闸门草案 §2.4 |
| `accepted` / `reject_reason` | 放行/拒绝结论；拒绝原因码（如 `meta_p<quantile_30` / `news_window` / `circuit_breaker`） | A1 |

#### 段 S3 — execution（执行段，成交回报后回填）

| 字段 | 口径 | 来源/对齐 |
|---|---|---|
| `intent_refs` | `idempotency_key / client_order_id`；对应 `strategy_order_intents` | A16 |
| `fill_refs` | `exchange_order_id / exchange_fill_id / execution_event_id / trade_uid` | A16、A4 |
| `entry_price / filled_qty` | 成交价与成交量；部分成交按回报分段记录，不合并成单笔推断 | A16 fills |
| `slippage / fill_time_ms / maker / fee` | 滑点（相对提议价）、成交耗时、maker/taker、费用与币种 | A16 fee 字段 |
| `filled_at` / `venue` | 成交时刻与场所；晚于决策时刻的回报不回填 S1/S2 | 硬规则 5 |

#### 段 S4 — outcome（结果段，平仓后回填）

| 字段 | 口径 | 来源/对齐 |
|---|---|---|
| `exit_price / exit_time / holding_hours` | 出场价、时刻、持仓时长 | A4 |
| `gross_pnl / commission / slippage_cost / net_pnl` | 毛盈亏、费用、滑点成本、净盈亏 | A4、`trade_journal_init.sql:26-30` |
| `r_multiple` | 盈亏比；一律用入场冻结的 `atr0/entry_dist` 计算，禁止用重算 ATR | `core/risk/stops.py:101-117`；A1 `r_multiple_at_close` |
| `exit_reason / market_regime` | 出场原因（止损/跟踪/人工/信号反向）；平仓时市场状态 | A4 |
| `attributed_to / lesson_learned / post_mortem_id` | 归因类别、教训摘要、关联复盘 | `trade_journal_init.sql:42-44` |

### 1.3 因果顺序与禁止反哺

1. 单向流水线：**L1 位置 → L2 状态 → L3 触发 → 仓位/风控 → 执行 → 结果**。L1 区域定义只用 KNOWN 集构建；L2 统计量只在 CLEAN 集估计；L3 触发结果（某区域被打穿后表现更好之类）**不得**回头改写 L1 定义（`docs/ANTI_FRAGILE.md:108-112`，confirmed）。
2. 段间冻结：S1/S2 在下单前冻结；S3/S4 只追加。回放校验时若发现 S1/S2 字段被 S3/S4 数值覆盖，记为审计违规（设计约束，检测实现属后续评审）。
3. 前视守卫复用 A11：时间戳单调、特征时间 ≤ 决策时间、训练/测试时间分离；进入管道前由检测器过一遍，违规记录 severity critical。

### 1.4 订单流追踪链路（设计对齐既有 DDL）

```
Decision(decision_uid)
  └─ S3.intent_refs.idempotency_key/client_order_id
        → strategy_order_intents(idempotency_key, client_order_id, exchange_order_id, status, payload_json)
              → strategy_order_fills(order_intent_id, exchange_order_id, exchange_fill_id, fee)
                    ├─ qd_execution_events(event_key, client_order_id, exchange_order_id,
                    │                      exchange_fill_id, order_status, price, qty, cumulative,
                    │                      realized_pnl, raw_json, processed_at)
                    └─ qd_strategy_trades(execution_event_id, exchange_fill_id)
                          → qd_trade_journal(decision_id, trade_uid)  ← S4 outcome 回填
```

- **关联键缺口（inferred/unknown）**：现有 DDL 中 `decision_uid` 与 `idempotency_key / client_order_id` 之间未见显式外键或统一关联字段；设计上要求决策快照生成时产出幂等键并透传进 intent `payload_json`，回填段按该键串链。当前代码是否已透传，本轮未核对（unknown）。
- 链路断链处理：某一环缺失时，审计记录标注 `link_missing: <环节>`，不静默补造关联；对账口径沿用对账草案 R2/R4，不另起一套比对。

### 1.5 可审计点

- 每笔决策留存：根标识、四段快照、阈值来源集、规则/模型版本、限额版本、各环关联键、调用入口、快照时间戳、失败归类。
- 回放：复用 A10 `replay_decision` 重算手数并比对；拒绝单快照手数必须为 0；接受单重算值与快照在容忍度内一致。
- 审计写库失败：沿用 A3 原则——不阻断交易主流程，失败记日志并返回 False；但写库失败率须可被监控发现（对齐闸门草案 §2.6「审计落库失败不阻塞结论，但需被监控」）。

---

## 2. K2 复盘归因方法

### 2.1 数据边界（硬约束）

- 归因只使用**已收盘 bar**与**已成交/已平仓**记录；open 仓位不参与胜率、R 倍数、因子预测力统计（A4 `status='closed'` 口径）。
- 样本内/样本外分离：基线与因子评估只用 CLEAN/KNOWN 段；静默集禁止读取（硬规则 2；对账草案 §5）。
- 不编制任何目标 Sharpe / 回撤 / 胜率；本文只定义口径，不产出绩效数值。

### 2.2 运气 vs 策略贡献拆分思路（设计口径）

| 拆分维度 | 思路 | 口径约束 | 分级 |
|---|---|---|---|
| 单笔 R 倍数 | 以入场冻结 entry_dist 计 R；区分「按规则执行的 R」与「偏离规则（手动改仓/提前出场/追单）的 R」；偏离记录单独打标，不计入策略样本 | R 倍数口径对齐 `stops.py`；偏离样本不与规则样本混合平均 | inferred（偏离打标字段尚未落地，见 §8） |
| 策略贡献 vs 基准 | 策略净盈亏与同期基准（品种买入持有/同 regime 基线）比较；超额部分才计入策略贡献；基准选取须在实验前冻结，不事后挑基准 | 基准来源、区间、版本随复盘记录留痕 | inferred |
| 噪声 vs 信号 | 样本达标后跑显著性检验，区分真 edge 与随机波动；样本不足只报描述统计，不下「策略有效/失效」结论 | 复用对账草案 D5 口径：样本 <30 返回样本不足；检验方法与基线均值来源待评审 | confirmed（门槛口径）/ inferred（接入点） |
| 执行成本剥离 | 毛盈亏 − 佣金 − 滑点 = 净盈亏；成本单独归因（复用 `v_cost_attribution` 视图口径），避免把成本侵蚀误判为策略失效 | `trade_journal_init.sql:125-141` | confirmed（视图存在） |
| 时段/regime 归因 | 按 `market_regime`、品种、时段分组统计 avg R / 胜率，定位 edge 集中区与失效区 | 复用 `v_regime_attribution / v_symbol_attribution` 口径 | confirmed（视图存在） |

> 方法论备注：二级预测（meta-labeling）的收益评估须走 purged/embargo 验证，避免标签泄漏（`STRATEGY_AUTO_MATCHING_DEEP_DIVE.md:169`，confirmed 引用）；本切片不实现二级模型评估流程。

### 2.3 因子预测力评估口径（设计草案）

| 指标族 | 口径 | 样本门槛（占位，待校准） |
|---|---|---|
| 排序相关性 | 因子值与前瞻收益的 Rank IC（Spearman）；按样本滚动窗口计算，只用历史样本 | 窗口最小样本数待校准；参照 `drift_monitor` 既有 20（统计量）/30（检验）/50（分型）门槛（对账草案 D2/D5/D6） |
| 分位单调性 | 因子分桶后各桶前瞻收益/胜率的单调性；桶内样本不足时该桶不参与结论 | 每桶最小样本数待校准 |
| 命中率 | 信号方向与后续已实现方向一致比例；按 confidence 分桶看校准度（参照 `analysis_memory` 的 confidence accuracy bucket 口径，A15） | 同上；样本不足返回 `insufficient_data`，不抛数值结论 |
| 稳定性 | IC/命中率在时间子段与品种子段的一致性；跨段反转记为不稳定 | 子段长度待校准 |

- 因子结论分三级：**样本外显著正向 / 不显著 / 反向**；证据不足记 `insufficient_data`，不得记负向结论。
- 禁止用实盘近期表现反推因子有效后再纳入生产；因子准入走实验记录（§4.2）与注册中心冻结流程（闸门草案 §4）。

### 2.4 需样本门槛的统计量清单（沿用既有 confirmed 门槛）

| 统计量 | 现有门槛 | 落点 |
|---|---|---|
| 滚动 Sharpe / 胜率 / 最大回撤 | <20 回退为默认值 | 对账草案 D2（`core/monitoring/drift_monitor.py`） |
| 显著性检验 | <30 判样本不足 | 对账草案 D5 |
| 漂移分型 | <50 返回 `insufficient_data` | 对账草案 D6 |
| 策略健康诊断 | closed 成交 <10 笔返回 `insufficient_data` | A8 |
| 新增 IC / 分桶 / 命中率 | 门槛待 CLEAN 分布校准后冻结，本文不填数值 | §2.3 |

---

## 3. K3 生命周期状态机

### 3.1 八阶段与既有状态机映射

草案八阶段：**发现 → 验证 → 小资金 → 规模化 → 拥挤 → 衰减 → 退役 → 复盘**。既有 `StrategyState` 为九态白名单（A12）。映射为设计对齐，非代码现状：

| 草案阶段 | 现有状态（A12） | 记录内容 | 进入/退出标准（占位，阈值待校准） | 分级 |
|---|---|---|---|---|
| 发现 | `DRAFT` | 策略假设、逻辑来源、初步回测记录 | 人工登记；假设与可证伪条件先冻结 | confirmed（状态存在）/ inferred（八阶段映射） |
| 验证 | `BACKTESTING → AB_TESTING → PAPER_TRADING` | 样本外测试、PBO/CPCV、压力测试、模拟成交与滑点 | 复用 `LaunchGate` 三项检查（回测就绪 / AB 通过 / 模拟就绪）；LaunchCriteria 默认值为占位 | confirmed（闸门存在）/ inferred（门槛校准） |
| 小资金测试 | `LIVE_SMALL` | 小仓位实盘、成交质量、回测-实盘差距 | 人工/评审进入；最小实盘天数占位（现 `min_live_days=7`，未校准） | confirmed / inferred |
| 规模化 | `LIVE_FULL` | 加仓过程、容量测试、市场冲击 | 评审进入；容量上限由成交冲击分布校准，不按绩效调 | inferred |
| 拥挤 | `MONITORING`（诊断标记 `crowding`） | 换手频率、信号重合度、edge 衰减迹象 | **现有状态机无独立 crowding 态**；检测指标与阈值均为草案 | unknown（无既有拥挤检测代码） |
| 衰减 | `MONITORING`（诊断标记 `decay`） | 收益/Sharpe/胜率/回撤相对冻结基线下滑 | 复用 `DriftMonitor` 与 `StrategyHealthMonitor`；基线取 CLEAN/上线冻结段 | confirmed（监控器存在）/ inferred（周期接线，对账草案 D11） |
| 退役 | `RETIRED` | 清仓过程、最终绩效、退役复盘报告 | 人工授权；状态机 `RETIRED` 为终态 | confirmed（终态存在） |
| 复盘 | 无独立状态；复盘记录流程（A7、A17 post-mortem） | 完整复盘、教训提炼、Playbook 沉淀 | 触发：亏损红灯（A7）或退役后人工发起 | confirmed（流程存在） |

### 3.2 状态机约束

- 只允许 `VALID_TRANSITIONS` 白名单内跳转；非法转换抛错（A12 `transition_to`）。八阶段映射不得新增跳步路径；拥挤/衰减是 `MONITORING` 内的诊断标记，不是绕过白名单的独立态。
- 每次转换落 `LifecycleEvent(timestamp, from_state, to_state, reason, metrics)`；metrics 只填已实现样本与冻结基线引用，不留待校准数值。
- 退役/否决为终态；退役策略经验沉淀到故障库/复盘/Playbook（§4），但其参数与基线不得被在跑策略直接复用而不经评审。

### 3.3 衰减 / 拥挤 / 退役检测的阈值原则

1. **阈值来自分布**：衰减告警切点、拥挤判据、退役建议线，正式取值须由 CLEAN/历史分布的分位数或冻结基线波动带校准；基线记录数据集、区间、版本、校准方式；占位值与已校准值在记录中显式区分（对齐不变量 3、对账草案 §5）。
2. **禁止事项**：不得用实盘 PnL 网格搜索挑阈值；不得在周期任务内用近期表现自更新基线；不得读取静默集估计阈值。
3. **现有默认值状态（如实标注）**：`DriftMonitor` Sharpe 降 0.3 / 胜率降 0.1 / 回撤 2.0 倍、基线 1.0/0.5/0.15（对账草案 D8）；`StrategyHealthMonitor` 胜率/PF/avgR 切点（A8）；`ReviewThresholds` -3R/5 笔/5%（A7）；`LaunchCriteria` 六项（A12）——均为代码默认占位，未见 CLEAN 校准记录，**不得视为已校准阈值**。
4. **检测输出边界**：监控只产出告警、健康分与降级建议；仓位调整/退役执行走人工或既有授权链路（对账草案 §4.4、D7），周期扫描本身不下单。

### 3.4 待校准的占位指标（草案，不填数值）

| 阶段 | 占位指标 | 校准来源 |
|---|---|---|
| 拥挤 | 换手频率相对基线倍数；策略间信号重合度；同类策略 edge 相关性；信号失效速度 | CLEAN/历史分布分位数；同类策略样本，待数据可得性评审 |
| 衰减 | 滚动 Sharpe/胜率/回撤相对冻结基线偏离度；PSI；滚动命中率偏移 | 复用 D2/D3/D9；基线冻结段 |
| 退役 | 健康分红灯持续轮次；显著性持续不达标；容量/冲击越界 | 分布校准 + 人工评审；连续轮次门槛属告警去抖参数（对账草案 §5.5） |
| 规模化 | 仓位边际冲击、滑点随规模变化曲线 | CLEAN 成交/滑点分布 |

---

## 4. K4 故障库 / 实验追踪 / Playbook 条目结构

### 4.1 故障知识库（对齐 `qd_fault_knowledge`，A6/A17）

| 字段 | 口径 | 分级 |
|---|---|---|
| `fault_uid` | 唯一幂等键；`fault-<hash>` 形式沿用 A6 | confirmed |
| `title / symptom` | 标题；现象描述（含错误类型、错误信息、上下文快照） | confirmed |
| `root_cause / solution / prevention` | 根因、解决方案、预防措施；初始可留「待分析」，随评审更新 | confirmed（DDL 含 prevention） |
| `category` | data / code / config / network / market / exchange；自动分类映射沿用 A6，人工可改 | confirmed |
| `severity` | P0 / P1 / P2 / P3；捕获默认 P2，可升级 | confirmed（DDL 枚举口径） |
| `tags_json` | 标签数组（品种、策略族、入口、错误码、组件）；GIN 索引 | confirmed |
| `occurrence_count / confidence_score / verified / status` | 出现次数；置信度 0–1；是否经人工验证；active / archived / deprecated | confirmed |
| `related_post_mortem_id / related_decision_id` | 关联复盘与决策 | confirmed |
| 可复现性要素（草案补充） | 触发条件、影响范围、复现步骤、代码版本/配置哈希、数据快照引用；缺失时 `reproducibility=partial` | inferred（现有表无对应列，见 §8.2） |

### 4.2 实验追踪（对齐 `qd_experiment_logs`，A5/A17）

| 字段 | 口径 |
|---|---|
| `experiment_uid / name / hypothesis` | 唯一键、名称、可证伪假设 |
| `experiment_type` | ab_test / parameter_search / new_strategy / feature_test |
| `design` | control_group、treatment_group、sample_size、duration_hours；验证方法（样本外/CPCV/PBO）引用 |
| `results` | metrics_json（分组指标）、result_json、p_value、effect_size；指标只记评估结果，不反推交易限额 |
| `conclusion / decision` | 结论；决策 `promote_to_production / pivot / abandon`（代码现状）；视图口径 `rollout/iterate/abandon` 差异见 §8.1 勘误 |
| 防过拟合 | `decision_rule_frozen`、`freeze_at`、`trials_count`（含失败/中止试验，只增不减，对齐 AGENTS 规则 11） |
| `reproducibility`（草案补充） | 数据快照引用、代码 commit、配置/参数哈希、模型制品版本；`status` running / completed / abandoned |

### 4.3 Playbook 条目（新增草案结构，对齐复盘 `how_to_harden / action_items_json`，A17）

| 字段 | 口径 |
|---|---|
| `playbook_uid / title / strategy_type` | 唯一键、标题、适用策略族/场景 |
| `tags` | 标签：品种、regime、入口、风险类型、来源类型 |
| `trigger_conditions` | 何时套用：信号形态、市场状态、故障症状、决策场景 |
| `preconditions` | 套用前提：数据完备性、仓位/账户状态、已验证样本门槛 |
| `steps[]` | 操作步骤（含禁止动作）；每步可关联校验点 |
| `risk_controls` | 止损/仓位/闸口约束；引用既有风控码，不复制限额公式 |
| `source_refs` | 来源：post_mortem_uid / experiment_uid / decision_uid / fault_uid |
| `version / status / owner` | 版本；draft / active / archived；责任人 |
| `reproducibility` | 数据快照引用、代码版本、配置哈希；验证状态 `validated_at` |
| `validated` | 是否经后续实盘/样本外对照验证；未验证 Playbook 标注 `unvalidated`，检索时降权 |

### 4.4 状态与严重度取值约定

- 故障状态：`active / archived / deprecated`；复盘状态：`open / in_progress / closed`；实验状态：`running / completed / abandoned`（均对齐 A17 DDL）。
- 严重度复用 P0–P3；检索默认只返回 `verified=true` 故障与 `closed` 复盘（A9），未验证条目可在显式请求下可见但标注。
- 知识生命周期：新条目先 draft/open → 人工验证/关闭 → active；失效条目归档而非删除（禁止删除文件/数据的边界在审计层同样适用：归档保留历史）。

---

## 5. K5 检索机制

### 5.1 基线检索（confirmed）

- **全文 + 标签/分类过滤**：沿用 A9 的 `ILIKE` 关键词匹配 title/symptom/root_cause（故障）、title/what_happened/what_we_learned（复盘）；category 精确过滤；排序 `confidence_score DESC, occurrence_count DESC`（故障）或 `created_at DESC`（复盘）。
- **规则加权相似度**：参照 A15，对结构化字段（regime、品种、波动档、信号类型）做权重打分与阈值过滤；仅在已验证（validated/closed）样本内匹配。
- **决策前教训聚合**：`get_lessons_for_decision(symbol, side, signal_type)` 聚合故障与复盘 Top-N，作为决策上下文输入；教训只作参考，不进入风控放行/拒绝判断（观测与决策面分离）。

### 5.2 向量语义检索（**inferred / unknown**，前置条件未满足）

- 现状：`core/` 与 `backend_api_python/` 无 embedding、向量库、相似度索引实现证据（A18，0 命中）；**不得**在设计中假设向量检索已可用。
- 若二期引入，前置条件（草案，均待评审）：
  1. 确定 embedding 模型与版本；条目文本字段、更新流程与再嵌入策略；
  2. 存储侧：向量列/扩展（如 pgvector）或独立向量库；索引类型与距离度量；
  3. 离线回填：存量故障/复盘/实验/Playbook 批量嵌入；条目版本化，模型升级后重嵌；
  4. 检索融合：全文 + 标签过滤先收敛候选集，向量在候选集内重排；未验证条目降权；
  5. 因果与合规：嵌入文本不含未公开凭证、静默集数据；检索结果可溯源到条目 uid。
- 在上述条件落地前，接口契约中向量检索作为可选通道预留字段，基线路径只依赖 §5.1。

### 5.3 检索结果口径

- 每条结果返回：条目 uid、类型、标题/摘要、匹配依据（关键词命中字段 / 规则得分 / 向量相似度-二期）、标签、严重度、验证状态、关联引用。
- 检索失败倾向：库不可用时返回空列表并记日志（沿用 A9 现状），不阻断交易决策；失败本身计入监控。

---

## 6. K6 API 契约草案（设计层，不写实现代码）

### 6.1 约定

- 响应信封沿用后端现状：`{code: 1|0, msg, data}`；成功 `code=1`，业务错误 `code=0` 并带错误码；未登录 401、不存在 404、计费不足 402（A14）。
- 读接口只读已落库审计/知识数据；写接口幂等：以业务 uid（decision_uid / trade_uid / fault_uid / experiment_uid / playbook_uid）为冲突键，重复提交 `ON CONFLICT DO NOTHING/UPDATE`，不产生重复知识条目。
- 写库失败不抛给交易主流程（A3），但返回写入状态与失败归类；敏感凭证字段不出现在任何响应中。
- 路由前缀与鉴权复用既有 `strategy_blp` + `@login_required` 模式（A14）；具体路径、队列归属属后续评审，本文不注册路由。

### 6.2 读接口形状（草案）

| 接口 | 入参 | 响应 `data` 形状 | 复用落点 |
|---|---|---|---|
| `GET /knowledge/decisions` | strategy_id, symbol, decision(accept/reject), caller_entry, date_from, date_to, limit, cursor | `{items: [{decision_id, symbol, side, accepted, reject_reason, model_version, threshold_dataset, created_at, caller_entry}], total, cursor}` | A1、A3 |
| `GET /knowledge/decisions/{decision_id}` | — | 四段完整快照 `{root, signal, risk_check, execution, outcome, replay: {ok, recomputed_lots, stored_lots}?}` | A1、A10、A4 |
| `GET /knowledge/trades` | strategy_id, symbol, status(open/closed), date_from, date_to, limit | `{items: [{trade_uid, decision_id, symbol, side, entry/exit, net_pnl, r_multiple, exit_reason, status}]}` | A4 |
| `GET /knowledge/faults` | keyword, category, severity, verified, tag, limit | `{items: [{fault_uid, title, symptom, root_cause, solution, category, severity, tags, verified, occurrence_count, updated_at}]}` | A9、A17 |
| `GET /knowledge/experiments` | strategy_id, status, decision, experiment_type, limit | `{items: [{experiment_uid, name, hypothesis, experiment_type, decision, p_value, effect_size, status, created_at}]}` | A5 |
| `GET /knowledge/playbooks` | strategy_type, tag, validated, limit | `{items: [{playbook_uid, title, strategy_type, tags, trigger_conditions, validated, version}]}` | §4.3 |
| `GET /knowledge/stats` | — | `{fault_knowledge: {total, verified}, post_mortems: {total, closed}, experiments: {total, completed}, decisions: {total, last_7d}}` | A9、A17 视图 |
| `GET /knowledge/lessons` | symbol, side, signal_type | `{lessons: [{source: fault\|post_mortem, uid, summary, solution}]}` | A9 |

### 6.3 写接口形状（草案）

| 接口 | 请求体要点 | 响应 `data` | 说明 |
|---|---|---|---|
| `POST /knowledge/decisions` | root 标识 + S1 signal + S2 risk_check 全字段 | `{decision_uid, written: bool}` | 下单前调用；拒绝单 lots=0；幂等键 decision_uid |
| `POST /knowledge/decisions/{decision_id}/execution` | S3 fill_refs、成交价/量/滑点/费用/时刻 | `{trade_uid?, written: bool}` | 成交回报后回填；可分段追加部分成交 |
| `POST /knowledge/decisions/{decision_id}/outcome` | S4 出场/盈亏/R/归因 | `{written: bool}` | 平仓后回填；R 倍数用冻结 entry_dist |
| `POST /knowledge/faults` | title, symptom, root_cause, solution, prevention, category, severity, tags, context | `{fault_uid, written: bool}` | 可由 FaultCatcher 自动登记，人工补根因 |
| `POST /knowledge/experiments/start` | name, hypothesis, experiment_type, control, treatment, sample_size, duration_hours, strategy_id | `{experiment_uid}` | 冻结决策规则与基线；trials_count 由实验脚本原子递增 |
| `POST /knowledge/experiments/{uid}/end` | metrics, conclusion, decision, p_value, effect_size, reproducibility | `{written: bool}` | 规则未冻结的实验不允许记 promote |
| `POST /knowledge/post-mortems` | title, type, severity, what_happened, why_it_happened, what_we_learned, how_to_improve, how_to_harden, related refs | `{post_mortem_uid}` | 对齐 A17 五层次字段 |
| `POST /knowledge/playbooks` | §4.3 全字段 | `{playbook_uid, version}` | 来源必须挂至少一条 post_mortem/experiment/fault 引用 |

### 6.4 接入点与三入口复用关系

| 入口 | 决策/审计复用 | 风险闸复用 | 故障/教训复用 |
|---|---|---|---|
| E1 策略自动（worker） | worker 下单前写 S1/S2；成交/平仓回调回填 S3/S4；决策前调 lessons 检索 | 统一 pre-trade gate（闸门草案 §2.3），归属闸 + 账户风险快照；结论写入 risk_check.checks | 下单失败经 FaultCatcher 登记故障；亏损红灯经 ReviewMonitor 触发复盘 |
| E2 手动成交（place_order, source=manual） | 成交后写决策/执行段，`caller_entry=manual`；风险快照与意图入审计 | 同一 gate 纯函数组装快照后调用；归属闸无 strategy_id 时跳过，暴露闸强制 | 失败走同一故障登记；历史教训可在下单前展示（参考性） |
| E3 快捷/AI 成交（source=ai_radar/ai_analysis/indicator） | 同 E2，`caller_entry=quick_ai`；信号引用 AI 分析记忆条目（A15） | 同 E2；账户暴露闸必须生效 | 同 E2；相似形态检索复用规则加权匹配 |

- **复用原则**：三入口共用同一审计写入器、同一 gate 判断、同一故障/复盘落库；差异只在快照组装与 `caller_entry` 标记，不各写一套日志口径。
- **边界**：审计/知识接口不触发下单、不改仓位；写接口不接受风控阈值参数（阈值走受控配置与分布校准流程，变更需人工确认）。

---

## 7. K7 单测计划

### 7.1 纯函数可测点（core 层，无网络/DB）

- **四段快照构造**：接受单 lots>0、拒绝单 lots=0 不变量；`threshold_dataset` 非 CLEAN/KNOWN 拒绝；S1/S2 缺必需 sizing 键时报缺失键清单（对齐 A10 `_REQUIRED_KEYS`）。
- **因果守卫**：`feature_time > decision_time` 判违规；时间戳非单调判违规；训练集最大时间 ≥ 测试集最小时间判泄露（A11）。
- **回放重算**：接受单重算手数与快照一致；超容忍度抛 `ReplayMismatch`；拒绝单快照手数非 0 抛错；JSONL 损坏行号可定位（A10）。
- **归因口径纯函数**：R 倍数用冻结 entry_dist；净盈亏 = 毛盈亏 − 佣金 − 滑点；open 仓位不计入 closed 统计；分组归因按 regime/品种聚合（§2.2）。
- **生命周期状态机**：白名单内跳转成功并落事件；非法跳转抛错；终态不可转出；事件审计轨迹字段齐全（A12）。
- **规则相似度打分**：RSI/MACD/MA/波动档权重与 0.25 阈值；未验证样本不进入候选；相似分边界值（A15 口径）。
- **检索过滤**：category 精确过滤；未 verified 故障/未 closed 复盘默认不返回；关键词命中字段映射正确（A9）。**已固化**：`core/audit/knowledge_filter.py`（`category_matches` / `filter_by_category` / `is_validated` / `filter_validated` / `keyword_hits` / `filter_by_keyword`），单测 `tests/test_audit/test_knowledge_filter.py`；DB 检索器接线仍属待确认项，未在本轮接入后端。
- **可进化规则**：复盘三条触发判定（单笔大亏损/连续亏损/单日亏损占比）、故障关键词分类、健康度评分/告警/分级。**已固化**：`core/audit/evolution_rules.py`（`evaluate_review_triggers` / `classify_fault` / `score_health` / `detect_health_warnings` / `classify_health` / `ReviewThresholds`），单测 `tests/test_audit/test_evolution_rules.py`；编排类（ReviewMonitor/FaultCatcher/StrategyHealthMonitor）已委托上述纯函数（等价重构，单例名/方法签名/计数状态归属不变）；DB 取数与写库仍留在既有编排边界。

### 7.2 I/O 注入桩

- DB 连接、PG 游标、交易所/经纪商客户端、行情快照全部注入桩；不触网、不读静默集。
- 写库失败桩：返回 False/抛连接异常，断言主流程不被阻断、失败归类与上下文落日志（对齐 A3、硬规则 9）。
- 成交回报桩：部分成交、拒单、超时、费用缺失各分支；断链场景 `link_missing` 标注。
- 桩替代既有单例（retriever / logger / monitor），测试间状态隔离。

### 7.3 既有 core 骨架复用

| 既有件 | 复用方式 | 落点 |
|---|---|---|
| `Decision` / `write_decision` / `decision_to_dict` | 四段快照根结构与 JSONL 序列化直接复用 | A1、A2 |
| `replay_decision` / `read_decisions` / `ReplayMismatch` | 回放校验与五要素还原复用 | A10 |
| `ExperimentLogger` 起止与冻结字段 | 实验追踪写入口径复用；trials_count 递增规则对齐 AGENTS 规则 11 | A5 |
| `FaultCatcher` 分类与捕获装饰器 | 故障自动登记复用；装饰器保持 re-raise 语义 | A6 |
| `ReviewMonitor` / `StrategyHealthMonitor` | 复盘触发与健康诊断复用；阈值占位值在单测中显式注入，不依赖代码默认 | A7、A8 |
| `KnowledgeRetriever` | 基线检索与统计复用；向量通道预留接口 | A9 |
| `AuditLogger` 分类/结构 | 段间日志分类映射复用（S1→SIGNAL/FEATURE，S2→RISK，S3→EXECUTION） | A13 |
| `LookaheadDetector` | 入库前因果/泄露校验复用 | A11 |
| 既有测试 | `test_audit_record.py`、`test_audit_replay.py`、`test_strategy_lifecycle.py`、`test_audit_logger.py` 作为回归基线；新增断言不得放宽黄金集（A19） | A19 |

### 7.4 回归约束

- 既有 worker 风险拒绝、归属闸、对账口径的既有测试断言不放宽（硬规则 10）。
- 新增纯函数先落单测再接路由（对齐闸门草案 §2.4 接线顺序）；纯函数未固化前不改入口。
- 本轮不执行全量测试；实现阶段须跑 `pytest -q`，新增测试覆盖四段写入、回填、检索过滤、状态机分支。

---

## 8. K8 待人工确认章节（DDL 草案与实盘接线）

> 本章所有 DDL 均为**设计草案**：本轮不新建表、不写迁移、不改数据库；正式 DDL 经人工评审、确认集合分离与幂等约束后，按受控变更流程落地（`configs/`、库结构变更属 AGENTS 停止条件）。

### 8.1 既有表复用结论（优先于草案新表）

飞书草案设想三张新表 `decision_audit_log / incident_knowledge_base / experiment_tracking`；本轮核对发现既有表已覆盖大部分口径（A3、A4、A17）。**设计建议：优先扩展既有表，不另建平行表**：

| 草案设想 | 既有落点 | 差距（草案补充项） |
|---|---|---|
| decision_audit_log | `qd_ai_decisions`（决策）+ `qd_trade_journal`（成交/结果） | 四段分段字段、订单流关联键（§1.4）、replay 状态；`qd_ai_decisions` 的 CREATE DDL 未在仓库定位（unknown，需 DBA 核对线上库结构） |
| incident_knowledge_base | `qd_fault_knowledge` + `qd_post_mortems` | 可复现性要素列、Playbook 关联 |
| experiment_tracking | `qd_experiment_logs` | reproducibility 列；decision 枚举口径与视图 `rollout/iterate/abandon` 的差异需统一（A5 vs A17） |

### 8.2 DDL 草案（待人工确认，不执行）

**(a) 决策审计分段补充（候选列，挂既有决策/交易表）**

```sql
-- 草案：为既有决策表补充分段与链路引用（列名/类型待评审；不新增平行表）
-- signal_json       JSONB   -- S1 段：l1/l2/l3/factors/confidence
-- risk_check_json   JSONB   -- S2 段：risk_state/checks[]/limits_version
-- execution_json    JSONB   -- S3 段：intent_refs/fill_refs/slippage/fee
-- outcome_json      JSONB    -- S4 段：exit/盈亏/R/归因（与 qd_trade_journal 字段对齐，避免双写不一致）
-- caller_entry      VARCHAR(20)  -- strategy_auto / manual / quick_ai
-- idempotency_key   VARCHAR(180) -- 关联 strategy_order_intents
-- replay_status     VARCHAR(20)  -- ok / mismatch / pending
-- 约束：S3/S4 列只允许追加更新；S1/S2 列冻结后不可更新（应用层守卫，DB 层触发器属二期评审）
```

**(b) Playbook 表（候选新表，待人工确认）**

```sql
-- 草案：playbook_knowledge（字段对齐 §4.3）
-- id BIGSERIAL PK, playbook_uid VARCHAR(64) UNIQUE NOT NULL,
-- title VARCHAR(255) NOT NULL, strategy_type VARCHAR(64),
-- tags_json JSONB DEFAULT '[]', trigger_conditions JSONB DEFAULT '{}',
-- preconditions JSONB DEFAULT '[]', steps_json JSONB DEFAULT '[]',
-- risk_controls JSONB DEFAULT '[]', source_refs_json JSONB DEFAULT '[]',
-- version INTEGER DEFAULT 1, status VARCHAR(16) DEFAULT 'draft',
-- owner VARCHAR(64), reproducibility_json JSONB DEFAULT '{}',
-- validated_at TIMESTAMP, created_at/updated_at TIMESTAMP DEFAULT NOW()
-- 索引：strategy_type、tags_json(GIN)、status、validated_at
```

**(c) 故障/实验表补充列（候选）**：`reproducibility_json JSONB`（数据快照引用、commit、配置哈希、制品版本）；故障表 `last_seen_at` 已在 A17 DDL 中。

### 8.3 实盘接线边界（只读路径，本轮不改）

- 只读勘察范围：`backend_api_python/app/services/live_trading/`、`quick_trade/`、`pending_orders/`、`native_protection`、`strategy_runtime/`、`strategy_v2/deployment.py`、凭证写库；接线实现须在后续切片按闸门草案 §2.4 / 对账草案 §6 的顺序评审后进行。
- 审计写入器接入三入口的位置：E1 worker 决策/成交回调；E2/E3 路由成交回报后；接入前须确认既有账本（`qd_quick_trades` / `qd_strategy_trades` / `qd_strategies_trading`）合并口径（闸门草案 G8、对账草案 §3.1）。
- 不做：自动补单/平仓/改仓；不把审计检索结果接入放行判断；不在知识管道内反推风控阈值。

### 8.4 未验证项清单（显式标注）

| # | 项 | 状态 | 说明 |
|---|---|---|---|
| U1 | `qd_ai_decisions` 线上表结构与既有列 | **unknown** | 仓库 SQL 未定位 CREATE TABLE；db_writer 写入字段与线上是否一致未核对 |
| U2 | decision_uid ↔ idempotency_key/client_order_id 透传 | **unknown** | 现有代码是否已把决策幂等键带入 intent payload 未核对（§1.4） |
| U3 | 向量语义检索可行性 | **未验证 / unknown** | 仓库无实现证据；embedding 模型、向量存储、回填与版本方案均未评审（§5.2） |
| U4 | 拥挤检测指标可得性 | **unknown** | 换手/信号重合度/同类相关性数据在现有账本中是否可计算未核对 |
| U5 | 三入口账本合并口径 | **inferred** | 快捷流水是否并入策略暴露/审计样本，沿用闸门草案 G8 待评审 |
| U6 | 后端既有故障/复盘/实验表数据质量 | **未验证** | verified/closed 比例、字段完整度、脏数据情况未抽样核对 |
| U7 | 全量测试 | **未执行** | 本轮未跑 `pytest -q`；仅静态阅读 core/audit 骨架与既有测试文件名 |
| U8 | 实盘/模拟冒烟 | **未验证** | 未连接任何交易所；四段回填在真实部分成交、费用口径下的正确性未跑过 |
| U9 | 决策审计段与 `qd_strategy_logs`、`qd_analysis_memory` 的去重边界 | **unknown** | 三类记录并存时的归属与展示口径需前后端联合评审 |
| U10 | 知识管道后端 API 真实 DB 读写与 HTTP 冒烟 | **未验证** | 服务层/路由已落地并经容器内 smoke 断言；pytest 未在容器内运行（镜像无 pytest），未走登录态真实 HTTP 请求与真实表读写抽样（§8.7） |

### 8.5 剩余风险

1. **口径双写风险**：S4 outcome 与 `qd_trade_journal` 字段重叠，若两处各自更新可能产生不一致；设计上以 journal 为成交/盈亏事实源，四段 JSON 为决策上下文快照，具体谁主谁辅待评审（§8.2a）。
2. **阈值未校准**：监控/复盘/上线现有切点均为占位默认（A7、A8、A12、对账草案 D8）；直接投入生产可能误报/漏报，须经 CLEAN 分布校准后转正。
3. **基线污染风险**：复盘归因若用近期表现刷新基线或挑基准，会造成 edge 误判；须基线冻结与版本留痕（§2.3、§3.3）。
4. **知识陈旧风险**：未验证 Playbook/故障条目若被同等检索，可能误导决策；二期需 validated 状态与降权/归档机制（§4.4、§5.1）。
5. **进程内易失**：既有检索/监控单例为内存结构（参照对账草案 D12）；审计留痕不能仅依赖进程内单例，持久化方案待评审。

### 8.6 后续评审清单（不属本轮实现）

- [ ] 四段字段在既有表上的落位与主从关系；`qd_ai_decisions` 线上结构核对（U1）。
- [ ] 决策-订单流关联键透传设计（U2）。
- [ ] 归因/因子评估的样本门槛与检验方法，经 CLEAN 校准后冻结（§2.3、§2.4）。
- [ ] 拥挤检测指标与数据可得性（U4）；八阶段状态机是否需要独立 crowding 态（§3.1）。
- [ ] Playbook 表 DDL 与故障/实验表 reproducibility 列评审（§8.2）。
- [ ] 向量检索二期前置条件评估（U3）。
- [ ] 三入口审计接线顺序与账本合并口径（U5、闸门草案 §2.4）。

### 8.7 后端接线落地状态（切片 #176，2026-11-08）

> 范围：仅知识/审计表的后端服务层、路由与 OpenAPI 装配；**不含**实盘决策四段写入、下单、仓位与风控阈值参数（§8.3 边界）。

**已落地（本地仓库，未提交）**

| 层 | 落点 | 覆盖接口 |
|---|---|---|
| 服务层 | `backend_api_python/app/services/knowledge_service.py`（`KnowledgeService` 单例） | 读：`list_faults / list_experiments / list_playbooks / get_stats / get_lessons`；写：`register_fault / start_experiment / end_experiment / register_post_mortem / upsert_playbook` |
| 路由 | `backend_api_python/app/routes/knowledge.py`（`knowledge_blp`，`@login_required`） | `GET /api/knowledge/faults · experiments · playbooks · stats · lessons`；`POST /api/knowledge/faults · experiments/start · experiments/<uid>/end · post-mortems · playbooks` |
| 装配 | `app/openapi/register.py`（注册 `/api/knowledge` 前缀 + tag 映射）；`app/openapi/tags.py`（`Knowledge` tag） | — |
| 单测 | `backend_api_python/tests/test_knowledge_pipeline.py` | 服务层 fail-open / 校验守卫 / 枚举归一 / 归一辅助；路由层包络与 400 校验 |

**接线口径（confirmed 代码现状）**

- 后端容器不携带 `core` 包（`ModuleNotFoundError: No module named 'core'`），服务层通过后端连接池 `get_db_connection()`（`DATABASE_URL` → RealDictCursor）直连知识表，**不 import `core.audit`**；过滤/归一口径在后端侧做最小等价实现：故障默认 `verified=true` 检索、复盘默认 `status='closed'` 检索。若后续把 `core` 挂载进后端镜像，检索谓词需与 `core/audit/knowledge_retriever.py` 对齐。
- 写接口以业务 uid 幂等：故障/实验/复盘 `ON CONFLICT (uid) DO NOTHING`；Playbook `ON CONFLICT (uid) DO UPDATE` 并递增 `version`。
- 实验收口守卫：`end_experiment` 先回读既有行 `decision_rule_frozen`；`promote_to_production` 仅允许规则已冻结的实验，未冻结拒绝 `rule_not_frozen`，uid 不存在拒绝 `experiment_not_found`（对齐 A5 / AGENTS 规则 11：决策规则须在实验前冻结）。Playbook upsert 后回读库内真实 `version` 返回，响应不恒为 1。
- fail-open：读失败返空集合；写失败返 `written=False` + 失败归类；异常记日志，不抛入交易路径。
- `qd_playbooks` 无仓库迁移 DDL，服务层 `_ensure_playbook_table()` 以 `CREATE TABLE IF NOT EXISTS` 运行时兜底；是否另落受控迁移脚本待评审（§8.2b）。
- 枚举白名单固化于服务层：实验决策 `promote_to_production/pivot/abandon`；实验类型 `backtest/ab_test/parameter_tuning/new_strategy/feature_test/parameter_search`；故障分类 `data/code/config/network/market/exchange/system`；严重度 `P0–P3`；Playbook 状态 `draft/active/archived`。

**验证证据与未验证项**

- 容器 `qdpro-backend` 内 smoke 断言 **25 项 PASS**（导入/路由注册/校验守卫/枚举归一/fail-open/读包络/400 校验/冻结守卫/未命中拒绝/Playbook version 回读），末行硬标记 `ALL SMOKE CHECKS PASSED`。
- **pytest 未在容器内运行**：后端镜像未安装 pytest；宿主 Python312 缺 flask/psycopg2 等后端依赖。`test_knowledge_pipeline.py` 按 pytest 规范书写，仅经容器内 smoke 直跑等价断言，**不等同于 pytest 通过**；后端新增接口尚未跑真实 HTTP 冒烟与真实 DB 读写抽样（见 U10）。
- 决策四段写入接口（§6.3 `POST /knowledge/decisions` 及 `execution/outcome` 回填）属实盘决策链路，本轮**未接**；`get_stats` 暂不含 `decisions` 计数，待决策链路接线后补齐。

