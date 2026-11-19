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

## 步骤与判据

| 步骤 | 判据 |
|---|---|
| `credential_environment` | `environment` ∈ {demo, testnet} |
| `create_client` | 适配器可构造；输出掩码后的配置 |
| `simulated_header` | 客户端实际发出的 `x-simulated-trading` / `PAPTRADING` 为 `1` |
| `ticker` | 有 `last` |
| `spot_wallet` / `position_long|short` | 余额或持仓可读 |
| `limit_roundtrip` | 本地名义额闸门通过 → 下单 → 查状态 → 撤单；撤单成功后不再重复撤 |
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

## 已知边界（未验证 / 未覆盖）

- **未验证**：demo 账户 `acctLv=1` 时永续开仓被 `OKX_SWAP_ACCOUNT_MODE_REQUIRED` 拒绝，
  swap 目前只覆盖只读；要覆盖永续下单需先在 demo 切保证金账户模式。
- **未覆盖**：成交路径（`filled>0`）。本轮全是 post-only 远端挂单后撤销，没有真实吃单，
  因此 `fills → qd_strategy_trades` 归集未经过本入口验证。
- **未覆盖**：OKX 现货最小名义额约 5 USDT，`0.61 USDT` 下单被 `51020`
  "minimum order amount" 拒绝；因此 `--max-usdt` 低于 5 的测试会失败，这是交易所限制不是脚本缺陷。
- 本轮观察到一次 `OKX readonly GET transient network error (attempt 0)` 但随后 PASS，
  说明适配器有退避重试；未统计失败率。

## 单测

```bash
cd backend_api_python && python -m pytest tests/test_demo_trading_smoke.py -q
```

专测不含网络与 DB：fail-closed（live 凭据拒绝且不构造 client）、名义额闸门边界、
掩码不外泄、撤单不重复、happy path 中断时兜底撤单一次、残留挂单判 FAIL。
