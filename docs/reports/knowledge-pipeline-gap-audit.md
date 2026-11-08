# 知识沉淀与复用管道 · 差距勘察矩阵（任务 #158）

- 审计日期：2026-11-08；审计方式：只读静态勘察（代码定位、grep 接线、SQL 表对照、测试清单核对）；未连库、未跑实盘/worker 冒烟。
- 对照基准：飞书草案《知识沉淀与复用管道架构》revision 4（只读锚点，未回写）；本地既有文档清单见 §8。
- 证据分级：**confirmed**（代码落点已逐行核实）/ **partial**（部分存在、部分缺失或未接线）/ **missing**（未发现实现）。
- 接线口径：「生产接线」指被 `backend_api_python` 运行时链路（路由/服务/worker/调度/启动入口）真实调用；仅被 `tests/` 或 `scripts/` 独立脚本引用，记为「未接线」。骨架存在 ≠ 生产生效。
- 边界：本轮只勘察与出报告，不改 `configs/`、`registry.yaml`、`mt5/`、`secrets/`、`runtime/`、`ledger/` 及实盘资金路径；未执行 git 写操作。

## 一、结论摘要

1. **决策审计**：后端生产已有分散的决策（`qd_ai_strategy_decisions`）、执行流（`qd_execution_events` / `qd_live_order_bindings` / order intents/fills）、成交结果（`qd_strategy_trades`）三类记录；但草案要求的「单条四段 JSON（signal / risk_check / execution / outcome）」审计表未落地，**risk_check 段无持久化快照**，core 层四段审计骨架（`core/audit/record.py` 等）未被后端运行时引用。
2. **复盘**：后端 AI 策略复盘报告链路（规则诊断 + 可选 AI 总结 + 历史归档）已接线并计费；亏损单**自动触发复盘**的 core 监控器未接入生产；单笔/组合归因纯函数与五维归因服务均未被成交链路喂数据；「盈利是运气还是策略有效」的聚合层 alpha 持续性判断仅有纯函数，未闭环。
3. **策略生命周期**：core 侧八阶段状态机、AB 框架、优化器、漂移监控均有离线纯实现与单测；后端侧健康评估纯函数 + 退役监控器已实现并有单测，但**无路由、无调度线程、无 Beat 任务**，未生产激活；「发现→验证→小资金→规模化→拥挤→衰减→退役→复盘」八阶段中，小资金/规模化跟踪、退役复盘绑定、经验自动回灌为缺口。
4. **知识库**：故障库、复盘库、实验库的 core 写入/检索骨架与 standalone SQL 存在，但后端无对应路由与迁移表；Wiki 为前端静态只读镜像；Playbook 为静态 Markdown；检索仅 ILIKE 关键词与标签 Jaccard/文本重合，**向量语义检索 missing**（代码与 requirements 均无嵌入/向量库依赖）。
5. **`qd_analysis_memory` 是预测校准记忆，不是决策审计、也不是故障库**（口径差异见 §7）。

## 二、决策审计矩阵

