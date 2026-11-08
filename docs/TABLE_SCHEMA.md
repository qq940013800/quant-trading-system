# PostgreSQL 表字段口径盘点（只读）

> 生成时间：2026-11-08
> 范围：后端 `backend_api_python` 落库相关的表与字段；仅读取 schema 文件与代码，**未连接数据库、未改 schema、未补造历史数据**。
> 事实来源：
> - `backend_api_python/migrations/init.sql`（建表与 `ALTER TABLE ADD COLUMN`）
> - `backend_api_python/migrations/20260724_execution_stream_ledger.sql`（执行流账本迁移）
> - 仓库根 `db_tables.txt`（线上 `\dt` 表清单，106 张）、`db_strategy_schema.txt`（`\d qd_strategies_trading`）
> - 后端 `app/routes`、`app/services`、`app/utils` 中的 `INSERT INTO` / `SELECT` 映射

## 0. 口径与置信度约定

- **confirmed**：schema（init.sql / 迁移 SQL / `\d` 输出）与后端代码双侧可核实，字段名、类型、落库路径明确。
- **inferred**：仅由表名、字段名或代码使用场景推断含义；schema 无注释、代码未显式写值，需后续复核。
- **unknown**：代码与 schema 均无法证实其含义、是否真正落库或是否被读取；不臆造取值。

审计回放必需字段（任务口径）：时间戳、品种、方向、价格、数量、盈亏、原因、关联策略/订单 id。下表「审计回放」列标注该字段是否属于上述范畴。

> 说明：本次盘点只覆盖与成交、策略、决策日志、凭证、持仓、执行/风控事件直接相关的表；计费、AI 助手、指标商城、社区、 fundamental 等表仅在第 6 节列名，不逐字段展开。

## 1. 核心表（任务点名）

### 1.1 `qd_quick_trades` — 手动/快速成交记录

落库代码：`app/routes/quick_trade.py`（`INSERT INTO qd_quick_trades ... RETURNING id`）。
schema：`init.sql` L2087–2115；佣金三列由 L2126–2135 的 `ALTER TABLE` 补齐。
置信度：confirmed。

| 字段 | 类型（schema） | 含义 | 是否落库 | 审计回放 | 置信度 |
|---|---|---|---|---|---|
| id | SERIAL PK | 自增主键 | 是（RETURNING id） | 关联凭证/回链 id | confirmed |
| user_id | INTEGER NOT NULL, FK qd_users(id) | 所属用户 | 是 | 用户归属 | confirmed |
| credential_id | INTEGER DEFAULT 0 | 关联交易所凭证 id | 是 | 关联凭证 id | confirmed |
| exchange_id | VARCHAR(40) NOT NULL DEFAULT '' | 交易所标识（okx/bybit/...） | 是 | 执行场所 | confirmed |
| symbol | VARCHAR(60) NOT NULL DEFAULT '' | 交易品种 | 是 | 品种 | confirmed |
| side | VARCHAR(10) NOT NULL DEFAULT '' | 方向 buy/sell | 是 | 方向 | confirmed |
| order_type | VARCHAR(20) NOT NULL DEFAULT 'market' | 订单类型 market/limit | 是 | 订单形态 | confirmed |
| amount | DECIMAL(24,8) DEFAULT 0 | 下单数量/金额（口径见风险项） | 是 | 数量 | confirmed |
| price | DECIMAL(24,8) DEFAULT 0 | 委托价格 | 是 | 价格 | confirmed |
| leverage | INTEGER DEFAULT 1 | 杠杆 | 是 | 仓位参数 | confirmed |
| market_type | VARCHAR(20) DEFAULT 'swap' | swap/spot | 是 | 市场类型 | confirmed |
| tp_price | DECIMAL(24,8) DEFAULT 0 | 止盈价 | 是 | 退出价位 | confirmed |
| sl_price | DECIMAL(24,8) DEFAULT 0 | 止损价 | 是 | 退出价位 | confirmed |
| status | VARCHAR(20) DEFAULT 'submitted' | submitted/filled/failed/cancelled | 是 | 结果状态 | confirmed |
| exchange_order_id | VARCHAR(120) DEFAULT '' | 交易所订单号 | 是 | 关联交易所订单 id | confirmed |
| filled_amount | DECIMAL(24,8) DEFAULT 0 | 已成交数量 | 是 | 数量 | confirmed |
| avg_fill_price | DECIMAL(24,8) DEFAULT 0 | 平均成交价 | 是 | 价格 | confirmed |
| commission | DECIMAL(24,8) DEFAULT 0 | 本笔已实现手续费（best-effort） | 是 | 成本 | confirmed |
| commission_ccy | VARCHAR(16) DEFAULT '' | 手续费币种（USDT/BNB 等，未知为空） | 是 | 成本币种 | confirmed |
| commission_quote | DECIMAL(24,8) | 折算到报价币的手续费；可为 NULL | 是（可能 NULL） | 成本 | confirmed |
| error_msg | TEXT DEFAULT '' | 下单失败/错误信息 | 是 | 失败原因 | confirmed |
| source | VARCHAR(40) DEFAULT 'manual' | 来源 ai_radar/ai_analysis/indicator/manual | 是 | 决策来源 | confirmed |
| raw_result | JSONB | 交易所原始返回（已脱敏合作归因字段） | 是 | 原始上下文 | confirmed |
| created_at | TIMESTAMP DEFAULT NOW() | 记录落库时间 | 是 | 时间戳 | confirmed |

缺口与备注：
- **无独立盈亏字段**：表内只有手续费，没有 realized/unrealized PnL 列；快速成交的平仓盈亏不落在本表（confirmed：schema 无盈亏列）。
- **无策略/订单链路上挂字段**：本表不挂 `strategy_id` / `strategy_run_id` / `order_intent_id`；成交与策略的关联通过 `qd_live_order_bindings`（owner_type=`quick_trade`）间接回链（confirmed：`quick_trade.py` L300–314 调 `register_binding`）。
- **无拒单/风控拦截原因结构化字段**：被风控拦截时进入 `error_msg` 文本，或走 `pending_orders.last_error`（见 4.1、第 5 节）。

### 1.2 `qd_strategy_trades` — 策略成交台账

落库代码：`app/services/live_trading/records.py`（`INSERT INTO qd_strategy_trades ... ON CONFLICT (execution_event_id) DO NOTHING`）。
schema：`init.sql` L419–449；执行流补齐列见 `20260724_execution_stream_ledger.sql` L8–16。
置信度：confirmed。

