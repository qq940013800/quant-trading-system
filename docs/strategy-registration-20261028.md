# 策略注册与匹配引擎接入 · 2026-10-28

## 1. 任务概述
把现有 3 个演示策略接入量化交易系统的策略匹配引擎，建立"市场状态 → 策略权重"的路由层，
并配套单测。不触碰 `registry.yaml`（实验登记用）、`configs/`、`mt5/`、`secrets/`、`runtime/`、`ledger/`。

## 2. 3 个演示策略代码位置

| # | 策略名 | 类型 | 代码位置 | 状态 |
|---|--------|------|----------|------|
| 1 | `DemoBreakoutStrategy` | 唐奇安通道突破（趋势跟踪） | `core/backtest/engine.py:105` | **真实可跑**，pipeline 自检用 |
| 2 | `MLTrendStrategy` | 海龟突破 + 逻辑回归 meta-label 过滤 | `core/models/ml_trend_strategy.py:65` | **真实可跑**，`tests/test_ml_trend_strategy.py` 覆盖 |
| 3 | 均值回归（`mean_reversion`） | RSI/布林带反向 | 仅在 `core/integration/gatekeeper.py:130` 模拟数据中以 `type=mean_reversion` 出现 | **未实现可交易类**，本次按路由画像登记为占位 |

> 诚实标注：第 3 个策略在 gatekeeper 模拟数据中被引用，但代码库中没有对应的策略类实现。
> 本次只在路由表中登记其 regime 画像（`implementation_ref` 字段明确标注"未实现"），
> **不代表该策略已可交易**。

## 3. 匹配引擎现状（已有，未改动）

| 模块 | 职责 | 本次关系 |
|------|------|----------|
| `core/registry/strategy_registry.py` | 策略版本生命周期状态机（draft→backtest→paper→live→retired） | **未修改** |
| `core/registry/strategy_matcher.py` | 根据市场状态给策略打分、排序、选 top-N | **未修改** |
| `core/features/regime.py` | L2 状态层：ADX/Hurst → `w_trend/w_mr/w_range` 连续权重 | **未修改**，作为上游 regime 信号来源 |

本次新增的 `strategy_router.py` 与上述模块的边界：
- 它**不负责**版本生命周期（那是 `StrategyRegistry` 的事）
- 它**不负责**打分排序（那是 `StrategyMatcher` 的事）
- 它**只负责**：输入离散 regime 标签 → 输出归一化策略权重（供组合分配）

## 4. 新建文件清单

| 文件 | 作用 |
|------|------|
| `core/registry/strategy_router.py` | 策略权重路由核心：`StrategyDescriptor` + `StrategyWeightRouter` + `build_demo_router()` |
| `tests/test_strategy_registry.py` | 19 个单测，覆盖权重和、方向、白名单、异常路径 |

修改的文件：
- `core/registry/__init__.py`：导出新模块的公开符号（只增不改）

## 5. 注册清单（策略元数据）

### 5.1 demo_breakout（唐奇安突破）
- version: `v1.0.0`
- symbols: `XAUUSD`, `BTCUSD`
- stop_loss_type: `atr_initial`
- params: `lookback=20, atr_n=14, entry_dist_mult=2.0`
- implementation_ref: `core.backtest.engine:DemoBreakoutStrategy`

### 5.2 ml_trend_meta（ML 增强趋势）
- version: `ml-trend-meta-label-v1`
- symbols: `XAUUSD`
- stop_loss_type: `atr_trailing`
- params: 来自 `StrategyConfig`（`entry_period=20, atr_period=14, meta_C=1.0, meta_threshold=0.55, atr_stop_mult=2.0, atr_trail_mult=3.0` 等）
- implementation_ref: `core.models.ml_trend_strategy:MLTrendStrategy`

### 5.3 demo_mean_reversion（均值回归，路由占位）
- version: `v0.1.0`
- symbols: `EURUSD`
- stop_loss_type: `bollinger_band`
- params: `rsi_period=14, bollinger_period=20`
- implementation_ref: `(未实现；gatekeeper 模拟数据 type=mean_reversion)`

## 6. 匹配规则：市场状态 → 权重表