| 清单项 | 现状落点（文件:行号） | 分级 | 是否已生产接线 | 证据与备注 |
|---|---|---|---|---|
| 每笔交易完整记录（接受/拒绝均留痕） | core 快照：`core/audit/record.py:65-103`（`Decision` dataclass，含 feature_snapshot/model_version/risk_state/accepted/reject_reason/final_signed_lots/threshold_dataset/decision_rule_version/r_multiple_at_close）；JSONL 落盘 `record.py:112-125`；PG 写入 `core/audit/db_writer.py:103-141`（`qd_ai_decisions`）；成交日志 `db_writer.py:247-339`（`qd_trade_journal`） | partial | **否（core 路径未接线）**；后端另有独立成交记录链路（见下） | `core/execution/engine.py:458-487,510-539` 调用上述写入；grep 全仓 `from core` / `core.audit` 在 `backend_api_python/app` 下 **0 命中**，core 引擎仅被 `tests/` 与 `scripts/test_execution_audit.py`、`test_knowledge_reuse.py`、`test_trade_journal.py` 引用。`qd_ai_decisions`、`qd_trade_journal` 未出现在 `backend_api_python/migrations/init.sql`，仅见于 `scripts/knowledge_pipeline_init.sql`、`scripts/trade_journal_init.sql` |
| 决策记录（后端生产侧） | `app/services/ai_decision.py:133` INSERT `qd_ai_strategy_decisions`（output_json/input_hash/prompt_hash/model_id/prompt_version/latency_ms/status/error_code；表结构 `migrations/init.sql:1135-1158`） | confirmed | 是（AI 决策运行时写入） | 记录主体是 AI 策略裁决契约；不含风控检查快照与执行/出场回填字段 |
| 成交结果记录（后端生产侧） | `app/services/live_trading/records.py:514` INSERT `qd_strategy_trades`（表结构 `init.sql:419-453`，含盈亏/平仓原因等） | confirmed | 是 | 作为 outcome 段数据源；与决策行通过 strategy_id/trade 事件关联，未见统一回放视图 |
| 订单流全链路追踪 | 执行流事件 `app/services/execution_streams/repository.py:90` INSERT `qd_execution_events`；订单绑定 `repository.py:39-47` `qd_live_order_bindings`（credential/exchange/owner/order_intent_id/client_order_id/exchange_order_id/observed_filled/status）；意图与成交 `strategy_runtime/order_intents.py`、`strategy_runtime/executors.py`；pending orders 链路 `app/services/pending_orders/fill_records.py` | confirmed | 是（执行流服务在线） | 链路覆盖 intent→binding→fill；与决策审计行的闭环上溯在后端无统一查询/回放入口；core 侧回放 `core/audit/replay.py:46-89` 仅服务 core 引擎内存线 |
| 决策日志四段：signal 段 | `core/logging/audit_logger.py:41-50`（LogCategory SIGNAL）；`log_decision` `:205-224`（layer/inputs/outputs）；后端决策表 `ai_decision.py:133` 存 output_json | partial | core 日志器未接线（`backend_api_python/app` grep `AuditLogger/audit_logger` 0 命中）；后端 signal 记录 confirmed | 后端无「因子值快照」结构化字段回显；前端决策日志仅 `timestamp/level/message` 文本（`frontend-pro/js/app.js:1189-1195`） |
| 决策日志四段：risk_check 段 | core：`record.py:85` risk_state 快照、`record.py:88` reject_reason；后端：`app/services/trading_executor.py:1130-1146,1446,1526` risk_state 仅内存传递 | missing | 否 | 未发现独立 risk_check JSONB 快照表或持久化字段；风控拦截/放行结论未作为可还原审计段落库。草案 `risk_check`（position_size/stop_loss/max_drawdown_allowed/risk_score）无对应落点 |
| 决策日志四段：execution 段 | 后端 `qd_execution_events` / `qd_live_order_bindings`（见上）；core `audit_logger.py:170-203` `log_trade` 写成交 JSONL | partial | 后端执行链路 confirmed 接线；core 日志器未接线 | 成交价/滑点/成交时延在后端执行事件内部分散记录，未与决策行合并为单条审计快照 |
| 决策日志四段：outcome 段 | 后端 `qd_strategy_trades`（records.py:514）；core `record.py:91` `r_multiple_at_close` 出场回填；`db_writer.py:247-339` 回填出场价/净盈亏/R 倍数 | partial | 后端成交记录 confirmed；core 回填路径未接线 | outcome 与 signal/risk_check 不同表存储，缺跨表按 decision_id/trade_id 串联的审计视图 |
| 决策日志（运行时文本流） | `app/routes/strategy_logs_routes.py:29-70` GET `/strategies/logs`，读 `qd_strategy_logs`（info/warning/error，级别归一 `:19-26`；表 `init.sql:756`）；前端日志中心三分类 decision/trade/system（`app.js:1131-1133`） | confirmed | 是（路由 + 前端页面） | 文本流归因素材可用；非结构化四段决策快照；tick 噪声在路由侧过滤（`:65-66`） |

## 三、复盘矩阵