| 字段 | 类型（schema） | 含义 | 是否落库 | 审计回放 | 置信度 |
|---|---|---|---|---|---|
| id | SERIAL PK | 自增主键 | 是 | 回链 id | confirmed |
| user_id | INTEGER NOT NULL DEFAULT 1, FK qd_users(id) | 所属用户 | 是 | 用户归属 | confirmed |
| strategy_id | INTEGER, FK qd_strategies_trading(id) | 关联策略 | 是 | 关联策略 id | confirmed |
| symbol | VARCHAR(50) | 交易品种（原始） | 是 | 品种 | confirmed |
| symbol_canonical | VARCHAR(50) DEFAULT '' | 归一化品种 | 是 | 品种 | confirmed |
| type | VARCHAR(30) | 成交方向/类型（open_long/close_short 等） | 是 | 方向 | confirmed |
| price | DECIMAL(20,8) | 成交价 | 是 | 价格 | confirmed |
| amount | DECIMAL(20,8) | 成交数量 | 是 | 数量 | confirmed |
| value | DECIMAL(20,8) | 名义价值 = amount × price（代码计算） | 是 | 名义金额 | confirmed |
| commission | DECIMAL(20,8) DEFAULT 0 | 手续费 | 是 | 成本 | confirmed |
| commission_ccy | VARCHAR(20) DEFAULT '' | 手续费币种 | 是 | 成本币种 | confirmed |
| commission_quote | DECIMAL(24,8) | 报价币手续费（迁移补齐） | 是（可能 NULL） | 成本 | confirmed |
| profit | DECIMAL(20,8) DEFAULT 0 | 平仓盈亏（开仓笔可为 NULL/0） | 是 | 盈亏 | confirmed |
| close_reason | VARCHAR(64) DEFAULT '' | 平仓原因 | 是 | 原因 | confirmed |
| matched_entry_price | DECIMAL(20,8) DEFAULT 0 | 配对开仓价 | 是 | 配对价格 | confirmed |
| grid_matched_profit | DECIMAL(20,8) DEFAULT 0 | 网格配对盈亏 | 是 | 盈亏（网格） | confirmed |
| market_type | VARCHAR(20) DEFAULT 'swap' | swap/spot | 是 | 市场类型 | confirmed |
| credential_id | INTEGER DEFAULT 0 | 关联凭证 id | 是 | 关联凭证 id | confirmed |
| inst_id | VARCHAR(80) DEFAULT '' | 交易所合约/inst 标识 | 是 | 合约标识 | confirmed |
| fill_source | VARCHAR(32) DEFAULT '' | 成交来源（websocket/rest/...） | 是 | 来源 | confirmed |
| pending_order_id | INTEGER DEFAULT 0 | 关联待执行订单 id | 是 | 关联订单 id | confirmed |
| grid_order_id | BIGINT DEFAULT 0 | 关联网格订单 id（迁移补齐） | 是 | 关联订单 id | confirmed |
| strategy_run_id | INTEGER DEFAULT 0 | 关联策略运行实例 id | 是 | 关联运行 id | confirmed |
| order_intent_id | INTEGER DEFAULT 0 | 关联下单意图 id | 是 | 关联订单 id | confirmed |
| execution_event_id | BIGINT NOT NULL DEFAULT 0 | 关联执行事件 id；>0 时唯一索引 | 是 | 关联执行事件 id | confirmed |
| exchange_fill_id | VARCHAR(160) DEFAULT '' | 交易所成交 id（迁移补齐） | 是 | 关联交易所成交 id | confirmed |
| fee_status | VARCHAR(24) NOT NULL DEFAULT 'pending' | 手续费对账状态（迁移补齐） | 是 | 对账状态 | confirmed |
| fee_source | VARCHAR(24) NOT NULL DEFAULT '' | 手续费来源（迁移补齐） | 是 | 成本来源 | confirmed |
| created_at | TIMESTAMP DEFAULT NOW() | 落库时间 | 是 | 时间戳 | confirmed |

缺口与备注：
- 决策快照（开仓时的信号、L1–L5 状态、仓位/止损参数）**不在本表**；只能经 `strategy_run_id` / `order_intent_id` / `execution_event_id` 回链到运行意图、成交与执行事件表（confirmed）。
- `profit` 为该笔台账盈亏；组合级已实现/浮动盈亏另见 `qd_strategy_equity_snapshots`（4.5）。

### 1.3 `qd_strategy_logs` — 策略决策/运行日志

落库代码：`app/utils/strategy_runtime_logs.py`（`append_strategy_log`，best-effort，写失败仅 `debug` 日志不抛错）。
schema：`init.sql` L756–765。
置信度：confirmed。

| 字段 | 类型（schema） | 含义 | 是否落库 | 审计回放 | 置信度 |
|---|---|---|---|---|---|
| id | SERIAL PK | 自增主键 | 是 | 回链 id | confirmed |
| strategy_id | INTEGER NOT NULL, FK qd_strategies_trading(id) | 关联策略 | 是 | 关联策略 id | confirmed |
| level | VARCHAR(20) DEFAULT 'info' | 级别 info/warning/error/...（代码截断小写 20 字符） | 是 | 严重程度 | confirmed |
| message | TEXT NOT NULL | 日志正文（代码截断 8000 字符） | 是 | 决策/事件原因文本 | confirmed |
| timestamp | TIMESTAMP DEFAULT NOW() | 日志时间（代码写入 UTC 当前时间） | 是 | 时间戳 | confirmed |

缺口与备注：
- **无结构化字段**：无品种、方向、价格、数量、信号快照、违规码、关联订单 id；这些只能解析 `message` 文本（confirmed：schema 仅四列；INSERT 仅写四列）。
- **风控拒单以文本落库**：`pending_order_worker.py` 拦截后调 `append_strategy_log(strategy_id, "warning"/"error", "Order rejected ...")`，违规码拼接进 `message`，未单独成列（confirmed）。
- 代码存在守卫：仅当 `qd_strategies_trading` 存在对应 `strategy_id` 时才插入（confirmed：INSERT 内 `WHERE EXISTS` 子查询）。

### 1.4 `qd_exchange_credentials` — 交易所凭证

落库代码：`app/routes/credentials.py`（INSERT L321；UPDATE L364）、`app/routes/alpaca.py`（L169 INSERT）。
schema：`init.sql` L1258–1269。
置信度：confirmed。

| 字段 | 类型（schema） | 含义 | 是否落库 | 审计回放 | 置信度 |
|---|---|---|---|---|---|
| id | SERIAL PK | 自增主键 | 是 | 关联凭证 id | confirmed |
| user_id | INTEGER NOT NULL DEFAULT 1, FK qd_users(id) | 所属用户 | 是 | 用户归属 | confirmed |
| name | VARCHAR(100) DEFAULT '' | 凭证显示名 | 是 | 标识 | confirmed |
| exchange_id | VARCHAR(50) NOT NULL | 交易所标识 | 是 | 执行场所 | confirmed |
| api_key_hint | VARCHAR(50) DEFAULT '' | 密钥脱敏提示（前缀/后缀，非明文） | 是 | 标识（脱敏） | confirmed |
| encrypted_config | TEXT NOT NULL | Fernet 加密的配置 blob（含 api_key/secret/passphrase/environment 等） | 是 | 上下文（加密，不可直接回放明文） | confirmed |
| created_at | TIMESTAMP DEFAULT NOW() | 创建时间 | 是 | 时间戳 | confirmed |
| updated_at | TIMESTAMP DEFAULT NOW() | 更新时间 | 是 | 时间戳 | confirmed |

