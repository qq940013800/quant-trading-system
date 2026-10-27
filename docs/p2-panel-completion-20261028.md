# P1/P2 模块可视化卡片补全（核心引擎面板）

日期：2026-10-28
范围：`frontend-pro/` 前端核心引擎页（`page-engine` → "📦 P1/P2 企业级模块状态" 区块），将 6 张静态占位卡片替换为实时数据卡片。

---

## 1. 模块 → API 路径映射

| 卡片 | 后端路由（Blueprint 前缀） | 方法 | 数据源服务 |
|---|---|---|---|
| 🛡️ 高可用与灾备 | `/api/p1/health` | GET | `services/business_continuity.py` |
| 📝 交易日志与归因 | `/api/p1/journal/analyze?days=30` | GET | `services/trade_journal.py` |
| 🔒 安全与合规 | `/api/p1/security/summary` | GET | `services/security.py` |
| 👥 策略拥挤度监控 | `/api/p2/crowding/summary` | GET | `services/crowding_monitor.py` |
| 📊 可观测性与告警 | `/api/p2/observability/summary` | GET | `services/observability.py` |
| 🚀 CI/CD与部署 | `/api/p2/cicd/status` | GET | `services/cicd.py` |

路由注册位置：
- `backend_api_python/app/routes/p1_modules.py` → 前缀 `/api/p1`（register.py:119）
- `backend_api_python/app/routes/p2_modules.py` → 前缀 `/api/p2`（register.py:120）

**结论：6 个模块后端路由全部存在，无"后端 API 缺失"的占位卡片。**

> 备注：任务书中说"6 个 P2 模块"，实际后端将其中 3 个（高可用 / 交易归因 / 安全合规）放在 `p1_modules.py`（前缀 `/api/p1`），其余 3 个（拥挤度 / 可观测性 / CI/CD）在 `p2_modules.py`（前缀 `/api/p2`）。卡片区块标题保持原样（"P1/P2 企业级模块状态"）。

## 2. 卡片字段映射（前端渲染 ← 后端返回）

统一响应包络：`{ success: bool, data: {...}, error?: str }`。

### 2.1 🛡️ 高可用（`/api/p1/health`）
- 状态灯：`data.overall_status` → healthy=绿 / degraded=黄 / unhealthy=红 / unknown=灰
- 指标：可用率 `availability_pct`；健康服务 `healthy/total_services`；累计故障 `total_failures`（>0 标黄）；故障切换 `total_failovers`

### 2.2 📝 交易日志归因（`/api/p1/journal/analyze?days=30`）
- 状态灯：后端无健康字段 → 前端推导：`total_trades > 0`=绿(ANALYZED)，否则=灰(NO DATA)
- 指标：周期 `period`；总交易 `total_trades`；胜率 `win_rate`（×100%）；净利 `total_pnl`；盈亏比 `profit_factor`

### 2.3 🔒 安全合规（`/api/p1/security/summary`）
- 状态灯：`data.security_level` → good=绿 / warning=黄 / critical=红
- 指标：活跃会话 `active_sessions`；活跃密钥 `active_api_keys`；审计日志 `total_audit_logs`；严重告警 `critical_alerts`（>0 标红）

### 2.4 👥 拥挤度（`/api/p2/crowding/summary`）
- 状态灯：`data.status === "no_strategies"` → 灰(NO DATA)；否则按 `distribution` 推导：extreme>0=红 / high+extreme>0=黄 / 否则绿
- 指标：监控策略 `total_strategies`；平均拥挤分 `avg_crowding_score`（≥50 标黄）；高/极高拥挤数；提示文案 `warning`

### 2.5 📊 可观测性（`/api/p2/observability/summary`）
- 状态灯：`data.status` → healthy=绿 / warning=黄 / critical=红
- 指标：活跃告警 `active_alerts`（>0 标黄）；严重告警 `critical_alerts`（>0 标红）；累计告警 `total_alerts`

### 2.6 🚀 CI/CD（`/api/p2/cicd/status`）
- 状态灯：后端无健康字段 → 前端推导：`latest_deployment` 为 null=灰(idle)；`success`=绿；`failed/rolled_back`=红；`pending/running`=黄
- 指标：当前版本 `current_version`；累计部署 `total_deployments`；最新部署 `latest_deployment.version (status)`；自动部署 `auto_deploy`（false 显示"人工确认"标黄）

每张卡片固定结构：状态指示灯（圆点发光 + 左边框同色）→ 标题 → 状态码（右上角，等宽字体）→ 指标列表 → 底部分隔线 + API 路径（详情标识）+ 客户端更新时间。

## 3. 修改的文件

| 文件 | 改动 |
|---|---|
| `frontend-pro/index.html` | 替换 "P1/P2 企业级模块状态" 区块内 6 张静态卡片为带 id 的数据卡片（`p2-card/dot/state/metrics/updated-<key>`，key ∈ ha/journal/security/crowding/obs/cicd）；网格 minmax 280px→300px |
| `frontend-pro/js/app.js` | 新增 `P2_LAMP`、`p2PaintLamp/p2SetState/p2SetMetrics/p2Stamp/p2Metric/p2FetchJson/p2Fail/loadP2ModuleCards`；在 `loadEngineData()` 末尾调用一次；底部新增 15s 轮询（仅当 `#page-engine` 处于 active 且已登录时请求） |

未改动：`css/main.css`（样式全部复用现有内联风格与 CSS 变量）、任何后端代码、其他页面卡片。

## 4. 轮询与降级行为

- 进入核心引擎页时立即拉取一次；之后每 15 秒刷新；离开页面后自动停止（守卫 `page-engine.active`）。
- `p2FetchJson` 带 8 秒客户端超时（`Promise.race`）。
- 任何单卡请求失败（网络错误 / HTTP 非 200 / `success=false` / 超时）→ 该卡状态灯置灰、状态码显示 `OFFLINE`、指标区显示"数据不可用"，不影响其他卡片，不向用户抛错。

## 5. 已知问题 / 未验证项

1. **容器未验证**：前端容器 `quantdinger-frontend:8888` 返回 200，但通过其 `/api` 代理请求上述 6 个端点在本机全部 5s 超时（后端服务当前未在本机可达）。卡片真实数据渲染**未在实环境验证**——改完本地源码后需**重启前端容器**（若 docker-compose 未挂卷热更新）才能看到效果；后端在线时卡片应自动点亮。
2. **更新时间为客户端时间**：各 summary 接口不返回服务端时间戳，"更新于"用的是浏览器本地拉取成功的时间，非事件发生时间。
3. **空数据常态**：这些服务为内存单例（进程内状态），冷启动时大多返回空（0 交易 / 0 告警 / 无注册策略），属预期；卡片会显示 NO DATA 而非虚假"正常"。
4. **交易归因的状态灯为前端推导**（后端无 health 字段）：`total_trades=0` 时显示灰灯 NO DATA，不等同于故障。
5. 未改动 `index_new.html` / `index_backup_*.html`（历史备份文件）。