| 清单项 | 现状落点（文件:行号） | 分级 | 是否已生产接线 | 证据与备注 |
|---|---|---|---|---|
| 亏损复盘自动触发（阈值监控） | core：`core/audit/review_monitor.py:37-155` `ReviewMonitor`，三阈值（单笔 -3R `:29`、连亏 5 笔 `:30`、日亏 5% `:31`）；触发写复盘记录 `:112-144`；单例 `:164-169`；调用点 `core/execution/engine.py:356-367` | partial | 否（core 引擎未接后端；后端无同功能调度） | 表 `qd_post_mortems` 仅 `scripts/knowledge_pipeline_init.sql:8-43` 定义，未进 `migrations/init.sql`；后端 routes/services grep `post_mortem` 0 命中 |
| 事后分析 / 策略复盘报告（规则 + AI） | `app/services/strategy_review.py:78-181` `StrategyReviewService.build_report`（成交/持仓/日志加载 `:106-109`，指标 `:111-118`，规则诊断 `:119-125`，可选 AI 总结 `:150-165`，历史归档 `:167-179`）；历史列表 `:183-199`；表 `qd_strategy_review_reports`（`init.sql:526`，建表/索引 `strategy_review.py:298-318`）；路由 `app/routes/strategy_review_routes.py:87-179`（POST 报告 / GET 历史 `:176`）；计费 `ai_review` `:18-59` | confirmed | 是（路由 + 服务 + 归档表 + 前端 AI 复盘页） | 前端 `index.html:1345` 自认缺口：复盘报告无亏损单根因分类字段，`exit_reason_counts` 仅全平仓原因计数，不作亏损归因；测试 `backend_api_python/tests/test_strategy_review_billing.py` 仅覆盖计费，未覆盖报告构建逻辑 |
| 决策对错归因（单笔） | core 归因纯函数：`core/audit/attribution.py:104` `split_trade_outcome`（market/alpha/cost 三分量，`:4-17`）；后端五维归因：`app/services/trade_journal.py:206` 收益分解、`:221` 成本归因、`:239` 尾部风险、`:265` 行为偏差 | partial | 否（两侧归因逻辑均未被生产成交链路调用） | core `attribution.py` 仅被 `tests/test_audit/test_attribution.py` 引用；后端 `TradeJournalService`（`trade_journal.py:109`）内存 journal，`log_trade` `:124` 无生产调用方，仅 `routes/p1_modules.py:74` 读取空/内存态；未发现把归因结果回写成交记录或复盘报告的链路 |
| 盈利是运气还是策略有效（聚合层 alpha 持续性） | core：`attribution.py:190` `aggregate_attribution`（聚合层判断 alpha 持续性；单笔残差不宣称技能，`:14-16`） | partial | 否 | 纯函数有单测（`tests/test_audit/test_attribution.py`）；后端无对应聚合归因服务被复盘/监控调用；无运气 vs 技能的统计口径落地（如 bootstrap 持续性检验的生产接线） |
| 哪些因子有预测力（因子有效性研究） | `app/services/strategy_v2/factor_research.py:11` `FactorResearchEngine`（分组回测/持有期/成本滑点 `:12-33`）；路由 `app/routes/backtest_center.py:223` POST `/factor-research`、`:286` 历史、`:302` 单条；持久化 `qd_factor_research_runs`（`init.sql:1225`）；测试 `backend_api_python/tests/test_factor_research.py` | confirmed（研究层） | 是（研究接口 + 历史库） | 研究结论未与交易复盘、策略上线闸门或决策因子快照闭环；core 侧因子注册表 `core/features/registry.py` 为特征目录，非预测力评估 |
| 模型改进（复盘→校准→改进闭环） | 校验回填：`app/services/reflection.py:27-48` `ReflectionService.run_verification_cycle`；置信度校准 `app/services/ai_calibration.py:57`（分桶准确率 `analysis_memory.py:778-820`，置信度调整 `:822-846`）；接线：启动线程 `startup.py:261-271`；Celery Beat `tasks/maintenance.py:36-50`、`celery_app.py:60-67`（reflection / ai-calibration 周期任务） | partial | 是（定时任务在线，默认开关 `ENABLE_REFLECTION_WORKER` / `ENABLE_OFFLINE_AI_CALIBRATION`） | 校准对象是 AI 快速分析的置信度，不是策略/模型版本的迭代改进；退役策略经验自动沉淀到知识库、改进项回流因子/策略库的链路未发现 |

## 四、策略生命周期矩阵

