# 设计草稿：实盘三入口持仓口径、统一风控闸、对账接线与策略注册接入

> 状态：**待评审草稿**；纯函数切片已分批固化（#166 现货两层口径、#167 统一 pre-trade 闸、#168 部署校验），后端路由/适配器接线留第二步，尚未改任何运行时入口。
> 边界：不触碰 `configs/`、`registry.yaml`、`mt5/`、`secrets/`、`runtime/`、`ledger/` 及任何风控阈值常量；不修改 `live_trading/`、`quick_trade/`、`pending_orders/`、`strategy_runtime/`、`strategy_v2/deployment.py`、凭证写库相关运行时代码（本切片仅只读勘察）。
> 不变量约束（`AGENTS.md`）：因果单向（只用 `available_at <= bar.close` 的数据）、决策可审计（每笔接受/拒绝可还原各层输入与判断）、阈值来自分布（不由绩效网格搜索产生）；硬规则 1（前视守卫）、2（集合分离：ATR/vol/Hurst 只在 CLEAN 集估计；供需区只用 KNOWN 集构建）、5（intra-bar：信号与退出决策只允许在已收盘 bar 调用）、9（异常必须带上下文记录）、10（改动须附单测，黄金集断言不得放宽）。
> 证据分级：**confirmed** = 本轮只读核对到代码落点；**inferred** = 由已核对代码推断，未直接执行验证；**unknown** = 本轮未核对或无法判定。
> 关联文档：对账/漂移模块盘点、调度现状、降级矩阵与审计要求已由 `docs/design/reconciliation_drift_alarm_design.md`（下称「对账草案」）覆盖，本文 §3 引用其结论（R1–R11、D1–D12、S1–S8），不整段重复，聚焦「三入口对账接线 + 告警出口」。

## 0. 本轮范围与票据映射

| 票据 | 主题 | 本文小节 |
|---|---|---|
| #153 | 现货两层持仓口径与存量保护 | §1 |
| #154 | 自动/手动/快捷三入口统一 pre-trade 风控闸 | §2 |
| #155 | 三入口对账接线与告警出口 | §3 |
| #156 | 策略/模型注册中心接入（替代硬编码演示策略） | §4 |

行号偏差说明：任务简报给出的部分行号与代码实际落点有偏差，本文以代码实际落点为准并标注；未发现与简报结论相矛盾的证据。

---

## 1. #153 现货持仓口径：系统跟踪净持仓 vs 钱包可用余额

### 1.1 现状落点

| # | 现状结论 | 落点 | 分级 |
|---|---|---|---|
| S1 | 快捷成交净持仓按 `qd_quick_trades` 成交记录聚合：long = buy − sell，short = sell − buy，结果向下截断到 0；注释明确「若用户在别处同品种交易或记录不全，口径不完美」 | `backend_api_python/app/routes/quick_trade.py:1379` `_quick_trade_net_base_qty`（简报记 :1387，实际函数定义 :1379，docstring :1387） | confirmed |
| S2 | `close_scope=system_tracked` 仅对 swap/perp 开放；现货传入即被拒（400） | `quick_trade.py:1526-1527` | confirmed |
| S3 | swap 的 system_tracked 平仓量 = `min(tracked_net, position_size)`；`tracked_net <= 0` 时拒绝平仓 | `quick_trade.py:1530-1546` | confirmed |
| S4 | 现货平仓走 `clamp_spot_close_quantity`：上限取交易所钱包 free base × 安全比率，再向下归一化到手数步长 | `backend_api_python/app/services/live_trading/spot_sizing.py:395`；free 取数 `:411`；封顶 `:417` | confirmed |
| S5 | 现货持仓展示 `get_spot_base_holding` 返回钱包 **total / available / avg_cost**（交易所账户口径，含账户原有存量） | `spot_sizing.py:96`；free 口径 `:246` `get_spot_free_base_balance` | confirmed |
| S6 | 现货平仓安全比率来自 env `SPOT_CLOSE_SAFETY_RATIO`，默认 `_DEFAULT_CLOSE_SAFETY = 1.0`；开仓缓冲默认 `0.995`；未见由 CLEAN 分布校准的证据 | `spot_sizing.py:20-31,34-41` | confirmed（数值存在）；**inferred**（未接入校准流程） |
| S7 | 现货平仓上限只与钱包 free 比较，**未与本地系统跟踪净持仓比较**；当钱包含账户原有存量时，存在误卖存量的风险 | `spot_sizing.py:415-420`；`quick_trade.py:1562-1583` | confirmed（代码路径）；**inferred**（误卖规模取决于账户存量分布，未量化） |
| S8 | 除 `routes/quick_trade.py` 外，`routes/agent_v1/quick_trade.py` 不含上述净持仓/平仓口径符号（grep 0 命中） | `backend_api_python/app/routes/agent_v1/quick_trade.py` | confirmed |

### 1.2 第一性原理目标

- **决策可审计**：一笔现货卖出「卖的是哪部分」必须可还原——是本系统跟踪到的成交净额，还是钱包里的存量；两个口径的输入快照、取值层级、封顶结果都要留痕。
- **因果单向**：平仓数量只能基于已成交、已收盘的本地记录与已拉取的钱包快照计算；不得用未来成交或未更新的缓存余额反推。
- **不把存量当可处置额度**：系统只应对「自己跟踪到的净持仓」负有平仓语义；钱包 free 只是交易所侧的可成交物理上限，不是所有权口径。

### 1.3 两层口径定义（本设计的核心区分）

| 层级 | 含义 | 数据来源 | 用途 |
|---|---|---|---|
| L1 系统跟踪净持仓 | 本系统成交聚合得到的净 base 量（quick 成交流水 + 策略台账），记录「这部分是系统经手的」 | 本地库：`qd_quick_trades` 成交净额；策略侧 `qd_strategy_trades` / `qd_strategies_trading`（见 §3.1） | 平仓数量的**所有权上限**；存量保护边界 |
| L2 钱包可用余额 | 交易所钱包该 base 资产的 total / available（free + locked），含账户原有存量、在途挂单占用 | 交易所账户接口（`get_spot_base_holding` / `get_spot_free_base_balance`） | 平仓可成交的**物理上限**（防超卖、预留手续费/锁定） |

**平仓数量上限取法（设计结论，待评审）**：

