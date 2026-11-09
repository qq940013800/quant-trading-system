# 企业级 AI/ML 量化交易系统架构优化路线 ADR

> 状态：**待评审草稿**，本文件不含生产代码改动；只做现状复核、目标架构、缺口映射与分阶段路线。
> 关系：本文是 `docs/knowledge/08_system_blueprint.md`（蓝图 v2.0，2026-11-02）的**现状复核与路线更新**，不修改 v1 冻结的接口契约（`docs/trading/AI_ML_SYSTEM_DESIGN.md`）；各专题细节见 `docs/design/` 既有文档，本文只做索引与收口，不重复其方案。
> 日期：2026-11-10 ｜ 评审人：待人工确认 §9 决策项

---

## 1. 背景与范围

用户目标：基于第一性原理与全球顶级交易员/机构/量化程序最佳实践，优化程序架构、前端、后端、API 与各模块，形成企业级 AI/ML 增强、自动优化的智能量化交易系统；覆盖市场状态/趋势/结构/K 线形态识别、策略智能匹配与自动优化、入场/止盈/止损、资金与仓位管理，目标稳定盈利、截断亏损让利润奔跑。

**结论先行**：本系统已过骨架期，不是从零编写。当前最大风险不是"模块不够多"，而是控制面与实盘接线未闭环、部分绩效口径未统一、验证正确性待固化。**本轮不推倒重写**——既有守卫、纯函数底座、单测与审计链必须保留；优化在既有分层内收口。

### 1.1 第一性原理（不可拆解的约束）

长期期望：

```
期望收益 = Edge(统计边际) × 暴露(仓位/时长) × (胜率×均盈 − 败率×均亏) − 交易成本 − 尾部回撤
```

- **下行有界**：单笔亏损由止损 + 仓位硬约束；组合回撤由风控分级降档约束。这是"截断亏损"。
- **上行开放**：趋势跟踪、移动止损、分批止盈，盈利端不封顶。这是"让利润奔跑"。
- **边际为正且可审计**：阈值来自分布校准（非绩效网格搜索）；每笔接受/拒绝可还原各层输入。
- **过拟合免疫**：trials 含失败、PBO/DSR/CPCV、walk-forward 分段，杜绝样本内自我安慰。
- **成本可控**：滑点/佣金/点差计入边际准入闸门；成本×1.5 压力后期望仍需 > 0。

### 1.2 三条不可协商不变量（沿用 AGENTS.md，架构不得违背）

1. **因果单向**：任何计算只用 `available_at <= bar.close` 的数据。
2. **决策可审计**：每笔接受/拒绝都能还原各层输入与判断。
3. **阈值来自分布**：不由绩效网格搜索产生。

### 1.3 AI/ML 定位（沿用蓝图 v2 §6，钉死边界）

ML 只做三件事：**L2 状态权重、L3 meta-labeling 过滤、概率→仓位映射；ML 不生成方向**。LLM 只做研究/运维文本处理，输出落到文件/测试/PR 并人审，**禁止进入下单路径**。

---

## 2. 现状审计（2026-11-10 实测）

> 证据分级：**confirmed** = 目录/文件/签名/行数实测；**inferred** = 据 TODO 登记与既有专题文档判断；**unknown** = 运行时真实数据充分性/样本外表现未验证。

| 维度 | 实测 | 等级 |
|---|---|---|
| core 研究层 | 111 个 `.py`，735.1 KB；regime 5 / selector 4 / strategies 8 / risk 11 / models 10 / control 4 / explainability 2 / backtest 8 | confirmed |
| 后端 app | 413 个 `.py`，5.57 MB；routes 46 个、services 108 个 | confirmed |
| 前端 | 单页 SPA：`frontend-pro/index.html` + `js/app.js` + `css/main.css`；回测分析仪表盘已并入真实回测页（#274–#280） | confirmed |
| 测试 | `tests/` 15 个测试子目录、86 个 `test_*.py`；守卫/快照/纯函数单测覆盖至 #280 | confirmed |
| 实盘链路 | OKX 等适配器与 live_trading 服务存在；**下单/对账/持仓归集接线阻塞，待真实 Key 与人工拍板** | inferred |
| 绩效样本 | 历史回测记录多数字段 null/0；真实成交样本极少；样本外表现 **unknown** | inferred/unknown |

### 2.1 愿景项与既有落点对照

