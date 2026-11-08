# 知识沉淀与复用管道 · 前端只读审计（任务 #161）

- 审计范围：`frontend-pro/index.html`（2549 行）、`frontend-pro/js/app.js`（2914 行）、`frontend-pro/css/main.css`（935 行）；`src/assets|components|views` 为空目录，无独立脚本/页面。
- 审计对象：内部 Wiki 只读页、AI 复盘页、日志中心、决策审计日志面板、绩效归因（Journal）面板、P2 Journal 卡片、策略生命周期监控面板，以及概览页知识链路静态文案。
- 对照基准：飞书草案《知识沉淀与复用管道架构》revision 4（决策审计四段 JSON、故障知识库、实验跟踪、KnowledgeBase 检索、策略生命周期八阶段、复盘回灌）；上一轮口径审计见 `docs/frontend_realdata_audit.md`（#152，本报告引用不重复）。
- 审计日期：2026-11-08；审计方式：静态通读 + 分支归属核对 + 端点清单复核；未做浏览器实跑与登录态联调（见「未验证项」）。
- 证据分级：confirmed（代码逐行核实）/ inferred（相邻代码推断）/ unknown（现状不明）。
- 口径约定：real = 已登录且接口 `code===1` / `success===true` 成功分支；demo-fallback = `!isReal` / 未登录 / 接口全挂兜底分支；unknown = 静态镜像或分支归属无法从静态代码判定。`!isReal` 分支内演示值属合规兜底，本报告不标记为需删除。

## 一、结论

1. 本切片覆盖的知识管道相关面板（Wiki / 日志中心 / AI 复盘 / 审计日志 / Journal 归因 / 生命周期）**未发现 real 成功分支误留硬编码演示哨兵或占位数字**；复盘、日志、审计面板均无 `!isReal` 演示分支，演示兜底只存在于仪表盘/持仓/成交/K线/订单簿等面板（归属见 #152）。
2. 缺失值口径基本合规：复盘指标、Journal 四指标、日志成交行的 null/空串/NaN 走 `--`；真实 0 正常渲染（成交 0 笔、胜率 0.0%、盈亏 0.00 等）。
3. **相对草案的主要缺口在能力入口层，而非渲染口径**：故障知识库、实验跟踪、KB 检索（相似故障/相似实验/Playbook）、生命周期八阶段时间线、复盘结论「固化回灌」动作在前端均无对应面板或端点；决策审计在前端仅有列表级 `时间/级别/消息` 回显，草案四段 JSON（信号因子 / 风控检查 / 执行 / 出场结果）无可视化还原入口。
4. 残留观察 7 项（F1–F7），均为口径边界或失败分支收口问题，非演示数字泄漏；本切片未改动任何代码。

语法验证：`node --check D:\Trader\frontend-pro\js\app.js` → PASS（exit 0，Node v22.23.2）。

## 二、逐面板核对

### 2.1 内部 Wiki 页（`page-wiki`）

| 页面/面板 | 分支归属 | 证据行号 | 对照草案的缺口 | 结论 |
|---|---|---|---|---|
| Wiki 整页（宪法/框架/铁律/口径/经验/对标/原则/复盘回灌/风控与止盈设计/一致性规约/阻塞项/踩坑表） | unknown（static-mirror，无数据分支、无接口请求） | index.html 2041-2423；app.js 全量 grep `wiki/knowledge/incident/playbook` 0 命中 | 草案 Layer 4 组织层知识（技能库/Playbook/培训材料）仅以静态文字镜像呈现；无条目列表、无检索框、无条目详情；踩坑表为手工节选（现象/根因解法/影响三列），非草案 incident 条目结构 | confirmed：静态只读镜像，口径与 `docs/RULES.md`、`docs/TODO.md` 单一事实源一致；无 real/demo 数据口径问题 |
| 踩坑经验清单（静态表） | unknown（static-mirror） | index.html 2404-2422 | 缺草案 incident 字段：`incident_id / severity / status / symptoms[] / root_cause / solution / prevention[] / lessons_learned[] / tags / resolved_at`；无按错误码/症状关键词匹配 | confirmed：纯文档节选，不冒充结构化故障库 |
| AI 复盘与经验回灌说明块 | unknown（static-mirror） | index.html 2247-2271 | 回灌闭环（诊断人工确认 → 固化 RULES.md / 技能库；待改进项登记 TODO.md）仅文字描述；前端无「固化为规则 / 回灌经验库」操作入口 | confirmed：闭环落地在后端/文档侧，前端只做说明 |
| 机构对标表（Renaissance/Two Sigma/Citadel/DE Shaw/Millennium/Jane Street） | unknown（static-mirror） | index.html 2208-2230 | 草案对标表中「决策审计/实验管理/故障复盘/生命周期/知识库」五行机制，前端无对应可交互视图 | confirmed：演进方向文字，不含绩效数字 |

