# 胜法手册（SUCCESS_PLAYBOOK）

> 最后更新：2026-10-29 ｜ 证据：见每条末
> 维护纪律：与 `docs/ANTI_FRAGILE.md`（必死清单）互为正反面——那本记"怎么死"，这本只记"做对了、且证据在手"的事。**没收证据的事一律不写**；证据不足的标【待验证】，不许装 ✅。

---

## 1. 本文件定位

这是 QuantDinger 的"已验证胜法"沉淀册。收录标准只有一条：**这个做法在本仓库里留下了可复核的证据**（pytest 输出、真实文档记录、真实文件存在）。没有证据的经验、道听途说的最佳实践、理论推演，一律降级到第 7 节"待验证假设"，不许混进第 2 节"已验证清单"。

读法：遇到问题先翻第 5 节知识地图路由 → 按路由找到原始证据文件 → 再回来看对应做法在第 2/3 节的描述。本手册不复制正文，只做索引与判定。

---

## 2. 已验证有效的模块清单

> 验证时间：2026-10-29 本轮真实执行。pytest 输出为本次实跑结果，非照抄历史 hint。

| 模块 | 验证证据（测试文件 / 报告路径） | 实际跑通结果（2026-10-29 实测） | 证据等级 |
|---|---|---|---|
| 策略注册与权重路由引擎 `core/registry/strategy_router.py` | `tests/test_strategy_registry.py`（19 个单测：权重和=1、方向、白名单、异常路径） | `.venv\Scripts\python.exe -m pytest tests/test_strategy_registry.py -q` → **19 passed in 0.03s**（退出码 0） | 【已验证·单测层】 |
| 测试收集基线 | `tests/` 全目录 | `pytest tests/ -q --collect-only` → **376 tests collected, 1 error in 9.13s**；1 个收集错误为 basename 冲突（`tests/test_strategy_registry.py` 与 `tests/test_registry/test_strategy_registry.py` 同名），与被测模块无关 | 【已验证·含已知瑕疵】 |
| P2 面板 6 张实时数据卡片（高可用 / 交易日志归因 / 安全合规 / 拥挤度 / 可观测性 / CI-CD） | `docs/p2-panel-completion-20261028.md`；改动文件 `frontend-pro/index.html`、`frontend-pro/js/app.js`（`P2_LAMP`/`loadP2ModuleCards`/15s 轮询） | 后端 6 条路由全部存在（`/api/p1/health`、`/api/p1/journal/analyze`、`/api/p1/security/summary`、`/api/p2/crowding/summary`、`/api/p2/observability/summary`、`/api/p2/cicd/status`）；**但该文档第 5 节自认：通过 `:8888` 代理请求 6 端点本机全部 5s 超时，卡片真实数据渲染未在实环境验证** | 【代码已实现，实环境渲染未验证】 |
| 策略注册登记（3 个演示策略：demo_breakout / ml_trend_meta / demo_mean_reversion 占位） | `docs/strategy-registration-20261028.md` | 文档实测结果与本轮 pytest 一致（19 passed）；诚实标注：第 3 个 mean_reversion **没有可交易类实现**，仅按路由画像占位 | 【已验证·注册层；mean_reversion 实现本身待补】 |
| 五层市场识别（L1 状态 / L2 结构 / L3 趋势 / L4 价格行为 / L5 K线形态）规则版 | `docs/WIKI.md`「第二层→五层市场识别架构」表，L1–L5 规则版均标 ✅ | 本轮未逐文件重跑对应测试；等级按 WIKI 文档声明登记 | 【文档声明·本轮未独立复验】 |
| 前端真实 K 线函数 `fetchRealKline` | `docs/TODO.md` 第 13、30 行「代码已写」；实现于 `frontend-pro/js/app.js` | TODO.md P0-4 自认：实环境验证被 P0-1（nginx 502）阻塞，尚未看到真实 K 线渲染 | 【待验证·实环境】 |
| OKX 连接测试拿到账户余额 | `docs/TODO.md` 第 25、95 行：「连接测试API → 成功，账户余额 $98,340.28」「验证：返回余额 $98,340.28」 | 本轮未重连 OKX 复验（实盘凭证不在本脚本可执行范围）；为一次有文档时间戳的成功记录 | 【有文档证据的单次成功记录·非本轮复验】 |

