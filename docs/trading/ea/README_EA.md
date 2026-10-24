# README_EA.md — MQL5 执行层 EA 骨架说明

> 版本：skeleton v0.1（2026-10-24）｜设计依据：`docs/trading/AI_ML_SYSTEM_DESIGN.md` 第⑥章（冻结）。
> 边界：本目录是**骨架设计与示例代码**，不入 `mt5/`；受管控的实盘执行代码后续经人工确认后放入 `mt5/`。
>
> **未验证声明：本环境无 MetaEditor / MetaTrader，EA 代码未经编译与实盘验证。**

---

## 1. 文件清单与结构

| 文件 | 职责 |
|---|---|
| `EA.mq5` | EA 主骨架：`OnInit / OnTick / OnTimer / OnTradeTransaction / OnDeinit` 事件驱动；从信号 JSONL 拉取 Python 信号；建市价单并附冻结 SL/TP；熔断与新闻窗口门控 |
| `trade_utils.mqh` | 交易工具库：`ReadSymbolSpecs` / `NormalizeLots` / `SafeOrderSend`（retcode 检查+指数退避重试）/ `MonotonicModifySL`（止损单调）/ `SafeClosePartial`（部分平仓）/ 新闻日历 / 熔断三态机 / JSONL 最小解析器 / retcode 映射 |
| `SIGNAL_PROTOCOL.md` | Python→EA 信号对接协议（JSONL 字段、单调序号、幂等键、ACK、时区、沙盒部署） |
| `README_EA.md` | 本文件 |

> 命名说明：冻结设计文档第⑥章曾列出 `XAUUSD_EA.mq5 / SIGNAL_CONTRACT.md / README.md` 占位名；本分片按任务范围落盘为 `EA.mq5 / SIGNAL_PROTOCOL.md / README_EA.md`，内容与设计第⑥章一一对应，未偏离。

```
EA.mq5（事件驱动）
├─ OnInit      SymbolInfo* 取规格 → 时区 sanity → 新闻日历 → 熔断初始化 → 载入幂等游标 → EventSetTimer(5s)
├─ OnTick      空实现（设计：不堵事件队列；intra-bar 不决策，硬规则5）
├─ OnTimer     ① 熔断三态机 ② ScanNewSignals() 拉新增行 ③ 止损单调管理钩子（骨架位）
├─ OnTradeTransaction  异步成交确认（DEAL_ADD 对账）
└─ OnDeinit    杀定时器 + 保存游标
```

## 2. 配置项（全部 `input` 化；风控阈值只允许来自 config）

| input | 默认 | 说明 |
|---|---|---|
| `InSignalDir` / `InSignalPrefix` / `InAckPrefix` | `Signals` / `xauusd_signal_` / `ack_` | 信号与回执文件位置（见 SIGNAL_PROTOCOL §6 沙盒约定） |
| `InTimerPeriodSec` | 5 | OnTimer 拉取周期（设计 5s，不堵队列） |
| `InStateFile` | `ea_last_seq.txt` | 幂等游标持久化 |
| `InServerOffsetHours` | 2.0 | 服务器−UTC（小时）；**必须与 Python `--tz` 同口径，禁止写死 UTC+2/+3**（硬规则6） |
| `InDstAuto` | false | DST 由人工核对后开启 |
| `InSymbol` / `InMagic` / `InSlippagePoints` | `XAUUSD` / `20261024` / 30 | 品种、EA magic、允许滑点（点） |
| `InNewsCsv` / `InNewsWindowMin` | `news_events.csv` / 15 | 新闻窗口冻结（±15min 默认，可配） |
| `InDailyMaxDDPct` | 0.03 | 当日权益熔断线（参照 3% 档；实际值由 CLEAN 分布校准后人工填入） |

**禁止事项**：点值、digits、最小/步长手数、合约规模、stops_level、filling mode 全部运行时经 `SymbolInfo*` 读取（`ReadSymbolSpecs`）；任何阈值不得硬编码进交易逻辑（AGENTS.md 硬规则8）。

## 3. 部署步骤（人工执行，本环境不做）

1. 将 `EA.mq5` 与 `trade_utils.mqh` 复制到终端 `MQL5\Experts\` 下某目录；在 MetaEditor 打开编译（**本环境未验证**）。
2. 确认终端「算法交易」总开关开启、品种 `XAUUSD` 可交易；`InMagic` 与部署 config 一致。
3. 按 `SIGNAL_PROTOCOL.md` §6 把 `experiments/signals/` 目录对接到 MT5 公共 Files 目录；放入 `news_events.csv`（UTC 时刻列表）。
4. 先在策略测试器 real-ticks 模式跑一段冒烟（G02：M5 必须 real ticks），再在模拟账户纸面验证一个完整交易日。
5. 人工核对 DST 切换日 `InServerOffsetHours` 与 Python `--tz`。

## 4. 与 AGENTS.md 硬规则的落点对照

| 硬规则 | 本骨架落点 |
|---|---|
| 4 止损单调 / atr0 冻结 | `MonotonicModifySL` 放宽即拒；`atr0/entry_dist/sl/lots` 字段只读不重算 |
| 5 intra-bar 不决策 | OnTick 空实现；信号只对应已收盘 bar；拉取走 OnTimer |
| 6 时区一致 | `InServerOffsetHours` input + OnInit 实测比对告警 |
| 7 异步返回检查+重试 | `SafeOrderSend` 读 `res.retcode`，10004/10020/10021/10012 指数退避重试；`PositionModify/ClosePartial` 复用同一通道 |
| 8 禁硬编码 | `ReadSymbolSpecs` 全量 SymbolInfo*；阈值全 input 化 |
| 9 禁静默吞错 | 每个失败分支打印 symbol/retcode/attempt/order 上下文；回执写失败显式告警 |

## 5. 限制与已知缺口

- `SafeOrderSend` 内重试用 `Sleep()` 退避（最坏 ≈1.4s/次调用），阻塞 OnTimer；若未来信号频率提高，应改为状态机异步重试。
- JSONL 解析器为最小实现（按键取值），不是完整 JSON 校验器；字段语义合法性靠 Python 侧与单测保证。
- 不内置追踪止损逻辑——方向骨架与移动止损决策在 Python 研究层，EA 只执行冻结结果（G05：风控模块与信号生成解耦）。
- ZeroMQ 备选通道未实现；文件通道的 Windows 共享写语义未实测。

## 6. 未验证项清单（实现报告必须保留）

1. **未验证**：MT5 编译（无 MetaEditor 环境）。
2. **未验证**：实盘执行——retcode 重试链路、幂等游标、滑点、时区对拍、ACK 对账。
3. **未验证**：经纪商差异——点差、合约规格、DST 表、stops_level、filling mode。
4. **未验证**：文件通道并发读写（Python 写 / EA 读同目录）在真实终端下的锁行为。
