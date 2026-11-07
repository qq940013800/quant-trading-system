# MLOps 实验管理设计（版本注册 / 规则冻结 / trials 计数 / AB 灰度 / 回滚 / 漂移监控）

> 状态：**待评审草稿**，不含生产代码。
> 范围：模型与策略版本注册、实验纪律（规则冻结、trials 只增不减、多重检验校正）、AB/灰度发布、版本回滚、漂移监控与告警调度（关联 #108）。
> 边界：当前仓库**无已落地的 ML 训练制品与模型注册中心**，本文档不把训练/注册/漂移监控写成现状；不修改风控阈值常量与实盘资金路径。

## 1. 目标

1. **版本注册与快照**：模型/策略版本登记参数、特征版本、代码 commit、数据区间、随机种子、基准指标、父版本与变更说明；快照可序列化、可还原。
2. **规则实验前冻结**：`decision_rule`（成功标准、最小样本、多重检验校正口径）在首个 trial 之前写入并冻结；实验后只评估，不改规则。
3. **trials 计数诚实**：trial 计数包含失败与中止，只增不减；挖掘偏差由 DSR/Bonferroni/FDR 等口径校正，不只报告最优一次。
4. **AB / 灰度发布**：对照组与实验组按事前冻结的样本量、周期、最小可检测效应（MDE）与护栏指标并行评估；扩量/继续观察/淘汰由事前规则产出。
5. **可回滚**：任一 live 版本可切回上一注册版本，参数、特征版本、（未来的）模型快照一并还原；回滚先在 paper 环境演练。
6. **漂移监控与告警调度**：性能漂移（Sharpe/胜率/回撤）与特征漂移（PSI、滚动命中率）周期性对账；基准取上线时冻结快照；告警接入现有 Prometheus/Alertmanager 链路。

## 2. 现状证据

### 2.1 confirmed（代码快照佐证）

| 项 | 证据文件 | 事实 |
|---|---|---|
| 策略注册表（内存） | `core/registry/strategy_registry.py` | `StrategyVersion`（strategy_id/version/parameters/status/parent_version/changelog/performance）；`StrategyStatus` 状态机 draft→backtest→paper→live→paused→retired；`freeze_parameters`；`update_status` 合法转换校验；`compare_versions` 参数/性能差异对比。存储为进程内 dict，未见持久化后端对接。 |
| AB 框架（离线/内存） | `core/experiment/ab_test.py` | `ABTestConfig`（对照/实验组名、MDE、alpha、power、最长/最短周期、风险厌恶）构造即冻结；`required_sample_size`；Welch t、均值差 CI、Cohen's d；`bonferroni_correction`、`fdr_correction`；结论 `launch/continue/abort`。收益序列存内存 list，未见线上流量或资金分流接线。 |
| 优化器 trials 计数 | `core/experiment/auto_optimizer.py` | `trials_count` 显式包含所有试验（含失败）；`max_trials`；候选版本命名 `trial_001…`。 |
| 实验日志（PG） | `core/audit/experiment_logger.py` | 表 `qd_experiment_logs`；开始时写 `decision_rule_frozen=true`、`trials_count=1`、`status=running`；结束写 metrics/result/p_value/effect_size/conclusion/decision；统计 total/completed。 |
| 实验账本（追加式） | `registry.yaml` | 头部声明 append-only：不改写历史条目、不下调 `trials_N`；`decision_rule.frozen_at/rule/multiple_testing`；trial 条目含 id/date/hypothesis/command/params/data_range/code_commit/seed/report/outcome（`pass/fail/aborted`）。 |
| 性能漂移监控 | `core/monitoring/drift_monitor.py` | `DriftMonitor`：Sharpe/胜率/回撤漂移、显著性判断、缓慢衰减 vs 突然失效分类、降级建议；`DriftAlert` 含类型/当前值/基准值/偏离度/级别/信息。阈值为构造函数默认参数。 |
| 特征漂移 | `core/models/drift.py` | PSI 计算（分桶按 reference 分布分位点，阈值来自分布）+ 滚动命中率口径。 |
| 现有告警 | `ops/prometheus/alerts.yml` | 现有规则：API 宕机、worker 缺失、5xx 错误率、p95 延迟、策略命令失败、PostgreSQL exporter 掉线；**未见**策略 Sharpe 衰减、PSI、命中率越限类告警规则。 |
| 后台任务 | `backend_api_python/app/tasks/`（`agent_jobs.py`、`fast_analysis.py`、`maintenance.py`）、`app/workers/trading.py` | maintenance 含心跳、运行时元数据清理、reflection、AI 校准、市场目录同步；未见周期性漂移对账任务。 |
| 模型权重制品 | 全仓扫描（排除 `.venv`） | 无 `.pkl/.joblib/.onnx/.pt/.pmml` 权重文件；`core/models/*.py` 未见 save/load/persist 调用。 |

