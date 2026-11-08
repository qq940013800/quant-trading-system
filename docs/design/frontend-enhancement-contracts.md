# 前端增强缺口契约（风险面板 / AI 复盘 / 日志中心）

> 状态：**待评审草稿**。本轮（2026-11-08）前端 `frontend-pro/` 只做只读收口：有真实契约的字段按真实回填，无真实数据源的面板走真实空态 `--`，不造演示值或随机噪声。
> 本轮**不实现**下列后端只读聚合端点，不改交易链路 / 风控 gate / 下单平仓 / 资金计算，不改 schema。
> 口径纪律：阈值/限额由 CLEAN 集分布校准，禁止按绩效网格搜索；动态复盘结果不留静态 Wiki；缺失数值一律 `--`，区分「真实 0」与「无数据」。

## 0. 已核实的现状证据（2026-11-08 登录态实测 + 代码勘察）

| 前端诉求 | 现有后端 | 实测/代码结论 |
|---|---|---|
| 账户回撤 vs 限额 | `GET /api/risk/portfolio` | 真实返回 `current_equity / peak_equity / current_drawdown_pct / open_positions / max_drawdown_limit_pct / risk_level`；实测 `current_drawdown_pct=0.0`、`max_drawdown_limit_pct=20.0`、`risk_level=green`。**未透出**单日亏损限额、总名义敞口、单策略风险、相关性、VaR/CVaR。 |
| 策略级回撤监控 | 无对应只读端点 | `/api/portfolio/monitors` 为持仓监控 CRUD（表 `qd_position_monitors`），不是策略回撤；复盘报告的 `window_max_drawdown_pct` 仅复盘上下文，不构成监控端点。 |
| 风控拦截/拒单历史 | `GET /api/risk/alerts`（内存引擎告警） | 真实端点，字段 `alert_id / timestamp / level / type / message / position_id / symbol / action_required`；实测 `data: []`、`count=0`；**内存态不落库**，重启清空。持久化拒单事件见缺口 G1/G2/G3。 |
| 亏损根因分类 | `POST /api/strategies/review-report` | `metrics` 含 `losing_trades / avg_loss / max_loss / exit_reason_counts`（全平仓原因计数，非亏损归因）；**无**亏损单根因分类字段。 |
| 止损触发统计 | 同上 | **无** `stop_loss_trigger_count` 类字段；`exit_reason_counts` 未按止损族归并，也未区分亏损止损/保本/追踪。 |
| 过早止盈统计 | 同上 | **无**出场后价格路径 / 最大有利 R 对比字段，无法判定「过早止盈」。 |
| 日志中心风控事件分类 | `GET /api/strategies/logs` / `/api/strategies/trades` | 拦截违规码仅落在 `pending_orders.last_error`（TEXT）与 `qd_strategy_logs.message`（TEXT）；无结构化 `reject_reason / violation_code` 列，无拦截计数持久化（G1/G2/G3）。 |

缺口编号引用 `docs/TABLE_SCHEMA.md` 第 5 节：G1 独立风控事件表缺失；G2 拒单/拦截原因未结构化；G3 拦截计数未持久化；G4 风控输入快照未留痕。

---

## C-RISK-01 账户级回撤 / 亏损阈值只读聚合

### 现状
`GET /api/risk/portfolio`（`risk.py::get_portfolio_risk` → `RiskEngine.get_portfolio_risk_summary`）已透出组合快照与回撤限额；单日亏损限额 `daily_loss_limit_pct` 仅存在于引擎配置默认值，未进入响应。

### 建议契约（待评审，后端实现前前端保持空态）
- **路径 / 方法**：`GET /api/risk/portfolio`（扩展现有响应，不新增写操作）
- **鉴权**：沿用现有 Bearer token；按当前用户隔离。
- **请求参数**：无。
- **响应字段（草案）**：

```json
{
  "success": true,
  "data": {
    "account_state": {
      "current_equity": 100000.0,
      "peak_equity": 100000.0,
      "current_drawdown_pct": 0.0,
      "daily_pnl_pct": null,
      "open_positions": 0,
      "risk_level": "green"
    },
    "account_limits": {
      "max_drawdown_limit_pct": 20.0,
      "daily_loss_limit_pct": null,
      "max_position_notional_pct": null,
      "leverage_cap": null
    },
    "data_kind": "real",
    "as_of": "2026-11-08T00:00:00Z"
  }
}
```

- **数据来源**：`risk_engine` 内存组合快照 + 策略/账户 `trading_config.account_risk`；限额数值最终由分布校准，不在代码内拍死。
- **空态口径**：字段缺失或为 `null` → 前端显示 `--`；禁止用配置默认值（如 5%、20%）冒充已生效的真实限额；`data_kind` 非 `real` 时不回填。

### 前端现状
账户回撤 / 回撤限额 / 权益 / 持仓数已按现有真实字段回填；单日亏损限额、敞口、相关性、VaR/CVaR 保持 `--`。

