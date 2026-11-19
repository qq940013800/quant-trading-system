# 奥卡姆剃刀 × 马斯克五步：系统瘦身准则（#333）

> 目的：把"要不要做这个模块"从品味争论变成可复核的度量。本文只定义判定规则与执行顺序，不代替任何人拍板删除。

## 1. 两条方法论怎么落到本项目

**奥卡姆剃刀**：在同一预测能力下，选概念更少的实现。本项目的"概念"具体化为四类可数实体——模块、枚举词表、阈值常量、门禁入口。剃刀的判据不是"代码漂亮"，而是：*删掉它，系统对外行为是否改变？* 不改变即为多余实体。

**马斯克五步算法**（顺序不可颠倒，先删后简化，最后才自动化）：

| 步骤 | 在本项目的含义 | 反模式（我们实际踩过的） |
|---|---|---|
| 1 质疑需求 | 谁在调用？不调用会怎样？需求方是策略、风控还是"看着完整"？ | 为"架构完整"先写纯函数，无人接线 |
| 2 删除 | 删模块 / 删路径 / 删词表 / 删阈值副本 | 用新增适配层去兼容旧重复，而不是删掉重复 |
| 3 简化 | 一个概念一个实现，一个入口一个裁决 | 同时存在 gatekeeper / gate_shadow / middleware / pretrade_gate 四条准入 |
| 4 加速 | 只在被验证的路径上优化 | 给未接线模块做性能优化 |
| 5 自动化 | 把前四步变成可重复检查 | 靠人肉 review 记住"别再加重复门禁" |

与三条不变量的关系：因果单向与阈值来自分布**不能**为了"简化"而妥协；剃刀只作用于**冗余表达**，不作用于**证据链**。审计日志、决策快照属于不变量 2 的载体，不在删除范围内。

## 2. 度量（可复核）

复现命令：

```
python scripts/audit_orphan_modules.py --root D:\Trader          # 人类可读
python scripts/audit_orphan_modules.py --root D:\Trader --json   # 机器可读
python scripts/audit_orphan_modules.py --root D:\Trader --fail-over <预算>
```

判定口径：`core/` 下某模块若**没有任何非 tests/ 文件导入它**（含相对导入、包级 `__init__` 再导出），且自身不是 `if __name__ == "__main__"` 入口，则记为**悬空（orphan）**。悬空 = 已实现、已单测、但运行时无调用方。

2026-11-19 实测：

| 指标 | 数值 |
|---|---|
| `core/` 与 `scripts/` 规模 | 117 文件 / 21,497 行（scripts 26 文件 / 3,463 行） |
| `tests/` 规模 | 106 文件 / 15,224 行（测试:实现 ≈ 0.71:1） |
| 悬空模块 | **17 个 / 4,315 行**，占 core 代码 **20.1%** |
| `backend_api_python` 导入 core 的文件数 | **0**（core 尚未进容器） |
| 悬空模块中带 `__main__` 入口的 | 0（全部是真悬空，不是 CLI 工具） |

悬空清单（按行数降序）：`experiment.strategy_lifecycle`(601)、`models.ml_trend_strategy`(499)、`debug.system_diagnoser`(395)、`experiment.auto_optimizer`(375)、`experiment.ab_test`(334)、`features.patterns`(316)、`explainability.decision_explainer`(283)、`registry.strategy_matcher`(266)、`logging.audit_logger`(259)、`execution.spot_ownership`(202)、`backtest.integration`(181)、`execution.gate_shadow`(175)、`registry.deployment_guard`(115)、`control.approval_gate`(109)、`models.gbm`(102)、`models.meta_label`(61)、`models.drift`(42)。

**勘误（#335，2026-11-19）**：本行原写"`pretrade_gate`/`gatekeeper`/`verification_middleware`/`economics_gate` 均有非测试调用方"，该判断基于模块 docstring 与既有设计文档，**不是引用图**。按引用图复核后：`pretrade_gate` 仅被 `gate_shadow` 引用、`gate_shadow` 无生产引用方、`verification_middleware` 仅被 `gatekeeper` 引用、`gatekeeper` 仅被 `scripts/generate_gatekeeper_report.py` 引用、`economics_gate` 无生产引用方。唯一在交易路径上生效的闸是**后端** `backend_api_python/app/services/live_trading/account_risk.py`（`pending_order_worker.py:1825-1848`）。详见 `docs/design/design-live-gate-authority.md`。真正"接线"的对照组此时只剩 `risk.protection`。

