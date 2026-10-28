# MEMORY — 项目级长期记忆（学习飞轮的记忆层）

> 最后更新：2026-10-29 ｜ 维护人：每次踩坑者本人

## 1. 定位

MEMORY.md 是本项目的**项目级长期记忆**：跨任务、跨月份的"一句话经验索引"。它不存事故全过程，也不存禁令条文，只存"下次排障时 Grep 标签能秒命中"的提炼条目。目标只有一个——**同样的坑永远不花第二次时间**，让系统随踩坑次数复利变聪明。

### 与相邻文档的分工边界（什么内容记到哪个文件）

| 内容类型 | 记到哪里 | 为什么不记在 MEMORY |
|---|---|---|
| 禁令 / 硬规则（违反即打回，改了要人审） | `../AGENTS.md` 11 条硬规则 + `RULES.md` | 规则是"法"，需人审、不可随手加；MEMORY 只链接引用 |
| 事故档案（完整时间线、影响、复现步骤、截图） | `ERROR_LOG.md`（规划中，对应 `knowledge-management-architecture.md` 的"故障知识库"） | MEMORY 只存提炼后的一行，不存全过程 |
| 必死清单（怎么死、20 条死法） | `ANTI_FRAGILE.md` | 死法已成体系归档，MEMORY 只挂链接 |
| 胜法（被反复验证有效的标准流程） | `SUCCESS_PLAYBOOK.md`（规划中） | 经验须 ≥2 次验证才升级过去，不直接写 MEMORY |
| 按日期的踩坑流水账表格 | `RULES.md` 第六节 | 原始时间线记录，不做提炼 |
| **可复用的一句话经验 + 标签 + 复用条件 + 证据等级** | **本文件** | 排障时 Grep 标签秒查，这是唯一职责 |

判断口诀：**要执行时读 AGENTS.md/RULES.md；要避坑时读 ANTI_FRAGILE.md；要排障时先 Grep 本文件标签。**

---

## 2. 记录格式（强制模板）

每条记忆 = 场景标签 | 问题 | 解决方案 | 复用条件 | 关联文件 | 证据等级。

**证据等级三档（必须诚实标注）：**
- 【已验证】——本项目实际踩过、复现、修复并确认有效
- 【行业共识】——量化圈公开文献 / 头部机构普遍承认，本项目尚未实盘验证
- 【待验证】——推测或二手信息，小资金阶段需证伪

### 填好的示例

```
[docker][nginx][502][dns]
- 问题：前端 :8888 所有 /api/* 返 502，但直连 :5000/api/health 是 200
- 解决方案：nginx proxy_pass 里写的 upstream 主机名，必须在 docker network 里有 DNS 别名；
  改完先用 docker exec <前端容器> getent hosts <upstream名> 验证解析，再 nginx -s reload
- 复用条件：任何"容器间 502 / Host not found"，尤其 nginx 用 set 变量 + proxy_pass 的写法
- 关联文件：RULES.md「nginx upstream / 502 排查清单」；frontend-bug-list-20261028.md P0-1
- 证据等级：【已验证】（2026-10-28 用 getent hosts 复现并定位根因）
```

---

## 3. 记忆分类索引

> 每条一行，只做索引；正文一律用相对路径链接指向源文档。

### A. Docker / 部署运维