### 2.2 日志中心（`page-logs`）

| 页面/面板 | 分支归属 | 证据行号 | 对照草案的缺口 | 结论 |
|---|---|---|---|---|
| 决策日志列表（decision） | real | app.js 1189-1195、1266-1277；index.html 1242、1248-1252、1290-1292 | 草案决策审计四段 JSON（trade_id / signal.factors / risk_check / execution / outcome / pnl_r / holding_period_hours）未展示；行内仅 `timestamp / level / message`，无 trade_id 下钻、无因子值、无风控与执行字段 | confirmed：real 驱动；未授权 / 非 `code===1` 清空并置错误文案（1191-1194、1339-1342）；消息缺失 `--`（1275），时间缺失 `--`（1145-1150） |
| 交易日志列表（trade） | real | app.js 1196-1203、1279-1295；index.html 1243、1239-1247 | 成交行展示时间/方向/品种/价格/数量/盈亏/平仓原因；无单笔决策链路上溯（信号→风控→执行→出场） | confirmed：pnl 缺失 `--`（1280-1282），价格/数量缺失 `--`（1290-1291），品种/平仓原因缺失 `--`（1289、1293）；真实 0 盈亏渲染 `+0.00`，数量 0 正常渲染 |
| 系统日志列表（system） | real（会话内运行时 `debugLogs`，非后端接口） | app.js 3-13、1212、1297-1307；index.html 1244 | 草案 Layer 2 系统/风控事件留痕的一部分；无后端系统事件源 | 基本合规；边界见 F2：行内 `log.time` / `log.msg` 无 `--` 兜底（1301、1305），来源为前端运行时日志，缺字段概率低 |
| 风控事件列表（risk） | real（固定空态，不拉演示） | app.js 1181-1184、1211、1343-1346；index.html 1245、1253-1257 | 草案风控事件/拦截记录无结构化事件源；缺口 G1/G2/G3、契约 C-LOG-01 / C-RISK-03 | confirmed：固定空态文案，无演示事件、无静态档位；导出同样收口为空态说明（1434-1435） |
| 统计卡片（总数/错误/警告/API 或分类计数） | real（由当前列表长度实时计算） | app.js 1309-1329；index.html 1263-1281 | 无 | confirmed：初始 `0` 为真实零值，非演示占位；risk 分类计数固定 0（1322-1324） |
| 策略下拉 / 级别过滤 / 搜索 / 清空 / 导出 | real | app.js 1164-1177、1215-1234、1413-1448；index.html 1247-1259 | 无 | confirmed：下拉空态「暂无可用策略」（1171）；清空仅作用于 system（1416）；导出文本字段缺失用空串（1431、1433），不编数据 |

### 2.3 AI 复盘页（`page-review`）

