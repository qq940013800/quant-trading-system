# Demo 冒烟：用模拟盘替代实盘验证

## 为什么有这条入口

实盘冒烟要动真钱，且失败成本不可逆。OKX 提供模拟盘（`x-simulated-trading: 1`），
账户、下单、撤单、持仓的接口行为与实盘一致，因此**验证一律先在 demo 上做完**，
实盘只做最后一步确认。

`scripts/demo_trading_smoke.py` 是这条路径的唯一入口。它有一条硬规则：

> 凭据 `environment` 不在 `demo` / `testnet` 时，任何步骤都不执行，直接 `DEMO_SMOKE_REQUIRES_SIMULATED_CREDENTIAL` 退出（退出码 2）。

即：**实盘凭据进不来**。这不是提示，是前置拒绝——把 `--allow-orders` 加在 live 凭据上也不会下单。

## 凭据来源

脚本自己从 `qd_exchange_credentials` 读加密配置，用 `app.utils.credential_crypto.decrypt_credential_blob`
在内存中解密，不落盘、不打印。输出里的 key/secret/passphrase 只保留前 2 字符和长度（`af***len36`）。

`DATABASE_URL` 的 host 是 compose 服务名（`postgres`），宿主机解析不到，所以脚本要在后端容器里跑：

```bash
docker cp backend_api_python/scripts/demo_trading_smoke.py qdpro-backend:/app/scripts/demo_trading_smoke.py
```

镜像不带 bind mount，改完脚本必须重新 `docker cp` 或重建镜像，否则容器里还是旧副本。

## 用法

只读（默认，不下单）：

```bash
docker exec qdpro-backend python scripts/demo_trading_smoke.py --credential-id 2 --market spot --symbol BTC/USDT
docker exec qdpro-backend python scripts/demo_trading_smoke.py --credential-id 2 --market swap --symbol BTC/USDT
```

带下单往返（post-only 限价买单 → 查状态 → 撤单 → 复查挂单为空），双重闸门必须同时满足：

- 命令行 `--allow-orders`
- 环境变量 `DEMO_SMOKE_ALLOW_ORDERS=1`

```bash
docker exec -e DEMO_SMOKE_ALLOW_ORDERS=1 qdpro-backend python scripts/demo_trading_smoke.py \
  --credential-id 2 --market spot --symbol BTC/USDT \
  --allow-orders --limit-price 50000 --limit-quantity 0.0001 --max-usdt 5
```

`--max-usdt` 是本地名义额上限（默认 5），超过直接判 FAIL 且不下单。价格取远离盘口的价位，
post-only 保证只做 maker，正常情况下瞬时不会成交。

### 按交易所最小名义额下单

`--min-notional` 不再手填数量，而是从交易所公开合约信息推最小可下单数量：

`qty = ceil( max(交易所最小名义额, minSz * 单价 * ctVal) / (lotSz * 单价 * ctVal) )`（现货 `ctVal=1`）

推导结果会打印成 `min_notional` 步骤，例如 BTC-USDT 在 `price=50000` 时
`minSz=0.00001 lotSz=0.00000001 → qty=2e-05 notional=1.00000000`。

```bash
docker exec -e DEMO_SMOKE_ALLOW_ORDERS=1 qdpro-backend python scripts/demo_trading_smoke.py \
  --credential-id 2 --market spot --symbol BTC/USDT \
  --allow-orders --min-notional --limit-price 50000 --max-usdt 5
```

## 最小下单量：实测边界

OKX 现货的最小下单量不是 instrument 里的 `minSz`，而是**交易所级最小名义额**，且不写在合约信息里。
2026-11-19 在同一 demo 账户上用同一 `price=50000` 逐点逼近：

| 名义额（USDT） | 结果 |
|---|---|
| 0.50（= minSz 0.00001 × 50000） | `sCode 51020` 拒 |
| 0.61 | `sCode 51020` 拒 |
| 0.99 | `sCode 51020` 拒 |
| 1.00 | 下单成功 → 撤销成功 |
| 4.99 / 5.00 | 成功（此前误记为“最小 5 USDT”，已更正） |

结论：**OKX 现货最小名义额 = 1 USDT**，写入脚本常量 `EXCHANGE_MIN_NOTIONAL_USDT = {"okx": 1.0}`。
换交易所需要重新实测，不能直接套用。

合约侧换算：`sz` 是张数，1 张 = `ctVal` 个币。BTC-USDT-SWAP `minSz=0.01, lotSz=0.01, ctVal=0.01`，
所以在 64000 价位最小一档 `0.01 张 = 0.0001 BTC ≈ 6.4 USDT` 名义额，高于 1 USDT 全局下限，
此时 `minSz` 才是约束项。

## 步骤与判据

