# QuantDinger Pro 待办清单

> 最后更新：2026-11-08
> 状态：所有未完成事项、临时方案、技术债全部列入，必须逐个清零
> 原则：不虚报进度，每一项都标注真实状态

---

## ✅ 最近完成（2026-10-28）

- ✅ 策略生命周期健康度评估模块（三级状态+自动退役逻辑）
- ✅ OKX下单方法优化（错误码识别+市价单USDT金额+client order id）
- ✅ 前端真实K线加载函数（fetchRealKline，每30秒刷新）
- ✅ Docker容器恢复（用官方镜像，HTTP 200正常）
- ✅ RULES.md新增4条Docker运维铁律

## ✅ 最近完成（2026-10-31）

- ✅ **自建系统独立化主体**：自建后端容器 qdpro-backend（:5001，本地全量代码 docker cp）跑通；自建前端 :8899 反代切换至自建后端；登录/行情/K线/策略/持仓模块 Chrome 复测控制台 **0 错误**
- ✅ 认证 token 问题落定：前端 dev-token 假登录 → 真实自动登录 admin/admin123（后端真实鉴权 SKIP_AUTH 未开）
- ✅ risk 前端路径对齐：/api/risk/dashboard（后端不存在）→ /api/risk/portfolio（真实 success 结构）
- ✅ credentials 数据结构适配：data 为 {items:[...]} 对象，前端取 data.items
- ✅ 镜像旧代码缺 account.py 误判"前端路径错"纠正（见 ERROR_LOG E009）

---

## 🔴 P0 优先级（阻塞实盘，必须最先完成）

### 1. OKX 对接全链路（demo 当实盘推进）🔄 部分闭环
> **2026-11-12 复核**：本条原为 10-31 旧快照，已按 #199/#202/#295/#297/#298/#299/#300 提交回填；现货链路已闭环，剩余阻塞见下。凭证为 demo（env=demo，id=2，OKX-DEMO），非 live。

- **已闭环（现货 / demo）**：
  - ✅ 前端 API 账户设置弹窗（Key/Secret/Passphrase）；凭证列表收口到 `GET /credentials/list` 真实回填（#199/#295 相关）
  - ✅ 后端 OKX 客户端；连接测试 / 余额 / 实时 ticker 通（历史快照余额 $98,340.28，2026-10-31）
  - ✅ 现货真实成交：recent_trades 返回 4 笔真实 OKX BTC 现货成交并上屏（#199）；demo 现货小额往返冒烟闭环、连字符 symbol 归一化（#298/#299/#300）
  - ✅ 持仓口径对齐凭证库主链，排除余额现金误列（#295）；quick-trade 行情缺失时数量换算返回 0 走下游拒单，避免 USDT 金额误当 base 数量（#297）
  - ✅ 只读 GET 有限退避 / POST 下单撤单不重试 / 错误码分流（#202/#203）
  - ✅ 认证 token：dev-token 假登录 → 真实自动登录，401 循环登出消除（E009）；本地网络访问 OKX 被拒已解除（E007）
- **剩余阻塞 / 未验证**：
  - ⏳ **永续（swap）开仓**：demo 简单账户 `acctLv=1`，`account_configuration.py:137` fail-closed 抛 `OKX_SWAP_ACCOUNT_MODE_REQUIRED`；现货可成交。解阻塞需在 demo 切保证金账户模式，或策略只跑现货——账户模式决策待拍板
  - ⏳ **V2 合约层**：历史版本脚本 manifest 仍是 sp500 池，候选按 manifest 解析；3 条 crypto 快照要真实成交需重编译脚本版本（合约层改动，停止条件待确认）
  - ⏳ **fills→`qd_strategy_trades` 账本归集 + 周期对账**：触实盘账本路径，待拍板（#155/#108）
  - ⏳ **容器镜像**：常驻后端进程/镜像未含 #295/#297/#299/#300 改动；HTTP 网关带登录态端到端下单未在容器复验
  - ⏳ **总权益字段**：`/account/positions` 后端未返回 `total_equity/equity`，前端总权益仍演示值（#64/#97）
  - ⏳ 历史 K 线接入图表：框架已搭，容器恢复后需部署复测
- **验收标准**：能真实下单、真实平仓、真实查持仓、真实查余额、真实 K 线渲染
- **安全约束**：先用最小手数测试，确认没问题再加大；不承诺盈利，须过蓝图 §7 门禁方可影子→小资金→全量灰度

### 2. 策略生命周期自动退役逻辑 ⏳ 待做
- **现状**：前端三级健康度面板已做，后端自动退役逻辑未实现
- **需要**：触发阈值自动停掉策略+发通知+记录原因
- **验收标准**：策略失效时能自动发现、自动预警、自动减仓

### 3. 五层市场识别接入真实K线数据 ⏳ 待做
- **现状**：L1/L2/L3/L4/L5市场识别用的是演示数据
- **需要**：接OKX真实K线数据，转换成特征，喂给L1-L5检测器
- **验收标准**：市场状态识别是基于真实行情的，不是假数据

### 4. GitHub推送修复 ⏳ 进行中
- **现状**：Gitee已同步，GitHub连接被重置（curl 28）
- **方案**：网络恢复后重试，或配置代理

---

## 🟡 P1 优先级（核心功能，决定能赚多少）

### 5. 策略匹配引擎接入真实策略 ⏳ 待做
- **现状**：只有3个硬编码的演示策略
- **需要**：把系统里现有的真实策略注册进去
- **验收标准**：策略池里有≥5个真实策略，不同市场状态下自动分配不同权重

### 6. 五层市场识别ML增强版 ⏳ 待做
- **现状**：规则版已完成（L1-L5）
- **需要**：ML模型增强识别准确率

### 7. 因子库扩展到20+因子 ⏳ 待做
- **现状**：当前只有10个基础因子
- **需要**：更多弱信号因子（文艺复兴模式：海量弱信号叠加）

### 8. 过拟合防御三重验证算法实现 ⏳ 待做
- **现状**：框架已建
- **需要**：PBO/CPCV/Deflated Sharpe具体算法实现

---

## 🟢 P2 优先级（企业级，决定能走多远）

### 9. P2模块前端可视化 ⏳ 待做
后端API都有了，前端面板还没加：
- [ ] 高可用与灾备面板
- [ ] 可观测性与告警面板
- [ ] CI/CD与部署状态面板
- [ ] 交易日志归因面板
- [ ] 安全与合规面板
- [ ] 策略拥挤度监控面板

---

## ✅ 已完成（最近更新，按时间倒序）

### #314 退役联合裁决纯编排接缝与单测 ✅ 已完成
- **完成时间**：2026-11-12
- **内容**：`core/experiment/retirement_arbitration.py` 新增 `arbitrate_retirement(*, health_score, health_threshold, lifecycle_recommendation=None, lifecycle_reasons=None, health_warn_line=None)`：合并健康分阈值线与 lifecycle `recommend_retirement` 建议，输出 `RetirementArbitration`（decision=retire/watch/keep、合并原因码、健康分/阈值/观察带、lifecycle 建议、审计 flags）。判定：retire=健康分低于硬阈值或 lifecycle retire；watch=健康分落在观察带 `[threshold, warn_line)` 或 lifecycle watch；其余 keep；retire 优先于 watch；原因码去重保序。纯函数无 IO/不读 DB/不下单；阈值全部入参，模块不写业务默认；鸭子类型解耦（只接收建议串与原因码序列，不 import `RetirementRecommendation`）；模块不反向依赖 registry，无循环耦合。退役状态机迁移仍由编排层调 `retire_if_health_below` 落地。单测 20 例（keep/双 retire 路径/观察带 watch/lifecycle watch/优先级/原因码去重/to_dict/守卫参数化）。experiment+registry+audit 501 passed 无回归。
- **剩余风险/未验证**：① 联合裁决尚未在编排进程/后端接线（纯接缝已就位）；② 硬门禁否决（DSR>0/PBO/交易数下限）未并入本裁决，另走上线门禁；③ 观察带/硬阈值未做 CLEAN 分布校准，入 `configs/` 需人审；④ 未触 configs/registry.yaml/mt5/风控阈值常量/密钥/实盘资金路径。

### #313 S4 保本/时间止损口径逐行核对回填 ✅ 已完成
- **完成时间**：2026-11-12
- **内容**：只读逐行核对 `core/risk/stops.py` 与后端 V2 `strategy_v2/protection.py`。保本：core 1.0R 激活 + `offset_r×entry_dist` 偏移；risk_engine 0.5R 激活 + 价格百分比 buffer；V2 无保本能力（缺口非分歧）。时间止损：core `bars_held≥max_holding_bars 且 max_favorable_r<breakeven_r` 双门控；V2 纯墙钟秒数到即平。分裂点回填 `protection-layers-reconciliation.md` S4；risk_engine 时间止损仍未逐行核，列未验证。未改后端、未动阈值常量。

### #312 快照健康分合成纯函数桥接与单测 ✅ 已完成
- **完成时间**：2026-11-12
- **内容**：`core/audit/evolution_rules.py` 新增 `health_score_from_snapshot(snapshot)`：鸭子类型取 `win_rate`(0-1 转百分比)/`profit_factor`/`avg_r_multiple`，复用既有 `score_health` 口径，输出 `score/100` ∈ [0,1] 归一化健康分，供 `retire_if_health_below` 调用。鸭子类型取属性避免 audit→registry 循环耦合；守卫 win_rate∈[0,1]、PF 非负、三项有限。硬门禁否决（DSR>0/PBO/交易数下限）不在连续评分内，另走 lifecycle `recommend_retirement`；不读 DB、不反推阈值。`core/audit/__init__.py` 导出。单测 5 例（高/低/归一化区间/胜率百分比换算/守卫×6 参数化）。audit+registry+strategies 430 passed 无回归。
- **剩余风险/未验证**：① 评分档位阈值（55/50/45 胜率、1.5/1.3/1.1 PF、1.5/1.0/0.5 R）为既有占位默认，未做 CLEAN 分布校准；② 健康分与 lifecycle 退役建议的联合裁决尚未在编排层串联；③ 未触 configs/registry.yaml/mt5/风控阈值常量/密钥/实盘资金路径。

### #311 注册表健康度退役裁决纯方法与单测 ✅ 已完成
- **完成时间**：2026-11-12
- **内容**：`core/registry/strategy_registry.py` 新增 `StrategyRegistry.retire_if_health_below(strategy_id, version, *, health_score, threshold, reason="")`：健康分 `< threshold` 且状态可退役时走状态机迁移到 RETIRED，写 `retirement_log` 审计快照（id/version/from→to/score/threshold/reason/时间戳）。守卫：score/threshold 有限且 ∈[0,1]、策略已注册、仅 BACKTEST/PAPER/PAUSED/LIVE 可退役、RETIRED 终态不重复记日志。健康分由上游 RES/门禁底座按分布与蓝图准则传入，注册表不自行从绩效快照合成，避免绩效网格搜索入注册层；通知/回调由编排层读日志触发，本方法不下单不写库。单测 7 例（触发退役/达标不退役/未注册 fail-closed/DRAFT 不可退役/终态不重复记日志/区间有限性守卫×6 参数化）。`test_registry` 185 passed；strategies+registry 252 passed 无回归。
- **剩余风险/未验证**：① 健康分合成口径（多指标/红灯期数）尚未在 core 落地，复用 G9 红灯持续性底座另轮；② 后端退役通知/回调接线未做；③ 退役阈值未做 CLEAN 分布校准，入 `configs/` 需人审；④ 未触 configs/registry.yaml/mt5/风控阈值常量/密钥/实盘资金路径。

### #310 四套保护层口径对照清单（只读）✅ 对照完成，接线待门
- **完成时间**：2026-11-12
- **内容**：只读勘察 core `risk/protection`、后端 `risk_engine`、`strategy_v2/protection`、`live_trading/native_protection` 四套保护层，产出 `docs/design/protection-layers-reconciliation.md`。结论：core↔risk_engine 在吊灯/分批/回吐/止损单调上已对齐；登记 5 个分裂/缺口——S1 分批单 bar 一档 vs 后端多档、S2 risk_engine 阈值硬编码默认值（2R/3R、3ATR、30%、1R 激活，未走分布校准）、S3 百分比↔ATR/R 基准分裂、S4 保本缓冲口径待核、S5 core 底座后端运行时未激活（#209）。待决策门 D1-D5 单列，ORCH 不擅改阈值/configs/接线。
- **剩余风险/未验证**：后端容器是否含当前 core 底座未验证；实盘/经纪商原生单语义未验证；V2 与 core `stops` 保本/时间止损逐行一致性未核对；本轮未改后端、未动阈值常量、未触红线。

### #309 Matcher×WeightRouter 子集路由集成纯函数与单测 ✅ 已完成
- **完成时间**：2026-11-12
- **内容**：`core/registry/strategy_router.py` 新增 `StrategyWeightRouter.route_subset(selected_names, regime)` 与便捷函数 `route_selected`——对 Matcher 选出的 top-N 策略子集在白名单内按 regime_profile 归一化，子集外策略归零（不出现）；守卫：regime 合法、入选名必须在白名单（策略池不同步 fail-closed，不静默忽略）、子集在该 regime 权重全 0 抛错不静默全 0、名单去重保序。`registry/__init__` 导出 `route_selected`。单测 6 例（子集归一化/排除未入选/未知名 fail-closed/未知 regime/全 0 抛错/去重与便捷函数等价）。`test_strategy_registry` 28 passed；strategies+registry 213 passed 无回归。
- **剩余风险/未验证**：① Matcher `MarketRegime` 枚举（trending/ranging）与 Router `SUPPORTED_REGIMES`（trend/range/volatile/quiet）口径未对齐，端到端 select→subset 串联留后续切片；② Profile↔Descriptor 同名策略池同步机制未建；③ 权重数值仍为定性默认，未做 CLEAN 分布校准（P1-4）；④ 未触 configs/registry.yaml/mt5/密钥/实盘资金路径。

### #308 回填 OKX/均值回归过期口径并挂接路由占位 ✅ 已完成
- **完成时间**：2026-11-12
- **内容**：修正 TODO 事实源分裂——顶部 P0/T5/P0-2/P1-3 仍为 10-31 旧快照，已按 #199/#202/#295/#297/#298/#299/#300 提交回填：现货 demo 链路闭环（凭证/余额/行情/现货往返冒烟/持仓口径/数量换算/symbol 归一化/只读重试分流），剩余阻塞如实标注（永续 acctLv=1 fail-closed、V2 合约 manifest、fills 账本归集、容器镜像未含新改动、总权益字段缺失）。代码侧：`core/registry/strategy_router.py` 的 `demo_mean_reversion` 占位条目 `implementation_ref` 从「(未实现)」改为 `core.strategies.mean_reversion:MeanReversionStrategy`，params 键对齐构造器（去死键 `bollinger_period`），description 去掉占位表述；未改 regime 权重画像、未晋升版本号。单测补 1 例（ref 可 import 解析到真实类、无死键）；`test_strategy_registry` 22 passed，strategies+registry 213 passed 无回归。
- **剩余风险/未验证**：① 均值回归策略类尚未接入后端匹配/部署硬切换链（后端 0 命中 core 注册中心，M6）；② 策略参数（RSI 30/70、2σ、2 ATR 门控等）为构造器默认值，未经 CLEAN 分布校准；③ 版本号仍 v0.1.0，生命周期晋升由 StrategyRegistry 状态机另轮评估；④ 永续/账本/容器镜像/总权益字段阻塞项未在本轮解除；未触 configs/registry.yaml/mt5/密钥/实盘资金路径。

### #307 统一保护裁决编排入口 decide_protection ✅ 已完成
- **完成时间**：2026-11-12
- **内容**：`core/risk/protection.py` 新增 `decide_protection` 编排入口，把 `stops` 四级止损与吊灯/分批/回吐三类裁决组合为单一裁决，统一输出 `ProtectionDecision` 快照。优先级：信号/时间止损平仓 > 利润回吐清剩余 > 分批止盈减仓 > 吊灯/跟踪/保本收紧止损 > 持有；止损判定与三类裁决全部复用既有纯函数，单调不变量走 `update_stop`；审计快照携带入场冻结值、当前 R、峰值、剩余比例等可回放上下文。`core/risk/__init__.py` 导出 `decide_protection`。单测补 10 例（信号/时间/回吐/分批/吊灯/跟踪/持有/回吐优先于分批/吊灯未激活回落/审计字段）；`tests/test_risk` 289 passed，risk+audit 457 passed 无回归。
- **剩余风险/未验证**：① 编排入口尚未被后端服务层调用，三套后端口径（risk_engine 冻结 ATR/R、strategy_v2 百分比、native_protection 原生单）的适配映射留待后续切片；② 加仓后峰值重定基准、分批与吊灯并存时的状态合并仍未实现；③ 阈值数值未做分布校准（占位默认，入 `configs/` 需人审）；④ 未触 configs/registry/mt5/风控阈值常量/密钥/实盘资金路径。

### #306 持仓保护裁决纯函数底座：吊灯/分批止盈/利润回吐 ✅ 已完成
- **完成时间**：2026-11-12
- **内容**：`core/risk/protection.py`：在 `stops.py` 四级止损之外补齐研究层缺失的三类保护裁决纯函数——① 吊灯退出（峰值 ± 冻结 `atr0×mult`，仅当候选价优于当前止损才返回，不放宽风险；激活态由编排层判断）；② 分批止盈（规则档 `level_r/ratio`，同 bar 只推进首个未完成级别，剩余比例相乘，完成标记不重复减仓）；③ 利润回吐保护（峰值利润回撤 ≥ `retracement_pct` 且当前仍盈利、`r≥min_r` 才触发清剩余）；`ProtectionDecision` 统一审计快照（`action/source/new_stop/reduce_ratio/close/audit`）。阈值参数由调用方按分布校准传入，底座不写死经验数值；纯函数、无副作用、不持有资金、不下单。`core/risk/__init__.py` 导出新符号。单测 `tests/test_risk/test_protection.py` 32 例；`tests/test_risk` 279 passed，risk+audit 447 passed 无回归。
- **剩余风险/未验证**：① 裁决层尚未与后端 `risk_engine` / `strategy_v2/protection` / `native_protection` 三套服务层口径接线；② 原生保护单与内部跟踪状态统一对账、加仓后峰值重定基准仍待后续切片；③ 阈值数值未做分布校准（保持占位默认，入 `configs/` 需人审）；④ 未触 configs/registry/mt5/风控阈值常量/密钥/实盘资金路径。

### #301/#302 多 Agent 职责与编排规范（草案）✅ 已完成
- **完成时间**：2026-11-11
- **内容**：`docs/design/design-multi-agent-orchestration.md`：定义 ORCH 项目负责人 / RES 策略研究 / ENG 代码实现 / RISK 仓位资金管理四角色的职责边界、输入产出契约、交接物、协作流程（L1→L2→L3 因果顺序）与门禁放行条件；角色→现有 `core/`、`backend_api_python/`、`frontend-pro` 模块映射对齐蓝图 G1–G13 与 TODO 缺口；红线停止条件对齐 `AGENTS.md`。明确口径：Agent 为会话内职责切面，非常驻后台自治交易员，会话结束即终止；不承诺盈利，须过蓝图 §7 上线门禁方可按影子→小资金→全量灰度；LLM 不进下单路径。本轮为纯设计文档，未改生产代码与配置，无单测适用。

### 47. 研究/ML 层阶段1骨架：特征注册表 + 模型注册中心 + 训练管线编排 ✅ 已完成
- **完成时间**：2026-11-08
- **内容**：
  - `core/features/registry.py`：中心化特征元数据注册表。`FeatureSet` 仅 CLEAN/KNOWN（HELD_OUT 刻意不入枚举，注册层拒绝）；`FeatureDefinition` 冻结快照（name/version/func/upstream_fields/params/window_bars/set_owner/available_at/source/description，血缘 `name@version`，序列化不含 func）；注册机检 snake_case 命名、version 非空、func callable、upstream_fields 属 BarLike 字段子集、window_bars≥0、集合归属合法、source 必填；同源 `panel_features` 导出；`build_default_registry()` 预登记 `atr_wilder@v1` / `realized_vol@v1` / `donchian_position@v1`。
  - `core/registry/model_registry.py`：ML 模型版本注册中心。`ModelStage` 严格状态机 CANDIDATE→STAGED→PRODUCTION→ARCHIVED/RETIRED（RETIRED 终态，非法转换拒绝）；`ModelVersion` 快照含特征血缘/标签口径/数据区间/种子/commit/超参/指标/父版本/制品占位；进入 STAGED 自动冻结，冻结后拒改 metrics（防事后调标）；`to_dict/from_dict` 往返还原阶段/冻结态/时间戳；唯一键 `model_id:version` 拒绝覆盖。
  - `core/models/pipeline.py`：训练管线编排。同源因果面板 → triple-barrier 二分类标签 → 特征 NaN 行清洗 → purged walk-forward + embargo（禁随机切分）→ 折内 `Model` protocol 拟合 → OOS accuracy / AUC（Mann-Whitney，纯 numpy，ties 平均秩）/ 正类概率 → 可序列化 `TrainingResult`，可转 CANDIDATE `ModelVersion`。
  - 包导出对齐 `core/features/__init__.py`、`core/registry/__init__.py`、`core/models/__init__.py`。