---

## C-RISK-02 策略级回撤监控只读端点

### 现状
无逐策略回撤序列或当前回撤快照；现有持仓监控表面向手工持仓，不承载策略净值曲线。

### 建议契约（待评审）
- **路径 / 方法**：`GET /api/strategies/risk-snapshot`
- **鉴权**：Bearer token；按 `user_id` 隔离。
- **请求参数**：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `strategy_id` | int | 否 | 不传返回当前用户全部策略 |
| `window` | enum | 否 | `live` / `backtest` / `both`，默认 `live` |

- **响应字段（草案）**：

```json
{
  "code": 1,
  "data": [
    {
      "strategy_id": 5,
      "strategy_name": "供需区吞没策略",
      "symbol": "universe:POOL:sp500",
      "as_of": "2026-11-08T00:00:00Z",
      "current_equity": 1000.0,
      "peak_equity": 1000.0,
      "current_drawdown_pct": 0.0,
      "max_drawdown_limit_pct": null,
      "risk_level": "green",
      "open_positions": 0,
      "data_status": "completed_trades"
    }
  ]
}
```

- **数据来源**：`qd_strategy_trades` 平仓成交序列 + 策略风险状态；样本不足返回 `data_status: "no_signals" / "sample_small"`，不回填 0 绩效。
- **空态口径**：无成交样本、接口异常或未登录 → 列表空态占位，回撤/限额 `--`；不展示演示策略名与占比。

### 前端现状
策略级回撤列表固定空态，文案标注「后端暂无逐策略回撤只读端点」。

---

## C-RISK-03 风控拦截 / 拒单历史事件端点

### 现状（缺口 G1 / G2 / G3 / G4）
- 无独立 `risk_events` / `risk_rejects` 表；违规码由 `live_trading/account_risk.py` 组装为 `violations` 列表，拦截时写入 `pending_orders.last_error` 文本与 `qd_strategy_logs.message` 文本。
- `pending_orders.attempts` 是下单重试次数，不等于风控拦截计数；`account_risk_snapshot` 仅请求时内存计算，不落库。
- `/api/risk/alerts` 为内存引擎告警，非持久化拒单流水。

### 建议契约（待评审，涉及新表/新列需单独评审，触碰实盘链路由人工拍板）
- **路径 / 方法**：`GET /api/risk/events`
- **鉴权**：Bearer token；按 `user_id` 隔离。
- **请求参数**：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `strategy_id` | int | 否 | 按策略过滤 |
| `symbol` | string | 否 | 按品种过滤 |
| `level` | enum | 否 | `info / warn / error` |
| `limit` | int | 否 | 默认 50，上限 200 |
| `offset` | int | 否 | 分页 |

- **响应字段（草案）**：

```json
{
  "code": 1,
  "data": {
    "events": [
      {
        "event_id": 1024,
        "ts": "2026-11-08T00:00:00Z",
        "strategy_id": 5,
        "credential_id": null,
        "symbol": "INCY",
        "order_intent_id": 47,
        "violation_code": "accountRisk.grossNotionalExceeded",
        "violation_message": "总名义超出限额",
        "action": "blocked",
        "source": "account_risk",
        "risk_snapshot_json": null,
        "counts": {"reject_count": 1}
      }
    ],
    "total": 1
  }
}
```

- **数据来源**：新表 `qd_risk_events`（或在既有 `strategy_runtime_events` 上扩展 `violation_code / risk_snapshot_json / order_intent_id` 列，方案评审时定）；关联 `pending_orders` / `qd_strategy_logs`。
- **字段口径**：`violation_code` 枚举对齐 `account_risk.py` 违规码；`source` 枚举 `account_risk / portfolio_gate / circuit_breaker / kill_switch / entry_guard / native_protection`；`action` 枚举 `blocked / reduced / closed / warned`。
- **空态口径**：无事件返回空数组，前端空态占位；**不得**从 `last_error` / `message` 文本中正则猜违规码；拦截计数与 `attempts`（下单重试）分开口径。

### 前端现状
风控告警/拦截历史区接 `/api/risk/alerts` 真实内存告警并按真实字段渲染；空数组走空态；持久化拒单事件区保持空态并标注 G1/G2/G3。

---

## C-REVIEW-01 亏损根因分类

### 现状
复盘报告 `metrics` 无亏损归因维度；`exit_reason_counts` 统计全部平仓事件的原因码，不区分盈亏，也不输出根因类别。

### 建议契约（待评审）
- **路径 / 方法**：随 `POST /api/strategies/review-report` 响应扩展 `metrics`（不新增写操作）。
- **请求参数**：沿用现有 `id / lookback_days / include_ai / language`。
- **响应字段（草案）**：

```json
{
  "metrics": {
    "loss_root_causes": [
      {
        "category": "stop_loss",
        "label": "止损触发",
        "count": 3,
        "total_loss_pnl": -42.5,
        "sample_trade_ids": [101, 102, 103]
      }
    ],
    "data_status": "completed_trades"
  }
}
```