> 已知瑕疵登记（不掩盖）：全量收集存在 1 个 import basename 冲突（`test_strategy_registry.py` 两处同名）。单跑该文件不受影响，但全量 `pytest` 会中断收集——修法：给其中一个目录的测试文件改名或加 `__init__.py`，属人工确认项，本轮未动。

---

## 3. 可复制成功模式（怎么做 / 为什么有效 / 下次怎么复用）

### 3.1 决策规则冻结：实验前定死，实验后只评估不修改
- **怎么做**：`RULES.md` 第 1.1 节——阈值在实验前冻结，`trials_N` 由 `run_gate_experiment.sh` 原子递增（含失败试验），禁止手工改 `registry.yaml`（`AGENTS.md` 硬规则 11）。
- **为什么有效**：把"试了多少次"变成公开账本，从流程上消灭"挑最好的一次汇报"。
- **下次复用**：任何新变体上线前，先写死 `decision_rule`，再跑实验；跑完无论结果如何，`decision_rule` 一个字都不改。
- 证据：`docs/RULES.md` §1.1；`AGENTS.md` 硬规则 11；防御对照 `ANTI_FRAGILE.md` 死法 5/6/18。

### 3.2 集合分离：CLEAN / KNOWN / 静默集三权分立
- **怎么做**：ATR/波动率/Hurst 只在 CLEAN 集估计；供需区只用 KNOWN 集构建；静默集代码里禁止读（`AGENTS.md` 目录边界）。
- **为什么有效**：研究者再怎么"手痒"也物理上碰不到静默集，泄漏被结构性杜绝，而不是靠自觉。
- **下次复用**：新增任何统计量时，先问一句"这个估计用的是 CLEAN 还是 KNOWN"；答不上来就不许写。
- 证据：`AGENTS.md` 硬规则 2、目录边界；`docs/ANTI_FRAGILE.md` 死法 2。

### 3.3 Docker 排障"先 logs 再动手"
- **怎么做**：容器崩了第一步是 `docker logs --tail 100 <容器>`，不是先重启、更不是先 `stop+rm`；恢复一律走 `docker compose up -d <service>`，不裸 `docker run`。
- **为什么有效**：RULES.md 踩坑清单（2026-10-27）证明：手动 `stop+rm` 生产容器 + 新容器没加入 `trader_quantdinger-network`，直接造成 502，恢复花了半小时。logs 里 30 秒就能看到"DNS 解析不到 backend"。
- **下次复用**：任何容器异常，按这个顺序固定动作——`docker ps` → `docker logs --tail 100` → `getent hosts <对端名>` → 才动手修。
- 证据：`docs/RULES.md`「2026-10-28 本轮新踩坑·Docker 容器崩溃排查清单」；`skills/quant-trading-expert/references/docker-okx-debug-2026-10.md`。

### 3.4 前端 3949 行单文件组件化拆分
- **怎么做**：不用固定行号切分，用正则匹配 `<style>...</style>` / `<script>...</script>` 标签拆成 `index.html + css/main.css + js/app.js`；每插一个模块立刻跑 `python diagnose_frontend.py`（div 平衡 + 页面 ID 匹配）；小步快跑，一次只加一个模块。
- **为什么有效**：固定行号拆分一改就错位（RULES.md 2026-10-25 踩坑）；div 开闭不平衡会整页空白且报错位置很远，诊断脚本把这个排查从半小时缩到秒级。
- **下次复用**：再拆任何大 HTML，先写诊断脚本再动手；回滚路径常备 `git checkout HEAD -- index.html`。
- 证据：`docs/frontend-systematic-optimization.md`；`docs/RULES.md`「前端组件化拆分调试经验」。

