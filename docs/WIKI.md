# QuantDinger Pro 内部 Wiki 思维导图

> 基于第一性原理 + 全球顶级量化机构最佳实践
> 最后更新：2026-11-08（新增交易所前端看板对接对照表 + 真实口径收口规则索引）

---

## 🧠 系统整体架构（五层闭环）

```
量化交易系统 = 数据输入 → 信号生成 → 组合构建 → 订单执行 → 风控监控 → 绩效反馈
```

### 第一层：数据层
- ✅ OKX 行情API（ticker/kline）
- ✅ PostgreSQL 时序数据库
- ✅ Redis 缓存
- ⏳ 历史K线数据导入
- ⏳ 另类数据接入

### 第二层：信号层（AI/ML核心）
#### 五层市场识别架构
| 层级 | 模块 | 状态 | 说明 |
|------|------|------|------|
| L1 | 市场状态识别 | ✅ 规则版完成 | 趋势/震荡/高波动/低波动 |
| L2 | 市场结构识别 | ✅ 规则版完成 | BOS/CHoCH/高低点序列 |
| L3 | 市场趋势识别 | ✅ 规则版完成 | 趋势方向/强度/阶段 |
| L4 | 价格行为识别 | ✅ 规则版完成 | 吞没/针形线/内包线 |
| L5 | K线形态识别 | ✅ 规则版完成 | 早晨之星/黄昏之星等 |
| ML增强版 | 五层模型增强 | ⏳ 待做 | 提高识别准确率 |

#### 策略优化引擎
- ✅ 因子库（10个基础因子）
- ✅ 参数优化器（网格/随机/贝叶斯）
- ✅ 过拟合防御框架
- ⏳ 因子扩展到20+
- ⏳ PBO/CPCV/Deflated Sharpe算法实现
- ⏳ ML训练管线

#### 策略匹配引擎
- ✅ 匹配规则引擎（市场状态→策略组合）
- ✅ 三级健康度监控
- 🔄 策略注册/匹配：本轮正在把 3 个演示策略注册进匹配引擎（由并行任务推进，结果以 `docs/TODO.md` 第 5 项与 `docs/p0-modules-upgrade-report.md` 为准）
- ⏳ 接入真实策略（目标 ≥5 个，当前只有 3 个演示策略）
- ⏳ 动态资金分配（PM模型）
- ⏳ 自动退役逻辑

### 第三层：组合层
- ✅ 仓位管理基础框架
- ✅ 波动率目标法
- ✅ 分数Kelly公式
- ⏳ 风险预算
- ⏳ 分散化校验（风险因子分散，不是持仓数量分散）
- ⏳ 回撤自动减仓

### 第四层：执行层
- ✅ OKX API客户端
- ✅ 现货下单接口
- ✅ 持仓查询接口
- ⏳ 下单失败排查（All operations failed）
- ⏳ 滑点建模
- ⏳ 拆单算法（TWAP/VWAP）
- ⏳ 实时WebSocket推送

### 第五层：风控层
- ✅ 止损框架
- ✅ 追踪止损
- ✅ 移动止盈
- ⏳ 系统层强制止损（不依赖人工）
- ⏳ 最大回撤控制
- ⏳ 尾部风险监控
- ⏳ 事前拦截+事中监控+事后审计

---

## 🎯 稳定盈利第一性原理

```
稳定盈利 = 正期望值 × 大数定律 × 不爆仓
```

### 怎么赚钱（Alpha四分类）
1. **行为偏差**：人性的非理性（处置效应、羊群效应）→ 反转/动量策略
2. **信息优势**：更快获取/处理信息 → 高频新闻交易
3. **统计偏差**：数据中的伪规律 → 统计套利/配对交易
4. **结构红利**：市场规则创造的机会 → 做市/指数再平衡

### 怎么亏钱（逆向思维：先想怎么会死）
1. ❌ 不止损，死扛等回本 → 一次大亏回到解放前
2. ❌ 仓位太重 → 一次假突破就爆仓
3. ❌ 过拟合，回测好看实盘亏 → 数据挖掘偏差
4. ❌ 策略失效了不知道还在做 → Alpha衰减
5. ❌ 前视偏差，用未来数据 → 回测假阳性
6. ❌ 杠杆太高 → LTCM两个诺奖得主都没了
7. ❌ 不分散，全仓一个策略 → 策略失效全完

---

## 🏆 全球顶级机构对标差距

| 机构 | 核心优势 | 我们的差距 | 改进方向 |
|------|---------|-----------|---------|
| **Renaissance** | 海量弱信号叠加，不追求圣杯 | 只有10个因子，太少 | 扩展到20+弱信号因子 |
| **Two Sigma** | 另类数据+ML驱动 | 只有价格数据 | 接入另类数据（成交量/持仓量/舆情） |
| **Citadel** | 风控前置，事中拦截 | 风控是事后的 | 订单发出前就做风控检查 |
| **Jane Street** | 做市赚流动性钱 | 还没做市策略 | 先把趋势跟踪做好 |
| **DE Shaw** | 多策略平台，方法论优先 | 单策略为主 | 策略组合分散风险因子 |
| **Millennium** | 绝对收益，不追求高Sharpe | 追求高Sharpe反而过拟合 | 追求稳定正收益，不追求高Sharpe |

