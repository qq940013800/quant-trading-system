# AI/ML 增强量化交易系统——系统架构设计（第二阶段冻结版）

> 标的：XAUUSD｜周期：M5｜研究层：Python 3.12（`core/` `scripts/`）｜执行层：MQL5 EA 骨架（`docs/trading/ea/`）
> 版本：design-frozen v1（2026-10-24）。本文是实现 agent 的唯一设计依据；实现不得偏离本文的接口签名与目录边界。
> 铁律对齐：AGENTS.md 三条不变量（因果单向 / 决策可审计 / 阈值来自分布）与 11 条硬规则在第⑧章逐条映射。

---

## ① 架构总览：数据流

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Python 研究层（core/）                           │
│                                                                         │
│  MT5导出CSV / 公开数据源                                                 │
│        │                                                                │
│        ▼                                                                │
│  core.data   导入→校验→时区归一(UTC+offset)→集合打标(CLEAN/KNOWN)        │
│        │  Bar(ts_utc, ts_server, offset, OHLCV, spread)                 │
│        ▼                                                                │
│  core.features  因果特征（as_of 入参断言 available_at<=bar.close）       │
│        │  FeatureFrame(df, available_at 列)                             │
│        ├── L1 位置：供需区(consolidation→impulse, KNOWN集) / Donchian    │
│        ├── L2 状态：ATR分位(CLEAN集) + ADX/Hurst + BOCPD → regime分数w   │
│        ▼                                                                │
│  core.models  标签(triple-barrier) → 基线(Logistic/Ridge)               │
│        │      → GBM(LightGBM) meta-labeling 二级分类 → 概率p/仓位系数k    │
│        │      验证：purged walk-forward + embargo（禁随机KFold）          │
│        ▼                                                                │
│  core.backtest  事件驱动 bar-by-bar（只在已收盘bar决策）                  │
│        │  成本模型：分时段点差(平静/新闻±15min/跳空) + 滑点 + 佣金        │
│        ▼                                                                │
│  core.risk   size = 风险预算 / (atr0×entryDist×point_value)             │
│        │      atr0/entryDist 入场冻结；止损单调；fractional Kelly 上限    │
│        │      日内权益熔断三态机（正常/熔断/冷却）                         │
│        ▼                                                                │
│  core.audit  每笔接受/拒绝落 Decision 快照(JSONL)，可全量还原            │
│        │                                                                │
│        ▼ 信号产物：experiments/signals/xauusd_signal_YYYYMMDD.jsonl     │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ 信号文件/ZeroMQ（单调序号+幂等键）
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  MQL5 执行层 EA（docs/trading/ea/ 骨架；实盘代码后续放入 mt5/ 受人工管控）│
│  OnTimer 拉取信号 → 校验序号/幂等 → SymbolInfo* 取规格 →                 │
│  OrderSend(检查retcode, 重试) → PositionModify(止损单调校验) →          │
│  OnTradeTransaction 确认 → 回执写回回执文件                              │
└─────────────────────────────────────────────────────────────────────────┘
```

**设计哲学（来自研究结论）**：AI/ML 是"增强"而非"预言机"。ML 只嵌入三处——L2 regime 分数、L3 meta-labeling 过滤、不确定性→仓位映射；方向骨架与风控始终是规则层。预期产出是"减少错误信号、降低回撤与成本占比"，不是"提高方向准确率"。

---

## ② 模块划分与职责

| 模块 | 路径 | 职责 | 禁止事项 |
|---|---|---|---|
| 数据管线 | `core/data/` | CSV 导入、校验、时区归一、缺口检测、CLEAN/KNOWN 打标、合成数据生成 | 禁止读取静默集；禁止用未来 bar 填缺口 |
| 特征工程 | `core/features/` | ATR/vol/ADX/Hurst/供需区/形态特征；全部带 `as_of` 因果断言 | 禁止全样本 z-score；禁止特征读 `t>=当前bar` 数据 |
| AI/ML 模型 | `core/models/` | triple-barrier 标签、基线、GBM、meta-labeling、purged CV、漂移监控 | 禁止随机 KFold；禁止按 Sharpe 网格搜超参 |
| 回测引擎 | `core/backtest/` | 事件驱动 bar 循环、成本模型、成交模拟、绩效指标 | 禁止 intra-bar 决策；禁止零成本假设 |
| 风控资金 | `core/risk/` | 仓位公式、atr0/entryDist 冻结、止损单调、熔断 | 禁止硬编码点值/手数/阈值 |
| 审计 | `core/audit/` | Decision 快照落盘、回放校验 | 禁止省略任何被拒信号 |
| 入口脚本 | `scripts/` | 数据导入、阈值校准(distribution)、实验登记、回测运行 | 禁止手工改 registry.yaml 的 trials_N |

`scripts/`、`tests/`、`ops/` 已有平台层文件（bump_version、score_agent_eval 等）保持不动；交易相关新增文件见第④章清单，命名不得冲突。

---

## ③ 接口契约（冻结，实现不得改签名）

### 3.1 核心数据结构 schema

**Bar**（不可变，数据层最小单元）
```python
@dataclass(frozen=True)
class Bar:
    symbol: str                      # "XAUUSD"
    ts_utc: pd.Timestamp             # 规范时间：bar.close 对应的 UTC 时刻（主键）
    ts_server: pd.Timestamp          # 经纪商服务器时间（审计用，不参与计算）
    server_offset_hours: float       # 该 bar 收盘时刻的服务器偏移（DST 切换日单独打标）
    open_: float                     # 计价货币 USD，2 位小数（XAUUSD）
    high: float
    low: float
    close: float
    tick_volume: float               # MT5 tick_volume（非真实成交量，标注语义）
    spread_points: Optional[float]   # 点差（点），无数据时 None