- **验证**：新单测 32 passed（特征注册 14、模型注册 12、管线 6）；`import core.features / core.models / core.registry` 无环；全量 `pytest -q` 595 passed。
- **既有失败（非本轮引入，未夹带修复）**：`tests/test_control/test_kill_switch.py::test_missing_state_with_audit_fails_closed` 1 failed；`tests/test_logging/test_audit_logger.py` 4 errors（teardown 临时目录 WinError 145 清理失败，用例本体通过）。对应源文件不在本轮改动列表，属 control/logging 既有切片，待单独处理。
- **边界 / 未验证**：纯逻辑内存骨架，不持久化权重二进制、不连数据库、不产交易收益序列；未引入 sklearn/lightgbm 硬依赖；PBO/CPCV/DSR 仅预留指标槽位，实验账本与 trials 计数仍由实验脚本/审计负责（AGENTS.md 规则 11）。生产化 ML 依赖引入、训练脚本与权重落库、制品库与在线灰度属边界外，待拍板。
- **提交**：Gitee `7e482c5`。

### 48. 策略中心交易对收口为可成交主流品种（现货）✅ 已完成
- **完成时间**：2026-11-08
- **内容**：
  - 后端 `app/services/strategy.py` 新增模块级纯函数：`normalize_strategy_symbol`（池/指数/股票前缀引用原样保留；crypto 无斜杠/横杠/下划线/资金费后缀规范成 `BASE/QUOTE`；空值返空串）、`classify_strategy_symbol`（`pool/crypto/equity/other/""`）、`is_research_only_strategy`（signal 模式或挂组合池品种→研究信号）；`_query` 出口派生 `symbol`（规范后）、`symbol_kind`、`research_only` 三字段；`redact_strategy_row` 全量复制不剥离派生字段。
  - DB 快照 `qd_strategies_trading`：id1/2/3 对齐 OKX demo 现货主流币对 `BTC/USDT`、`ETH/USDT`、`SOL/USDT`（canonical 同步、market_type=spot），凭证 `exchange_config.credential_id` 由失效的 1 修正为实际存在的 2（OKX-DEMO，user_id=1）；id4/5 美股 sp500 池研究信号策略品种/市场/凭证/manifest 全部保留不动。
  - 前端详情弹窗交易对行新增研究信号标注「研究信号·不可实盘成交」（`research_only===true || symbol_kind==='pool' || execution_mode==='signal'` 显隐）；`.detail-value-wrap` / `.detail-hint` 样式；css/js 版本号破缓存。
- **验证**：新单测 `tests/test_strategy_symbol_normalization.py` 8 passed；策略相关子集 34 passed（v2_routes/v2_storage/v2_service/lifecycle/secret_handling/deployment_payload/normalization）；容器内探针直连 `StrategyService.list_strategies(user_id=1)` 返回 5 行，1/2/3 为 crypto/spot/live/cred 2，4/5 为 pool/signal/research_only；浏览器登录态复验：id5 详情显示 `universe:POOL:sp500` + 研究信号标注，id1 详情显示 `BTC/USDT` 且无标注。
- **未验证 / 遗留（阻塞待拍板）**：V2 实盘会话候选品种由编译脚本 manifest 解析（`trading_executor.resolve_candidates(manifest=program.manifest)`），不由 DB 顶层 symbol 驱动。1/2/3 引用的历史版本 pk15/11/19 合约仍为 `set_universe(pool="sp500")` + `set_benchmark("USStock:SPY")`，与顶层 crypto 快照本就不一致；要让这三条在 OKX 现货真实成交，需把对应脚本合约改为 crypto 单品种并重编译版本、更新部署引用——属合约层改动，按 AGENTS.md 停止条件待人工确认。实盘下单成交未验证：demo 账户 `acctLv=1` 简单账户仅现货可成交，永续开仓被 `OKX_SWAP_ACCOUNT_MODE_REQUIRED` 阻塞。
- **提交**：本地 `2f8f35d`。

### 43. 账户列表去演示哨兵并接入真实凭证端点 + 日志签名错位修复 ✅ 已完成
- **完成时间**：2026-11-08
- **内容**：侧边「我的账户」与绑定弹窗账户列表唯一事实源收口到 `GET /credentials/list`；`loadAccountsList` 改为异步拉取真实凭证回填，删除硬编码 `OKX-DEMO` 与固定 api_key_hint 演示卡片。`updateAccountsList` 真实登录态空凭证走空态「暂无已连接交易账户」，仅未登录/接口全挂（非真实）保留演示兜底；卡片按 `environment` 标注模拟盘/实盘。同时修正 14 处 `debugLog(msg, type)` 参数颠倒（级别↔消息）导致的系统日志级别筛选/计数失效；请求层、K线/WS/下单路径的裸 `console` 收口到系统日志通道，不改变控制流与返回值。
- **验证**：`node --check` 通过；后端 `/credentials/list` 实测返回 1 条真实凭证（id=2，okx，env=demo，hint `af36...5c1a`）；浏览器登录态侧边与弹窗均回显真实凭证 hint，未上屏硬编码 `8a12...0cf2`；系统日志级别徽标 SUCCESS/INFO 与消息正文分离正确，控制台无报错。
- **未验证**：真实空凭证（无任何已绑定账户）的空态仅按代码路径收口，当前库内存在 1 条 demo 凭证，未在"零凭证"环境实测空态文案；实盘/live 凭证标注未在真实 live 凭证上复核。
- **提交**：Gitee

### 44. 综合市场分析面板去演示噪声端点收口 ✅ 已完成
- **完成时间**：2026-11-08
- **内容**：核心引擎「综合市场分析」面板原先无条件 `fetch('/api/p1/market-layers/demo')` 上屏方向/置信度/L1-L5；核查后端确认该端点与 `/api/market-analysis/demo` 均用 `random` 生成演示 K 线再跑分析器，返回的方向/置信度为随机噪声，后端暂无基于真实行情的综合分析只读端点。收口为：登录态（`Auth.isLoggedIn()`）不拉 demo、渲染空态「暂无真实综合市场分析，待接入」，状态标签切「待接入」；仅未登录/接口全挂（非真实）保留 demo 兜底与「演示数据」标签。面板标题去掉「（演示）」。不改交易路由/风控/下单/资金计算，未动行情直连链路。
- **验证**：`node --check app.js` 通过；浏览器登录态进入核心引擎页，面板空态文案与「待接入」标签生效，控制台 0 报错；K 线徽标实测 `● LIVE 实时数据`，真实 K 线链路正常。
- **遗留/未验证**：① K 线 `generateMockKlineData()` 人造蜡烛（42000 起）仅在接口空/异常的失败降级分支调用，当前真实链路走 LIVE，本轮保留为遗留候选，未改降级为空态；② 绑定弹窗保存凭证 payload `environment: 'demo'` 写死，弹窗无 live/demo 选择控件，属凭证提交参数、边界外，未决；③ 未登录分支 demo 兜底路径未跑未登录实测。
- **提交**：Gitee

### 45. 系统简介页补技术架构与数据流说明 ✅ 已完成
- **完成时间**：2026-11-08
- **内容**：简介页原有「五层闭环」为概念职责分层，缺真实技术栈/部署拓扑/组件职责与数据流。在五层闭环后新增两块只读说明：①「技术架构与部署拓扑」六层条——浏览器前端（原生静态站 + ApiService + Bearer token）、接入层（静态服务 :8899，`/api/*` 反代后端 :5001）、后端路由层（Flask 蓝图按领域拆分，auth/credentials/dashboard/portfolio/risk/strategy*/backtest/kline/indicator/p1_modules/p2_modules/validation/quick_trade）、后端服务层（回测/组合风控/策略运行时/live_trading 工厂/因子/通知）、数据源层（factory 路由 crypto/forex/us_stock/cn_stock/hk_stock/asia_stock/futures/moex/tencent，带缓存/熔断/限流）、存储与外部连接（PostgreSQL，凭证 Fernet 加密，凭证库 → live_trading.factory → 交易所客户端）；②「关键数据流与前后端分工」三卡（行情与指标、凭证与交易、决策审计）+ 分工边界条（后端计算风控/仓位/信号/回测，前端只展示确认，止损风控后端强制执行）。模块名/端口/数据源均核对真实目录与 `scripts/serve_frontend_pro.py`，未编性能指标或不存在的接口。
- **验证**：全文件 div 开闭配平 1061/1061；浏览器登录态切到「系统简介」，两块新卡片六层条、三卡与分工条完整上屏，控制台 0 报错；纯静态文案，未改 JS/后端/交易路由/风控/资金链路。
- **未验证**：架构说明为当前代码库快照口径，后续后端新增路由/数据源时需同步本页文案；未在未登录态复核展示（纯静态，不依赖登录态）。
- **提交**：Gitee

### 46. 系统简介页补现状优缺点与分阶段演进待办 ✅ 已完成
- **完成时间**：2026-11-08
- **内容**：简介页「后端API设计理念」后新增两块只读静态：①「现状优势与局限（代码快照自评）」——优势 5 条（闭环骨架、过拟合三重验证落地、数据源可插拔、决策可审计、工程纪律），局限 6 条（ML 生产闭环未成型、研究-生产特征同源待加固、执行层偏直连缺 OMS/EMS 与拆单、风控网关复用待闭合、韧性与实验基建待补、实盘未验证）；②「分阶段演进待办」——P0 稳固底座 / P1 研究与 ML 骨架 / P2 执行·韧性·规模化，条目对齐本 TODO 阻塞项与差距矩阵。口径上严格区分已落地与待补缺口，不把 ML 训练、OMS/EMS/拆单写成现状；不含绩效数字，阈值由分布校准；待办单一事实源仍在 `docs/TODO.md`，页面不另写一套。
- **验证**：`index.html` div 开闭配平 1075/1075 diff=0；`node --check app.js` exit 0；浏览器登录态进入简介页，9 项关键文案全部命中 DOM，优势/局限卡片 903×564 正常渲染，控制台 0 报错；纯静态文案，未改 JS/后端/交易路由/风控/资金链路。
- **未验证**：未在未登录态复核（纯静态，不依赖登录态）；优缺点/待办为代码快照口径，后续后端新增模块需同步本页；既有「五层闭环」概念块中 ML 训练、OMS/EMS/拆单为目标态表述，本轮未改动该口径。
- **提交**：Gitee

### 42. 日志中心接入交易日志 / 决策日志（复盘归因素材）✅ 已完成
- **完成时间**：2026-11-08
- **内容**：前端日志中心新增「决策日志 / 交易日志 / 系统日志」三类切换。决策日志接 `GET /api/strategies/logs?id=<sid>`（表 `qd_strategy_logs`），交易日志接 `GET /api/strategies/trades?id=<sid>`（表 `qd_strategy_trades`），系统日志沿用前端内存 `debugLogs`；按所选策略拉取，级别/关键词筛选、当前过滤结果导出。决策/交易日志为后端只读，禁用清空；未选策略、空数组、接口异常走真实空态与错误提示，缺值 `--`，不编演示值。只读归因，不触发下单/平仓/资金动作。
- **验证**：前端 `node --check` 通过，index.html div 配平 1024/1024；浏览器登录态复验：决策日志选策略 5 真实回显（error 8 / warn 31，第四卡「决策记录」），交易日志 0 条真实空态（表头方向/品种/价格/数量/盈亏/平仓原因），系统日志隐藏策略下拉、清空可用、第四卡「API请求数」；error 级别筛选 8 行、关键词搜索命中、重置正常，控制台无报错。
- **未验证**：`qd_strategy_trades` 对在跑策略当前为 0（demo 成交落在 `qd_quick_trades`），交易日志空态为真实口径；是否合并 `qd_quick_trades` 口径本轮未决，沿用既有边界未改后端。
- **提交**：Gitee

### 41. AI 复盘模块接入 + 复盘经验回灌 Wiki ✅ 已完成
- **完成时间**：2026-11-08
- **内容**：前端新增「AI复盘」页，接 `POST /api/strategies/review-report` 与 `GET /api/strategies/review-report/history`；按真实契约渲染策略概要、绩效指标、规则诊断、改进建议、AI 总结、计费/归档标记与历史记录；只读归因，不触发下单/平仓/资金动作。Wiki（`docs/WIKI.md` + 前端只读镜像）新增「AI 复盘与经验回灌」分区：归因框架、链路、边界纪律、回灌闭环与机构对标；动态单次复盘结果留后端历史库，不固化进 Wiki。
- **验证**：后端健康检查/登录/策略列表（5 条真实策略）规则复盘（include_ai=false）HTTP 200、`code=1`，诊断/建议/计费字段按契约回显；历史列表 HTTP 200。前端 `node --check` 通过，div 配平。
- **未验证**：含外部 LLM 的 AI 总结（include_ai=true）返回结构与可用性未实测；历史条目点击二次拉取完整报告本轮未接入。
- **提交**：Gitee

### 40. OKX API账户绑定模块 ✅ 已完成
- **完成时间**：2026-10-27
- **内容**：前端API弹窗+后端OKX客户端+连接测试+DEMO账户已绑定
- **验证**：返回余额$98,340.28
- **提交**：Gitee

### 39. OKX实时行情API ✅ 已完成
- **完成时间**：2026-10-27
- **内容**：ticker API（BTC实时价格）+ kline API框架
- **验证**：前端顶部显示$80,240 ● LIVE实时数据
- **提交**：Gitee

### 38. P1核心引擎前端可视化面板 ✅ 已完成
- **完成时间**：2026-10-27
- **内容**：五层市场识别架构+策略优化引擎+因子库+策略健康度+综合市场分析
- **验证**：Chrome DevTools截图确认正常渲染
- **提交**：Gitee commit 07828bb

### 37. L3/L4/L5市场识别模块 ✅ 已完成
- **完成时间**：2026-10-26
- **内容**：五层架构全部搭好（L1市场状态→L2市场结构→L3趋势→L4价格行为→L5K线形态）
- **提交**：Gitee commit 1db4bfb

### 36. 策略优化引擎基础框架 ✅ 已完成
- **完成时间**：2026-10-26
- **内容**：因子库+参数优化+过拟合防御
- **提交**：Gitee commit 5677908

### 35. WebSocket实时推送连接 ✅ 已完成
- **完成时间**：2026-10-25
- **问题根因**：`logDebug` 函数名不匹配
- **修复方案**：批量替换 `logDebug` → `debugLog`

### 34. 前端工程化拆分 ✅ 已完成
- **完成时间**：2026-10-26
- **拆分结果**：index.html + css/main.css + js/app.js
- **踩坑记录**：用正则匹配拆分，Python处理UTF-8

---

## 🔧 技术债与临时方案

| # | 事项 | 状态 | 说明 |
|---|------|------|------|
| T1 | 开发模式自动登录 | ⚠️ 临时方案 | 代码已写，浏览器缓存没生效 |
| T2 | API认证token问题 | ⏳ 待修复 | 开发环境下API返回401，需要跳过认证 |
| T3 | 飞书云文档/Wiki同步 | ⏳ 待做 | 文档只在本地和Gitee |
| T4 | 数据库真实K线数据导入 | ⏳ 待做 | PostgreSQL还没导入历史数据 |
| T5 | 现货下单链路 | ✅ 现货闭环 / ⏳ 永续阻塞 | 现货 demo 小额往返冒烟闭环（#298/#300）；永续开仓被 demo 简单账户 `acctLv=1` fail-closed 拦截（`OKX_SWAP_ACCOUNT_MODE_REQUIRED`），需账户模式决策 |
| T6 | core 纯函数有限性守卫旁路 | ⏳ 待接线 | 已加固风控/仓位/路由/撮合/组合/止损/选择器/策略/模型/成本/执行引擎活路径（#185–#197）：NaN/inf/负/0 在边界显式失败。未加固旁路：lifecycle `WatchThresholds`/`LaunchCriteria` 与 metrics 容错、verification_middleware 阈值、drift_monitor、stress_test、容错归一 pretrade_gate——适配器未接线（#154/#155），非法值当前 fail-closed 或仅影响建议、不放大敞口；待适配器接线时在适配器/冻结配置层补 finite/区间校验 |

---

## 📚 知识沉淀

| # | 事项 | 状态 |
|---|------|------|
| K1 | RULES.md避坑指南已创建 | ✅ 完成 |
| K2 | 技能知识库TODO同步 | ⏳ 本次更新 |
| K3 | 内部Wiki思维导图创建 | ⏳ 待做 |
| K4 | 对话经验Memory沉淀 | ⏳ 待做 |

---

## 🕳️ 踩坑经验（必须记住，避免重复）

### 前端踩坑
1. **禁止用PowerShell处理UTF-8中文文件**：Get-Content/Set-Content会搞坏编码
2. **前端文件修改后必须用Node.js做语法检查**：`node --check app.js`
3. **Docker部署后必须强制刷新浏览器**：浏览器会缓存旧的JS/CSS
4. **禁止用固定行号拆分前端**：应该用正则匹配 `<style>`/`<script>` 标签

### 后端踩坑
1. **Python方法名必须和调用方严格一致**
2. **Docker容器代码不是挂载的**：本地改完必须docker cp进去，重启容器才生效
3. **Blueprint路由不能带url_prefix**：统一在register.py注册时传
4. **函数命名不一致是最高频bug**：`logDebug` vs `debugLog` 这种小问题会导致整个JS执行中断

### 部署运维踩坑
1. **浏览器缓存是前端调试最大敌人**：每次部署后必须 ignoreCache: true
2. **Docker容器内文件修改后不会自动同步**：必须手动 docker cp
3. **Git分支名要统一**：gitee用main不是master

---

## 完成状态图例
- ❌ 未开始
- 🔄 进行中
- ✅ 已完成
- ⚠️ 临时方案

---

## 2026-10-28 重排：P0/P1/P2

> 基于本轮 4 份联调/策略文档（frontend-bug-list / frontend-debug-experience / p2-panel-completion / strategy-registration）对原有 TODO 重新归类。
> 原 TODO 内容保留不动，本节为重排视图。每条标注【真实状态】+【下一步动作】。

### P0（阻塞实盘 / 本周必须完成）

| # | 事项 | 真实状态 | 下一步动作 |
|---|------|----------|-----------|
| P0-1 | **nginx upstream 502 修复**：前端容器 nginx 配 `backend:5000`，但 docker 网络里后端 DNS 别名只有 `quantdinger-backend`，导致 `/api/*` 全 502，登录/核心引擎/K线全部不可用 | ✅ 已完成（2026-10-31 复测：nginx `set $backend_upstream http://quantdinger-backend:5000`，`:5000` 与 `:8888` 健康检查均 200） | 已修复；每次前端容器重启后需重跑 `sed` 改 upstream + `nginx -s reload`（官方镜像会回滚配置） |
| P0-2 | **OKX 下单链路**：原 `"All operations failed"` / tdMode / 现货参数问题 | ✅ 现货闭环（#295/#297/#298/#299/#300：持仓口径、数量换算、现货往返冒烟、symbol 归一化）；⏳ 永续阻塞于 demo `acctLv=1` 简单账户模式 | 现货维持最小手数复测；永续需先在 demo 切保证金账户模式或策略只跑现货（账户模式决策待拍板）；容器镜像尚未含本轮改动，端到端下单待容器复验 |
| P0-3 | **API 认证 token 401**：开发环境下 `/api/dashboard/summary` 等已鉴权接口返回 401，导致前端持仓面板即使 API 通了也没数据 | ✅ 已完成（登录 `POST /api/auth/login` → `data.token`，Bearer 访问 dashboard/summary 200） | 已修复；官方镜像不支持 `SKIP_AUTH` 环境变量，鉴权必须走登录拿 token |
| P0-4 | **前端容器实环境验证 P2 六卡片 + 真实 K 线接入**：本地源码已改（p2-panel-completion），但通过 `:8888` 代理请求 6 个 P1/P2 端点在本机全部 5s 超时 | 🔄 进行中（P0-1 已修复 + 网络已恢复，后台子任务容器验证中） | 重启前端容器 `docker restart quantdinger-frontend`，强刷浏览器，逐卡片看状态灯是否点亮（健康服务 / 拥挤度 / 可观测性 / CI-CD） |
| P0-5 | **本地直连 OKX API 被墙**：curl 退出码 7，`www.okx.com` 连不通，"联通"结论假阳性 | ✅ 已解除（2026-10-31：宿主机直连 200；容器内经 Docker NAT 亦通 `{"code":"0"}`；代理 127.0.0.1:7890 仍可兜底，wss CONNECT 200） | 直连与代理双通道均已验证；"OKX 链路已通"结论成立 |
| P0-6 | **GitHub 推送修复**：Gitee 已同步，GitHub curl 28 连接重置 | ✅ 已完成（2026-10-31：merge 远程占位初始提交 → `861dc24`，GitHub+Gitee 双端 HEAD 一致） | 已推送成功；详见 ERROR_LOG E008（unrelated histories 合并 + 系统代理未设环境变量的教训） |