1. 现货系统跟踪平仓（对应 swap 的 `system_tracked` 语义）：`final_close = min(requested, L1 系统跟踪净额, L2 free × 安全比率)`，再归一化到手数步长；**L1 是所有权硬上限**，L2 只是物理约束。
2. 现货全平（用户明确处置整个钱包持仓）：可直接以 L2 free 为物理上限，但请求与审计记录中必须显式标注「含账户存量、非系统跟踪部分」，不得与 L1 口径混算。
3. 存量保护表达：当 `L2 free > L1 净额` 时，超出部分标记为 `unmanaged_stock`，不进入可平仓额度；当 `L2 free < L1 净额`（存量缺失/成交漏记/手续费侵蚀）时，以 L2 为准并在审计记录中标注口径缺口，不允许虚卖。

### 1.4 拟落地的最小改动方案（不写实现代码）

- **复用**现有纯函数：`get_spot_base_holding`（L2 total/available）、`get_spot_free_base_balance`（L2 free）、`normalize_spot_base_quantity`（步长归一化）；现有 `_quick_trade_net_base_qty` 的聚合口径扩展到现货时复用其 SQL 聚合语义，不另起一套流水统计。
- **拟新增**（设计层，落地评审后再实现）：
  - 一个现货持仓口径解析纯函数：输入本地跟踪净额（来自台账聚合）+ 钱包持有快照，输出 `{tracked_net, wallet_total, wallet_free, unmanaged_stock, ownership_cap, physical_cap}` 结构化口径，供平仓 sizing 与展示层共用。
  - 平仓 sizing 分支：按 §1.3 第 1/2 条区分「系统跟踪平仓」与「存量全平」两种意图，分别套用 L1/L2 上限；意图由请求显式声明，不得从余额大小猜测。
- **接线顺序**：① 先落口径解析纯函数与单测；② 再接平仓路由调用，路由只做意图透传与错误码映射；③ 最后对齐展示层 `get_spot_base_holding` 的字段口径，避免页面用 L2 总量误报「系统持仓」。
- **不做**：不自动补单、不自动划转存量、不改动钱包与挂单锁定逻辑。

#### 1.4.1 纯函数落点（已固化，#166；适配器接线未做）

- 模块：`core/execution/spot_ownership.py`；单测 `tests/test_execution/test_spot_ownership.py`（20 用例，定向通过；#324 补 NaN/±inf 有限性兜底后纳入基线）。
- `resolve_spot_ownership(tracked_net, wallet_total, wallet_free, safety_ratio=1.0) -> SpotOwnershipSnapshot`：tracked/total 容错转非负；`wallet_free=None` → `free_known=False`、`physical_cap=None`、`unmanaged/shortfall=0`（未知不推断）；free 已知时 `unmanaged=max(0, free−tracked)`、`shortfall=max(0, tracked−free)`、`physical=free×ratio`；ratio 越界（≤0 或 >1.0）回退默认 1.0。
- `resolve_spot_close(snapshot, requested, intent="tracked", lot_step=None) -> SpotCloseDecision`：intent 归一 `full`/`tracked`；req≤0 → `rejected_nonpositive`；free 未知 → `rejected_free_unknown`（fail-closed，不回退按请求量放行）；tracked 意图 cap=`min(ownership_cap, physical_cap)`，capped_by=ownership/physical；full 意图 cap=physical_cap，audit 标 `includes_unmanaged_stock=True`；cap 为 None/≤0 → `rejected_no_cap`；lot_step 注入时向下 floor 到步长，缺省不归一化。
- 边界：纯函数不触网、不读库；L1 净额聚合 SQL、钱包快照拉取、意图透传与错误码映射留后端适配器（第二步）。安全比率默认 `1.0` 为占位值，非 CLEAN 校准产物（见 §1.6）。#324 起 `_nonneg` 对 NaN/±inf 归一 0.0、`_valid_ratio` 对非有限比率回落默认 1.0；inf 请求平仓量随之拒为 `rejected_nonpositive`。

### 1.5 失败降级与可审计点

| 场景 | 降级行为 | 分级 |
|---|---|---|
| 钱包快照拉取失败/字段缺失 | 本轮不产出可平仓额度，拒绝平仓（fail-closed 倾向）；记录错误归类、symbol、credential 与快照时间戳；不回退到「按请求量放行」 | inferred（沿用 §3 对账草案 fail-closed 原则） |
| 本地跟踪净额聚合失败 | 拒绝系统跟踪平仓；提示改用显式存量全平路径（该路径单独留痕）；异常带上下文记录，禁止 `except: pass` | inferred |
| L2 free 未知（接口返回空/0） | 不判定为无存量；额度标记 `unknown`，保守拒绝；不把 0 free 当作可卖 0 之外的结论 | inferred |
| 可审计记录 | 每笔平仓留存：意图层级（tracked/full）、L1 净额及其流水范围、L2 total/free 快照与时间戳、安全比率取值、各层上限、最终量、归一化前后值、拒绝原因码 | 设计约束，对齐对账草案 §8 |

### 1.6 阈值必须来自分布

- 现货平仓安全比率、手续费/锁定预留缓冲、存量缺口告警容差，正式取值须由 **CLEAN 集**上的手续费率、滑点、挂单锁定占用分布校准（分位数/基线，见 §3.6 与对账草案 §5）；当前 env 默认 `1.0 / 0.995` 为占位值，不得视为已校准阈值。
- 禁止用实盘绩效网格搜索反推安全比率；阈值/基线记录数据集、区间、版本与校准方式，占位值与已校准值在记录中显式区分。
- 集合分离：费率/滑点类统计只在 CLEAN 估计；结构/口径类常量只用 KNOWN；HELD_OUT 静默集禁止读取（`core/data/splits.py:73-95`  confirmed）。

### 1.7 单测计划（core 纯函数可测；I/O 注入桩）

- L1/L2 口径解析纯函数：`free > tracked_net`（存量保护，超额部分进 `unmanaged_stock`）；`free < tracked_net`（口径缺口标记）；`free=0/None` 未知分支；total 与 available 不一致（locked 占用）。
- 平仓 sizing：系统跟踪平仓三层封顶 `min(req, tracked_net, free×ratio)`；存量全平仅以 L2 封顶并打标；步长归一化向下取整；请求量为 0/负；部分成交后净额重算。
- 桩替代：交易所账户接口、DB 聚合均以注入桩返回；不触网、不读静默集。
- 展示口径：L2 total 不得被渲染为「系统持仓」字段。

### 1.8 剩余风险与未验证项

- **未验证**：各现货适配器（okx/binance/bitget/htx 等）free/locked 字段口径与锁单行为未在本切片精读；存量在挂单成交后的释放时点 unknown。
- **未验证**：账户原有存量的规模与占比未知；误卖存量的实际概率与影响未量化。
- **inferred**：现有 `qd_quick_trades` 聚合是否覆盖策略台账成交（`qd_strategy_trades`）尚未打通，L1 净额在混合入口下可能低估。
- **unknown**：前端是否已有「系统持仓 / 钱包余额」分开展示的契约；改动展示字段需前后端联合评审。