| 愿景项 | 既有落点（confirmed） | 状态 |
|---|---|---|
| AI 市场状态/趋势/结构/形态 | core `regime`/`selector`；后端 `market_regime`/`market_trend`/`market_structure`/`candlestick_patterns`/`price_action`/`comprehensive_market_analyzer`/`market_context` | 模块在；因果顺序与口径待收口 |
| AI 策略匹配 | 后端 `strategy_matcher`/`strategy_bot_recommend`；core `selector` | 部分接线；逐策略绩效快照缺真实源（P1-10） |
| AI 自动优化策略/参数 | 后端 `strategy_optimizer`/`parameter_optimizer`/`ai_calibration`/`ai_decision`；core `experiment` | 研究层；过拟合防御接入程度待核 |
| 入场/止盈/止损 | core `strategies`/`risk`；后端 `risk_engine`/`position_sizing`/`live_trading/account_risk`/`gate` | 研究链在；实盘 gate 三入口阻塞 |
| 资金/仓位管理 | core `risk`；后端 `position_sizing`/`live_trading/account_risk`/`spot_sizing` | 现货两层持仓口径阻塞（#153） |
| 执行/对账/复盘 | 后端 `live_trading/*`/`exchange_execution`/`trading_executor`/`trade_journal`/`reflection` | fills 归集与对账调度阻塞 |
| 过拟合防御 | core `experiment`；后端 `overfitting_defense`；PBO/DSR 已修 | CPCV 名实不符待修；落地口径待固化 |

---

## 3. 蓝图 v2 差距矩阵复核（G1–G13）

> 对照 `08_system_blueprint.md` §4。蓝图写于 11-02，其后 #181–#280 落地大量守卫与纯函数底座；下表更新每项当前状态。

| # | 蓝图差距 | 2026-11-10 复核 | 剩余缺口 | 优先级 |
|---|---|---|---|---|
| G1 | Kill switch 缺失 | **底座已落地**：`core/control/kill_switch.py`（262 行，`KillSwitchState`/`trigger`/`reset`/`guard`/文件原子写/审计） | 独立进程/IPC 触发源、实盘三入口挂接仍阻塞（#107/#154） | P0（接线） |
| G2 | 订单/持仓对账缺失 | **底座已落地**：`core/execution/reconcile.py`（336 行，`Tolerance`/`OrderView`/`PositionView`/`ReconcileReport`/`reconcile`/`enforce` + fills 归集） | 周期调度、fills→账本归集接线阻塞（#108/#155/#199） | P0（接线） |
| G3 | 无真实策略 | **已落地 4 类**：`TrendBreakoutStrategy`/`MeanReversionStrategy`/`StructureBreakStrategy`/`SupplyDemandStrategy` + 注册器（`core/strategies/`） | 端到端回测冒烟、样本外有效性、实盘适配待核 | P0（验证） |
| G4 | ML 阈值硬编码 0.55 | 部分落地：MetaLabeler `q_lo/q_hi` 分位守卫（#271）、regime 分位阈值守卫（#231） | 复核是否仍有硬编码 `0.55`/`0.45` 残留；阈值配置外置待 G10 | P0 |
| G5 | CPCV 名实不符 | 未闭环；过拟合参数守卫已补（#228） | 真组合净化 CV（C(N,k)，purge/embargo 生效、无泄漏） | P1 |
| G6 | 数据 manifest/血缘 | 缺；`core/data/` 除 `validator.py` 外代码被 gitignore | 哈希+行数+时间范围+缺口+集合标签（CLEAN/KNOWN/SILENT） | P1 |
| G7 | 无 TCA | 部分：后端 `trading_cost_analysis.py` 存在 | 实盘成交 vs 回测成本偏差日报、滑点/冲击/佣金分解与告警接线 | P1 |
| G8 | 组合优化弱 | 部分：风险预算+相关性熔断纯函数（#207）、高相关阈值参数化（#210） | 协方差风险平价/相关性上限、组合波动目标误差 < 20% | P1 |
| G9 | 策略退役不自动 | 部分：生命周期准则/监控阈值守卫（#220）、`strategy_lifecycle`/`strategy_health` 服务 | 连续 N 日红灯自动退役/降仓工单接线 | P1 |
| G10 | 配置外置缺失 | 未做；`configs/` 需人工确认（§9-1） | 全部阈值来自配置，无业务字面量 | P1（待确认） |
| G11 | 部署无灰度 | 部分：E1 shadow 对照适配器（#209）、AB 测试配置守卫（#225） | 影子→小资金→全量；一键回滚演练 < 5 分钟 | P2 |
| G12 | 多标的/多周期 | 单标的 M5 现状 | **决策待定**（§9-2） | — |
| G13 | 另类数据 | 部分：data_providers 含 news/sentiment/commodities/economic_calendar 等 | 因果可得性验证、先新闻舆情后另类 | P2 |