| 清单项 | 现状落点（文件:行号） | 分级 | 是否已生产接线 | 证据与备注 |
|---|---|---|---|---|
| 生命周期状态机（研究→上线→退役） | core：`core/experiment/strategy_lifecycle.py:26-37` `StrategyState`（DRAFT/BACKTESTING/AB_TESTING/PAPER_TRADING/LIVE_SMALL/LIVE_FULL/MONITORING/RETIRED/REJECTED）；合法转移 `:40-50`；事件审计轨迹 `:115-136`；上线标准 `LaunchCriteria` `:151-159`、`LaunchGate` `:161-211` | partial | 否（core 未接后端）；后端有另一套健康评估（见下） | 单测 `tests/test_experiment/test_strategy_lifecycle.py` 通过口径在册；后端 `app/services/strategy_lifecycle.py` 同名文件实为「致命错误自动停 + 健康评估」，与 core 状态机不是同一套 |
| 发现 / 验证阶段 | 因子研究 `factor_research.py:11`；core AB 框架 `core/experiment/ab_test.py:32-60`（冻结配置/MDE/alpha/power/样本量/统计检验/多重校正）；优化器 `core/experiment/auto_optimizer.py:33-58`（候选状态/trials 计数）；策略注册表内存态 `core/registry/strategy_registry.py`（见 `docs/design/design-mlops-experiment.md:22`） | partial | 否（core AB/优化器离线内存；因子研究接口在线） | AB/优化器仅被 `tests/test_experiment/` 引用；注册表为进程内 dict，未见持久化后端对接；实验跟踪表 `qd_experiment_logs` 未进后端迁移 |
| 小资金测试 / 规模化阶段 | 未发现小资金灰度仓位状态跟踪、容量测试、市场冲击记录模块 | missing | 否 | 草案「小资金测试」「规模化」两阶段在状态机与后端服务中均无独立记录字段/流程；`LIVE_SMALL` 仅为 core 枚举值 |
| 拥挤阶段监控 | `app/services/crowding_monitor.py:71` `CrowdingMonitorService`（拥挤度分级 LOW/MODERATE/HIGH/EXTREME `:33-38`）；路由 `app/routes/p2_modules.py:26,38,51` | partial | 是（P2 面板接口在线） | 拥挤信号来源与阈值口径需另核；未与生命周期状态转移或退役建议自动联动 |
| 衰减 / 模型监控与衰减检测 | core 漂移监控 `core/monitoring/drift_monitor.py:37` `DriftMonitor`（Sharpe/胜率/回撤漂移、显著性、缓衰/突失效分类、降级建议；测试 `tests/test_monitoring/test_drift_monitor.py`）；后端健康评估 `app/services/strategy_lifecycle.py:173-279`（HealthStatus/StrategyPerformance/HealthDecision/`evaluate_strategy_health`，阈值 `:209-216`：回撤 10%/20%、连亏 5/10、Sharpe 衰减 40%、最小样本 20）；退役监控器 `app/services/strategy_health_monitor.py:54-231`（绩效快照 `:54`、取在跑策略 `:118`、取成交 `:136`、退役执行 `:149`、评估调用 `:231`）。另有第二套 `app/services/strategy_health.py:44` `StrategyHealthMonitor` + 路由 `app/routes/p1_modules.py:514-543` `/strategy-health/summary` | partial | **DB 版监控器未激活**：无路由调用、`startup._start_scheduler_services`（`startup.py:240-271`）未启动其线程、`celery_app.py:59-80` Beat 无对应任务、`app/commands/` 无调用；core 漂移监控未接后端。`strategy_health.py` 路由传入 3 条硬编码演示策略（`p1_modules.py:519-541`），属 P1 演示面板，非生产监控 | DB 版监控器有单测 `backend_api_python/tests/test_strategy_health_monitor.py`（退役动作被 mock）；基线绩效无持久化来源，Sharpe 衰减维度在 baseline=None 时跳过（文件头注释 `strategy_health_monitor.py:20`）；两套后端健康实现并存、口径不一致 |
| 退役机制 | 故障类自动停：`app/services/strategy_lifecycle.py` `is_fatal_exchange_error` / `maybe_auto_stop_on_exchange_error` / `auto_stop_live_strategy`；调用点 `app/services/grid/engine.py:108,1754`、`app/services/pending_order_worker.py:118`、`app/services/pending_order_position_sync.py:37`；测试 `backend_api_python/tests/test_strategy_lifecycle.py` | confirmed | 是（worker/引擎链路在线） | 这是致命凭证/连接错误的被动止损，不等同绩效衰减触发的主动退役；主动退役走 `strategy_health_monitor.py:149`，但该监控器未激活（见上） |
| 退役复盘 / 经验沉淀 | 未发现退役事件自动生成复盘报告、经验条目回写知识库的链路；复盘服务 `strategy_review.py` 不感知策略退役事件 | missing | 否 | 草案「退役 → 复盘 → 经验入库」闭环缺后两段；core `qd_post_mortems` 有 `strategy_retirement` 类型枚举（`knowledge_pipeline_init.sql:11`）但无写入方接线 |
| 交易员经验沉淀 | 静态文档层：`docs/SUCCESS_PLAYBOOK.md`（已验证胜法索引）、`docs/ANTI_FRAGILE.md`（必死清单）、`docs/RULES.md`；技能参考库 `skills/quant-trading-expert/`；后端 `app/services/ai_skill_registry.py`（工具/技能调用注册，非交易经验沉淀） | partial | 文档层 confirmed；运行时经验入库 missing | 无结构化「交易员经验」条目模型与检索入口；经验固化依赖人工编辑 Markdown |

