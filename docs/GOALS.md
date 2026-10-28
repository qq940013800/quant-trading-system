# QuantDinger Pro 目标牵引体系（GOALS）

> 最后更新：2026-10-29 ｜ 状态：季度滚动复盘
> 方法论第一性追问：**一个成功的量化交易系统最终要达到什么状态？**
> 逆向推导四层：① 先活下来（不爆仓、不黑天鹅归零）→ ② 再稳赚（正期望值穿透样本外与实盘）→ ③ 然后可复制（策略工厂而非单个圣杯）→ 最后可进化（每次错误都让系统更聪明）。
> 任何一条目标若与这四层相悖，优先砍目标而不是砍风控。
> 铁律基线见 `../AGENTS.md`；死法清单见 `ANTI_FRAGILE.md`；经验沉淀见 `RULES.md`（本文不重复其内容）。

---

## 证据等级标注约定

- **【已验证】**：本仓库已跑通、有代码/测试/成交回执或 API 返回值佐证。
- **【行业共识】**：量化圈公开文献与头部机构（桥水 / 文艺复兴 / Two Sigma / D.E.Shaw / Millennium）通行标准。
- **【待验证假设】**：基于本项目架构的推断，尚未经实盘或样本外验证。

---

## 一、北极星目标（North Star）

**建成一个稳定盈利、可审计、可进化的 AI/ML 增强量化交易系统，连续实盘运行 ≥ 6 个月并满足以下量化阈值：**

| 指标 | 阈值 | 依据与标注 |
|------|------|-----------|
| 组合 Sharpe | > 1.5 | 【行业共识】专业管理资金的优秀线（Millennium pod 典型 1.0–2.0，文艺复兴级 > 2 属顶级）；【待验证假设】我们能在加密现货上达到该水平——当前策略池仅 3 个演示策略、因子仅 10 个，尚无实盘 track record |
| 最大回撤 | < 20% | 【行业共识】20% 是个人/小机构赎回线与风控止损线的常见分界；桥水风格风险预算即以此为硬约束。配套内部红线：回撤 10% 自动减仓 50%、15% 清仓（已写入 WIKI 踩坑经验） |
| 年化收益 | > 15% | 【行业共识】扣手续费后跑赢无风险利率 + 主要股指的基准线；【待验证假设】作为本项目目标值——无任何实盘数据支撑，若实盘 6 个月 Sharpe 达标但年化仅 8%，优先保 Sharpe 不动摇 |
| 实盘连续运行 | ≥ 6 个月 | 【行业共识】至少跨越一个完整市场 regime 切换期，交易样本量才有统计意义（大数定律）；短于 6 个月的盈利不可信，短于 6 个月的亏损也不急于否定系统 |

**为什么不追求更高 Sharpe**：【行业共识】WIKI 已对标——追求高 Sharpe 是过拟合的温床（Millennium 哲学：绝对收益优先于高 Sharpe）。本系统的目标函数是 **风险调整后稳定可复制的正期望**，不是曲线漂亮。

---

## 二、季度目标（2026 Q4 → 2027 Q1）

> 全部对齐 `TODO.md` 2026-10-28 重排的 P0/P1/P2 真实状态，不写超出当前阶段的空话。

### QG-1 OKX 实盘对接全链路打通（对应 P0-1/P0-2/P0-3/P0-5）

- **可衡量指标**：在容器环境（`quantdinger-backend` / `quantdinger-frontend`）下，下单 → 成交回执 → 持仓查询 → 平仓 → 余额对账五环全部闭环，且 `docker exec quantdinger-frontend getent hosts backend` 通过。
- **完成标准（DoD）**：
  1. nginx upstream 502 修复（network alias 或改 nginx 配置二选一，ADR 留档）；
  2. dev 模式 401 绕过（`settings.ENV == "dev"` 时 bypass，生产鉴权不碰）；
  3. 最小手数（10 USDT 等值）真实下单 1 笔 BTC 市价单并拿到 `okx_client.py` 返回的成交回执；
  4. 本地出口连 OKX 通过代理或海外部署解决（`curl www.okx.com` 退出码 0）。
- **失败预警线**：连续 2 周卡在 "All operations failed"，或下单回执与持仓查询对账不一致 ≥ 2 次 → 立即停止试单，回到 `okx_client.py` 对照 OKX 官方错误码与 tdMode 参数复盘，禁止盲目重试烧真实资金。

### QG-2 策略池 ≥ 10 个真实策略 + Matcher × Router 集成（对应 P1-3/P1-5）

- **可衡量指标**：`registry.yaml` 中注册的策略，`implementation_ref` 非空（即 `core/strategies/` 下有对应策略类且单测通过）的条数 ≥ 10。
- **完成标准（DoD）**：
  1. 补齐 `core/strategies/mean_reversion.py`（RSI(14) + 布林带(20, 2σ) 反向开仓）等缺失策略类；
  2. StrategyMatcher 输出 top-N 排名 → StrategyWeightRouter 对 top-N 输出归一化权重，其余策略权重归零；
  3. 每个新策略必须配套单测 + `tests/test_features_causal.py` 追加前视守卫断言（硬规则 10）。
