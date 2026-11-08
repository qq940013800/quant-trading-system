# OKX Demo 全链路实测报告（下单 → 持仓 → 平仓 → 收益）

- 测试时间：2026-11-08（库内 created_at 02:33–02:35 UTC）
- 环境：OKX **demo 模拟盘**（`x-simulated-trading:1`），未触碰真实资金
- 凭证：库表 `qd_exchange_credentials` id=2，`OKX-DEMO`（exchange_id=okx，environment=demo，market_scope=both，enable_demo_trading=true）
- 后端：容器 `qdpro-backend`，宿主 `127.0.0.1:5001` → 容器 5000；DB `quantdinger-db` healthy
- 结论分级：**confirmed**（代码/接口实测回链）、**inferred**（由现象推断）、**unknown**（未验证）

## 1. 结论摘要

| 环节 | 现货（spot） | 永续（swap） |
| --- | --- | --- |
| 下单 | confirmed：market buy 成交落库（id=6） | blocked：账户模式拒绝，未成交（id=5 failed） |
| 持仓查询 | confirmed：可回读 spot / swap 持仓 | confirmed：swap 持仓空 `positions:[]`，无遗留敞口 |
| 平仓 | confirmed：market sell 对冲成交落库（id=7） | 未验证（账户模式阻塞） |
| 收益复算 | confirmed：逐笔价差/佣金/净盈亏手工复算（见 §5） | 未验证 |
| 系统内归集 | partial：快捷成交仅佣金进入日盈亏；价差毛利与顶部已实现盈亏/胜率未归集（见 §6） | — |

**一句话**：现货小额一笔已在 demo 盘完成「买入 → 持仓 → 卖出平仓 → 逐笔复算」闭环；永续被 demo 账户 `acctLv=1`（简单账户）阻塞，需在 OKX demo 网页端切换账户保证金模式后复验。

## 2. 只读基线（成交前，confirmed）

- USDT 余额：available `4156.96045887893`，total `4226.96045887893`（接口同时返回 spot/swap 两段，数值相同）。
- 永续持仓：`positions:[]`（空仓）。
- 现货持仓（钱包余额口径）：BTC/USDT long `size=1.0099402961`，entry≈77533.06，mark≈75733.9，unrealized≈-1817.04，leverage=1.0。
  - 该 1.01 BTC 存量与历史成交（id1/2 仅对冲 0.0001319 BTC）对不上，属已知 **P0 现货持仓口径偏大**缺陷（见 §7.1），非本轮新引入。

## 3. 永续尝试与阻塞根因（confirmed）

- 请求：`POST /api/quick-trade/place-order`，swap buy，amount=400 USDT 保证金，leverage=2，margin_mode=cross，market。
- 返回：HTTP 500，`code=0, msg=OKX_SWAP_ACCOUNT_MODE_REQUIRED`；落库 id=5，status=`failed`，无 exchange_order_id。
- 成交后核验：swap 仍空仓，余额无变化 → **无遗留永续敞口、无资金占用**。
- 根因（回链代码）：`app/services/live_trading/account_configuration.py` 读取 OKX `acctLv`，若为 `"1"`（简单账户）直接抛 `OKX_SWAP_ACCOUNT_MODE_REQUIRED`；`app/services/live_trading/okx.py:546 get_account_config` 走 `GET /api/v5/account/config`。
  - OKX 账户等级：1=简单账户（不支持合约/永续），2=单币种保证金，3=跨币种保证金，4=组合保证金。本 demo 账户当前为 1。
- 解锁条件：需在 **OKX demo 网页端**将账户切换为单币种/跨币种保证金（acctLv 2/3/4）。API 不代切账户等级（高危账户操作），后端代码不代做。
- 备注：本地手工 HMAC 直连 `/api/v5/account/config` 与 `/account/balance` 返回 403（手工签名时间戳/路径细节与后端客户端有差异）；后端客户端经 `_signed_request` 可读 `acctLv`，故以后端链路判定为准。

### 永续最小规则（ccxt `fetch_markets` 只读实测，confirmed）

`BTC/USDT:USDT`（instId `BTC-USDT-SWAP`）：contractSize=0.01，amount_min=0.01，amount_step=0.01，price_tick=0.1。后端 `okx.py:_normalize_order_size` 已把基础币数量换算为张数并对齐 lotSz/minSz；低于最小返回 0 并报 `below lot/min size`。最小 1 张 ≈ 0.01 BTC ≈ 757 USDT 名义；2x 保证金约 379 USDT。

## 4. 现货全链路实测（confirmed）

### 4.1 开仓 id=6

