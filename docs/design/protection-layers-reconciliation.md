# 四套持仓保护层口径对照（只读勘察）

> 切片 #310 · 2026-11-12 · 状态：只读对照，未改后端、未动阈值常量。
> 目的：在接线 core 保护底座之前，先把现有四套保护层的口径基准、一致项、分裂点与覆盖缺口登记成单一事实源，避免再次出现 TODO 口径分裂。
> 行号为勘察时点快照，可能随版本漂移；定位以模块 + 方法名为准。

## 1. 口径基准

| 层 | 模块 | 口径基准 | 副作用 | 阈值来源 |
|---|---|---|---|---|
| 研究层底座 | `core/risk/protection.py` | entry_atr/entry_dist 冻结，**R 倍数 + ATR 倍数** | 纯函数，不下单/不写库 | 阈值由调用方按分布校准后入参，底座不写死 |
| 后端旧主链 | `backend_api_python/app/services/risk_engine.py` | ATR0 + **R 倍数** | 回调下单/告警（`_reduce_position_callback` / `_close_position_callback` / `_create_alert`） | dataclass 字段**硬编码默认值**（见 S2） |
| 后端 V2 共享层 | `backend_api_python/app/services/strategy_v2/protection.py` | **价格百分比** + 秒级时间限制；无 ATR/R | 纯决策（`ProtectionEngine.evaluate_bar/price`） | spec 百分比入参 |
| 执行适配层 | `backend_api_python/app/services/live_trading/native_protection.py` | 绝对 SL/TP 价 + 百分比跟踪 | 交易所原生 reduce-only 挂单适配 | 阈值来自上游 payload |

## 2. 能力覆盖对照

| 保护能力 | core 底座 | risk_engine | V2 protection | native |
|---|---|---|---|---|
| 硬止损 | ✅ `stops.evaluate_stops` 编排 | ✅ `_check_stop_loss_trigger` | ✅ `stop_loss_pct` | ✅ 原生止损单 |
| 止盈 | ✅ R 倍数 | ✅ R 倍数 | ✅ `take_profit_pct` | ✅ 原生止盈单 |
| 跟踪止损 | ✅ `stops` 编排 | ✅ `_update_trailing_stop`（R 激活 + ATR 距离，单调） | ✅ `trailing_stop_pct` + `trailing_activation_pct` | ✅ 百分比跟踪 |
| 保本止损 | ✅ `stops` | ✅ `_update_breakeven_stop`（0.5R 激活 + 缓冲） | ❌ | ❌ |
| 吊灯退出 | ✅ `evaluate_chandelier` | ✅ `_update_chandelier_exit` | ❌ | ❌ |
| 分批止盈 | ✅ `evaluate_scale_out` | ✅ `_check_scale_out` | ❌ | ❌ |
| 利润回吐 | ✅ `evaluate_profit_retracement` | ✅ `_check_profit_retracement` | ❌ | ❌ |
| 时间止损 | ✅ `stops` | ✅ | ✅ `time_limit_seconds` | ❌ |
| 审计快照 | ✅ `ProtectionDecision` | 告警 + 回调记录 | `ProtectionDecision` | 交易所响应 |

## 3. 已对齐项（core ↔ risk_engine）

- **吊灯**：多头 `peak - atr0×mult`、空头 `peak + atr0×mult`；候选须优于当前止损（向盈利方向收紧）才覆盖；激活前提 `trailing_activated`。两侧语义一致。
- **分批**：`r ≥ level_r` 触发，`done` 标记跳过已完成级别，剩余比例 `remaining × (1 - ratio)`。
- **回吐**：`r ≥ min_r`（后端默认 1R）、峰值利润与当前利润均为正、回撤比例 `(peak - current)/peak ≥ pct` 才清剩余。
- **止损单调**：跟踪/吊灯/保本只允许向盈利方向移动，两侧均校验方向。

## 4. 分裂点与缺口

### S1 分批单 bar 档位推进语义不一致
- core `evaluate_scale_out`：同一根 bar **只推进一个**未完成级别。
- risk_engine `_check_scale_out`：`for` 循环遍历全部级别，同一 bar 内**可连续推进多档**。
- 待决策：统一为单 bar 一档（更保守、可审计）还是允许多档；属策略语义，需 RES 确认后再改。