---

## 2. #154 三入口统一 pre-trade 风控闸

### 2.1 现状落点

| # | 现状结论 | 落点 | 分级 |
|---|---|---|---|
| G1 | 策略自动入口在下单前先做持仓归属闸 `evaluate_entry_position_guard`（归属漂移/反向腿校验）；`guard.error` 存在即 `mark_failed` 并通知、记策略日志后返回 | `backend_api_python/app/services/pending_order_worker.py:1790-1810` | confirmed |
| G2 | 随后做账户级风险快照 `account_risk_snapshot`；`allowed` 为假时取首条 violation 作为错误码 `mark_failed`；快照抛异常同样 `mark_failed`（fail-closed） | `pending_order_worker.py:1817-1854`（allowed 判定 :1838，mark_failed :1841；简报记 :1838 未 allowed 即 mark_failed，一致） | confirmed |
| G3 | 归属闸返回不可变结果 `EntryPositionGuardResult(ownership, error, log_level, log_message)`，worker 侧无额外副作用 | `backend_api_python/app/services/pending_orders/entry_position_guard.py:21-28,36-50` | confirmed |
| G4 | 账户风险快照返回 `{allowed, violations, long/short/gross/net notional, hedge_ratio, gross_leverage, margin/fee/funding estimate, capital_budget, symbol_gross, limits, ...}`；violation 码含 `positionPriceMissing / proposedPriceMissing / grossNotionalExceeded / marginEstimateExceeded / feeBudgetExceeded / fundingBudgetExceeded / grossLeverageExceeded / symbolGrossNotionalExceeded` | `backend_api_python/app/services/live_trading/account_risk.py:101-278`（violation :234-249） | confirmed |
| G5 | 风险限额来自策略 `trading_config.account_risk` JSON；未配置时回退到资金/杠杆容量与默认费用/资金费率比例（费用预算默认 5%、资金预算默认 2%） | `account_risk.py:217-229,281-284`；费率默认值 `:61-78` | confirmed（取值逻辑）；**inferred**（默认比例非 CLEAN 校准产物） |
| G6 | 手动/快捷成交入口 `POST /place-order`：前置检查仅为数量/最小名义额归一化、现货报价余额预检、合约保证金估算预检；读路径套 `RequestGuard` 限流缓存 | `quick_trade.py:323-326`（路由/函数）；现货余额预检 `:465-488`；合约保证金预检 `:499-519`；guard 缓存导入 `:54`、读路径 `:814-820` | confirmed |
| G7 | `quick_trade.py` 全文 grep `account_risk / entry_position_guard / evaluate_entry / risk_snapshot` **0 命中**：手动/快捷入口未复用账户级风险闸与归属漂移闸，三入口标准不一致 | `quick_trade.py` 全文件 | confirmed |
| G8 | 账户风险统计的持仓面来自 `qd_strategies_trading`；快捷成交流水写 `qd_quick_trades`（路由插入 `quick_trade.py:277`；worker 成交回写 `pending_order_worker.py:378-389`）。两套账本在风险汇总时是否合并，现状未打通 | `account_risk.py:81-90`；`quick_trade.py:277`；`pending_order_worker.py:378` | confirmed（落点）；**inferred**（合并口径设计） |
| G9 | 归属漂移容差 `dust_quote` 默认 1.0 USDT，夹在 [0, 5]；按参考价折算为数量容差 | `entry_position_guard.py:61-70` | confirmed（数值）；**inferred**（默认值未校准） |

### 2.2 第一性原理目标

- **同一笔风险，同一套判断**：无论策略自动、手动还是快捷成交，进入下单前经过的账户暴露/归属/价格完整性判断必须是同一组规则，禁止某一入口绕过。
- **决策可审计**：放行/拒绝都要能还原输入快照（现有持仓、提议订单、限额）、逐项判断结果、命中的原因码与审计元数据；拒绝信息可追溯到具体 violation。
- **失败倾向保守**：风险快照取不到、价格缺失、口径不明时 fail-closed，不把「查不到」当作「安全」。
- **因果单向**：闸口只能使用当前已收盘 bar、已拉取快照的数据；不得以成交后价格或后续成交回填闸口结论。

### 2.3 统一 pre-trade gate 纯函数签名建议（设计层，不落代码）

将 G1 归属闸与 G4 账户风险快照组合为一个**纯判断函数**：不持网络/DB 副作用，输入为已组装好的快照与订单意图，输出放行/拒绝 + 原因码 + 审计元数据；I/O 拉取（客户端、持仓、限额）由入口适配器在调用前完成并注入。

```
GateInput
  user_id, credential_id, exchange_id, market_type, symbol
  side: "long" | "short" | "buy" | "sell"
  order_intent: { quantity, price, leverage, order_type, source, close_scope? }
  account_snapshot: {
      open_positions: [...],        # 由适配器从账本/交易所快照组装
      capital_budget, existing_symbol_gross, ...
  }
  limits: account_risk policy dict # 来自配置/校准基线，函数内不读库
  context: { strategy_id?, run_id, caller_entry, snapshot_at, price_source }

GateResult (frozen)
  allowed: bool
  reason_codes: list[str]          # 复用 G4 violation 码 + 归属漂移码；空列表=放行
  checks: list[CheckRecord]         # 每项: {check_name, passed, input_refs, detail}
  audit: {
      run_id, caller_entry, snapshot_at, limits_version,
      account_refs, intent_hash, gate_version
  }
  ownership: dict                   # 透传 G1 归属结论（漂移量/保护量/共存模式）
  estimates: dict                  # 透传 G4 名义/保证金/费用/资金费估算
```

- **复用点**：判断规则直接复用 `account_risk_snapshot` 的估算与 violation 口径（G4）、`evaluate_entry_position_guard` 的归属结论（G3）；统一函数只做组合、归一化与审计封装，不复制限额公式。
- **原因码分层**：账户暴露类（gross/margin/fee/funding/leverage/symbol gross）、归属类（漂移/反向腿/共存模式）、数据完整性类（价格缺失/持仓缺价）；拒绝时返回首个阻断码 + 全部命中码清单。
- **纯函数边界**：闸口函数内不发起 REST、不写库；快照拉取、限额读取、结果落库由适配器完成，便于 core 单测注入桩。

#### 2.3.1 纯函数落点（已固化，#167；适配器接线未做）

