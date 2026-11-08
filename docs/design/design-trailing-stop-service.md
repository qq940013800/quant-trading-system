# 设计草稿：统一跟踪止盈 / 移动止损服务

> 状态：**待评审草稿**，不含任何生产代码。
> 边界：本文件只做职责划分、状态口径与统一关系设计，不改交易/风控/下单/资金逻辑，不碰 `configs/`、`registry.yaml`、`mt5/`、`secrets/`、`runtime/`、`ledger/`。
> 强制不变量（`AGENTS.md` 硬规则 4）：**止损只允许向盈利方向移动（单调）**；**R 倍数用入场冻结的 `atr0 / entryDist`**。硬规则 5：信号与退出决策只允许在已收盘 bar 调用；硬规则 9：异常必须带上下文记录；阈值来自分布校准，不照搬机构数值。

## 1. 目标

把当前分散在多个模块中的"止损 / 保本 / 跟踪止盈 / 吊灯 / 利润回吐 / 分批止盈"逻辑，收敛为一套**口径统一、状态可审计、单调可证**的跟踪止盈服务设计：

1. **单一止损状态口径**：每笔持仓一个冻结的入场快照（入场价、方向、`atr0`、`entryDist`），一个当前止损价，一组保护状态（是否激活保本/跟踪、峰值价、最大有利 R、分批进度）。
2. **单调强制**：任何止损价更新都必须经过单调校验——多头只上移、空头只下移；放宽方向拒绝并记录上下文，不允许静默覆盖。
3. **R 倍数冻结口径**：R 一律用入场冻结的 `atr0 / entryDist` 计算，禁止用重算后的实时 ATR 替换冻结距离；保本、激活、跟踪偏移都以冻结 `entryDist` 为基准。
4. **与现有保护模块的统一关系**：明确哪些是现状 confirmed、哪些待建；统一服务作为**裁决口径层**，现有各模块按环境（本地风控引擎 / 交易所原生保护 / 策略 v2 / 入场守卫）分层承接，初期不替换已在跑路径。
5. **让利润奔跑的分层触发**：基础止损 → 保本 → 分批止盈 → 跟踪/吊灯/回吐保护，状态迁移可回放、可审计。

### 1.1 非目标（本期明确不做）

- 不新增风险限额、不平仓指令绕过现有执行链路；不修改交易所原生止损单的下单/撤单语义。
- 不重新估计或热更新冻结的 `atr0 / entryDist`；不用实时波动率反推 R。
- 不在本层引入新的绩效目标或胜率阈值；所有触发阈值（R 倍数、ATR 倍数、回吐比例）由 CLEAN 集分布校准后冻结。
- 不编造任何止损/止盈绩效数字或机构常用 ATR 倍数基线。

## 2. 现状证据（文件:目录佐证，分级 confirmed / inferred / unknown）

### 2.1 研究层风控：单调 + 冻结口径已有基础（confirmed）

| 证据位置 | 现状描述 | 分级 |
|---|---|---|
| `core/risk/stops.py`（231 行） | 四级止损（时间/价格 ATR/信号/跟踪）；`StopState` 冻结 `entry_price / direction / entry_atr / entry_dist`；`compute_current_r` 用冻结 `entry_dist` 算 R；`update_stop` 单调校验，放宽方向抛 `StopWideningError`（带 current/new/direction/ts/上下文）；`update_breakeven_stop / update_trailing_stop` 基于 `max_favorable_r` 与冻结 `entry_dist`；`evaluate_stops` 统一决策入口。黄金夹具 `c03_stop_widen` 反例：多头把止损改到更低值必须被拒。 | confirmed |
| `backend_api_python/app/services/risk_engine.py`（587 行） | `Position` 冻结 `atr_atry_entry`（入场 ATR）、`entry_dist`（入场止损距离）；`trailing_activated / breakeven_activated / peak_price / peak_unrealized_pnl / remaining_ratio / scale_out_done` 等状态齐全。`_update_trailing_stop`：多头 `new_stop = peak - trail_dist`，仅当 `new_stop > stop_loss_price` 才上移；空头仅当 `new_stop < stop_loss_price` 才下移；`_update_breakeven_stop` 保本价须比当前止损更优才移动；另有吊灯 `_update_chandelier_exit`、分批 `_check_scale_out`、回吐 `_check_profit_retracement`。 | confirmed |
| `risk_engine.py` 配置 | `RiskConfig` 含 `trailing_activation_r / trailing_atr_mult / breakeven` 等；`StopLossType.ATR` 初始止损由 `atr_at_entry × atr_multiplier` 或 `entry_dist` 派生。 | confirmed |