### 八阶段覆盖度对照（草案：发现→验证→小资金→规模化→拥挤→衰减→退役→复盘）

| 阶段 | 现状 | 分级 |
|---|---|---|
| 发现 | 因子研究接口在线；core 候选生成在优化器内离线 | partial |
| 验证 | AB 框架/过拟合检测/优化器离线纯实现，有单测；未接线上流量分流 | partial |
| 小资金测试 | 无灰度仓位状态跟踪与记录 | missing |
| 规模化 | 无容量测试/市场冲击/加仓过程记录 | missing |
| 拥挤 | 拥挤度监控服务 + P2 接口 | partial |
| 衰减 | core 漂移监控离线；后端健康评估纯函数 + 监控器未激活 | partial |
| 退役 | 故障被动止损在线；绩效主动退役未激活 | partial |
| 复盘 | AI 复盘报告链路在线；退役事件绑定复盘缺失 | partial |

## 五、知识库矩阵

| 清单项 | 现状落点（文件:行号） | 分级 | 是否已生产接线 | 证据与备注 |
|---|---|---|---|---|
| 故障知识库（结构化条目） | core 写入：`core/audit/fault_catcher.py:53-100` `FaultCatcher.capture`（自动分类 `:102-121`）→ `core/audit/db_writer.py:201-241` `write_fault_knowledge_to_db`；装饰器 `fault_catcher.py:141-163`；表结构 `scripts/knowledge_pipeline_init.sql:88-122`（symptom/root_cause/solution/prevention/tags_json/verified/confidence_score/occurrence_count） | partial | 否 | 表未进 `migrations/init.sql`；后端 services/routes grep `fault_knowledge/qd_fault` 0 命中；无 pytest（仅 `scripts/test_knowledge_reuse.py`、`test_knowledge_system.py` 独立脚本，不在 `pytest.ini` testpaths=tests 收集范围）。后端有下单错误分类 `app/services/pending_orders/error_classification.py`，用于失败处理，不沉淀知识条目 |
| 内部 Wiki | 前端静态只读镜像：`frontend-pro/index.html:2041-2352`（宪法/框架/铁律/口径/经验/对标/踩坑表，标注镜像 `docs/RULES.md`、`docs/WIKI.md`）；`app.js` grep `wiki` 0 命中，无 API 请求 | partial | 是（静态页可达）；无后端知识管理 | 无条目列表/检索框/详情；踩坑表为手工节选，非草案 incident 条目结构；详见前端切片报告 `docs/reports/knowledge-pipeline-frontend-audit.md:25-26` |
| 知识管理系统 / Playbook | 静态 Markdown：`docs/SUCCESS_PLAYBOOK.md`、`docs/ANTI_FRAGILE.md`、`docs/RULES.md`、`docs/knowledge/01-09 + README`、`docs/trading/KNOWLEDGE_BASE.md` / `KNOWLEDGE_BASE_INDEX.md`；技能库 `skills/quant-trading-expert/` | partial | 文档层 confirmed；运行时系统 missing | 无 DB 条目模型、无版本/评审/生命周期状态；Playbook 不被决策或复盘链路自动引用 |
| 检索：全文/关键词 | core：`core/audit/knowledge_retriever.py:40-91` 故障 ILIKE 关键词 + category 过滤 + confidence/occurrence 排序；`:93-134` 复盘 ILIKE；后端分析记忆 `analysis_memory.py:231-286` 按 market/symbol 取近期 | partial | 否（core 检索未接线；后端记忆检索随 fast_analysis 在线） | ILIKE 为子串匹配，无全文索引；`knowledge_retriever` 在 DB 不可达时返回 `[]`（`:55-56,106-107`），无降级词法方案 |
| 检索：标签 | core 纯函数 `core/audit/knowledge_match.py:40-50` 标签 Jaccard；归一 `core/audit/knowledge_normalize.py:229` `normalize_entry` / `normalize_tags`；SQL 预留 `tags_json` GIN 索引（`knowledge_pipeline_init.sql:117` 区） | partial | 否（纯函数 + 脚本表，无后端路由） | 无 pytest（grep `knowledge_match/normalize_entry` 在 `tests/` 0 命中）；后端无标签字段查询入口 |
| 检索：向量语义 | 全仓 grep `embedding/vector/pgvector/cosine/向量/语义检索/faiss/chroma`：后端代码 0 实现命中；`backend_api_python/requirements*.txt` 无嵌入/向量库依赖 | missing | 否 | 草案 `search_similar_incidents` 的语义匹配层未落地；`analysis_memory.py:506-577` 为指标加权启发式相似度（RSI/MACD/MA/波动率档位），非向量 |
| 知识复用（决策前引用历史教训） | core：`knowledge_retriever.py:136-167` `get_lessons_for_decision`；调用点 `core/execution/engine.py:557-559` | missing | 否 | 未接入后端决策/执行链路；决策前自动检索历史故障与复盘的闭环在生产路径不存在 |
| 实验跟踪（实验台账） | core：`core/audit/experiment_logger.py:54-118` `start_experiment`（假设/对照/实验组/样本量/冻结规则/trials）、`:120-181` `end_experiment`（metrics/result/p_value/effect_size/conclusion/decision）、`:183-208` 统计；表 `scripts/knowledge_pipeline_init.sql:46-83` | partial | 否 | `qd_experiment_logs` 未进 `migrations/init.sql`；后端 grep 0 命中；无 pytest；现有实验纪律（规则冻结/trials 只增不减）落在 registry/脚本层（AGENTS.md 硬规则 11），与该表无接线 |

