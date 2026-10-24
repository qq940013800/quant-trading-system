# SIGNAL_PROTOCOL.md — Python → MQL5 EA 信号对接协议

> 冻结依据：`docs/trading/AI_ML_SYSTEM_DESIGN.md` 第⑥章「信号对接方式」。
> 通道：**文件 JSONL（推荐）**；ZeroMQ 为备选通道（骨架未实现，接口字段不变）。
> 版本：v1（2026-10-24，随 design-frozen v1）。任何字段增删须先改设计文档并重新冻结。

---

## 1. 总览

```
Python 研究层（core.audit / core.risk 产出 Decision 快照）
   │  写 experiments/signals/xauusd_signal_YYYYMMDD.jsonl（追加，单行一条 JSON）
   ▼  （共享文件目录：MT5 沙盒 Files/ 或公共目录，见 §6 部署）
MQL5 EA（docs/trading/ea/EA.mq5）
   │  OnTimer 每 5s 拉取新增行 → 校验单调序号/幂等键 → SafeOrderSend
   ▼
   写 experiments/signals/ack_YYYYMMDD.jsonl（追加，单行一条 JSON 回执）
```

设计原则（对应 AGENTS.md 三条不变量与硬规则）：
- **单向冻结**：`atr0 / entry_dist / sl_price / tp_price / lots` 全部由 Python 侧冻结后下发；**EA 绝不重算**（硬规则4：R 倍数用入场冻结的 atr0/entryDist）。
- **幂等**：单调序号 + `signal_id` 双保险，EA 重启/重复投递不会重复下单。
- **不堵队列**：信号拉取只发生在 `OnTimer(5s)`，`OnTick` 零工作（MQL5 事件队列对积压 NewTick 直接丢弃）。
- **可审计**：每笔信号无论接受/拒绝都有 ACK；拒绝原因即 `status` 字段。

---

## 2. 信号文件：`xauusd_signal_YYYYMMDD.jsonl`

- 路径：`experiments/signals/xauusd_signal_YYYYMMDD.jsonl`（YYYYMMDD 取 **UTC** 日期）。
- 格式：UTF-8、LF、每行一条 JSON 对象，追加写；禁止改写历史行。
- 编码：UTF-8（EA 侧 `FileOpen(..., CP_UTF8)` 读取）。

### 2.1 字段表

| 字段 | 类型 | 语义 | 冻结/校验要求 |
|---|---|---|---|
| `seq` | int | **单调递增序号**，跨进程不重置（= Python 侧 `Decision.decision_id`） | EA 只处理 `seq > 已处理游标`；`<=` 一律跳过 |
| `symbol` | string | 品种，固定 `"XAUUSD"` | 与 `InSymbol` input 不一致 → `REJECTED_SYMBOL` |
| `signal_id` | string | **幂等键**：`f"{symbol}_{bar_ts_utc}_{expert}_{dir}"`（冻结，不可为空） | 与 `seq` 双重去重依据 |
| `direction` | int | `+1` 多 / `-1` 空 | 非 ±1 → 行非法，跳过 |
| `atr0` | float | 入场冻结 ATR（计价货币） | EA 只读不重算（硬规则4） |
| `entry_dist` | float | 入场到止损距离（默认 2×atr0，CLEAN 分布校准） | EA 只读不重算 |
| `sl_price` | float | 冻结止损价 | EA 另做经纪商 stops_level 距离校验 |
| `tp_price` | float\|null | 止盈价；`null` 表示不下止盈 | `null`/缺失 → 不下 TP |
| `lots` | float | 最终手数（Python `target_lots` 冻结输出） | EA 只按 `lot_step` 向下取整并夹 `[lot_min,lot_max]`，不重算风险 |
| `ts_utc` | int(unix) | 触发依据 bar 的收盘 UTC 时刻（`bar.close`） | 用于审计与时间对齐；EA 不据此 intra-bar 决策（硬规则5） |
| `decision_rule_version` | string | 冻结的决策规则版本 | 原样回写 ACK 上下文，便于审计对账 |

### 2.2 示例行

```json
{"seq":1042,"symbol":"XAUUSD","signal_id":"XAUUSD_2026-10-24T08:35:00Z_trend_breakout_+1","direction":1,"price_ref":3342.50,"atr0":4.82,"entry_dist":9.64,"sl_price":3332.86,"tp_price":3352.14,"lots":0.12,"ts_utc":1792840500,"decision_rule_version":"v1-frozen-20261024"}
```

> 注：`price_ref` 等 Python 侧内部字段可一并下发用于日志；EA 只按 §2.1 表消费，未知字段忽略。

---

## 3. 回执文件：`ack_YYYYMMDD.jsonl`