**复核结论**：G1/G2/G3 的"从零写"部分已完成，当前缺口是**生产接线与正确性验证**；G4/G7/G8/G9/G11/G13 为部分落地；G5/G6 仍缺；G10/G12 待人工决策。

---

## 4. 目标分层架构

沿用蓝图 v2 §3 五面 + 控制面 + 注册表唯一事实源；下表标注既有落点与待补接缝。

```
                 ┌────────────────────────── 控制面（独立进程） ──────────────────────────┐
                 │  Kill Switch  │ 限额/熔断 │ 配置中心 │ 部署/回滚 │ 双人复核/告警      │
                 └───────┬──────────────┬─────────────┬──────────────┬──────────────────┘
                         │              │             │              │
┌─────────────┐   ┌──────▼──────┐  ┌────▼─────┐  ┌────▼──────┐  ┌────▼────────────┐
│ 数据面       │→  │ 研究面       │  │ 决策面    │  │ 执行面     │  │ 可观测面          │
│ ingest      │   │ features     │  │ L1 位置   │→ │ 订单路由   │→ │ metrics/logs     │
│ validate    │   │ labels       │  │ L2 状态   │  │ 经纪商适配 │  │ traces/TCA       │
│ manifest    │   │ models       │  │ L3 触发   │  │ 状态机     │  │ drift/audit      │
│ 存储/血缘    │   │ CPCV/PBO/DSR │  │ meta/仓位 │  │ 对账       │  │ 看板/复盘         │
└─────────────┘   └──────────────┘  └───────────┘  └────────────┘  └──────────────────┘
                         │                │              │
                         └──── 策略注册表 / 模型注册表 / 实验账本（唯一事实源） ────┘
```

### 4.1 各面落点与接缝

| 面 | 既有落点（confirmed） | 待补接缝 |
|---|---|---|
| 数据面 | `core/data`、后端 `data_sources`/`data_providers`/`kline`/`market_data_collector` | manifest/血缘（G6）；PIT 一致性与集合分离校验固化 |
| 研究面 | core `features`/`models`/`experiment`/`backtest`；后端 `factor_library`/`factor_research` | CPCV 修正（G5）；特征/标签/模型版本卡；实验账本 trials 只增不减 |
| 决策面 | core `regime`/`selector`/`strategies`/`risk`；后端 `market_*`/`strategy_matcher`/`position_sizing` | 因果顺序 L1→L2→L3 口径对齐；ML 阈值分位化收口（G4） |
| 执行面 | core `execution`；后端 `live_trading/*`/`exchange_execution`/`trading_executor` | 对账周期调度（G2）；fills 归集；现货两层持仓口径（#153）；网关三入口挂接（#107） |
| 控制面 | core `control`（`kill_switch`/`approval_gate`/`dual_review`） | 独立进程触发；配置外置（G10）；灰度回滚（G11） |
| 可观测面 | core `monitoring`/`audit`；后端 `observability`/`trade_journal`/`reflection`/`portfolio_monitor` | TCA 日报（G7）；漂移优先于 PnL 告警；复盘闭环接线 |
| 注册表 | core `registry`；后端 `strategy_v2`/`registry` | 策略/模型版本引用落库；退役自动工单（G9） |

### 4.2 模块边界原则（架构约束）

- **研究与生产分离**：研究镜像与生产镜像共用特征代码；模型有版本卡与回滚点（蓝图 P2）。
- **风险单位化**：所有仓位以"每笔风险占权益比例"为唯一单位，可加总、可限额、可熔断（蓝图 P1）。
- **信号工厂而非圣杯**：多策略/多信号集成，单信号权重小；组合相关性与容量受约束（蓝图 P3）。
- **控制面独立于策略进程**：kill switch 不得依赖策略进程存活（蓝图 P6/P9）。

---

## 5. 缺口映射（对接 TODO 与专题设计）

> 既有专题设计文档已覆盖细节，本节只做映射索引；落地时以对应专题方案为准。

### 5.1 P1 后端/契约缺口