## 六、core 骨架测试覆盖与接线状态对照

| core 模块 | 单测落点 | 有 pytest | 生产接线 | 备注 |
|---|---|---|---|---|
| `audit/record.py` | `tests/test_audit_record.py` | 是 | 否（core 引擎线内；后端未引用） | Decision 快照构造/序列化/JSONL 落盘 |
| `audit/replay.py` | `tests/test_audit_replay.py` | 是 | 否 | 回放重算手数并比对五要素 |
| `audit/attribution.py` | `tests/test_audit/test_attribution.py` | 是 | 否 | 单笔/组合归因纯函数 |
| `audit/lookahead_detector.py` | `tests/test_audit/test_lookahead_detector.py` | 是 | 部分：`core/integration/verification_middleware.py:30` 引用 `quick_lookahead_check` | 前视守卫；未接后端运行时 |
| `logging/audit_logger.py` | `tests/test_logging/test_audit_logger.py` | 是 | 否 | 结构化 JSON 日志器 |
| `experiment/ab_test.py` | `tests/test_experiment/test_ab_test.py` | 是 | 否 | AB 统计框架，内存收益序列 |
| `experiment/auto_optimizer.py` | `tests/test_experiment/test_auto_optimizer.py` | 是 | 否 | 候选生成/评估/选择闭环 |
| `experiment/strategy_lifecycle.py` | `tests/test_experiment/test_strategy_lifecycle.py` | 是 | 否 | 状态机 + 上线闸门 |
| `monitoring/drift_monitor.py` | `tests/test_monitoring/test_drift_monitor.py` | 是 | 否 | 漂移检测 |
| `audit/review_monitor.py` | 触发判定已委托 `evolution_rules.py`（test_evolution_rules 覆盖）；编排写库无单测 | 否 | 否 | 亏损复盘触发 |
| `audit/experiment_logger.py` | 无 | 否 | 否 | 实验台账写库 |
| `audit/strategy_health_monitor.py` | 评分/分级已委托 `evolution_rules.py`（test_evolution_rules 覆盖）；DB 取数无单测 | 否 | 否 | core 健康度评分（与后端同名服务不同实现） |
| `audit/knowledge_retriever.py` | 无 | 否 | 否 | 故障/复盘关键词检索 |
| `audit/fault_catcher.py` | 分类已委托 `evolution_rules.py`（test_evolution_rules 覆盖）；编排写库无单测 | 否 | 否 | 故障捕获入库 |
| `audit/db_writer.py` | 无（`scripts/test_db_writer.py` 独立脚本） | 否 | 否 | PG 写入：决策/成交/复盘/故障 |
| `audit/knowledge_match.py` / `knowledge_normalize.py` | `tests/test_audit/test_knowledge_match.py`、`test_knowledge_normalize.py` | 是 | 否 | 标签/文本相似度纯函数 |
| `audit/knowledge_filter.py` | `tests/test_audit/test_knowledge_filter.py` | 是 | 否 | 分类精确匹配 / verified·closed 状态过滤 / 关键词命中字段映射纯函数 |
| `audit/evolution_rules.py` | `tests/test_audit/test_evolution_rules.py` | 是 | 否 | 复盘触发判定 / 故障关键词分类 / 健康度评分·告警·分级纯函数；编排类已委托纯函数，DB 取数/写库留编排边界 |
| `execution/spot_ownership.py`（#166） | `tests/test_execution/test_spot_ownership.py` | 是 | 否 | 现货 L1 跟踪净额 / L2 钱包 free 两层口径解析与平仓封顶纯函数；钱包快照拉取、意图透传留适配器 |
| `execution/pretrade_gate.py`（#167） | `tests/test_execution/test_pretrade_gate.py` | 是 | 否 | 统一 pre-trade 风险闸纯判断（提议投影 + 限额 violation + 归属组合 fail-closed），另含全量投影直接判定 `evaluate_projected_limits` 供适配器 shadow 对照；快照组装/限额读取留适配器 |
| `registry/deployment_guard.py`（#168） | `tests/test_registry/test_deployment_guard.py` | 是 | 否 | 策略/模型版本上线前部署校验（环境状态合规、已冻结、未退役/暂停、制品校验和）；注册中心读取与版本引用落库留适配器 |
| `execution/reconcile.py` 成交腿聚合（#169） | `tests/test_execution/test_reconcile.py` | 是 | 否 | 成交腿流水按 symbol 聚合净持仓 PositionView，缺字段/缺侧/非法量进 dropped 留痕；账本行别名映射、周期对账任务与告警出口留适配器 |

