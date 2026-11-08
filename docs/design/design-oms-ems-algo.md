# 设计草稿：独立 OMS / EMS 与拆单算法层

> 状态：**待评审草稿**，不含任何生产代码。
> 边界：本文件只做方案与边界划分，不改交易/风控/下单/资金逻辑，不碰 `configs/`、`registry.yaml`、`mt5/`、`secrets/`、`runtime/`、`ledger/`。
> 不变量约束（`AGENTS.md`）：因果单向（只用 `available_at <= bar.close` 的数据）、决策可审计（每笔接受/拒绝可还原各层输入与判断）、阈值来自分布（不由绩效网格搜索产生）；硬规则 5（intra-bar：信号与退出决策只允许在已收盘 bar 调用）、硬规则 7（异步返回必须检查返回值并重试）、硬规则 8（禁止硬编码点值/手数/阈值，走 `SymbolInfo*` 与 config）。

## 1. 目标

在现有"策略信号 → 风控检查 → 直连下单"链路之上，补一层**可审计、可回放、可归因**的订单管理与执行算法能力：

1. **OMS（订单管理）**：把"一个意图订单（parent order）→ 若干子单（child orders）→ 成交流水"的完整生命周期状态化管理，支持部分成交、撤销、拒绝、超时、对账与幂等。
2. **EMS（执行管理）**：在风控放行后、交易所下单前，提供拆单与择时算法（TWAP / VWAP / 参与率），降低单笔大单的市场冲击与可见度；执行算法只负责"怎么发、发多少、何时发"，不产生新的交易方向。
3. **TCA 成交质量归因**：对每笔/每组订单，按滑点、点差、延迟、成交偏离（vs 决策价/到达价/基准价）拆解成本，并与现有成本模型对账；归因只读，不回灌信号或修改下单决策。
4. **衔接边界清晰**：新层作为现有直连执行器的可选前置/旁路，初期不替换任何已在跑的直连路径；所有算法参数与阈值由分布校准，不照搬机构数值。

### 1.1 非目标（本期明确不做）

- 不做高频/低延迟做市、不做跨所对冲与路由寻优（无此数据与基础设施）。
- 不重写现有交易所适配客户端（`live_trading/` 各所 adapter），不改动其下单/撤单/查询语义。
- 不在本层引入新的风险限额、不平仓、不加仓；风险判断仍由现有风控模块前置完成。
- 不编造任何绩效数字、滑点 bps 基线或机构执行指标；阈值与默认参数在落地阶段由 CLEAN 集分布校准。

## 2. 现状证据（文件:目录佐证，分级 confirmed / inferred / unknown）

### 2.1 执行层偏直连，无独立 OMS/EMS 与拆单（confirmed）

| 证据位置 | 现状描述 | 分级 |
|---|---|---|
| `backend_api_python/app/services/trading_executor.py`（1825 行） | `TradingExecutor` 为核心直连执行器；内部通过 `session.context.update_order_statuses({...})` 直接更新订单状态，状态散落在执行循环内，未见独立的 parent/child 订单聚合模型与拆单编排器。 | confirmed |
| `backend_api_python/app/services/strategy_runtime/executors.py`（1230 行） | 面向网格/DCA/马丁等策略模板的执行 payload 预览与归一化（`preview_executor`、`build_executor_strategy_payload`、`_preview_grid/_preview_dca/_preview_martingale` 等），属于策略建仓脚本编排，不是通用 OMS/EMS。 | confirmed |
| `backend_api_python/app/services/live_trading/executors.py`（208 行） | 三种直连执行器：`MarketOrderExecutor`、`RestingLimitExecutor`、`LimitThenMarketExecutor`；`OrderExecutionResult` 携带 `exchange_order_id / filled / avg_price / status`，直接调用 adapter 下单，无子单拆分与参与率控制。 | confirmed |
| `backend_api_python/app/services/execution_streams/`（`adapters.py` 29KB、`processor.py` 33KB、`repository.py`、`supervisor.py`、`events.py`、`normalizers.py`） | 各所成交/订单事件的接入、归一化、落库与监督；`ExecutionEvent` 含 `symbol / exchange_order_id / client_order_id / side / position_side / fees`。这是**成交事件回流**通道，可作为 OMS 成交回填与 TCA 取数来源，但本身不管理订单生命周期编排。 | confirmed |
| `core/execution/engine.py` | 研究/回测侧执行引擎：`OrderStatus` 已有 `PENDING / SUBMITTED / PARTIAL / FILLED / CANCELLED` 枚举，`Order` 含 `filled_quantity / filled_at / error_message`，带 `_submit_with_retry` 与对账（`reconcile`）。可作为 OMS 状态机的语义参考，但它是研究层，未与实盘 OMS 打通。 | confirmed |
| `backend_api_python/app/routes/quick_trade.py`、`agent_v1/quick_trade.py`、`services/quick_trade/` | 快捷交易直连下单与余额/错误处理路径；现货 size 口径存在已知缺口（见 P2-12），与本设计无耦合，但 OMS 取量须以后端核准口径为准。 | confirmed |
| 全仓检索 `twap / vwap / participation / slicing` 关键字 | 后端服务层未见 TWAP/VWAP/参与率拆单实现；`top-firm-gap-analysis.md` 差距 3 亦将"无真实执行算法与市场冲击建模"列为漏项。 | confirmed |