### 2.2 inferred（路径推断，待核对）

- `core/models/ml_trend_strategy.py` 在内存持有模型对象并调用 `predict_proba`；模型实例的来源（现建/加载/工厂注入）与重启后重建路径未持久化，需核对工厂加载链路。
- `core/models/`（`baseline.py` 逻辑/岭回归、`gbm.py`、`cv.py`、`labels.py`、`meta_label.py`）为研究骨架；训练产物未落盘，注册中心当前无制品可挂。

### 2.3 unknown / 缺口

- **无模型注册中心与制品库**：无版本化模型制品、阶段流转（staging/production）与在线灰度标签。
- **在线 AB/灰度分流未接线**：现有 AB 框架基于收益序列离线评估，无按资金比例/交易对/时间片的在线切分。
- **漂移对账调度未建**：#108 周期对账/漂移告警需新增后台调度，当前未动；告警指标是否已被后端暴露为 Prometheus 度量，需核对。
- PBO/CPCV/DSR 三重验证算法落地状态见 TODO P2-4（框架已建，具体算法待实现）；本设计只预留挂载点。

## 3. 候选方案权衡

| 维度 | A. 账本 + 注册表增强（持久化快照，paper 并行评估） | B. 独立模型注册服务/制品库（版本化制品 + 阶段流转 + 灰度标签） | C. 全功能 MLOps 平台（实验追踪 UI、自动流水线、bandit 分配、自动退役闭环） |
|---|---|---|---|
| 版本可追溯/回滚 | 中高：快照落账本/DB，回滚切版本 | 高：制品 + 元数据双版本化 | 高 |
| 实验纪律（冻结/trials） | 直接复用 `registry.yaml` 与 `qd_experiment_logs` 口径 | 需在注册服务层重建校验 | 平台内置 |
| 在线灰度发布 | 弱：先支持 paper/并行收益记录 | 中：支持标签与流量切分 | 强 |
| 持久化与并发 | 复用现有 PG/文件账本 | 需新增制品存储与服务 | 需整套平台 |
| 落地成本 | 低 | 中高 | 高 |
| 与现有审计一致性 | 高：同一套决策审计链路 | 中：需打通审计写入 | 中：需对接 |
| 运维负担 | 低 | 中 | 高 |
| 适用前提 | 当前无训练制品阶段 | 出现真实训练产物后 | 规模化、多策略并行后 |

## 4. 选型建议（供评审，分阶段）

### 阶段 1：注册表快照补强 + 实验纪律收口

- 扩充版本快照字段：特征版本、代码 commit、数据区间（IS/OOS）、随机种子、报告路径、基准指标、父版本；制品路径先留占位（当前无产物）。
- 注册表持久化：复用 `qd_experiment_logs` 与 `registry.yaml` 追加账本口径；版本状态流转沿用现有状态机，不新造一套状态。
- **trials 原子递增**：trial 计数只能由实验脚本原子写入，含失败/中止，只增不减；`decision_rule` 在首个 trial 前冻结并记录 `frozen_at`；实验后回填规则视为违规。
- AB 框架先在 paper/离线收益序列上运行：事前冻结样本量、周期、MDE、alpha 与护栏指标；结论由事前规则产出；多重检验校正口径（DSR/Bonferroni/FDR）在规则中写明。
- **回滚路径**：回滚 = 注册表切回上一 live 版本并还原参数/特征版本快照；先在 paper 环境演练，不触实盘资金路径。

> **落地状态（2026-11-08）**：模型版本快照与状态机骨架已落地 `core/registry/model_registry.py`（特征血缘/标签口径/数据区间/种子/commit/超参/指标/父版本/制品占位，进入 STAGED 自动冻结、冻结后拒改指标）；训练编排 `core/models/pipeline.py` 产出可序列化 `TrainingResult` 并可转 CANDIDATE 版本。持久化账本、trials 原子递增脚本、AB 框架与回滚演练仍属后续；当前无权重制品。

### 阶段 2：漂移对账调度 + 告警（关联 #108）