## 3. 由度量推出的三个结论

1. **20% 的 core 不参与任何决策**。它们不是错代码，而是"未被需求证实的实体"。每新增一个纯函数切片前，必须先答"它的调用方是谁、什么时候接线"；答不出就进 `docs/TODO.md` 的候选池，而不是直接落码。
2. **同一概念多实现是最大的隐性成本**：准入门（7 条实现，交易路径上生效 0 条，真正拦单的是后端 `account_risk`，见 #335）、时区偏移（load 层与表层两处守卫，已由 #331/#332 统一口径）、非有限数值（数据层 #328 / 特征层 #330 各自一套，口径已对齐但实现分散）、regime 词表（已由 #334 收敛到 `SHORT_KEYS`/`normalize_state`）。剃刀在这里不是删代码，而是**先定权威、再收敛到单一裁决入口**。
3. **测试配额被悬空能力占用**。15,224 行测试里，悬空模块对应测试仍在消耗回归时间（全量已到 2344 例 / 164s）。回归时长是决策速度的直接成本，属于"加速"步骤要治理的对象。

## 4. 执行顺序（含人工门）

**P0（本批已做）**
- 把判断自动化：`scripts/audit_orphan_modules.py` + `tests/test_orphan_module_audit.py`（6 例），让"悬空"可复测、可进发布前检查。
- 规则：新增 core 模块必须在同一提交内出现非测试调用方，或显式标注"待接线 + TODO 编号"。否则审阅即打回（并入 `docs/RULES.md` 踩坑表）。

**P1（待排期，多数不需要人工门）**
- `regime` 词表合一：先出权威词表 ADR（规则引擎 / Router / Matcher 三套对齐），随后其余两处改为引用同一枚举。属纯函数层改动，可自主执行。
- 门禁收敛（已被 #335 修正方向）：不是"以 `pretrade_gate` 为唯一入口"，因为它本身未接线；先承认后端 `account_risk` 为唯一权威闸，再决定 `pretrade_gate`+`gate_shadow` 是否走 shadow→cutover（改实盘前置路径，需人工门），`deployment_guard`/`approval_gate`/`economics_gate` 明确归类（部署/审批/边际经济）并给出接线或归档结论。详见 `docs/design/design-live-gate-authority.md`。
- 悬空模块三选一决策（逐模块，需 RES 给需求方结论）：**接线 / 明确归档 / 退役候选**。退役涉及删文件 → **必须人工执行**，本 Agent 只出清单。

**P2（需人工门）**
- 把 `--fail-over` 纳入发布前检查脚本（CI 或本地 pre-push），预算从当前 4,315 起只降不升。
- 容器化取舍（core 是否进 backend）：当前 backend 对 core 导入为 0，说明保护链在后端是另一套实现——这属于"同一概念两套实现"的根因，需 D4/D5 决策后再动。

## 5. 逐模块决策三问（接线还是退役）

1. 有明确需求方与触发时点吗（策略上线？风控演练？审计要求？）
2. 接线成本是否小于重复实现成本（对照现已接线的那条路径）
3. 不接线时，它的存在是否会误导后来者以为"系统已有该保护"

三问全否 → 退役候选；第 3 问为是 → 至少要在模块 docstring 顶部标 `UNWIRED`。

## 6. 剩余风险 / 未验证

- 静态导入分析看不到**反射式调用**（`importlib`、字符串分派、配置文件指定类名）。本仓库未发现此类用法，但审计工具不能证明"绝对无调用"，只能证明"无静态导入"。出现 `__main__` 或动态加载时需人工复核。
- 悬空 ≠ 无用：`system_diagnoser`、`decision_explainer` 等属运维/解释能力，可能由人工直接调用。是否保留是需求判断，不是代码判断。
- 本文件不含任何删除动作；清单落地前不修改 `.gitignore`、`configs/`、`mt5/`。