- 模块：`core/execution/pretrade_gate.py`；单测 `tests/test_execution/test_pretrade_gate.py`（20 用例，定向通过）。
- `project_proposed(projection, proposed) -> (RiskProjection, proposed_price_missing)`：notional=qty×price；price_missing=qty>0 且 price≤0；short 入 `short_notional`，否则 `long_notional`；`symbol_gross` 累加；margin += notional/max(1.0, leverage)；fee += notional×fee_rate×2.0；funding += notional×funding_rate。
- `evaluate_risk_limits(projection, proposed, limits) -> RiskGateResult`：先并入提议增量再走公共限额判定；violation 码前缀 `accountRisk.`，含 `positionPriceMissing / proposedPriceMissing / grossNotionalExceeded / marginEstimateExceeded / feeBudgetExceeded / fundingBudgetExceeded / grossLeverageExceeded / symbolGrossNotionalExceeded`；比较容忍 `1e-8`；limit 字段 0 = 该约束不启用（限额回退默认在适配器侧完成，core 不做回退推断）；gross_leverage=gross/capital_budget（cap>0 否则 0）；hedge_ratio=min/max（max>0 否则 0）。
- `evaluate_projected_limits(projection, limits, *, proposed_symbol="", proposed_price_missing=False) -> RiskGateResult`：对**已含提议**的全量投影直接判定，不再二次并入提议；供适配器 shadow 对照——后端快照已把提议并入全量，直接喂全量投影即可逐条比对 violation 码，无需先拆分既有持仓与提议增量。
- `evaluate_pretrade_gate(*, ownership_allowed, ownership_error="", risk) -> PretradeGateResult`：allowed=归属通过且风险通过；fail-closed；audit 记 `ownership_allowed/risk_allowed/gross_notional/gross_leverage`。归属 unknown/不允许由调用方传 `ownership_allowed=False + error`。
- 边界：账户限额读取、持仓/报价快照组装、归属闸 DB/网络取数、结果落库留后端适配器（第二步，对应 §2.4 E1/E2/E3）；symbol 归一化（去 `-`、大写、补 `/`）属适配器职责，core 透传已归一 symbol。限额默认值非 CLEAN 校准产物（见 §2.7）。

### 2.4 三入口接线顺序与复用点

| 入口 | 现状 | 拟接线（评审后实施） | 复用点 |
|---|---|---|---|
| E1 策略自动（worker） | G1 + G2 已内联在 worker 流程 | 第一步 **shadow 对照**：后端快照取数/聚合/限额回退保持不变，把全量投影 + 回退后 limits 喂 `evaluate_projected_limits` 并行判定，violation 集合不一致记 warning 日志，**放行仍以后端现有判定为准**；对照一致后第二步再把限额判定替换为 core 输出，归属结论映射 `evaluate_pretrade_gate`；保持现有 `mark_failed` + 通知 + 策略日志收尾语义；归属结论与风险估算写入 `phases` 审计轨迹 | `EntryPositionGuardResult` 结构、`account_risk_snapshot` 估算/violation、worker 既有审计字段 `phases`、core `evaluate_projected_limits` |
| E2 手动成交（place_order, source=manual） | 仅余额/保证金预检（G6） | 下单前组装账户快照与意图 → 调统一 gate；拒绝按现有 400 错误映射返回；预检（最小名义额、余额估算）保留为前置 UX 检查，不替代风险闸 | 同一 gate 纯函数；余额预检结果作为 gate 输入之一，不重复实现限额判断 |
| E3 快捷/AI 成交（place_order, source=ai_radar/ai_analysis/indicator） | 同 E2，未接风险闸 | 同 E2；`source` 进入 `context.caller_entry` 与审计记录，便于事后区分哪类入口被拒 | 同 E2；策略归属闸仅在有 `strategy_id` 时参与，纯快捷单不强制归属校验，但账户暴露闸必须生效 |

**接线顺序（设计）**：① 先落统一 gate 纯函数 + 单测，E1 作为首个适配入口迁移（已有两段判断可对照回归）；② 再为 E2/E3 补快照组装适配器；③ 最后统一错误码与审计落库格式。禁止在纯函数未固化前改入口路由。

### 2.5 inferred / unknown 标注

- **inferred**：快捷成交流水（`qd_quick_trades`）是否应计入账户 gross/notional 暴露——若不计入，多入口同账户会出现风险汇总盲区；设计上建议 gate 的账户快照覆盖所有在跑入口的跟踪持仓，但合并口径需评审。
- **inferred**：手动/快捷单是否需要归属漂移闸（无 strategy_id 时归属边界如何定义）；建议账户暴露闸强制、归属闸按策略上下文可选。
- **unknown**：除 `quick_trade.py` 外是否存在其他绕开 worker 的下单路由（本切片未穷尽全仓路由检索）；其他券商适配器（alpaca/ibkr 等，worker :2424/:2595 附近有专属分支）的风险口径是否一致未核对。
- **unknown**：`trading_config.account_risk` 限额在生产中的实际配置值与来源；是否有历史校准记录未核对。

### 2.6 失败降级与可审计点

| 场景 | 降级行为 | 分级 |
|---|---|---|
| 账户快照/限额读取失败 | fail-closed：拒绝下单，错误归类 `snapshotFailed:*`，带 user/credential/symbol/时间戳上下文；不降级为「跳过风险检查」 | confirmed 倾向（沿用 G2 :1849-1854 现状）；接线为 inferred |
| 提议价格缺失 | 命中 `proposedPriceMissing` 拒绝；不得以 0 价估算名义额 | confirmed（G4 :235-236） |
| 归属快照异常 | 沿用 G1 失败路径拒绝；归属结论缺失时不进入共存模式放行 | inferred |
| 闸口审计落库失败 | 不阻塞拒绝/放行结论本身；审计写入失败需被监控发现并本地日志留痕（报告优先于告警，对齐对账草案 §7） | inferred |
| 可审计记录 | 每次闸口调用留存 `run_id`、入口来源、快照时间戳与引用、限额版本、意图哈希、逐项 CheckRecord、命中码、放行/拒绝结论 | 设计约束 |

### 2.7 阈值必须来自分布

- 账户限额（总名义、单品种 gross、保证金、费用预算、资金费预算、总杠杆）正式值须由 **CLEAN/历史分布**校准：以账户级利用率/占用分布的分位数（如 P95/P99）为基线，结合资金约束形成上限；基线冻结并版本留痕，禁止用实盘 PnL 网格搜索调参。
- 归属漂移容差（`dust_quote`）应来自 CLEAN 上成交价/滑点/报价波动分布，而非固定 1 USDT 占位；费用率/资金费率估算基线同样取自 CLEAN 分布。
- 限额配置与校准基线分两层存储：配置可覆盖的是「策略级参数」，分布校准的是「基线/默认上限」；两者来源在审计记录中区分。