缺口与备注：
- **`environment`（demo/paper/live）不是独立列**：由 `_crypto_credential_config` 写入 `encrypted_config` JSON 内的 `environment`/`market_scope`/`enable_demo_trading` 字段；读取时解密后由 `exchange_trading_environment()` 推导（confirmed：credentials.py L123–134；schema 无该列）。
- 无独立的凭证状态/连通性健康字段；连通性在执行流健康表 `qd_execution_stream_health` 按凭证维度维护（4.7）。

## 2. 策略主表

### 2.1 `qd_strategies_trading` — 策略注册主表

schema：`init.sql` L297–316；线上 `\d` 见仓库根 `db_strategy_schema.txt`（含后续迁移补列 `source_version_id`、索引与外键）。
代码读取：`app/services/strategy.py`、`account_risk.py`、`pending_order_worker.py` 等。
置信度：confirmed（列名/类型以 `\d` 输出为准；`source_version_id` 仅在线上 schema 与迁移 FK 中出现，`init.sql` 建表段未列该列，按线上 `\d` 计为 confirmed）。

| 字段 | 类型（schema/`\d`） | 含义 | 是否落库 | 审计回放 | 置信度 |
|---|---|---|---|---|---|
| id | integer PK, nextval | 策略主键 | 是 | 关联策略 id | confirmed |
| user_id | integer NOT NULL DEFAULT 1, FK qd_users(id) | 所属用户 | 是 | 用户归属 | confirmed |
| strategy_name | VARCHAR(255) NOT NULL | 策略名称 | 是 | 标识 | confirmed |
| strategy_type | VARCHAR(50) DEFAULT 'StrategyV2' | 策略类型 | 是 | 策略类别 | confirmed |
| market_category | VARCHAR(50) DEFAULT 'Crypto' | 市场大类 | 是 | 市场类别 | confirmed |
| execution_mode | VARCHAR(20) NOT NULL DEFAULT 'signal' | signal/... 执行模式 | 是 | 执行形态 | confirmed |
| notification_config | JSONB NOT NULL DEFAULT '{}' | 通知配置 | 是 | 配置上下文 | confirmed |
| status | VARCHAR(20) DEFAULT 'stopped' | running/stopped/... 状态 | 是 | 策略状态 | confirmed |
| symbol | VARCHAR(50) | 主交易品种 | 是 | 品种 | confirmed |
| symbol_canonical | VARCHAR(50) DEFAULT '' | 归一化品种 | 是 | 品种 | confirmed |
| timeframe | VARCHAR(10) | 周期 | 是 | 周期 | confirmed |
| initial_capital | DECIMAL(20,8) DEFAULT 1000 | 初始资金 | 是 | 仓位基准 | confirmed |
| leverage | INTEGER DEFAULT 1 | 杠杆 | 是 | 仓位参数 | confirmed |
| market_type | VARCHAR(20) DEFAULT 'swap' | swap/spot | 是 | 市场类型 | confirmed |
| exchange_config | JSONB NOT NULL DEFAULT '{}' | 交易所/凭证相关配置 | 是 | 配置上下文 | confirmed |
| trading_config | JSONB NOT NULL DEFAULT '{}' | 交易/风控参数（含 `account_risk` 限制） | 是 | 决策参数快照 | confirmed |
| created_at | timestamp DEFAULT now() | 创建时间 | 是 | 时间戳 | confirmed |
| updated_at | timestamp DEFAULT now() | 更新时间 | 是 | 时间戳 | confirmed |
| source_version_id | integer, FK qd_script_source_versions(id) ON DELETE RESTRICT | 关联脚本源码版本 | 是（线上 schema） | 代码版本溯源 | confirmed（线上 `\d`） |

缺口与备注：
- `trading_config` 为 JSONB，策略参数/风控限制嵌套其中；结构化参数不在独立列（confirmed）。
- 策略健康度三级状态、退役原因当前未在主表落独立列；相关运行态见 `strategy_runtime_events`、`qd_strategy_equity_snapshots`（4.5/4.6）。

## 3. 持仓表

### 3.1 `qd_strategy_positions` — 策略持仓台账

落库代码：`app/services/live_trading/records.py`（UPSERT，`ON CONFLICT(strategy_id, symbol, side) DO UPDATE`）。
schema：`init.sql` L389–413。
置信度：confirmed。

| 字段 | 类型（schema） | 含义 | 是否落库 | 审计回放 | 置信度 |
|---|---|---|---|---|---|
| id | SERIAL PK | 自增主键 | 是 | 回链 id | confirmed |
| user_id | INTEGER NOT NULL DEFAULT 1, FK qd_users(id) | 所属用户 | 是 | 用户归属 | confirmed |
| strategy_id | INTEGER, FK qd_strategies_trading(id) | 关联策略 | 是 | 关联策略 id | confirmed |
| symbol | VARCHAR(50) | 品种 | 是 | 品种 | confirmed |
| symbol_canonical | VARCHAR(50) DEFAULT '' | 归一化品种 | 是 | 品种 | confirmed |
| side | VARCHAR(10) | long/short | 是 | 方向 | confirmed |
| size | DECIMAL(20,8) | 持仓数量 | 是 | 数量 | confirmed |
| entry_price | DECIMAL(20,8) | 开仓价 | 是 | 价格 | confirmed |
| current_price | DECIMAL(20,8) | 最新价 | 是 | 价格 | confirmed |
| highest_price | DECIMAL(20,8) DEFAULT 0 | 持仓期最高价（UPSERT 只上推） | 是 | 轨迹参考 | confirmed |
| lowest_price | DECIMAL(20,8) DEFAULT 0 | 持仓期最低价（UPSERT 只下推） | 是 | 轨迹参考 | confirmed |
| unrealized_pnl | DECIMAL(20,8) DEFAULT 0 | 浮动盈亏 | schema 有列；本次 INSERT 未写（见备注） | 盈亏 | 列 confirmed / 写入路径 unknown |
| pnl_percent | DECIMAL(10,4) DEFAULT 0 | 盈亏百分比 | schema 有列；本次 INSERT 未写（见备注） | 盈亏 | 列 confirmed / 写入路径 unknown |
| equity | DECIMAL(20,8) DEFAULT 0 | 持仓权益 | schema 有列；本次 INSERT 未写（见备注） | 权益 | 列 confirmed / 写入路径 unknown |
| market_type | VARCHAR(20) DEFAULT 'swap' | swap/spot | 是 | 市场类型 | confirmed |
| credential_id | INTEGER DEFAULT 0 | 关联凭证 id | 是 | 关联凭证 id | confirmed |
| inst_id | VARCHAR(80) DEFAULT '' | 交易所合约标识 | 是 | 合约标识 | confirmed |
| strategy_run_id | INTEGER DEFAULT 0 | 关联运行实例 id | schema 有列；本次 INSERT 未写 | 关联运行 id | 列 confirmed / 写入路径 unknown |
| updated_at | TIMESTAMP DEFAULT NOW() | 更新时间 | 是 | 时间戳 | confirmed |
| UNIQUE | (strategy_id, symbol, side) | 持仓唯一键 | — | — | confirmed |