| 页面/面板 | 分支归属 | 证据行号 | 对照草案的缺口 | 结论 |
|---|---|---|---|---|
| 策略下拉 / 周期 / AI 开关 / 生成按钮 | real | app.js 2515-2532、2659-2704；index.html 1307-1321 | 无 | confirmed：空列表「暂无可用策略」（2523-2525）；未授权走状态提示（2681-2684），不回填演示报告 |
| 复盘指标网格（10 项：平仓盈亏笔数/胜率/盈亏比/期望值/区间净盈亏/区间收益/区间回撤/最大连亏/手续费/当前持仓） | real | app.js 2570-2588；index.html 1331-1332 | 草案 outcome 段的 `exit_price / holding_period_hours` 未单列；指标为聚合统计，不含单笔决策还原 | confirmed：`_reviewNum/_reviewPct` 对 null/空串/NaN 返回 `--`（2498-2506）；真实 0 渲染为 `0` / `0.00` / `0.0%`；手续费 4 位小数 |
| 归因统计三卡（亏损根因 / 止损触发 / 过早止盈） | real（后端字段缺口，固定 `--`） | app.js 2548-2554；index.html 1334-1357 | 草案复盘归因（为什么对/错、运气 vs 体系缺陷）所需的根因分类、止损/追踪止损/保本聚合、出场后价格路径比对字段后端未提供（C-REVIEW-01/02/03） | confirmed：固定 `--`，不编统计数字；卡片附缺口说明文案 |
| 规则诊断列表 | real | app.js 2590-2606；index.html 1363-1365 | 诊断项未回链到具体 trade_id / 决策记录 | confirmed：空数组 →「暂无规则诊断项」；边界见 F3：`detail` 缺失渲染空串而非 `--`，标题/级别缺失回退默认标签 |
| 改进建议列表 | real | app.js 2608-2624；index.html 1367-1369 | 建议无「采纳/固化」状态与回灌动作（草案：经验沉淀为结构化资产） | confirmed：空数组 →「暂无改进建议」；边界同 F3 |
| AI 总结卡片（summary / 诊断要点 / AI 建议 / 风险提示） | real | app.js 2626-2646；index.html 1372-1376 | 无 | confirmed：无内容时整卡隐藏（2643-2646），不展示空壳；数组空块不输出（2632-2636） |
| 计费与归档标记 | real | app.js 2648-2656；index.html 1378-1379 | 无 | 基本合规；边界见 F5：`b.charged || 0` 将缺失扣费 coerce 为 0（2653）；`remaining` 缺失走 `--`（2653、2498-2501）；无 `billing` 对象时整行隐藏 |
| 历史复盘记录列表 | real | app.js 2706-2738；index.html 1381-1391 | 草案「跨周期对比策略是否衰减」仅有同策略历史列表，无跨策略/跨周期对比视图 | confirmed：未选策略 → 引导文案；无记录 →「暂无历史复盘记录」；数值缺失 `--`；`ai_status` 缺失回退 `skipped`（2732） |
| 复盘结论回灌入口 | unknown（前端无入口） | index.html 2268 文字描述；app.js 无对应按钮/端点 | 草案「退役策略经验自动沉淀到知识库」「诊断经人工确认固化为规则」在前端无操作位；闭环依赖后端/文档人工步骤 | confirmed：前端只读归因，不触发资金动作（index.html 1301、1315-1318 注释一致） |

### 2.4 决策审计日志面板（验证层 `audit` 页签）

| 页面/面板 | 分支归属 | 证据行号 | 对照草案的缺口 | 结论 |
|---|---|---|---|---|
| 决策审计日志（最近）列表 | real | app.js 1991-2000、2125-2142；index.html 746-756 | 草案 decision_audit_log 四段字段（signal.confidence/factors、risk_check.position_size/stop_loss/max_drawdown/risk_score、execution.entry_price/slippage/fill_time_ms、outcome.exit_price/pnl/pnl_r/holding_period_hours）前端均未展示；无 trade_id、无策略名、无决策版本号；仅 `time / level / message` | 基本合规；边界见 F1：行内 `log.time / log.level / log.message` 无 `--` 兜底（2137-2139）；接口未成功时保留初始「暂无决策审计日志」（index.html 754），不回填演示 |

### 2.5 交易日志与绩效归因面板（Journal，验证层）

| 页面/面板 | 分支归属 | 证据行号 | 对照草案的缺口 | 结论 |
|---|---|---|---|---|
| Journal 四指标（总交易数/胜率/盈利因子/期望值） | real | app.js 2019-2028、2144-2153；index.html 1104-1121 | 草案归因分析所需因子预测力、分层（信号/执行/风控/样本）拆解未展示 | confirmed：null → `--`（2147-2153）；真实 0 渲染 `0` / `0.0%` / `0.00` / `+0.00R` |
| 行为偏差列表 / 改进建议 | real | app.js 2155-2166；index.html 1131-1137 | 偏差类型/描述无结构化条目编号，不回链交易 | confirmed：空数组 →「暂无行为偏差数据」；边界见 F3：`description` 缺失空串（2159），建议空串（2165） |

### 2.6 引擎 P2 Journal 卡片（`page-engine`）

| 页面/面板 | 分支归属 | 证据行号 | 对照草案的缺口 | 结论 |
|---|---|---|---|---|
| P2 交易归因卡片（周期/总交易/胜率/净利/盈亏比） | real | app.js 2838-2855；index.html 1545-1556 | 同 2.5，无分层归因 | 基本合规；边界见 F5：缺失字段 `?? 0` / `|| 0` coerce 为 0（2843、2850-2852），与「缺失 `--`」口径存在偏差，属 #152 R2 同类；失败走 `p2Fail` 置「数据不可用」（2855） |

### 2.7 策略生命周期 / 健康度面板（验证层 + 引擎页）