| 编号 | 缺口 | 关联专题 | 下一步 |
|---|---|---|---|
| P1-10 | 逐策略绩效快照接口无真实源 | `design-perf-snapshot-api.md` | 按专题草案落地 `GET /api/strategies/perf-snapshot`，缺失即 `--`，不编造指标 |
| P1-11 | 压力测试后端为内置演示情景 | 待补专题 | 接真实波动/相关性/冲击参数；前端已判 `data_kind==='real'`，非 real 空态 `--` |
| P1-12 | 策略健康度摘要硬编码 demo 三条 | 待补专题 | 接 `runtime_health`/`strategy_health` 真实来源 |
| P1-13 | 夏普/绩效两套口径并存（逐笔未年化 vs 日收益年化） | `design-perf-snapshot-api.md` R2 | 统一为日收益年化；统一前快照夏普只取回测口径 |

### 5.2 P2 口径与展示缺口

| 编号 | 缺口 | 关联专题 | 下一步 |
|---|---|---|---|
| P2-10 | 风险预算口径选型 | `design-risk-budget-basis.md` | 评审拍板口径后固化纯函数与接口 |
| P2-11 | 月度收益后端预聚合 | `design-monthly-heatmap-route.md` | 后端聚合替代前端日收益累加；口径与年化一致 |
| P2-12 | 现货持仓口径偏大（阻塞） | `live-trading-gates-and-reconciliation-design.md` | 触资金路径，须人工拍板；平仓前先核准钱包真实基础币余额 |
| P2-13 | 旧 validation 监控面板与引擎 P2 卡片去重 | 待补专题 | 保留唯一事实源，旧面板标记废弃 |

### 5.3 阻塞项（触碰实盘/资金路径，本轮不自动执行）

| 编号 | 阻塞项 | 现状 | 解除条件 |
|---|---|---|---|
| #107/#154 | 风控 gate 三入口挂接 | 纯函数/底座在，入口未挂 | 人工拍板实盘风控边界后接线 |
| #108/#155 | 对账周期调度 | 对账纯函数在，调度未起 | 人工确认对账容忍度与触发链 |
| #153 | 现货两层持仓口径 | `spot_ownership` 纯函数在 | 拍板钱包/持仓口径后接线 |
| #199/#155 | fills 归集 | `aggregate_fills_to_positions` 在 | 成交→持仓归集链路对账一致 |
| #198 | 合约版本 | 待核 | 明确合约/现货版本口径 |
| #102/#87/#91/#157 | 实盘链路 | 适配器在 | OKX 真实 Key + 影子运行 ≥ 4 周 |

### 5.4 技术债

- **前端无 JS 自动化单测**：仓库无 JS runner，`tests/` 全 Python；未引入 jest/vitest 新栈。落地前端契约前需先决定测试栈。
- **后端容器 pytest 未跑**：宿主缺 flask/ccxt/numpy/scipy，容器无 pytest；需在容器内补测试执行通道。
- **黄金集断言不放宽**：任何接线改动不得放宽既有单测断言。

---

## 6. 分阶段路线

### 6.1 P0 — 能安全地跑（不碰实盘下单/资金路径）

1. **研究链因果收口**：L1 位置 → L2 状态 → L3 触发顺序与口径对齐；复核 G4 硬编码阈值残留并分位化。
2. **绩效契约真实化**：落地 P1-10 快照接口、统一 P1-13 夏普口径；缺失值 `--`，真实 0 必须渲染。
3. **策略端到端冒烟**：4 个策略类注册进 registry，回测可跑、单测通过；记录样本量与指标边界。
4. **控制面/对账底座固化**：复核 G1/G2 纯函数与审计；接线留阻塞清单，不在本轮挂实盘入口。
5. 全量测试保持绿；文档与 README/策略目录同步。

**P0 验收**：研究链无未来函数；快照接口不编造指标；策略回测冒烟通过；既有单测不放宽；阻塞项明确标注未验证。

### 6.2 P1 — 能可信地跑

6. CPCV 修正 + 守门员集成（PBO/DSR/CPCV 三指标进验证中间件，G5）。
7. 数据 manifest/血缘（G6）。
8. TCA 日报与成本偏差告警（G7）。
9. 组合优化/相关性上限（G8）。
10. 策略自动退役工单（G9）。
11. 配置外置（G10，**需 §9-1 人工确认**）。
12. P1-11 压力测试真实参数化、P1-12 健康度接真实来源。

### 6.3 P2 — 能规模化

13. 灰度/回滚演练（影子→小资金→全量，G11）。
14. 多标的/多周期（G12，**需 §9-2 人工决策**）。
15. 另类数据接入与因果可得性验证（G13）。