缺口与备注：
- 本次定位到的 UPSERT 仅写 size/entry/current/high/low/market_type/credential/inst_id 等列；`unrealized_pnl`、`pnl_percent`、`equity`、`strategy_run_id` 在该写入路径未出现，可能由其他同步任务刷新——**未在本次代码中证实刷新路径，标 unknown**。
- 持仓开仓时间戳（entry_time）无独立列；开仓时间需回链 `qd_strategy_trades` 开仓笔的 `created_at`（inferred：由成交台账配对）。

### 3.2 `qd_account_positions` — 账户持仓镜像（交易所真值）

schema：`init.sql` L549–567；代码：`app/services/live_trading/account_positions.py`。
置信度：confirmed。

| 字段 | 类型（schema） | 含义 | 审计回放 | 置信度 |
|---|---|---|---|---|
| id | SERIAL PK | 主键 | 回链 id | confirmed |
| user_id | INTEGER NOT NULL DEFAULT 1, FK | 用户 | 用户归属 | confirmed |
| credential_id | INTEGER NOT NULL DEFAULT 0 | 凭证 id | 关联凭证 id | confirmed |
| exchange_id | VARCHAR(40) NOT NULL DEFAULT '' | 交易所 | 执行场所 | confirmed |
| market_type | VARCHAR(20) NOT NULL DEFAULT 'swap' | swap/spot | 市场类型 | confirmed |
| inst_id | VARCHAR(80) NOT NULL DEFAULT '' | 合约标识 | 合约标识 | confirmed |
| symbol | VARCHAR(50) NOT NULL DEFAULT '' | 品种 | 品种 | confirmed |
| side | VARCHAR(10) NOT NULL DEFAULT '' | 方向 | 方向 | confirmed |
| size | DECIMAL(24,8) NOT NULL DEFAULT 0 | 持仓数量 | 数量 | confirmed |
| entry_price | DECIMAL(24,8) DEFAULT 0 | 开仓价 | 价格 | confirmed |
| mark_price | DECIMAL(24,8) DEFAULT 0 | 标记价 | 价格 | confirmed |
| unrealized_pnl | DECIMAL(24,8) DEFAULT 0 | 浮动盈亏 | 盈亏 | confirmed |
| raw_json | JSONB DEFAULT '{}' | 交易所原始快照 | 原始上下文 | confirmed |
| synced_at | TIMESTAMP NOT NULL DEFAULT NOW() | 同步时间 | 时间戳 | confirmed |
| UNIQUE | (credential_id, market_type, inst_id, side) | 镜像唯一键 | — | confirmed |

### 3.3 `qd_position_reservations` — 持仓归属/预留与漂移状态

schema：`init.sql` L570–594；迁移 `20260801_position_ownership.sql`。
置信度：confirmed（列名/类型）；漂移判定细节 inferred。

| 字段 | 类型（schema） | 含义 | 审计回放 | 置信度 |
|---|---|---|---|---|
| id | SERIAL PK | 主键 | 回链 id | confirmed |
| user_id | INTEGER NOT NULL DEFAULT 1, FK | 用户 | 用户归属 | confirmed |
| credential_id | INTEGER NOT NULL DEFAULT 0 | 凭证 id | 关联凭证 id | confirmed |
| exchange_id | VARCHAR(40) NOT NULL DEFAULT '' | 交易所 | 执行场所 | confirmed |
| market_type | VARCHAR(20) NOT NULL DEFAULT 'swap' | swap/spot | 市场类型 | confirmed |
| inst_id | VARCHAR(80) NOT NULL DEFAULT '' | 合约标识 | 合约标识 | confirmed |
| symbol / symbol_canonical | VARCHAR(50) | 品种（原始/归一化） | 品种 | confirmed |
| side | VARCHAR(10) NOT NULL DEFAULT '' | 方向 | 方向 | confirmed |
| coexistence_mode | VARCHAR(20) NOT NULL DEFAULT 'strict' | 归属共存模式 | 归属规则 | inferred |
| manual_reserved_qty | DECIMAL(24,8) NOT NULL DEFAULT 0 | 人工预留数量 | 数量 | confirmed |
| observed_account_qty | DECIMAL(24,8) NOT NULL DEFAULT 0 | 账户观测数量 | 数量 | confirmed |
| allocated_qty | DECIMAL(24,8) NOT NULL DEFAULT 0 | 已分配数量 | 数量 | confirmed |
| status | VARCHAR(32) NOT NULL DEFAULT 'ok' | 归属/漂移状态 | 状态 | confirmed |
| drift_reason | VARCHAR(80) NOT NULL DEFAULT '' | 漂移原因 | 原因 | confirmed |
| last_log_at | TIMESTAMP | 上次记录时间 | 时间戳 | confirmed |
| created_at / updated_at | TIMESTAMP | 创建/更新时间 | 时间戳 | confirmed |

## 4. 执行、意图、事件与对账表

### 4.1 `pending_orders` — 待执行订单（信号→下单中转）

schema：`init.sql` L649–694；执行流迁移补 `client_order_id`/`fee_status`/`fee_source`。
代码：`app/services/strategy_v2/live_execution.py`（INSERT）、`app/services/pending_order_worker.py`（状态推进/失败标记）。
置信度：confirmed。

| 字段 | 类型（schema） | 含义 | 审计回放 | 置信度 |
|---|---|---|---|---|
| id | SERIAL PK | 主键 | 回链 id | confirmed |
| user_id | INTEGER NOT NULL DEFAULT 1, FK | 用户 | 用户归属 | confirmed |
| strategy_id | INTEGER FK qd_strategies_trading(id) ON DELETE SET NULL | 关联策略 | 关联策略 id | confirmed |
| symbol | VARCHAR(50) NOT NULL | 品种 | 品种 | confirmed |
| signal_type | VARCHAR(30) NOT NULL | 信号/方向类型 | 方向/信号 | confirmed |
| signal_ts | BIGINT | 信号时间戳（epoch，单位需复核） | 时间戳 | 列 confirmed / 时间单位 unknown |
| strategy_run_id | INTEGER NOT NULL DEFAULT 0 | 运行实例 id | 关联运行 id | confirmed |
| order_intent_id | INTEGER NOT NULL DEFAULT 0 | 下单意图 id | 关联订单 id | confirmed |
| idempotency_key | VARCHAR(180) NOT NULL UNIQUE | 幂等键 | 幂等溯源 | confirmed |
| market_type | VARCHAR(20) DEFAULT 'swap' | swap/spot | 市场类型 | confirmed |
| order_type | VARCHAR(20) DEFAULT 'market' | 订单类型 | 订单形态 | confirmed |
| amount | DECIMAL(20,8) DEFAULT 0 | 数量 | 数量 | confirmed |
| price | DECIMAL(20,8) DEFAULT 0 | 委托价 | 价格 | confirmed |
| execution_mode | VARCHAR(20) DEFAULT 'signal' | 执行模式 | 执行形态 | confirmed |
| status | VARCHAR(20) DEFAULT 'pending' | pending/.../failed/filled | 结果状态 | confirmed |
| priority | INTEGER DEFAULT 0 | 优先级 | 调度上下文 | inferred |
| attempts / max_attempts | INTEGER DEFAULT 0 / 10 | 已尝试次数 / 上限 | 重试溯源 | confirmed |
| last_error | TEXT DEFAULT '' | 最近一次错误/拒单原因 | 原因 | confirmed |
| payload_json | TEXT DEFAULT '' | 信号/下单载荷（文本 JSON） | 决策快照 | confirmed |
| dispatch_note | TEXT DEFAULT '' | 调度备注 | 原因/备注 | inferred |
| exchange_id | VARCHAR(50) DEFAULT '' | 交易所 | 执行场所 | confirmed |
| credential_id | INTEGER NOT NULL DEFAULT 0 | 凭证 id | 关联凭证 id | confirmed |
| inst_id | VARCHAR(80) NOT NULL DEFAULT '' | 合约标识 | 合约标识 | confirmed |
| exchange_order_id | VARCHAR(100) DEFAULT '' | 交易所订单号 | 关联交易所订单 id | confirmed |
| exchange_response_json | TEXT DEFAULT '' | 交易所响应原文 | 原始上下文 | confirmed |
| filled | DECIMAL(20,8) DEFAULT 0 | 已成交数量 | 数量 | confirmed |
| avg_price | DECIMAL(20,8) DEFAULT 0 | 平均成交价 | 价格 | confirmed |
| executed_at | TIMESTAMP | 成交时间 | 时间戳 | confirmed |
| created_at / updated_at / processed_at / sent_at | TIMESTAMP | 创建/更新/处理/发送时间 | 时间戳 | confirmed |
| client_order_id | VARCHAR(100) NOT NULL DEFAULT '' | 客户端订单 id（迁移补齐） | 关联订单 id | confirmed |
| fee_status | VARCHAR(24) NOT NULL DEFAULT 'pending' | 手续费对账状态（迁移补齐） | 对账状态 | confirmed |
| fee_source | VARCHAR(24) NOT NULL DEFAULT '' | 手续费来源（迁移补齐） | 成本来源 | confirmed |

