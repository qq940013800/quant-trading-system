# 前端真实口径只读审计表（任务 #152）

- 审计范围：`frontend-pro/js/app.js`、`frontend-pro/index.html`、`frontend-pro/css/main.css`
- 审计口径：真实模式（已登录且接口返回真实数据）缺失值显示 `--`；`0` 是真实值必须渲染；仅未登录 / 接口全挂分支保留示例兜底。`!isReal` 分支内的 66.7% / 1.85 / -3.2% / 演示策略列表属合规兜底，不计缺陷。
- 审计日期：2026-11-08
- 审计方式：静态通读 + 分支归属核对；未做浏览器实跑与登录态联调（见「未验证项」）。

## 一、结论

未发现 real 成功分支（已登录且接口 `code===1` / `success===true`）误留硬编码演示哨兵或占位数字。所有数值型演示兜底均挂在 `!isReal` / `!Auth.isLoggedIn()` / 接口异常分支内。本切片**未改动任何代码**，仅交付本审计表。

语法验证：`node --check D:\Trader\frontend-pro\js\app.js` → PASS（Node v22.23.2）。

## 二、逐面板核对

### 2.1 仪表盘（page-dashboard）

| 面板 / 字段 | 分支归属 | 证据行号（app.js / index.html） | 结论 |
|---|---|---|---|
| 顶栏账户名 `nav-account-name` | real：无凭证显示 `--`；demo：`OKX-DEMO 已连接` | app.js 1549-1550、1594；index.html 64 | 合规。real 空态为 `--`，演示名仅 `!isReal` |
| 账户列表 `accounts-list` / `modal-accounts-list` | real：空态「暂无已连接交易账户」；demo：OKX-DEMO 样例 | app.js 1528-1566；index.html 119-123 | 合规。演示凭证 `8a12...0cf2` 仅 `!isReal && credentials.length===0` |
| 总权益 `total-equity` | real：不由 summary 回填，仅由 `loadRealPositions` 真实权益覆盖；HTML 初始 `--` | app.js 1597-1607、3062-3075；index.html 84 | 合规。`10,234.56` 仅 `!isReal` 且无 `total_equity` 时出现 |
| 今日盈亏 `daily-pnl` | real：字段非 null 即渲染（含真实 0），缺失 `--`；demo：`+123.45` | app.js 1609-1621；index.html 89 | 合规。0 作为真实值渲染，未被演示占位顶替 |
| 今日交易 `stat-trades` | real：后端值渲染，缺失 `--`；demo：`12` | app.js 1627-1634；index.html 133 | 合规 |
| 胜率 `stat-winrate` | real：后端百分数渲染，缺失 `--`；demo：`66.7%` | app.js 1636-1643；index.html 137 | 合规（任务约定的合规兜底） |
| 盈亏比 `stat-plratio` | real：后端值渲染，缺失 `--`；demo：`1.85` | app.js 1645-1652；index.html 141 | 合规 |
| 最大回撤 `stat-drawdown` | real：后端负数百百分数渲染，缺失 `--`；demo：`-3.2%` | app.js 1654-1662；index.html 145 | 合规 |
| 夏普 `stat-sharpe` | real：后端年化夏普渲染，null/样本不足 `--`；demo：`1.85` | app.js 1664-1672；index.html 149 | 合规 |
| 策略卡片 `running-strategies` / `strategies-grid` | real：空列表渲染「暂无策略」；demo：三条示例策略 | app.js 1675-1692、1708-1734；index.html 233-255 | 合规。演示三条（ML增强趋势/均值回归/突破）仅 `!isReal && isEmpty` |
| 持仓列表 `positions-list` | real：空态「暂无持仓」；demo：BTC/ETH 两条样例 | app.js 1737-1751；index.html 96-101 | 合规。样例 `0.5 @42000 / 2.0 @2300` 仅 `!isReal` |
| 成交记录 `trades-list` | real/demo 统一：空态「暂无成交」，无演示成交兜底 | app.js 1766-1818；index.html 106-111 | 合规。pnl 缺失显示 `--`，时间/方向/品种缺失均 `--` |
| K 线图 `main-chart` | real 登录态空/异常：`_clearKlinePanel()` 清空蜡烛/量/价格，badge「暂无真实行情」；mock 随机行情仅未登录 | app.js 256-316、326-347；index.html 159-175 | 合规。42000 起的人造行情仅 `!Auth.isLoggedIn()` |
| 订单簿 `orderbook-asks/bids/spread` | real 登录态推送为空/断流：清空档位，spread `--` | app.js 478-529；index.html 185-194 | 合规。无静态演示档位 |
| 实时价格 `chart-price` | real：WS/`/api/market/ticker` 回填；失败仅记日志，初始 `--` | app.js 309-316、409-439、3044-3059；index.html 159 | 合规 |
| 全局演示哨兵 `demo-global-badge` | 仅未登录 / 核心接口全挂上屏；真实登录态一律隐藏 | app.js 1465-1506、1894、3116 | 合规。`coreReal` 判定 credentials + summary 均非 error 且 code===1 |