### P1（重要但不阻塞）

| # | 事项 | 真实状态 | 下一步动作 |
|---|------|----------|-----------|
| P1-1 | **策略生命周期后端自动退役逻辑**：前端三级健康度面板已做，后端触发阈值自动停策略+通知+记录原因未实现 | 🔄 部分落地（#311：core `StrategyRegistry.retire_if_health_below` 退役裁决纯方法；#312：`health_score_from_snapshot` 快照→[0,1] 健康分桥接；#314：`retirement_arbitration.arbitrate_retirement` 健康分×生命周期建议联合裁决纯编排接缝） | 剩余：硬门禁否决（DSR>0/PBO/交易数下限）另走 lifecycle/上线门禁；后端通知/回调由编排层读 `retirement_log` 触发；联合裁决尚未在编排进程接线；评分/观察带阈值未做 CLEAN 分布校准，入 `configs/` 需人审 |
| P1-2 | **五层市场识别接入真实 K 线**：L1-L5 规则版完成但喂的是演示数据 | 🔄 进行中（后台子任务接 OKX kline → 特征化 → 喂 regime.py；容器内 OKX 连通已确认） | 先接 BTCUSD M15 一个品种跑通，再扩展 |
| P1-3 | **均值回归策略类**：原路由表 `implementation_ref=(未实现)`、代码库无对应类 | ✅ 已落地并挂接（`core/strategies/mean_reversion.py`：RSI(14 Wilder)+布林(20,2σ)+非强趋势门控+Wilder ATR+因果窗口守卫；单测 `tests/test_strategies/test_mean_reversion.py`，#260；`strategy_router.py` 占位条目 ref 已指向真实类、params 键对齐构造器） | 策略类未接入后端匹配/部署硬切换链；参数阈值待 CLEAN 分布校准；版本号仍 v0.1.0，生命周期晋升由 StrategyRegistry 状态机另轮评估 |
| P1-4 | **路由权重表分布校准**：当前 4×3 权重表是定性配置，未经 CLEAN 分布驱动 | ❌ 未开始 | 跑 `python scripts/calibrate_regime.py --mode distribution`，用输出分位替换 `strategy_router.py` 里硬编码权重；改前 ADR 留档 |
| P1-5 | **StrategyMatcher × StrategyWeightRouter 集成**：两层目前独立（一个打分排序、一个出资金权重） | 🔄 部分落地（#309：Router 侧 `route_subset`/`route_selected` 已落地——Matcher top-N 名单子集内归一化、子集外归零、未知策略名 fail-closed；单测 6 例） | 剩余：Matcher `MarketRegime` 枚举（trending/ranging）与 Router `SUPPORTED_REGIMES`（trend/range/volatile/quiet）口径对齐；同名 Profile↔Descriptor 池同步；端到端 select→subset 路由串联另轮评估 |
| P1-6 | **前端 axios 响应拦截器容错**：502 时把 nginx HTML 原文塞给用户（P1-1 bug） | ❌ 未开始 | 拦截器里判断 `Content-Type`，非 JSON 时统一提示"服务暂时不可用 (HTTP 5xx)"，不暴露 HTML |
| P1-7 | **登录错误 state 在路由切换后未清空**（P2-1 bug）：跳注册页被守卫弹回，旧 502 错误还挂着 | ❌ 未开始 | 登录页 `onMounted` 或 `watch(route.query.redirect)` 时清空 `errorMessage` + 表单字段 |
| P1-8 | **`quantdinger-scheduler-worker` / `trading-worker` 容器 unhealthy**：基础设施告警 | ❌ 未开始 | `docker logs quantdinger-scheduler-worker --tail 50` 看根因；不影响前端联调，但要排 |
| P1-9 | **连续 regime 线性插值**：当前用离散 trend/range/volatile/quiet 4 类，未接 regime.py 的连续 `w_trend/w_mr/w_range` | ❌ 未开始 | 在 `StrategyWeightRouter.route()` 加可选连续模式，用连续权重做线性插值；保留离散模式做回退 |
| P1-10 | **后端三套保护层与 core 底座口径对齐**：risk_engine（ATR/R）、strategy_v2（百分比）、native_protection（原生单）并行，基准/阈值/分批语义存在分裂 | 🔄 只读对照完成（#310 清单 + #313 S4 保本/时间止损逐行核对，见 `docs/design/protection-layers-reconciliation.md`） | 待决策门 D1-D5：后端硬编码阈值改分布校准+config 注入（红线）、百分比↔ATR/R 基准统一 ADR、分批单 bar 语义统一、core 进容器取舍、接线 core `decide_protection` 底座 |

### P2（优化项 / 可延后）

| # | 事项 | 真实状态 | 下一步动作 |
|---|------|----------|-----------|
| P2-1 | **P2 六卡片真实数据在容器内复测**：本轮本地改完未在容器环境验证 | 🔄 进行中（P0-1 已修复 + 网络已恢复，与 P0-4 同由后台子任务验证） | P0-4 验证通过后逐卡片人工核对：高可用 / 交易归因 / 安全合规 / 拥挤度 / 可观测性 / CI-CD |
| P2-2 | **因子库从 10 扩展到 20+**（文艺复兴式海量弱信号叠加） | ❌ 未开始 | 每加一个因子必须配套：单测 + 前视守卫测试 + 在 CLEAN 集上做 IC 衰减检验 |
| P2-3 | **五层市场识别 ML 增强版**（提高 L1-L5 识别准确率） | ❌ 未开始 | 先用规则版攒够标注数据，再训练；禁止拿测试集做特征选择 |
| P2-4 | **PBO / CPCV / Deflated Sharpe 三重验证算法落地**（框架已建） | ❌ 未开始 | 按 López de Prado 教材实现；每个策略上线前必须三指标全过 |
| P2-5 | **PostgreSQL 历史 K 线数据导入**（当前库里没历史数据） | ❌ 未开始 | 写 `scripts/import_kline.py`，按 symbol/timeframe 批量灌；灌完跑 `core/gap_normalizer.py` 清洗缺口 |
| P2-6 | **飞书云文档 / Notion / Gitee 多端知识库同步**（当前只在本地 + Gitee） | ❌ 未开始 | 先打通 Gitee → Notion 单向 webhook；本地 RULES.md / TODO.md 为主源 |
| P2-7 | **密码输入框加 `autocomplete="current-password"`**（antd 控制台警告） | ❌ 未开始 | 一行属性修复，下次顺手改 |
| P2-8 | **P2 卡片"更新时间"改用服务端时间戳**（当前用浏览器本地时间） | ❌ 未开始 | 后端 summary 接口统一加 `server_ts` 字段；前端渲染该字段 |
| P2-9 | **开发模式自动登录（T1）清理**：代码已写，浏览器缓存没生效 | ⚠️ 临时方案 | P0-3 修完后此条一并关闭，不要长期保留自动登录后门 |

---

**2026-10-31 状态：P0 完成 4/6（P0-1 ✅、P0-3 ✅、P0-5 ✅、P0-6 ✅），P0-2 / P0-4 后台子任务推进中；P1-1 / P1-2 / P1-3 后台子任务推进中（5 个子任务并行执行中）。**
**下一步重点：等后台子任务收口（OKX 下单根因、策略退役、真实K线接入、均值回归策略、P2 六卡片验证），收口后统一验证并沉淀。**

---

**2026-10-31 晚 更新（#99 自建前端真实数据链路收口 ✅）**：
- **持仓真实性**（#64 部分推进）：`loadRealPositions` 判据兼容 `code:1` + `data.positions/items`；`updatePositionsList` 真实模式空持仓显示"暂无持仓"，不再塞示例 0.5 BTC；假数据 $42,000 已从界面清除（Chrome 截图取证）。**剩余缺口**：总权益仍显示演示 5,000.00——`/api/account/positions` 后端未返回 `total_equity/equity` 字段，需后端 account 模块补（查 OKX balance），属 #97/#64 后续。
- **K 线冗余调用消除**：30s 轮询 `fetchRealKline`（/api/market/kline 空拉不画图）→ 统一为 `loadKlineData(true)`（真实 /api/indicator/kline 渲染 + 静默刷新），Network 中 market/kline 请求消失。
- **p1/p2/validation 全链路实测**：16 端点 Bearer 全 200（health/journal/security/market-layers/optimizer/strategy-health/crowding/observability/cicd/websocket/validation×3/risk×3），无 404。
- 验证：Chrome 强刷 :8899 console **0 error/0 warn**，持仓区"暂无持仓"、K 线 LIVE $77,621、5 策略运行中。
- 沉淀：ERROR_LOG E010 已登记；git 提交后 HEAD/github/gitee 三方一致。

---

## 2026-11-08 真实数据口径收口（#123/#124/#125/#126）

### ✅ 本轮完成

- ✅ **#123 压力测试面板空态收口**：无数据/接口异常时五卡名称/数值/描述/评分清空置 `--`；有数据回填后端情景；评分元素改显式 `id` 选择器（修复旧 `[style*=文本]` 恒命中 null、评分从未回填的既有 bug）。
- ✅ **#124 绩效对比表 + 月度热力图真实空态隔离**：真实模式（`code===1` 且 rows 非空）清空对比表三行八列与热力图 12 格；无 rows/异常保留静态样例作未登录兜底；版本号破缓存。
- ✅ **#125 规则/Wiki/TODO 沉淀**：RULES.md 追加 4.4 演示/真实视图隔离、4.5 图表画布渲染时序两条；WIKI.md 新增 OKX/Bybit/WEEX/币安前端看板对接对照表。
- ✅ **#126 三份阻塞方案草稿**（`docs/design/`，待评审，不含生产代码）：
  - `design-perf-snapshot-api.md`：逐策略绩效快照接口 `/strategies/perf-snapshot`
  - `design-risk-budget-basis.md`：风险预算【资金名义占比】vs【波动率风险贡献】选型
  - `design-monthly-heatmap-route.md`：月度热力图【后端预聚合】vs【前端 equityCurve 切片】选型
- 提交：Gitee `1dd8130`（2 files，91+/26-）；`node --check` 通过；浏览器实测真实模式缺失项 `--`、评分/摘要回填正常。