### 2.8 单测计划

- 统一 gate 纯函数：逐项 violation 命中（gross/margin/fee/funding/leverage/symbol gross/价格缺失）；全部通过 → `allowed=True` 且原因码为空；多码同时命中时清单完整；`limits` 为空时走容量回退的口径一致。
- 归属组合：有 strategy_id 时归属结论透传进 `ownership`；漂移拒绝原因码与 G1 现状一致；无 strategy_id 时归属检查跳过但暴露闸仍生效。
- 降级注入：快照异常/价格缺失/空持仓各分支 fail-closed；审计元数据字段齐全、`intent_hash` 稳定。
- 入口适配器（桩）：E1/E2/E3 三条路径都调用同一 gate；E2/E3 不直接读库；错误映射不丢失原因码。
- 回归：现有 worker 风险拒绝用例（G2）迁移后断言不放宽；归属闸既有行为对照 `entry_position_guard` 现状。

### 2.9 剩余风险与未验证项

- **未验证**：未连接模拟/实盘账户，gate 在真实多策略、多腿、对冲账户下的估算准确性未跑过。
- **未验证**：`account_risk_snapshot` 现有估算（费用双边、资金费、保证金）与真实成交口径的偏差未对账；与 §3 周期对账结果可能互相印证。
- **unknown**：快捷流水并入账户暴露后，限额是否需要按入口分层（策略仓 vs 手动仓）；属产品风险政策决策，超出本设计切片。
- **inferred**：统一 gate 重构 E1 存在回归风险，须以现有 worker 测试与黄金集断言守住（硬规则 10）。

---

## 3. #155 三入口对账接线与告警出口

> 模块盘点（纯函数、容忍度、严重问题码、漂移统计、调度现状、降级矩阵、审计要求）见对账草案 §1.1/§1.2/§1.3/§7/§8，本文不重复；本节只补「三入口账本如何接入同一对账口径」与「告警出口如何落地」。

### 3.1 现状落点

| # | 现状结论 | 落点 | 分级 |
|---|---|---|---|
| R-1 | 对账纯函数 `reconcile()` 不做网络 I/O，输出 `ReconcileReport`；non-clean 经 `enforce()` 触发 KillSwitch；核心内 Engine 已封装调用 | 对账草案 R1、R7、R8；`core/execution/reconcile.py`、`core/execution/engine.py:393-401` | confirmed（沿用草案） |
| R-2 | 后端 app 内未发现对 `core.execution.reconcile` / `core.monitoring.drift_monitor` 的 import；缺周期对账接线 | 对账草案 R10、D11 | confirmed（沿用草案） |
| R-3 | 周期调度候选：Celery Beat 维护类任务（`maintenance.py`，env 开关 + backoff/jitter 重试）、按需持久化作业（`agent_jobs.py`，当前仅 `backtest`）、按需 AI 分析（`fast_analysis.py`）、非 Celery 长驻线程（`startup.py`）、worker 既有持仓同步循环 | 对账草案 S1–S8；任务文件 `backend_api_python/app/tasks/maintenance.py`、`agent_jobs.py`、`fast_analysis.py` 存在 | confirmed（沿用草案） |
| R-4 | 三入口对应的本地账本面：快捷/手动成交流水 `qd_quick_trades`（路由插入 `quick_trade.py:277`；worker 成交回写 `pending_order_worker.py:378-389`）；策略成交腿 `qd_strategy_trades`（`records.py:514`；worker :780/:826/:2836）；策略持仓/账户行 `qd_strategies_trading`（部署写入 `strategy_v2/deployment.py:184`；风险读取 `account_risk.py:90`） | 同左 | confirmed |
| R-5 | 进程内可观测单例 `ObservabilityService`：Metric/Alert/AlertRule/`_alert_callbacks` 回调注册；默认规则为 API 延迟/错误率/CPU/内存 | `backend_api_python/app/services/observability.py:83-147`（callbacks :98，record_metric :147） | confirmed（类与回调存在）；**unknown**（告警落库表、跨进程可见性，沿用草案 D12） |
| R-6 | 外部告警候选产物存在：`ops/prometheus/alerts.yml`、`ops/prometheus/prometheus.yml`、`ops/alertmanager.yml`、`ops/rules.yml`、`ops/alertmanager/alertmanager.yml` | `ops/` 目录 | confirmed（文件存在）；**unknown**（app 指标如何暴露到 Prometheus、规则是否已接入） |
| R-7 | 既有多条独立对账/同步链路（按需路由对账、worker 启动后/循环持仓同步、activity/funding/fee/ledger 对账），本切片不改其内部口径 | 对账草案 R11 | confirmed（存在性）；内部口径 unknown |

### 3.2 第一性原理目标

- **两套独立事实必须定期对齐**：本地账本（三入口成交/持仓）与交易所实际订单/持仓是两套事实；不一致时后续决策都建立在错误状态上（对账草案 §0 第一性原理）。
- **口径复用，不复制逻辑**：周期对账必须复用 `core.execution.reconcile` 同一比对口径与容忍度；三入口账本映射到统一的 `OrderView/PositionView`，不各写一套比对。
- **报告先于告警**：对账结果先落审计记录，再推告警；告警通道不可用不阻塞对账主流程。
- **可审计**：每轮留存两侧快照标识、时间戳、口径/容忍度版本、差异码、结论与调用来源。

### 3.3 三入口对账接线设计（评审后实施，不落代码）

**账本 → 对账视图映射（设计层）**：

| 入口 | 本地账本面 | 映射到对账视图 | 交易所侧取数 |
|---|---|---|---|
| E1 策略自动 | `qd_strategies_trading`（持仓/账户行）+ `qd_strategy_trades`（成交腿）+ worker 回写的 `qd_quick_trades` | 持仓按 symbol/side → `PositionView`；订单按交易所订单 id → `OrderView` | 复用既有持仓/订单快照拉取（worker 同步链路 R-7），不另起一份拉取 |
| E2 手动成交 | `qd_quick_trades`（source=manual） | 成交记录 → `OrderView`；净持仓 → `PositionView`（与 §1 两层口径对齐） | 同上，按 credential+symbol 拉取 |
| E3 快捷/AI 成交 | `qd_quick_trades`（source=ai_radar/ai_analysis/indicator）+ 平仓腿记录 | 同 E2 | 同上 |