---

## 7. 上线门禁（沿用蓝图 v2 §7，未改）

| 指标 | 通过线 | 说明 |
|---|---|---|
| PBO | < 0.5（警告 0.3） | 组合对称交叉验证，越低越好 |
| Deflated Sharpe | > 0（95% 置信更佳） | 已按 trials 修正 |
| CPCV 方向一致率 | ≥ 60% | G5 修好后启用 |
| 成本×1.5 后期望 | > 0 | 保守成本压力 |
| 样本外交易数 | ≥ 100 笔（或统计功效达标） | 大数定律 |
| 影子运行 | ≥ 4 周 | 实盘行情、模拟下单 |
| 回放校验 | 100% 一致 | Decision 五要素 |

---

## 8. 明确不做（边界，沿用蓝图 v2 §5/P10）

- **不做**：HFT、做市、期权做市、跨交易所套利——需要 colocation、L2/tick 全深度、期权链与费率结构，零售环境不可达，做了也是负期望。
- **暂缓**：横截面动量、因子投资、事件驱动、加密基差——需多标的/多资产数据，先扩数据面。
- **LLM 不进下单路径**；ML 不生成方向。
- **不推倒重写**：既有守卫、纯函数底座、单测、审计链保留；优化在既有分层内收口。

---

## 9. 待人工确认的决策（阻塞架构收口）

1. **是否创建 `configs/` 并外置全部阈值**（AGENTS.md 要求人工确认；G10）。
2. **是否扩第二标的/上移趋势周期**（影响容量、成本与策略族取舍；G12）。
3. **是否冻结"HFT/做市/期权做市不做"为长期边界**。
4. **前端测试栈选型**：是否引入 JS runner（jest/vitest），还是维持后端 Python 单测覆盖纯逻辑。
5. **实盘风控/对账/持仓口径**（§5.3 阻塞项）：解除前不挂接实盘下单与资金路径。

在上述决策前，系统按"XAUUSD M5 单标的 + 三策略族"推进（蓝图 v2 §12）。

---

## 10. 风险登记簿

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 策略实盘与回测偏离 | 高 | 高 | 影子运行 + TCA + 成本×1.5 压力 |
| 过拟合（多重检验） | 高 | 高 | PBO/DSR/CPCV + trials 账本 + 决策规则实验前冻结 |
| 执行故障（幽灵持仓） | 中 | 高 | 对账 + kill switch + 幂等 |
| 数据泄漏/前视 | 中 | 高 | 因果断言 + 集合分离 + 单测 |
| 模型衰减 | 高 | 中 | 漂移监控优先于 PnL 告警 + 自动退役 |
| 运维事故 | 中 | 高 | 灰度 + 回滚 + 告警 |
| 范围蔓延（多标的/高频） | 中 | 中 | §8 边界 + 人工决策 |
| 口径不一致误导决策 | 中 | 中 | 接口层固化口径；缺失 `--`、真实 0 渲染；P1-13 统一 |

---

## 11. 证据与来源

- 实测：core 111 `.py`/735.1KB；后端 app 413 `.py`/5.57MB（routes 46、services 108）；`tests/` 15 子目录、86 测试文件；策略/控制/执行层签名与行数（2026-11-10）。
- 既有蓝图：`docs/knowledge/08_system_blueprint.md` v2.0（G1–G13、门禁、路线、风险）。
- 专题设计：`docs/design/` 下 `design-perf-snapshot-api.md`、`design-monthly-heatmap-route.md`、`design-risk-budget-basis.md`、`design-oms-ems-algo.md`、`design-trailing-stop-service.md`、`live-trading-gates-and-reconciliation-design.md`、`reconciliation_drift_alarm_design.md`、`design-mlops-experiment.md`、`design-feature-store.md`、`design-dr-ha-backup.md`、`design-alt-data-onboarding.md`、`degradation-failclosed-design.md`、`observability-metrics-alerting.md`、`frontend-enhancement-contracts.md`、`knowledge-pipeline-design.md`。
- 研究结论：`docs/knowledge/01`–`07`；行业实践：López de Prado *AFML*、Bailey et al. PBO/DSR（见 `09_sources.md`）。
- 未验证项：实盘冒烟、经纪商差异、样本外绩效、真实成交充分性——均标注 unknown，不在本 ADR 内下结论。

*版本：v1.0 ｜ 2026-11-10 ｜ 下次复审：P0 完成后*