---

## 🏦 主流交易所前端看板对接对照（行情层 CCXT 适配）

> 原则：行情层继续走 CCXT 统一适配，实盘自研交易链路不动；下表为前端看板字段对接与口径注意点。**除 OKX demo 只读实测外，Bybit/WEEX/币安字段与接口尚未核验**，接入前必须以各交易所官方文档 + CCXT 统一签名为准，不按本表猜字段。

| 看板模块 | OKX（已接 demo 只读） | Bybit | WEEX | 币安 | 前端口径注意 |
|---|---|---|---|---|---|
| 行情 ticker | ✅ 已接（BTC 实时价） | ⏳ 未核验 | ⏳ 未核验 | ⏳ 未核验 | 现价/24h 涨跌统一前端格式化；缺失 `--` |
| K 线 | ✅ 框架已搭（kline） | ⏳ 未核验 | ⏳ 未核验 | ⏳ 未核验 | 时间戳时区对齐；空 K 线不画零值 |
| 订单簿 | ⏳ 未接 | ⏳ 未核验 | ⏳ 未核验 | ⏳ 未核验 | 买卖盘档位/数量口径以交易所为准 |
| 持仓 | ✅ 框架已搭（现货口径偏大，见 TODO 阻塞项） | ⏳ 未核验 | ⏳ 未核验 | ⏳ 未核验 | 现货/合约口径区分；持仓数量不得用资金账户总额近似 |
| 成交历史 | ✅ 两笔 demo 成交落库 `qd_quick_trades` | ⏳ 未核验 | ⏳ 未核验 | ⏳ 未核验 | 成交价/数量/手续费口径；成交状态枚举对齐 |
| 账户权益 | ✅ demo 只读权益约 9.3 万 USDT 量级 | ⏳ 未核验 | ⏳ 未核验 | ⏳ 未核验 | 余额/可用/冻结分列；权益口径统一，不混用 |
| 下单面板 | ⏳ 实盘链路不动，本轮仅收口展示空态 | ⏳ 未核验 | ⏳ 未核验 | ⏳ 未核验 | 危险操作二次确认；风控 gate 前置，不改交易路由 |

### 对接纪律
- ✅ 先登录拿 token、Bearer 鉴权；401 循环按真实鉴权链路排查，不走假登录后门。
- ✅ 看板所有指标先判"数据源状态"：真实回填 / 无数据 `--` / 仅演示兜底；真实模式禁止演示哨兵顶替。
- ❌ 禁止凭上表或记忆写交易所字段名；接入新交易所前 Read 官方文档与 CCXT 签名实现。
- ❌ 禁止在前端把现货持仓、合约持仓、资金账户余额混为一个口径展示。

---

## 📋 P0/P1/P2 待办清单

### 🔴 P0（阻塞实盘，必须最先做）
- [ ] Docker容器恢复（我之前手动删了，要用compose恢复）
- [ ] API认证问题（开发模式跳过token）
- [ ] OKX实盘全链路测试（下单/持仓/K线渲染）
- [ ] 五层识别接入真实K线数据
- [ ] 策略生命周期自动退役
- [ ] GitHub推送修复

### 🟡 P1（核心功能，决定能赚多少）
- [ ] 策略匹配引擎接入真实策略
- [ ] 五层识别ML增强版
- [ ] 因子库扩展到20+
- [ ] 过拟合三重验证算法实现
- [ ] 动态资金分配（PM模型）

### 🟢 P2（企业级，决定能走多远）
- [ ] 6个模块前端可视化（本轮并行任务补全，结果以 `docs/TODO.md` 第 9 项为准）
  - [ ] 高可用与灾备面板
  - [ ] 可观测性与告警面板
  - [ ] CI/CD 与部署状态面板
  - [ ] 交易日志归因面板
  - [ ] 安全与合规面板
  - [ ] 策略拥挤度监控面板
- [ ] WebSocket实时推送
- [ ] 拆单执行算法
- [ ] 尾部风险监控
- [ ] 策略灰度上线机制

---

## 🕳️ 踩坑经验（避坑指南摘要）

### 工程踩坑
1. ❌ 随便删正在运行的Docker容器 → 必须用docker-compose恢复，不要手动rm
2. ❌ PowerShell处理UTF-8中文 → 会乱码，用Python
3. ❌ 浏览器缓存旧JS → 必须强制刷新ignoreCache
4. ❌ 前后端函数名不一致 → 先Read代码确认签名再调用
5. ❌ Docker代码不是volume挂载 → 改完必须docker cp + restart
6. ❌ **直接 pull 官方后端镜像 → 我们自己写的 `account.py`/`okx_client.py` 不在里面**：Dockerfile 必须 `COPY app/` 整体进去；build 完用 `/openapi.json` 验证 `/api/okx/*` 路由真的注册了（详见 `skills/quant-trading-expert/references/docker-okx-debug-2026-10.md`）
7. ❌ **本地直连 OKX API 被墙**（curl 退出码 7）：不是代码问题，是出口网络问题；必须走代理或把后端部署到能直连 OKX 的区域，否则"联通"结论都是假阳性