**接线顺序**：① 定义账本行 → `OrderView/PositionView` 的归一化映射（纯函数，含侧别归一化，沿用草案 R5）；② 对账任务组装两侧快照后调 `reconcile()`，non-clean 走既有 `enforce()`/KillSwitch 路径（R-1）；③ 结果写审计记录并接告警出口（§3.4）；④ 与既有按需对账/同步链路对齐口径，避免双重状态（草案 §6.5）。

**边界**：周期对账不自动补单/平仓/改仓位；差异只报告并触发既有保护链路，处置走人工或既有授权流程（草案 §2.2）。

#### 3.3.1 纯函数落点（已固化，#169；适配器接线未做）

- 模块：`core/execution/reconcile.py` 新增 `aggregate_fills_to_positions(fills, *, flat_net=1e-12) -> FillAggregation`；单测 `tests/test_execution/test_reconcile.py`（59 用例，定向通过；#325 补视图/净聚合数量有限性守卫后纳入基线）。
- 净额 `net = Σbuy qty − Σsell qty`；`net > flat_net` → buy，`net < -flat_net` → sell `|net|`；净额在 `[-flat_net, flat_net]` 内视为已平仓，不产出持仓。
- 缺 `symbol` / 侧别无法归一 / 数量非正 / 数量非法的行进 `dropped`（带索引与原因码 `missing_symbol / missing_side / nonpositive_quantity / invalid_quantity`），不静默跳过；缺失行由适配器归入对账 mismatch/unknown。
- 边界：列名别名映射（lots/direction 等）、成交腿 → 订单视图、两侧快照拉取、周期任务调度与告警出口留后端适配器（第二步，对应 §3.3 接线顺序 ②③④）；`entry_price` 不在聚合层推断（无 VWAP 口径），加权成本由需要的适配器自行计算。`flat_net=1e-12` 为占位阈值，正式容忍度走 §3.6 分布校准。#325 起视图工厂 `quantity/filled_quantity/entry_price` 非有限或负值抛 ValueError，净聚合非有限数量归入 dropped `invalid_quantity`；持仓负数量不再 `abs()` 取正，方向由 side 表达。

### 3.4 告警出口设计

- **出口分层**：
  1. **审计记录（主）**：对账报告/差异码/快照引用先落本地审计存储（存储位置与保留周期后续评审，不触碰 `ledger/` 既有数据）。
  2. **进程内告警（短链路）**：经 `ObservabilityService` 回调发出，严重度映射复用 `AlertSeverity`；告警内容引用报告 `run_id`，不重复搬运全量快照。
  3. **外部通道（候选）**：对账/漂移指标暴露到 `ops/prometheus` 既有规则体系，经 `alertmanager.yml` 路由通知；接入方式与指标命名属后续评审。
- **非阻塞原则**：回调/上送失败进入重试或死信候选，不回滚对账结论；进程内单例为内存结构，重启后历史告警可见性 unknown，审计留痕不能仅依赖该单例（草案 §9.2-6）。
- **分级倾向**：对账 non-clean 倾向 fail-closed 并经既有 KillSwitch 路径；漂移告警仅输出建议与健康分，不直接切断交易（草案 §6.6）。

### 3.5 失败降级与可审计点

| 场景 | 降级行为 | 分级 |
|---|---|---|
| 交易所快照拉取失败（网络/超时/鉴权） | 本轮标记「对账未完成」，不产出 clean 结论；退避重试；连续失败达占位阈值后上报告警；fail-closed 倾向 | 沿用草案 §7；连续失败阈值 inferred（待校准） |
| 本地账本读取失败 | 本轮不判定；异常带策略/账本标识上下文 | 沿用草案 §7 |
| 告警通道/持久化不可用 | 审计报告先落本地；告警上送失败可重试；不阻塞对账 | inferred（沿用草案 §7） |
| 两侧快照时间差 | 报告标注两侧快照时间戳；时间差超占位容差时标记「快照不同步」，不作为一致结论 | inferred |
| 可审计记录 | `run_id`、调用方/入口、策略与品种、venue、两侧快照时间戳、口径与容忍度版本、差异码/严重度、结论、失败归类；阈值/基线记录来源（数据集、区间、版本、校准方式） | 沿用草案 §8 |

### 3.6 阈值必须来自分布

- 对账数量容忍度现状为固定绝对 `1e-6` / 相对 `1e-4`（草案 R3）；正式容忍度与「快照不同步」时间差阈值，应由 CLEAN/KNOWN 上的成交残差、手续费侵蚀、报价抖动分布校准（分位数/基线），不照搬固定值。
- 连续失败告警次数、漂移告警切点等占位阈值，按草案 §5 与 §4.4 走分布校准路径；禁止用绩效网格搜索产生。
- 基线冻结与版本留痕：防止周期任务误用近期表现刷新基线导致漂移感知钝化（草案 §9.2-3）。

### 3.7 单测计划

- 账本映射纯函数：三入口账本行 → `OrderView/PositionView`；侧别归一化；重复 id / 缺失侧 / 缺字段归入 mismatch/unknown，不静默跳过。
- 对账编排（桩）：两侧快照注入；non-clean 触发 `enforce` 调用（桩捕获 KillSwitch reason/metadata）；clean 不触发；快照时间戳与口径版本写入报告。
- 告警出口：回调抛异常时对账主流程不中断；告警内容携带 `run_id`；审计记录先于告警写入。
- 降级：快照拉取异常、账本读取异常、样本不足各分支返回对应「未完成/不足」标记，不误判为 clean 或漂移。

### 3.8 剩余风险与未验证项

- **未验证**：未连接任何实盘/模拟交易所跑真实快照比对；多适配器成交回报、部分成交、手续费口径差异 unknown（沿用草案 §9.1）。
- **未验证**：容器内调度拓扑（Beat/worker/API 进程角色）未读 `docker-compose*.yml`；新周期任务在容器内可达性 unknown。
- **unknown**：告警落库表、通知渠道（站内/邮件/webhook）；app 到 Prometheus 的指标暴露链路未核对。
- **风险**：后端已存在多条对账/同步链路（R-7），新周期任务若不复用既有拉取与口径，会产生双重状态与不一致结论。

---

## 4. #156 策略/模型注册中心接入

### 4.1 现状落点

