# 量化交易系统 Rules 避坑指南

> 基于第一性原理 + 查理芒格逆向思维 + 全球顶级机构最佳实践
> 所有踩坑经验沉淀于此，避免重复犯错

---

## 一、过拟合防御铁律（违反即打回）

### 1.1 决策规则冻结
- ❌ **禁止**：根据回测结果调整阈值
- ✅ **必须**：决策规则在实验前冻结，实验后只能评估不能修改
- ❌ **禁止**：试了100次只报告最好的1次
- ✅ **必须**：trials计数包含所有失败试验，数据挖掘偏差必须惩罚

### 1.2 三重验证缺一不可
- ✅ PBO（概率回测过拟合）
- ✅ CPCV（组合交叉验证）
- ✅ Deflated Sharpe Ratio（衰减夏普比率）

### 1.3 样本外是唯一真理
- ❌ **禁止**：回测好看就上线
- ✅ **必须**：样本外连续3个月稳定表现才允许小仓位测试
- ❌ **禁止**：用未来数据做回测（前视偏差）
- ✅ **必须**：所有信号只用收盘后的数据计算

---

## 二、风控铁律（违反即爆仓）

### 2.1 仓位管理
- ❌ **禁止**：单笔风险超过总资金2%
- ✅ **必须**：波动率目标法，波动大少做，波动小多做
- ❌ **禁止**：盈利后加仓（越涨越买 = 越跌越亏）
- ✅ **必须**：分数Kelly（1/4 ~ 1/2），永远不用全Kelly

### 2.2 止损纪律
- ❌ **禁止**：止损只靠人执行（人会"再等等"）
- ✅ **必须**：止损在系统层强制执行，人工无法覆盖
- ❌ **禁止**：亏损单扛着等回本
- ✅ **必须**：触发止损立即执行，不犹豫不讨价还价

### 2.3 回撤控制
- ❌ **禁止**：回撤超过20%还不减仓
- ✅ **必须**：回撤10%自动减仓50%，回撤15%全部清仓
- ❌ **禁止**：杠杆超过3倍
- ✅ **必须**：杠杆永远保守，不追求高收益

---

## 三、数据质量铁律（垃圾进 = 垃圾出）

### 3.1 前视防御
- ❌ **禁止**：用t+1的数据算t时刻的信号
- ✅ **必须**：所有特征只用available_at <= bar.close的数据
- ❌ **禁止**：用未来函数（如`shift(-1)`）
- ✅ **必须**：单元测试专门测前视偏差

### 3.2 集合分离
- ❌ **禁止**：统计量估计集和策略构建集混用
- ✅ **必须**：CLEAN集估计ATR/波动率，KNOWN集构建供需区
- ❌ **禁止**：测试集参与参数优化
- ✅ **必须**：训练集/验证集/测试集严格分离

### 3.3 数据清洗
- ❌ **禁止**：不做缺口清洗直接回测
- ✅ **必须**：M5/M15数据必须做缺口检查和插值
- ❌ **禁止**：忽略跳空缺口的影响
- ✅ **必须**：回测成本必须包含滑点和点差

---

## 四、工程铁律（系统可靠性）

### 4.1 Docker部署
- ❌ **禁止**：本地改完直接跑（容器内代码不是volume挂载）
- ✅ **必须**：修改后docker cp进去，然后docker restart
- ❌ **禁止**：PowerShell处理UTF-8中文（会乱码）
- ✅ **必须**：用Python脚本处理中文文件读写
- ❌ **禁止**：手动stop+rm生产容器，用新镜像启动
- ✅ **必须**：用docker compose up -d恢复，不要手动run
- ❌ **禁止**：猜环境变量名（POSTGRES_PASSWORD vs DATABASE_URL）
- ✅ **必须**：先Read后端代码确认环境变量名再传
- ❌ **禁止**：docker cp零散文件进去导致依赖缺失崩溃
- ✅ **必须**：要么完整build新镜像，要么用官方镜像跑稳定版本