### 运维 / Docker 分支（2026-10-28 补充）
- 后端容器：故障后用官方镜像恢复，`/health` 200、PostgreSQL 连接正常
- 前端容器：`quantdinger-frontend` 跑在 :8888，与本地源码**未挂 volume**，本地改完必须 rebuild 或 `docker cp` + restart
- OKX 网络：本地出口访问 `www.okx.com` 被墙，需要代理 / 海外服务器中转
- 镜像自定义路由：`account.py`、`okx_client.py` 必须由 Dockerfile `COPY` 进镜像，不能依赖官方镜像自带路由

### 量化踩坑
1. ❌ 追求高Sharpe → 往往过拟合，追求稳定正收益
2. ❌ 用未来数据做回测 → 前视偏差，只用收盘后数据
3. ❌ 决策规则跟着结果调 → 实验前冻结，实验后只能评估
4. ❌ 只报告成功的试验 → trials计数包含所有失败
5. ❌ 回撤大了还不减仓 → 10%自动减仓50%，15%清仓

---

## 📚 知识沉淀机制

### 四层知识模型
1. **决策审计日志**：每笔交易为什么做、输入了什么、结果如何
2. **事后复盘**：每周复盘，什么做对了、什么做错了、下次怎么改
3. **故障知识库**：每个bug怎么发现的、根因是什么、怎么修的
4. **实验管理**：每个策略实验的参数、结果、结论

### 复用机制
- 遇到问题先检索知识库
- 新策略上线先看历史经验
- 每次故障都沉淀成文档
- 不重复踩同样的坑

---

**维护人**：QuantDinger
**更新频率**：每天开发后更新
**用途**：新成员快速上手、避免重复踩坑、对齐全局认知

---

## 🔁 五层知识管理闭环（2026-10-28 新增）

> 第一性原理：知识不能只堆在脑子里，必须**按层落盘、可追溯、可回灌**。每一层都是下一层的输入，上一层是下一层的约束。

### 闭环总览

```
┌──────────────────────────────────────────────────────────────────────┐
│                          L5 全局视图（认知对齐）                       │
│            docs/WIKI.md  +  skills/.../quant-trading-expert/SKILL.md │
│                       ↑ 汇总 / 反哺 / 校验 ↑                          │
└──────────────────────────────────────────────────────────────────────┘
                              ▲               ▲
                              │ 产出          │ 指导
                              │               │
┌──────────────────┐   沉淀   │   登记待办    │
│ L4 待办追踪      │──────────▶│               │
│ docs/TODO.md     │           │               │
└──────────────────┘           │               │
                                ▼               ▼
┌──────────────────┐   归纳   ┌──────────────────────────────┐
│ L3 经验沉淀      │────────▶│ L2 决策记录                  │
│ docs/RULES.md    │         │ docs/decisions/*.md          │
│ skills/.../references/│     │ ADR：为什么这么做             │
└──────────────────┘         └──────────────────────────────┘
                                ▲
                                │ 触发复盘 / 记录决策
                                │
┌──────────────────────────────────────────────────────────────────────┐
│                          L1 代码层（真实来源）                         │
│   core/  scripts/  ops/  tests/  mt5/  backend_api_python/           │
│   frontend-pro/   configs/   registry.yaml                           │
└──────────────────────────────────────────────────────────────────────┘
```

### 每层职责与产物路径

| 层级 | 名称 | 职责 | 产物路径 | 谁来写 |
|------|------|------|----------|--------|
| **L1** | 代码层 | 系统真实行为的唯一来源；一切结论必须能回到代码 | `core/`、`scripts/`、`ops/`、`tests/`、`mt5/`、`backend_api_python/`、`frontend-pro/`、`configs/`、`registry.yaml` | 开发者（含 AI 协同） |
| **L2** | 决策记录 | 每个非平凡选择为什么这么做、备选方案、否决理由；实验前冻结的 decision_rule | `docs/decisions/ADR-*.md`、`registry.yaml`（trials_N 原子递增） | 开发者 + 实验脚本 |
| **L3** | 经验沉淀 | 踩坑/模式/反模式；可被下次同类问题直接检索命中 | `docs/RULES.md`、`skills/quant-trading-expert/references/*.md`、`docs/frontend-debug-experience.md` | 每次故障/复盘后追加 |
| **L4** | 待办追踪 | 未完成项、技术债、P0/P1/P2 重排；不虚报进度 | `docs/TODO.md`、技能库 `references/project-todo-and-tech-debt.md` | 每天开发后更新 |
| **L5** | 全局视图 | 跨层索引、机构对标、五层系统架构图、新成员上手入口 | `docs/WIKI.md`、技能库 `SKILL.md` | 周期性刷新 |

### 闭环动作（每日 / 每次故障后必跑）

1. **L1 → L2**：做了一个非平凡决策（改路由、改阈值、改架构）→ 在 `docs/decisions/` 落一份 ADR，写明备选与否决理由。
2. **L2 → L3**：实验/上线失败或踩坑 → 把「现象/根因/修复/预防/验证命令」追加到 `docs/RULES.md`。
3. **L3 → L4**：修完一个 bug 或做完一个模块 → 在 `docs/TODO.md` 改状态，未完成的归入 P0/P1/P2。
4. **L4 → L5**：每周/每次大版本 → 把 TODO 关键变化、新踩坑、新对标同步进 `docs/WIKI.md` 和技能库 `SKILL.md`。
5. **L5 → L1**：下次遇到问题，**先在 L3/RULES.md 和技能库 references 检索**，命中就按经验做；没命中才动手。这一步是闭环的回灌口。