### 3.5 测试驱动：每个改动配单测，黄金集断言不放宽
- **怎么做**：`AGENTS.md` 硬规则 10——每次改动必须附带或更新单测；黄金集（`tests/test_risk_stops.py`、`tests/test_risk_sizing.py` 等）断言只许加、不许放宽。策略路由引擎落地时同步产出 19 个单测，本轮复跑 19 passed。
- **为什么有效**：本轮实测证明——策略路由 19 个测试 0.03 秒跑完，任何一次回归都会被当场抓住，而不是等实盘亏钱才发现。
- **下次复用**：写代码前先想"这个改动谁来挡住回归"，没有测试文件的改动不提交。
- 证据：本轮实跑 `19 passed in 0.03s`；`AGENTS.md` 硬规则 10。

### 3.6 诚实登记：没验通就标没验通，不假装 ✅
- **怎么做**：TODO.md 风格——P2 卡片写完立刻在第 5 节写"容器未验证"；mean_reversion 在注册文档里直接写"未实现可交易类"；P0 表格里 4 个未完成项全部标 🔄/🚫。
- **为什么有效**：假 ✅ 是未来爆仓的种子——以为已验证的东西没验证，比不知道它存在更危险。本手册第 2 节每个模块都带证据等级，就是这条纪律的产物。
- **下次复用**：写完成报告时，先列"没验证什么"，再列"验证了什么"。
- 证据：`docs/TODO.md` P0 表（P0-1~P0-4 状态诚实登记）；`docs/p2-panel-completion-20261028.md` 第 5 节。

---

## 4. 顶级机构可复制实践索引

> 正文不复制，需要时打开原文件。来源：`skills/quant-trading-expert/references/top-firm-practices.md`

1. [文艺复兴科技——持续进化的信号生产线](../skills/quant-trading-expert/references/top-firm-practices.md)
2. [Two Sigma——数据工程与版本化研究](../skills/quant-trading-expert/references/top-firm-practices.md)
3. [DE Shaw——多因子与风险中性组合](../skills/quant-trading-expert/references/top-firm-practices.md)
4. [Citadel Securities——做市级风控与技术栈](../skills/quant-trading-expert/references/top-firm-practices.md)
5. [Millennium Management——多 PM 分散与独立盈亏核算](../skills/quant-trading-expert/references/top-firm-practices.md)
6. [Jane Street——概率建模与系统可靠性文化](../skills/quant-trading-expert/references/top-firm-practices.md)
7. [Jump Trading——低延迟基础设施与研究闭环](../skills/quant-trading-expert/references/top-firm-practices.md)
8. [AQR——系统性因子与学术严谨](../skills/quant-trading-expert/references/top-firm-practices.md)
9. [行业共识总结：所有顶级机构都认同的 5 条](../skills/quant-trading-expert/references/top-firm-practices.md)
10. [常见误区：ML 越复杂越好 / 回测好看=有效 等 5 条](../skills/quant-trading-expert/references/top-firm-practices.md)

---

## 5. 知识地图（问题 → 文件路由表）

> 正式事故档案已建立：`docs/ERROR_LOG.md`（E001~E007，含 Docker 崩溃/环境变量/nginx 502/前端部署/OKX 下单/GitHub 推送/OKX 被墙）。下表中涉及事故类问题的条目已优先路由到 ERROR_LOG 对应编号，原参考文档作为旁证保留。