- [docker][compose][恢复] 禁止手动 `docker stop`+`rm` 生产容器；恢复一律 `docker compose up -d <svc>`；删容器前先 `docker inspect` 全量留档 env / 网络别名 / 挂载卷。【已验证】→ 详见 `../skills/quant-trading-expert/references/docker-okx-debug-2026-10.md` §2、`RULES.md` §4.1
- [docker][镜像][路由缺失] "容器起来了"≠"我们的代码在里面"：官方镜像不含自写 `account.py`/`okx_client.py`；Dockerfile 必须 `COPY app/` 整体构建；build 后必跑 `curl /openapi.json | Select-String "okx"` 确认路由注册。【已验证】→ `docker-okx-debug-2026-10.md` §4
- [docker][nginx][502][dns] upstream 主机名必须在 compose 里配 network alias（或改 nginx 用 `quantdinger-backend`），`resolver 127.0.0.11` 救不了"主机名本身不存在"。【已验证】→ `RULES.md` 2026-10-28 段 nginx 清单、`frontend-bug-list-20261028.md` P0-1
- [docker][env][密码] 环境变量名禁止猜（`POSTGRES_PASSWORD` vs `DATABASE_URL` 是经典坑）：先 `Select-String "os.getenv"` 列出后端真实读取名，再对齐 `.env`。【已验证】→ `RULES.md` §4.1 与 2026-10-28 环境变量清单
- [docker][network][手动run] 裸 `docker run` 起的容器不自动加入 `trader_quantdinger-network`，必须 `docker network connect`；一律走 compose 让网络自动编排。【已验证】→ `docker-okx-debug-2026-10.md` §1-2
- [docker][cp][零散文件] 不要 `docker cp` 零散文件进容器补路由——重启即丢、易漏依赖；要么 volume 挂载，要么完整 rebuild 镜像。【已验证】→ `docker-okx-debug-2026-10.md` §5、`RULES.md` §4.1

### B. 前端工程化与部署

- [前端][拆分][正则] 拆分单文件 HTML/CSS/JS 用正则匹配 `<style>`/`<script>` 标签，禁止用固定行号（一改就错位）。【已验证】→ `RULES.md` §4.2、`frontend-debug-experience.md`
- [前端][dom][空白] 页面空白先跑 `python diagnose_frontend.py`（div 平衡 + nav/page ID 匹配 + script 标签平衡），不靠肉眼；改前 `git stash` 留退路，回滚 30 秒。【已验证】→ `frontend-debug-experience.md` 快速验证脚本
- [前端][缓存][强刷] 浏览器强缓存旧 JS/CSS 会让"部署了却不生效"：测试时 DevTools 勾 Disable cache + Ctrl+Shift+R。【已验证】→ `RULES.md` §4.2
- [前端][node-check] 改完 JS 必须 `node --check app.js` 通过后再部署；函数名改完全局 grep 无残留旧名。【已验证】→ `RULES.md` §4.3
- [前端][错误处理][html] axios 响应拦截器遇 `Content-Type: text/html` 时不要把 nginx 502 错误页原文塞进用户提示框（P1-1 教训）。【已验证】→ `frontend-bug-list-20261028.md` P1-1

### C. 数据与因果纪律

- [前视][shift] 所有特征只用 `available_at <= bar.close` 的数据；禁止 `shift(-1)`/`iloc[i+1]`；新特征必须在 `tests/test_features_causal.py` 追加断言。【行业共识】→ `../AGENTS.md` 规则 1/5、`RULES.md` §3.1、`ANTI_FRAGILE.md` 死法 1
- [集合分离] ATR/vol/Hurst 只在 CLEAN 集估计、供需区只用 KNOWN 集构建；禁止读静默集数据。【行业共识】→ `../AGENTS.md` 规则 2、`../docs/data_splits.md`、`ANTI_FRAGILE.md` 死法 2
- [时区] MT5 服务器偏移必须与 Python 端 `--tz` 一致，禁止硬编码；任何时间对齐改动必跑 `tests/test_data_timezone.py`。【行业共识】→ `../AGENTS.md` 规则 6、`ANTI_FRAGILE.md` 死法 3
- [缺口清洗] M5/M15 必须过 `core/gap_normalizer.py`；`ffill` 假行情会让波动率低估、止损被跳空打穿。【行业共识】→ `RULES.md` §3.3、`ANTI_FRAGILE.md` 死法 4

### D. 交易策略与风控