### 反模式（破坏闭环）

- ❌ 只改代码不写 ADR → 三个月后没人知道为什么这么写。
- ❌ 踩坑只口头说、不追加 RULES.md → 下次还踩。
- ❌ TODO 只增不改状态 → 清单失去可信度，最终没人看。
- ❌ WIKI 与代码脱节 → 全局视图变成过期宣传册。
- ❌ 把临时方案当完成项勾选 → 技术债越积越多。

**五层知识管理闭环 已纳入 WIKI（2026-10-28）**

---

## 🧠 AI 复盘与经验回灌（2026-11-08 新增）

> 第一性原理：每一笔交易决策都是一次实验；复盘就是对照「输入 → 判断 → 结果」做归因，把**运气造成的盈亏**与**可改进的策略/执行/风控缺陷**分开。复盘的产出不是一份好看的报告，而是可复用、可回灌到规则库的经验。

### 复盘链路（真实来源，动态报告不落静态 Wiki）

```
成交记录 / 决策日志
        │  POST /api/strategies/review-report（规则诊断 + 可选 AI 总结）
        ▼
复盘报告：绩效指标 · 规则诊断 · 改进建议 · AI 总结 · 计费标记
        │  归档
        ▼
qd_strategy_review_reports  ── GET /api/strategies/review-report/history 历史回溯
```

- 前端入口：交易终端「AI复盘」页；策略、回看周期（7/30/90 天）、是否含 AI 总结均可选。
- 报告结构：策略概要、绩效指标网格、规则诊断（info/warn/error）、改进建议（low/medium/high）、AI 总结（诊断要点 / 建议 / 风险提示）、计费与归档标记、历史记录列表。
- 指标口径：胜率、区间收益、最大回撤、费用占名义比均为 **0–100 数值**，前端直接加 `%`，不再二次 ×100。

### 边界与纪律

1. **只读归因**：复盘页面只做分析与历史回溯，**不触发下单、平仓、改仓位或任何资金动作**；交易路由、风控 gate、资金计算不在复盘链路内。
2. **样本不足不下结论**：已平仓样本偏少（后端诊断 `sample_small`）时，结论仅作方向性参考，需积累 10–20 笔平仓后再判断参数是否调整。
3. **结论可追溯**：每条诊断/建议必须能回溯到所选周期内的真实成交记录与日志；不沿用静态演示数值。
4. **动态结果不进 Wiki**：单次复盘的盈亏、胜率、AI 摘要留在后端历史库；Wiki 只沉淀方法论、归因框架和**已固化**的经验条目。

### 经验回灌闭环（复盘 → 知识层）

1. 复盘诊断/建议经人工判断确认可固化 → 追加到 `docs/RULES.md` 踩坑表或技能库 `references/`（L3 经验沉淀）。
2. 复盘暴露的待改进项（参数、样本、执行成本、策略失效）→ 登记到 `docs/TODO.md`，按 P0/P1/P2 重排（L4 待办追踪）。
3. 复盘方法论与新踩坑 → 周期性同步回本 Wiki 全局视图（L5）。
4. 下次策略上线或同类问题出现时，先检索 RULES.md 与历史复盘，命中再行动——这是闭环的回灌口。

### 机构最佳实践对标

- **定期事后归因**：把盈亏拆解到信号层、执行层、风控层、样本分层，区分「市场给的运气」与「体系挣到的能力」。
- **区分噪音与失效**：样本期内的回撤先核对样本量、成本与数据质量，不因短期结果直接改决策规则（规则须在实验前冻结）。
- **复盘留痕**：每次复盘归档可回溯记录，支持跨周期对比策略是否衰减，服务生命周期监控与自动退役判断。

### 日志中心：交易 / 决策 / 系统日志（复盘归因素材）

日志中心为 AI 复盘与决策透明度提供同源留痕，三类口径与来源如下：

| 类别 | 来源 / 端点 | 落库表 | 字段口径 |
|---|---|---|---|
| 决策日志 | `GET /api/strategies/logs?id=<sid>` | `qd_strategy_logs` | `level`（`error/info/warning`，含 `SIGNAL` 等后端原样级别）、`message`、`timestamp`（ISO UTC） |
| 交易日志 | `GET /api/strategies/trades?id=<sid>` | `qd_strategy_trades` | 成交事件 `symbol/type/price/amount/profit(net_pnl)/close_reason/created_at`（秒级时间戳） |
| 系统日志 | 前端运行期内存 `debugLogs` | 不落库 | API 请求/响应、价格更新等终端运行记录 |