缺口与备注：
- **风控拦截落点**：`pending_order_worker.py` 风控不通过时 `_mark_failed(order_id, error=违规码)`，违规码进 `last_error`，同时写一条 `qd_strategy_logs` 文本；**无独立风控事件表、无违规码结构化列、无拦截计数列**（confirmed：见 4.8 与第 5 节）。

### 4.2 `strategy_order_intents` — 策略下单意图（决策层）

schema：`init.sql` L1750–1779。代码：`app/services/strategy_runtime/order_intents.py`（INSERT）。
置信度：confirmed。

| 字段 | 类型（schema） | 含义 | 审计回放 | 置信度 |
|---|---|---|---|---|
| id | SERIAL PK | 主键 | 回链 id | confirmed |
| strategy_run_id | INTEGER NOT NULL DEFAULT 0 | 运行实例 id | 关联运行 id | confirmed |
| strategy_id | INTEGER NOT NULL | 策略 id | 关联策略 id | confirmed |
| idempotency_key | VARCHAR(180) NOT NULL | 幂等键 | 幂等溯源 | confirmed |
| symbol | VARCHAR(80) NOT NULL | 品种 | 品种 | confirmed |
| market_type | VARCHAR(20) NOT NULL DEFAULT 'swap' | swap/spot | 市场类型 | confirmed |
| side | VARCHAR(10) NOT NULL | 方向 | 方向 | confirmed |
| position_side | VARCHAR(10) NOT NULL DEFAULT '' | 持仓方向（多/空/对冲） | 方向 | confirmed |
| reduce_only | BOOLEAN NOT NULL DEFAULT FALSE | 是否减仓/平仓 | 方向属性 | confirmed |
| order_type | VARCHAR(24) NOT NULL DEFAULT 'market' | 订单类型 | 订单形态 | confirmed |
| quantity | DECIMAL(28,12) NOT NULL DEFAULT 0 | 数量 | 数量 | confirmed |
| notional | DECIMAL(28,12) NOT NULL DEFAULT 0 | 名义金额 | 名义金额 | confirmed |
| limit_price | DECIMAL(28,12) NOT NULL DEFAULT 0 | 限价 | 价格 | confirmed |
| execution_algo | VARCHAR(32) NOT NULL DEFAULT 'market' | 执行算法 | 执行形态 | inferred |
| portfolio_id / universe_id / rebalance_group_id | VARCHAR(96/96/128) | 组合/股票池/再平衡分组 | 归属上下文 | inferred |
| target_weight / target_notional / target_position_qty | DECIMAL(18,10) / DECIMAL(28,12) / DECIMAL(28,12) | 目标权重/名义/目标持仓 | 决策目标 | confirmed |
| status | VARCHAR(32) NOT NULL DEFAULT 'intent_created' | 意图状态 | 状态 | confirmed |
| client_order_id / exchange_order_id | VARCHAR(100) NOT NULL DEFAULT '' | 客户端/交易所订单号 | 关联订单 id | confirmed |
| payload_json | JSONB NOT NULL DEFAULT '{}' | 意图载荷/决策快照 | 决策快照 | confirmed |
| created_at / updated_at | TIMESTAMP | 创建/更新时间 | 时间戳 | confirmed |
| UNIQUE | (strategy_run_id, idempotency_key) | 幂等唯一键 | — | confirmed |

### 4.3 `strategy_order_fills` — 策略成交回报（执行层）

schema：`init.sql` L1781–1800；迁移补 `credential_id`/`commission_quote`/`fee_status`。代码：`app/services/pending_orders/fill_records.py`（INSERT）。
置信度：confirmed。

| 字段 | 类型（schema） | 含义 | 审计回放 | 置信度 |
|---|---|---|---|---|
| id | SERIAL PK | 主键 | 回链 id | confirmed |
| order_intent_id | INTEGER NOT NULL DEFAULT 0 | 关联意图 id | 关联订单 id | confirmed |
| strategy_run_id | INTEGER NOT NULL DEFAULT 0 | 运行实例 id | 关联运行 id | confirmed |
| strategy_id | INTEGER NOT NULL DEFAULT 0 | 策略 id | 关联策略 id | confirmed |
| exchange_id | VARCHAR(50) NOT NULL DEFAULT '' | 交易所 | 执行场所 | confirmed |
| exchange_order_id | VARCHAR(100) NOT NULL DEFAULT '' | 交易所订单号 | 关联交易所订单 id | confirmed |
| exchange_fill_id | VARCHAR(128) NOT NULL DEFAULT '' | 交易所成交 id | 关联成交 id | confirmed |
| side | VARCHAR(10) NOT NULL DEFAULT '' | 方向 | 方向 | confirmed |
| position_side | VARCHAR(10) NOT NULL DEFAULT '' | 持仓方向 | 方向 | confirmed |
| price | DECIMAL(28,12) NOT NULL DEFAULT 0 | 成交价 | 价格 | confirmed |
| quantity | DECIMAL(28,12) NOT NULL DEFAULT 0 | 成交数量 | 数量 | confirmed |
| notional | DECIMAL(28,12) NOT NULL DEFAULT 0 | 名义金额 | 名义金额 | confirmed |
| fee | DECIMAL(28,12) NOT NULL DEFAULT 0 | 手续费 | 成本 | confirmed |
| fee_ccy | VARCHAR(20) NOT NULL DEFAULT '' | 手续费币种 | 成本币种 | confirmed |
| filled_at | TIMESTAMP NOT NULL DEFAULT NOW() | 成交时间 | 时间戳 | confirmed |
| raw_json | JSONB NOT NULL DEFAULT '{}' | 成交原始报文 | 原始上下文 | confirmed |
| credential_id | INTEGER NOT NULL DEFAULT 0 | 凭证 id（迁移补齐） | 关联凭证 id | confirmed |
| commission_quote | DECIMAL(28,12) | 报价币手续费（迁移补齐） | 成本 | confirmed |
| fee_status | VARCHAR(24) NOT NULL DEFAULT 'pending' | 对账状态（迁移补齐） | 对账状态 | confirmed |