| # | 你遇到什么问题 | 第一步查哪个文件 | 关键词 Grep 什么 |
|---|---|---|---|
| 1 | 回测夏普虚高、曲线漂亮得不正常（疑似前视） | `docs/ANTI_FRAGILE.md` 死法 1 + `docs/RULES.md` §1.1/§3.1 | `shift(-`、`iloc[i+1]`、`future` |
| 2 | 静默集被偷看 / 验证集混入 | `docs/ANTI_FRAGILE.md` 死法 2 + `docs/data_splits.md` | `静默`、`CLEAN`、`KNOWN` |
| 3 | Docker 502 / 404 / nginx Host not found | `docs/ERROR_LOG.md` E001/E003 + `skills/.../docker-okx-debug-2026-10.md` | `getent hosts`、`proxy_pass`、`aliases` |
| 4 | 新容器起来了但服务间不通信 | `docs/RULES.md`「Docker 容器崩溃排查清单」 | `network connect`、`trader_quantdinger-network` |
| 5 | OKX 下单失败 "All operations failed" | `docs/ERROR_LOG.md` E005 + `backend_api_python/app/services/okx_client.py:124-170` | `tdMode`、`clOrdId`、`sz` |
| 6 | 时区错位 / 信号在错的 bar 触发 | `docs/ANTI_FRAGILE.md` 死法 3 + `core/data/timezone.py` | `--tz`、`timezone`、`EET` |
| 7 | 前端改了不生效 / 浏览器还是旧行为 | `docs/RULES.md` §4.2 +「前端组件化拆分调试经验」 | `docker cp`、`ignoreCache`、`node --check` |
| 8 | 本地网络访问 OKX 被拒（curl 退出码 7） | `docs/ERROR_LOG.md` E007 + `skills/.../docker-okx-debug-2026-10.md` §3 | `curl`、`退出码 7`、`HTTPS_PROXY` |
| 9 | 策略想上线 | `docs/WIKI.md` 五层架构 + `docs/RULES.md` §1.3/§5.1 + `docs/ANTI_FRAGILE.md` 死法 20 | `dryrun`、`影子模式`、`样本外` |
| 10 | 仓位怎么定 / 单笔风险多少 | `docs/RULES.md` §2.1 + `skills/.../position-sizing.md` + `core/risk/sizing.py` | `Kelly`、`波动率目标`、`2%` |
| 11 | 数据缺口 / 周末跳空被 ffill 填成假行情 | `core/gap_normalizer.py` + `docs/ANTI_FRAGILE.md` 死法 4 | `gap`、`ffill`、`缺口` |
| 12 | 样本外太短 / 把噪声当信号 | `docs/ANTI_FRAGILE.md` 死法 7 + `scripts/run_walkforward.py` | `walk-forward`、`OOS`、`t 统计` |
| 13 | 止损被插针扫掉 / 止损方向被错误移动 | `docs/ANTI_FRAGILE.md` 死法 10 + `core/risk/stops.py` | `PositionModify`、`atr0`、`entryDist` |
| 14 | OrderSend / 异步返回没检查、幽灵持仓 | `docs/ANTI_FRAGILE.md` 死法 11 + `AGENTS.md` 硬规则 7 | `OrderSend`、`retcode`、`ResultRetcode` |
| 15 | WebSocket 断连 / 行情时间戳不前进 | `docs/ANTI_FRAGILE.md` 死法 13 + `core/risk/circuit.py` | `stale`、`心跳`、`重连` |
| 16 | `except Exception: pass` 吞错 / 对账少单 | `docs/ANTI_FRAGILE.md` 死法 15 + `AGENTS.md` 硬规则 9 | `except.*pass`、`except:` |
| 17 | 连亏后手数越下越大（报复性交易） | `docs/ANTI_FRAGILE.md` 死法 17 + `core/risk/circuit.py` | `熔断`、`手数`、`连亏` |
| 18 | registry.yaml 被手改 / trials_N 对不上 | `docs/ANTI_FRAGILE.md` 死法 18 + `AGENTS.md` 硬规则 11 | `trials_N`、`registry.yaml` |
| 19 | 已鉴权接口返回 401（开发环境） | `docs/TODO.md` P0-3 | `401`、`token`、`bypass` |
| 20 | 环境变量名前后端对不上（密码认证失败） | `docs/ERROR_LOG.md` E002（实查：`D:\Trader\.env` 与 `backend_api_python\.env` 变量名不一致，`backend.env` 竟是目录） | `POSTGRES_PASSWORD`、`DATABASE_URL`、`backend.env` |

---

## 6. "系统越来越聪明"复利飞轮

六个组件构成闭环：**MEMORY（记忆）→ ERROR_LOG（事故）→ SUCCESS_PLAYBOOK（胜法）→ RULES（禁令）→ GOALS（方向）→ TESTS（固化）**。每踩一次坑，按四级下沉逐级升级，下一次同类问题在更早的层级被挡住——不再靠人记。