- **只读边界**：决策/交易日志是后端只读归因素材，前端不提供清空（仅系统内存日志可清空）；日志页面不触发下单、平仓、改仓位或任何资金动作，交易路由、风控 gate、资金计算不在日志链路内。
- **空态纪律**：未选策略时提示先选择策略；后端空数组、未登录或接口异常走真实空态与错误提示，不编演示值；缺失数值显示 `--`。
- **口径注意**：demo 平仓成交当前落在 `qd_quick_trades`，不在 `qd_strategy_trades`，因此交易日志在部分策略下为空属真实空态；决策/交易日志与复盘服务 `samples.recent_logs / recent_trades` 同源。
- **级别归一**：后端 `warning` 前端归一为 `warn`；时间字段兼容数字秒级时间戳与 ISO 字符串；成交方向 `buy/long→多`、`sell/short→空`、`close/exit/flat→平仓`。

---

**AI 复盘与经验回灌 已纳入 WIKI（2026-11-08）**

---

## 🛡️ 系统全局风控设计说明（2026-11-08 新增）

> 第一性原理：截断亏损是风控的左尾工程目标——单笔风险可控、回撤分级、超限拦截、后端强制执行，不靠人工临场判断。
> 口径约定：**confirmed** = 代码已逐行核实落点；**inferred** = 由相邻代码/配置推断，未在本轮回测或实盘复核；**unknown** = 现状不明。阈值一律由 CLEAN 分布校准，不照搬机构数值，本篇不含夏普/胜率/回撤/年化等绩效数字。
> 边界：本篇描述 `core/` 研究/风控层与 `backend_api_python/app/services/` 服务层现状；`mt5/` 执行层常量与 `configs/`、`registry.yaml` 不在本轮改动范围。

### 1.1 风控分层与强制执行链路（现状落点）

| 层级 | 职责 | 代码落点（文件:模块/函数） | 口径 |
|---|---|---|---|
| 单笔止损执行 | 止损触发即走回调平仓，不等人工；止损价只向盈利方向移动 | `backend_api_python/app/services/risk_engine.py`：`RiskEngine._check_stop_loss_trigger`、`RiskEngine._close_all_positions`；回调由 `set_close_position_callback` / `set_reduce_position_callback` 注入 | confirmed |
| 止损单调不变量 | 多头止损只许上移、空头只许下移；放宽方向抛 `StopWideningError`，异常带上下文 | `core/risk/stops.py`：`update_stop`、`StopWideningError`（`current_stop/new_stop/direction/context`） | confirmed |
| 四级止损体系 | 时间 / ATR 价格 / 信号 / 跟踪四类止损，带优先级综合决策 | `core/risk/stops.py`：`check_time_stop`、`check_signal_stop`、`update_trailing_stop`、`evaluate_stops`、`StopType` | confirmed |
| 账户/组合限额 | 总名义、保证金、费用、资金费率、总杠杆、单品种名义、持仓数等限额校验，返回 `allowed` 与违规码 | `backend_api_python/app/services/live_trading/account_risk.py`：`account_risk_snapshot`、`account_risk_limits` | confirmed |
| 组合敞口门禁 | 当日亏损熔断、策略数量、总敞口、聚类敞口四道开仓前检查 | `core/risk/portfolio_risk.py`：`PortfolioRiskManager.can_open_new_position`、`PortfolioRiskConfig` | confirmed |
| 日内熔断三态机 | `normal → breaker → cooldown`，熔断/冷却态禁止新开仓，跨交易日边界重置 | `core/risk/circuit.py`：`CircuitBreaker.update`、`allows_new_position`、`CircuitState` | confirmed |
| 紧急停止开关 | fail-closed 文件持久化开关；状态损坏/缺失按已触发处理；触发/复位写审计；复位需授权 | `core/control/kill_switch.py`：`KillSwitch.is_armed/trigger/reset/guard` | confirmed |
| 入场持仓守卫 | 下单前核对账户与策略持仓归属漂移、反向腿是否已平；越界拒绝并留痕 | `backend_api_python/app/services/pending_orders/entry_position_guard.py`：`evaluate_entry_position_guard`、`EntryPositionGuardResult` | confirmed |
| 交易所原生保护单 | 成交后在交易所侧挂 reduce-only 止损/止盈/追踪条件单（多交易所适配） | `backend_api_python/app/services/live_trading/native_protection.py`：`place_native_protection_orders`、`protection_prices_from_payload`、`NativeProtectionRequest` | confirmed |
| 确定性保护评估器 | 回测与实盘共用同一保护语义（止损/止盈/跟踪/时限），带 intrabar 模式 | `backend_api_python/app/services/strategy_v2/protection.py`：`ProtectionEngine.evaluate_bar/evaluate_price`、`ProtectionState`、`ProtectionSpec` | confirmed |

### 1.2 截断亏损的工程逻辑

