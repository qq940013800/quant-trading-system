# ADR：regime 状态词表唯一来源（#334）

状态：已落码（唯一来源）+ 待决策（轴拆分）
日期：2026-11-19

## 1. 问题

同一"市场状态"概念在本仓库有四套拼写，且其中一处把两个正交维度压成一个枚举。四套词表用 grep 可复核：

| 位置 | 词表 | 语义 |
|---|---|---|
| `core/regime/rules.py:22-25` | `trend` / `mean_reversion` / `ranging` | 权威分类器输出（方向+结构），带 CLEAN 分布阈值与审计链 |
| `core/selector/blend.py:42`（改前） | 本地 `dict(zip(STATES, ("trend","mr","range")))` | 仅为对齐策略 `regime_weights` 的短键，重复维护 |
| `core/strategies/*.py` `regime_weights` | `trend` / `mr` / `range` | 单专家策略声明的适用状态（短键） |
| `core/registry/strategy_router.py:28` | `trend` / `range` / `volatile` / `quiet` | 策略权重路由的 4 态枚举 |
| `core/registry/strategy_matcher.py` docstring | `trending` / `ranging` / `volatile` / `quiet` | 策略打分画像的自由字符串 |

后果不是"名字不统一"这种审美问题，而是三个实际缺陷：

1. **同义多拼写导致静默失配**：`range` vs `ranging`、`mr` vs `mean_reversion` 一旦在配置或存档里写错，查表返回 0 权重/0 分而不是报错 —— 决策被静默降级为"不使用该策略"，审计链上看不出是拼写问题。
2. **router 的 4 态枚举把两个正交轴压平**：`trend`/`range` 是方向-结构轴，`volatile`/`quiet` 是波动轴。压平后无法表达"趋势 + 高波动"，而这个组合恰恰是择时与仓位最需要区分的格子；同时它**没有** `mean_reversion` 态，意味着均值回归策略在 router 里只能借 `range` 表达。
3. **短键表两处维护**，任何一处新增状态都会漏改另一处（`blend.py` 本次改动前正是手工复制的一份）。

## 2. 决策

**D1（已执行）单一来源 + 入口归一化**

- `core/regime/rules.py` 成为唯一词表来源，新增：
  - `SHORT_KEYS`：`STATES → 短键`（`trend→"trend"`、`mean_reversion→"mr"`、`ranging→"range"`），这是策略 `regime_weights` 与 selection 快照的**契约值域**，不再由调用方各自维护。
  - `STATE_ALIASES` + `normalize_state(value)`：把历史拼写（`trending` / `mr` / `mean-reversion` / `range` …，大小写与首尾空白容忍）归一为 `STATES` 之一；未知值抛 `ValueError` 并列出允许集合，**不做静默回退**。
- `core/selector/blend.py` 改为引用 `SHORT_KEYS`，删除本地映射表，**行为零变化**（值完全相同，`test_selector_blend.py` 全绿）。
- 归一化函数的定位是**入口**（配置、存档、外部输入），不在计算路径内做拼写猜测：状态一旦进入决策，必须是 `STATES` 之一。

**D2（待决策，需 RES 出结论）router 轴拆分**

现在的 4 态枚举必须先拆成两个正交字段再谈"合并词表"：

- `direction_state ∈ {trend, mean_reversion, ranging}`（复用 `STATES`）
- `vol_band ∈ {low, medium, high}`

理由：分离后 `mean_reversion` 不再被 `range` 冒充；`trend × high` 这类格子可表达；`volatile`/`quiet` 变成 `vol_band=high/low` 的别名而不是独立状态。**代价**是 `StrategyDescriptor.regime_profile` 的键要从 4 个变成 2×3 的笛卡尔积（或保留 4 键并声明为投影），会改动路由权重表结构与既有 `registry.yaml` 口径——属于需人工确认的范围，本 ADR 只给方案，不落码。

**D3（待决策）matcher 画像对齐**

`StrategyMatcher` 的 `best_regimes` / `worst_regimes` 目前是自由字符串，建议在构造时用 `normalize_state` 校验并在未知值时抛错（而非打分 0）。风险：若历史配置里存在 `volatile` 等词，会被新校验拒绝——需先盘点所有调用点的实际取值，再决定是否保留 `volatile/quiet` 作为 `vol_band` 的别名。

## 3. 验证与影响面

- 新增测试：`tests/test_regime_rules.py::TestRegimeVocabulary`（9 例）——短键与 `STATES` 一一对应且值固定；7 种历史拼写归一；短键经别名可回环到原状态；`volatile`/`quiet`/空串/`None`/数字/近似词全部被拒并带上下文。
- 回归：`tests/test_regime_rules.py tests/test_selector_blend.py tests/test_selector_walkforward_smoke.py tests/test_regime_classifier.py` 60 passed（改前）；加新例后 `test_regime_rules.py + test_selector_blend.py` 43 passed。
- 未改变：`predict` 的因果守卫、`derive_thresholds` 的分布派生、`blend` 的权重合成与 selection 快照键值。

## 4. 剩余风险 / 未验证

- `normalize_state` 目前只在测试中被直接调用（真实入口尚未接线）。按 #333 的规则，它落在**已接线模块** `core/regime/rules.py` 内，不产生新的悬空模块；但"策略配置解析时校验状态键"这一步仍未做，属 D3 待决策项。
- `strategy_router` 仍接受 `volatile`/`quiet`，`normalize_state` 会拒绝这两个词 —— 两者**不能混用**，接线时必须以 D2 的拆分为前提，否则会把合法的 router 配置打成错误。
- 本次未跑动 router 权重表相关测试的全量口径（`tests/test_enum_mapping.py`、router 相关例）以外的影响面，待 D2 落码时统一验证。