### 2.2 策略中心 / 策略详情弹窗

| 面板 / 字段 | 分支归属 | 证据行号 | 结论 |
|---|---|---|---|
| 策略详情绩效（收益/夏普/回撤/胜率/笔数） | real：策略携带字段，null → `--`；不编演示数字 | app.js 735-751；index.html 273 起 | 合规。`detail-total-return` / `detail-profit-factor` 固定 `--`（后端未返回） |
| 策略详情参数（资金/杠杆/止损） | real：携带字段，null → `--`；累计亏损停止固定空态 | app.js 754-766 | 合规 |

### 2.3 回测工作台（page-backtest）

| 面板 / 字段 | 分支归属 | 证据行号 | 结论 |
|---|---|---|---|
| 回测结果四指标 `bt-total-return/Sharpe/dd/winrate` | real：历史记录回填；空记录 / 异常 → `_btBlankResults()` 全 `--`，曲线清空 | app.js 871-889、1044-1085；index.html 435-447 | 合规。回撤恒带负号，win_rate/sharpe null → `--` |
| 策略绩效对比表 `comparison-table-body` | real 成功：`_clearComparisonTable()` 全部置 `--`（后端暂无逐策略绩效） | app.js 895-904、1056；index.html 510-541 | 合规。HTML 静态三行初始均为 `--` |
| 月度收益热力图 `monthly-heatmap-grid` | real 成功：`_clearMonthlyHeatmap()` 全部置 `--` | app.js 906-913、1057；index.html 463-491 | 合规。单元格初始 `--` |
| 回测曲线（权益/回撤） | real：`_btCurvePoints` 映射；无序列 → 空数据 | app.js 1005-1042 | 合规 |

### 2.4 风险管理（page-risk）

| 面板 / 字段 | 分支归属 | 证据行号 | 结论 |
|---|---|---|---|
| 风险阈值卡（当前回撤/限额/权益/单日亏损限额） | real：后端字段缺失 `--`；接口失败 → `_clearRiskThreshold()` 全 `--`，进度条归零 | app.js 2270-2307；index.html 640-653 | 合规。单日亏损限额后端未透出，固定 `--`，不用配置默认值冒充 |
| 组合风险摘要（敞口/单策略/相关性/日回撤/VaR/CVaR） | real：`renderRiskDashboard` 仅回填已透出字段；HTML 初始 `--` | app.js 2354-2385；index.html 556-590 | 基本合规；边界见风险项 R3（真值判断跳过真实 0） |
| 策略级风险预算 `risk-budget-list` | real 成功：`_clearRiskBudget()` 清空为「暂无策略级风险预算数据」；静态 35%/28%/22%/15% 为演示兜底 | app.js 919-923、2247-2249；index.html 596-626 | 有条件合规；残留观察 R1 |
| 策略级回撤 `strategy-dd-list` | 固定空态文案，无后端端点，不拉演示 | index.html 670-674 | 合规 |
| 风控告警列表 `risk-alert-list` | real：接口空 / 失败 → 空态「暂无风控告警 / 拦截事件」 | app.js 2311-2346；index.html 684-686 | 合规。消息缺失 `--`，时间缺失 `--` |

### 2.5 AI 验证层（page-validation）