1. **后端强制执行，人工不可覆盖（confirmed）**：`risk_engine.py` 止损触发后由 `_close_position_callback` 执行平仓，告警 `action_required="close_position"`；`native_protection.py` 把保护单挂到交易所侧 reduce-only，双保险。回调是否在真实交易链路被完整接线、失败重试与重试上限，本轮未在实盘复核 → **unknown**（实盘冒烟属未验证项）。
2. **止损单调（confirmed）**：`core/risk/stops.py::update_stop` 对多头拒绝 `new < cur`、对空头拒绝 `new > cur`，否则抛 `StopWideningError`；`risk_engine.py` 的追踪/保本/吊灯分支同样只在更优方向改写 `stop_loss_price`。止损放宽被硬拦截，不允许事后把止损挪远。
3. **回撤分级减仓（部分 confirmed / 部分目标态）**：
   - `core/risk/state.py::RiskState.drawdown_tier` 为回撤档位系数字段（注释：海龟分级降档），`risk_engine.py` 组合层 `check_portfolio_risk` 在回撤达 `max_drawdown_pct` 时走 `_close_all_positions` 全平；持仓数超限产生 `position_limit` 告警。
   - **现状缺口（目标态/待建）**：未见「回撤达到某一档位即按比例减仓、再达一档再减」的连续分级减仓执行链路；`drawdown_tier` 如何作用到手数、减仓动作由谁触发并落地成交，本轮未核到闭环。RULES.md 中「回撤 10% 减仓 50%、15% 清仓」是纪律口径，**当前代码未按该数值实现**，不得当作现状。
4. **账户限额与入场守卫（confirmed）**：`account_risk_snapshot` 按凭证/市场类型归集现存持仓与拟开仓位，估算 gross/net 名义、对冲比、总杠杆、保证金、往返费用、区间资金费率与单品种名义，超限返回对应 `accountRisk.*` 违规码；`entry_position_guard.py` 在下单前拒绝持仓漂移与未平反向腿。限额数值来自传入 `limits` 或策略 `trading_config.account_risk`，**阈值最终须由分布校准，不在代码内拍死**。
5. **熔断与急停（confirmed）**：`CircuitBreaker` 按已收盘 bar 推进，breaker/cooldown 态 `allows_new_position=False`；`KillSwitch` fail-closed，多来源（人工/对账/回撤/数据过期）可触发同一开关，触发与复位均落审计。

### 1.3 目标态 / 待建（不得写成现状）

- **ML 驱动的风险分层与仓位缩放**：风险状态/档位由模型判别属目标态；当前为规则与配置驱动。
- **OMS/EMS 与拆单执行**：组单、风控前置闸门、TWAP/VWAP 拆单、执行回报归集属目标态；当前执行层偏直连下单（见 TODO P2 与系统简介页局限口径）。
- **强制风控网关全链路复用**：统一在订单发出前过账户限额 + 组合门禁 + 熔断 + 急停 + 入场守卫的闸门闭环，部分模块已存在但跨入口串联复用未闭合（关联阻塞项 #107，触碰实盘链路，待拍板）。
- **回撤分级减仓闭环**：档位系数到手数/减仓动作的执行链路待补。
- **实盘强制执行闭环验证**：保护单挂单成功率、回调失败重试、交易所原生条件单与本地风控的一致性，均未在真实账户复核 → **未验证**。

### 1.4 纪律约束

- 阈值/限额由 CLEAN 分布与 config 派生，禁止按绩效网格搜索（不变量 3、硬规则 8）。
- 异常必须带上下文记录，禁止 `except Exception: pass`（硬规则 9）；`StopWideningError`、`LiveTradingError` 等均带 layer/上下文。
- 止损、开仓决策只在已收盘 bar / 已收盘数据上调用（intra-bar 纪律，硬规则 5）。

---

## 📈 跟踪止盈 / 让利润奔跑设计说明（2026-11-08 新增）

> 第一性原理：左尾截断之后，右尾要暴露给趋势——保本先消除「盈利变亏损」，分批落袋一部分，剩余仓位用跟踪/吊灯/回吐保护继续奔跑。
> 口径同上：**confirmed** 代码已核实；**inferred** 相邻推断；**unknown** 现状不明。R 倍数口径以入场冻结值为准；本篇不写绩效数字。

### 2.1 R 口径：冻结 atr0 / entryDist（confirmed）

| 项 | 落点 | 口径 |
|---|---|---|
| 冻结字段 | `core/risk/state.py::RiskState.atr0`、`entry_dist`；持仓期不重算；`frozen_r_denominator()` 强制返回冻结 `entry_dist` | confirmed |
| R 倍数计算 | `core/risk/stops.py::compute_current_r`：`R = (current_price - entry_price) × direction / entry_dist` | confirmed |
| 初始止损派生 | `core/risk/stops.py::initial_stop`：多头 `entry - entry_dist`，空头 `entry + entry_dist`；`entry_dist <= 0` 拒绝 | confirmed |
| 服务层冻结镜像 | `backend_api_python/app/services/risk_engine.py::Position.atr_at_entry`、`entry_dist`；`r_multiple = unrealized_pnl / (entry_dist × quantity)` | confirmed |
| 回放对齐 | `core/audit/replay.py`：`feature_snapshot.stop_dist_price` 作为冻结 `atr0` 形参重算手数；`core/audit/record.py::Decision.r_multiple_at_close` 出场后回填，用入场冻结 `entry_dist` | confirmed |

> 纪律：持仓途中 ATR 变化不允许刷新止损距离或 R 分母；任何「按当前 ATR 重算止损」的写法违反硬规则 4。

### 2.2 各类止盈/跟踪机制：现状与目标态