- [仓位][kelly] 单笔风险 ≤ 总资金 2%；分数 Kelly（1/4~1/2），永不全 Kelly；波动率目标法，波动大少做。【行业共识】→ `RULES.md` §2.1
- [止损][单调] 止损只允许向盈利方向移动；R 倍数用入场冻结的 `atr0/entryDist`；止损在系统层强制执行，人工无法覆盖。【行业共识】→ `../AGENTS.md` 规则 4、`RULES.md` §2.2、`ANTI_FRAGILE.md` 死法 10
- [回撤][熔断] 回撤 10% 自动减仓 50%，15% 全部清仓；杠杆永不超过 3 倍。【行业共识】→ `RULES.md` §2.3
- [过拟合][冻结] 决策规则实验前冻结，实验后只评估不修改；`trials_N` 含失败只增不减；PBO/CPCV/DSR 三重验证缺一不可；OOS 连续 3 个月才允许小仓位测试。【行业共识】→ `RULES.md` §一、`../AGENTS.md` 规则 11、`ANTI_FRAGILE.md` 死法 5/6
- [上线][阶梯] 新策略必须 dryrun → 影子模式 ≥2 周 → 小资金 ≤1% ≥1 个月 → 正常仓位，禁止跳级；连赢后也不例外。【行业共识】→ `ANTI_FRAGILE.md` 死法 20 与 §2.4

### E. 顶级机构实践（只列标题，正文见原文）

→ 全部详见 `../skills/quant-trading-expert/references/top-firm-practices.md`

1. Renaissance：海量弱信号叠加成信号工厂，不追圣杯；过拟合防御比模型复杂度重要。【行业共识】
2. Two Sigma：数据基建 / Feature Store 是护城河；研究与生产严格分离。【行业共识】
3. DE Shaw：多策略组合平台，方法论比单一策略更重要。【行业共识】
4. Citadel Securities：做市赚"即时性保险"的价差，核心是库存与风险定价而非预测方向。【行业共识】
5. Millennium：Pod 风险预算制——单 pod 亏穿不传导，不行就换。【行业共识】
6. Jane Street：一切决策概率化（贝叶斯）；内部培训与知识传承是核心竞争力。【行业共识】
7. Jump Trading：低延迟是特定领域壁垒，"快到刚好能赚钱"即可，不是越快越好。【行业共识】
8. AQR：因子是慢变量，注意论文发表后的因子衰减与拥挤。【行业共识】
9. 行业共识 7 条：风控第一 / 过拟合最大敌 / 分散化 / 数据质量 / 因果 / 基建 / 持续进化。【行业共识】
10. 常见误区 5 条：ML 非越复杂越好 / 回测好看≠有效 / 没有圣杯策略 / 杠杆放大亏损 / 机构方法不可直接照搬。【行业共识】

### F. 思维模型（只列框架名，应用见原文）

→ 全部详见 `../skills/quant-trading-expert/references/mental-models.md`

- **查理·芒格**：逆向思维（inversion——先研究怎么死）、能力圈、奥卡姆剃刀、决策前检查清单。
- **瑞·达里欧**：极度透明 / 极度求真；"不要问我对不对，问我怎么知道我是对的"（确认偏误防御）。
- **埃隆·马斯克**：第一性原理——从最基本事实推导，不从"别人怎么做"出发。
- **工具箱其余**：概率思维 / 期望值、安全边际、二阶思维、系统思维（存量与流量 / 杠杆点）、机会成本与沉没成本、均值回归、复利与杠杆、编程思维（模块化 / 分层 / 因果性 / 测试 / 实验管理 / 增量开发 / 可复现）。

### G. 网络与外部 API

- [okx][被墙][curl7] `curl` 退出码 7 = 连不上，先 `nslookup` 区分 DNS 还是网络；`Test-NetConnection www.okx.com -Port 443`；对比 baidu（通）/google（不通）即可定位"仅境外站被墙"。【已验证】→ `docker-okx-debug-2026-10.md` §3
- [okx][代理] 本地开发必须让 Python `requests` 读到代理（`$env:HTTPS_PROXY="http://127.0.0.1:7890"`），只配浏览器没用；生产环境要部署在能直连 OKX 的区域。【已验证】→ `docker-okx-debug-2026-10.md` §3
- [git][gitee] GitHub 直连慢/超时走代理；推送同步走 Gitee 远端（`git push gitee main`）。【已验证】→ `frontend-debug-experience.md` 部署后流程
- [okx][假阳性] 代理没通之前，禁止在 TODO 里把"OKX 联通"标 ✅——否则换个网络环境全是假阳性。【已验证】→ `docker-okx-debug-2026-10.md` §3