### 4.2 前端调试
- ❌ **禁止**：用固定行号拆分HTML/CSS/JS
- ✅ **必须**：用正则匹配`<style>`/`<script>`标签拆分
- ❌ **禁止**：改了本地frontend-pro/就以为部署生效了
- ✅ **必须**：确认Docker容器跑的是哪个前端，改完必须docker cp进去或重启volume
- ❌ **禁止**：改完JS不做语法检查
- ✅ **必须**：`node --check app.js`通过后再部署
- ❌ **禁止**：浏览器缓存旧文件
- ✅ **必须**：测试时强制刷新（ignoreCache: true）

### 4.3 函数命名
- ❌ **禁止**：前后端函数名不一致
- ✅ **必须**：后端返回字段名和前端期望的字段名严格对齐
- ❌ **禁止**：猜函数名
- ✅ **必须**：先Read后端代码确认方法签名再调用

---

## 五、策略生命周期铁律（Alpha会衰减）

### 5.1 策略上线前
- ✅ 逻辑可解释：为什么这个策略能赚钱？
- ✅ 样本外验证：连续3个月稳定表现
- ✅ 容量评估：最多能承载多少资金？
- ✅ 失效预案：什么信号出现就说明策略不行了？

### 5.2 策略运行中
- ✅ 三级健康度监控：绿区运行→黄区减仓→红区退役
- ✅ 夏普衰减监控：对比上线时的夏普比率
- ✅ 拥挤度监控：持仓集中度、换手率
- ✅ 自动退役机制：触发阈值自动停掉

### 5.3 策略退役后
- ✅ 复盘：为什么失效了？
- ✅ 沉淀：经验写入知识库
- ✅ 归档：代码和参数保留，可回滚

---

## 六、踩坑经验清单（按时间排序）

| 日期 | 踩坑内容 | 解决方案 | 影响 |
|------|---------|---------|------|
| 2026-10-25 | PowerShell处理UTF-8中文乱码 | 改用Python脚本读写文件 | 前端拆分失败，回滚重做 |
| 2026-10-25 | 前端函数名不匹配（logDebug vs debugLog） | 批量替换，统一命名 | WebSocket连接失败 |
| 2026-10-26 | Docker容器代码不是volume挂载 | 修改后必须docker cp + restart | 改了代码不生效 |
| 2026-10-26 | 前后端字段名不一致（active vs healthy_count） | 对齐字段名，加打印调试 | 前端显示"加载中" |
| 2026-10-26 | StrategyHealth构造函数参数不匹配 | 按实际dataclass字段传参 | API 500错误 |
| 2026-10-26 | 浏览器缓存旧JS文件 | 强制刷新ignoreCache: true | 改了不生效 |
| 2026-10-26 | 用固定行号拆分前端文件 | 改用正则匹配标签 | 拆分失败回滚 |
| 2026-10-27 | 随便删除正在运行的Docker容器 | 禁止stop+rm生产容器，重启前先记录所有环境变量和网络配置 | 后端连不上数据库，花了半小时恢复 |
| 2026-10-27 | 新容器没加入docker网络 | docker network connect加入原有网络 | 容器之间无法通信，502错误 |
| 2026-10-27 | 后端代码环境变量名和数据库不匹配 | 先Read代码确认用的环境变量名（不是POSTGRES_PASSWORD） | 密码认证失败 |
| 2026-10-27 | 手动stop+rm生产容器 | 禁止手动删容器，必须用 `docker compose up -d <service>` 恢复 | 后端服务瘫痪，花了半小时还没恢复 |
| 2026-10-27 | 新容器没加入docker网络 | 用compose启动会自动加入网络，手动run要docker network connect | 502 Bad Gateway |

---

## 七、核心原则速查

1. **先想怎么亏钱，再想怎么赚钱**（查理芒格逆向思维）
2. **简单的策略比复杂的模型更可靠**（奥卡姆剃刀）
3. **分散化是唯一的免费午餐**（不是持仓数量，是风险因子分散）
4. **截断亏损，让利润奔跑**（数学：左尾截断+右尾暴露）
5. **不爆仓是第一要务**（活得久才能复利）
6. **每次故障都是一次学习机会**（反脆弱）
7. **决策可审计，每笔交易都能还原**（透明度）
8. **因果单向，只用收盘后的数据**（前视防御）

---