- ✅ **#127 风险预算面板收口**：后端仅返回组合级六字段，无策略级 allocation/budget/exposure/相关性/VaR/CVaR；真实模式清空四条静态演示占比为空态行，标题下补口径副标。
- ✅ **#128 健康度卡片收口 + id 错位修复**：修复重复 id `strategy-health-list` 导致引擎摘要永远未回填；引擎摘要容器改名 `engine-health-list`，回填目标同步改名；validation 旧三条假绩效卡片真实模式清空。
- ✅ **#129 TCA 成本面板收口**：对接 `/api/tca/cost-summary`，`no_orders`/失败清空六格 + verdict 为 `--`；有订单回填 breakdown 与 avg_cost_bps。
- ✅ **#130 数据治理 / L1 状态 / 高可用 / 重复旧监控面板收口**：DQ 五格 + 进度条 + 综合评分清空；L1 状态卡/六态分布/推荐条、高可用逐组件四格清空；与引擎 P2 卡片重复的旧 validation 面板（安全四格 / 拥挤度列表 / 可观测四格 / CI-CD 列表）真实模式清空演示数字与列表。提交 Gitee `dfb0060`（2 files，143+/45-）；`node --check` 通过；浏览器实测各容器空态、控制台 0 报错。
- ✅ **#131 订单簿回填错位 + 字段名 bug 修复**：JS 回填目标原为不存在的 `orderbook-content`（命中 null 提前 return，WS 推送成功也不渲染，静态演示行永久残留）；HTML 上容器归位 `orderbook-asks`、下容器 `orderbook-bids`、价差行 `orderbook-spread`。字段映射由增量流误用的 `b`/`a` 改为 partial book depth 流的 `bids`/`asks`；分容器三列回填（价格/数量/累计总额 + amount-bar），asks 高到低、bids 高到低。静态 10 行保留为未登录/WS 全挂兜底。浏览器复验 asks/bids 各 20 档、价差 `$0.01`、价格真实、控制台 0 报错。
- ✅ **#132 策略详情参数四格收口**：原静态默认 1000 / 1x / -5% / 30%；HTML 四格默认 `--`，标签"止损比例"改"权益止损比例"；JS 回填 `initial_capital`（toFixed2）、`leverage ?? tc.leverage`（Number+x）、`tc.equity_stop_loss_pct`（×100 百分数），累计亏损停止后端无独立字段恒 `--`。浏览器复验 capital `1000.00`、leverage `1x`、stop `30.0%`、maxloss `--`。
- ✅ **#133 压力测试内置演示情景与 72 分收口**：`/validation/stress-test` 后端为硬编码 5 情景 + 72 分 + 写死 summary，非真实持仓/权益冲击测算。前端 HTML 五卡 name/dd/desc 与综合评分/summary 改空态 `--`；`renderStressTest` 增加真实契约判定：仅 `data_kind==='real'` 才渲染，缺标记/内置演示/无情景一律 `_clearStressTest()`。浏览器复验评分 `--/100`、summary 空、五卡 `--`、控制台 0 报错。后端真实冲击引擎见 P1-11。
- ✅ **#134 前端新增内部 Wiki 只读知识库页**：导航新增"内部 Wiki"，纯静态只读镜像，分区含系统宪法三卡、过拟合/风控/数据质量/工程可靠性四宫格、真实数据口径收口、核心原则速查 8 条、当前阻塞/待拍板、踩坑经验表 5 行；规则与待办单一事实源仍在 `docs/RULES.md`、`docs/TODO.md`，页面不另写一套口径，本轮未做后端动态读取。
- ✅ **#134 附带修复存量 HTML 嵌套未闭合缺陷**：`#page-validation` 内"策略拥挤度监控"面板与 validation 容器两处 `div` 未闭合，浏览器容错把 `logs/engine/about/wiki` 吞入其 `display:none` 子树，级联塌缩为 0×0 宽度；补两处闭合标签后 9 个页面全部回到 `MAIN.main-content` 平级。浏览器逐页复验宽度 967、内容按高度展开、控制台 0 报错；`index.html` div 开合配平 diff=0，`node --check app.js` exit 0。
- ✅ **#135 Wiki 补充可复制成功经验与机构最佳实践对标**：`#page-wiki` 新增"🏆 可复制成功经验"8 条（真实契约先行/显式 id 回填/只读最小手数/单一事实源/新旧分层收口/闭环复验/容器部署纪律/故障沉淀闭环）与"🌐 全球机构最佳实践对标"表 6 行（Renaissance/Two Sigma/Citadel/DE Shaw/Millennium/Jane Street，列核心做法、现状差距、演进方向）；对标为方向参考，阈值仍须分布校准，不照搬机构数值。素材对齐 `docs/WIKI.md` 机构对标表；浏览器复验 11 分区标题、对标表 6 行、宽度 967、控制台 0 报错。
- ✅ **#136 Wiki 沉淀第一性原理推导框架**：`#page-wiki` 宪法之后新增"🧭 第一性原理推导框架"分区：稳定盈利 = 正期望值 × 大数定律 × 不爆仓；五层闭环链（数据输入→信号生成→组合构建→订单执行→风控监控→绩效反馈，反馈回灌）；Alpha 四分类（行为偏差/信息优势/统计偏差/结构红利）；逆向致死清单（不止损/仓位重/过拟合/失效未识别/前视/高杠杆或全仓单一策略）。顶部声明同步纳入方法论框架；素材对齐 `docs/WIKI.md` 稳定盈利原理段，未新编数字。浏览器复验 12 分区标题、公式/闭环/分类/清单文本命中、宽度 967、控制台 0 报错。
- ✅ **#198 策略中心交易对收口为现货主流品种**：后端品种规范化/分类/研究信号纯函数 + 出口派生字段；DB 快照 1/2/3 对齐 BTC/ETH/SOL-USDT 现货并修正凭证 id=2；4/5 sp500 研究信号保留并在详情弹窗标注「研究信号·不可实盘成交」。新单测 8 passed、策略子集 34 passed；容器探针与浏览器复验通过。遗留：历史版本脚本 manifest 仍是 sp500 池，V2 候选按 manifest 解析，合约层改动待拍板。
- ✅ **#199 策略无成交/看板空态归因与状态标签修复**：① 前端策略列表状态映射 bug——`status: s.status || s.execution_mode==='live' ? 'running':'stopped'` 运算符优先级 + 把交易模式误兜底成运行态，导致 3 张 stopped 卡片被标「运行中」；改为只认落库 `status==='running'/'active'`，与详情页口径对齐。② 归因：控制台 8888 502/401/ERR_NO_BUFFER_SPACE 为旧 QuantDinger 隔离栈残留缓冲，8899 实测 17 条资源无 8888；看板 `recent_trades` 实际返回 4 笔真实 OKX BTC 现货成交并正确上屏（多/空/量/价/时间，快捷单无配对盈亏故 `--`）；41 条 `strategy_order_fills` 全为历史 virtual 模拟成交（exchange_id=virtual、credential_id=0、raw_json={}），按口径不冒充实盘成交；7 条 `sent` 为 signal 研究信号策略的通知单（worker signal 分支仅通知不下单），非成交。验证：`node --check app.js` exit 0；浏览器破缓存复验 3 已停止 / 2 运行中、成交列表 4 笔；`/api/strategies`、`/dashboard/summary`、`/strategies/trades` 均 200。遗留：策略驱动成交归集到 `qd_strategy_trades` 账本（fills→账本映射 + 周期对账）属 #155/#108 阻塞项，触及实盘账本路径，待拍板。
- ✅ **#202/#203 对照 OKX v5 官方规范复核下单/成交/鉴权/限流链路并落地安全切片**：通读官方指南（签名 `Base64(HMAC_SHA256(Secret, ts+method+path+body))`、下单字段、`/trade/fills` 等成交端点、限速 50011/50061、模拟盘 `x-simulated-trading:1`）复核本地主适配器 `live_trading/okx.py`；鉴权/下单参数/成交查询主链路无协议级硬伤。工程健壮性缺口与修复：① `base.py` 新增纯函数 `is_retryable_transient`（429/5xx/限流码可重试，4xx 业务错误不重试）与 `retry_delay_sec`（指数退避 0.4→0.8→1.6s 封顶）。② `okx.py` 新增 `_request_readonly_with_retry`：**仅只读 GET** 对连接/超时等网络瞬时错误、HTTP 429/5xx 做有限退避（max 2 次）；**POST 下单/撤单/设杠杆直连不重试**，避免超时歧义触发重复下单；`_public_request` 与 `_signed_request` 按 GET/POST 分流。③ 错误码分类补全：50011/50061 → 限流（退避降频，下单/改单/撤单限速相互独立）；50113 → 签名/时间戳/凭证环境不匹配（核对 Secret/Passphrase、NTP 校时、live/demo 环境匹配）；循环内与空 data 数组顶层兜底各一份。验证：新单测 `tests/test_okx_retry_and_errors.py` 19 passed；既有 OKX/live_trading 子集 22 passed 无回归；容器 `docker cp` + 重启后导入自检 `True/True/True`，`/api/health` 200。**未验证**：退避/限流仅单测 mock 覆盖，未在 OKX 真实环境冒烟下单；fills 归集/周期对账/现货持仓口径分层仍属阻塞待拍板项，本轮未触碰。
- ✅ **#207 风险预算分配 + 相关性熔断纯函数底座（研究层）**：新增 `core/risk/risk_budget.py`，补齐报告清单 #6 两块纯函数底座——① `risk_budget_weights`：按风险贡献倒数归一化（波动越高风险预算越低），零波动等权兜底、全零退化等权；② 相关性熔断：`correlation_pairs`（超阈值高相关对）、`average_pairwise_correlation`（上三角成对相关均值）、`correlation_breaker`（单对超阈或平均成对相关超上限即触发，返回策略/平均相关/高相关对/原因，只判断不处置）。纯 Python（仅 math，不引 numpy），无 IO/不查库/不下单；阈值全部参数注入，模块内不写业务阈值；输入守卫覆盖序列等长且 ≥2、元素有限、波动率非负有限、阈值 ∈(0,1]。`core/risk/__init__.py` 纳入导出。验证：新单测 `tests/test_risk_budget.py` 14 passed；相邻风控子集 15 passed 无回归。**剩余风险**：底座尚未接入开仓决策链（组合门禁/分配器接线属触决策链环节，另轮评估）；`portfolio_analyzer.py` 内 0.7 高相关阈值仍硬编码为遗留缺口，本轮未改既有诊断器契约。
- ✅ **#208 成本边际准入闸门纯函数（研究层）**：新增 `core/execution/economics_gate.py`，补齐报告清单 #7 的边际经济准入判断：`economics_gate` 判定预期边际收益是否达到往返成本的 k 倍（`edge ≥ k×cost`），返回放行/拒绝、收益成本倍数（成本为 0 时不除零记 None）与留痕原因。纯函数、无 IO/不下单；k 倍阈值由调用方/配置注入；守卫覆盖边际收益有限、往返成本非负有限、倍数 ≥1。验证：新单测 `tests/test_economics_gate.py` 9 passed；相邻执行层（对账/归属）子集 25 passed 无回归。**剩余风险**：尚未在 pre-trade 链路与 `pretrade_gate` 组合闸串联；成本口径（点差/滑点/佣金/资金费）仍需适配器侧冻结注入，本轮未接实盘取数。
- ✅ **#209 E1 shadow 对照适配器纯函数（研究层）**：新增 `core/execution/gate_shadow.py`，落地 #154 设计 §2.4 第一步 shadow 对照底座——把后端 `account_risk_snapshot` 返回 dict 映射为 core `RiskProjection`/`RiskLimits`（费用/资金费/symbol_gross 字段名对齐），并行调 `evaluate_projected_limits` 全量投影判定，与后端既有 violation 集合比对，输出 `match/core_allowed/backend_allowed/only_core/only_backend/estimates/missing_fields`。纯函数、无 REST/不查库/不写库；快照缺字段按 0 兜底并记 `missing_fields`，非 Mapping 输入降级不抛；shadow 不改后端既有放行结论。验证：新单测 `tests/test_execution/test_gate_shadow.py` 8 passed；执行层目录 117 passed、control/registry 子集 73 passed 无回归。**剩余风险**：适配器尚未在 worker（E1）进程内接线跑 shadow 日志；E2/E3 手动/快捷入口仍未接账户暴露闸（触下单链路，另轮评审）；后端容器运行时不 import core，接线需先解决 core 进容器或适配器侧复制口径的取舍。
- ✅ **#210 组合分析器高相关阈值参数化（研究层）**：`core/risk/portfolio_analyzer.py` 把伪分散化识别里硬编码的 0.7 抽为 `analyze_portfolio(..., high_corr_threshold: float = 0.7)` 可选参数，向后兼容（既有调用方不传参行为不变）；新增 `_high_corr_threshold` 守卫，非有限/越界（∉(0,1]）回退默认 0.7。验证：`tests/test_risk/test_portfolio_analyzer.py` 新增阈值 1.0 抑制告警、低阈值 0.3 告警、非法阈值（0/1.5/NaN/非数值）降级默认 6 例；risk 目录 122 passed 无回归。**剩余风险**：阈值默认值 0.7 仍为经验默认，尚未由 CLEAN 集分布校准（阈值须来自分布，另轮校准）；该诊断器仍未接入开仓决策链的相关性熔断。
- ✅ **#211 收益分布形态画像纯函数底座（研究层）**：新增 `core/risk/return_profile.py`，补齐报告清单 #4 偏度/左尾维度的可复算统计底座——`describe_returns(returns)` 输出样本数、均值、样本标准差、下行/上行半差（ddof=1）、样本偏度（Fisher-Pearson g1）、超额峰度、最差/最佳单笔、亏损占比、下行/上行半差比（上行半差为 0 记 None）。纯 Python（仅 math，不引 numpy/pandas），无 IO/不查库/不下单；空序列与退化序列中性降级不抛；守卫拒绝 str/bytes/dict 与非有限元素，抛带上下文 ValueError；只算统计量，不产出需分布校准的分类标签（标签阈值交上层适配器按 CLEAN 集注入）。`core/risk/__init__.py` 纳入导出。验证：`tests/test_risk/test_return_profile.py` 13 passed；risk 目录 135 passed 无回归。**剩余风险**：偏度/峰度未做小样本无偏修正（口径已在模块 docstring 注明）；画像尚未被部署守卫/风险闸读取接线；左尾厚/偏度方向的业务分类阈值未校准。
- ✅ **#212 双人复核独立批准人纯校验底座（研究层）**：新增 `core/control/dual_review.py`，补齐报告清单 #9 双人复核（two-person rule）纯判定——`evaluate_dual_review(approvers, *, required_count=2)` 把批准人标识 strip 归一、剔除 None/空白、去重保留顺序，独立人数达注入的所需人数才放行；fail-closed：无批准人 `no_approvers`、单人 `single_reviewer`、重复/人数不足 `insufficient_reviewers` 一律拒绝；审计记录 required_count/unique_count/独立批准人列表。纯函数、无 IO/不查库/不下单；所需人数由配置注入，模块不写死业务复核等级；守卫 required_count 须为 ≥1 整数（排除 bool/浮点/字符串，非法抛错），拒绝 str/bytes/dict/不可迭代输入。`core/control/__init__.py` 纳入导出。验证：`tests/test_control/test_dual_review.py` 16 passed；control 目录 34 passed 无回归。**剩余风险**：尚未在审批闸/危险动作链路接线（哪些风险等级需双人复核仍由配置决定，本轮未改 `approval_gate` 契约）；批准人身份真实性由适配器鉴权注入，本模块不校验签发凭证。
- ✅ **#213 回撤分级降档纯函数底座与引擎参数化（研究层）**：抽离 `core/backtest/engine.py` 闭包内硬编码的回撤分级算术（原步长 0.10、系数 0.8 写死在代码里），新建 `core/risk/drawdown_tier.py::drawdown_tier_factor(equity, peak_equity, *, dd_step=0.10, tier_mult=0.8, base_factor=1.0, max_steps=None)`——回撤深度按步长 floor 计档，返回 `base_factor * tier_mult ** steps`；步长/系数/起始系数/最大档位全部注入，peak≤0 或权益非有限安全降级为 base_factor；守卫 dd_step>0、tier_mult∈(0,1]、base_factor>0、max_steps 为非负整数或 None，非法抛错。引擎改从 cfg 读取 `drawdown_step/drawdown_tier_mult/drawdown_max_steps`（默认沿用历史 0.10/0.8/不封顶，口径等价），闭包改为调用纯函数。`core/risk/__init__.py` 纳入导出。验证：`tests/test_risk/test_drawdown_tier.py` 18 passed；risk 153、backtest 56 passed 无回归。**剩余风险**：分级阈值（步长/系数/封顶档）尚未由 CLEAN 集分布校准，当前为历史默认值；未接实盘减仓执行链，仅回测研究层仓位系数。
- ✅ **#214 漂移监控构造参数边界值守卫（研究层）**：`core/monitoring/drift_monitor.py` 的 `DriftMonitor` 构造原缺入参校验，补 fail-closed 守卫——`baseline_sharpe` 须有限（可负/零）；`baseline_win_rate` 须 ∈[0,1]；`baseline_max_dd` 须 ≥0 有限；三个漂移阈值 `sharpe/win_rate_drop_threshold`、`dd_increase_threshold` 须 >0 有限；`window_size` 须为 ≥1 整数（排除 bool/浮点/字符串）；非法抛带上下文 ValueError。不改变既有合法默认口径。验证：`tests/test_monitoring/test_drift_monitor.py` 新增边界守卫 13 例；monitoring 目录 39 passed 无回归。**剩余风险**：阈值默认值（0.3/0.1/2.0/100）仍为经验默认，尚未由 CLEAN 集分布校准；监控器尚未接入实盘降级/退役决策链。
- ✅ **#215 分类器构造参数整数/区间/有限性守卫（研究层）**：`core/regime/classifier.py` 的 `RegimeClassifier` 构造原仅校验混合权重和为 1，补 fail-closed 前置守卫——`adx_period/hurst_window/hurst_min_window/min_train_rows` 为 ≥1 整数（排除 bool/浮点/字符串）；`random_state` 为整数；`q_lo/q_hi` 有限且满足 `0<q_lo<q_hi<1`（与 `derive_thresholds` 口径一致）；`w_rule/w_gmm` 补有限性校验后保留非负且和为 1；`use_gmm` 须为 bool。不改变既有默认构造口径。验证：`tests/test_regime_classifier.py` 新增构造守卫 19 例；regime 目录 39 passed 无回归。**剩余风险**：分位级别与混合权重默认值仍为经验默认，尚未由 CLEAN 集分布校准；分类器尚未接入实盘 regime 路由的硬切换链。
- ✅ **#216 CV 切分与 PSI/滚动命中率参数整数守卫（研究层）**：`core/models/cv.py::purged_walk_forward` 补 `n/embargo_bars/n_splits/label_window_bars` 整数类型与非负守卫（排除 bool/浮点/字符串），`n≥1`，既有 embargo≥标签视野、warmup 不足、无有效折等契约校验保留；`core/models/drift.py` 的 `psi` 补 `bins≥2` 整数守卫，`rolling_hit_rate` 补 `window≥2` 整数守卫（排除 bool/浮点/字符串）。不改变既有时间序/embargo/PSI 口径。验证：`tests/test_models_cv.py` 新增 CV 守卫 11 例、`tests/test_models_walkforward.py` 新增 drift 守卫 9 例；models 目录 42 passed 无回归。**剩余风险**：CV 折数/embargo 宽度默认值仍为经验默认，未由 CLEAN 集样本量与标签视野校准；PSI 分桶数与命中率窗口尚未接入实盘漂移告警调度链。
- ✅ **#217 基线模型与二级标签参数有限性/整数守卫（研究层）**：`core/models/baseline.py` 的 `LogisticBaseline` 补 `C` 有限且 >0、`max_iter` ≥1 整数（排除 bool/浮点/字符串）、`tol` >0 有限；`RidgeBaseline` 补 `alpha≥0` 有限。`core/models/meta_label.py` 的 `MetaLabeler` 补 `q_lo/q_hi` 有限性后保留 `0≤q_lo<q_hi≤1` 口径。不改变既有可学习性、概率归一与 k∈[0,1] 行为。验证：`tests/test_models_baseline.py` 新增基线守卫 10 例、`tests/test_models_walkforward.py` 新增二级标签守卫 5 例；models 目录 58 passed 无回归。**剩余风险**：正则强度 C/alpha、迭代上限与 tol 默认值仍为经验默认，未由 CLEAN 集样本量与收敛曲线校准；基线模型尚未接入训练管线的 OOS 守门判据。
- ✅ **#218 压力测试器权益/杠杆有限性守卫（研究层）**：`core/backtest/stress_test.py::StressTester` 构造补 `initial_equity` 有限且 >0、`max_leverage` 有限且 >0 守卫，非法（零/负/NaN/Inf）抛带上下文 ValueError。不改变既有预设情景回放、低敞口存活与高敞口爆仓/熔断断言。验证：`tests/test_backtest/test_stress_test.py` 新增构造守卫 8 例；stress 目录 17 passed 无回归。**剩余风险**：杠杆上限与初始权益默认值仍为经验默认，未按账户真实风险承受度校准；压力情景的价格冲击/波动率倍数为内置预设，尚未接入可审计的历史尾部分布复核。
- ✅ **#219 实验优化器配置/评分阈值有限性区间守卫（研究层）**：`core/experiment/auto_optimizer.py` 的 `OptimizationConfig` 补非空策略名、`max_trials`≥1 整数（排除 bool/浮点）、`min_sharpe`>0 有限、过拟合评分 ∈[0,1]、`ab_alpha`∈(0,1)、探索率 ∈[0,1]、`random_seed` 整数；`MultiArmedBandit` 探索率 ∈[0,1]；`CandidateScorer` 的 `min_sharpe`/`max_dd` >0 有限（避免除零/除负）。不改变既有探索/利用选择、候选评分与合格判定口径。验证：`tests/test_experiment/test_auto_optimizer.py` 新增配置/评分守卫 29 例；experiment 目录 37 passed 无回归。**剩余风险**：min_sharpe、过拟合上限、显著性水平 alpha 与探索率默认值仍为经验默认，未由 CLEAN/OOS 样本分布与功效分析校准；优化器闭环仍接模拟回测，未接真实回测与过拟合检测底座。
- ✅ **#220 生命周期上线准则/监控阈值有限性区间守卫（研究层）**：`core/experiment/strategy_lifecycle.py` 的 `LaunchCriteria` 补 `min_sharpe`/`max_drawdown`>0 有限、`min_trades`/`min_live_days`≥1 整数（排除 bool/浮点）、显著性 ∈(0,1)、过拟合分位 ∈[0,1]；frozen `WatchThresholds` 补成交率/容量/相关/Sharpe 与胜率比率 ∈[0,1]、滑点 ≥0、回撤 >0 有限、衰减样本 ≥1 整数、期望值有限。不改变既有 crowding/decay/退役推荐口径。验证：`tests/test_experiment/test_strategy_lifecycle.py` 新增准则/阈值守卫 41 例；lifecycle 目录 69 passed 无回归。**剩余风险**：上线 Sharpe/回撤/交易笔数/模拟天数与监控拥挤/衰减阈值默认值仍为经验默认，未由 OOS 分布与样本量功效校准；生命周期状态机尚未接后端真实策略档案与灰度发布链路。
- ✅ **#221 复盘触发阈值有限性/方向守卫与重复口径去重（研究层）**：`core/audit/evolution_rules.py` 的 `ReviewThresholds`（frozen 底座）补 `single_loss_r_multiple` 有限且为负（亏损 R 阈值方向）、`consecutive_losses`≥1 整数（排除 bool/浮点）、`daily_loss_pct`>0 有限；`core/audit/review_monitor.py` 删除本地冗余裸类，改为导入底座阈值，消除双份口径漂移。不改变既有单笔大亏损/连续亏损/单日亏损占比三条触发判定口径。验证：`tests/test_audit/test_evolution_rules.py` 新增阈值守卫 10 例；audit 目录 123 passed，ReviewMonitor 导入链与默认构造无回归。**剩余风险**：-3R/5 笔/5% 触发阈值默认值仍为经验占位，未见 CLEAN/OOS 分布校准；复盘自动写库仍留在编排边界，未在纯函数底座内触发 DB 写入。
- ✅ **#222 动态分配器交易数/探索天数/探索权重守卫（研究层）**：`core/risk/dynamic_allocator.py` 的 `DynamicAllocator` 构造补 `min_trades_for_score`/`explore_period_days`≥1 整数（排除 bool/浮点）、`base_explore_weight`∈[0,1] 有限。不改变既有三态得分、探索期权重与 active 权重归一化口径。验证：`tests/test_risk/test_dynamic_allocator.py` 新增构造守卫 10 例；allocator 目录 29 passed 无回归。**剩余风险**：探索天数、最少交易数与探索期基础权重默认值仍为经验默认，未由样本量功效与策略分散度校准；分配器仅输出权重建议，尚未接组合波动率目标与独立风险否决链。
- ✅ **#223 策略匹配器策略列表类型与切换阈值守卫（研究层）**：`core/registry/strategy_matcher.py` 的 `StrategyMatcher` 构造补 `strategies` 必须为列表（空列表合法退化，返回空排名/空组合）、`switch_threshold`∈[0,1] 有限（防抖动切换得分差阈值）。不改变既有适配度打分、排序、防抖动与跨聚类分散口径。验证：`tests/test_registry/test_strategy_matcher.py` 新增构造守卫 8 例；matcher 23 passed 无回归。**剩余风险**：`StrategyProfile` 档案字段（expected_sharpe/max_drawdown/risk_level 等级）尚未在数据载体层做有限性/区间守卫；匹配器仍未接注册中心真实策略档案（#156 运行时接线属后端/DB 边界）。
- ✅ **#224 验证中间件风险闸阈值有限性区间守卫（研究层）**：`core/integration/verification_middleware.py` 的 `VerificationMiddleware` 构造补六个闸阈值——过拟合 PBO 线、漂移警告线、漂移拒绝线、压力存活下限、最大总敞口、单聚类敞口——均 ∈[0,1] 有限（排除 bool/NaN/Inf/越界）。默认值与既有过拟合拦截/漂移降级/压力拒绝/敞口超标判定口径不变。验证：`tests/test_verification_middleware.py` 新增构造守卫 19 例；中间件 30 passed 无回归。**剩余风险**：未守阈值间有序关系（拒绝线 ≤ 警告线、单聚类敞口 ≤ 总敞口）；六个默认闸阈值仍为经验占位，未由 CLEAN/OOS 分布校准；中间件尚未接入后端上线/下单决策链。
- ✅ **#225 AB 测试配置效应/显著性/功效/周期守卫（研究层）**：`core/experiment/ab_test.py` 的 `ABTestConfig` 补对照/实验组名非空、`min_detectable_effect`>0 有限、`alpha`/`power`∈(0,1) 开区间、实验周期天数 ≥1 整数且 min≤max、`risk_aversion`≥0 有限。不改变既有样本量公式、t 检验/Bootstrap/Bayes 结论与多重检验校正口径。验证：`tests/test_experiment/test_ab_test.py` 新增配置守卫 21 例；AB 28 passed 无回归。**剩余风险**：`required_sample_size` 纯函数的 `baseline_std` 尚未做有限性/非负守卫；alpha/power 默认值与最短/最长实验周期仍为经验默认，未见样本量功效与 OOS 校准；框架结论尚未接上线审批链路。
- ✅ **#226 桥接配置超时/重试/退避参数守卫（集成层配置）**：`core/integration/bridge.py` 的 `BridgeConfig` 补 `base_url` 非空字符串、`timeout_seconds`>0 有限、`max_retries`≥0 整数（排 bool/浮点）、`retry_backoff`≥0 有限、`request_log_enabled` 为布尔值。守卫仅在配置 dataclass 构造层生效，不发起任何 HTTP 请求；既有重试次数、退避与降级容错口径不变。验证：`tests/test_integration_bridge.py` 新增配置守卫 13 例；桥接 25 passed 无回归。**剩余风险**：未校验 `base_url`/`api_prefix` 的 URL 形态与 scheme；`auth_token` 为空/非字符串未约束；桥接底层 `requests.Session` 与真实连通性、超时重试上限未在单测覆盖（依赖外部服务，未验证）。
- ✅ **#227 绩效指标年化周期/无风险利率参数守卫（研究层纯函数）**：`core/backtest/metrics.py` 的 `compute_metrics` 补 `bars_per_year`≥1 整数（排 bool/浮点/0/负）、`risk_free` 有限数值（可负，排 bool/NaN/Inf）。年化周期仍由调用方按周期 config 注入，不写死；既有 Sharpe/Sortino/MaxDD/Calmar/ProfitFactor/胜率/期望值口径不变。验证：`tests/test_backtest_metrics.py` 新增参数守卫 8 例；指标 13 passed 无回归。**剩余风险**：未校验 `trades` 元素结构与 `pnl_usd` 数值有限性；权益曲线本身的空值/非正未在本函数兜底（由上游数据清洗保证）；年化口径 `bars_per_year` 与实际周期匹配性未机检。
- ✅ **#228 过拟合检验年化/试验次数/折数/净化比例守卫（研究层纯函数）**：`core/backtest/overfitting.py` 公共纯函数补 `bars_per_year`≥1 整数、`risk_free`/偏度/峰度有限、`trials`≥1 整数、`max_combinations`≥1 整数、CPCV `n_splits`≥2 整数且 `purge_fraction`∈[0,1)。DSR 多重检验修正、PBO-CSCV 枚举、CPCV 净化/embargo 与诊断评分卡口径不变；PBO 既有 DataFrame 类型/test_size∈(0,1)/NaN-Inf 校验保留。验证：`tests/test_backtest/test_overfitting.py` 新增参数守卫 27 例；过拟合 52 passed 无回归。**剩余风险**：未守 PBO `n_splits` 数值下限（块数不足由既有降级返回 0.5 兜底）；DSR 偏度/峰度若由调用方外部传入，其分布合理性未校验；CPCV 折数与样本长度匹配性仍靠既有 fold_size<30 降级。
- ✅ **#229 triple-barrier 屏障倍数/持有 bar 数守卫（研究层纯函数）**：`core/models/labels.py` 的 `triple_barrier_labels` 补 `tp_mult`/`sl_mult` 正有限数值（排 bool/NaN/Inf/≤0）、`max_holding_bars`≥1 整数（排 bool/浮点/0/负）。标签方向、atr0 入场冻结、同 bar 双触保守按止损先触、时间屏障归 0 口径不变；bars/atr 长度一致性校验保留。验证：`tests/test_models_labels.py` 新增参数守卫 11 例；标签 21 passed 无回归。**剩余风险**：未校验 `bars` 元素 OHLC 数值有限性（沿用上游数据清洗）；屏障倍数与 ATR 量纲匹配性未机检；embargo 宽度须≥持有 bar 数的约束由调用方配置保证，函数内未交叉校验。
- ✅ **#230 特征面板预热 bar 数整数守卫（研究层纯函数）**：`core/features/base.py` 的 `build_feature_panel` 补 `warmup_bars`≥0 整数（排 bool/浮点/负/非字符串）。`available_at` 契约、前 N 根预热行保留 NaN、逐点重算一致性口径不变；特征函数自身的 as_of 因果装饰器校验保留。验证：`tests/test_features_causal.py` 新增参数守卫 5 例；因果面板 11 passed 无回归。**剩余风险**：未校验 `features` 字典的值是否为可调用特征函数；各底层特征 period/window/k 既有下限比较未统一排 bool/浮点/NaN；预热长度与特征所需最小样本量的匹配性由调用方配置保证。
- ✅ **#231 regime 权重分位阈值/Hurst 判据有限性守卫（研究层纯函数）**：`core/features/regime.py` 的 `regime_weights` 补 `adx_q_lo`/`adx_q_hi`/`mr_hurst_thresh` 有限数值（排 bool/NaN/Inf），保留 `adx_q_hi > adx_q_lo` 分布分位单调性校验。信号值 `adx_val`/`hurst_val`/`atr_pct` 的 NaN 降级均匀分布口径不变；三权重归一化、clip[0,1]、全 NaN 均匀兜底口径不变。验证：`tests/test_features_regime.py` 新增参数守卫 11 例；regime 18 passed 无回归。**剩余风险**：信号值 Inf 未拦截（沿用既有 NaN 降级口径，Inf 进入 clip 计算）；分位阈值是否真正来自 CLEAN 分布校准由调用方/校准脚本保证，函数内不回溯数据；Hurst 判据理论区间 [0,1] 未机检。
- ✅ **#232 ATR Wilder 平滑窗长整数守卫（研究层纯函数）**：`core/features/atr.py` 的 `wilder_atr` 补 `period`≥2 整数（排 bool/浮点/NaN/非字符串），复用 `base._min_int`。history 长度不足返回 NaN、TR 三式取最大、Wilder RMA 平滑与 atr0 入场冻结口径不变；@as_of 前视/时序契约校验保留。验证：`tests/test_features_causal.py` 新增参数守卫 6 例；因果面板 17 passed 无回归。**剩余风险**：同目录 volatility/structure/regime 底层 window/k/period 仍仅做下限比较，未统一排 bool/浮点/NaN；ATR 所用 history 是否属于 CLEAN 集由调用方集合分离纪律保证，函数内不校验归属。
- ✅ **#233 已实现波动率窗长/分位最小历史整数守卫（研究层纯函数）**：`core/features/volatility.py` 的 `realized_vol` 补 `window`≥2 整数、`atr_percentile_rank` 补 `min_history`≥0 整数（排 bool/浮点/NaN），复用 `base._min_int`。history 不足返回 NaN、history/atr_series 长度一致性、当前 ATR 非有限降级、expanding 分位口径不变。验证：`tests/test_features_regime.py` 新增参数守卫 10 例；regime 28 passed 无回归。**剩余风险**：`atr_percentile_rank` 的 `period` 形参当前未被函数体引用（死参数，未守）；对数收益 std 的 ddof=1 口径与年化缩放由调用方配置；分位分布是否仅用 CLEAN 集由调用方集合分离纪律保证。
- ✅ **#234 Donchian 窗长/swing 确认 k 整数守卫（研究层纯函数）**：`core/features/structure.py` 的 `donchian_position` 补 `window`≥2 整数、`nearest_confirmed_swing`/`detect_swing_points` 补 `k`≥1 整数（排 bool/浮点/NaN/非字符串），复用 `base._min_int`；`get_market_structure`/`market_structure_at` 经委托 `detect_swing_points` 覆盖。swing 需 k 根确认、confirmed_at 因果口径、@as_of 前视/时序契约校验保留。验证：`tests/test_features/test_structure.py` 新增参数守卫 21 例；structure 34 passed 无回归。**剩余风险**：`detect_bos`/`detect_choch` 复用 swings 列表不再独立校验 k；结构区间是否仅在 KNOWN 集构建由调用方 splits 层集合分离纪律保证，函数内不校验归属。
- ✅ **#235 ADX 周期/Hurst 窗长整数守卫（研究层纯函数）**：`core/features/regime.py` 的 `adx` 补 `period`≥2 整数、`hurst_exponent` 补 `window`≥2 与 `min_window`≥1 整数且 `min_window≤window`（排 bool/浮点/NaN/非字符串），复用 `base._min_int`。history 不足返回 NaN、R/S 分段估计、Hurst 输出 clip[0,1] 口径不变；@as_of 前视/时序契约保留。验证：`tests/test_features_regime.py` 新增参数守卫 15 例；regime 43 passed、regime_classifier 58 passed 无回归。**剩余风险**：ADX/Hurst 所用 history 是否属于 CLEAN 集由调用方集合分离纪律保证；Hurst R/S 最小 lag 数与 `len(rs)≥4` 降级阈值为算法内部常量，未参数化。
- ✅ **#236 对账容忍度/净额平仓阈值有限性区间守卫（执行层纯函数）**：`core/execution/reconcile.py` 的 `Tolerance` 构造补 `qty_abs`≥0 有限、`qty_rel`∈[0,1] 有限；`aggregate_fills_to_positions` 补 `flat_net`≥0 有限（排 bool/NaN/Inf/负/非数值）。frozen dataclass 只校验不回写；订单/持仓按 id/symbol 匹配、缺失/多余/重复标记、非法行进 dropped 留痕口径不变。验证：`tests/test_execution/test_reconcile.py` 新增参数守卫 16 例；reconcile 44 passed 无回归。**剩余风险**：容忍度默认值（1e-6/1e-4）与 flat_net 1e-12 为占位常量，正式取值须经分布校准；对账仅做纯比较，enforce 触发 KillSwitch 的执行动作由调用方决定是否接入。
- ✅ **#237 审计快照概率向量有限性/归一化守卫（选择层纯函数）**：`core/selector/audit.py` 的 `SelectionRecord` 构造补 `regime_probs` 逐个有限非负且和为 1（容差 1e-6），`strategy_weights` 补逐个有限显式校验（排 bool/NaN/Inf）。权重非负/和为 1、blend_strength 有限≥0、ts_utc/state/dict 非空既有口径不变；JSONL 落盘/读回/回放重算交叉校验逻辑不变。验证：`tests/test_selector_audit.py` 新增参数守卫 8 例；selector audit/blend 13/11 passed 无回归。**剩余风险**：概率三键归属与 regime 状态一致性由调用方分类器保证，快照层不校验键集合；概率向量和为 1 的容差 1e-6 与权重同口径，未按概率精度收紧。
- ✅ **#238 压力测试敞口/快析指标有限性区间守卫（回测层纯函数）**：`core/backtest/stress_test.py` 的 `current_exposure` 守 ∈[0,1] 有限（run_scenario 入口，覆盖 run_all_presets/stress_report 调用链）；`core/backtest/integration.py` 补 `analyze` 敞口 ∈[0,1] 有限、`quick_analyze` 的 sharpe 有限（可负）、max_drawdown≥0 有限、敞口 ∈[0,1] 有限（排 bool/NaN/Inf/越界）。构造 equity/leverage 既有守卫不变；压力情景损失模型与风险评分/分级口径不变。验证：`tests/test_backtest/test_stress_test.py` 新增敞口守卫 6 例、`test_integration.py` 新增 12 例；stress/integration 43 passed 无回归。**剩余风险**：敞口 [0,1] 为占权益比例口径，叠加杠杆后的名义敞口上限未在此层约束；压力损失模型为简化近似（滑点/跳空系数为内部常量），非真实经纪商撮合。
- ✅ **#239 注册表性能快照指标/模型种子有限性区间守卫（注册层纯数据类）**：`core/registry/strategy_registry.py` 的 `PerformanceSnapshot` 构造补守卫——sharpe/sortino/calmar/avg_r_multiple/deflated_sharpe 有限（可负），max_drawdown/profit_factor 非负有限，win_rate/pbo∈[0,1] 有限，total_trades 非负整数（排 bool/浮点/NaN/Inf/越界）；`core/registry/model_registry.py` 的 `ModelVersion.seed` 守可选非负整数（None 或 int≥0，排 bool/浮点/字符串/负数）。状态机流转、冻结防改 metrics、序列化往返口径不变；metrics/hyperparams 自由 dict 键值口径仍由上层负责。验证：`test_strategy_registry.py` 新增快照守卫 21 例、`test_model_registry.py` 新增种子守卫 7 例；registry 目录 90 passed 无回归。**剩余风险**：盈亏比/卡玛等指标上限未设界（极端值由上层分布校准拦截）；win_rate/pbo [0,1] 容差取硬边界 0/1，未留浮点容差；自由 dict 内的指标数值未逐个强守。
- ✅ **#240 K线形态比例阈值有限性区间守卫（特征层纯函数）**：`core/features/patterns.py` 入口补守卫——shadow_ratio/max_upper_ratio/max_lower_ratio/tolerance_ratio/body_ratio 非负有限，min_penetration_ratio∈[0,1] 有限（排 bool/NaN/Inf/负数/越界）；方向枚举、退化返回 False、`@as_of` 因果口径不变。验证：`test_patterns.py` 新增比例守卫参数化用例（hammer 6、shooting_star 3、doji 3、penetration 6、body_ratio 6 + 2 合法自定义比例）；features 目录 103 passed 无回归。**剩余风险**：min_penetration_ratio 当前未参与刺透/乌云盖顶判定（函数体仍按实体中点固定 50% 比较），守卫仅约束入参类型与区间，未改变判定逻辑；body_ratio 等比例上限未设界；direction 非法值走 bearish 容错分支，未做枚举强校验。
- ✅ **#241 回测引擎止损候选/ATR 窗/演示策略构造参数守卫（回测层纯函数）**：`core/backtest/engine.py` 内部纯函数入口补守卫——`_trailing_candidate`/`_breakeven_candidate` 守 direction∈{+1,-1}、offset_r/entry_dist 非负有限、价格有限；`_wilder_atr` 守 n≥1 整数（排 bool/浮点/0/负）；`DemoBreakoutStrategy` 构造守 lookback/atr_n≥1 整数、entry_dist_mult 非负有限。主循环 risk_cfg dict 消费口径、因果顺序、止损单调规则不变。验证：`test_backtest_engine.py` 新增候选函数方向/偏移/距离守卫 14 例、ATR 窗 4 例、演示策略构造 7 例 + 1 合法；backtest 目录 144 passed 无回归。**剩余风险**：run_backtest 的 risk_cfg 数值（initial_equity/risk_pct/kelly_cap/lot 规格等）仍由上层配置注入，本层未逐个强守；`_Signal`/`Position` 数据类字段未在构造处回写校验；演示策略非生产专家，参数口径以生产策略基类 schema 为准。
- ✅ **#242 regime 阈值快照有限性/区间守卫（规则层纯快照）**：`core/regime/rules.py` `RuleThresholds` frozen 快照 `__post_init__` 补守卫——adx/atr 四条阈值与 q_lo/q_hi 必须为有限数值（排 bool/NaN/Inf），adx_q_hi>adx_q_lo、atr_q_hi>atr_q_lo，分位级别满足 0<q_lo<q_hi<1；`derive_thresholds` 分布派生与 `rule_state_and_soft_probs` 规则判定/降级口径不变。验证：`test_regime_rules.py` 新增有限性 5 例、退化带宽 3 例、非法分位级别 4 例 + 1 合法；regime 三文件 57 passed 无回归。**剩余风险**：阈值仍由 CLEAN 段经验分位派生，守卫只约束快照字段类型与次序，不校验阈值数值相对业务分布是否合理；RuleThresholds 落盘/反序列化路径未在本快照层复核（沿用 derive 产出口径）。
- ✅ **#243 决策解释器信号/置信度/贡献分解守卫（可解释层纯逻辑）**：`core/explainability/decision_explainer.py` `FeatureContribution.__post_init__` 守 name/explanation 非空字符串、value/contribution 有限（排 bool/NaN/Inf）、direction∈{pushes_long,pushes_short,neutral}；`build_trace` 入口守 strategy_name/strategy_version 非空、raw_signal 有限且 ∈[-1,1]、confidence 有限且 ∈[0,1]、final_decision 必须为 `DecisionOutcome` 枚举；解释/反事实生成口径不变，模块无 DB/网络/下单。验证：`test_decision_explainer.py` 新增贡献分解 5 例、trace 入参 9 例 + 1 合法；explainability 目录 19 passed 无回归。**剩余风险**：`data_inputs`/`features`/`counterfactuals` 为自由 dict/list，未逐键守值类型；`filtered_signal` 由 raw_signal 按风控原因数线性折算，折算系数 0.1 为模块内演示口径，未参数化；解释文案与反事实阈值（0.3/0.5）为启发式，未做业务校准。
- ✅ **#244 行情校验器窗长/倍数参数守卫（数据层纯校验）**：`core/data/validator.py` `validate_bars` 入口守 `bar_minutes`/`outlier_window` 为 ≥1 整数（排 bool/浮点/非 int）、`outlier_mult` 为正的有限数值（排 bool/NaN/Inf/非正）；OHLC 一致性、单调时间戳、缺口检测、离群点 trailing std 判定口径不变，函数无 IO/DB。验证：`test_data_loader.py` 新增非法参数 13 例 + 1 合法；data 三文件 39 passed 无回归。**剩余风险**：校验器只守调用方注入的窗长/倍数，未复核 bar 数量相对窗长是否充足（样本不足时离群点分支自然跳过）；`server_offset_hours`/`spread_points` 等 Bar 字段口径沿用 bar.py schema，本层未重复强守。**待人工确认（历史缺口）**：`.gitignore` 第 33 行 `data/` 规则误伤整个 `core/data/` 代码包——除本轮强制纳入的 `validator.py` 外，`bar.py`/`loader.py`/`splits.py`/`synthetic.py`/`timezone.py` 均未被 git 跟踪，远端仓库缺数据层基础模块；是否将规则收敛为根目录 `/data/`（仅忽略行情数据 CSV/parquet）需人工确认，本轮未改 .gitignore。
- ✅ **#245 策略信号快照有限性/类型守卫（策略层纯快照）**：`core/strategies/signal.py` `StrategySignal.__post_init__` 守 signal_id/expert/strategy_version 非空字符串、direction 为 int 且排 bool 且 ∈{1,-1}、price_ref/atr0/entry_dist 为有限正数（排 bool/NaN/Inf/非正）、meta_p 为 None 或有限且 ∈[0,1]、regime_weights 为 dict；时区感知校验与既有方向/正值口径不变，快照无 IO/DB/下单。验证：`test_strategies_signal.py` 新增非法字段 19 例 + meta_p 区间/可空合法 2 例；strategies 六文件 96 passed 无回归。**剩余风险**：`regime_weights` 仅守 dict 类型，键名与权重值∈[0,1]/归一化口径由上层策略负责；`l1_in_zone` 布尔未做类型强校验（鸭子消费允许 truthy）；信号 price_ref 未复核与 atr0/entry_dist 的相对量级一致性。
- ✅ **#246 训练管线配置快照参数守卫（模型层纯配置）**：`core/models/pipeline.py` `PipelineConfig.__post_init__` 守 model_id/version 非空字符串、feature_names 非空字符串列表、tp_mult/sl_mult 有限正数、max_holding_bars≥1 整数、embargo_bars/warmup_bars≥0 整数、n_splits≥2 整数、positive_label∈{0,1}、seed 为 None 或整数（排 bool/浮点/NaN/Inf）；frozen 只校验不回写，标签/CV/拟合/快照口径不变，管线无 DB/权重落盘。验证：`test_models_pipeline.py` 新增非法配置 23 例 + 1 合法；models 五文件 103 passed 无回归。**剩余风险**：`hyperparams`/`label_spec`/`metrics` 为自由 dict，键值口径由模型后端与注册表负责，未逐键强守；`model_factory` 可调用性未在构造处探测（延迟实例化，坏工厂在 run_training 折内拟合时才暴露）；embargo_bars≥label_window 的跨字段次序校验沿用下游 `purged_walk_forward`。
- ✅ **#247 滑点纯函数入参有限性/非负守卫（回测层纯公式）**：`core/backtest/costs.py` 模块级新增 `_nonneg_finite`/`_ratio`，在 `sqrt_slippage`/`volume_impact_slippage`/`volatility_adjusted_slippage`/`estimate_total_slippage` 入口守基础滑点/冲击系数/手数/成交量/ATR/波动率为有限非负（排 bool/NaN/Inf/负值），订单占比裁剪到 [0,1]；零成交量放大 3 倍、零均波动短路返回基础滑点两条既有降级分支保留，公式与点差口径不变，纯函数无 IO/DB/下单。验证：`test_backtest/test_slippage.py` 新增非法入参 19 例 + 2 降级合法；backtest 目录 149 passed 无回归。**剩余风险**：`volatility_adjusted_slippage` 的 `atr` 形参未参与公式计算（历史遗留，仅守类型有限性）；`current_vol/avg_vol` 比值>0 但 `np.log` 对极小正值产生大负值的极端值未截断；成本点差三档单调性仍由 `tiers_valid()` 显式调用方判定，构造处不强制。
- ✅ **#248 回测-压力集成器权益/回撤参数守卫（回测层聚合）**：`core/backtest/integration.py` `BacktestStressIntegration.__init__` 守 `initial_equity` 为 >0 有限（排 bool/NaN/Inf/≤0，口径与下游 `StressTester` 对齐）；`analyze` 入口守 `backtest_metrics` 为 dict、`max_drawdown` 为有限非负（缺省 0.15 保留，浅拷贝后回填不改动调用方原 dict）；敞口 [0,1]、sharpe/快速分析既有守卫不变，聚合纯逻辑无 IO/DB/下单。验证：`test_backtest/test_integration.py` 新增非法权益 5 例、非法回撤 3 例、非 dict 1 例 + 缺省回撤合法 1 例；backtest 目录 159 passed 无回归。**剩余风险**：`backtest_metrics` 除 `max_drawdown` 外的键值（sharpe/存活率等）仍为自由 dict，未逐键强守；风险评分 40/40/20 权重与等级阈值 80/60/40 为模块内既有常量，未参数化；`stress_results` 列表长度为 0 时 `max(...)` 会抛 `ValueError`，依赖 `run_all_presets` 恒返回非空。
- ✅ **#249 Decision 审计快照字段类型/有限性守卫（审计层冻结快照）**：`core/audit/record.py` 模块级新增 `_finite`/`_nonempty_str`；`Decision.__post_init__` 守 `decision_id`/`model_version`/`decision_rule_version` 为非空字符串、`accepted` 为 bool（排非布尔）、`final_signed_lots` 为有限数值（排 bool/NaN/Inf）、`r_multiple_at_close` 若非 None 须有限；既有 `threshold_dataset∈{CLEAN,KNOWN}` 与 accepted↔lots 一致不变量保留，frozen 只校验不回写，快照无下单/仓位改写。验证：`test_audit_record.py` 新增空版本/ID 3 例、accepted 非 bool 1 例、lots 非法 4 例、r_multiple 非法 2 例 + 带 r_multiple 合法 1 例；audit 目录 141 passed、跨层 608 passed 无回归。**剩余风险**：`feature_snapshot`/`signal`/`risk_state` 为鸭子序列化对象，内部数值有限性由各自快照守卫负责，本层不递归校验；`reject_reason` 在 accepted 时为 None、rejected 时非空的配对关系未强守；`write_decision` 落盘路径/编码沿用既有 JSONL 追加口径，未做目录存在性校验。
- ✅ **#250 决策回放比对容差/记录类型守卫（审计回放纯函数）**：`core/audit/replay.py` 模块级新增 `_nonneg_finite`（排 bool/NaN/Inf/负值，math.isfinite）；`replay_decision` 入口守 `rec` 为 dict、`tol` 为有限非负比对容差；五要素重算与 accepted↔lots=0 既有不变量保留，回放纯逻辑无 IO/DB/下单（`read_decisions` 读 JSONL 沿用既有路径）。验证：`test_audit_replay.py` 新增非 dict 1 例、tol 非法 4 例（nan/inf/负/True）+ tol=0 合法 1 例；audit 目录 147 passed、跨层 553 passed 无回归。**剩余风险**：`feature_snapshot` 各 sizing 键值仍按 `float(...)` 直接转换，非法字符串/NaN 会向下游 `target_lots` 透传，未在回放层逐键强守；`read_decisions` 未校验空文件/非 JSON 行以外的 schema；`tol=0` 时浮点累积误差可能把合法重算误判为不一致，依赖 sizing 步长与手数取整口径对齐。
- ✅ **#251 RiskState 风控快照字段类型/有限性守卫（风控层冻结快照）**：`core/risk/state.py` 模块级新增 `_finite`/`_positive`/`_nonneg_int`（math.isfinite，排 bool/非 int/float/NaN/Inf）；`RiskState.__post_init__` 守 `equity`/`atr0`/`stop_price` 有限、`entry_dist`/`drawdown_tier` 为 >0 有限、`heat_units` 为非负整数、`circuit_state∈{normal,breaker,cooldown}`、`extra` 为 dict；入场冻结 `atr0/entry_dist` 与可变 `equity/stop_price` 既有语义不变，快照纯逻辑无 IO/DB/下单。验证：`tests/test_risk/test_state.py` 新增 entry_dist 非法 4 例、equity 非法 3 例、heat_units 非法 3 例、circuit_state 非法 1 例、tier 非法 3 例、extra 非 dict 1 例 + breaker 合法 1 例；risk 目录 163 passed、跨层 513 passed 无回归。**剩余风险**：`entry_dist>0` 为构造期硬约束，极端零波动场景若上游传 0 会被拒而非降级；`equity` 仅守有限未守 ≥0（允许负权益快照透传给下游）；`stop_price` 未与 entry_dist/方向做单调一致性校验（止损单调由 `stops.update_stop` 链路负责）；`extra` 内部键值未递归校验有限性。
- ✅ **#252 组合策略风险快照字段类型/有限性守卫（组合风控层）**：`core/risk/portfolio_risk.py` 模块级新增 `_finite`/`_nonneg_finite`/`_nonneg_int`/`_nonempty_str`（math.isfinite，排 bool/非 int/float/NaN/Inf）；`StrategyRisk.__post_init__` 守 `strategy_id` 非空串、`risk_per_trade`/`current_exposure` 非负有限、`correlation_cluster` 非负整数、`daily_pnl` 有限（可负盈亏）；`set_equity` 守权益有限且 >0；既有 `PortfolioRiskConfig` 三阈值与 `planned_risk` 守卫（#190）不变，纯逻辑无 IO/DB/下单。验证：`tests/test_risk/test_portfolio_risk.py` 新增 ID 非法 3 例、risk_per_trade 非法 2 例、exposure 非法 2 例、cluster 非法 3 例、daily_pnl 非法 2 例、equity 非法 3 例；文件 45 passed、risk 目录 + 跨层 481 passed 无回归。**剩余风险**：`risk_per_trade`/`current_exposure` 仅守非负有限，未守 ≤1（比例上限依赖 config 阈值在 `can_open_new_position` 链路把关）；`correlation_cluster` 未校验是否落在已注册聚类集合；`daily_pnl` 未按权益归一化校验量级；`set_equity` 未与既有持仓敞口重算一致性，仅单点校验。
- ✅ **#253 RegimeOutput 版本/数据集/降级标志类型守卫（regime 审计快照）**：`core/regime/output.py` 模块级新增 `_nonempty_str`；`RegimeOutput.__post_init__` 在既有 state∈STATES、probs 覆盖三状态/∈[0,1]/归一≈1 校验之上，补守 `version`/`threshold_dataset` 非空串、`degraded` 为 bool（排 int/str/None）；frozen 快照只校验不回写，纯逻辑无 IO/DB/下单。验证：新建 `tests/test_regime_output.py`，version 非法 4 例、dataset 非法 3 例、degraded 非法 4 例 + 合法 degraded=True 对照；output/blend 18 passed、跨层 regime+selector+risk+audit 390 passed 无回归。**剩余风险**：`threshold_dataset` 仅守非空串，未强制枚举 ∈{CLEAN,KNOWN}（集合分离口径依赖调用方/分类器约定）；`degraded=True` 时未强制 probs 为均匀分布（降级产物语义由分类器层保证）；probs 键值未逐键校验类型，NaN/Inf 由 `0<=v<=1` 比较兜底；`version` 未做格式/版本号一致性校验。
- ✅ **#254 知识匹配权重/阈值类型与区间守卫（审计知识检索纯函数）**：`core/audit/knowledge_match.py` 模块级新增 `_ratio`（math.isfinite，排 bool/非 int/float/NaN/Inf，并守 [0,1]）；`similarity` 的 `tag_weight` 与 `find_similar` 的 `threshold`/`tag_weight` 改走同一辅助；既有 Jaccard/文本重合纯计算口径与空条目降级不变，无 IO/DB/向量服务。验证：`tests/test_audit/test_knowledge_match.py` 新增 tag_weight 非比 5 例、threshold 非比 4 例、find_similar tag_weight 非比 4 例；文件 29 passed、跨层 audit+risk+selector 346 passed 无回归。**剩余风险**：`entries` 序列本身未校验类型（非序列会在迭代处抛原生 TypeError）；条目内 tags/文本字段未递归校验有限性；`tag_weight` 与 `threshold` 为独立注入值，未校验二者与综合分口径的联动一致性；相似度分数未做归一化容差复核。
- ✅ **#255 模型版本快照字段类型/容器守卫（registry MLOps 快照）**：`core/registry/model_registry.py` 模块级新增 `_nonempty_str`/`_opt_str`/`_dict`/`_str_list`；`ModelVersion.__post_init__` 在既有 seed 非负整数守卫之上，补守 `model_id`/`version` 非空串、`created_at` 为 datetime、`changelog` 为 str、`feature_versions` 为非空串列表、`label_spec`/`data_range`/`hyperparams`/`metrics` 为 dict、`parent_version`/`code_commit`/`artifact_uri`/`artifact_checksum` 为 str 或 None（空串保留为缺失占位语义）；纯内存快照，不连库、不写 registry.yaml。验证：`tests/test_registry/test_model_registry.py` 新增 ID 非法 4 例、version 非法 3 例、created_at 非法 3 例、feature_versions 非法 3 例、四 dict 字段非法 4 例、可选 str 字段非法 4 例；文件 40 passed、registry 目录 111 passed 无回归。**剩余风险**：dict 字段内的键/值未递归校验类型与有限性（metrics 数值量级由部署闸/评审口径把关）；`feature_versions` 元素未校验版本号格式；`created_at` 未校验时区一致性（naive/aware 混用未拒）；`hyperparams`/`label_spec` 未做 schema 白名单约束。
- ✅ **#256 策略版本快照字段类型/容器守卫（registry 策略版本）**：`core/registry/strategy_registry.py` 模块级新增 `_nonempty_str`/`_opt_str`/`_dict`；`StrategyVersion.__post_init__` 补守 `strategy_id`/`version` 非空串、`created_at` 为 datetime、`parameters` 为 dict、`parent_version` 为 str 或 None、`changelog`/`description` 为 str、`performance` 为 `PerformanceSnapshot` 或 None；既有状态机流转与参数冻结口径不变，纯内存快照不连库。验证：`tests/test_registry/test_strategy_registry.py` 新增 ID 非法 4 例、version 非法 3 例、created_at 非法 3 例、parameters 非法 3 例、parent_version 非法 1 例、文本字段非法 2 例、performance 类型非法 1 例 + 合法对照；文件 52 passed、registry 目录 129 passed 无回归。**剩余风险**：`parameters` dict 内键值未递归校验类型/有限性与参数 schema 白名单；`description`/`changelog` 未限制长度；`created_at` 未校验时区一致性；`performance` 仅守类型，快照内部指标由 `PerformanceSnapshot` 自身守卫把关；父版本 `parent_version` 未校验是否指向已注册的真实版本。
- ✅ **#257 组合分析器收益/权重序列有限性与键对齐守卫（risk 组合诊断）**：`core/risk/portfolio_analyzer.py` 模块级新增 `_finite_num`（np.isfinite，排 bool/非 int/float/NaN/Inf）与 `_validate_inputs`；`analyze_portfolio` 前置校验 `strategy_returns`/`strategy_weights` 为 dict、收益序列为 list/tuple 且逐元素有限、权重逐值有限、权重键必须落在收益键集合内（未知权重键拒入）；既有高相关阈值越界回退默认 0.7 口径、缺省权重补 1/n、零方差退化不崩溃不变，纯内存计算无 IO/DB/下单。验证：`tests/test_risk/test_portfolio_analyzer.py` 新增 returns 非 dict 1 例、weights 非 dict 1 例、序列非序列 2 例、收益元素非法 5 例、权重非法 4 例、未知权重键 1 例；文件 30 passed、risk 目录 208 passed 无回归。**剩余风险**：权重未守非负与归一化（负权重/权重和≠1 依赖调用方与组合配置口径）；各策略收益序列长度一致性未校验（长度不齐时 corrcoef 按广播/原生错处理）；收益序列未校验最小样本长度；高相关阈值仍为回退默认而非 fail-closed 抛错；`risk_budget` 占比在组合波动率为 0 时按 0 向量兜底。
- ✅ **#258 归因结果快照字段类型/有限性守卫（audit 归因快照）**：`core/audit/attribution.py` 模块级新增 `_finite_num`（math.isfinite，排 bool/非 int/float/NaN/Inf）/`_opt_finite`/`_opt_nonneg_int`；`AttributionResult.__post_init__` 守 `side` ∈ {buy,sell}、11 个数值分量有限、entry_price>0、notional≥0、cost≥0、`holding_period` 可选有限、`holding_bars` 可选非负整数、`notes` 为 tuple[str]；既有 `split_trade_outcome` 拆分口径、聚合统计与零盈亏除零兜底不变，纯内存归因不连库/不下单。验证：`tests/test_audit/test_attribution.py` 新增 side 非法 1 例、pnl 非法 4 例、entry 越界 2 例、notional 非法 1 例、cost 非法 1 例、holding_period 非法 1 例、holding_bars 非法 3 例、notes 类型非法 2 例 + 合法对照；文件 27 passed、audit 目录 151 passed 无回归。**剩余风险**：分量之间的会计恒等式（gross=pnl+cost、alpha=gross-market、cost_component=-cost）仅由工厂保证，快照层未做残差一致性复核；`benchmark_return` 未守分数区间；`own_directional_return` 未守方向符号一致性；`holding_period` 单位与 `holding_bars` 换算关系未校验；notes 未限制条数与长度。
- ✅ **#259 前视违规记录字段类型/枚举守卫（audit 前视检测）**：`core/audit/lookahead_detector.py` 的 `LookaheadViolation.__post_init__` 守 `location`/`violation_type`/`detail` 为非空字符串（拒 None/空串/纯空白/非 str）、`severity` ∈ {high, critical}；检测器其余时间戳单调、特征-标签泄漏、滚动窗纯净度、幸存者偏差、切分分离等纯检查口径不变，纯内存检测不连库/不下单。验证：`tests/test_audit/test_lookahead_detector.py` 新增文本字段非法 12 例（3 字段 × 4 非法值）、severity 非法 4 例 + 合法对照；文件 26 passed、audit 目录 168 passed 无回归。**剩余风险**：`violation_type` 未限定到检测器实际产出的类型集合（仅文本非空）；`detail` 未限长度；检测器 `violations` 列表未去重、未限条数；时间戳/特征/标签输入的 pandas 类型与空序列边界由各 check 方法内部兜底，未在构造层统一校验。
- ✅ **#260 布林带纯函数周期/σ 守卫（strategies 均值回归）**：`core/strategies/mean_reversion.py` 的 `bollinger_bands` 复用模块级 `_period` 守 `period` 为 ≥2 整数（排 bool/非 int/过小）、`_finite` + >0 守 `sigma` 为有限正数；既有总体标准差 ddof=0 口径、空序列兜底与策略构造器守卫不变，纯序列计算无 IO/DB/下单。验证：`tests/test_strategies/test_mean_reversion.py` 新增 period 非法 5 例、sigma 非法 4 例 + 合法对照；文件 35 passed、strategies 目录 52 passed 无回归。**剩余风险**：`_finite` 经 `float(val)` 未显式排 bool（sigma=True 会被转 1.0 放行，与模块既有构造器口径一致）；closes 元素未逐值守有限性（NaN/Inf 会带入均值/标准差）；period 超过 closes 长度时按尾部切片兜底，未在函数层报错；布林带未守标准差非负以外的分布假设。
- ✅ **#261 诊断检查项/报告快照类型与区间守卫（debug 诊断框架）**：`core/debug/system_diagnoser.py` 模块级新增 `_nonempty_str`/`_dict`/`_health`；`DiagnosisCheck.__post_init__` 守 `layer`/`name`/`message` 非空字符串、`severity` 为 `Severity` 枚举、`details` 为 dict；`DiagnosisReport.__post_init__` 守 `timestamp` 非空字符串、`checks` 为 `DiagnosisCheck` 列表、`overall_health` 为 [0,100] 有限数；既有五层诊断扣分规则（warning -5/error -15/critical -30）与摘要口径不变，纯内存诊断不连库/不下单。验证：`tests/test_debug/test_system_diagnoser.py` 新增 Check 文本非法 12 例、severity 非枚举 1 例、details 非 dict 1 例；Report timestamp 非法 4 例、checks 非列表/元素非法 2 例、health 越界 5 例 + 合法对照；文件 33 passed、debug 目录 33 passed 无回归。**剩余风险**：`add_check` 扣分可使 `overall_health` 跌破 0，快照层只守构造初值区间、不拦截后续扣减演化；`details` 内键值未递归守类型；`timestamp` 仅守非空串未校验 ISO 时间格式；severity 与健康度扣分档位的映射未在快照层复核。
- ✅ **#262 性能快照 evaluated_at 时间类型守卫（registry 策略注册）**：`core/registry/strategy_registry.py` 的 `PerformanceSnapshot.__post_init__` 在既有数值/非负/区间/非负整数守卫基础上，补守 `evaluated_at` 必须为 `datetime` 实例（拒字符串/时间戳/None）；其余夏普/索提诺/卡玛/回撤/胜率/盈亏比/交易次数/R 倍数/校正夏普/PBO 口径与 `StrategyVersion.created_at` 既有守卫不变，纯内存快照不连库/不下单。验证：`tests/test_registry/test_strategy_registry.py` 新增 evaluated_at 非 datetime 4 例 + datetime 合法对照；文件 57 passed、registry 目录 134 passed 无回归。**剩余风险**：未校验时间戳是否为 UTC/时区感知（naive 与 aware 混用未拦截）；未限制未来时间；性能指标未做跨指标一致性校验（如胜率与盈亏比/交易次数的内在矛盾）；快照未冻结为只读，后续 `update_performance` 仍可覆写。
- ✅ **#263 成交模拟入参类型/有限性守卫补强（backtest 撮合）**：`core/backtest/broker.py` 的 `_finite` 在既有 `math.isfinite` 有限性检查前补排 `bool` 与非 `int/float` 入参（拒 True/字符串/None）；`simulate_fill` 方向枚举、ref_price>0、spread/slippage/佣金非负、lots>0、point_value>0 口径与点差+滑点+佣金成交价/成本折算公式不变，纯内存撮合不连库/不下单。验证：`tests/test_backtest/test_broker.py` 新增 6 个数值字段 × 3 类非法类型（bool/str/None）共 18 例 + 合法对照；文件 26 passed、backtest 目录 158 passed 无回归。**剩余风险**：`lots` 未守为整数（允许小数手数，与现货/份额口径一致，未按合约手数取整）；成交价未守有限性回算（极端 adverse 偏移下 fill_price 可为负，未在函数层拦截）；`commission_per_lot` 未与 `point_value` 做单位一致性校验；模拟成交不校验 ref_price 与 bar 收盘的因果时点。
- ✅ **#264 策略工厂注册器名称/版本/可调用守卫（strategies 运行时注册表）**：`core/strategies/registry.py` 的 `register_strategy` 补守 `name` 为非空字符串、`factory` 可调用、`version` 非 None 且转为非空字符串；既有重复注册拒绝（带已存在版本号上下文 ValueError）、未注册 KeyError（附已注册清单）、内置策略幂等登记口径不变，纯内存工厂表不连库/不下单。验证：新增 `tests/test_strategies/test_registry.py`，name 非法 5 例、factory 不可调用 4 例、version 非法 3 例 + 合法注册/解析/重复注册/未知策略对照；文件 15 passed、strategies 目录 67 passed 无回归。**剩余风险**：`version` 允许经 `str()` 转换非字符串（如整数），未限定语义化版本格式；工厂签名（入参名/返回 Strategy 协议）未在注册层校验，仅在 `get_strategy` 调用时才暴露；全局 `_REGISTRY` 非线程安全；测试临时注册用例在 finally 中清表，未模拟跨用例残留隔离。
- ✅ **#265 RiskState.stop_price 可选 None 占位与 engine 口径对齐（修 #251 遗留）**：`core/risk/state.py` 的 `stop_price` 注解改为 `Optional[float]`，守卫在 `stop_price is None`（裁决前尚未生成止损价）时放行，非 None 仍走有限数值校验；`core/backtest/engine.py` 裁决前 `base_state` 占位由 `float("nan")` 改为 `None`，成交后持仓 `pos.stop_price` 的有限止损价与止损单调移动口径不变，纯内存快照不连库/不下单。根因：#251 收紧 stop_price 有限性后，engine 初始快照仍传 nan 占位，selector walkforward smoke 两例被拒（`RiskState ... stop_price 必须为有限数值，收到 nan`）。验证：`tests/test_risk/test_state.py` 补 stop_price=None 合法对照 + nan/inf/True 非法 3 例；test_state 与两个 smoke 共 27 passed；risk+backtest 目录 370 passed 无回归。**剩余风险**：审计/replay 读取裁决前快照时需识别 `stop_price=None` 为"未设置"而非 0；字段未设默认值，调用方必须显式传（引擎与单测已显式传）；未在快照层校验 None 与 accepted=True 状态的一致性（成交后理论上应有止损价，当前由持仓链路保证）。
- ✅ **#266 shrink_params 收缩系数/参数向量类型与有限性守卫（selector 权重）**：`core/selector/weights.py` 模块级新增 `_finite_num`（排 bool/非 int-float/NaN/Inf）；`shrink_params` 补守两组映射为 dict、`lam` 为有限数值 ∈[0,1]（排 True/False/字符串/None/NaN/Inf/越界）、两组参数向量逐元素有限；既有键对齐校验与 `out = lam·global + (1-lam)·local` 收缩公式、生产路径 lam=1 口径不变，纯内存计算不连库/不下单。验证：`tests/test_selector_weights.py` 新增 lam 非法 8 例、非 dict 映射 3 例、两组元素非法 8 例 + 端点/中点既有对照；文件 29 passed、selector 四文件 50 passed 无回归。**剩余风险**：参数向量未校验取值业务区间（如阈值须 >0），仅守有限性；未校验两组参数键的取值类型一致性（同名键 global/local 量纲是否匹配）；`lam` 允许经 float 转换的 numpy 标量，未限定原生 Python 数值；收缩结果未在函数层回算有限性（两组均有限时线性组合必然有限，未做兜底断言）。
- ✅ **#267 审批结果快照字段类型守卫（control 审批闸）**：`core/control/approval_gate.py` 的 `ApprovalResult`（frozen）补 `__post_init__`：`allowed` 严格 bool、`reason_code` 非空 str、`audit` 为 dict；既有 fail-closed 判定链（read/draft 放行、scope/confirmation/live_conditions 拒绝、unknown level 拒绝）与 audit 入参记录口径不变，纯内存判定不连库/不下单。验证：`tests/test_control/test_approval_gate.py` 新增 allowed 非法 5 例、reason_code 非法 4 例、audit 非法 4 例 + 合法对照；文件 23 passed、control 目录 48 passed 无回归。**剩余风险**：守卫仅校验快照字段类型，未校验 `reason_code` 取值是否落在已知放行/拒绝码集合内（当前由内部字面量保证）；`audit` 仅守 dict 类型，未校验其内部键值类型；`ApprovalResult` 仍可被外部直接构造绕过 `evaluate_approval` 判定链，快照层不承担调用方契约校验。
- ✅ **#268 GMM 构造器 random_state/n_init 整数守卫（regime 软概率层）**：`core/regime/gmm.py` 模块级新增 `_int_param`（排 bool/非 int/越界下限）；`GMMRegimeModel.__init__` 在 sklearn 隔离检查与 n_components=3 约束基础上，补守 `random_state` 为非负整数、`n_init` 为 ≥1 整数；既有 fit 有限性/shape 校验、组件对齐与后验归一化口径不变，无库时仍先抛带上下文 RuntimeError，纯内存建模不连库/不下单。验证：`tests/test_regime_gmm.py` 新增 random_state 非法 5 例、n_init 非法 5 例 + 合法整数对照（无 sklearn 时 importorskip）；文件 16 passed、regime/features_regime 五文件 123 passed 无回归。**剩余风险**：`random_state` 未接受 sklearn 兼容的 `None`/`RandomState` 对象（签名限定 int，与既往底座一致）；整数上界未限（超大种子/n_init 仅由 sklearn 自身约束）；守卫在 `_HAS_GMM` 检查之后，缺库环境不暴露参数类型错误。
- ✅ **#269 Fill 成交快照有限性/非负兜底守卫（backtest 撮合成交）**：`core/backtest/broker.py` 的 `Fill`（frozen）补 `__post_init__`：`fill_price`/`cost`/`slippage_price` 经既有 `_finite` 守有限（排 bool/非数值/NaN/Inf），`slippage_price` 与 `cost` 守 ≥0；既有点差+滑点+佣金公式、方向枚举、ref_price>0/spread·slippage·佣金非负/lots>0/point_value>0 入参口径不变，纯内存撮合不连库/不下单。验证：`tests/test_backtest/test_broker.py` 新增三字段非有限各 5 例、负 cost/负 slippage 2 例 + 合法快照对照；文件 33 passed、backtest 目录 165 passed 无回归。**剩余风险**：快照层未校验 `fill_price>0`（卖方向极端偏移下成交价可能为负，当前由 ref>0 与偏移量级间接约束）；`commission_per_lot` 与 `point_value` 的单位一致性未做交叉校验；`lots` 仍允许小数手数（现货/份额口径，未按合约手数取整）；快照守卫为兜底，正常路径入参有限时线性组合必然有限。
- ✅ **#270 GBM 封装构造参数类型/区间/有限性守卫（models LightGBM 层）**：`core/models/gbm.py` 模块级新增 `_finite_num`（排 bool/非 int-float/NaN/Inf）、`_int_param`（排 bool/非 int/越界下限）、`_ratio_open`（(0,1] 有限）；`LightGBMWrapper.__init__` 在 lightgbm 隔离检查基础上，补守 `max_depth` 整数 3-6、`learning_rate`/`subsample` ∈(0,1] 有限、`n_estimators` ≥1 整数、`early_stopping_rounds` ≥0 整数、`random_state` 非负整数；既有 objective/subsample_freq/verbose 配置、fit 有限性与后验归一化口径不变，无库时仍先抛带上下文 RuntimeError，纯内存建模不连库/不下单。验证：`tests/test_models_gbm.py` 新增 max_depth 非法 5 例、learning_rate 非法 7 例、subsample 非法 4 例、n_estimators 非法 4 例、early_stopping 非法 4 例、random_state 非法 4 例 + 合法参数对照（无 lightgbm 时 importorskip 整文件 skip）；文件 31 passed、models 六文件 134 passed 无回归。**剩余风险**：`learning_rate`/`subsample` 只守 (0,1] 区间，未做与样本规模/树深的联动约束；`max_depth` 上界 6 为设计约束常量（非绩效阈值）；整数无上界（超大 n_estimators/early_stopping 仅由 lightgbm 自身约束）；守卫在 `_HAS_LGBM` 检查之后，缺库环境不暴露参数类型错误。
- ✅ **#271 MetaLabeler 分位参数类型/有限性/区间守卫（models 二级过滤层）**：`core/models/meta_label.py` 模块级新增 `_finite_num`（排 bool/非 int-float/NaN/Inf）；`MetaLabeler.__init__` 补守 `q_lo`/`q_hi` 为有限数值并满足 `0 ≤ q_lo < q_hi ≤ 1`；既有 meta-labeling 分位映射公式 `k = clip((p-q_lo)/(q_hi-q_lo),0,1)`、分位阈值取自训练集经验分布（非固定 0.5、不按 Sharpe 调）口径不变，纯内存建模不连库/不下单。验证：新增 `tests/test_models_meta_label.py`，q_lo 非法 7 例、q_hi 非法 7 例 + 合法分位对照；新文件 + labels 36 passed、models 七文件 149 passed 无回归。**剩余风险**：`base_model` 未做协议类型强校验（仅在 fit/predict 时调用其 `.fit/.predict_proba/.version`，协议桩由调用方保证）；分位区间端点未与训练集样本量/类别平衡做联动校验；守卫只覆盖构造期分位参数，fit 后 `_q_lo_val/_q_hi_val` 由 `np.quantile` 导出，未再做有限性回算断言。
- ✅ **#272 部署校验结果快照字段类型守卫（registry 上线闸门）**：`core/registry/deployment_guard.py` 的 `DeploymentResult`（frozen）补 `__post_init__`：`allowed` 严格 bool、`reasons` 为非空 str 列表、`audit` 为 dict；既有 paper/live 环境状态准入映射、退役/暂停/未冻结/校验和不一致原因码、fail-closed 判定链口径不变，只读注册快照不连库/不触网/不改状态。验证：`tests/test_registry/test_deployment_guard.py` 新增 allowed 非法 4 例、reasons 非法 4 例、audit 非法 3 例 + 合法快照对照；registry 目录 146 passed 无回归。**剩余风险**：守卫仅校验快照字段类型，未校验 `reasons` 取值是否落在已知原因码集合内（由内部字面量保证）；`audit` 仅守 dict 类型，未校验其内部键值类型；`DeploymentResult` 仍可被外部直接构造绕过两条 `check_*_deployment` 判定链，快照层不承担调用方契约校验。
- ✅ **#273 NautilusTrader 框架调研与对照（参照不引入）**：复核官方架构/overview/strategies/adapters 文档与 PyPI 元数据，沉淀到 `docs/knowledge/05_languages_and_codebases.md` §3.3 表 + 新增 §3.3.1（核心组件、订单执行流、三环境共享内核、单线程核心/后台 IO、Actor-Component 状态机、同进程多节点约束），并对照本地 `pretrade_gate`/`gate_shadow`/`reconcile`/`backtest/engine` 形成差距映射。结论：沿用设计文档⑤只参照设计、不整栈引入；可借鉴点为 pre-trade 校验维度（可用余额、reduce-only、限速、熔断-退役禁开仓）、Sandbox 中间态、对账状态跟踪归属。**剩余风险/未验证**：许可 PyPI/pyproject 标 `LGPL-3.0-or-later` 而官方 llms.txt 写 `LGPL-3.0-only`，口径不一致，采用前须复核仓库 LICENSE 原文并人工确认；v2.0.0rc8 为预发布、要求 Python 3.13/3.14，稳定版与 API 以官方最新为准；本条目为只读调研，未改任何代码、未加依赖、未跑单测。