- **失败预警线**：新策略在 CLEAN 集上 IC 检验全部 < 0.02，或任一策略 PBO > 0.5 → 停止扩池，先回去做 QG-3 过拟合防御，否则池子越大死得越快。

### QG-3 PBO / CPCV / Deflated Sharpe 过拟合防御体系落地（对应 P2-4）

- **可衡量指标**：`scripts/` 下存在可运行的 `pbo.py` / `cpcv.py` / `deflated_sharpe.py`，且现有全部策略在 `experiments/` 目录下有对应三指标报告。
- **完成标准（DoD）**：
  1. 按 López de Prado 教材实现三算法，不允许"框架已建、算法空壳"；
  2. 任何策略上线实盘前必须三指标全过：PBO < 0.5、Deflated Sharpe > 0、CPCV 多折方向一致率 ≥ 60%；
  3. 结果随 `run_gate_experiment.sh` 原子登记进 `registry.yaml` 的 `trials_N`（含失败试验，硬规则 11）。
- **失败预警线**：三指标判定结果与 walk-forward 实际结果矛盾率 > 30% → 实现有 bug，立即冻结所有"已通过"结论，回查切分种子与数据泄漏。

### QG-4 五层市场识别接入真实 K 线（对应 P1-2）

- **可衡量指标**：L1–L5 检测器的输入源从演示数据切换为 OKX 真实 K 线，最先在 BTCUSD M15 单品种跑通。
- **完成标准（DoD）**：
  1. `scripts/import_kline.py` 把真实 K 线灌入 PostgreSQL；
  2. 跑 `core/gap_normalizer.py` 产出 `experiments/gate_BTCUSD.yaml`（人工审核后才进 `configs/`）；
  3. `regime.py` / `structure.py` / `price_action.py` 消费真实数据输出标签，前端 `fetchRealKline`（已写）在容器环境真实渲染；
  4. `tests/test_features_causal.py` 全绿。
- **失败预警线**：真实数据下 L1 标签分布与演示数据漂移 > 30%，或出现连续 20 根一字线 → 先停下来查数据缺口与清洗，禁止把假行情当真信号。

### QG-5 前后端部署流水线固化（对应 P0-1 衍生 / 踩坑 #5#6）

- **可衡量指标**：一次 `docker-compose up` 起全栈，`/openapi.json` 能验证 `/api/okx/*` 全部路由注册；改代码走 rebuild 而非 `docker cp`。
- **完成标准（DoD）**：
  1. Dockerfile 显式 `COPY app/` 进镜像（不再依赖官方镜像自带路由）；
  2. compose 网络 alias 一致，前端 nginx upstream 指向可解析的后端服务名；
  3. 新人按 `docs/deployment/` 文档一条命令起服务成功。
- **失败预警线**：同一份代码两次 rebuild 产物不一致 → 镜像层缓存污染，停下来查 Dockerfile，禁止带疑上线。

---

## 三、月度里程碑（可勾选）

### 2026-11：先清 P0，打通实盘第一环

- [ ] 修复 nginx upstream 502：docker network 加 alias `backend`（或 nginx 改指 `quantdinger-backend:5000`），`docker exec quantdinger-frontend getent hosts backend` 返回 IP
- [ ] dev 模式 401 绕过：`settings.ENV == "dev"` 时 bypass token 校验，生产路径不动
- [ ] **真实下单 1 笔 BTC 最小手数（10 USDT 等值），拿到 okx_client.py 返回的成交回执，并通过持仓查询接口查到该笔持仓**
- [ ] 用最小手数平掉该笔仓位，平仓前后余额对账一致（差 = 手续费 + 滑点，可解释）
- [ ] 本地出口打通 OKX：配置 HTTPS_PROXY 或后端容器部署到可直连区域，`curl https://www.okx.com` 退出码 0

### 2026-12：真实数据 + 策略补全

- [ ] 写 `scripts/import_kline.py`，把 BTCUSD M15 历史 K 线灌入 PostgreSQL
- [ ] 跑 `python core/gap_normalizer.py --sym BTCUSD --data <kline.csv> --out experiments/gate_BTCUSD.yaml`，人工审核产物
- [ ] 五层识别 L1 接入真实 K 线输出 regime 标签，前端 K 线图在容器环境（:8888）强刷后真实渲染点亮
- [ ] 新建 `core/strategies/mean_reversion.py`（RSI14 + 布林 20,2σ），配套单测 + 前视守卫测试
- [ ] StrategyMatcher × StrategyWeightRouter 集成：top-N 输出 + 归一化权重，其余归零；跑 `python scripts/calibrate_regime.py --mode distribution`，用输出分位替换 `strategy_router.py` 硬编码权重（ADR 留档）

### 2027-01：过拟合防御 + 扩池 + 固化