**最后更新**：2026-11-08（追加真实数据口径收口两条规则）
**维护人**：QuantDinger
**适用范围**：所有策略开发、系统修改、回测验证

---

## 2026-10-28 本轮新踩坑

> 来源：`docs/frontend-bug-list-20261028.md`、`docs/frontend-debug-experience.md`、`docs/p2-panel-completion-20261028.md`、`docs/strategy-registration-20261028.md`
> 每条统一格式：现象 / 根因 / 修复 / 预防措施 / 验证命令

### Docker 容器崩溃排查清单

- **现象**：
  - 后端容器突然连不上 PostgreSQL，前端 502；或手动 `docker stop` + `docker rm` 后无法恢复。
  - 新启动的后端容器起来了（`/health` 200），但前端容器访问 `/api/*` 全部 502 或连接被拒。
  - `quantdinger-scheduler-worker`、`quantdinger-trading-worker` 状态 unhealthy。
- **根因**：
  1. 手动 `docker run` 启动的新容器**没有加入 `trader_quantdinger-network`**，Docker DNS 无法解析对端容器名。
  2. 直接 pull 官方后端镜像恢复，结果我们自己写的 `account.py` / `okx_client.py` 路由**根本不在官方镜像里**（Dockerfile 没 `COPY app/`）。
  3. 本地改的前端/后端代码没有 volume 挂载到容器，`docker cp` 零散文件进去容易漏依赖，导致容器启动即崩。
- **修复**：
  1. 一律用 `docker compose up -d <service>` 恢复，不要手动 `run`；手动 run 后必须 `docker network connect trader_quantdinger-network <容器名>`。
  2. 自定义路由必须由 Dockerfile `COPY app/` 整体构建自有镜像；build 完立刻打 `GET /openapi.json` 确认 `/api/okx/*` 路由已注册。
  3. 恢复前先 `docker inspect <旧容器>` 记录所有环境变量、网络别名、挂载卷，再按原值重建。
- **预防措施**：
  - ❌ 禁止 `docker stop` + `docker rm` 正在运行的生产容器；删除前先 `docker inspect` 全量留档。
  - ❌ 禁止裸 `docker run` 起服务，统一走 docker-compose。
  - ✅ 容器崩溃后第一步先看日志（`docker logs --tail 100 <容器>`），不要先重启。
- **验证命令**：
  ```powershell
  docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
  docker inspect -f "{{range .NetworkSettings.Networks}}{{.NetworkID}} {{.Aliases}}{{end}}" quantdinger-backend
  docker exec quantdinger-frontend getent hosts quantdinger-backend
  curl.exe -s http://localhost:5000/api/health
  curl.exe -s http://localhost:5000/openapi.json | Select-String "okx"
  ```

### 环境变量前后端名一致性检查清单

- **现象**：
  - 后端日志反复报 `password authentication failed for user "postgres"`，但 `.env` 里密码看起来是对的。
  - 前端设置面板填了 Key/Secret/Passphrase，后端拿不到，连接测试返回空或 401。
- **根因**：
  1. 后端代码 `os.getenv("POSTGRES_PASSWORD")`，但 compose 里写的是 `DATABASE_URL`，名字对不上导致读成 `None`，走了默认值。
  2. 前端 axios 请求带的字段名 `active`，后端返回的是 `healthy_count`，字段错位。
  3. 前端调用的函数名 `logDebug`，后端/JS 里实际叫 `debugLog`，整个 JS 执行中断。
- **修复**：
  1. 改 compose 之前，先 `Get-Content backend/app/**/*.py | Select-String "os.getenv"` 把后端**真正读取的变量名**列出来，再对齐 `.env`。
  2. 字段名以**后端 dataclass / Pydantic 模型**为准，前端按后端返回字段名渲染，不要靠猜。
  3. 函数命名改完统一 `node --check app.js` + 全局 grep 确认没有残留旧名。
- **预防措施**：
  - ❌ 禁止凭直觉写环境变量名（`POSTGRES_PASSWORD` vs `DATABASE_URL` 是经典坑）。
  - ❌ 禁止猜前后端字段名/函数名，必须先 Read 代码。
  - ✅ 新接入一个环境变量时，在 `.env.example` 里同时写明「后端读取处 + 用途 + 默认值」。