| # | 现状结论 | 落点 | 分级 |
|---|---|---|---|
| M1 | 路由层内置 **3 个演示策略**并注释标注「内置演示策略注册（3 个）」；`build_demo_router()` 构造演示路由 | `core/registry/strategy_router.py:158-160` | confirmed |
| M2 | 三个演示条目：`demo_breakout`（实现 `core.backtest.engine:DemoBreakoutStrategy`）、`ml_trend_meta`（实现 `core.models.ml_trend_strategy:MLTrendStrategy`）、`demo_mean_reversion`（**路由占位，尚无完整策略类**，`implementation_ref` 标注未实现） | `strategy_router.py:171-239`（desc :190/:217/:238） | confirmed |
| M3 | 策略注册中心 `StrategyRegistry`：`register(StrategyVersion)`；`StrategyVersion` 含 strategy_id/version/parameters/状态机/性能快照/冻结标记；状态流转 DRAFT→BACKTEST→PAPER→LIVE/PAUSED/RETIRED，进 BACKTEST 自动冻结参数 | `core/registry/strategy_registry.py:68-157,159-182` | confirmed |
| M4 | 模型注册中心 `ModelRegistry`：`register/get/get_latest/get_production`；`ModelVersion` 含 model_id/version/feature_versions/label_spec/data_range/seed/code_commit/hyperparams/metrics/artifact_uri/checksum/stage；阶段状态机 CANDIDATE→STAGED→…，进 STAGED 自动冻结 | `core/registry/model_registry.py:62-101,165-190` | confirmed |
| M5 | 匹配器纯函数 `match_strategies(strategies: list[StrategyProfile], market, current)`，按 regime 画像打分排序；输入 Profile 列表，不自带数据源 | `core/registry/strategy_matcher.py:247-252` | confirmed |
| M6 | 后端 app 全仓 grep `core.registry / StrategyRegistry / ModelRegistry / strategy_registry / model_registry` **0 命中**：后端未接入 core 注册中心 | `backend_api_python/app` | confirmed |
| M7 | 后端策略部署写 `qd_strategies_trading`，元数据以 `exchange_config`/`trading_config` JSON 落库；未见与 core `StrategyVersion`/`ModelVersion` 的 id+version 关联 | `strategy_v2/deployment.py:151-195`（INSERT :184） | confirmed（落点）；**inferred**（缺版本关联设计） |
| M8 | 简报提及 `core/models/registry.py`；实测 **该文件不存在**：模型注册中心实际为 `core/registry/model_registry.py`；`core/models/` 下无 registry 模块 | `core/models/` 目录；`core/registry/model_registry.py` | confirmed（路径修正） |
| M9 | `build_demo_router` 在生产代码中除定义与 `__init__` 导出外，仅被测试 `tests/test_strategy_registry.py:31` 引用；本切片 grep 未发现 core/后端生产调用点 | `core/registry/__init__.py:11-12,29`；`tests/test_strategy_registry.py:30-31` | confirmed（检索范围）；**unknown**（是否存在动态加载/反射调用未穷尽） |

### 4.2 第一性原理目标

- **可审计的策略身份**：进入实盘的策略/模型必须有可追溯的 id、版本、冻结参数、制品校验和与状态；演示占位不得被当作可交易实现。
- **参数冻结单向**：参数一旦冻结（进入回测及以后）不可修改；部署时校验线上参数与注册快照一致，防止线上漂移（对齐 `StrategyVersion` 不变量，`strategy_registry.py:71-87`）。
- **因果单向 / 集合分离**：注册中心记录的性能快照来自 CLEAN 集上的回测/评估；不以实盘近期表现回写注册基线；静默集数据禁止进入注册评估。
- **注册中心是元数据事实源**：匹配/部署从注册中心读取策略画像与模型版本，而非硬编码列表；注册缺失或版本非法时拒绝部署，不回退到演示条目。

### 4.3 拟落地的最小改动方案（评审后实施，不落代码）

- **复用**：`StrategyRegistry`/`ModelRegistry` 的注册、版本查找、状态机与冻结校验；`match_strategies` 的打分排序；`StrategyDescriptor` 的 regime 画像/品种/参数/止损类型/实现引用结构。
- **拟新增映射（设计层）**：
  - 部署/启动时按 `(strategy_id, version)` 从 `StrategyRegistry` 解析元数据，按 `(model_id, version)` 从 `ModelRegistry` 解析制品与校验和；校验状态允许进入目标阶段、参数冻结、参数哈希与线上配置一致。
  - 后端 `qd_strategies_trading` 记录追加策略版本引用与模型版本引用（id+version+制品校验和），作为审计关联键；不改动既有 JSON 配置语义，只做引用记录。
  - 匹配器输入 `StrategyProfile` 列表由注册中心产出，替代 `build_demo_router` 的硬编码演示列表；演示路由仅保留为 pipeline 自检/测试夹具。
- **接线顺序**：① 固化注册中心读取与校验纯函数（版本查找、冻结/状态/哈希校验）；② 部署链路接入校验并留痕版本引用；③ 匹配数据源切换到注册中心；④ 演示条目从生产路由摘除（摘除动作属后续评审，不在本切片执行）。
- **边界**：不改 `deployment.py` 运行时逻辑（本切片只读）；不新增策略/模型训练流程；不把注册中心当成风控阈值来源（阈值仍走 §2.7/§3.6 分布校准）。

#### 4.3.1 纯函数落点（已固化，#168；适配器接线未做）

- 模块：`core/registry/deployment_guard.py`；单测 `tests/test_registry/test_deployment_guard.py`（14 用例，定向通过；全量 838 passed 纳入基线）。
- `check_strategy_deployment(version: StrategyVersion, target_env: str) -> DeploymentResult`：环境允许表 `paper={PAPER, LIVE}`、`live={LIVE}`；原因码 `unknown_environment / retired / paused / status_not_eligible / parameters_not_frozen`；audit 记 strategy_id/version/status/frozen/env。
- `check_model_deployment(version: ModelVersion, target_env: str, expected_checksum=None) -> DeploymentResult`：`paper={STAGED, PRODUCTION}`、`live={PRODUCTION}`；原因码 `unknown_environment / retired / stage_not_eligible / snapshot_not_frozen / checksum_mismatch`；提供 `expected_checksum` 时比对 `artifact_checksum`（strip 后不等或为空即 mismatch），无期望校验和则跳过。
- 边界：注册中心读取、版本引用落库（id+version+checksum）、匹配数据源切换与演示条目生产摘除留后端适配器（第二步，对应 §4.3 接线顺序 ②③④）；注册中心当前为进程内内存结构，持久化与多进程一致性方案未设计（见 §4.7）。

### 4.4 失败降级与可审计点