```
        GOALS（方向：这季度要解决什么）
              │ 驱动
              ▼
   踩坑/事故  ──►  MEMORY（这次发生了什么，现象+时间戳）
              │  判定：能否稳定复现？
              ▼
   ERROR_LOG（根因+修复+验证命令；已建立 → docs/ERROR_LOG.md，E001~E007）
              │  判定：同类问题还会不会再犯？
              ▼
   RULES（禁令/铁律：不许再这么干）──► SUCCESS_PLAYBOOK（这么干有效）
              │  判定：这条规则能否变成可执行断言？
              ▼
   TESTS（单测把规则焊死：再犯就红灯）
              │
              └────► 反馈给 GOALS：下季度补什么
```

**每一级下沉的判定标准（不达标不许升级）：**

| 层级 | 什么才算"够格升到下一级" |
|---|---|
| L0 MEMORY → L1 ERROR_LOG | 有明确根因（不是"重启好了"），有可复现路径，有验证命令证明修复生效 |
| L1 ERROR_LOG → L2 RULES/SUCCESS_PLAYBOOK | 该类事故发生 ≥ 2 次，或第一次就造成 > 半小时恢复 / 资金风险，值得写成通用禁令 |
| L2 RULES → L3 TESTS | 规则能用代码断言表达（如：出现 `shift(-1)` 就 lint 失败；trials_N 递减就测试失败）；表达不了的规则留在 CODE REVIEW 清单 |
| L3 TESTS → L4 退役出记忆 | 该测试连续守护 ≥ 3 个月未被触发，且代码未重写，才可从 MEMORY 归档 |

**飞轮的收益公式**：每升一级，同类问题的拦截成本按数量级下降——人记（最累）→ 文档查（次之）→ 测试自动挡（零成本）。目标状态：新人上手时，坑已经被测试焊死，他根本没机会踩。

---

## 7. 本季度还缺什么胜法（诚实清单：【待验证假设】）

> 以下现在都**不是**已验证胜法。列出"需要跑多久 / 什么条件"才能升级到第 2 节。

| # | 现在的状态 | 升级为【已验证】需要什么 | 预计周期 |
|---|---|---|---|
| 1 | P2 六卡片实环境渲染未验证（本机 6 端点 5s 超时） | 修好 nginx 502（P0-1）后重启前端容器，逐卡片截图确认状态灯点亮 | P0-1 修复后当天 |
| 2 | `fetchRealKline` 实环境 K 线渲染未验证 | 同上，K 线图真实出数且 30s 刷新正常 | P0-1 修复后当天 |
| 3 | OKX 真实下单 / 平仓 / 查持仓未通（"All operations failed"） | 用 10 USDT 最小手数在 DEMO 账户复现并成功一笔 | 待 P0-2 |
| 4 | `demo_mean_reversion` 策略类未实现，仅路由占位 | 补出可交易类并配单测 | 1 个迭代 |
| 5 | 路由权重表是定性配置，未经 CLEAN 分布校准 | 跑 `scripts/calibrate_regime.py --mode distribution`，输出分位驱动权重并对比 | 1 个迭代 |
| 6 | WebSocket 断连重连 / stale 检测未实战验证 | 影子模式跑 1 个月，统计自然断连时长分布（ANTI_FRAGILE H1） | 1 个月 |
| 7 | PBO / CPCV / Deflated Sharpe 算法未实现（WIKI 标 ⏳） | 算法落地 + 历史策略回算 PBO 分布（ANTI_FRAGILE H9） | 1 个迭代 |
| 8 | ~~正式 ERROR_LOG 文档未建立~~ ✅ 已建立 docs/ERROR_LOG.md（E001~E007），其中 E002/E005/E006/E003 修复仍标【待验证】 | 把待验证条目逐条在实环境复跑、翻牌成【已修复并验证】 | 2 周内 |
| 9 | 实盘冒烟 / 经纪商差异未验证（AGENTS.md 要求显式标注） | 小资金 ≥1% 仓位跑 1 个月，真实滑点回填回测引擎 | 1 个月+ |
| 10 | 五层市场识别 ML 增强版未做（规则版已完成） | ML 管线落地，识别准确率对比规则版 | 下季度 |

---

**文档版本**：v1.0（2026-10-29 初版）
**下次复审**：P0-1 / P0-2 修复完成时同步升级第 2 节证据等级
**维护纪律**：任何条目从【待验证】升为【已验证】，必须在该行末附上本次真实 pytest 输出或文档证据路径；不许凭感觉升级。