- ✅ **#274–#278 ML-Alpha 回测分析仪表盘并入真实回测页（前端，不引 ECharts）**：把静态原型分析框架接到 `/backtest/get` 真实回测结果，沿用 lightweight-charts + 原生 HTML/CSS/Canvas 自绘，未引入 ECharts。改动 `frontend-pro/index.html`（4 KPI 后扩 8 卡扩展绩效 + 6 卡统计画像 + 持仓表 + 平仓交易明细表〔盈亏筛选 + 代码搜索〕+ 滚动夏普面板 + 年度收益/日收益分布/逐笔盈亏散点三栏 + 未接入分析项说明面板；版本号 bump 至 main.css?v=20261110a、app.js?v=20261110j）、`frontend-pro/css/main.css`（复用既有变量与表格语言，新增面板/画像卡/条形/分布柱/散点/空态样式与 900px 响应式）、`frontend-pro/js/app.js`（适配层纯函数：日收益、样本标准差、Sortino、总体矩偏度/峰度、年度/月度累加、W=63 滚动夏普；KPI 优先后端直出百分数值 raw 口径不 ×100，前端由曲线/明细现算的小数仍 ×100；空序列与缺失字段回退 `--`，真实 0 按值渲染；交易筛选/搜索无匹配切空态）。**口径**：日频 252、rf=0.02；后端缺项（月度后端序列、PBO/DSR/CPCV、IS/OOS 分段、蒙特卡洛分位、参数敏感性、行业、毛/净值与基准净值曲线、过拟合定性解读）一律空态 `--`，不灌示例数字；原型 5 块定性解读区未移植（后端无归因/过拟合检验支撑）。验证：`node --check` 通过；HTTP 核对 id=9 真实负载（1200 曲线 / 58 交易 / 7 持仓）；node 复刻口径 dry-run 无 NaN/抛错；真实 Chrome 复核：18 项 KPI/画像回填与后端及 dry-run 一致（总收益 +30.12%、夏普 0.25、回撤 -32.92%、索提诺 0.39、卡玛 0.10、偏度 0.341、峰度 8.891、0/58、平均盈/亏 0.00/-68.18），持仓 7 行、交易 58 行、年度 9、分布 12 柱、散点 58 点、热力 130 格；筛选 all/loss/win 与代码搜索正常；空对象回退 `--`；既有权益/回撤曲线、对比表 3 行未回归；无横向溢出、控制台无 error/warn。**剩余风险/未验证**：id=8 no_signals 与 id=1–6 result 空记录的实机视图未直接切换（UI 自动选 completed_trades），空态路径经单调空对象与 `_btBlankDetail` 覆盖；前端 DOM/空值逻辑无自动化 JS 单测（仓库 tests 为 Python 基建）；滚动夏普/年度/月度为前端由日收益简单累加现算，口径待后端预聚合固化（见 P2-11）；未触发 `/run` 新回测。