- **分类枚举（草案）**：`stop_loss / signal_reversal / spread_slippage / news_gap / strategy_decay / other`；归类规则须在决策规则版本内冻结并可回溯到成交记录。
- **数据来源**：平仓成交（盈亏 + `close_reason`）+ 决策日志；样本不足返回 `data_status: "sample_small"`，仅作方向性参考。
- **空态口径**：字段缺失、样本不足或无亏损单 → 分类区 `--`，不按原因码臆造根因占比。

### 前端现状
「亏损根因分类」卡片固定 `--`，标注契约 C-REVIEW-01。

---

## C-REVIEW-02 止损触发统计

### 现状
无止损触发次数、追踪止损次数、保本次数的聚合字段；原因码族映射见 `app/utils/trade_close_reason.py`（`server_stop_loss / server_trailing_stop / *_equity_stop_loss / *_equity_trailing_stop` 等）。

### 建议契约（待评审）
- **路径 / 方法**：随复盘报告 `metrics` 扩展。
- **响应字段（草案）**：

```json
{
  "metrics": {
    "stop_loss_stats": {
      "stop_loss_count": 2,
      "trailing_stop_count": 1,
      "breakeven_count": 0,
      "avg_loss_on_stop": -12.3,
      "as_of": "2026-11-08T00:00:00Z"
    }
  }
}
```

- **口径**：止损族与止盈族分开计数；保本单单独归类；计数口径与 `exit_reason_counts` 可对账。
- **空态口径**：字段缺失或无平仓样本 → `--`；不把追踪止盈计入止损。

### 前端现状
「止损触发统计」卡片固定 `--`，标注契约 C-REVIEW-02。

---

## C-REVIEW-03 过早止盈统计

### 现状
复盘链路只看已成交记录与出场原因，不保留出场后 N 根 bar 的价格路径，也无最大有利 R（`max_favorable_r`）事后比对，无法识别「出场后行情继续奔跑」的过早止盈。

### 建议契约（待评审）
- **路径 / 方法**：随复盘报告 `metrics` 扩展（后端需补出场后行情比对，属新增计算，评审后排期）。
- **响应字段（草案）**：

```json
{
  "metrics": {
    "premature_tp_stats": {
      "premature_tp_count": 0,
      "avg_missed_r_after_exit": null,
      "sample": [
        {
          "trade_id": 101,
          "r_at_exit": 1.2,
          "max_favorable_r_after": 2.8,
          "bars_after_exit": 12
        }
      ]
    }
  }
}
```

- **口径**：「过早」阈值（如出场后最大有利 R 超出出场 R 若干倍）须在规则版本内冻结；R 分母用入场冻结 `entry_dist / atr0`（见 WIKI《跟踪止盈 / 让利润奔跑设计说明》2.1）。
- **空态口径**：字段缺失、样本不足或行情不可比对 → `--`；不凭主观印象标注过早止盈。

### 前端现状
「过早止盈统计」卡片固定 `--`，标注契约 C-REVIEW-03。

---

## C-LOG-01 日志中心 · 结构化风控事件分类

### 现状
日志中心现有三类：决策日志（`qd_strategy_logs`）、交易日志（`qd_strategy_trades`）、系统日志（前端内存 `debugLogs`）。风控拦截散落在决策日志文本与 `pending_orders.last_error` 文本，无独立分类可读。

### 建议契约（待评审，依赖 C-RISK-03 落地）
- **路径 / 方法**：复用 `GET /api/risk/events`（见 C-RISK-03），日志中心新增 `risk` 分类标签。
- **响应字段**：`event_id / ts / level / violation_code / message / strategy_id / symbol / order_intent_id / source / action`。
- **数据来源**：同 C-RISK-03；只读展示，不提供清空（持久化事件不可由前端删除）。
- **空态口径**：C-RISK-03 落地前，`risk` 分类固定空态，说明「后端无独立风控事件表、拒单原因未结构化（G1/G2/G3）」；不把决策日志里含「rejected/blocked」字样的文本过滤冒充风控事件流。

### 前端现状
日志中心已新增「风控事件」标签，固定空态与缺口说明；决策/交易/系统三类既有口径不变。

---

## 评审备注

1. 上述端点均为**只读聚合**；不改变下单、平仓、仓位与资金计算口径。
2. 任何限额/阈值字段必须来自分布校准与 config，禁止按 PnL 网格搜索（AGENTS.md 不变量 3、硬规则 8）。
3. 后端实现时须补单测与契约标记（`data_kind / data_status`）；前端渲染先判标记，非 `real` 一律空态。
4. 关联阻塞项：#107 共享风控 gate 复用三同步入口（触碰实盘链路，待拍板）；TABLE_SCHEMA TODO-A 风控事件结构化落库、TODO-B 拒单原因与拦截计数成列。