后端服务测试对照：`test_strategy_review_billing.py`（仅计费）、`test_strategy_health_monitor.py`（健康评估 + mock 退役）、`test_strategy_lifecycle.py`（故障自动停）、`test_factor_research.py`（因子研究）；`trade_journal.py` 五维归因服务无单测。

## 七、`analysis_memory` 与决策审计 / 故障库的口径差异

| 维度 | `qd_analysis_memory`（`app/services/analysis_memory.py:52-79`） | 决策审计（草案 `decision_audit_log`） | 故障库（草案 `incident_knowledge_base`） |
|---|---|---|---|
| 主体 | AI 快速分析结论（market/symbol/decision/confidence） | 一笔交易/策略决策（signal/risk_check/execution/outcome 四段） | 一次故障事件（symptom/root_cause/solution/prevention/lessons） |
| 关键字段 | consensus_score / consensus_abs / agreement_ratio / quality_multiplier / actual_return_pct / was_correct / user_feedback（`:65-78`） | trade_id、因子快照、风控检查、执行成交、出场盈亏/R 倍数、决策规则版本、阈值来源集 | incident_id、severity、status、symptoms[]、root_cause、solution、prevention[]、tags、resolved_at |
| 用途 | 预测校准（置信度分桶准确率 `:778-820`、置信度调整 `:822-846`）、相似形态召回 `:506-577`、人工反馈记录 `:579-600` | 事后还原「为什么做这个决策」、归因、回放复核 | 新故障时检索历史相似经验并推荐解法 |
| 接线状态 | 生产在线：`app/routes/fast_analysis.py:117,211,249,285,320,376` 读写；校准 `app/services/ai_calibration.py:30,181,205`；定时校验 `reflection.py:37` | core 骨架未接线；后端仅有分散三表，无四段统一审计行 | core 骨架未接线；后端无表/路由 |
| 结论 | **是预测校准记忆，不是决策审计，也不是故障库**；三者不可互相替代 | 缺统一四段审计表与 risk_check 快照 | 缺结构化故障条目、检索复用与预防措施闭环 |

## 八、既有文档覆盖映射（避免重复造轮子）

