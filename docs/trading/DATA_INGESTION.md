# XAUUSD M5 数据接入文档（DATA INGESTION SPEC）

> 本文冻结数据管线的列 schema、时间语义、校验规则、无前视合成数据策略与目录规划。
> 服务 `core/data/`（loader/validator/timezone/splits/synthetic）与 `scripts/ingest_xauusd.py`。
> 时区铁律（AGENTS.md 硬规则6）：MT5 服务器偏移必须与 Python 端 `--tz` 一致，禁止硬编码。

---

## ① 列 schema（导入 CSV 的标准列）

| 列名 | 类型 | 单位/语义 | 必填 |
|---|---|---|---|
| `timestamp_server` | string（ISO8601 或 MT5 默认 `yyyy.MM.dd HH:mm`） | bar 的**服务器时间**收盘时刻，原始导入列 | 是 |
| `open` / `high` / `low` / `close` | float（USD/盎司，XAUUSD 通常 2 位小数） | bar 四价；计价货币 USD | 是 |
| `tick_volume` | float | MT5 tick_volume（成交笔数代理，**非真实成交量**，特征文档须注明） | 是 |
| `spread` | float（点） | 该 bar 平均点差（`close*100` 与 bid/ask 差换算的点）；无则缺失 | 否 |
| `real_volume` | float | MT5 外汇/贵金属不提供，留空即可 | 否（忽略） |

**归一化后内存 schema（`core/data/bar.py::Bar`）**：导入后一律转成 UTC 主键：

```
ts_utc            # timestamp_server - server_offset_hours（DST 感知），作为全局主键
ts_server         # 原始服务器时间（仅审计/对账，不参与任何特征计算）
server_offset_hours  # 该 bar 收盘时刻的偏移（DST 切换日 ±0.5/±1h 跳变单独打标）
open_, high, low, close
tick_volume
spread_points     # 无数据为 None，回测成本模型退化为"平静档默认点差"
```

不变量：`low <= open, close <= high`；`ts_utc` 单调严格递增；`Bar` 为 frozen dataclass，不可就地改价。

---

## ② 时间戳语义与时区

- **唯一计算时钟 = UTC**。所有特征、标签、回测、信号文件时间戳一律 `ts_utc`；`ts_server` 仅用于与 MT5 对账。
- **Broker server offset**：主流外汇/黄金券商服务器时间为 EET（冬季 UTC+2、夏季 UTC+3，跟随美国 DST 切换）；少数券商用 GMT+0 无 DST。偏移不是常数——`core/data/timezone.py` 提供一张 **DST 切换表**（按年记录切换日，从导入数据或经纪商文档校准），逐 bar 计算 `server_offset_hours`，不允许单一全局常数。
- **配置一致性**：Python `scripts/ingest_xauusd.py --tz EET`（或显式 `--offset-table path`）与 MQL5 EA 的 `input InServerOffset` 必须指向同一张表；两侧切换日表不一致即视为配置错误，测试中对拍。
- **DST 处理**：切换日当天存在重复/缺失的本地时间，一律以 UTC 归一化后消除歧义；切换日打标 `is_dst_transition=True` 供审计。
- **每日收盘锚**：纽约 17:00（美东）= 服务器每日收盘锚；session 划分（亚/欧/美盘）由 UTC 时间推出，不依赖未来事件。

---

## ③ 数据来源

1. **MT5 导出 CSV（主源）**：MT5 终端 → 历史中心 → XAUUSD → M5 → 导出。列形如 `<DATE> <TIME> <OPEN> <HIGH> <LOW> <CLOSE> <TICKVOL> <VOL> <SPREAD>`；`scripts/ingest_xauusd.py` 做列名映射。
2. **本机 MT5 Python 包（自动导出，可选）**：`pip install MetaTrader5` 后用 `copy_rates_from_pos()` 批量拉历史 M5；仅当本机终端登录经纪商账户可用时使用。
3. **公开数据源（补充/交叉校验，可选）**：主流行情商的 XAUUSD M5 历史导出；仅用于校验 MT5 导出是否有缺段，**不与主源混用**（时间戳口径必须重新归一化后才能入库）。
4. **禁止**：把"今天还在的品种/交易所列表"类幸存者偏差来源引入；单资产 XAUUSD 影响小，但仍只认 point-in-time 导出。