### 2.2 现有成本/TCA 能力为模型估算，缺实盘成交归因（confirmed / inferred）

| 证据位置 | 现状描述 | 分级 |
|---|---|---|
| `backend_api_python/app/services/trading_cost_analysis.py` | `TransactionCostAnalyzer` 基于参数模型估算成本：`OrderCost` 含 `spread_cost / slippage_cost / market_impact / commission / timing_risk / cost_bps`；滑点模型 `NONE / FIXED / LINEAR / SQUARE_ROOT`；`get_cost_summary` 从 `order_history` 聚合平均成本 bps 与占比。**当前为事前/模型估算**，未见以实盘成交均价、到达价、基准价反推的已实现归因。 | confirmed |
| `backend_api_python/app/routes/tca.py` | `/estimate-cost`（POST 估算）、`/cost-summary`（GET 聚合）、`/diagnose_backtest_gap`、`/check_data_quality`；前端 TCA 成本面板已对接 `/cost-summary`，`no_orders`/失败时空态 `--`（TODO #129）。 | confirmed |
| 成交延迟/到达价/基准价快照 | 事件流 `ExecutionEvent` 携带成交与费用，但未见"决策时刻价、订单到达交易所时刻价、成交时刻价、延迟（信号→提交、提交→成交）"的结构化时间戳与基准价快照落库。 | unknown（需落地前核实事件流与 adapter 实际可提供的字段与时戳） |

### 2.3 风控与对账前置边界（confirmed）

| 证据位置 | 现状描述 | 分级 |
|---|---|---|
| `backend_api_python/app/services/risk_engine.py`、`live_trading/account_risk.py`、`live_trading/gate.py`、`pending_orders/entry_position_guard.py` | 风控 gate、账户敞口/限额、入场持仓守卫在下单前置；OMS/EMS 不得在风控放行后再放宽任何限额或重判方向。 | confirmed |
| `core/execution/reconcile.py`（被 `engine.py` 引用） | 研究层已有对账容差与 `enforce/reconcile`；实盘周期对账/漂移调度尚属阻塞项 #108。 | confirmed（研究层）/ unknown（实盘调度是否复用） |

## 3. 概念模型与状态机

### 3.1 层级划分（OMS 职责 vs EMS 职责）

```
策略/信号层（方向、目标量、目标价、策略 id）
        │  意图订单 ParentIntent（只读方向与量，不做风控裁决）
        ▼
风控前置（现有：risk_engine / account_risk / entry_position_guard / gate）—— 放行或拒绝，OMS 不重复裁决
        │  放行后的可执行意图
        ▼
OMS 订单管理（parent order 生命周期、子单登记、成交回填、撤销/超时/对账、幂等键）
        │  子单指令
        ▼
EMS 执行算法（TWAP / VWAP / 参与率；节奏、切片大小、挂单/市价选择；不产生方向）
        │  原子订单
        ▼
现有直连执行器（live_trading/executors.py + 各所 adapter）—— 保持现状，异步返回检查并重试（硬规则 7）
        │
        ▼
成交/订单事件回流（execution_streams/）→ OMS 回填 + TCA 归因（只读）
```