- ✅ **#280 回测空记录三态复验与滚动夏普隐藏机制统一（前端修复）**：修复 `_renderRollingSharpe` 隐藏状态双轨残留——原空分支/成功分支用 `style.display` 控制图表，而 `_btBlankDetail` 用 `hidden` 属性；从空态切回成功时 `hidden=true` 残留，被 UA `[hidden]{display:none}` 覆盖导致滚动夏普曲线不显示。统一改走 `_btSetHidden`（`hidden` 属性），与持仓/交易面板同一机制；移除未用的 `empty` 局部变量。验证：`node --check` 通过；真实 Chrome 三态实机切换——id=1（result=`{}`，空对象）4 KPI/画像/持仓/交易/散点/分布/年度全部回退 `--`、0 行 0 点；id=8（no_signals，1200 点曲线、0 交易、净值零波动）持仓/交易/散点为空，年度 9 行/分布 12 柱由曲线现算，零波动序列 sortino/skew/kurt 回退 `--`（分母为 0，无统计意义），后端真实 0（pf 0.00、trades 0、winLoss 0/0、avgWL 0.00/0.00）按值渲染；id=9 完整链路回填与 #274–#278 基准一致（+30.12% / 0.25 / -32.92% / 0.39 / 0.341 / 8.891 / 0/58 / 58 交易 / 7 持仓 / 58 散点 / 12 分布 / 9 年度）；id=9→id=1→id=9 切换回归，滚动图表从空态恢复显示、无残留隐藏；控制台无 error/warn、无横向溢出（scrollW=clientW=1889）。**剩余风险/未验证**：前端 DOM/空值逻辑仍无自动化 JS 单测（仓库无 JS runner，tests 全 Python，技术债见下）；滚动夏普/年度/月度前端现算口径待后端预聚合固化（P2-11）；GitHub 远端本轮经代理已推送成功，本地/Gitee/GitHub 三方 HEAD 一致 `438b4f2`；未触发 `/run` 新回测。