| 步骤 | 判据 |
|---|---|
| `credential_environment` | `environment` ∈ {demo, testnet} |
| `create_client` | 适配器可构造；输出掩码后的配置 |
| `simulated_header` | 客户端实际发出的 `x-simulated-trading` / `PAPTRADING` 为 `1` |
| `ticker` | 有 `last` |
| `spot_wallet` / `position_long|short` | 余额或持仓可读 |
| `min_notional` | 仅 `--min-notional`：由 minSz/lotSz/ctVal 与交易所最小名义额推最小数量；元数据缺失或无法推导判 FAIL |
| `swap_account_mode` | 仅 swap：`acctLv>=2` PASS；`acctLv=1` 只读记 WARN、要求下单记 FAIL 且不发单 |
| `limit_roundtrip` | 本地名义额闸门通过 → 下单 → 查状态 → 撤单；交易所拒单记 FAIL（不再中断）；撤单成功后不重复撤 |
| `pending_orders` | 结束后 `orders-pending` 为 0；适配器无该能力则 SKIP（不冒充通过） |

退出码：0 全通过，1 有 FAIL，2 凭据/前置拒绝。

## 2026-11-19 实测结果（OKX demo，credential id=2）

```
PASS credential_environment   environment=demo
PASS create_client            OkxClient {... 'environment': 'demo', 'enable_demo_trading': True}
PASS simulated_header         value=1
PASS ticker                   last=63929.2
PASS spot_wallet              rows=4
PASS limit_roundtrip          notional=5.00000000 order=4113653926560804865 status=open filled=0.0 avg=0.0
PASS pending_orders           open=0
```

swap 只读同样 PASS（`position_long=0.0`、`position_short=0.0`）。

按最小名义额（`--min-notional --limit-price 50000`）：

```
PASS min_notional             minSz=0.00001 lotSz=0.00000001 ctVal=- qty=2e-05 notional=1.00000000
PASS limit_roundtrip          notional=1.00000000 order=4113714637131493377 status=open filled=0.0 avg=0.0
PASS pending_orders           open=0
```

swap 要求下单且 `acctLv=1`：

```
FAIL swap_account_mode        acctLv=1 posMode=net_mode — ... upgrade the demo account in the OKX demo web/app first
SKIP limit_roundtrip          blocked by swap_account_mode; no order was sent
```

## 已知边界（未验证 / 未覆盖）

- **合约（swap）被账户模式阻塞**：demo 账户 `acctLv=1`（简单/现货模式），下单路径在
  `account_configuration.py:137` fail-closed 抛 `OKX_SWAP_ACCOUNT_MODE_REQUIRED`。
  2026-11-19 实测（三条独立证据）：
  1. `POST /api/v5/account/set-account-level` 切 `acctLv=2/3/4` **全部被拒**
     `51070 "You do not meet the requirements for switching to this account mode. Please upgrade
     your account mode on the OKX website or app."` —— 该接口本身不提供跨模式升级。
  2. 绕过脚本直接打交易所（`POST /api/v5/trade/order`，`BTC-USDT-SWAP`、`tdMode=cross`、
     `posSide=net`、`sz=minSz=0.01`、`px=30000` 远端限价）→ `sCode 51010
     "You can't complete this request under your current account mode."`。
     **即 51010 是交易所侧硬拒，不是本地闸门误判**；脚本的 fail-closed 方向正确，无需放宽。
  3. demo 网页逐项排查（个人资料页 / 偏好设置 / 交易 ▾ 下拉 / 下单面板齿轮 / 资产管理·模拟交易 /
     右上角图标簇 / 右侧工具栏 / 资产页 / `demo-trading` 入口）均**没有账户模式入口**；
     同一 UID 的**实盘账户已持有多笔永续仓位（50x）**，说明实盘 `acctLv` 已 ≥2、与 demo 账户模式相互独立，
     demo 不存在「跟着实盘升级」的捷径。
  脚本把这一步显式成 `swap_account_mode` 步骤：只读时记 WARN，要求下单时记 FAIL 且**不发单**
  （`limit_roundtrip` 记 SKIP），不会把账户侧限制伪装成通过。
- **demo 现货侧的旁证（2026-11-19）**：在 demo 现货页开通「借币交易」（杠杆）后，可用额度从
  ~4,156 USDT 变为 ~883,670 USDT，而 `GET /api/v5/account/config` 仍返回 `acctLv=1`。
  说明 OKX demo 的「现货模式」允许币币杠杆，但**不允许永续**；杠杆成交路径同样未验证。
- **升级路径结论**：demo 永续只能在 OKX **手机 App**（或官网旧版设置面板）里改账户模式，
  网页 demo 工作区当前无入口。升级后复跑同一条命令即可验收合约往返。
- **未覆盖**：成交路径（`filled>0`）。本轮全是 post-only 远端挂单后撤销，没有真实吃单，
  因此 `fills → qd_strategy_trades` 归集未经过本入口验证。
- 本轮观察到一次 `OKX readonly GET transient network error (attempt 0)` 但随后 PASS，
  说明适配器有退避重试；未统计失败率。

## 单测

```bash
cd backend_api_python && python -m pytest tests/test_demo_trading_smoke.py -q
```

专测不含网络与 DB（19 例）：fail-closed（live 凭据拒绝且不构造 client）、名义额闸门边界、
掩码不外泄、撤单不重复、happy path 中断时兜底撤单一次、交易所拒单记 FAIL 不中断、
最小名义额推导（现货/合约 ctVal/lot 上取整）、swap `acctLv=1` 不发单。