### 3.2 Parent / Child 订单状态机（建议语义，落地前冻结）

**Parent Order（父单，对应一个可执行意图）**

| 状态 | 进入条件 | 退出条件 |
|---|---|---|
| `CREATED` | 风控放行后登记，带幂等键（client order id 派生）与冻结字段 | 进入 `ACTIVE` 或 `REJECTED` |
| `ACTIVE` | 已开始派发子单，剩余量 > 0 | 全部成交 `FILLED`；主动/被动撤销 `CANCELLED`；超期/异常 `EXPIRED` / `PARTIAL_CANCELLED` |
| `PARTIAL_FILLED` | 已有部分成交，剩余量 > 0，父单仍在推进 | 继续 `ACTIVE` 路径至终态 |
| `FILLED` | 累计成交量 == 目标量（含容差，容差来自配置分布校准） | 终态 |
| `CANCELLED` | 主动撤单且无剩余成交 | 终态 |
| `PARTIAL_CANCELLED` | 部分成交后撤销，剩余量未完成 | 终态 |
| `EXPIRED` | 超过父单时限仍未完成，且不允许继续 | 终态 |
| `REJECTED` | 派发前/派发中被风控或 adapter 拒绝，记录拒绝原因与上下文 | 终态 |

**Child Order（子单，对应一次原子下单尝试）**

沿用 `core/execution/engine.py` 已有语义：`PENDING → SUBMITTED → PARTIAL → FILLED`，旁路 `CANCELLED / REJECTED`；每个子单记录提交时间、交易所订单号、成交均价、成交量、费用、错误码与重试次数。

**状态机硬约束（对齐不变量）**

- 因果单向：拆单节奏与基准价只使用派发时点及之前已收盘/已确认的数据；不得用未来成交结果反推父单状态定义（硬规则 1、3）。
- 决策可审计：父单/子单/成交流水都保留输入快照（意图量、方向、风控放行结论、算法参数版本、各时间戳），拒绝路径必须带原因与上下文（硬规则 9）。
- 幂等：重试与事件回填以 client order id / 交易所订单号去重；异步返回必须检查返回值，失败按既有重试策略处理（硬规则 7）。
- intra-bar：由策略/退出触发的父单只在已收盘 bar 产生；EMS 内部切片计时属于执行节奏，不改变信号时点口径（硬规则 5）。

## 4. 候选方案权衡

### 4.1 OMS 落地形态

| 维度 | A. 旁路记录层（先只登记与对账，不改下单路径） | B. 轻量编排层（OMS 持有父单子单，直连执行器仍在底层） | C. 全量替换执行层（OMS/EMS 接管全部下单链路） |
|---|---|---|---|
| 与现有直连链路耦合 | 最低，只读接入事件流 | 中，在执行器前加编排，adapter 不动 | 高，需重写全部下单/撤单/查询 |
| 可审计性 | 只能事后归因，缺父单聚合 | 父子单全链路可还原 | 全链路可控 |
| 落地风险 | 低 | 中 | 高，触碰实盘下单链路（停止条件） |
| 对账/幂等能力 | 弱 | 强 | 强 |
| 适用阶段 | 阶段 1 取证与 TCA 打底 | 阶段 2 小流量灰度 | 阶段 3 以后，须评审与人工确认 |
| 主要缺点 | 不能控制拆单节奏 | 需处理编排器与 adapter 的状态一致性 | 回归面大，违反"不擅改实盘链路"边界 |

**建议**：阶段 1 走 A 取数与归因打底；阶段 2 在**单品种、最小手数、demo/只读可回放**环境验证 B；C 不在本期范围。

### 4.2 拆单算法候选