- 新增周期性对账任务（调度载体待评审：现有 worker 或独立定时任务），调用 `DriftMonitor` 与 PSI/命中率；基准值取该版本上线时冻结的快照，不用当期滚动均值自我参照。
- 漂移指标导出为 Prometheus 度量；在 `ops/prometheus/alerts.yml` 增补 Sharpe 衰减、PSI 越限、命中率越限规则；分级建议（观察/减仓/暂停/退役）走现有风控与审计链路，**不改** `mt5/` 风控阈值常量。
- 对账结果与触发原因写入审计，可回溯到版本与基准快照。

### 阶段 3：制品注册与在线灰度（条件触发）

- 仅当出现真实训练产出的模型制品时，再评估方案 B：制品版本化、阶段流转、在线资金比例灰度；护栏指标与多重检验校正随灰度一并落地。
- 多臂老虎机式动态资金分配、自动退役闭环属方案 C，延后到多策略并行、监控数据充分后评估。

### 不建议

- 在无训练制品时先建模型注册服务或制品库。
- 实验后回填/修改 `decision_rule`；只统计成功 trial。
- 漂移告警阈值按 PnL 网格搜索产生（违反 AGENTS.md 不变量 3）。
- 跳过 paper 演练直接在线回滚或扩量。

## 5. 未验证假设

- 漂移基准（基准 Sharpe/胜率/回撤）取自哪段样本、样本长度是否足以代表基线；需在该版本 paper/上线期数据积累后标定。
- 在线 AB 切分维度：按资金比例、按交易对、还是按时间片；影响分流实现与护栏统计口径。
- 模型制品格式与运行时加载方式当前未定（无产物）；阶段 3 再拍板。
- 告警通知通道（现有 Alertmanager 路由/通知 webhook）可达性与值班处理流程未验证。
- 后端是否已暴露漂移相关 Prometheus 度量，需核对现有 instrumentation。

## 6. 上线前置条件与验收标准

### 前置条件

- 实验脚本原子写 trials，失败/中止均留痕；规则冻结校验在实验启动前执行。
- 版本快照全部字段可序列化；回滚演练在 paper 环境完成。
- 不触碰 `configs/`、`registry.yaml`（脚本按规则 11 自动登记除外）、`mt5/` 风控常量、实盘资金路径。

### 验收标准

1. **版本可还原**：任一注册版本可还原参数、特征版本、commit、数据区间、种子、基准指标与父版本。
2. **实验纪律**：账本 `trials_N` 只增不减；失败/中止 outcome 留痕；`decision_rule.frozen_at` 早于首个 trial；多重检验校正口径已登记。
3. **AB 记录完整**：对照/实验组样本量、周期、MDE、alpha、护栏指标齐全；结论由事前规则产出，无事后调标。
4. **回滚可演练**：paper 环境从当前版本切回父版本，参数与特征版本快照一致；审计记录回滚原因。
5. **漂移对账**：周期性任务运行并输出性能/特征漂移指标；告警规则在 Prometheus 可查；告警含版本、基准值、当前值与偏离度。
6. **决策可审计**：每笔决策可还原其策略/模型版本；退役/暂停动作留完整输入快照。

## 7. 对应 TODO / 阻塞编号

- **#108**：周期对账 / 漂移告警调度（阶段 2 直接对应；需新增后台调度，确认后再动）。
- P2-3：五层识别 ML 增强（训练产物与注册入口的上游需求）。
- P2-4：PBO / CPCV / DSR 三重验证落地（AB 与实验账本的校正口径挂载点）。
- P1-12：策略健康度摘要接真实 runtime_health（漂移监控数据来源之一）。
- P1-1：策略生命周期后端自动退役逻辑（漂移分级建议的落地出口）。
- P2-2：因子库扩展（特征版本快照随版本登记）。
- RULES.md 1.1（决策规则冻结）、1.2（三重验证）；AGENTS.md 规则 11（trials 原子递增、规则冻结、禁止手工改写账本）。

## 8. 风险与未验证

- 当前无模型制品，阶段 1 的"模型版本注册"实际以策略参数/特征版本快照为主；模型注册字段为预留。
- 漂移基准充分性、在线分流维度、告警通道可达性均未验证，需在数据与调度落地后复核。
- 现有 `DriftMonitor` 阈值为构造默认值，阶段 2 须改为 CLEAN/上线快照分布校准口径，保留默认值仅作占位。
- 本设计不含生产代码；任何落地改动须附单测，黄金集断言不得放宽（AGENTS.md 规则 10）。
