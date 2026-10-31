# QuantDinger Pro 待办清单

> 最后更新：2026-10-31
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