```
不变量：`low <= open_,close <= high`；`ts_utc` 单调递增；`available_at(bar) = ts_utc`（特征只能用 ts_utc <= 当前 ts_utc 的 Bar）。

**FeatureFrame**（特征矩阵）
```python
# pandas DataFrame，index = ts_utc；强制附带列：
#   available_at: pd.Timestamp   # 该行特征实际可被使用的时刻（=生成所用最新bar.close）
# 约定：对行 t 做任何计算前，断言该行用到的所有输入数据 available_at <= t
FeatureFrame = pd.DataFrame  # 附契约：禁止 inplace 修改历史行；新增特征列须重跑全流水线
```

**Signal**（L3 专家候选触发）
```python
@dataclass(frozen=True)
class Signal:
    signal_id: str                   # 幂等键：f"{symbol}_{bar_ts_utc}_{expert}_{dir}"
    bar_ts_utc: pd.Timestamp         # 触发依据 bar 的收盘时刻
    expert: str                      # "trend_breakout" | "mean_reversion" | "range"
    direction: int                   # +1 多 / -1 空
    price_ref: float                  # 参考价（触发 bar.close）
    atr0: float                      # 入场冻结 ATR
    entry_dist: float                # 入场到止损距离（默认 2×atr0，CLEAN 分布校准）
    l1_in_zone: bool                 # 是否处于供需区边界内（KNOWN 集构建）
    regime_weights: dict[str, float] # w_trend / w_mr / w_range（连续，非 0/1）
    meta_p: Optional[float]          # meta-labeling 二级模型输出开仓概率（无模型时 None）
```

**Decision**（审计快照，接受/拒绝都必须产生一条）
```python
@dataclass(frozen=True)
class Decision:
    decision_id: str                 # 单调递增序号（跨进程信号同步用）
    signal: Signal
    feature_snapshot: dict            # 各层输入特征值（as_of 时刻取值）
    model_version: str                # 模型版本号（无模型时 "rules-vN"）
    risk_state: "RiskState"
    accepted: bool
    reject_reason: Optional[str]      # 如 "meta_p<quantile_30" / "news_window" / "circuit_breaker"
    final_signed_lots: float          # 接受时的最终手数（拒绝为 0）
    threshold_dataset: str            # "CLEAN" | "KNOWN"（本决策阈值来源集）
    decision_rule_version: str        # 冻结的决策规则版本
    r_multiple_at_close: Optional[float]  # 出场后回填（事后归因用）