### 2.2 实盘/策略侧保护模块（confirmed，口径分散）

| 证据位置 | 现状描述 | 分级 |
|---|---|---|
| `backend_api_python/app/services/strategy_v2/protection.py`（341 行） | `ProtectionSpec`（`stop_loss_pct / trailing_stop_pct / trailing_activation_pct / trailing_rebase_on_scale_in / take_profit_pct / time_limit_seconds`）；`ProtectionState`（`entry_price / highest_price / lowest_price / trailing_active`）；`ProtectionEngine.evaluate_bar / evaluate_price` 产出 `ProtectionDecision`；`_trailing_trigger` 按**百分比**从峰值回撤（多：`highest*(1-pct)`；空：`lowest*(1+pct)`），激活用入场价×(1±activation_pct)；intra-bar 模式 `conservative/balanced/aggressive` 决定同 bar 多候选优先级。**口径为百分比，未使用冻结 `atr0/entryDist` 的 R 倍数**；加仓时可按 `trailing_rebase_on_scale_in` 重置峰值/重新激活。 | confirmed |
| `backend_api_python/app/services/live_trading/native_protection.py`（326 行） | 交易所**原生保护单**下单适配：`NativeProtectionRequest`（`stop_loss_price / take_profit_price / trailing_stop_pct / trailing_activation_pct / entry_price`）；`protection_prices_from_payload` 从排队单 payload 解析绝对价或百分比止损；按所（binance/okx/bitget/bybit/gate/htx）分别挂 STOP_MARKET / move_order_stop / trading-stop / loss_plan；部分所（gate/htx）跟踪止损标注 `managed_by: strategy_runtime`。 | confirmed |
| `backend_api_python/app/services/live_trading/account_risk.py`（252 行） | 账户级敞口/限额快照（gross/margin/fee/funding/限额违规），属组合与仓位风险，不负责单笔止损价移动。 | confirmed |
| `backend_api_python/app/services/pending_orders/entry_position_guard.py`（124 行） | 入场前持仓归属/反向持仓守卫（preflight），拒绝反向开仓与漂移入场；属**入场闸门**，不参与持仓后的跟踪止盈。 | confirmed |

### 2.3 口径缺口与待核实项（inferred / unknown）

| 事项 | 现状判断 | 分级 |
|---|---|---|
| 多套止损口径并存 | `risk_engine` 用冻结 ATR/R；`strategy_v2` 用百分比峰值回撤；`native_protection` 把百分比/绝对价转成交易所原生单。三者触发口径、激活条件、回撤基准未在一处对齐。 | inferred（代码路径已确认，是否同一持仓同时受多套约束需核实） |
| 冻结快照在实盘链路的一致性 | `risk_engine.Position` 有冻结字段；`strategy_v2.ProtectionState` 仅冻结 `entry_price`，未见冻结 `entry_dist/atr0`，其 R 口径缺失。 | confirmed（v2 无冻结距离字段） |
| 原生保护单与内部跟踪状态对账 | 交易所原生止损/跟踪单被触发或失效后，内部状态是否同步、是否存在重复保护或孤儿单，未见统一对账。 | unknown（关联阻塞 #108 周期对账） |
| intra-bar 触发口径 | `strategy_v2` 有 `evaluate_bar`（用 high/low/open）与 `evaluate_price` 两种；硬规则 5 要求退出决策只在已收盘 bar 调用，bar 内 high/low 触碰的保守/激进取舍需在统一口径中明确。 | unknown（现有模式选择与策略实际调用方式需核实） |
| 加仓后峰值重定基准 | `strategy_v2` 有 `trailing_rebase_on_scale_in`；`risk_engine` 分批/加仓路径如何处理峰值与冻结距离需核实。 | unknown |

## 3. 统一服务设计

### 3.1 分层职责