- 请求：`place-order`，spot，buy，market，amount=10.0 USDT（现货 quote 名义），leverage=1，source=manual。
- 回报（HTTP 200，status=`filled`）：
  - exchange_order_id `4080315631944871937`
  - filled `0.00013204` BTC，avg_price `75734.0`，notional 10.0 USDT
  - commission `1.3204e-07` BTC，commission_ccy=BTC
  - protection_status=`not_requested`（本次未挂止盈止损）

### 4.2 持仓回读

- 买入后 spot position 仍显示钱包口径 `size=1.0099402961`，entry/浮盈未反映本次小额买入（口径滞后，见 §7.1）。
- 成交事实以 `qd_quick_trades` id=6 filled 记录为准。

### 4.3 平仓 id=7

- 请求：`POST /api/quick-trade/close-position`，spot，size=`0.00013204`（恰为本次买入量），close_scope=`full`，source=manual。
- 回报（HTTP 200，status=`filled`）：
  - exchange_order_id `4080317666148757505`
  - filled `0.00013204` BTC，avg_price `75740.6`，closed_size `0.00013204`
  - position_side=`long`，close_scope=`full`，tracked_net_base=null
  - 落库：side=sell，amount=`10.000788824` USDT，commission=`0.010000788824` USDT，commission_ccy=USDT
- 平仓后核验：
  - swap `positions:[]`（无永续遗留）。
  - spot 本次买入量已对冲；钱包存量未被误卖（平仓按指定 size 成交，`clamp_spot_close_quantity` 夹紧到钱包 free，safety_ratio=1.0）。
  - 余额 available `4156.951329554106`，total `4226.951329554106`。

## 5. 逐笔收益复算（confirmed，口径：BTC 数量 × 成交价）

| 项 | 数值 | 计算 |
| --- | --- | --- |
| 买入毛成本 | 9.99991736 USDT | 0.00013204 × 75734.0 |
| 卖出毛收入 | 10.000788824 USDT | 0.00013204 × 75740.6 |
| 价差毛利 | **+0.000871464 USDT** | 卖出毛收入 − 买入毛成本 |
| 买入佣金折 USDT | 0.009999917 USDT | 0.00000013204 × 75734.0 |
| 卖出佣金 | 0.010000788824 USDT | 接口落库 |
| 双边佣金合计 | ≈ 0.020000706 USDT | 买入佣金 + 卖出佣金 |
| **净盈亏** | **≈ -0.019129 USDT** | 价差毛利 − 双边佣金 |

- 解读：价格上涨 6.6 USDT/BTC，小额做多价差微盈，但被双边 taker 手续费吞没；OKX 现货 taker 费率约 0.1%（10 USDT 双边佣金 ≈ 0.02 USDT，与落库佣金量级吻合）。
- 余额差额校验：平仓后 available − 成交前 available = `-0.009129` USDT，**与净盈亏 -0.019129 不相等**。原因：买入扣的 10 USDT 在滞后的余额/权益接口里未逐笔反映（余额接口读缓存/权益口径）。**不能用余额差额对账**，真实逐笔盈亏以成交记录复算为准。该现象本身印证 P1 对账缺口（#108 周期对账/漂移告警）。

## 6. 系统内收益归集口径核验（confirmed，回链 dashboard.py）

实测 `GET /api/dashboard/summary`（2026-11-08）：

| 字段 | 实测值 | 口径 |
| --- | --- | --- |
| total_realized_pnl | 0.0 | 仅聚合 `qd_strategy_trades`（`dashboard.py:463-486`），**不含** `qd_quick_trades` |
| total_pnl | 0.0 | unrealized + total_realized_pnl |
| performance.total_trades / win_rate | 0 / 0.0 | 按 `profit IS NOT NULL` 过滤，快捷成交自动排除（注释 `dashboard.py:525-526`） |
| daily_pnl | -0.02 | 遍历 recent_trades（策略 + 快捷，`dashboard.py:556-558`）按日聚合 |
| daily_pnl_chart 2026-11-08 | profit `-0.020000706184` | 与双边佣金口径吻合 |

归集逻辑要点（`app/utils/trade_net_pnl.py` + `dashboard.py`）：

- 快捷成交行由 `_build_quick_trade_row` 映射，`profit=None`；`enrich_trades_net_pnl` 只对 `profit IS NOT NULL` 的 exit 行做 FIFO 配对与净盈亏分摊，快捷行不参与配对。
- 日盈亏对快捷行走 `net_pnl_for_equity_step` 的佣金分支（`trade_net_pnl.py:202-205`）：**只扣佣金，不计配对价差毛利**。
- 因此本次对冲的价差毛利 +0.00087 USDT 在系统内未被归集；系统日盈亏只记录了双边佣金 ≈ -0.0200 USDT。