| 页面/面板 | 分支归属 | 证据行号 | 对照草案的缺口 | 结论 |
|---|---|---|---|---|
| 验证层健康度列表 `strategy-health-list` | real（仅有清空函数，无 real 渲染器） | app.js 926-930、1980；index.html 876-886 | 草案生命周期八阶段（发现→验证→小资金→规模化→拥挤→衰减→退役→复盘）无阶段标签、无阶段流转记录；拥挤/衰减信号、退役记录、退役经验沉淀均无前端视图 | confirmed：`_clearHealthMonitorCards()` 置空态「暂无策略级健康度绩效数据」；代码路径中无该列表的 real 回填函数；静态演示样例归属见 #152 2.5 节 |
| 引擎页策略健康度列表 `engine-health-list` | real | app.js 2439-2457；index.html 1668-1674 | 同上：无八阶段时间线、无退役记录与退役经验沉淀；仅有总数/健康/观察/暂停退役/平均健康分五个计数 | 基本合规；边界：缺失字段 `\|\| '-'`（2446-2450），真实 0 会被跳过回退 `-`（#152 R3 同类）；catch 仅记日志，失败停留「加载中...」（2455-2457、index.html 1673，#152 R4 同类） |
| 三级状态说明（Active/Watch/…） | unknown（static-mirror 说明文字） | index.html 888-896 | 状态阈值（夏普>1.5、回撤<5% 等）为静态说明，非后端实时判定口径 | confirmed：装饰性说明，不回填数据 |

### 2.8 概览/架构页知识链路静态文案

| 页面/面板 | 分支归属 | 证据行号 | 对照草案的缺口 | 结论 |
|---|---|---|---|---|
| 五层闭环 / 数据流 / 路线图中的知识链路描述 | unknown（static-mirror） | index.html 1818、1833、1891、2016、2027 | 「实验管理」「知识沉淀」「生命周期管理」「自动退役」均为路线图文字，无对应动态面板与端点 | confirmed：纯说明文案；app.js 端点清单（31 处 `/api/*` 与 `request`）中无 experiments / incidents / knowledge / playbook 路由 |

## 三、对照草案的能力缺口汇总（前端入口视角）

| 草案机制 | 草案要求（rev4） | 前端现状 | 缺口分级 |
|---|---|---|---|
| 决策审计日志 `decision_audit_log` | 每笔决策四段 JSON 可完整还原：signal(confidence/factors)、risk_check(position_size/stop_loss/max_drawdown/risk_score)、execution(entry_price/slippage/fill_time_ms)、outcome(exit_price/pnl/pnl_r/holding_period_hours) | 两处列表（日志中心 decision 页签、验证层审计面板）仅回显 `时间/级别/消息`；Journal 与复盘页为聚合统计；无 trade_id 下钻、无四段字段展示、无决策规则版本/模型版本字段 | confirmed 缺口：字段级还原视图未建；后端是否已落四段数据属 unknown（未在本切片复核后端表结构） |
| 故障知识库 `incident_knowledge_base` | 条目含 incident_id/title/severity/status/symptoms/root_cause/solution/prevention/lessons_learned/tags；支持关键词、症状、错误码匹配与方案推荐 | 无端点、无列表/详情/搜索面板；Wiki 踩坑表为静态三列节选；日志中心 risk 页签固定空态（G1/G2/G3） | confirmed 缺口：结构化故障库前端零入口 |
| 实验跟踪 `experiment_tracking` | experiment_id/hypothesis/design/results(control/treatment)/conclusion/decision/reproducibility；可复现 | 无端点、无实验列表/详情/对比面板；仅概览页路线图文字提及 | confirmed 缺口：实验管理前端零入口（注册/冻结/trials/AB 的后端状态不在本切片范围） |
| KnowledgeBase 检索 | `search_similar_incidents`（全文+向量语义+标签）、`search_relevant_experiments`、`get_strategy_playbook` | Wiki 页无检索框；前端无相似故障/相似实验/Playbook 推荐请求；向量语义检索前后端均未见入口 | confirmed 前端缺口；向量检索后端是否存在属 unknown（草案第 111 行已标注待复核） |
| 策略生命周期八阶段 | 阶段记录 + 退役经验自动沉淀知识库 | 仅健康度列表与三级状态说明；无阶段时间线、无退役记录、无经验沉淀视图 | confirmed 缺口 |
| 复盘回灌 | 复盘诊断人工确认后固化为规则/经验；退役策略经验入库 | 复盘页只读产出报告与历史列表；无「固化/采纳/回灌」按钮；Wiki 静态说明闭环靠人工 | confirmed 前端缺口；后端回灌链路属 unknown |