### S2 risk_engine 阈值为硬编码默认值（硬规则 3 隐患）
- `RiskConfig` / `Position` 默认：`atr_multiplier=2.0`、`trailing_activation_r=1.0`、`trailing_distance_atr=2.0`、`chandelier_atr_mult=3.0`、`scale_out_levels=[2.0,3.0]`、`scale_out_ratios=[0.5,0.25]`、`profit_retracement_pct=0.30`、保本 `0.5R` + 缓冲。
- `risk_engine.py` 尾部另有硬编码 `3.0R` / `2.0R` 决策分支。
- 这些数值未走 CLEAN 集分布校准，也未由 config 注入。**接线前必须改为分布校准产物 + config 注入**；触阈值/`configs/` 红线，须人工显式确认，ORCH 不擅改。

### S3 基准口径分裂：百分比 ↔ ATR/R
- V2 protection 全链路价格百分比；core 与 risk_engine 用 ATR/R。两套基准并行，未建映射。
- 待决策：统一到哪套基准、跨基准换算（需 ATR/入场价）如何审计；需 RES 出 ADR。

### S4 保本 / 时间止损口径分裂（core ↔ risk_engine ↔ V2，已逐行核对 core 与 V2）

**保本**：
- core `stops.update_breakeven_stop`：当前 R ≥ `breakeven_r`（默认 1.0R）才激活，保本价 = `entry + direction × breakeven_offset_r × entry_dist`（默认 +0.1R 偏移，R/ATR 距离口径）。
- risk_engine：保本价 = 入场价 ×(1 ± `breakeven_buffer`)，缓冲为价格百分比；激活阈值 0.5R。
- **分裂**：① 激活 R 阈值不同（core 1.0R vs risk_engine 0.5R）；② 保本偏移基准不同（core `offset_r × entry_dist` 的 R 距离 vs risk_engine 价格百分比 buffer）。
- V2 `ProtectionSpec` **无保本字段/逻辑**，属能力缺口，不是口径分歧。

**时间止损**：
- core `check_time_stop`：`bars_held ≥ max_holding_bars`（K 线根数）**且** `max_favorable_r < breakeven_r`，bar 计数 + 未达保本 R 双门控。
- V2 `_time_limit_reached`：墙钟秒数 `(ts - opened_at).total_seconds() ≥ time_limit_seconds`，纯时间到即平，无 R 条件、无 bar 计数。
- **分裂**：基准不同（bar 数 vs 秒）；门控不同（core 叠加未达保本 R 条件，V2 纯时间门控）。
- risk_engine 时间止损本轮未逐行核，仍列未验证。

### S5 core 底座在后端运行时未激活（#209 架构阻塞）
- 后端容器运行时不 import `core`；`gate_shadow.py` 纯函数 shadow 适配器已建，尚未在 worker 进程接线。
- 取舍（core 进容器 vs 适配器侧复制口径）待评估；在此之前后端行为不代表 core 底座已上线。

## 5. 待决策门（ORCH 不擅自推进）

| 编号 | 事项 | 触发红线/前置 |
|---|---|---|
| D1 | risk_engine 硬编码阈值改为 CLEAN 分布校准产物并由 config 注入 | 风控阈值 / `configs/`，须人工显式确认 |
| D2 | 百分比 ↔ ATR/R 基准统一方向与换算映射 | 需 RES 出 ADR |
| D3 | 分批单 bar 一档 / 多档语义统一 | 策略语义，需 RES 确认 |
| D4 | core 进容器 vs 适配器侧复制口径 | #209 架构取舍评估 |
| D5 | 后端保护链接 core `decide_protection` 底座 | 依赖 D1/D4 闭环 + 容器镜像刷新后端到端复验 |

## 6. 未验证项

- 后端容器常驻进程/镜像是否含当前 core 底座改动：**未验证**（S5）。
- 实盘/经纪商差异、原生保护单在各所的挂单语义：**未验证**。
- risk_engine 时间止损逐行口径：**未核对**；core ↔ V2 保本/时间止损口径已逐行核对（见 S4）。