| 面板 / 字段 | 分支归属 | 证据行号 | 结论 |
|---|---|---|---|
| 验证模块状态 `validation-modules` | real：`renderValidationModules` 由后端 modules 渲染；HTML 初始占位文案 | app.js 1976-1977、2082-2103；index.html 741-743 | 合规 |
| 策略健康度卡片 `strategy-health-list` | real 成功：`_clearHealthMonitorCards()` 清空 | app.js 926-930、1980；index.html 884-886 | 合规 |
| 数据集质量 `dq-*` 五项 + 综合评分 | real 成功：`_clearDataQuality()` 置 `--`，进度条归零 | app.js 964-977、1982；index.html 961-1005 | 合规 |
| L1 状态 / 分布 / 推荐 / HA 组件 | real 成功：`_clearRegimeAndHa()` 清空为待接入文案 | app.js 980-989、1984；index.html 1061-1083 | 合规 |
| 旧安全 / 拥挤度 / 可观测 / CI-CD 面板 | real 成功：`_clearLegacyMonitorPanels()` 清空（数据见引擎页 P2 卡片） | app.js 992-1002、1986；index.html 1170-1220 | 合规 |
| TCA 成本六项 + 总成本 / 结论 | real：`no_orders` / 失败 → `_clearTca()` 全 `--`；`renderTcaSummary` 字段缺失 `--` | app.js 932-961、2030-2043；index.html 914-948 | 合规 |
| 压力测试五情景 + 综合评分 | 仅 `data.data_kind==='real'` 且有情景才渲染；否则 `_clearStressTest()` 名称/数值/描述/评分全 `--` | app.js 2169-2234；index.html 767-797 | 合规。内置演示情景不得顶替真实冲击测算 |
| 过拟合三重验证 PBO/CPCV/DSR | real：null → `--`；CPCV 布尔渲染 通过/不稳定 | app.js 2045-2080；index.html 819/836/853 | 合规 |
| 绩效归因 journal 四指标 + 偏差 / 建议 | real：字段 null → `--`；偏差空 → 「暂无行为偏差数据」 | app.js 2144-2167；index.html 1107-1119、1133-1136 | 合规 |
| 漂移监控 `drift-data/concept/status` | real：后端未返回 drift_monitor 模块时保留空态占位 | app.js 2105-2123；index.html 1144-1155 | 合规 |
| 决策审计日志 `audit-logs` | real：后端 logs 渲染；HTML 初始「暂无决策审计日志」 | app.js 2125-2142；index.html 753-755 | 合规 |
| 模块接口异常兜底 | `loadValidationData` catch：保留空态 `--`，不回填演示哨兵 | app.js 2060-2063 | 合规 |

### 2.6 日志中心（page-logs）

| 面板 / 字段 | 分支归属 | 证据行号 | 结论 |
|---|---|---|---|
| 日志列表（决策/交易/系统/风控） | 全部真实驱动；未授权 / 非 code===1 → 清空并置错误文案；风控事件固定空态，不拉演示 | app.js 1179-1206、1331-1359；index.html 1290-1292 | 合规 |
| 统计卡片（总数/错误/警告/API 数） | 由当前列表长度实时计算；HTML 初始 `0` 为真实零值 | app.js 1309-1329；index.html 1267-1279 | 合规。初始 0 非演示占位 |

### 2.7 AI 复盘（page-review）

| 面板 / 字段 | 分支归属 | 证据行号 | 结论 |
|---|---|---|---|
| 复盘指标网格（10 项） | real：`_reviewNum/_reviewPct` 缺失 → `--` | app.js 2498-2506、2570-2588；index.html 1332 | 合规 |
| 归因统计（根因/止损/过早止盈） | 后端字段缺口，固定 `--`，不编统计数字 | app.js 2548-2554、2557；index.html 1344-1355 | 合规 |
| 规则诊断 / 改进建议 / AI 总结 / 计费 | real：空数组 → 空态文案；AI 无内容 → 隐藏 AI 卡片 | app.js 2590-2656；index.html 1364-1379 | 合规 |
| 历史复盘列表 | real：无记录 → 「暂无历史复盘记录」；数值缺失 `--` | app.js 2706-2738；index.html 1388-1389 | 合规 |

### 2.8 核心引擎（page-engine）

| 面板 / 字段 | 分支归属 | 证据行号 | 结论 |
|---|---|---|---|
| P2 六卡片（HA/Journal/Security/Crowding/Obs/CICD） | real：后端渲染；失败 `p2Fail` 置灰灯 + `OFFLINE` + 「数据不可用」；HTML 初始 `--` / 「数据加载中...」 | app.js 2759-2935；index.html 1529-1621 | 基本合规；边界见风险项 R2（缺失字段 coerce 为 0） |
| 五层市场识别 `market-layers-list` | real：后端 layers 渲染；catch 仅记日志 | app.js 2392-2405；index.html 1640-1642 | 观察项 R4：失败停留「加载中...」，未收口空态；无演示数字 |
| 优化引擎状态 `optimizer-status` / 因子库 `factor-list` | real：后端渲染；catch 仅记日志 | app.js 2407-2437；index.html 1654-1659 | 同 R4 |
| 策略健康度 `engine-health-list` | real：后端渲染；`-` 兜底；catch 仅记日志 | app.js 2439-2457；index.html 1672-1674 | 同 R4 |
| 综合市场分析 `market-analysis-result` / badge | real 登录态：空态收口「暂无真实综合市场分析，待接入」，badge「待接入」；仅未登录才拉 `/demo` 端点 | app.js 2459-2487；index.html 1683-1688 | 合规。静态「⚠️ 演示数据」文案会被 real 分支覆盖 |