## 四、残留观察与嫌疑点（未改动）

- **F1（real 分支空态口径偏差，minor）**：验证层审计面板行渲染未做字段兜底——`log.time` / `log.level` / `log.message` 直接插值（app.js 2137-2139），后端缺字段时会出现空白或 `undefined`，未按 `--` 口径收口。非演示数字；建议后续对齐 Journal/复盘页的 null 判断。
- **F2（real 分支空态口径偏差，minor）**：系统日志行 `log.time` / `log.msg` 无 `--` 兜底（app.js 1301、1305）；来源为前端会话内 `debugLogs`（app.js 3-13），缺字段概率低，风险低于 F1。
- **F3（real 分支空串占位，minor）**：复盘诊断/建议的 `detail` 缺失渲染空串而非 `--`（app.js 2603、2621）；`title` 缺失回退「诊断项/建议」、`severity` 缺失回退 `info`、`priority` 缺失回退 `low`（2600-2601、2618-2619）；Journal 偏差 `description` 缺失空串（2159）。属默认标签/空串，非演示哨兵。
- **F4（失败分支残留，medium-low）**：`generateReviewReport` 在接口失败/异常时仅清归因三卡（app.js 2670），不清 `review-metrics / review-diagnostics / review-recommendations / review-ai`；若上一次成功报告仍在 DOM，本次失败会残留旧报告卡片。状态条已置失败文案（2695、2699），但数据卡片未收口。建议失败/异常分支补一次清空。
- **F5（缺失 coerce 为 0，#152 R2 同类）**：P2 Journal 卡片 `total_trades ?? 0`、`win_rate || 0`、`total_pnl || 0`、`profit_factor || 0`（app.js 2843、2850-2852）；复盘计费 `b.charged || 0`（2653）。后端字段缺失时显示 0 而非 `--`，与「缺失值 `--`、区分真实 0 与无数据」口径存在偏差；非硬编码演示值。
- **F6（未授权分支未显式收口，minor）**：复盘策略下拉 `loadReviewStrategies` 未单独判 `_unauthorized`（app.js 2518-2521）；未授权时 `res.data` 为空，回落「暂无可用策略」，不报错也不提示登录。行为可接受，建议后续与日志中心的未授权提示对齐。
- **F7（静态定性 badge 不随接口翻转，#152 R6 同类）**：审计面板「实时」（index.html 750）、生命周期「实时监控中」（index.html 880）为静态装饰标签，接口失败时不翻转；非数据数字。

## 五、改动与验证记录

- 改动文件：无（只读审计，未改前端代码；未触碰 `configs/ registry.yaml mt5/ secrets/ runtime/ ledger/`）。
- 为什么不改：知识管道相关面板未发现 real 成功分支演示值泄漏；缺口主要是能力入口未建，超出本切片「只读审计」范围。
- 实际验证：
  - `node --check D:\Trader\frontend-pro\js\app.js` → PASS（exit 0，Node v22.23.2）。
  - 静态通读：index.html 全量、app.js 全量、main.css 全量；CSS grep `demo/演示/占位/66.7/1.85/42000/2300/10,234/OKX-DEMO` 0 命中。
  - 端点清单复核：app.js 31 处接口调用无 knowledge / incident / experiment / playbook / wiki 路由；复盘/日志/审计段数字哨兵扫描仅命中 CSS 色值、布局宽度、时间乘数 1000、`limit=200` 与默认标签，无演示数值。
  - `index_new.html`、`index_backup_20261026_004342.html` 为未被 `index.html` 引用的历史快照，`src/` 三个子目录为空；本轮未审计快照内口径。

## 六、未验证项（显式标注）

- 浏览器实跑、已登录真实态联调：复盘报告 / 历史记录 / 日志中心 / 审计面板在真实接口返回下的页面实际渲染——**未验证**。
- 后端字段实际命名与空值形态（null / 缺失键 / 空串 / 0）：审计日志 `time/level/message`、复盘 `metrics/diagnostics/recommendations/ai/billing`、Journal `behavioral_biases/recommendations` 的边界——**未验证**，依赖登录态联调确认。
- 后端是否已落草案四段决策审计数据、故障库条目、实验跟踪记录、向量/全文检索能力——**未验证**（属后端/数据切片范围）。
- 复盘失败分支残留旧报告（F4）在连续两次生成（成功后失败）场景下的实际 DOM 表现——**未验证**。
- 未登录态与接口全挂态下，本切片面板的空态/兜底视觉上屏效果——**未验证**。