| 既有文档 | 已覆盖内容 | 本轮定位 |
|---|---|---|
| `docs/knowledge-pipeline-architecture.md` | 四层模型、核心机制草案、机构对标 | 设计草案，非现状盘点；本轮不重复其推导 |
| `docs/knowledge-management-architecture.md` | 内部 Wiki / Playbook / 复盘 / 实验管理 / 复用机制路线 | 路线图口径；现状缺口以本报告 §2–§5 为准 |
| `docs/knowledge-migration-plan.md` | 跨端知识流动、SSOT 架构；§1 现状表自陈「决策审计日志表未建、运行时知识沉淀未实现」 | 与本轮勘察一致；飞书云文档/GitHub 备份仍为待做 |
| `docs/SUCCESS_PLAYBOOK.md` | 已验证胜法索引册（证据等级纪律） | Playbook 静态册；无运行时检索 |
| `docs/trading/KNOWLEDGE_BASE.md` / `KNOWLEDGE_BASE_INDEX.md` | 知识库总索引（原理/策略/ML/风控执行层） | 静态参考层 |
| `docs/knowledge/01-09 + README.md` | 全球机构/人物/策略/失败案例综合研究 + 系统映射表 | L2 研究层；`06_failures_and_lessons.md` 为静态失败案例，非运行时故障库 |
| `docs/design/live-trading-gates-and-reconciliation-design.md` | 三入口持仓口径、风控闸、对账接线、审计要求 | 执行流对账现状由该文档覆盖，本轮不重复 |
| `docs/design/reconciliation_drift_alarm_design.md` | 对账/漂移模块盘点（R/D/S 编号） | 漂移监控现状引用其结论 |
| `docs/design/design-mlops-experiment.md` | 版本注册/规则冻结/trials/AB 灰度/回滚/漂移监控设计；§2.1 已登记 core 注册表、AB、优化器、实验日志现状 | 与本轮 §3、§6 互证 |
| `docs/reports/knowledge-pipeline-frontend-audit.md`（#161） | 前端 Wiki/复盘/日志/归因面板只读口径审计 | 前端呈现层结论归该报告；本轮聚焦后端与 core 落点 |

## 九、未验证项

1. **数据库实际建表情况**：`qd_post_mortems` / `qd_fault_knowledge` / `qd_experiment_logs` / `qd_trade_journal` / `qd_ai_decisions` 是否在某环境已由 standalone SQL 手工创建，本轮未连库核对；`migrations/init.sql` 未包含上述五表。
2. **实盘成交链路落库完整性**：core 审计骨架是否被任何未列入 `backend_api_python/app` 的运行时入口（外部脚本/常驻进程）调用，本轮仅覆盖仓库内 `app/`、`ops/`、`scripts/`、`mcp_server/`、`dashboard/` 的 grep 结果；实盘/worker 冒烟未执行。
3. **后端健康监控器的外部触发**：`strategy_health_monitor.py` 是否由仓库外的 cron、进程管理器或编排脚本周期调用，本轮未核验外部调度配置。
4. **检索质量**：各 ILIKE / Jaccard 检索在真实数据量下的召回与排序质量，未做数据验证；空库/小库行为未实测。
5. **向量依赖排除**：requirements 三个文件（`requirements.txt` / `requirements-windows.txt` / `requirements-dev.txt`）grep 无向量/嵌入关键词；是否存在未锁文件的运行时依赖，未逐一核验 import 清单。
6. **复盘报告归因深度**：`StrategyReviewService` 的规则诊断维度与 AI 总结质量未跑真实策略样本验证；单测仅覆盖计费分支。
7. **基线绩效持久化**：健康评估所需上线基线绩效（`baseline_perf`）当前无持久化来源，Sharpe 衰减维度在缺基线时跳过；该缺口已由代码注释标注，基线存储方案未勘察。

## 附：本轮勘察动作记录

- 读取并核对：`core/audit/` 全部 13 个 py 文件、`core/experiment/` 3 个、`core/logging/audit_logger.py`、`core/monitoring/drift_monitor.py`、`core/execution/engine.py` 审计调用段（340-560）；后端 `analysis_memory.py`、`strategy_review.py`、`strategy_lifecycle.py`、`strategy_health_monitor.py`、`trade_journal.py`、`reflection.py`、`crowding_monitor.py`、`ai_decision.py`、`execution_streams/repository.py`、`strategy_review_routes.py`、`strategy_logs_routes.py`、`factor_research.py`；`migrations/init.sql` 相关表段；`scripts/knowledge_pipeline_init.sql`、`trade_journal_init.sql`；`startup.py`、`celery_app.py`、`tasks/maintenance.py`；前端 `index.html` / `js/app.js` 相关段。
- grep 接线关键词：`core.audit / core.experiment / core.logging / ReviewMonitor / FaultCatcher / KnowledgeRetriever / ExperimentLogger / write_decision / post_mortem / fault_knowledge / qd_experiment_logs / embedding / vector / audit_logger` 等，覆盖 `backend_api_python/app`、`ops/`、`scripts/`、`tests/`。
- 测试清单核对：`pytest.ini` testpaths=`tests`；core 各模块与后端服务单测归属见 §6。