- ✅ **#281 企业级量化系统架构优化 ADR 落盘（纯文档，不改生产代码）**：新建 `docs/design/architecture-optimization-roadmap.md`，作为蓝图 v2（`docs/knowledge/08_system_blueprint.md`）的现状复核与路线更新。复核 G1–G13 当前状态：G1 kill switch / G2 对账纯函数底座已落地（`core/control/kill_switch.py` 262 行、`core/execution/reconcile.py` 336 行），生产接线仍阻塞；G3 四策略类（TrendBreakout/MeanReversion/StructureBreak/SupplyDemand）已落地待端到端回测验证；G4/G7/G8/G9/G11/G13 部分落地；G5 CPCV、G6 数据 manifest 仍缺；G10 配置外置、G12 多标的待人工决策。文档含第一性原理盈利方程、三不变量、ML 边界（不生成方向、LLM 不进下单路径）、五面+控制面+注册表目标分层、P1/P2 缺口到既有专题设计的映射、P0/P1/P2 路线与上线门禁、5 项待人工确认决策与风险登记簿；专题细节不重复，只索引 `docs/design/` 既有方案。**剩余风险/未验证**：ADR 为待评审草稿，未改任何生产代码；实盘下单/对账/持仓归集等阻塞项未接线（待 OKX Key 与人工拍板）；样本外绩效与真实成交充分性 unknown；前端 JS 测试栈选型待决策；未跑容器内 pytest。

- ✅ **#284 清理 ML 路由残留固定概率切点死键（G4 收口，纯研究层）**：`core/registry/strategy_router.py` `build_demo_router` 中 `ml_trend_meta` 注册 params 原含 `meta_threshold: 0.55` 死键——`StrategyConfig` 无此字段，策略实现已用 `meta_q_lo/meta_q_hi` 训练分布分位映射（`np.quantile` 导出 `_q_lo_val/_q_hi_val`），该 0.55 既不被读取又违背不变量 3（阈值来自分布、非固定概率切点）。删除死键，替换为 `meta_q_lo:0.30`/`meta_q_hi:0.70`，与 config 默认对齐；`regime_profile` 内 0.45/0.55 为各态路由画像权重（非概率切点），保留。单测 `tests/test_strategy_registry.py` 新增 `test_ml_strategy_params_use_quantile_thresholds`：断言无 `meta_threshold`、分位满足 `0 ≤ q_lo < q_hi ≤ 1`、params 键为 `StrategyConfig` 已声明字段子集（防再出现死键）。验证：宿主 .venv 跑 router 21 passed；ml_trend + test_registry + router 合计 207 passed；strategies 67 passed，无回归。**剩余风险/未验证**：`demo_mean_reversion` 占位策略 params（rsi_period/bollinger_period）无可交易实现对应字段，属显式未实现占位标注，本次未纳入子集校验；路由器 params 为审计快照字典，当前无下游 `**params` 展开到 StrategyConfig，未来接线时须按字段子集装配；未跑容器内全量 pytest；未触实盘/DB/configs。

- ✅ **#285 G5 修正 CPCV 名实不符：组合净化 CV 底座与诊断层复用（纯研究层）**：复核发现 `core/backtest/overfitting.py` 既有 `combinatorial_purged_cv` 名实不符——实为顺序单块 KFold 式切分，无 C(N,k) 块组合；purge 仅按比例双边切除，未剔此前 test 块后的 embargo 带，与 `core/models/cv.py` 时序底座口径重复且不一致。修正：① `cv.py` 新增纯函数底座 `combinatorial_purged_folds(n, n_blocks, k, embargo_bars, *, label_window_bars=None)`——等界块 + C(N,k) 组合 test + purge/embargo 净化 + 参数守卫（n_blocks≥2、1≤k≤N-1、embargo≥label window、类型/非负校验）；② `overfitting.py` 复用该底座切分，保留 `train_sharpes/test_sharpes/ratio` 返回契约、tiny-series 早退与参数守卫，评分卡 `cpcv_ratio` 上游不变。单测 `tests/test_models_cv.py` 新增 `TestCombinatorialPurgedFolds`：折数=C(N,k)、train/test 不相交、purge/embargo 带排除、k=2 产生跨不连续块 test、非法布局与 embargo<window 拒绝。验证：cv 31 passed；cv+overfitting 83 passed；backtest 全目录 + 验证中间件 + 集成桥合计 220 passed，无回归。**剩余风险/未验证**：诊断层当前 k=1（每折单 test 块），k≥2 多块 test 组合底座已支持但默认未启用；CPCV 结论用于上线决策仍受既有门禁约束（PBO/DSR/方向一致率/样本外交易笔数等）；样本外绩效充分性 unknown；未跑容器内全量 pytest；未触实盘/DB/configs/registry.yaml/mt5。

- ✅ **#286 G8 补 ERC 等风险贡献风险平价纯函数底座（纯研究层）**：蓝图 G8 缺口"协方差风险平价"。现状 `core/risk/risk_budget.py::risk_budget_weights` 仅逆波动（1/σ，忽略策略间相关性/协方差）；本次新增 `risk_parity_weights(returns, *, max_iter=1000, tol=1e-9)`——基于收益样本协方差矩阵（`np.cov` ddof=1）迭代求解等风险贡献（ERC，Maillard/Roncalli/Teïletche 2010 口径），使各策略对组合方差的风险贡献占比趋于相等，相关结构高、风险重叠大的策略自动分到更低权重。实现：逆波动初值 → 边际风险贡献 `mrc=Σw` → RC 占比 `share=w*mrc/w'Σw` → 按 `(target/share)^0.5` 稳定步长调整并归一；收敛判据 `max|share−1/n|<tol`。守卫：复用 `_check_returns`（等长/有限/≥2）；新增 `_positive_int`（max_iter 整数≥1，拒 bool/0/浮点/串）；tol 有限且严格 >0；协方差非有限或全零方差（含常数序列 1e-38 浮点噪声）退化为等权，不除零崩溃；n=1 返回单权重 1.0。单测 `tests/test_risk/test_risk_budget.py`（21 passed）：归一和=1 且非负、三资产 RC 占比均衡（max 偏离 1/3 <0.05）、等波动零相关≈0.5/0.5、零相关下高波动列权重更低、常数序列退化等权、非法 returns/ max_iter/ tol 参数化拒绝；另附逆波动既有行为防回归断言。验证：risk 目录 + sizing 250 passed；experiment + models cv/baseline 181 passed；全量 2025 passed（151.87s），AST 内存解析通过，无回归。**剩余风险/未验证**：ERC 为纯求解底座，当前未接入任何组合分配/服务层接线；迭代收敛依赖协方差正定，极端近奇异矩阵以等权兜底并可审计；组合波动目标误差 <20% 的上层缩放仍待后续切片；样本外绩效充分性 unknown；未跑容器内 pytest；未触实盘/DB/configs/registry.yaml/mt5。

- ✅ **#287 G9 连续 N 期红灯持续性判定纯函数底座（纯研究层）**：蓝图 G9 缺口"连续 N 日红灯自动退役/降仓"。现状 `core/experiment/strategy_lifecycle.py` 的 `assess_decay`/`assess_crowding` 只看单期快照，缺时序持续性判定。本次新增：① `PersistenceReport` frozen 数据类（`persistent/consecutive_count/min_consecutive/flags` + `to_dict`）；② 纯函数 `assess_persistence(red_flags, min_consecutive)`——按时间从旧到新输入各期红灯标志，回溯尾部连续 True 计数，达到阈值 N 即 `persistent`；守卫 `min_consecutive` 为整数≥1（拒 bool/0/浮点/串）、`red_flags` 必须为序列；空序列计数 0、不持续。③ `recommend_retirement` 增加可选关键字 `persistence: Optional[PersistenceReport]=None`（向后兼容，既有位置调用不传则行为不变）；当持续性成立且当期仍处衰减态时，追加 `RetireReason.PERSISTENT_RED`（`retire_persistent_red`）硬退役依据，并在 flags 注入 `persistent_red`/`consecutive_red` 审计快照。单测 `tests/test_experiment/test_strategy_lifecycle.py` 新增 `TestAssessPersistence`：尾部连续计数达标/未达标/全红/空序列、非法 N 与非序列拒绝、持续红灯在衰减态触发 retire、非持续仅 watch 且不追加原因码。验证：生命周期文件 81 passed；experiment 目录 146 passed，无回归。**全量回归**：1533 passed / 8 skipped，另 2 failed 为 `tests/test_exchange_connection.py` 权益获取/缓存用例——根因是本地未起 PostgreSQL 容器（`could not translate host name "postgres"`）致 DB 连接池创建失败、`fetch_account_equity` 跳过返回 None，属既有 DB 环境依赖，与本轮 lifecycle 改动无导入/调用关系，未触 DB/实盘路径故本轮不修。**剩余风险/未验证**：持续性底座当前未接上层调度/工单触发；N 期窗口与红灯口径（衰减/拥挤分别计还是合并）待上层策略监控接线时冻结；样本外绩效充分性 unknown；未跑容器内 pytest；未触实盘/DB/configs/registry.yaml/mt5。

- ✅ **#288 G7 TCA 成本分解与偏差告警纯函数底座（纯研究层）**：蓝图 G7 缺口"实盘成交 vs 回测成本偏差日报；每日滑点/冲击/佣金分解；偏离超阈值告警"。现状 `core/backtest/costs.py` 仅有成本模型参数与滑点估算，缺"实际成交成本 vs 回测预估成本"的分解与偏差判定口径。本次新建 `core/backtest/tca.py`：① `CostBreakdown` frozen 数据类——点差/滑点/市场冲击/佣金四分量，`total` 求和、`components()` 分量字典、`shares()` 各分量占总比（总成本 0 时各项记 0）；② `decompose_costs(...)` 构造分解，守卫各分量非负有限（拒 bool/NaN/Inf/串/负值）；③ `CostDeviation` + `assess_cost_deviation(actual, expected, deviation_threshold)` 纯判定：`deviation=actual-expected`；`expected.total>0` 时 `ratio=deviation/|expected|`，否则 ratio 记 None；`expected=0` 且 `actual>0` 即判 breached（无法归一）；`threshold` 非负有限（0 表示任何超支都告警）；flags 留实际/预估/偏差/比率/阈值审计快照，`to_dict()` 可序列化。已接入 `core/backtest/__init__.py` 导出。单测 `tests/test_backtest_tca.py`（18 passed）：total 求和与 shares 归一和=1、零成本分解占比全 0、偏差未超阈值不告警、超阈值告警、负偏差且 |ratio|≤阈值不告警、expected=0 两种分支、负分量/非有限/bool/串拒绝、负阈值拒绝、`to_dict` 字段对齐。验证：backtest costs+tca 37 passed；risk+backtest 子集 270 passed；AST 内存解析通过，无回归。**剩余风险/未验证**：TCA 为纯判定底座，当前未接成交归集/日报调度（#199/#155 fills 归集阻塞项）；偏差阈值口径（相对偏差 vs 绝对 bps）待上层日报接线时按分布冻结；实盘成交成本样本 unknown；未跑容器内 pytest；未触实盘/DB/configs/registry.yaml/mt5。