### 4.4 `qd_execution_events` — 统一执行事件流账本

schema：`20260724_execution_stream_ledger.sql` L53–85（init.sql L1852–1884 同定义）。代码：`app/services/execution_streams/repository.py`、`processor.py`、`supervisor.py`。
置信度：confirmed。

| 字段 | 类型（schema） | 含义 | 审计回放 | 置信度 |
|---|---|---|---|---|
| id | BIGSERIAL PK | 事件主键 | 回链 id | confirmed |
| event_key | VARCHAR(320) NOT NULL UNIQUE | 事件幂等键 | 幂等溯源 | confirmed |
| credential_id | INTEGER NOT NULL DEFAULT 0 | 凭证 id | 关联凭证 id | confirmed |
| user_id | INTEGER NOT NULL DEFAULT 1 | 用户 | 用户归属 | confirmed |
| exchange_id | VARCHAR(50) NOT NULL | 交易所 | 执行场所 | confirmed |
| market_type | VARCHAR(20) NOT NULL DEFAULT 'swap' | swap/spot | 市场类型 | confirmed |
| account_id | VARCHAR(128) NOT NULL DEFAULT '' | 交易所账户 | 账户标识 | confirmed |
| symbol | VARCHAR(80) NOT NULL DEFAULT '' | 品种 | 品种 | confirmed |
| exchange_order_id | VARCHAR(160) NOT NULL DEFAULT '' | 交易所订单号 | 关联订单 id | confirmed |
| client_order_id | VARCHAR(100) NOT NULL DEFAULT '' | 客户端订单号 | 关联订单 id | confirmed |
| exchange_fill_id | VARCHAR(160) NOT NULL DEFAULT '' | 成交 id | 关联成交 id | confirmed |
| side | VARCHAR(12) NOT NULL DEFAULT '' | 方向 | 方向 | confirmed |
| position_side | VARCHAR(12) NOT NULL DEFAULT '' | 持仓方向 | 方向 | confirmed |
| order_status | VARCHAR(24) NOT NULL DEFAULT '' | 订单/成交状态 | 状态 | confirmed |
| price | DECIMAL(28,12) NOT NULL DEFAULT 0 | 价格 | 价格 | confirmed |
| quantity | DECIMAL(28,12) NOT NULL DEFAULT 0 | 数量 | 数量 | confirmed |
| cumulative_quantity | DECIMAL(28,12) NOT NULL DEFAULT 0 | 累计数量 | 数量 | confirmed |
| is_cumulative | BOOLEAN NOT NULL DEFAULT FALSE | 是否累计口径 | 口径标记 | confirmed |
| realized_pnl | DECIMAL(28,12) | 已实现盈亏（可为 NULL） | 盈亏 | confirmed |
| maker | BOOLEAN | 是否 maker（可为 NULL） | 成交属性 | confirmed |
| fee_status | VARCHAR(24) NOT NULL DEFAULT 'pending' | 手续费状态 | 对账状态 | confirmed |
| occurred_at | TIMESTAMP NOT NULL | 交易所事件发生时间 | 时间戳 | confirmed |
| received_at | TIMESTAMP NOT NULL DEFAULT NOW() | 后端接收时间 | 时间戳 | confirmed |
| raw_json | JSONB NOT NULL DEFAULT '{}' | 原始报文 | 原始上下文 | confirmed |
| processed_at | TIMESTAMP | 处理完成时间（NULL=未处理） | 时间戳 | confirmed |
| process_attempts | INTEGER NOT NULL DEFAULT 0 | 处理尝试次数 | 重试溯源 | confirmed |
| process_error | TEXT NOT NULL DEFAULT '' | 处理错误信息 | 原因 | confirmed |

相关子表（confirmed，仅列用途）：
- `qd_execution_fee_components`：按事件拆分的手续费成分（fee_type/currency/amount/quote_amount/source）。
- `qd_execution_fee_projections`：事件→待执行订单的手续费投影。
- `qd_execution_owner_projections`：事件归属投影（owner_type/owner_id）。
- `qd_live_order_bindings`：客户端/交易所订单号与归属主体（策略/待执行单/快速成交）的绑定桥表。

### 4.5 `qd_strategy_equity_snapshots` — 策略权益快照

schema：`init.sql` L505–523。代码：`app/services/strategy_daily_pnl.py`（INSERT）。
置信度：confirmed。

| 字段 | 类型（schema） | 含义 | 审计回放 | 置信度 |
|---|---|---|---|---|
| id | BIGSERIAL PK | 主键 | 回链 id | confirmed |
| user_id | INTEGER NOT NULL, FK | 用户 | 用户归属 | confirmed |
| strategy_id | INTEGER NOT NULL, FK | 策略 id | 关联策略 id | confirmed |
| equity | DECIMAL(24,8) NOT NULL DEFAULT 0 | 权益 | 权益 | confirmed |
| realized_pnl | DECIMAL(24,8) NOT NULL DEFAULT 0 | 已实现盈亏 | 盈亏 | confirmed |
| unrealized_pnl | DECIMAL(24,8) NOT NULL DEFAULT 0 | 浮动盈亏 | 盈亏 | confirmed |
| initial_capital | DECIMAL(24,8) | 初始资金（迁移补齐列） | 仓位基准 | confirmed |
| basis_reason | VARCHAR(32) NOT NULL DEFAULT '' | 快照口径原因（迁移补齐列） | 原因 | confirmed |
| captured_at | TIMESTAMP NOT NULL DEFAULT NOW() | 快照时间 | 时间戳 | confirmed |

### 4.6 `strategy_runtime_events` — 运行时事件流水

schema：`init.sql` L1929–1939。代码：`app/services/strategy_runtime/events.py`（`append_runtime_event`，best-effort）。
置信度：confirmed。

| 字段 | 类型（schema） | 含义 | 审计回放 | 置信度 |
|---|---|---|---|---|
| id | SERIAL PK | 主键 | 回链 id | confirmed |
| strategy_run_id | INTEGER NOT NULL DEFAULT 0 | 运行实例 id | 关联运行 id | confirmed |
| strategy_id | INTEGER NOT NULL DEFAULT 0 | 策略 id | 关联策略 id | confirmed |
| event_type | VARCHAR(64) NOT NULL | 事件类型 | 事件类别 | confirmed |
| severity | VARCHAR(16) NOT NULL DEFAULT 'info' | 严重程度 | 严重程度 | confirmed |
| message | TEXT NOT NULL DEFAULT '' | 事件正文 | 原因/说明 | confirmed |
| payload_json | JSONB NOT NULL DEFAULT '{}' | 事件结构化载荷 | 决策上下文 | confirmed |
| created_at | TIMESTAMP NOT NULL DEFAULT NOW() | 落库时间 | 时间戳 | confirmed |

