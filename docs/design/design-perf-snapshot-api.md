# 方案 1：逐策略绩效快照接口设计（`/strategies/perf-snapshot`）

> 状态：**待评审草稿**，不含生产代码。
> 背景：回测页"策略绩效对比表"当前为静态演示样例；后端 `/api/strategies` 顶层只返回 `id/strategy_name/status/symbol/timeframe/initial_capital/current_equity/total_pnl/today_pnl/today_pnl_estimated/runtime_health`，**缺少**逐策略的夏普、最大回撤、胜率、盈亏比、年化、交易数；组合级绩效仅在 `dashboard` 的 `performance` 聚合，不能横向对比单策略。

## 1. 现状缺口（已勘察）

| 数据项 | `/api/strategies` 顶层 | 回测 history 行（`/api/backtest/history`） | 组合级 `dashboard.performance` |
|---|---|---|---|
| 总收益 | `total_pnl`（净盈亏，非收益率） | `total_return`（0–100 百分数） | `win_rate/profit_factor/max_drawdown/sharpe` |
| 夏普 | 无 | `sharpe`（多数行为 null） | 组合级 |
| 最大回撤 | 无 | `max_drawdown`（负数百分数，多数 null） | 组合级 |
| 胜率 | 无 | `win_rate`（0–100，多数 null） | 组合级 |
| 盈亏比 | 无 | `profit_factor`（多数为 0） | 组合级 |
| 交易数 | 无 | `total_trades`（多数 null） | 无 |
| 年化 | 无 | 无 | 无 |

> 实测：history id=9 一条字段完整（sharpe 0.2527、max_drawdown -32.915、win_rate 0.0、total_trades 58、profit_factor 0）；id=2–7 多为 `result_status=unknown`、指标全 null；id=8 `no_signals` 全 0。**直接按 history 聚合会把 null/0 误当真实绩效。**

## 2. 目标

为前端"逐策略横向对比表"提供**口径明确、缺失即 `--`** 的逐策略绩效快照；不编造指标，不把回测样本外指标与实盘运行指标混为一谈。

## 3. 接口草案

### 3.1 路径与方法
- `GET /api/strategies/perf-snapshot`（挂 `strategy_blp`，前缀 `/api`，沿用现有蓝图注册方式）
- 鉴权：复用现有 Bearer token 中间件；按 `user_id` 隔离。

### 3.2 查询参数（可选）
| 参数 | 类型 | 说明 |
|---|---|---|
| `strategy_id` | string | 单策略快照；不传则返回当前用户全部策略 |
| `window` | enum | `live`（实盘运行期）/ `backtest`（最近一次完整回测）/ `both`（默认） |

### 3.3 响应结构（草案）

```json
{
  "code": 1,
  "data": [
    {
      "strategy_id": "1",
      "strategy_name": "供需区吞没",
      "symbol": "BTC/USDT",
      "timeframe": "1d",
      "window": "backtest",
      "as_of": "2026-09-17T00:00:00Z",
      "metrics": {
        "total_return": 30.12,
        "annualized_return": null,
        "sharpe": 0.25,
        "max_drawdown": -32.92,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "total_trades": 58
      },
      "data_status": "completed_trades",
      "note": null
    }
  ]
}
```

### 3.4 字段口径约定（必须在接口层固化）

| 字段 | 口径 | 缺失处理 |
|---|---|---|
| `total_return` | 百分数，回测/实盘区间收益率；与 history `total_return` 同口径 | `null` → 前端 `--`，禁止填 0 |
| `annualized_return` | 年化收益；**口径未对齐前返回 `null`**（见未决项 R1） | `null` → `--` |
| `sharpe` | 风险调整后收益；**日收益年化口径**（与回测引擎一致），不使用仪表盘逐笔未年化口径 | `null` → `--` |
| `max_drawdown` | 负数百分数，恒带负号；取区间内峰谷最大回撤 | `null` → `--` |
| `win_rate` | 0–100 百分数；`no_signals`/`unknown` 不强行算 0 | `null` → `--` |
| `profit_factor` | 总盈利/总亏损；无亏损或无成交时为 `null`（不写 0） | `null` → `--` |
| `total_trades` | 已成交笔数；未成交为 0 还是 `null` 需对齐（建议：无成交 `0`，无数据 `null`） | 区分处理 |
| `data_status` | `completed_trades` / `no_signals` / `unknown` / `live`；前端据此区分"真实 0"与"无数据" | — |

## 4. 数据来源与计算路径（候选，待评审）

### 路线 A：回测快照聚合（轻量，先落地）
- 从 `qd_backtest_history` 按 `strategy_id` 取最近一条 `result_status=completed_trades` 记录，映射上表字段。
- 优点：复用已有 history 字段，改动小；缺点：只反映最近一次回测，非实盘运行绩效；多数历史记录字段 null。

### 路线 B：实盘运行期绩效聚合（重，后续）
- 基于 `qd_quick_trades` 成交记录按策略聚合区间收益、胜率、盈亏比、交易数；夏普/回撤需日级权益序列。
- 优点：反映真实运行；缺点：当前成交样本极少（demo 两笔），且需日权益序列落库；触及绩效计算口径，需先对齐 R1/R2。

### 路线 C：策略运行时快照（复用 runtime 服务）
- 复用 `strategy_v2/runtime.py` 已有的 `total_return/max_drawdown/sharpe_ratio/win_rate` 计算方法，按策略输出。
- 优点：计算逻辑集中；缺点：需确认这些方法当前是否对实盘策略实例可用、样本是否充分。

## 5. 未决项（评审拍板）

- **R1 年化口径**：年化收益按交易日还是自然日？无完整年度样本时是否返回 `null`？
- **R2 夏普口径统一**：仪表盘逐笔净盈亏（未年化）与回测日收益年化两套是否统一为日收益年化；统一前快照接口夏普只取回测口径。
- **R3 实盘 vs 回测并列**：对比表是否同时展示两列（实盘运行期 / 最近回测），还是只展示其一。
- **R4 样本门槛**：成交笔数低于阈值（如 <10）时，指标是否标注"样本不足"而非直接展示。

## 6. 验收标准

1. 单策略与全量两种调用均返回结构化快照；`null` 字段前端渲染 `--`，不出现编造数字。
2. `data_status` 能区分"真实 0"与"无数据"，前端不把 `no_signals` 当 0 胜率。
3. 指标口径与回测引擎一致；年化/夏普口径在文档与接口注释中写明。
4. 不修改交易路由、风控 gate、下单/平仓、资金计算逻辑；新增逻辑附后端单测（黄金集断言不放宽）。

## 7. 风险与未验证

- 当前成交样本与历史回测完整度有限，路线 B 上线前需确认数据充分性。
- 本方案未在后端落地；字段名/路径需在实现前与现有蓝图注册、服务层方法签名复核。