```

**RiskState**
```python
@dataclass
class RiskState:
    equity: float
    atr0: float                      # 入场时冻结，持仓期不变
    entry_dist: float                # 入场时冻结，R 倍数分母
    stop_price: float                # 当前止损价（只允许向盈利方向移动）
    heat_units: int                  # 同向累计单位数（上限由 config，CLEAN 校准）
    circuit_state: str               # "normal" | "breaker" | "cooldown"
    drawdown_tier: float             # 回撤档位系数（海龟分级降档：每 -10% ×0.8）
```

### 3.2 模块间函数签名

```python
# core/data/loader.py
def load_bars(csv_path: str, symbol: str, tz_offset_hours: float) -> list[Bar]: ...
def validate_bars(bars: list[Bar]) -> ValidationReport: ...   # 含缺口清单/异常值标记
def split_dataset(bars: list[Bar], splits_path: str) -> dict[str, list[Bar]]: ...
    # 返回 {"CLEAN":[...], "KNOWN":[...], "HELD_OUT":[...]}；静默集永不读入

# core/data/synthetic.py
def make_synthetic_bars(seed: int, n: int, kind: str = "martingale") -> list[Bar]: ...
    # kind: "martingale" | "trend_regime"；确定性种子；供"pipeline 无泄漏"自检用

# core/features/base.py
def as_of(feature_func): ...   # 装饰器：强制 feature_func(history: list[Bar], as_of: pd.Timestamp)
    # 实现内断言：history 中所有 bar.ts_utc <= as_of；违反即 raise LookAheadError

# core/models/labels.py
def triple_barrier_labels(bars: list[Bar], atr: pd.Series,
                          tp_mult: float, sl_mult: float,
                          max_holding_bars: int) -> pd.Series: ...  # +1/-1/0

# core/models/cv.py
def purged_walk_forward(n: int, embargo_bars: int, n_splits: int) -> list[tuple[np.ndarray, np.ndarray]]: ...
    # embargo_bars >= 标签窗口长度；返回 (train_idx, test_idx) 序列

# core/backtest/engine.py
def run_backtest(bars: list[Bar], strategy, cost_model, risk_cfg) -> BacktestResult: ...
    # BacktestResult: equity_curve, trades[list[Decision]], metrics[dict]

# core/backtest/costs.py
def spread_at(bar: Bar, news_window: set[pd.Timestamp]) -> float: ...  # 三档：平静/新闻/跳空
def slippage_points(bar: Bar, lot_fraction_of_volume: float) -> float: ...

# core/risk/sizing.py
def target_lots(equity: float, risk_pct: float, atr0: float,
                point_value: float, min_lot: float, lot_step: float,
                kelly_cap: float) -> float: ...

# core/risk/stops.py
def update_stop(current_stop: float, new_stop: float, direction: int) -> float: ...
    # 多头：只升不降；空头：只降不升；放宽请求 raise StopWideningError

