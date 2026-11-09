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

### 1. OKX实盘对接全链路 🔄 进行中
- **已完成**：
  - ✅ 前端API账户设置弹窗（Key/Secret/Passphrase）
  - ✅ 后端OKX客户端模块（okx_client.py）
  - ✅ 连接测试API → 成功，账户余额$98,340.28
  - ✅ 实时价格API（ticker）→ BTC $80,229 正常
  - ✅ 历史K线API（kline）→ 框架已搭好
  - ✅ 下单API（place-order）→ 框架已搭好（已优化错误码）
  - ✅ 持仓查询API（positions）→ 框架已搭好
  - ✅ 前端fetchRealKline函数 → 代码已写
- **未完成**：
  - ⏳ 下单失败排查（"All operations failed"，需查tdMode参数）
  - ⏳ 前端真实K线接入图表（代码写了，容器恢复后部署测试）
  - ⏳ 前端持仓面板真实数据展示（API通了，认证问题没显示）
  - ✅ 认证token问题（2026-10-31 落定：dev-token 假登录 → 真实自动登录，401 循环登出消除；E009）
  - ✅ 本地网络访问OKX API连接被拒绝（2026-10-31 已解除，E007）
- **验收标准**：能真实下单、真实平仓、真实查持仓、真实查余额、真实K线渲染
- **安全约束**：先用最小手数测试，确认没问题再加大

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
| T5 | 下单失败原因排查 | ⏳ 待做 | "All operations failed"，需查OKX现货参数 |
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
| P0-2 | **OKX 下单失败排查**：`"All operations failed"`，疑似 tdMode / 现货参数 / clientOrderId 问题 | 🔄 进行中（网络阻塞已解除：容器内直连 OKX `{"code":"0"}`；剩参数/业务根因，后台子任务排查中） | 用最小手数（10 USDT）在 DEMO 账户复现，打 OKX 官方错误码文档对照；先 `POST /api/okx/account/balance` 确认账户模式（cash / single/margin） |
| P0-3 | **API 认证 token 401**：开发环境下 `/api/dashboard/summary` 等已鉴权接口返回 401，导致前端持仓面板即使 API 通了也没数据 | ✅ 已完成（登录 `POST /api/auth/login` → `data.token`，Bearer 访问 dashboard/summary 200） | 已修复；官方镜像不支持 `SKIP_AUTH` 环境变量，鉴权必须走登录拿 token |
| P0-4 | **前端容器实环境验证 P2 六卡片 + 真实 K 线接入**：本地源码已改（p2-panel-completion），但通过 `:8888` 代理请求 6 个 P1/P2 端点在本机全部 5s 超时 | 🔄 进行中（P0-1 已修复 + 网络已恢复，后台子任务容器验证中） | 重启前端容器 `docker restart quantdinger-frontend`，强刷浏览器，逐卡片看状态灯是否点亮（健康服务 / 拥挤度 / 可观测性 / CI-CD） |
| P0-5 | **本地直连 OKX API 被墙**：curl 退出码 7，`www.okx.com` 连不通，"联通"结论假阳性 | ✅ 已解除（2026-10-31：宿主机直连 200；容器内经 Docker NAT 亦通 `{"code":"0"}`；代理 127.0.0.1:7890 仍可兜底，wss CONNECT 200） | 直连与代理双通道均已验证；"OKX 链路已通"结论成立 |
| P0-6 | **GitHub 推送修复**：Gitee 已同步，GitHub curl 28 连接重置 | ✅ 已完成（2026-10-31：merge 远程占位初始提交 → `861dc24`，GitHub+Gitee 双端 HEAD 一致） | 已推送成功；详见 ERROR_LOG E008（unrelated histories 合并 + 系统代理未设环境变量的教训） |

### P1（重要但不阻塞）