### 4.7 `qd_execution_stream_health` — 行情/执行流健康度

schema：`20260724_execution_stream_ledger.sql` L115–128。
置信度：confirmed（列名/类型）；具体状态枚举 inferred。

| 字段 | 类型（schema） | 含义 | 审计回放 | 置信度 |
|---|---|---|---|---|
| stream_key | VARCHAR(180) PK | 流唯一键 | 流标识 | confirmed |
| credential_id | INTEGER NOT NULL DEFAULT 0 | 凭证 id | 关联凭证 id | confirmed |
| exchange_id | VARCHAR(50) NOT NULL | 交易所 | 执行场所 | confirmed |
| market_type | VARCHAR(20) NOT NULL DEFAULT '' | 市场类型 | 市场类型 | confirmed |
| state | VARCHAR(24) NOT NULL DEFAULT 'stopped' | 连接状态 | 状态 | inferred |
| last_event_at / last_connected_at / last_disconnected_at | TIMESTAMP | 最近事件/连接/断开时间 | 时间戳 | confirmed |
| reconnect_count | INTEGER NOT NULL DEFAULT 0 | 重连次数 | 重试溯源 | confirmed |
| rest_fallback | BOOLEAN NOT NULL DEFAULT FALSE | 是否 REST 兜底 | 降级标记 | confirmed |
| last_error | TEXT NOT NULL DEFAULT '' | 最近错误 | 原因 | confirmed |
| updated_at | TIMESTAMP NOT NULL DEFAULT NOW() | 更新时间 | 时间戳 | confirmed |

### 4.8 其他与运行/审计相关表（confirmed 存在，用途按命名与代码）

| 表名 | 用途（confirmed/inferred） | 审计相关要点 | 置信度 |
|---|---|---|---|
| `strategy_runs` | 策略运行实例：代码版本、参数快照、凭证/品种、运行状态、停止原因 | `parameter_snapshot_json`、`code_hash`、`stop_reason`、`started_at/stopped_at` 为回放关键 | confirmed（schema） |
| `strategy_runtime_state` | 运行时 KV 状态（state_key/state_json/version，乐观锁） | 中间态恢复上下文 | confirmed（schema） |
| `strategy_runtime_locks` | 运行锁（lock_key/owner/fencing_token/expires_at） | 并发归属溯源 | confirmed（schema） |
| `qd_strategy_commands` | 策略指令队列（start/stop/restart/reconcile，幂等键、尝试次数、结果/错误） | 指令与结果审计 | confirmed（schema + CHECK 约束） |
| `qd_strategy_runtime_leases` | 策略运行租约（owner/fencing_token/到期/心跳） | 归属与租约溯源 | confirmed（schema） |
| `qd_worker_heartbeats` | worker 心跳（role/status/metadata） | 进程可用性 | confirmed（schema + CHECK 约束） |
| `qd_process_leases` | 进程租约 | 进程归属 | confirmed（schema） |
| `qd_strategy_notifications` | 策略通知（信号类型/渠道/标题/正文/载荷/已读） | 通知溯源 | confirmed（schema） |
| `qd_strategy_funding_fees` | 资金费现金流（正负号、外部 id、原始报文、唯一键） | 成本/现金流回放 | confirmed（schema + 迁移） |
| `qd_strategy_broker_activities` | 券商账单活动（费用/利息/贷方，分摊比例与原因） | 成本/活动回放 | confirmed（schema + 迁移） |
| `qd_strategy_review_reports` | AI 复盘报告历史（净盈亏/胜率/盈亏比/回撤/报告 JSON） | 复盘归因 | confirmed（schema） |
| `qd_ai_strategy_decisions` | AI 决策留痕（决策键、模型/提示词版本与哈希、输入/输出、错误码、延迟） | 模型决策溯源 | confirmed（schema + ai_decision.py INSERT） |
| `qd_security_logs` | 安全审计日志（action/ip/user_agent/details） | 安全审计，非交易风控 | confirmed（schema + security_service.py INSERT） |
| `qd_position_alerts` / `qd_position_monitors` | 持仓告警 / 持仓监控 | 告警上下文 | confirmed（schema）；写入路径本次未逐一核实 |
| `qd_strategy_virtual_accounts/orders/positions/trades` | 模拟盘/虚拟账户链路 | 虚拟成交台账 | 表存在 confirmed；字段本次未展开 |
| `qd_account_positions` 见 3.2 | 账户持仓镜像 | — | — |

## 5. 缺口盘点（风控 / 拒单 / 拦截计数）

> 以下结论基于本次定位到的 schema 与代码路径；未连库、未查实际数据。

| # | 缺口项 | 现状（代码/schema 证据） | 判定 |
|---|---|---|---|
| G1 | **独立风控事件表** | 未发现 `risk_events` / `risk_rejects` 一类表；风控违规码在 `account_risk.py` 组装为 `violations` 列表，拦截时写入 `pending_orders.last_error` 文本与 `qd_strategy_logs.message` 文本。`strategy_runtime_events` 是通用运行事件流水，可承载部分事件但非风控专用表。 | 缺口 confirmed：无专用风控事件表 |
| G2 | **拒单/拦截原因结构化字段** | `pending_orders.last_error`（TEXT）、`qd_quick_trades.error_msg`（TEXT）、`strategy_runtime_events.message`（TEXT）均为文本；违规码（如 `accountRisk.grossNotionalExceeded`）拼接在文本中，无独立 `reject_reason` / `violation_code` 列。 | 缺口 confirmed：原因未结构化 |
| G3 | **风险拦截计数落库字段** | 未发现拦截次数/违反次数的持久化列或计数表；`pending_orders.attempts` 是下单重试次数，不等于风控拦截计数；`account_risk_snapshot` 仅在请求时内存计算 `violations`，不落库。 | 缺口 confirmed：无拦截计数持久化 |
| G4 | **风控输入快照留痕** | 拦截时刻的名义敞口、保证金估算、费率、资金费估算、限额等只存在于内存返回 `risk_snapshot`（`phases["account_risk"]`）；schema 无对应快照表/列。 | 缺口 confirmed：拦截输入未留痕 |
| G5 | **凭证 environment 独立列** | demo/paper/live 存于 `encrypted_config` JSON 内，无独立列；列表展示靠解密推导。 | 缺口 confirmed（设计选择，非 bug） |
| G6 | **快速成交盈亏落库** | `qd_quick_trades` 无盈亏列；平仓盈亏不回写本表。 | 缺口 confirmed |
| G7 | **决策结构化快照** | 开仓信号、L1–L5 状态、止损/仓位参数未在成交表成列；仅能经意图/事件/载荷 JSON 回链，载荷完整度取决于写入方。 | 部分缺口：链路可回链，结构化程度 unknown |
| G8 | **信号时间戳口径** | `pending_orders.signal_ts` 为 BIGINT，单位（秒/毫秒）与时区本次未在代码中证实。 | unknown，需复核写入方 |
| G9 | **持仓浮动盈亏列刷新路径** | `qd_strategy_positions.unrealized_pnl/pnl_percent/equity/strategy_run_id` 在本次定位的 UPSERT 中未写入。 | 列存在 confirmed；刷新路径 unknown |