```
信号/策略层（产生开仓意图与平仓信号）
        │
风控前置（account_risk / entry_position_guard / gate）—— 入场与限额，不在本服务内
        │  成交确认后登记持仓保护快照
        ▼
统一跟踪止盈服务（口径裁决层，本设计）
  ├─ 冻结入场快照：entry_price / side / atr0 / entryDist / entry_time
  ├─ 保护状态：breakeven_active / trailing_active / peak_price / max_favorable_r / scale_out_done
  ├─ 单调校验：多头 new_stop >= current_stop；空头 new_stop <= current_stop；否则拒绝并记录
  ├─ 触发裁决：基础止损 → 保本 → 分批止盈 → 跟踪/吊灯/回吐 → 信号/时间止损
  └─ 输出：保护决策（持有 / 移止损 / 分批平仓 / 全部平仓）+ 审计快照
        │
执行承接（按环境分层，保持现状语义）
  ├─ 本地/研究路径：risk_engine 内部状态（core/risk/stops 口径）
  ├─ 策略 v2 路径：ProtectionEngine 决策结果
  ├─ 交易所原生：native_protection 挂/改/撤原生单（异步返回检查并重试，硬规则 7）
  └─ 事件回流：execution_streams 成交/状态回填，对账以交易所为准
```

**边界原则**：统一服务只产出"应该把止损移到哪 / 是否触发平仓"的裁决；实际下单、撤单、改单仍走现有执行器与原生适配；服务不直接持有资金与下单权限。

### 3.2 冻结入场快照（不可变字段）

| 字段 | 含义 | 来源约束 |
|---|---|---|
| `entry_price` | 成交均价（成交确认后冻结） | 不得被加仓均价覆盖而改变单笔 R 基准；加仓另立批次记录 |
| `side` | long / short（direction +1/-1） | 冻结 |
| `atr0` | 入场时点 ATR（冻结） | 只在 CLEAN 集估计口径内产生；禁止用后续实时 ATR 替换 |
| `entryDist` | 入场止损距离（冻结 = `atr0 × atr_mult` 或配置距离） | R 倍数唯一分母；后续重算 ATR 不得改写 |
| `entry_time` | 成交时点（UTC，时区对齐硬规则 6） | 时间止损与审计用 |

**R 倍数口径**：`R = (current_price - entry_price) × direction / entryDist`；保本、跟踪激活、分批目标、跟踪偏移均以冻结 `entryDist` 为基准，禁止用浮动距离或实时 ATR 重新标定。

### 3.3 保护状态机与触发口径

| 阶段 | 触发条件（口径，阈值待分布校准） | 止损/动作 | 单调约束 |
|---|---|---|---|
| 基础止损 | 价格触及初始止损（entry ∓ entryDist） | 平仓离场 | 初始止损为基准，后续只能向盈利方向收紧 |
| 保本 | 最大有利 R ≥ `breakeven_r` | 止损移到入场价 + 偏移（偏移以冻结 `entryDist` 计） | 多头上移、空头上移方向校验；不优于当前止损则不动 |
| 分批止盈 | 达到分批 R 目标（如 2R/3R，比例与档位列配置） | 按比例减仓，记录 `scale_out_done`；剩余仓位继续跟踪 | 减仓不改冻结快照；剩余量 R 基准仍为原 entryDist |
| 跟踪止损 | 最大有利 R ≥ `trailing_activation_r` 后激活 | 峰值价后退让固定 R 距离（或冻结 ATR 倍数） | 新止损必须比当前更优，否则拒绝 |
| 吊灯止损 | 跟踪激活后，峰值回撤达 `chandelier_atr_mult × atr0` | 剩余仓位离场（趋势反转保护） | 与跟踪止损取更优（更靠近盈利侧）者生效 |
| 利润回吐 | 峰值未实现利润回撤达回吐阈值 | 剩余仓位止盈 | 回吐阈值来自分布，不照搬固定百分比 |
| 信号/时间止损 | 入场逻辑反转；或超期且未达保本 | 平仓 | 优先级最高（逻辑失效先于价格保护） |

**候选冲突优先级**（沿用 `evaluate_stops` / `ProtectionEngine._choose` 思路，落地前冻结）：信号止损 > 时间止损 > 跟踪/吊灯 > 保本 > 基础 ATR 止损；同一 bar 多候选的取舍受 intra-bar 模式约束，且须符合硬规则 5（退出决策基于已收盘 bar；bar 内 high/low 触碰只用于保守口径判断，不产生提前 intra-bar 下单）。

### 3.4 单调强制（硬规则 4 落地口径）

- 多头：`new_stop >= current_stop`；空头：`new_stop <= current_stop`。
- 任何放宽方向的更新请求：拒绝，抛/记录带上下文的错误（symbol、ts_utc、current、new、direction、来源模块、触发阶段），不得静默回退为旧值或忽略。
- 保本、跟踪、吊灯各路算出的新止损，先汇入同一单调校验点，再决定是否生效；生效后记录旧值→新值与触发原因，保证可审计。
- 分批减仓后，剩余仓位的止损不得因减仓而放宽。