---

## 4. 自动沉淀触发机制（重点）

### 4.1 触发时机清单

| 时机 | 动作 | 时限 |
|---|---|---|
| T0 踩坑当天 | 修完 bug 立刻在本文件对应分桶追加一行；标签先打，正文后补也行 | 收工前 5 分钟 |
| T1 修 bug 顺手记 | 修的是已登记条目的变种 → 更新原条目，不新起一条；是新坑 → 新起一条 | 同 T0 |
| T2 实验失败复盘 | `experiments/` 复盘时，把"为什么失败"提炼成一条（关联 registry variant） | 复盘会上当场 |
| T3 每周五批量补 | 本周踩过但漏记的，下班前 10 分钟扫一遍 git log / 聊天记录补齐 | 每周五 |

### 4.2 检索约定

- 每条记忆开头打 **2-4 个方括号标签**，如 `[docker][nginx][502]`。
- 下次排障先 Grep：`rg -i "502"` 或 `rg -i "okx.*被墙"`，命中即读条目，不重造轮子。
- 标签词表（持续扩充）：`[docker]` `[nginx]` `[502]` `[dns]` `[env]` `[镜像]` `[前端]` `[缓存]` `[dom]` `[前视]` `[时区]` `[集合分离]` `[风控]` `[止损]` `[回撤]` `[过拟合]` `[okx]` `[代理]` `[github]`。
- 新条目打标签时优先复用已有词表，不要自造同义词，保证 Grep 召回率。

### 4.3 与 AGENTS.md 的衔接

- `docs/` 在 AGENTS.md「可改」清单内，**MEMORY.md 归 Agent 自己维护，不需要人审**——与 `configs/`、`registry.yaml`、`mt5/` 的人工确认制明确区分。
- 但反向升级要走原流程：MEMORY 里某条经验若想升格为「硬规则 / 风控阈值 / mt5 常量」，仍须按 AGENTS.md 停止条件停下来问人，不能在 MEMORY 里直接改写成禁令。
- MEMORY 本身不触发停止条件；它是沉淀层，不是决策层。

### 4.4 过期清理

- 每季度评审一次（对齐 `ANTI_FRAGILE.md` 复审节奏，原计划 2026-11-30 首次）。
- 已被代码 / 测试 / 脚本固化的条目（例：B2 已固化为 `diagnose_frontend.py`）从索引里删掉正文，只留一行"为什么这么做 + 指向脚本的链接"。
- 已被新经验推翻的旧条目标【已过时】并移到分桶末尾，三个月后删除——不留矛盾信息误导排障。

---

## 5. "系统越来越聪明"闭环图

```
踩坑发生
  ↓
ERROR_LOG 登记事故（完整时间线 / 影响 / 复现步骤）   ← 事故档案层
  ↓
30 秒内提炼一行写进 docs/MEMORY.md（打标签 + 证据等级） ← 本文件：记忆索引层
  ↓
下次任务开场先 Grep 标签 / 扫相关分桶
  ↓
命中 → 避开重犯；未命中 → 继续踩，踩完回到第一步再记
  ↓
连续 ≥2 次验证有效的经验 → 升级 SUCCESS_PLAYBOOK（胜法层）
  ↓
仍然成立且代价高的 → 固化成 AGENTS.md 硬规则 / 自动化测试 / 运维脚本（制度层）
  ↓
能力复利：同一个坑永远不再花第二次时间 → 系统随踩坑次数变聪明
```

---

## 6. 新记忆空白模板（复制粘贴即用）

```
[标签1][标签2][标签3]
- 问题：
- 解决方案：
- 复用条件：
- 关联文件：
- 证据等级：【待验证】
```