| # | 事项 | 真实状态 | 下一步动作 |
|---|------|----------|-----------|
| P1-1 | **策略生命周期后端自动退役逻辑**：前端三级健康度面板已做，后端触发阈值自动停策略+通知+记录原因未实现 | 🔄 进行中（后台子任务在 `core/registry/strategy_registry.py` 实现 `retire_if_health_below(threshold)`） | 阈值由 CLEAN 分布校准，禁止按 PnL 网格搜索；含审计日志与因果守卫（AGENTS.md 不变量） |
| P1-2 | **五层市场识别接入真实 K 线**：L1-L5 规则版完成但喂的是演示数据 | 🔄 进行中（后台子任务接 OKX kline → 特征化 → 喂 regime.py；容器内 OKX 连通已确认） | 先接 BTCUSD M15 一个品种跑通，再扩展 |
| P1-3 | **`demo_mean_reversion` 策略类补实现**：路由表已登记（`implementation_ref=(未实现)`），但代码库无对应策略类 | 🔄 进行中（后台子任务在 `core/strategies/` 实现 `mean_reversion.py`） | 按 RSI(14) + 布林带(20,2σ) 反向开仓；写单测覆盖 |
| P1-4 | **路由权重表分布校准**：当前 4×3 权重表是定性配置，未经 CLEAN 分布驱动 | ❌ 未开始 | 跑 `python scripts/calibrate_regime.py --mode distribution`，用输出分位替换 `strategy_router.py` 里硬编码权重；改前 ADR 留档 |
| P1-5 | **StrategyMatcher × StrategyWeightRouter 集成**：两层目前独立（一个打分排序、一个出资金权重） | ❌ 未开始 | 让 Matcher 输出 top-N 排名 → WeightRouter 对 top-N 输出归一化权重；其他策略权重归零 |
| P1-6 | **前端 axios 响应拦截器容错**：502 时把 nginx HTML 原文塞给用户（P1-1 bug） | ❌ 未开始 | 拦截器里判断 `Content-Type`，非 JSON 时统一提示"服务暂时不可用 (HTTP 5xx)"，不暴露 HTML |
| P1-7 | **登录错误 state 在路由切换后未清空**（P2-1 bug）：跳注册页被守卫弹回，旧 502 错误还挂着 | ❌ 未开始 | 登录页 `onMounted` 或 `watch(route.query.redirect)` 时清空 `errorMessage` + 表单字段 |
| P1-8 | **`quantdinger-scheduler-worker` / `trading-worker` 容器 unhealthy**：基础设施告警 | ❌ 未开始 | `docker logs quantdinger-scheduler-worker --tail 50` 看根因；不影响前端联调，但要排 |
| P1-9 | **连续 regime 线性插值**：当前用离散 trend/range/volatile/quiet 4 类，未接 regime.py 的连续 `w_trend/w_mr/w_range` | ❌ 未开始 | 在 `StrategyWeightRouter.route()` 加可选连续模式，用连续权重做线性插值；保留离散模式做回退 |

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
| P2-12 | **现货持仓口径偏大**：quick-trade 现货 size 取资金账户 total/availBal（约 1.01 BTC 量级），非现货成交净值 | ⚠️ 阻塞：触及持仓/资金路径，按停止条件须先拍板 | 平仓前只读核准钱包真实基础币余额；口径定义与解析链路改动待人工确认 |
| P2-13 | **validation 旧监控面板与引擎 P2 卡片去重**：安全/拥挤/可观测/CI-CD 旧面板已在真实模式清空假数字，但整块旧 UI 仍在；真实数据源在引擎页 `p2-card-*` 卡片 | ❌ 未开始 | 评估删除旧 validation 整块面板或将其改为只读引用；避免两套并存长期维护 |

### ⛔ 阻塞 / 待拍板（触碰实盘链路，未擅改）

- **#107 共享风控 gate 复用三同步入口**：触碰实盘下单链路，受停止条件约束，待用户拍板。
- **#108 周期对账 / 漂移告警**：需新增后台调度，确认后再动。
- **#102 / #87 / #91 实盘全链路测试**：等 OKX 真实 Key 与最小手数验证；当前仅 OKX demo 只读 + 两笔 demo 成交闭环。
- **#198 策略合约品种与顶层快照不一致**：1/2/3 历史版本脚本 manifest 仍是 sp500 池 + SPY benchmark，V2 会话候选按 manifest 解析，顶层 symbol 不驱动候选；需改脚本合约为 crypto 单品种并重编译版本、更新部署引用后才能在 OKX 现货成交。触碰合约/版本引用，按停止条件待人工确认。
- **#199 成交 fills → 策略账本归集未接线**：`strategy_order_fills`（41 条，含历史 virtual 模拟成交）未归集进 `qd_strategy_trades`；看板 recent_trades 只合并 `qd_strategy_trades` + filled `qd_quick_trades`，故策略驱动成交在账本/策略详情为空。归集映射 + 周期对账属 #155/#108，触及实盘账本/资金路径，按停止条件待人工确认后再动；当前不把 virtual 模拟成交冒充实盘成交。

### ⚠️ 未验证 / 技术债

- 前端 DOM 切换与空值逻辑**无自动化 JS 单测**（仓库 `tests/` 为 Python 后端基建）；本轮前端展示改动未新增 Python 单测，后端黄金集断言未放宽。
- 权益/回撤曲线在内嵌测试浏览器未上屏（判定画布合成/上屏环境限制，主图 K 线同样未上屏）；**真实 Chrome 复核曲线出图未完成**。
- 容器内 pytest 未跑（宿主缺 flask/ccxt/numpy/scipy，容器无 pytest）；后端黄金集断言未放宽。
- 未触发 `/run` 新回测：前端策略下拉与后端 source_id 体系不匹配；`/run` 缺参数且可能扣 credits，属另一子项。