---

## ④ 校验规则（`core/data/validator.py::validate_bars`）

| 规则 | 处理 |
|---|---|
| 时间戳单调递增 | 违反即 `ValidationError`（数据损坏，不自动修） |
| OHLC 一致性（low≤o/c≤high） | 违反标记 `bad_ohlc=True`，该 bar 隔离到异常清单 |
| 价格非负、close>0 | 违反隔离 |
| 缺失 bar（应有 M5 间隔而无数据） | 生成**缺口清单**（起止 UTC、缺失根数）；**禁止用未来信息回填**（前视）；缺口由 `core/gap_normalizer.py` 按既有流程产出 gate 配置，经人工审核后入 configs |
| 异常值（单 bar 涨跌 > N×滚动 ATR，N 取 CLEAN 分布分位） | 标记 `outlier=True` 但保留（不删文件、不改历史），回测可选过滤 |
| 重复时间戳 | 去重保留首条并记录 |
| spread 负值/缺失 | 缺失置 None；负值隔离 |

校验报告 `ValidationReport`：总 bar 数 / 隔离数 / 缺口清单 / DST 切换日清单 / 异常值清单。任何"自动修数据"行为都必须是因果的（只用已收盘历史），且全程留痕。

---

## ⑤ 无前视合成数据（`core/data/synthetic.py`）

用途：单测、以及"pipeline 无泄漏自检"（在 martingale 合成数据上跑完整研究 pipeline 若仍盈利，说明前视泄漏）。

- **确定性**：固定 `seed`，同种子逐字节复现（`np.random.default_rng(seed)`）。
- **生成模式**：
  - `martingale`：纯随机游走（μ=0，σ=目标 ATR），无趋势无 regime——任何策略在此"盈利"即泄漏。
  - `trend_regime`：两段 regime（低波趋势段 + 高波震荡段）切换，带已知断点——测试 regime 识别与 deadband。
- **标签可用**：合成数据上 triple-barrier 标签可精确计算（因为路径已知）。
- **禁止**：合成数据上做任何参数标定/阈值校准（标定只允许用真实 CLEAN 集）。

---

## ⑥ 数据目录规划

```
D:\Trader\
├── data/                         # 新建：原始与归一化数据（不入 git，.gitignore）
│   ├── raw/mt5/XAUUSD_M5_*.csv        # MT5 原始导出
│   ├── clean/XAUUSD_M5.parquet        # 校验+UTC归一后的主数据（列式，pandas 读）
│   └── splits/split_dates.yaml        # CLEAN/KNOWN/静默集的日期区间打标（人工维护）
├── experiments/
│   ├── gate_XAUUSD.yaml               # 缺口清洗产物（人工审核后才允许入 configs/）
│   └── reports/                        # 回测/实验报告
```

- **集合分离落地**：`data/splits/split_dates.yaml` 声明三段日期区间：
  - `CLEAN`：估计 ATR/vol/Hurst 等统计量、标定阈值的区间；
  - `KNOWN`：构建供需区结构的区间；
  - `HELD_OUT`（静默集）：**代码路径上显式拒绝读取**——`core/data/splits.py` 遇到静默集文件路径直接 raise，呼应 AGENTS.md"禁止读静默集数据"。
- `data/` 目录、静默集数据本体均不在本设计交付范围；本文件只约定其 schema 与边界。

---

## ⑦ 与既有流程的衔接

- 缺口清洗走既有命令：`python core/gap_normalizer.py --sym XAUUSD --data data/raw/mt5/XAUUSD_M5.csv --out experiments/gate_XAUUSD.yaml`（产物人工审核后再入 `configs/`）。
- 阈值校准：`python scripts/calibrate_regime.py --mode distribution`（只从 CLEAN 分布取分位数，默认不看 PnL）。
- 本文档不创建任何数据文件；所有导入产物由 `scripts/ingest_xauusd.py` 在实现阶段生成。