- [ ] 实现 `scripts/pbo.py` / `scripts/cpcv.py` / `scripts/deflated_sharpe.py`，对现有策略全部跑一遍，报告落 `experiments/`
- [ ] `registry.yaml` 策略池达到 ≥ 10 个，`implementation_ref` 全部非空
- [ ] 后端策略自动退役逻辑：`core/registry/strategy_registry.py` 加 `retire_if_health_below(threshold)`，阈值由 CLEAN 分布校准（禁止按 PnL 网格搜索），触发时自动停策略 + 通知 + 记录原因
- [ ] 验证一次 fresh `docker-compose up` 全栈启动：`/openapi.json` 含 `/api/okx/*` 全部路由，`/health` 200
- [ ] Gitee → Notion 单向 webhook 打通（多端知识库同步 P2-6 第一步）

---

## 四、目标反脆弱机制

> 原则：**目标不是用来追的，是用来暴露方向错误的。** 达不成不可耻，方向错了不自知才可耻。

### 4.1 未达成 → 降级 / 止损 / 复盘

| 触发条件 | 动作 |
|----------|------|
| 月度里程碑勾选率 < 50%，**连续 2 个月** | 冻结新策略开发 2 周，召开复盘会：是目标定高了、路径错了、还是资源不够？复盘结论写入 `docs/decisions/ADR-*.md` 后才允许继续 |
| 任一单项的"失败预警线"连续 2 次触发 | 该模块立即冻结为修复模式，禁止带疑前进（例：QG-1 对账不一致 → 停止一切真实下单） |
| 实盘组合回撤达 10% | 自动减仓 50%（WIKI 已约定），暂停新信号入场 |
| 实盘组合回撤达 15% | 全部清仓，系统切回 paper trading，重查归因 |
| 发现疑似前视函数 / 静默集泄漏 | 按 `AGENTS.md` 停止条件立即停下来问人，禁止自行绕过 |

### 4.2 超额达成 → 奖励（但带刹车）

| 触发条件 | 奖励 |
|----------|------|
| 月度里程碑勾选率 ≥ 90% | 该季度新策略的实盘资金分配上限上浮 20% |
| 季度 5 个 QG 全部 DoD 达标 | 北极星目标进入 6 个月实盘观察期（paper → demo → 小资金逐级放量） |
| 连续两个季度超额 | 允许启动 QG-3 之上的新研究线（ML 增强版五层识别 P2-3） |

**刹车条款**：任何资金上浮都必须同时满足 PBO < 0.5、Deflated Sharpe > 0、实盘回撤未触 10% 红线。奖励不改变风控参数——风控参数只由 CLEAN 分布驱动，不因业绩好而上调。

---

## 五、系统如何越来越聪明（闭环图）

```
   ┌──────────────────────────────────────────────────────────────────────┐
   │                                                                      │
   ▼                                                                      │
[目标] GOALS.md ──▶ [假设] docs/decisions/ADR-*.md + registry.yaml      │
   （本文件）        （decision_rule 实验前冻结）                          │
                        │                                                │
                        ▼                                                │
                 [实验] run_gate_experiment.sh                           │
                 trials_N 原子递增（含失败试验）                          │
                        │                                                │
                        ▼                                                │
                 [验证] pytest -q + PBO/CPCV/Deflated Sharpe             │
                 + tests/test_features_causal.py 前视守卫                  │
                        │                                                │
              ┌─────────┴─────────┐                                      │
              ▼                   ▼                                      │
        通过（信号有效）      失败（信号是噪声）                            │
              │                   │                                      │
              ▼                   ▼                                      │
        [沉淀]              [沉淀]                                        │
        MEMORY.md           ERROR_LOG.md                                 │
        （有效模式）          （错误根因 + 修复 + 预防）                     │
              │                   │                                      │
              └─────────┬─────────┘                                      │
                        ▼                                                │
                 [检索] 下次动手前先 grep                                 │
                 RULES.md / skills/.../references/ / ERROR_LOG.md       │
                        │                                                │
                        ▼                                                │
                 下次决策更准 ───────────────────────────────────────────┘
```

- 本闭环的知识沉淀落点：有效经验见 [`MEMORY.md`](./MEMORY.md)，错误与根因见 [`ERROR_LOG.md`](./ERROR_LOG.md)（两份文档与本批任务并行建立）。
- 闭环的回灌口纪律：**新策略上线前、新阈值落 configs 前、新模块接真实数据前，必须先在上述沉淀文件里检索同类问题**，命中就引用，没命中才动手——动手之后必须回写。
- 闭环失效的信号（反模式）：目标完不成没人复盘、实验失败不登记 trials、错误修完不写 ERROR_LOG、下次还踩同一个坑——出现任一现象，本文件的下一次滚动复盘必须把"闭环运转率"作为第一条指标检查。

---

**维护人**：QuantDinger ｜ **复盘频率**：每月末勾选月度里程碑，每季度末重排 QG 与北极星阈值 ｜ **变更纪律**：只允许追加复盘结论，不允许追溯修改已冻结的 decision_rule。