| 机制 | 研究/风控层落点 | 服务层落点 | 现状口径 |
|---|---|---|---|
| 保本止损 | `core/risk/stops.py::update_breakeven_stop`：R ≥ `breakeven_r` 后移到 `entry + direction × breakeven_offset_r × entry_dist` | `risk_engine.py::_update_breakeven_stop`：R ≥ `breakeven_activation_r` 移到入场价 + `breakeven_buffer` | confirmed（研究层 + 服务层均有实现）；具体 R/缓冲阈值须分布校准 |
| 分批止盈 | —（研究层未见分批落袋模块） | `risk_engine.py::_check_scale_out`：按 `scale_out_levels`/`scale_out_ratios` 分批减仓，`remaining_ratio` 递减，调 `_reduce_position_callback` | confirmed（服务层）；研究/回测侧分批语义在 `strategy_v2/protection.py` 未提供分批，属口径待对齐 |
| 跟踪止损 | `core/risk/stops.py::update_trailing_stop`：R ≥ `trailing_activation_r` 后在最大有利位置后退 `trailing_offset_r × entry_dist` | `risk_engine.py::_update_trailing_stop`：R ≥ `trailing_activation_r` 激活，距峰值 `trailing_atr_mult × atr_at_entry` | confirmed；`strategy_v2/protection.py::_trailing_trigger` 按价格峰值 + 激活百分比实现跟踪 |
| 吊灯止损 | —（研究层未见吊灯模块） | `risk_engine.py::_update_chandelier_exit`：激活跟踪后，峰值回撤 `chandelier_atr_mult × atr_at_entry` | confirmed（服务层）；研究层对等实现属目标态 |
| 利润回吐保护 | — | `risk_engine.py::_check_profit_retracement`：盈利 >1R 后，自峰值利润回撤达 `profit_retracement_pct` 平剩余仓位 | confirmed（服务层）；研究层对等实现属目标态 |
| 时限出场 | `core/risk/stops.py::check_time_stop`：超 `max_holding_bars` 且未达保本 R | `strategy_v2/protection.py`：`time_limit_seconds` 触发 `time_limit` 决策 | confirmed |
| 信号止损 | `core/risk/stops.py::check_signal_stop`：入场逻辑反转即离场 | — | confirmed（研究层）；服务层是否接线信号反转输入 unknown |
| 交易所原生跟踪/止盈 | — | `native_protection.py`：trailing callbackRatio / activatePrice、SL/TP 条件单；Gate/HTX 跟踪单标注 `managed_by: strategy_runtime` | confirmed 接线框架；不同交易所原生跟踪能力差异未逐一实盘核验 |

### 2.3 让利润奔跑的阶段划分（服务层，confirmed）

`risk_engine.py::_get_let_profit_run_stage` 按 R 与分批进度输出阶段：`in_loss → in_profit → breakeven → trailing → scaling_out → max_profit → stopped`，供摘要与审计读取。研究层 `StopState.max_favorable_r` 记录最大有利 R，供跟踪/保本触发判断。

### 2.4 口径缺口与目标态（不得写成现状）

- **研究-服务层止盈语义对齐**：吊灯、分批、回吐目前主要在 `risk_engine.py` 服务层；`core/risk/stops.py` 研究层对等模块不全，回测与实盘的右尾口径尚需逐机制对齐（关联研究-生产一致性规约）。
- **阈值分布校准**：`trailing_activation_r`、`breakeven_r`、`scale_out_levels`、`chandelier_atr_mult`、`profit_retracement_pct` 等当前为 dataclass 默认值/配置项；上线前须在 CLEAN 集做分布校准，禁止按回测绩效挑参数。
- **跟踪参数的 ATR 基**：服务层跟踪/吊灯距离用冻结 `atr_at_entry`；与研究层 `entry_dist`（R 倍数）两种基口径需在同一套决策规则版本下明确换算关系。
- **原生跟踪一致性**：交易所侧跟踪单与本地跟踪/吊灯并行时以谁为准、如何对账，属目标态；当前未核验实盘一致性。
- **未验证**：各机制在真实行情下的触发顺序、跳空穿透处理、部分成交后剩余仓位保护，未在真实账户复核。

---

## 🔗 研究-生产一致性规约（2026-11-08 新增）

> 第一性原理：回测结论只有在特征、数据切分、口径、成本、审计字段上与在线链路同源时才可外推；任何一边偷用未来数据、混用集合、漏算成本，都会让回测与实盘背离。
> 口径：**confirmed** 代码已核实；**inferred** 相邻推断；**unknown** 现状不明。

### 3.1 特征同源：研究/在线同一特征定义（confirmed）

- 特征函数契约：`core/features/base.py` 的 `@as_of` 装饰器强制 `feat_x(history, as_of, **kw)`；`as_of` 须 tz-aware UTC，history 内任一 `bar.ts_utc > as_of` 抛 `LookAheadError`，非单调抛 `AsOfContractError`。
- 因果可重算：同一 `(history, as_of)` 调用结果一致；history 尾部追加未来 bar 后，as_of 处值不变（黄金因果守卫 c01/c02，见 `tests/test_features_causal.py`）。
- 面板构建：`build_feature_panel` 逐根已收盘 bar 切片 `history[:i+1]` 计算，前 `warmup_bars` 行保留 NaN（不猜未来）；产出附 `available_at` 列。
- **目标态/待建**：在线推理链路是否直接复用 `core/features` 同一函数定义、还是另写一套在线特征，本轮未核到统一注册/比对机制 → **unknown**；研究与在线特征一致性回归（同输入双跑比对）属待建。