- 路径：`experiments/signals/ack_YYYYMMDD.jsonl`（同目录，UTC 日期）。
- 每行一条：

```json
{"signal_id":"XAUUSD_2026-10-24T08:35:00Z_trend_breakout_+1","retcode":10009,"retcode_name":"DONE","fill_price":3342.61,"fill_time_server":1792840541,"status":"FILLED"}
```

| 字段 | 语义 |
|---|---|
| `signal_id` | 与信号行一一对应（幂等键） |
| `retcode` / `retcode_name` | 经纪商返回码（10008 PLACED / 10009 DONE / 10010 DONE_PARTIAL …）；拒绝类为 `0` |
| `fill_price` | 成交价（拒绝时为参考价/0） |
| `fill_time_server` | 服务器时间（unix），审计用 |
| `status` | `FILLED` / `PLACED` / `REJECTED_SYMBOL` / `REJECTED_NEWS_WINDOW` / `REJECTED_CIRCUIT_BREAKER` / `REJECTED_LOTS` / `REJECTED_STOPS_LEVEL` / `ERROR` |

**推进游标的规则**：信号无论被接受还是拒绝，EA 都把 `g_last_seq` 推进到该 `seq`——拒绝已落 ACK，不重复投递。

---

## 4. 幂等与重复投递

1. EA 持久化游标 `ea_last_seq.txt`（MT5 Files 沙盒），重启后从 `max(已处理, 文件内最大)` 继续。
2. 同一 `signal_id` 重复出现（Python 重发/文件重放）：`seq <= 游标` 直接跳过，不重复下单。
3. 网络/退避重试发生在 `SafeOrderSend` 内部（同一请求重试，不是同一信号重复请求）。
4. 设计上 EA 不内置追踪止损逻辑；移动止损作为**新信号行**下发，经 `MonotonicModifySL` 单调校验后才允许执行。

## 5. 时区一致性约定（硬规则6）

- Python 侧所有时间戳为 **timezone-aware UTC**；信号 `ts_utc` 与文件日期 `YYYYMMDD` 一律 UTC。
- EA 的 `InServerOffsetHours`（默认 EET=2.0）必须与 Python 端 `--tz` 同一口径；DST 切换日人工核对。
- EA 在 `OnInit` 自动测量 `TimeCurrent()-TimeGMT()` 与配置值比对，偏差 >0.5h 打印警告（不自动改值——禁止写死 UTC+2/+3）。
- 新闻日历 `news_events.csv` 中事件时刻按 **UTC** 语义解释；冻结窗口 ±`InNewsWindowMin`（默认 15min）。

## 6. 文件部署约定（沙盒边界）

- MQL5 文件 API 默认受限在终端数据目录 `MQL5\Files\`（或公共目录 `...\MetaQuotes\Terminal\Common\Files\`，`FILE_COMMON` 标志）。
- 部署时二选一：
  1. **推荐**：Python 侧把信号/回执目录映射到 MT5 **公共 Files** 目录，双方在同一物理目录读写；`InSignalDir` 填相对该目录的子路径。
  2. 或在终端沙盒内做目录同步（mklink / 共享盘）。
- 信号文件生成与 EA 消费必须通过同一目录；**不要**让 Python 直接写 `C:\Program Files\...` 安装目录（权限与升级问题）。

## 7. 失败与降级语义

| 情形 | EA 行为 |
|---|---|
| 信号文件不存在（盘前） | 静默跳过，不告警 |
| 单行 JSON 非法/字段缺失 | 打印整行上下文，跳过该行，不推进游标到该行之后？—— 注：按实现，非法行不消费游标；合法行才推进 |
| 新闻窗口内新信号 | `REJECTED_NEWS_WINDOW`，推进游标 |
| 熔断态 | `REJECTED_CIRCUIT_BREAKER`，推进游标 |
| `SafeOrderSend` 不可重试失败 | `ERROR` 回执，`OnTradeTransaction` 人工对账 |
| `SafeOrderSend` 退避重试耗尽 | 同上 `ERROR`；日志含 attempt/backoff 上下文 |

> 禁止 EA 侧任何"没收到回执就重发"的行为——重发是 Python 侧的职责（按 `ack` 缺失补发同 `signal_id`，EA 幂等吸收）。

---

## 8. 未验证项（随交付声明）

- **未验证**：MT5 编译与实盘执行（retcode 重试、幂等、滑点、时区对拍）。
- **未验证**：经纪商差异（点差、合约规格、DST 表、stops_level、filling mode）。
- 文件锁/并发写边界（Python 写、EA 读同文件在 Windows 下的共享语义）未在真实 MT5 环境验证。