- **验证命令**：
  ```powershell
  Select-String -Path "backend_api_python/app/**/*.py" -Pattern "os\.getenv|os\.environ"
  docker exec quantdinger-backend env | Select-String "POSTGRES|DATABASE|OKX"
  node --check frontend-pro/js/app.js
  ```

### nginx upstream / 502 排查清单

- **现象**：
  - 通过前端 `http://localhost:8888` 访问，所有 `/api/*` 返回 `502 Bad Gateway`（nginx/1.25.5 默认错误页），但**直连** `http://localhost:5000/api/health` 返回 200。
  - 前端控制台报 `Failed to load security config: AxiosError: <html>...502 Bad Gateway...`。
  - nginx 错误日志：`backend could not be resolved (3: Host not found)`。
- **根因**：
  - 前端容器 `/etc/nginx/conf.d/default.conf` 里写的是 `set $backend_upstream http://backend:5000; proxy_pass $backend_upstream;`。
  - 但 docker 网络 `trader_quantdinger-network` 里后端容器的 DNS 别名只有 `quantdinger-backend`（和短 ID），**根本没有 `backend` 这个别名**，nginx 解析失败直接 502。
  - 注意：即使配了 `resolver 127.0.0.11`，主机名本身不存在也救不了。
- **修复**（三选一，按优先级）：
  - 方案 A（推荐）：`docker-compose.yml` 给后端 service 加 `networks.trader_quantdinger-network.aliases: [backend]`。
  - 方案 B：改 nginx 配置，把 `backend:5000` 改成 `quantdinger-backend:5000`，`docker cp` 进前端容器后 `docker exec quantdinger-frontend nginx -s reload`。
  - 方案 C：确认 compose 里服务名和 nginx upstream 名**严格一致**。
- **预防措施**：
  - ❌ 禁止在 nginx `proxy_pass` 里写主机名而不在 compose 里配 alias。
  - ✅ 新增/修改 upstream 后，必须 `docker exec <前端容器> getent hosts <upstream名>` 验证 DNS 能解析。
  - ✅ 前端 axios 响应拦截器要判断 `Content-Type: text/html` 时不把 nginx HTML 原文塞给用户（否则用户看到一整段 HTML，排查误导）。