### 2.9 样式表

| 文件 | 结论 |
|---|---|
| `css/main.css` | 无 demo / 演示 / 占位数值 / 哨兵文案；未发现静态数据口径问题。 |

## 三、残留观察与风险（未改动，超出本切片「real 分支演示值泄漏」修复范围）

- **R1（风险预算静态兜底的失败分支归属）**：`index.html` 597-626 的 35%/28%/22%/15% 演示占比，仅在 `/api/risk/portfolio` 成功时由 `_clearRiskBudget()` 清空；`loadRiskData` 的 else / catch 分支（app.js 2253-2261）只调 `_clearRiskThreshold()`，不清风险预算。按既定口径「接口全挂可保留兜底」，当前属失败兜底分支；但与同页阈值卡失败即清空的处理不一致。建议后续在 else/catch 补 `_clearRiskBudget()`，并明确未登录态是否保留该演示样例。**本切片未改。**
- **R2（P2 卡片缺失字段 coerce 为 0）**：`loadP2ModuleCards` 多处用 `|| 0` / `?? 0`（app.js 2830-2833、2843、2850-2852、2867-2870、2891-2893、2910-2912、2928-2931），后端字段缺失时显示 0 而非 `--`，与「缺失值 `--`」口径存在偏差。非硬编码演示哨兵，建议后续按 null → `--` 收敛。
- **R3（风险摘要真值判断跳过真实 0）**：`renderRiskDashboard` 用 `if (data.total_exposure)` 等真值判断（app.js 2356-2384），字段为真实 0 时会被跳过、保留 `--`；0 是真实值，边界场景建议改为 null 判断。
- **R4（引擎页四列表失败停留加载态）**：market-layers / optimizer / factors / engine-health 在接口 catch 后保留「加载中...」静态文案（app.js 2392-2457），未收口为空态或 `--`；不涉及演示数字。
- **R5（策略状态映射优先级隐患）**：app.js 1698 `status: s.status || s.execution_mode === 'live' ? 'running' : 'stopped'`，当 `s.status` 为真值字符串 `'stopped'` 时也会被判为 running。属真实分支状态映射缺陷，非演示泄漏，建议主代理另开任务处理。
- **R6（静态定性 badge 不随接口翻转）**：验证层 / 引擎页若干装饰性标签（「全部正常」「状态良好」「整体健康」「系统健康」「v1.0.0 运行中」「实时监控中」等，index.html 750/880/1078/1167/1185/1200/1216）不随接口失败翻转；非数据数字，未改。
- **R7（表单控件默认值，非展示口径）**：风险限额输入框 5/30/10/1（index.html 697-709）、回测初始资金 10000 与日期 2024-01-01 / 2024-12-31（417/421/425）、API 账户弹窗默认 `value="DEMO"`（2493）、编辑策略弹窗默认名「ML增强趋势策略」（2443）、回测策略下拉三条示例（395-397）。均为表单初始占位 / 控件默认值，不是数据面板展示值；按约束未改。

## 四、改动与验证记录

- 改动文件：无（未发现 real 成功分支误留演示值，按任务约束不改代码）。
- 为什么不改：所有数值型演示兜底均位于 `!isReal` / `!Auth.isLoggedIn()` / 接口异常分支；real 分支缺失值走 `--`，真实 0 正常渲染。
- 实际验证：
  - `node --check D:\Trader\frontend-pro\js\app.js` → PASS（exit 0，Node v22.23.2）。
  - 静态通读 app.js 全量 3147 行、index.html 全量 2535 行、main.css 全量 935 行；grep 复核 66.7 / 1.85 / -3.2 / 10,234.56 / 123.45 / 42000 / 2300 / 45.67 / 234.56 / OKX-DEMO 等哨兵，归属均符合口径。
- 未验证项（显式标注）：
  - 浏览器实跑、已登录真实态联调、各接口返回 null/0/缺字段时的页面实际渲染——**未验证**。
  - 未登录态与接口全挂态下演示兜底的视觉上屏效果——**未验证**。
  - 后端字段实际命名与空值形态（null / 缺失键 / 空串）的边界——**未验证**，依赖后续登录态联调确认。