## 4. 候选方案权衡

### 4.1 统一服务形态

| 维度 | A. 口径规范层（只定义快照/状态/校验，各模块自实现） | B. 共享裁决服务（统一状态机 + 单调校验，现有模块接入适配） | C. 全量替换（重写所有保护模块为单一实现） |
|---|---|---|---|
| 口径一致性 | 弱，仍靠各模块自觉 | 强，单一裁决点 | 最强 |
| 与现有路径耦合 | 最低 | 中，接入适配层 | 高，触碰实盘保护链路 |
| 落地风险 | 低 | 中（可先研究/demo 环境） | 高，须评审与人工确认 |
| 审计可回放 | 分散 | 集中 | 集中 |
| 主要缺点 | 不能真正消除口径分叉 | 需处理多源状态同步与对账 | 回归面大，违反不擅改边界 |

**建议**：阶段 1 走 A，先冻结统一快照/状态/单调口径文档与单测夹具；阶段 2 在研究层与 v2 路径验证 B；C 不在本期范围。

### 4.2 跟踪基准口径

| 维度 | 冻结 ATR / R 距离（`atr0 / entryDist`） | 峰值固定百分比回撤（现状 v2） | 混合（R 为主，百分比为兜底） |
|---|---|---|---|
| 与 R 倍数体系一致性 | 高，直接用冻结距离 | 低，百分比与 R 脱钩 | 中 |
| 跨品种波动适应性 | 好（波动自适应） | 弱（固定百分比在高波/低波失真） | 较好 |
| 实现复杂度 | 中 | 低 | 中高 |
| 现有基础 | `stops.py` / `risk_engine` 已有 | `strategy_v2` / `native_protection` 已有 | 需映射层 |
| 风险 | ATR 估计样本不足时不稳 | 口径分叉、被噪声扫出 | 两套口径需明确优先级 |

**建议**：统一口径以冻结 `atr0/entryDist` 的 R 距离为主；百分比口径仅作为交易所原生单落地时的翻译参数，不作为内部裁决基准；映射关系与优先级在评审拍板。

### 4.3 保护落地位置

| 维度 | 内部状态跟踪（risk_engine/stops） | 交易所原生单（native_protection） | 双轨（内部裁决 + 原生单兜底） |
|---|---|---|---|
| 断网/进程崩溃韧性 | 弱（依赖内部进程存活） | 强（留在交易所侧） | 最强 |
| 口径一致性 | 高 | 受各所能力限制（部分所不支持跟踪/激活） | 中，需对账 |
| 实现复杂度 | 低 | 中（多所适配已存在） | 高 |
| 孤儿单/重复保护风险 | 低 | 中 | 需对账消除 |

**建议**：阶段 1 先在内部路径统一口径；实盘是否双轨、双轨如何对账，待 #108 周期对账与各所能力核实后再定，不在本期拍板。

## 5. 选型建议（分阶段）

### 阶段 1：口径冻结与夹具（不改实盘路径）

- 冻结统一快照字段、R 口径、状态机与单调校验规则；补齐 `entryDist/atr0` 在 v2 路径缺失字段的映射方案（文档级）。
- 复用 `core/risk/stops.py` 已有单调校验与黄金夹具，补充：多模块口径对照表、合法/非法状态迁移用例、冻结 R 计算用例。
- 输出"内部口径 ↔ 交易所原生参数"翻译映射表（百分比/R/绝对价），标注各所能力缺口。

### 阶段 2：共享裁决服务接入（研究层 + demo）

- 在研究层与策略 v2 路径引入统一裁决点：各路止损候选汇入同一单调校验，输出决策与审计快照。
- 先在研究回测与 demo 环境验证：单调拒绝、冻结 R、分批进度、峰值重定基准等行为；不接实盘下单。
- 参数（R 档位、ATR 倍数、回吐阈值）经分布校准后冻结。

### 阶段 3（后续，须评审与人工确认）

- 内部裁决与交易所原生单双轨对账；孤儿单检测与自动收口；实盘小灰度。
- 是否收敛为 C 方案单一实现，待阶段 2 证据充分后再议。

## 6. 未验证假设与待拍板项

### 6.1 未验证假设（unknown）