- **验证命令**：
  ```powershell
  docker exec quantdinger-frontend getent hosts quantdinger-backend
  docker exec quantdinger-frontend getent hosts backend
  curl.exe -s -o NUL -w "%{http_code}`n" http://localhost:8888/api/auth/security-config
  curl.exe -s -o NUL -w "%{http_code}`n" http://localhost:5000/api/health
  docker logs quantdinger-frontend --tail 30
  ```

### 前端组件化拆分调试经验

- **现象**：
  - 把单文件 `index.html` 拆成 `index.html + css/main.css + js/app.js` 后，整个页面空白或导航点了没反应。
  - 一次插入 5 个新模块后页面崩，不知道是哪一处出问题。
  - 改完 JS 本地看没问题，部署到容器后浏览器还是旧行为。
- **根因**：
  1. `<div>` 开闭不平衡（开了 N 个只闭合 N-1 个），浏览器渲染失败整页空白。
  2. 插入位置错：插到 `</main>` 之后，或插在某个未闭合 div 内部，破坏了原有 DOM 结构。
  3. 插入的 HTML 里带了裸 `<` `>`，被 JS 解析成语法错误；或 CSS 引号未闭合。
  4. 浏览器强缓存了旧 `app.js` / `main.css`。
  5. 用「固定行号」拆分 HTML/CSS/JS，一改就错位。
- **修复**：
  1. 用正则匹配 `<style>...</style>` / `<script>...</script>` 标签拆分，不用行号。
  2. 插入新模块严格定位在两个 `<div class="page-view">` 之间，模板复用：
     ```html
     <div class="page-view" id="page-xxx"> ... </div>
     ```
  3. 每加一个模块立刻跑 `python diagnose_frontend.py`（div 平衡 + 导航/页面 ID 匹配 + script 标签平衡）。
  4. 部署后 `Ctrl+Shift+R` 或 DevTools 勾选 `Disable cache`。
  5. 小步快跑：插一个模块 → 验证 → 再插下一个，不要一次塞 5 个。
- **预防措施**：
  - ❌ 禁止用 PowerShell 处理 UTF-8 中文（Get-Content/Set-Content 会搞坏编码），一律用 Python 脚本读写。
  - ❌ 禁止改完 JS 不做语法检查就部署。
  - ✅ 每次拆分/插入前 `git stash` 或 `git checkout HEAD -- index.html` 留退路。
  - ✅ 故障回滚 30 秒：`git checkout HEAD -- frontend-pro/index.html` → `docker cp` → 强刷浏览器。
- **验证命令**：
  ```powershell
  python diagnose_frontend.py
  node --check frontend-pro/js/app.js
  docker cp frontend-pro/index.html quantdinger-frontend:/usr/share/nginx/html/pro/index.html
  docker cp frontend-pro/js/app.js    quantdinger-frontend:/usr/share/nginx/html/pro/js/app.js
  # 浏览器侧：DevTools Network → Disable cache 打勾 → Ctrl+Shift+R
  ```

---

**本轮新踩坑沉淀完毕（2026-10-28）**

---

## 2026-11-08 本轮新踩坑（真实数据口径收口）

> 来源：压力测试面板空态收口、绩效对比表/月度热力图真实空态隔离（commit `1dd8130`）。
> 主线口径：行情层继续用 CCXT，实盘自研链路不动；真实模式禁止演示哨兵顶替缺失值，缺值 `--`；仅未登录/接口全挂的演示兜底保留示例。

### 4.4 演示模板视图与真实数据源视图必须隔离

- **现象**：
  - 真实登录态下，压力测试五卡、绩效对比表、月度热力图仍渲染 HTML 里硬编码的演示数字（-1.22%、+3.2、+67.97% 等），容易被误读为真实绩效。
  - 接口失败或返回空数组时，渲染函数早 `return`，静态演示值残留；有些指标回填选择器永远命中 `null`，评分一直显示静态默认值。
- **根因**：
  1. 演示模板与真实数据回填未做隔离，"有数据回填、无数据清空"的分支缺失。
  2. 用 CSS `[style*="文本"]` 选择器匹配指标文本——文本在 `textContent` 不在 `style` 属性里，选择器恒为 `null`，回填从未生效。
  3. 未区分"真实 0"与"无数据"，null/0 混填。
- **修复**：
  1. 每个需回填的面板加真实模式标志（如 `backtestIsReal`）：接口 `code===1` 且数据非空 → 回填；无数据/异常 → 调清空函数，所有单元格置 `--`、清空内联颜色与正负类。
  2. 仅未登录或接口全挂时，才保留 HTML 静态样例作为演示兜底；真实模式一律不得用演示数字顶替缺失值。
  3. 回填元素用**显式 `id`**（`getElementById`），不用按 `style` 属性匹配文本；回填用 `textContent`，避免 `innerHTML` 重建导致 `id` 丢失后二次回填又匹配不到。
  4. `data_status` 区分 `completed_trades / no_signals / unknown / live`，前端据此区分真实 0 与无数据。
  5. 同一指标存在新旧两套 UI（旧静态面板 + 新 P2/引擎卡片）时，真实数据源只接新卡片；旧面板在真实模式清空演示数字/列表为空态占位，不在旧面板另写一套回填，避免双口径长期并存。
  6. 后端返回的结果须带口径契约标记（如 `data_kind:"real" / "demo"`，回测行用 `data_status`）；前端渲染函数先判标记，**仅 `real` 才回填**，`demo`/缺标记/无情景一律走清空函数。缺标记按"非真实"处理，不得默认渲染。
  7. WS 行情回填先核对流类型与字段名：partial book depth 流字段是 `bids`/`asks`（数组），增量 depth diff 流才是 `b`/`a`；回填容器必须用 HTML 里真实存在的显式 `id`，改容器命名/互换后同步更新 JS 目标 id，避免命中 `null` 提前 return、静态兜底行永久残留。
- **预防措施**：
  - ❌ **禁止**：真实模式下用演示哨兵数字顶替缺失指标；把 `no_signals` 当 0 胜率；按 `style` 属性选择器匹配可见文本。
  - ✅ **必须**：缺值统一渲染 `--`；新面板先定"数据源状态（真实/演示/无数据）"再决定渲染；静态演示块在真实登录态加"演示模板"标记。
  - ✅ **必须**：新增指标回填前，先确认后端字段存在且非空，再写前端映射；不猜字段名。
  - ✅ **必须**：账户/凭证列表唯一事实源为 `GET /credentials/list`；真实登录态空凭证渲染空态提示，仅未登录/接口全挂（非真实）才保留演示兜底卡片，不得在真实模式硬编码 `OKX-DEMO` 与固定 api_key_hint。
  - ✅ **必须**：前端日志 `debugLog(msg, type)` 签名不可颠倒；把级别放首参会让 `type` 字段错位成消息文本，导致系统日志 error/warn 级别筛选与计数失效。
- **验证命令**：
  ```powershell
  node --check frontend-pro/js/app.js
  # 浏览器：登录态切到回测/验证页，核对对比表、热力图、压力卡缺失项显示 --，无静态演示数字残留
  ```

### 4.5 图表画布渲染时序：容器不可见时初始化会得到离屏空图

- **现象**：
  - 权益/回撤曲线数据成功喂入 series、无未捕获报错，但浏览器里曲线空图；canvas 保持 300×150 的离屏缓冲默认尺寸。
  - 主图 K 线在仪表盘同样未上屏。
- **根因**：
  - 多页 SPA 中目标图表容器处于 `display:none` / 未激活页时初始化图表，画布拿不到布局宽高；切到可见页后未触发 resize 重绘。
- **修复方向**（规则层，具体实现按图表库 API）：
  1. `init` 图表前先判容器 `clientWidth/clientHeight > 0`，不可见则延迟到页面激活后再初始化。
  2. 页面切换/懒加载激活后，对已存在图表调用 resize 重绘；空容器给文字占位 fallback。
  3. 图表懒加载：不在首屏一次性初始化所有隐藏页图表。
- **预防措施**：
  - ❌ **禁止**：在离屏容器首屏批量初始化多页图表；忽略容器尺寸直接 `addSeries`。
  - ✅ **必须**：图表初始化绑定在"容器可见"之后；窗口/容器尺寸变化后 resize。
- **未验证**：本轮在内嵌测试浏览器中观察到画布合成/上屏环境限制（主图 K 线同样未上屏），**曲线是否在真实 Chrome 正常出图未复核**；需在真实 Chrome 强刷后确认权益/回撤曲线渲染。

### 4.6 多页 SPA 的 page-view 容器必须闭合配平

- **现象**：新增/既有页面在导航切换后 DOM 可读到文本、标题齐全、控制台 0 报错，但主体区域 0×0 宽度全黑空白。
- **根因**：前一个页面容器内某个面板 `div` 或页面自身 `div` 未闭合，浏览器容错把后续 `page-view` 吞进其 `display:none` 子树；父级 `display:none` 级联隐藏，即使目标页加了 `active` 也拿不到布局宽高。
- **定位方法**：浏览器读目标页 `getBoundingClientRect()` 宽高为 0 时，沿 `parentElement` 父链向上看，被吞页面会挂在某个 `#page-xxx` 或无名面板 DIV 下，而不是直挂 `MAIN.main-content`；用父链锚定未闭合的容器，比逐行正则栈解析可靠（行内嵌套 `div` 会让行首正则漏算）。
- **预防措施**：
  - ✅ **必须**：每个 `#page-xxx` 及其内部面板 `div` 开闭配平；新增页面前确认前一页面容器已闭合，与既有页面平级挂在 `MAIN.main-content` 下。
  - ✅ **必须**：改完 HTML 在浏览器逐页切换，核验每页 `active` 页 `getBoundingClientRect()` 宽度正常（非 0），不只看 DOM 文本是否可读。
  - ❌ **禁止**：只凭控制台 0 报错或 DOM 文本存在就判定页面上屏通过；宽度塌缩属于静默布局缺陷。