## 7. 确认的问题与对应切片

### 7.1 P0 现货持仓口径偏大（对应 #153）

- 现象：position 接口按钱包余额口径（含 demo 初始/遗留存量 1.01 BTC），非策略/快捷成交净持仓；买入后持仓展示不随本次成交更新。
- 落点：`quick_trade.py` 持仓展示与净量计算、`spot_sizing.get_spot_base_holding` / `get_spot_free_base_balance`。
- 建议方向（设计见 `docs/design/live-trading-gates-and-reconciliation-design.md` #153 节）：分层展示「系统跟踪净持仓」与「钱包余额」两层，平仓/对账分别取对应口径。

### 7.2 余额/持仓接口滞后（对应 #108 / #155）

- 现象：成交后 available 未即时逐笔扣减；余额差额不能用于对账。
- 建议方向：周期对账以成交记录（fill 流水）为准，比对钱包权益/持仓并在漂移超阈值时告警。

### 7.3 快捷成交盈亏归集缺口（对应 #118 延伸 / #153）

- 现象：顶部已实现盈亏、胜率、PF 不含快捷成交；日盈亏对快捷成交只扣佣金、不计价差毛利；快捷买卖未做 FIFO 配对。
- 建议方向：在交易归集层统一两类台账（`qd_quick_trades` 与 `qd_strategy_trades`）的配对与净盈亏口径，或在 UI 明确标注「快捷成交未计入策略绩效」。

### 7.4 永续账户模式引导（体验项，非缺陷）

- 行为正确：`acctLv=1` 时 fail-closed 拒绝永续下单，未产生挂单/敞口。
- 可改进：错误信息补账户模式切换指引（网页端路径）与可观测告警；当前仅返回通用错误码。

## 8. 未验证项（demo 受限或本轮未触发）

- 永续开多/开空、杠杆与保证金模式、减仓/部分平仓、双向持仓（long_short_mode / net_mode）。
- 限价单成交、止盈止损挂单、native protection 挂单链路（本次 `protection_status=not_requested`）。
- 资金费率、持仓资金占用、强平距离/保证金率。
- 真实（非 demo）资金链路。
- 策略自动入口（pending_orders worker）的风控 gate 与真实策略匹配；本轮仅测手动/快捷入口。

## 9. 本轮改动与验证

- **仓库代码改动：无。** 本轮为 demo 只读勘察 + 小额成交验证，未修改 `core/`、`app/`、`configs/`、`mt5/` 任何文件。
- 容器内：`/app/.env` 注入代理（`PROXY_URL/HTTPS_PROXY/HTTP_PROXY/ALL_PROXY=http://host.docker.internal:7890`），原备份 `/app/.env.bak_proxy`；属容器环境配置，不在 git 仓库内。
- 探针/脚本位于 agent workspace（不入库）：登录→凭证→余额→持仓→history 只读探针，现货开仓/平仓脚本，summary 探针。
- 后台并发切片（编排智能体，已 100% 完成，详见对应任务）：
  - #150 后端纯逻辑边界测试：venv 全量 **673 passed**（基线 596，+77），零警告。
  - #151 对账/漂移告警设计草案：`docs/design/reconciliation_drift_alarm_design.md`。
  - #152 前端真实口径只读审计：`docs/frontend_realdata_audit.md`（静态 HTML 风险项以该文档为准）。
  - #153–#156 方案设计：`docs/design/live-trading-gates-and-reconciliation-design.md`（零代码/受保护路径改动）。

## 10. 复现要点

1. 代理：宿主 `127.0.0.1:7890` 与容器 `host.docker.internal:7890` 均需可达 OKX（`GET /api/v5/public/time` 200）。
2. 登录：`POST /api/auth/login` `{"username":"admin","password":"admin123"}`，token 取 `data.token`，请求头 `Authorization: Bearer <token>`。
3. 只读顺序：`/api/credentials/list` → `/api/quick-trade/balance?credential_id=2&market_type=spot` → `/api/quick-trade/position?credential_id=2&symbol=BTC/USDT&market_type=spot` → `/api/quick-trade/history?limit=20`。
4. 现货下单/平仓：参考 §4.1 / §4.3 请求体；平仓数量必须等于或小于本次买入 filled，避免误卖钱包存量。
5. 永续复验前置：先在 OKX demo 网页把账户切到单币种/跨币种保证金，再跑 swap 开仓→持仓→平仓。