### 6.1 基础权重（未归一化，配置在 `regime_profile` 中）

| 策略 | trend | range | volatile | quiet |
|------|-------|-------|----------|-------|
| demo_breakout | 0.45 | 0.10 | 0.25 | 0.15 |
| ml_trend_meta | 0.45 | 0.20 | 0.55 | 0.35 |
| demo_mean_reversion | 0.10 | 0.70 | 0.20 | 0.50 |

### 6.2 归一化后权重（`route(regime)` 输出，和为 1）

| regime | demo_breakout | ml_trend_meta | demo_mean_reversion |
|--------|---------------|---------------|---------------------|
| trend | 0.450 | 0.450 | 0.100 |
| range | 0.100 | 0.200 | 0.700 |
| volatile | 0.250 | 0.550 | 0.200 |
| quiet | 0.150 | 0.350 | 0.500 |

### 6.3 设计依据（第一性原理）
- **trend**：趋势类策略（breakout + ml_trend）占 90%，均值回归仅 10%（逆势风险高）
- **range**：均值回归占 70%（震荡市回归是主要 alpha），突破策略仅 10%（假突破多）
- **volatile**：带 ML 过滤的 ml_trend_meta 权重最高（0.55），因为 ML 层能在高波动中过滤假信号；纯突破次之
- **quiet**：低波平静市适合均值回归（0.50），趋势策略权重低（趋势不易形成）

> 这些权重是**路由配置**，来自策略画像的定性判断（best/worst regime），
> **不是**绩效网格搜索产物，符合硬规则第 3 条（阈值来自分布而非绩效）。

## 7. 接口设计

```python
from core.registry.strategy_router import build_demo_router

router = build_demo_router()
router.list_registered()           # ['demo_breakout', 'demo_mean_reversion', 'ml_trend_meta']
router.route("trend")              # {'demo_breakout': 0.45, 'ml_trend_meta': 0.45, 'demo_mean_reversion': 0.10}
router.route("range")              # {'demo_breakout': 0.1, 'ml_trend_meta': 0.2, 'demo_mean_reversion': 0.7}
router.route_all_regimes()         # 全表，用于审计
```

异常路径：
- 未知 regime → `ValueError("未知 regime ...")`
- 某 regime 下所有策略权重为 0 → `ValueError("...基础权重均为 0")`
- 重复注册 → `ValueError("策略已注册 ...")`
- `StrategyDescriptor` 校验：未知 regime 键、负权重、未知止损类型 → 构造时抛错

## 8. 测试结果

```
tests/test_strategy_registry.py
19 passed in 0.15s
```

覆盖项：
- 4 个 regime 权重和均为 1（参数化）
- trend 下趋势类合计 > 85%，均值回归 < 15%
- range 下均值回归 > 60%，突破 < 20%
- volatile 下 ml_trend_meta > demo_breakout
- quiet 下均值回归 > 突破
- 未注册策略不出现在结果里
- 注销后策略消失
- 未知 regime / 负权重 / 未知止损类型 / 重复注册均抛错
- 零权重策略不泄漏到结果
- 全零 regime 抛错（不静默返回空 dict）

回归验证：`tests/test_ml_trend_strategy.py` + `tests/test_gatekeeper.py` 共 19 项仍全绿。

## 9. 未验证 / 剩余风险

| 项 | 状态 |
|----|------|
| `demo_mean_reversion` 策略类实现 | **未实现**，仅路由占位；上线前需补策略类 |
| 权重表是否经 CLEAN 分布校准 | **未校准**，当前是定性配置；后续应由 `scripts/calibrate_regime.py --mode distribution` 输出分位驱动 |
| 与 `StrategyMatcher`（打分排序层）的组合使用 | **未集成**，两层目前独立；后续可让 `StrategyMatcher` 输出排名、`StrategyWeightRouter` 输出资金权重 |
| 实盘冒烟 / 经纪商差异 | **未验证** |
| 权重随 regime 连续变化（而非离散 4 类） | **未实现**；当前用离散 regime 标签，后续可接 `core/features/regime.py` 的连续 `w_trend/w_mr/w_range` 做线性插值 |