| 维度 | TWAP（时间加权） | VWAP（成交量加权） | 参与率（Participation Rate） | 单批直连（现状） |
|---|---|---|---|---|
| 基本思路 | 把总量按固定时间片均拆 | 按历史/滚动成交量分布分配切片 | 子单量跟随市场实时成交量的固定比例 | 一次性市价/限价发出 |
| 所需数据 | 时钟、目标时长 | 成交量分布（历史或滚动） | 实时成交量流 | 无 |
| 市场冲击控制 | 中，平滑时间分布 | 较好，贴合流动性 | 好，跟随流动性自动收缩 | 差，大单一次性冲击 |
| 信息暴露 | 低 | 低 | 低 | 高 |
| 实现复杂度 | 低 | 中（量能估计需分布校准，避免前视） | 中高（依赖实时量流与口径） | 低 |
| 风险 | 固定切片在低流动时段仍可能冲击 | 量能估计在结构突变时失真 | 参与率口径与交易量定义需核准 | 冲击/滑点集中 |
| 适用场景 | 流动性平稳、时限明确 | 有可靠成交量分布 | 高流动、希望控制参与占比 | 小额、紧急、限价可成交 |

**建议**：阶段 2 先实现 TWAP（数据依赖最少、语义最可审计）；VWAP/参与率待成交量流与口径核准后再评估。所有切片间隔、参与率上限、时限等参数由 CLEAN/KNOWN 集分布校准，不写死机构常用值。

### 4.3 TCA 归因口径候选

| 成本成分 | 口径定义（建议） | 数据依赖 | 现状可得性 |
|---|---|---|---|
| 点差成本 Spread | 决策/到达时刻买一卖一价差的一半 × 成交量 | 报价快照（bid/ask） | unknown：需核实事件流/adapter 是否留存快照 |
| 滑点 Slippage | 成交均价相对到达价（arrival price）的不利偏移 | 到达价 + 成交均价 | 部分：成交均价可得，到达价快照待补 |
| 延迟 Delay | 信号→提交、提交→成交的时间差分段 | 各环节结构化时间戳 | unknown：需核实时间戳精度与时钟一致性（硬规则 6 时区一致） |
| 成交偏离 Deviation | 成交均价相对基准价（决策价/VWAP/收盘参考）的偏离 | 基准价 + 成交均价 | 部分：成交均价可得，基准价口径待拍板 |
| 费用 Commission/Funding | 成交费用与资金费（来自事件流 fees） | 成交流水 | confirmed：`ExecutionEvent.fees` 已有 `FeeComponent` |

归因分解须可加总回总成交成本，并与现有 `trading_cost_analysis` 模型估算值并列展示、标注口径差异；**不得用模型估算值冒充已实现归因**。

## 5. 选型建议（分阶段）

### 阶段 1：取证与只读归因（不改下单路径）

- 只接入 `execution_streams/` 事件回流，补齐父单/子单与成交的只读登记（复用既有事件与落库，不新建交易决策）。
- TCA 先落地**可得成分**：费用、成交均价、成交量；点差/滑点/延迟/偏离在快照字段缺失时标 `--`，不填模型估算值。
- 输出一份"现有事件字段 vs TCA 所需字段"缺口表，作为阶段 2 前置。
- 所有读数口径标注 real/demo（对齐 RULES 4.4 演示/真实隔离）。

### 阶段 2：轻量 OMS + TWAP 小流量灰度

- 在风控放行后引入 B 方案编排：父单登记 → TWAP 切片 → 子单交给现有 `live_trading/executors.py`；adapter 语义不变。
- 先单品种、最小手数、demo 环境；对账以交易所成交流水为准（关联阻塞 #108 周期对账）。
- 算法参数（切片间隔、时限、参与率上限预留）经分布校准后冻结，写入实验/配置评审流程；不手工改 `registry.yaml`。

### 阶段 3（后续，须评审与人工确认）

- VWAP / 参与率算法；跨算法效果对比；与风险预算、策略退役等模块联动（只读引用，不反向改风控）。
- 是否演进到 C 方案全量替换，待阶段 2 对账与稳定性证据充分后再议。

## 6. 未验证假设与待拍板项

### 6.1 未验证假设（unknown，落地前必须核实）