| 场景 | 降级行为 | 分级 |
|---|---|---|
| 注册中心查无此版本 / 版本已退役 | 拒绝部署或拒绝上线该策略；错误带 strategy_id/version/当前状态；不回退到同名最新版或演示条目 | inferred（基于状态机语义 M3） |
| 参数哈希不一致 / 未冻结 | 拒绝上线；记录线上配置哈希 vs 注册快照哈希；差异进入审计 | inferred |
| 模型制品缺失或校验和不符 | 拒绝加载模型；记录 artifact_uri/checksum 比对结果 | inferred |
| 注册中心不可用（内存/存储） | 上线路径 fail-closed；已有在跑策略不因注册中心临时不可用被自动平仓（观测/元数据面故障与交易保护面分离） | inferred |
| 可审计记录 | 策略/模型 id+version、状态转换记录、冻结时间、参数快照哈希、制品校验和、性能快照引用、部署人/调用来源、校验结论 | 设计约束 |

### 4.5 阈值必须来自分布

- 注册中心的性能准入（如 deflated Sharpe、PBO、胜率/回撤门槛）属于评估标准，须由 CLEAN 集回测/评估分布校准（分位数/基线），并记录评估数据集区间与版本；禁止以实盘 PnL 表现网格搜索准入线。
- `PerformanceSnapshot` / `metrics` 只记录评估结果，不在注册中心内反推交易限额；交易限额仍归 §2.7。
- 状态机转换与冻结规则是结构约束，不依赖绩效数值。

### 4.6 单测计划

- 注册解析纯函数：按 id+version 命中；最新版/生产版选取；未注册/已退役版本拒绝；非法状态转换拒绝；冻结后参数修改被拒。
- 部署校验：参数哈希一致放行；不一致拒绝并记录双方哈希；模型校验和不符拒绝；制品缺失拒绝。
- 匹配数据源：注册中心产出的 Profile 经 `match_strategies` 排序；演示夹具与生产数据隔离；注册为空时匹配结果为空且不抛伪排序。
- 桩替代：注册存储、模型制品加载均注入桩；不触网、不读静默集。

### 4.7 剩余风险与未验证项

- **未验证**：后端策略清单/详情接口当前使用哪些字段、是否已有模型版本引用位；前端展示契约未核对。
- **unknown**：`strategy_v2` manifest 的构建来源与字段（`driving_frequency` 等）是否已携带策略/模型版本信息；`deployment.py` 内部映射细节本切片未精读。
- **unknown**：core 注册中心当前为进程内内存结构（`StrategyRegistry`/`ModelRegistry` 实例化见测试），其持久化与多进程一致性方案未设计。
- **inferred**：`demo_mean_reversion` 占位条目若被生产链路误引用，会产生「有画像、无实现」的幽灵策略；摘除前需在匹配/部署校验中显式拒绝 `implementation_ref` 未实现的条目。

---

## 5. 本轮只读勘察清单与未验证项汇总

### 5.1 本切片只读勘察的文件（未修改任何实现代码）

- `backend_api_python/app/routes/quick_trade.py`
- `backend_api_python/app/routes/agent_v1/quick_trade.py`（grep 核对，无相关符号）
- `backend_api_python/app/services/live_trading/spot_sizing.py`
- `backend_api_python/app/services/live_trading/account_risk.py`
- `backend_api_python/app/services/pending_order_worker.py`
- `backend_api_python/app/services/pending_orders/entry_position_guard.py`
- `backend_api_python/app/services/live_trading/records.py`（仅落点核对 :514）
- `backend_api_python/app/services/strategy_v2/deployment.py`（只读 :151-195，未改）
- `backend_api_python/app/services/observability.py`
- `backend_api_python/app/tasks/maintenance.py`、`agent_jobs.py`、`fast_analysis.py`（存在性与草案结论核对）
- `core/execution/reconcile.py`、`core/execution/engine.py`（草案结论核对）
- `core/registry/strategy_router.py`、`strategy_registry.py`、`strategy_matcher.py`、`model_registry.py`、`__init__.py`
- `core/data/splits.py`（集合分离语义核对）
- `docs/design/reconciliation_drift_alarm_design.md`（引用，未改）
- `ops/prometheus/alerts.yml`、`ops/prometheus/prometheus.yml`、`ops/alertmanager.yml`、`ops/rules.yml`（存在性核对）

### 5.2 未验证项清单（显式标注）

| # | 项 | 状态 |
|---|---|---|
| U1 | 实盘/模拟对账冒烟、真实快照比对 | 未验证 |
| U2 | 多交易所适配器订单/持仓/成交/手续费/部分成交口径差异 | 未验证 / unknown |
| U3 | 容器内调度拓扑与新周期任务可达性 | 未验证 |
| U4 | 告警落库表、通知渠道、app→Prometheus 指标暴露链路 | unknown |
| U5 | 后端既有对账/同步链路内部比对规则 | 未验证（仅核对存在性与调用点） |
| U6 | 手动/快捷入口之外是否存在其他下单路由 | unknown（未穷尽全仓路由检索） |
| U7 | 注册中心持久化与多进程一致性、后端 manifest 版本字段 | unknown |
| U8 | 研究层全量 `pytest -q` 基线 2297 passed（#325 后，exit 0）；后端全量存在隔离性失败（测试顺序/共享状态污染，失败文件单跑通过）；未运行任何实盘 I/O | 研究层已验证 / 后端隔离失败 / 实盘未验证 |

### 5.3 路径/行号勘误记录

- 简报 `quick_trade.py:1387 _quick_trade_net_base_qty`：实际函数定义 `:1379`，docstring 在 `:1387`。
- 简报 `pending_order_worker.py:1838 未 allowed 即 mark_failed`：allowed 判定 `:1838`，`mark_failed` 调用 `:1841`。
- 简报 `core/models/registry.py`：不存在；模型注册中心为 `core/registry/model_registry.py`。
- 现货平仓 `clamp_spot_close_quantity` 落点 `spot_sizing.py:395`，free 取数 `:411`，与简报一致。

### 5.4 后续评审清单（不属本轮实现）

- [ ] §1 现货两层口径与存量保护的产品语义确认（tracked 平仓 vs 存量全平的入口契约）。
- [ ] §2 统一 gate 纯函数接口冻结、三入口适配器迁移顺序与账户暴露合并口径。
- [ ] §3 周期对账任务的触发周期、队列归属、env 开关；告警持久化与外部通道接入方式。
- [ ] §4 注册中心持久化方案、后端版本引用落库字段、演示条目生产摘除计划。
- [ ] 各节阈值经 CLEAN 分布校准后替换占位值，并在审计记录中区分占位/已校准。