## 6. 未逐字段展开的表（来自 `db_tables.txt`，106 张）

下列表与本次交易审计主线关系较弱，本次仅核对存在性（`\dt` 清单 confirmed），字段未逐一展开：
计费/会员：`qd_billing_plans`、`qd_credits_log`、`qd_membership_fulfillments`、`qd_membership_orders`、`qd_stripe_orders`、`qd_usdt_orders`、`qd_referral_reward_accounts`、`qd_referral_reward_ledger`、`qd_referral_withdrawals`；
AI/助手：`qd_ai_calibration`、`qd_ai_copilot_messages/sessions/tool_calls`、`qd_ai_decisions`、`qd_ai_user_memories`、`qd_ai_workspace_changes/messages/threads`；
研究/回测/因子：`qd_backtest_runs/trades/equity_points`、`qd_factor_research_runs`、`qd_analysis_memory`、`qd_analysis_tasks`；
行情/标的：`qd_market_symbols`、`qd_market_symbol_aliases`、`qd_market_sync_runs`、`qd_universes/universe_members/universe_snapshots`、`qd_fundamental_snapshots/sync_items/sync_jobs/sync_schedules`、`qd_watchlist`；
指标商城/社区：`qd_indicator_codes/code_versions/comments/purchases/signal_alerts`、`qd_script_sources/source_versions/templates`；
网格：`qd_grid_actor_events/state`、`qd_grid_cells`、`qd_grid_resting_orders`；
Agent 多租户：`qd_agent_audit/idempotency/jobs/notional_reservations/paper_orders/tokens`；
其他：`qd_event_inbox`、`qd_login_attempts`、`qd_mfa_challenges`、`qd_oauth_links/states`、`qd_user_mfa`、`qd_users`、`qd_verification_codes`、`qd_manual_positions`、`qd_portfolio_rebalance_plans/orders`、`qd_strategy_event_subscriptions`、`qd_strategy_virtual_*`（见 4.8）。

## 7. 验证记录

- 事实来源文件已读：`AGENTS.md`、`docs/RULES.md`、`docs/TODO.md`、`db_tables.txt`、`db_strategy_schema.txt`、`db_schema.txt`、`insert_strategy.txt`、`migrations/init.sql`、`migrations/20260724_execution_stream_ledger.sql`。
- 代码对照（INSERT/SELECT 映射）：
  - `app/routes/quick_trade.py` — `qd_quick_trades` 落库与绑定回链。
  - `app/services/live_trading/records.py` — `qd_strategy_trades`、`qd_strategy_positions` 落库/UPSERT。
  - `app/utils/strategy_runtime_logs.py` — `qd_strategy_logs` 落库。
  - `app/routes/credentials.py`、`app/routes/alpaca.py` — `qd_exchange_credentials` 落库/更新。
  - `app/services/strategy_runtime/events.py` — `strategy_runtime_events` 落库。
  - `app/services/strategy_runtime/order_intents.py` — `strategy_order_intents` 落库。
  - `app/services/pending_orders/fill_records.py` — `strategy_order_fills` 落库。
  - `app/services/strategy_v2/live_execution.py` — `pending_orders` 落库。
  - `app/services/strategy_daily_pnl.py` — `qd_strategy_equity_snapshots` 落库。
  - `app/services/ai_decision.py` — `qd_ai_strategy_decisions` 落库。
  - `app/services/security_service.py` — `qd_security_logs` 落库。
  - `app/services/live_trading/account_risk.py`、`app/services/pending_order_worker.py` — 风控违规组装与拦截落点。
- 本次未执行：数据库连接查询、`pytest`、任何 schema 变更或数据写入。

## 8. 剩余风险与未验证项

1. **未连库核对实际列**：线上库可能存在未纳入迁移脚本的手工 `ALTER`；`db_strategy_schema.txt` 显示 `qd_strategies_trading.source_version_id` 即属此类。实际列以库内 `information_schema` 为准（本次未查）。
2. **写入路径未全覆盖**：部分表（如 `qd_strategy_positions` 盈亏列、`qd_position_alerts/monitors`、虚拟账户表）的刷新/写入代码本次未定位到，标 unknown，不代表未写入。
3. **时间口径未核实**：`signal_ts` 单位/时区、`timestamp` 与 `occurred_at` 的时区口径未逐处核对；AGENTS.md 要求时区与 `--tz` 一致，落库时间字段需在后续联调中复核。
4. **枚举取值未穷举**：`status`、`event_type`、`state` 等字段的合法枚举以代码 CHECK 约束/调用方为准，本表只列 schema 类型与注释。
5. **历史数据质量未验证**：不补造、不回溯；存量行是否存在空值/口径漂移，本次未查。
6. **范围边界**：计费、AI 助手、指标商城、社区、fundamental 等表未逐字段展开；如后续审计需要，再按同一方法补充。

## 9. 拟登记 TODO 条目（供编排者统一编号，本文件不写入 `docs/TODO.md`）

> 以下为建议条目，编号、优先级由编排者/负责人拍板；均不触碰实盘资金链路，落地前按 AGENTS.md 停止条件确认。

- TODO-A（P1）**风控事件结构化落库**：评估新增独立风控事件表（或在既有事件表扩展 `violation_code`/`risk_snapshot_json`），记录拦截时刻的违规码、限额、敞口/保证金/费率输入快照与关联 `pending_order_id`/`strategy_id`；阈值仍由分布校准，禁止按 PnL 网格搜索。
- TODO-B（P1）**拒单原因与拦截计数成列**：将 `accountRisk.*` 违规码从文本中拆出为结构化列；增加拦截计数（按策略/凭证/品种/日维度），与 `attempts`（下单重试）区分口径。
- TODO-C（P2）**凭证 environment 独立化评估**：评估是否为 `qd_exchange_credentials` 增加 `environment` 只读列（或稳定 JSON 契约），避免展示侧反复解密推导；改动属 schema，需人工确认。
- TODO-D（P2）**决策快照完整度梳理**：核对开仓链路写入 `payload_json`/`payload_json TEXT` 的字段覆盖（信号、L1–L5、仓位/止损参数），补齐回放所需上下文；明确各载荷 JSON 的字段契约。
- TODO-E（P2）**时间戳口径复核**：统一核对 `signal_ts` 单位与时区、`occurred_at/received_at/created_at` 时区，与 MT5/Python 端 `--tz` 口径对齐。
- TODO-F（P2）**持仓盈亏列刷新路径核实**：定位 `qd_strategy_positions.unrealized_pnl/pnl_percent/equity/strategy_run_id` 的刷新写入方，确认是漏写还是由同步任务回填；补单测覆盖。
- TODO-G（P3）**未展开表字段补盘**：对虚拟账户链路、网格、告警/监控等表按本方法补字段口径，形成全库数据字典。