### 3.2 集合分离（confirmed）

| 集合 | 用途 | 落点 |
|---|---|---|
| CLEAN | 估计 ATR/波动率/Hurst 等统计量与分布阈值 | `core/data/splits.py::split_dataset` 划分 CLEAN 桶；`core/risk/sizing.py::quantile_threshold` 从样本分位派生门限 |
| KNOWN | 构建供需区等结构 | `split_dataset` 划分 KNOWN 桶 |
| HELD_OUT（静默集） | 不参与任何优化/选择/训练；代码路径上显式拒绝 | `split_dataset` 对静默窗口 bar 丢弃，返回 `HELD_OUT: []`；`SplitConfig.from_file` 拦截指向静默数据文件的键（`_FORBIDDEN_DATA_KEYS`），抛 `SilentSetAccessError` |

- 审计留痕：`core/audit/record.py::Decision.threshold_dataset` 取值仅限 `CLEAN|KNOWN`，构造时校验；每条决策可追溯阈值来源集。
- 纪律：统计量估计集与策略构建集不得混用；测试/静默集禁止参与参数选择（硬规则 2、RULES 3.2）。

### 3.3 回测/实盘口径对齐

| 口径项 | 现状落点 | 口径 |
|---|---|---|
| 信号只用已收盘数据 | `@as_of` 守卫 + `build_feature_panel` 逐收盘 bar；`CircuitBreaker.update` 每根已收盘 bar 推进；`strategy_v2/protection.py::evaluate_bar` 按 OHLC 判定，`evaluate_price` 按价格判定 | confirmed |
| 前视自动检测 | `core/audit/lookahead_detector.py::LookaheadDetector`：时间戳单调性、特征/标签泄露、滚动窗口边界检查 | confirmed（检测器存在）；是否在每条策略上线流程强制跑过 unknown |
| 成本含滑点 + 点差 + 佣金 | `core/backtest/costs.py`：`CostModel`（平静/新闻/跳空三档点差）、`spread_at`、`slippage_points`、平方根/成交量冲击/波动率调整滑点；`tiers_valid` 保证新闻/跳空点差不低于平静期 | confirmed（回测成本模型）；实盘成交成本如何回填对齐同一口径 unknown |
| 零成本退化 | `costs.py` 中 `cost_model=None` 返回 0 成本，仅对照实验，默认不用于正式回测 | confirmed |
| intra-bar 成交假设 | `strategy_v2/protection.py`：`VALID_INTRABAR_MODES = conservative/balanced/aggressive`，同一根 bar 多候选按模式选优先级 | confirmed；回测成交撮合假设与实盘滑点/跳空穿透的一致性未复核 |
| 时区一致 | 熔断以 UTC 日期为交易日键，注释要求实盘经纪商日边界配置覆盖（硬规则 6） | confirmed（研究层）；MT5/实盘服务器偏移与 Python `--tz` 一致性须在接入时核对 |

### 3.4 审计回放字段要求（confirmed）

- 每条信号无论接受/拒绝都落一条 `Decision`（`core/audit/record.py::write_decision`，JSONL 单行追加）；拒绝单 `final_signed_lots==0`，接受单 `lots>0`，构造即校验。
- 必备字段：`decision_id`、`signal`、`feature_snapshot`、`model_version`、`risk_state`、`accepted`、`reject_reason`、`final_signed_lots`、`threshold_dataset`、`decision_rule_version`、`r_multiple_at_close`（出场后回填）。
- 回放五要素：`core/audit/replay.py::replay_decision` 须能还原 `feature_snapshot / model_version / threshold_dataset / final_signed_lots / reject_reason`；`feature_snapshot` 缺 sizing 输入键（`equity/risk_pct/stop_dist_price/point_value/min_lot/lot_step/kelly_cap/vol_scale`）抛 `ReplayMismatch`；接受单手数重算与快照超容差即不一致。
- 决策规则版本：`decision_rule_version` 在实验前冻结；规则变更须新版本，禁止事后改旧快照口径（硬规则 11）。

### 3.5 一致性缺口与目标态（不得写成现状）

- **在线特征复用与双跑比对**：研究特征定义与在线推理特征的统一注册、同输入一致性测试待建。
- **实盘成本回填对齐**：成交滑点/点差/佣金/资金费的实盘归集与回测 `CostModel` 口径对齐待建。
- **前视检测强制门禁**：检测器已存在，纳入上线前必跑流程属目标态。
- **研究-服务止盈/止损语义对齐**：见《跟踪止盈 / 让利润奔跑设计说明》2.4，两引擎对等机制需补齐并挂同一规则版本。
- **未验证**：回测撮合与实盘成交在跳空、流动性、部分成交场景下的差异；审计回放对真实成交记录的闭环还原，未在实盘复核。

---

**三篇规约已纳入 WIKI（2026-11-08）；单一事实源在 docs/WIKI.md，前端只读镜像由后续环节收口，本轮未改前端文件。**