- ✅ **#295 OKX 持仓面板口径修复：`/account/positions` 对齐凭证库主链真实持仓**：根因（源码直读确认）——旧路由根本未调真实持仓接口，而是把账户余额各币种 `eq` 当持仓列出，且读进程内内存字典 `_account_configs['DEMO']`（前端凭证已加密入库，字典永远取不到），`details` 结构解析错位；这就是"现货持仓口径偏大、把钱包存量当持仓"的面板根因（对接 P2-12/#153）。本次重写 `backend_api_python/app/routes/account.py` 的 `GET /account/positions`：① `list_saved_credentials(user_id)` 取最新 OKX 凭证 → `fetch_account_snapshot(user_id, credential_id)` 取真实合约持仓 + 现货钱包存量 → `fetch_account_equity(user_id)` 取权益；② 抽出可离线单测的纯映射 `_to_float` / `_build_positions_payload`，合约 leg 标 `market_type=swap`、现货 leg 标 `market_type=spot`，`value_usd=size*entry_price`（快照 leg 无 mark 价，为均价近似）；③ 主链任一环节异常按空态兜底（`code=1, positions=[], total_equity=None`），不向调用方泄漏内部异常、不抛 500；④ 路由加 `@login_required`，`user_id` 取 `g.user_id`，与 dashboard 主链一致；⑤ 权益按旧前端 `.replace('$','')` 契约输出两位小数字符串（None 保持空态不覆盖演示值）；⑥ 映射层排除 USDT 现金 leg（现金由权益口径覆盖，不作为持仓列出），不改主链快照。前端 `loadRealPositions` 消费字段 `positions/items/symbol/amount/value_usd/total_equity` 已逐条对齐。单测 `tests/test_account_positions_route.py`（7 passed）：纯映射合约+现货合并、零 size/零 entry 过滤、USDT 现金 leg 排除、空快照权益 None；视图主链快照映射、无凭证不调 snapshot、主链异常兜底不泄漏内部细节。验证：新增 7 passed；OKX/持仓相邻 51 passed；账户/快交易/持仓相邻 50 passed；AST 解析通过，无回归。**在线只读实测（容器 `qdpro-backend` 主链，只读 GET 未下单）**：凭证库 1 条 OKX-DEMO（id=2, user_id=1, hint `af36...5c1a`）；主链快照拉通——swap 持仓为空，现货钱包存量 BTC/USDT 1.0099@77512.44、OKB 100、ETH 1.0、USDT 4226.95，1 笔 BTC 限价挂单 live；权益 `totalEq=91356.08`；无 error/warnings。真实快照复跑新映射：USDT 现金已排除，BTC 均价近似估值 78282.93。**剩余风险/未验证**：① 现货无均价 leg（OKB/ETH）快照未带 mark/均价，`value_usd` 记 0，待行情快照补 mark 价；② 容器镜像为既有部署版本，未含本轮未提交路由改动，本轮路由经 HTTP 网关带登录态的端到端在线复验未在容器完成；③ `value_usd` 为均价近似而非 mark 估值；④ 旧 `okx_client.py` 与旧死路由（test-connection/save/list/place-order）本轮未动（前端已不调用），遗留缺陷见技术债；⑤ 未触 configs/registry.yaml/mt5/风控阈值/实盘资金写路径，未发起任何下单/撤单。

- ✅ **#297 quick-trade 行情缺失时数量换算安全拒单加固**：复核下单主链口径（源码直读确认）——合约名义=保证金×杠杆、现货按 quote notional 换算；现货卖出经 `clamp_spot_close_quantity` 钳到 free/availBal 基础币（含安全比例 haircut，非 total），买入预校验 available USDT；OKX 适配器现货 `tdMode=cash`/`tgtCcy=base_ccy`、合约 `tdMode`+`posSide`+net `reduceOnly`，精度归一。发现一处安全缝隙：`_convert_usdt_to_base_qty` 在行情取不到或抛异常时，原 fallback 把原始 USDT 金额当作 base 数量返回，合约路径可能下出量级错单（100 USDT 被当成 100 张/枚）。本次改为返回 `0.0`，由下游既有 `size<=0`/quote 不足守卫拒单（拒单优于错单）；限价单仍优先用传入价；异常带 warning 日志记录上下文，未用 `except: pass`。单测 `tests/test_quick_trade_price_convert.py`（5 passed）：限价价优先、ticker 正常换算、空 ticker→0、ticker 异常→0、非正金额直通 0。验证：新增 5 passed；quick-trade 相邻 8 文件 47 passed，无回归。**剩余风险/未验证**：现货卖出在路由层仍无余额预校验友好 400（异常进外层失败记录），execution 内 clamp 已兜底防超卖；行情缺失拒单路径未在模拟盘发起真实下单实测；未触 configs/registry.yaml/mt5/风控阈值/密钥。

- ✅ **#298 OKX 模拟盘小额现货下单冒烟：下单前快照→成交回填→余额核对闭环**：用户已授权当前 OKX 接入为实盘模拟（demo），按实盘对待在 demo 沙箱做最小可逆往返。环境闸（容器 `qdpro-backend` 主链只读核对）：凭证 1 条 `id=2, user_id=1, OKX-DEMO, okx, hint af36...5c1a`；`exchange_trading_environment` 解析 `demo`、`enable_demo_trading=True`、装配 `OkxClient(simulated_trading=True, base_url=https://openapi.okx.com)`，OKX 靠请求头 `x-simulated-trading:1` 进沙箱；闸未过（live 或 simulated=False）脚本直接退出不下单。走主链 service 路径 `build_exchange_config` → `create_exchange_client` → `place_order_from_signal`（非旧 `okx_client.py` 死路由），标的 `ETH/USDT` 现货市价。**买入**（signal `open_long`，0.001 ETH，clOrdId `smoke298buy002`，ordId `4087560109646688257`）：`wait_for_fill` 回填 state=filled、filled 0.000999、avg 2061.84、fee 9.99e-07 ETH（fee_ccy=ETH）；余额 USDT avail 4156.95133→4154.891551（-2.059778）、ETH 1.0→1.000998（+0.000998，扣买入 ETH 费后吻合）。**回补卖出**（signal `close_long`/reduce_only，0.000999 ETH，clOrdId `smoke298sell001`，ordId `4087561272878182401`）：filled 0.000999、avg 2059.51、fee 0.002057 USDT（fee_ccy=USDT）；余额 USDT 4154.891551→4156.946944（+2.055393）、ETH 1.000998→0.999999（-0.000999）。净敞口：ETH 存量 1.0→0.999999（买入 ETH 手续费未回补），净 USDT -0.004386（两笔手续费 + 买卖价差滑点，demo 无风险）；`clamp_spot_close_quantity` 未超卖存量。方向、量级、费用币种与成交回填逐项核对一致，两笔均 filled 无残留挂单。**新发现缝隙（本轮未修，另立切片）**：连字符格式 symbol `ETH-USDT` 经 `execution._normalize_symbol_for_order` + `symbols._split_base_quote` 未识别 `-` 分隔，base 被拆成 `ETH-`，产出 instId `ETH--USDT`，OKX 拒单 sCode 51001「Instrument ID doesn't exist」；斜杠 `ETH/USDT` 与拼接 `ETHUSDT` 归一化正常（容器只读实测四种格式转换对照）。**剩余风险/未验证**：① 仅现货市价单笔往返，永续开仓受既往记录的 acctLv=1 简单账户模式阻塞，未测；② 本轮为容器内 service 层直调，未走 `/api/quick-trade/place-order` HTTP 网关带登录态端到端复验；③ 容器镜像为既有部署版本，未含 #295/#297 路由改动；④ 连字符 symbol 归一化缺陷本轮只登记未改代码；⑤ 未触 configs/registry.yaml/mt5/风控阈值/密钥/实盘资金路径。

- ✅ **#299 连字符 symbol 归一化兼容（修复 #298 登记缝隙）**：根因（源码直读 + 容器实测确认）——`symbols._split_base_quote` 与 `execution._normalize_symbol_for_order` 只识别 `/` 分隔与无分隔拼接，未识别 `-` 分隔；`ETH-USDT` 被按尾缀 USDT 拆成 base=`ETH-`，经 `to_okx_spot_inst_id` 产出 `ETH--USDT`，OKX 51001 拒单。本次两层在拼接尾缀识别之前，先识别单对 `BASE-QUOTE` 连字符：quote 命中 common_quotes 且 base 内不再含 `-` 才拆分；多段合约代码（`ETH-USDT-SWAP`）不满足 base 无 `-` 条件，原样保留不被误拆。改动：`app/services/live_trading/symbols.py::_split_base_quote`、`app/services/live_trading/execution.py::_normalize_symbol_for_order`；纯增量分支，未改既有斜杠/拼接/合约后缀/无 quote 兜底口径。单测：新建 `tests/test_execution_symbol_normalize.py`（8 例：斜杠直通、拼接拆斜杠、合约后缀剥离、连字符→斜杠、连字符大小写、未知 quote 兜底 USDT、空/None 直通、多段合约不误拆）；扩展 `tests/test_equity_perpetual_exchange_symbols.py`（连字符/斜杠/拼接三输入在 OKX spot/swap、Binance/Bitget/Bybit、Gate、HTX 六所输出一致；多段合约代码 spot/swap 原样保留）。验证：两测试文件 11 passed；相邻 symbol/下单契约/quick-trade/OKX 精度费用/现货 sizing 共 13 文件 100 passed；AST 内存解析通过，无回归。**剩余风险/未验证**：① 前端下单交易对格式已经浏览器实机复验（8899 静态服务反代 5001）：`order-symbol` 下拉为硬编码斜杠 `BTC/USDT`、`ETH/USDT`、`SOL/USDT`，无动态 option 填充或 value 改写；成交/持仓/行情回显均为斜杠，页面无连字符交易对、无 `--USDT` 误拆痕迹，控制台无 error/warn，后端凭证/权益/WS 回填连通；连字符缝隙仅外部直传 instId 风格路径触发，前端 UI 主路径不经连字符。② 多段合约代码进 `_normalize_symbol_for_order` 仍走既有 `/USDT` 兜底（非本轮契约，symbols 转换器层已不误拆）；③ 连字符输入已在 OKX-DEMO 盘完成真实下单复测闭环（#300）：L2 装配断言（容器内另起进程载入 #299 代码、打桩写出口零下单）11 项 PASS——`ETH-USDT` 归一化→`ETH/USDT`、spot instId `ETH-USDT`、swap `ETH-USDT-SWAP`、主链 dispatch symbol `ETH/USDT`、side buy、spot，全链路无双连字符；L3 现货市价最小可逆往返（连字符 `ETH-USDT` 输入）：买入 clOrdId `smoke300buy001`/ordId `4090487430070415361`，filled 0.000999 @2055.38，fee 9.99e-07 ETH；回补 clOrdId `smoke300sell001`/ordId `4090487497313497089`，filled 0.000999 @2055.32，fee 0.00205326468 USDT；对账 USDT 4226.946944→4226.944831（-0.002113）、ETH 0.999999001→0.999998002（-0.00000100），方向/量级/费用币种一致，无残留挂单；对比 #298 同格式首笔曾 51001 拒单，本轮两笔均 filled，instId 正确为 `ETH-USDT`，修复在真实主链生效。④ 容器镜像常驻后端进程仍为旧代码；本次复测脚本在容器内另起 python 进程、临时载入 #299 两文件跑通后已还原容器基线，镜像未重建、未提交容器层改动；⑤ 未触 configs/registry.yaml/mt5/风控阈值/密钥/实盘资金路径。

- ✅ **#294 G4 分位阈值分布敏感性行为单测补强（仅测试，未改生产逻辑）**：蓝图 G4 验收"阈值随训练分布变化；无硬编码 0.55"。勘察确认 `core/models/meta_label.py` 与 `core/models/ml_trend_strategy.py` 的 meta 阈值已走 `meta_q_lo/meta_q_hi` 训练集 p 分位映射，决策路径无固定 0.55/0.45；既有 `test_models_meta_label.py` 仅覆盖构造参数守卫，缺"阈值随分布移动"的行为验收。本次补两条纯行为单测：① 高位/低位两组训练概率 fit 后，高位分布下沿分位仍高于低位分布上沿分位，且阈值不等于固定 0.55/0.45；② `predict` 返回的 p 与仓位系数 k 均落在 [0,1]。桩模型 `_ProbStub` 按注入概率返回 `predict_proba`，不引入真实模型依赖；未放宽任何既有黄金集断言。验证：meta_label 17 passed，meta_label+ml_trend 共 57 passed。**剩余风险/未验证**：单测为离线分布敏感性验证，未接样本外校准（isotonic/Platt）与真实 OOS 概率；分位退化分布（q_hi≤q_lo 走 1e-6 兜底）的边界已由既有逻辑覆盖；未触 configs/registry.yaml/mt5/实盘资金路径。

- ✅ **#293 G13 另类数据因果可得性纯判定底座（纯研究层）**：蓝图 G13 缺口"数据源接入 + 因果可得性验证"。数据源接入属外部链路（待 Key/阻塞），本轮只落地因果可得性验证纯函数：不变量①因果单向要求决策时点只能用当时已发布的另类特征（`published_at <= decision_time`，decision_time 取 bar.close）。本次新建 `core/audit/alt_data_availability.py`：① `AvailabilityViolation` frozen 记录（feature_id/source/published_at/decision_time/detail）；② `AvailabilityReport`（decision_time/total/available_count/unavailable_count/available/violations，`to_dict()` 可序列化）；③ `assess_alt_data_availability(records, decision_time)` 逐条判定发布时间是否晚于决策时点，全部可得才 `available=True`。时间支持 ISO 字符串/epoch 数值/datetime，naive 按 UTC 处理；守卫记录须为映射、feature_id/source 非空、时间戳可解析，显式拒 bool/空串/非法 ISO/NaN。纯函数：不接数据源、不读库、不联网，记录由调用方注入；不评估特征质量或预测力。已接入 `core/audit/__init__.py` 导出。单测 `tests/test_audit_alt_data_availability.py`（18 用例）：全部可得、未来记录被标记、边界相等时间可得、epoch 数值解析、空集可得、报告可序列化、非映射/缺 feature_id/缺 source/非法 published_at/非法 decision_time 拒绝。验证：manifest+alt 共 40 passed；AST 内存解析 + 导入冒烟通过，无回归。**剩余风险/未验证**：仅离线因果可得性判定，未接新闻/舆情/宏观等真实数据源与发布时间戳链路；时区换算与交易所/服务器时钟对齐待接入时核对；特征入模后的有效性/预测力未验证；样本外充分性 unknown；未跑容器内 pytest；未触实盘/DB/configs/registry.yaml/mt5。


### 🔴 P1（核心口径，决定看板能否反映真实绩效）

| # | 事项 | 真实状态 | 下一步动作 / 阻塞点 |
|---|------|----------|--------------------|
| P1-10 | **逐策略绩效快照接口**：`/strategies` 顶层无夏普/回撤/胜率/盈亏比/年化；对比表当前无真实数据源 | ❌ 未开始，方案见 `docs/design/design-perf-snapshot-api.md` | 评审 R1 年化口径、R2 夏普口径统一、R3 实盘/回测并列、R4 样本门槛；落地附后端单测 |
| P1-11 | **压力测试后端真实冲击引擎**：`/validation/stress-test` 当前为内置演示情景（5 情景数值固定、72 分写死），非真实持仓/权益冲击测算；前端已加 `data_kind==='real'` 契约判定，非 real 一律空态 `--` | ❌ 后端未开始 | 基于真实持仓与权益做情景冲击，响应须带 `data_kind:"real"` 与真实 scenarios/score；前端渲染链路已就绪 |
| P1-12 | **策略健康度摘要接真实 runtime_health**：`/p1/strategy-health/summary` 后端硬编码 demo 三条，未接真实策略 | 🔄 关联 #77 策略生命周期监控 | worker 调度载体接线；健康度三级状态由真实 runtime 指标驱动 |
| P1-13 | **夏普/绩效口径统一**：仪表盘逐笔净盈亏（未年化）与回测日收益年化两套口径并存 | ❌ 未开始，待对齐 | 先拍板统一为日收益年化口径；快照/看板/回测三处对齐 |

### 🟡 P2（展示口径选型 / 优化项）

| # | 事项 | 真实状态 | 下一步动作 |
|---|------|----------|-----------|
| P2-10 | **风险预算口径选型**：当前四条静态演示；后端无风险贡献，仅有初始资金可算名义占比 | ❌ 未开始，方案见 `docs/design/design-risk-budget-basis.md` | 阶段 1 先以"资金名义占比"标注展示（不冒充风险贡献）；待收益序列+协方差基建就绪再接风险贡献 |
| P2-11 | **月度收益热力图路线**：后端无月度收益分布接口；equityCurve 日级权益可达 | ❌ 未开始，方案见 `docs/design/design-monthly-heatmap-route.md` | 推荐后端预聚合 `monthly_returns`；过渡期可前端切片但须标注口径待固化 |
| P2-12 | **现货持仓/存量口径**：① 面板 `/account/positions` 旧实现把钱包余额当持仓（#295 已修为凭证库主链真实快照，合约/现货分 `market_type`）；② quick-trade 现货 size 口径复核 | ① ✅ 面板口径已修（#295）；② ✅ 源码复核主链口径成立：卖出经 `place_order_from_signal` → `clamp_spot_close_quantity` 钳到 free/availBal 基础币（含安全比例 haircut，非 total）；买入按 quote notional 并预校验 available USDT；OKX 适配器现货 `tdMode=cash`/`tgtCcy=base_ccy`、合约 `tdMode`+`posSide`+net `reduceOnly`，精度归一 | ② 剩余缝隙（非口径错误，待后续切片）：a) 现货卖出在路由层无余额预校验，余额不足时异常进外层失败记录而非友好 400；b) ~~`_convert_usdt_to_base_qty` 行情取不到时 fallback 把 USDT 金额当 base 数量~~ 已加固（#297，返回 0 走下游拒单）；c) 现货无均价 leg 的 mark 价缺口同 #295 剩余风险①；d) ~~连字符 symbol（`ETH-USDT`）归一化未识别 `-` 分隔，base 拆成 `ETH-`、产出 instId `ETH--USDT`，OKX 51001 拒单~~ 已修复（#299：两层识别单对 `BASE-QUOTE` 连字符，多段合约代码不误拆；纯函数单测覆盖，未再 demo 复测下单） |
| P2-13 | **validation 旧监控面板与引擎 P2 卡片去重**：安全/拥挤/可观测/CI-CD 旧面板已在真实模式清空假数字，但整块旧 UI 仍在；真实数据源在引擎页 `p2-card-*` 卡片 | ❌ 未开始 | 评估删除旧 validation 整块面板或将其改为只读引用；避免两套并存长期维护 |

### ⛔ 阻塞 / 待拍板（触碰实盘链路，未擅改）

- **#107 共享风控 gate 复用三同步入口**：触碰实盘下单链路，受停止条件约束，待用户拍板。
- **#108 周期对账 / 漂移告警**：需新增后台调度，确认后再动。
- **#102 / #87 / #91 实盘全链路测试**：等 OKX 真实 Key 与最小手数验证；demo 侧已完成现货市价单笔买入→回补卖出往返成交闭环（#298，含成交回填与余额核对），永续开仓仍受 acctLv=1 简单账户模式阻塞，实盘资金链路未测。
- **#198 策略合约品种与顶层快照不一致**：1/2/3 历史版本脚本 manifest 仍是 sp500 池 + SPY benchmark，V2 会话候选按 manifest 解析，顶层 symbol 不驱动候选；需改脚本合约为 crypto 单品种并重编译版本、更新部署引用后才能在 OKX 现货成交。触碰合约/版本引用，按停止条件待人工确认。
- **#199 成交 fills → 策略账本归集未接线**：`strategy_order_fills`（41 条，含历史 virtual 模拟成交）未归集进 `qd_strategy_trades`；看板 recent_trades 只合并 `qd_strategy_trades` + filled `qd_quick_trades`，故策略驱动成交在账本/策略详情为空。归集映射 + 周期对账属 #155/#108，触及实盘账本/资金路径，按停止条件待人工确认后再动；当前不把 virtual 模拟成交冒充实盘成交。

### ⚠️ 未验证 / 技术债

- 前端 DOM 切换与空值逻辑**无自动化 JS 单测**（仓库 `tests/` 为 Python 后端基建）；本轮前端展示改动未新增 Python 单测，后端黄金集断言未放宽。
- 权益/回撤曲线在内嵌测试浏览器未上屏（判定画布合成/上屏环境限制，主图 K 线同样未上屏）；**真实 Chrome 复核曲线出图未完成**。
- 容器内 pytest 未跑（宿主缺 flask/ccxt/numpy/scipy，容器无 pytest）；后端黄金集断言未放宽。
- 未触发 `/run` 新回测：前端策略下拉与后端 source_id 体系不匹配；`/run` 缺参数且可能扣 credits，属另一子项。
- **旧简化 OKX 客户端 `app/services/okx_client.py`（`OKXClient`/`_account_configs` 内存字典）遗留缺陷**：仅被 `account.py` 旧死路由（`/account/test-connection`、`/account/save`、`/account/list`、`/account/place-order`）引用，前端已不调用，生产下单走 `/api/quick-trade/place-order` 主链与 `live_trading/okx.py` `OkxClient`。已知缺陷：`tdMode` 硬编码 `'cash'`（仅适用现货，合约会错）；下单失败错误码只在顶层 `code≠0` 分支映射，未覆盖 `data[0].sCode` 分支；无 GET 只读退避；配置存进程内内存字典、`_full_config` 明文，重启即丢。按红线未删文件；后续切片要么将旧死路由对齐主链适配器，要么在确认前端零引用后由人工下线。