# core/audit/record.py
def write_decision(path: str, decision: Decision) -> None: ...   # JSONL 追加，单行一条
```

### 3.3 异常体系（禁止 `except Exception: pass`——硬规则 9）
`LookAheadError`（特征前视）、`StopWideningError`（止损放宽）、`AsOfContractError`（as_of 断言失败）、`ValidationError`（数据校验失败）、`RetcodeError`（MQL5 返回非 DONE/PLACED）。所有异常必须带上下文（symbol/ts/layer 字段）。

---

## ④ 目录与文件规划（新建清单；已有文件一律不动）

```
core/
├── __init__.py
├── config.py                  # config 加载层：从 configs/*.yaml 读，无硬编码阈值
├── data/
│   ├── __init__.py
│   ├── bar.py                 # Bar schema、ValidationReport
│   ├── loader.py              # CSV→list[Bar]
│   ├── validator.py           # 单调时间戳/OHLC一致/缺口检测/异常值标记
│   ├── timezone.py             # UTC 归一、broker offset、DST 表
│   ├── splits.py              # CLEAN/KNOWN 打标；静默集路径显式拒绝
│   └── synthetic.py           # 确定性合成 bar（martingale/trend_regime）
├── features/
│   ├── __init__.py
│   ├── base.py                # as_of 装饰器、LookAheadError
│   ├── atr.py                 # Wilder ATR
│   ├── volatility.py          # realized vol、expanding 归一化
│   ├── regime.py              # ADX/Hurst、分位门控、regime 分数 w 向量
│   ├── structure.py           # swing 点、consolidation→impulse 供需区（KNOWN 集）
│   └── patterns.py            # FVG/吞没等布尔特征（仅 L3 加成，不独立触发）
├── models/
│   ├── __init__.py
│   ├── base.py                # Model protocol（fit/predict_proba/version）
│   ├── baseline.py            # LogisticRegression/Ridge（必须先打赢）
│   ├── gbm.py                 # LightGBM 封装（max_depth 3-6, early stopping）
│   ├── labels.py              # triple barrier
│   ├── cv.py                  # purged walk-forward + embargo
│   ├── meta_label.py          # 二级分类器：候选信号→(p, k)
│   └── drift.py               # PSI/KS 特征漂移 + 滚动命中率监控
├── backtest/
│   ├── __init__.py
│   ├── engine.py              # 事件驱动 bar 循环
│   ├── costs.py               # 分时段点差/滑点/佣金
│   ├── broker.py              # 成交模拟（部分成交比例限制）
│   └── metrics.py             # Sharpe/Sortino/Calmar/MDD/PF/期望值/PSR
├── risk/
│   ├── __init__.py
│   ├── sizing.py              # vol-target 手数、fractional Kelly 上限
│   ├── stops.py                # atr0 冻结、止损单调
│   └── circuit.py             # 日内权益熔断三态机
└── audit/
    ├── __init__.py
    ├── record.py              # Decision schema、JSONL 写盘
    └── replay.py              # 审计回放：快照→重算→比对（测试用）

scripts/
├── ingest_xauusd.py           # MT5 CSV→校验→打标→parquet
├── calibrate_regime.py         # 已有约定：--mode distribution（只从分布取分位数）
├── train_meta_label.py        # purged WF 训练二级模型，产物版本化
├── backtest_run.py            # 跑回测并输出 BacktestResult 报告
└── run_gate_experiment.sh       # 已有约定：--registry --variant --mode dryrun；只允许原子递增 trials_N

tests/
├── test_data_loader.py         # 校验规则、缺口检测
├── test_timezone_dst.py       # DST 切换日 offset 正确性
├── test_synthetic.py           # 合成数据可复现（同种子同结果）
├── test_features_causal.py     # 前视守卫：as_of 打乱时间索引必崩
├── test_regime_no_lookahead.py # regime 统计只用 CLEAN 已收盘数据
├── test_labels_purged.py      # 标签窗口/embargo 正确性
├── test_backtest_costs.py     # 新闻窗口点差放大、滑点量级
├── test_risk_monotonic.py     # 止损放宽必 raise（复用 fixtures/causal_guard/）
├── test_atr0_freeze.py        # R 倍数用入场冻结值
└── test_audit_replay.py       # Decision 快照可全量还原每笔接受/拒绝

experiments/
├── signals/                   # EA 信号 JSONL（运行产物）
└── reports/                   # 回测/实验报告（Markdown，含 DSR/PSR 复核）