- A1 事件流与各所 adapter 是否留存 bid/ask 快照、到达价、分段时间戳；时钟是否跨服务一致（时区偏移对齐硬规则 6）。
- A2 现有 `update_order_statuses` 与事件回流是否已能去重回填；是否存在重复成交计数风险。
- A3 现货/合约的成交量口径（合约张数 vs 名义量）在参与率/VWAP 计算中如何统一；关联 P2-12 现货持仓口径缺口。
- A4 实盘下单链路当前是否已有幂等键与重试上限；硬规则 7 的重试在各 adapter 的落地情况需逐一核实。
- A5 研究层 `core/execution` 的状态机与对账语义能否直接复用，还是仅作参考。

### 6.2 待评审拍板项

- C1 父单时限、成交容差（数量/价格）由哪一层定义，容差阈值取自哪个分布集。
- C2 TCA 基准价口径：决策价、到达价、当日 VWAP 还是收盘参考；不同方向（开/平/加仓）是否区分。
- C3 阶段 2 灰度的品种、手数、环境（demo 优先）与回退条件。
- C4 父单/子单/归因流水的落库归属与保留期；是否复用既有审计表，不改 schema（新增表须另行评审）。

## 7. 上线前置条件与验收标准

### 7.1 前置条件

- 风控前置链路（`risk_engine / account_risk / entry_position_guard / gate`）结论可被 OMS 只读引用；OMS 不重复裁决、不放宽限额。
- 事件回流去重与字段缺口表完成核实（A1、A2）。
- 阶段 2 之前：幂等键、异步返回检查与重试策略在底层执行器/adapter 核实通过（硬规则 7）。
- 算法参数经分布校准并冻结；决策规则实验前冻结（RULES 1.1）。
- 涉及实盘下单链路的改动，按 AGENTS.md 停止条件先人工确认。

### 7.2 验收标准（阶段 1，只读）

1. 父单/子单/成交流水可按幂等键还原：方向、量、风控放行结论、算法参数版本、时间戳、拒绝原因齐全（决策可审计）。
2. TCA 面板只展示已实现成分；缺失快照的成分显示 `--`，不出现模型估算冒充实盘归因。
3. 不修改仓位、下单、平仓、资金计算逻辑；不触碰禁改目录；不改既有 schema。
4. 关键路径附单测：状态迁移合法路径、非法跃迁被拒、幂等回填不重复计数；黄金集断言不放宽（硬规则 10）。

### 7.3 验收标准（阶段 2，灰度，供评审）

1. TWAP 父单可在时限内完成或按规则撤销；子单状态与交易所成交流水对账一致（容差来自配置）。
2. 单笔大单被拆为多子单，无重复下单、无超量成交；撤单后剩余量状态正确。
3. 成交归因可分解到可得成本成分，并与模型估算并列标注口径。
4. 灰度仅在批准品种/手数/环境；异常时可回退到现有直连路径，且不留悬挂子单。

## 8. 对应 TODO / 阻塞编号

| 编号 | 关联内容 | 本设计关系 |
|---|---|---|
| #107 | 共享风控 gate 复用三同步入口（触碰实盘下单链路，待拍板） | OMS 前置引用风控结论，复用方式须随 #107 一并拍板 |
| #108 | 周期对账 / 漂移告警（需新增后台调度，确认后再动） | 父单/子单与成交流水对账、漂移告警依赖该调度 |
| P2-12 | 现货持仓口径偏大（触及持仓/资金路径，须先拍板） | 拆单量与参与率口径须先核准现货基础币/名义量口径 |
| 差距 3（top-firm-gap-analysis） | 低延迟执行：无真实执行算法与市场冲击建模 | 本设计对应 TWAP/VWAP/参与率与 TCA 补口 |
| 待登记（拟） | 见第 9 节拟登记 TODO 条目 | 评审通过后由人写入 `docs/TODO.md`，本文件不自行改 TODO |

## 9. 风险与未验证项汇总

- **风险**：编排器与 adapter 状态不一致导致悬挂子单/重复下单；量能估计前视失真；跨服务时钟不一致使延迟归因失真。
- **未验证**：实盘成交质量、各所字段完备性、灰度冲击与滑点表现均未在真实环境复核；本文件不含绩效数字，所有阈值待分布校准。
- **边界重申**：本草稿不含生产代码；`configs/`、`registry.yaml`、`mt5/`、`secrets/`、`runtime/`、`ledger/` 未触碰；未删文件、未改 schema；未执行 git 提交。