- A1 同一实盘持仓是否同时受 `risk_engine`、`strategy_v2`、`native_protection` 多套约束；触发以哪一套为准。
- A2 v2 路径与原生保护单能否补齐冻结 `atr0/entryDist`；加仓/分批后峰值与距离如何重定基准。
- A3 各所原生跟踪单（callbackRatio/move_order_stop/trading-stop）在激活、失效、撤单后的状态回流字段是否完备。
- A4 intra-bar：`evaluate_bar` 的 high/low 触碰在实盘调用链中是否被提前用于下单；与硬规则 5 的合规边界需逐路径核实。
- A5 现有 `risk_engine` 线程检查间隔（`stop_loss_check_interval_sec`）与事件回流时点是否一致，是否存在漏触发/重复触发。

### 6.2 待评审拍板项

- C1 跟踪主口径：冻结 R 距离 vs 峰值百分比；二者映射与优先级。
- C2 分批止盈档位、比例、保本/激活 R 阈值的分布校准来源与冻结方式。
- C3 加仓（scale-in）后是否重置峰值、是否重定基准；`trailing_rebase_on_scale_in` 统一取值。
- C4 是否双轨（内部 + 原生单）；对账容差与孤儿单收口归谁负责。
- C5 信号止损/时间止损/跟踪在同一 bar 冲突时的最终优先级与 intra-bar 模式默认值。

## 7. 上线前置条件与验收标准

### 7.1 前置条件

- 冻结快照字段在接入路径可取得（entry_price、side、atr0、entryDist、entry_time）；缺失时不得用实时值顶替。
- 单调校验点唯一且可记录上下文；异常路径符合硬规则 9（禁止 `except Exception: pass`）。
- 阈值经 CLEAN 集分布校准并实验前冻结；不按绩效网格搜索（不变量 3、RULES 1.1）。
- 涉及实盘保护单/下单链路的改动，按 AGENTS.md 停止条件先人工确认。

### 7.2 验收标准（阶段 1，文档 + 单测）

1. 单调不变量有单测覆盖：多头上移/空头上移合法；放宽方向被拒且上下文完整；黄金集断言不放宽。
2. R 倍数单测：用冻结 `entryDist` 计算；重算 ATR/实时价格不得改写冻结距离。
3. 状态迁移表覆盖：基础→保本→分批→跟踪/吊灯/回吐的合法路径与非法跃迁；审计快照字段齐全。
4. 不修改现有下单/平仓/资金逻辑；不触碰禁改目录；不改 schema。

### 7.3 验收标准（阶段 2，研究/demo，供评审）

1. 各路保护候选汇入同一裁决点后，生效止损始终满足单调约束；旧值→新值与原因可回放。
2. 分批减仓后剩余仓位止损未被放宽；冻结 R 基准保持一致。
3. 决策日志可还原：入场快照、峰值、最大有利 R、触发阶段、最终决策。
4. demo 环境无重复保护/孤儿单；与交易所状态对账（如已接入）差异在配置容差内。

## 8. 对应 TODO / 阻塞编号

| 编号 | 关联内容 | 本设计关系 |
|---|---|---|
| #107 | 共享风控 gate 复用三同步入口（待拍板） | 统一保护服务的前置风控结论引用方式随 #107 对齐 |
| #108 | 周期对账 / 漂移告警（需新增调度，确认后再动） | 内部状态与交易所原生单对账、孤儿单检测依赖该调度 |
| 硬规则 4 | 止损单调；R 倍数用入场冻结 atr0/entryDist | 本服务核心不变量 |
| 硬规则 5 | intra-bar 只在已收盘 bar 决策 | bar 内触碰口径与决策时点须合规 |
| 待登记（拟） | 见第 9 节拟登记 TODO 条目 | 评审通过后由人写入 `docs/TODO.md`，本文件不自行改 TODO |

## 9. 风险与未验证项汇总

- **风险**：多套保护口径并存导致重复触发或孤儿单；v2/原生路径缺冻结 R 基准；跨所原生能力不一致；进程崩溃后内部状态丢失。
- **未验证**：实盘多轨保护行为、各所原生单状态回流、intra-bar 调用合规性、加仓重定基准均未在真实环境复核；本文件不含绩效数字，阈值待分布校准。
- **边界重申**：本草稿不含生产代码；`configs/`、`registry.yaml`、`mt5/`、`secrets/`、`runtime/`、`ledger/` 未触碰；未删文件、未改 schema；未执行 git 提交。