docs/trading/ea/               # MQL5 骨架（见第⑥章清单）
```

> 注：`docs/data_splits.md`（静默集路径清单）按 AGENTS.md 引用，本设计只读其约定、不读取静默数据本体；实现 agent 读 `splits_path` 指向的打标文件即可。

---

## ⑤ 依赖策略（最小依赖原则）

**基线已可用（.venv 现状）**：Python 3.12.10、pandas 3.0.6、numpy 2.5.4、pytest 9.1.1。研究层核心（数据/特征/回测/风控/审计）只用 numpy+pandas 即可实现，这是必须保持的——任何模块不得把 GBM 依赖作为 import 期硬依赖。

**需要安装（建议执行）**：
```powershell
D:\Trader\.venv\Scripts\pip install scikit-learn lightgbm
```
- `scikit-learn`：Ridge/Logistic 基线 + permutation importance（OOS 特征可信度）。
- `lightgbm`：GBM 主候选（表格特征事实标准）；max_depth 限制 3–6、early stopping、subsample。
- **纯 numpy 备选**：若安装失败，`core/models/baseline.py` 提供 IRLS 逻辑回归纯 numpy 实现；`core/models/gbm.py` import 失败时降级为"无 GBM 模式"（只用规则+基线），pytest 必须在无 lightgbm 时仍全绿（用 `pytest.importorskip` 隔离 GBM 测试）。

**执行层联调（可选，不进研究层依赖）**：
```powershell
D:\Trader\.venv\Scripts\pip install MetaTrader5
```
仅用于 `scripts/ingest_xauusd.py` 从本机 MT5 终端导出历史数据；CI/无终端环境跳过。

**禁止引入**：qlib 全栈、TensorFlow/PyTorch（DL 方向预测第二阶段不做）、DRL 库、任何按绩效网格搜参的库。

---

## ⑥ MQL5 EA 骨架结构（落盘 `docs/trading/ea/`，实现参考，不入 mt5/）

> 边界：本目录只放"骨架设计与示例代码"；真正受管控的执行代码后续经人工确认后放入 `mt5/`。EA 常量/风控阈值一律 `input` 化，禁止写死。

```
docs/trading/ea/
├── README.md                  # 对接说明
├── SIGNAL_CONTRACT.md         # 信号 JSONL 协议（字段/序号/幂等/回执）
├── XAUUSD_EA.mq5             # EA 主骨架（OnInit/OnTick/OnTimer/OnTradeTransaction）
└── trade_utils.mqh            # OrderSend 封装 + retcode 重试 + 止损单调校验
```

**信号对接方式（推荐文件 JSONL，备选 ZeroMQ）**：
- Python 侧写 `experiments/signals/xauusd_signal_YYYYMMDD.jsonl`，每行一条：
  `{seq, symbol, signal_id(幂等键), direction, atr0, entry_dist, sl_price, tp_price_or_null, lots, ts_utc, decision_rule_version}`
- EA 在 `OnTimer`（每 5s，不堵 OnTick 队列）扫描新增行；**单调序号 + signal_id 幂等键**，已处理序号直接跳过（防重复下单）。
- 回执写 `experiments/signals/ack_YYYYMMDD.jsonl`：`{signal_id, retcode, fill_price, fill_time_server, status}`。
- `atr0/entryDist/sl_price` 由 Python 侧冻结后下发，EA 不重算（硬规则 4：R 倍数用入场冻结值）。

**trade_utils.mqh 必须实现的封装（对齐硬规则 7/8）**：
1. `bool SafeOrderSend(const MqlTradeRequest& req, MqlTradeResult& res, int retries=3)`：发送后**必须读 `res.retcode`**；`TRADE_RETCODE_DONE(10009)`/`PLACED(10008)` 视为成功；REQUOTE(10004)/PRICES_OFF 等按指数退避重试，其余记录上下文日志后放弃（禁止静默吞错）。
2. `bool MonotonicModifySL(ulong ticket, double new_sl)`：修改前校验方向——多头只允许新 SL >= 当前 SL，空头只允许新 SL <= 当前 SL；放宽请求直接拒绝并告警。
3. `void ReadSymbolSpecs()`：点值、digits、最小手数、手数步长、合约规模一律 `SymbolInfoDouble/Integer` 动态读取；`lots` 按 `lot_step` 向下取整。
4. 时区：`input string InServerOffset`（如 "EET"）+ `input bool InDstAuto`；EA 内部把信号 `ts_utc` 换算为服务器时间对齐，禁止写死 UTC+2/+3。
5. 新闻窗口冻结：`input string InNewsCsv`（事件 UTC 时间列表）；窗口内（默认 ±15min，可配）拒绝新开仓。
6. 日权益熔断：OnTimer 读 `AccountInfoDouble(ACCOUNT_EQUITY)`，当日回撤超阈值（input，参照 3% 档）进入 breaker 态：禁止新开仓、只允许平仓；冷却恢复须人工重启或次日 00:00 服务器时间重置。

---

## ⑦ 验收清单（实现 agent 完成标准）

**A. 测试**
1. `pytest -q` 全绿（含既有 `test_enum_mapping.py`、`test_agent_config.py`，不得放宽任何黄金集断言）。
2. 前视守卫测试：对特征函数喂"打乱时间索引"的合成数据，`LookAheadError` 必抛；`tests/fixtures/causal_guard/` 六组夹具（shift_neg/center_true/stop_widen/atr_recompute/clean/intrabar）全部通过。
3. 无 lightgbm 环境下 `pytest -q` 仍全绿（GBM 测试 importorskip）。

**B. 因果与集合分离**
4. ATR/vol/Hurst 统计量只从 CLEAN 集估计；供需区只用 KNOWN 集构建；代码审查确认无 `t>=当前bar` 读取。
5. triple-barrier 标签 + purged walk-forward + embargo 在单测中断言：embargo 宽度 >= 标签窗口；训练集不含与测试标签重叠样本。

**C. 风控与执行**
6. `update_stop` 对放宽请求必 raise；`target_lots` 输出经 `lot_step` 取整且 <= fractional Kelly 上限。
7. 回测成本断言：新闻窗口点差 > 平静窗口；零成本开关会显著改变绩效（防止成本模型被旁路）。

**D. 可审计**
8. 每笔接受/拒绝都有 Decision JSONL；`audit/replay.py` 能用快照完整还原某笔决策（特征值/模型版本/阈值来源集/最终手数），含 reject_reason。

**E. 实验纪律**
9. 任何 variant 实验走 `run_gate_experiment.sh`：`trials_N` 只增不减、`decision_rule` 实验前冻结；报告附 OOS 多路径分布（不只是单条 Sharpe）与 PSR/DSR 复核位。

**F. 未验证项标注**（实现报告必须显式列出）：MT5 实盘执行（retcode 重试/滑点/幂等）未验证；经纪商差异（点差/合约规格）未验证；XAUUSD M5 上 GBM 相对线性基线的 OOS 增益未验证。

---

## ⑧ 与 AGENTS.md 不变量/硬规则逐条映射

| AGENTS.md 条款 | 本设计落点 |
|---|---|
| 不变量1 因果单向 | `as_of` 装饰器 + `available_at` 列 + `LookAheadError`；intra-bar 不决策（硬规则5） |
| 不变量2 决策可审计 | `Decision` schema + JSONL + replay.py；拒绝信号同样落盘 |
| 不变量3 阈值来自分布 | `calibrate_regime.py --mode distribution`；configs 人工审核；禁绩效网格 |
| 硬规则2 集合分离 | CLEAN 估统计量 / KNOWN 建结构 / 静默集显式拒绝 |
| 硬规则3 L1→L2→L3 单向 | features/structure.py(L1) → regime.py(L2) → meta_label.py(L3)，L3 不反哺 L1 |
| 硬规则4 止损单调/atr0冻结 | `RiskState.atr0` 冻结 + `update_stop` 单调校验 + EA `MonotonicModifySL` |
| 硬规则6 时区一致 | `Bar.ts_server+server_offset_hours` 随 DST 打标；EA 与 Python 共用同一 offset 配置 |
| 硬规则7 异步返回检查 | `SafeOrderSend` 重试封装 + `RetcodeError` |
| 硬规则8 禁硬编码 | sizing/EA 全部走 config + `SymbolInfo*` |
| 硬规则9 禁 except pass | 异常体系（3.3）全部带上下文 |
| 硬规则10 单测随改 | 第⑦章验收清单；黄金集断言不放宽 |
| 硬规则11 trials_N | 实验脚本原子递增；本设计不提供任何手工登记路径 |
