# ADR：实盘门禁权威归属与 7 个 core 闸模块的处置（#335）

状态：只读核查完成，处置待人工/RES 决策（未改任何代码）
日期：2026-11-19

## 1. 结论先行

**本仓库有 7 个"门禁"模块，其中 0 个在交易路径上生效。** 真正拦单的是后端 `backend_api_python/app/services/live_trading/account_risk.py`（违规码前缀 `accountRisk.`），由 `pending_order_worker.py:1838-1848` 在每次下单前调用并 `_mark_failed` + 通知 + 策略日志；core 侧 7 个闸模块只被测试与一个报表脚本引用。

因此「把多套门禁收敛成一套」这个方向是错的：**问题不是重复，而是 6 个从未接线 + 1 个接线了但喂的是假数据**。收敛前必须先确定权威，否则等于给死代码再包一层抽象。

## 2. 证据（逐条可复核）

| 模块 | 裁决函数 | 决策词表 | 生产引用方（非测试） | 真实调用链 |
|---|---|---|---|---|
| `backend_api_python/app/services/live_trading/account_risk.py` | `account_risk_snapshot` / `account_risk_limits` | `accountRisk.*`（8 类违规码，`:234-249`） | `pending_order_worker.py`、`strategy_positions_routes.py:358` | **唯一在每笔下单前生效**（`pending_order_worker.py:1825-1848`） |
| `core/execution/pretrade_gate.py` | `evaluate_pretrade_gate` / `evaluate_risk_limits` / `evaluate_projected_limits` | 同名 `accountRisk.*` 违规码 | 仅 `core/execution/gate_shadow.py:18` | 无真实消费者（见下） |
| `core/execution/gate_shadow.py` | `compare_snapshot` | `match` / `only_core` / `only_backend` | **0** | 无 worker 接线（`docs/design/protection-layers-reconciliation.md:68` 已注明"尚未在 worker 进程接线"） |
| `core/integration/verification_middleware.py` | `gate_before_deploy` / `gate_before_trade` | `PASS/WARN/REJECT/DOWNGRADE`（`:63-68`，`:593-601` 取最严） | 仅 `core/integration/gatekeeper.py:19` | 仅报表链路 |
| `core/integration/gatekeeper.py` | `run_full_gate` | `can_deploy` + 建议动作 | 仅 `scripts/generate_gatekeeper_report.py:22` | 手工报表，且**输入是硬编码假数据**（`:142-149`：pbo 0.15 / DSR 1.5 / trials 10 / 写死的收益序列） |
| `core/execution/economics_gate.py` | `economics_gate` | `allowed` + `reason` + `edge_cost_ratio` | **0** | 无 |
| `core/registry/deployment_guard.py` | `check_strategy_deployment` / `check_model_deployment` | `allowed` + `reasons` | **0** | 无 |
| `core/control/approval_gate.py` | `evaluate_approval` | `allowed` + `reason_code` | **0** | 无；但 `docs/agent/MCP_SETUP.md:49` 称其"已固化"——**文档与实现不符** |

`backend_api_python` 对 `core` 的导入文件数仍为 0（`scripts/audit_orphan_modules.py` 与早前 #333 度量一致），所以 core 侧任何闸都不可能经由"后端 import core"生效。

## 3. 这推翻了什么

- **勘误 #333**：当时列出的"在跑的门禁：`pretrade_gate`（在跑）+ `gatekeeper`/`verification_middleware`/`economics_gate`（在跑）"是基于模块文档字符串与既有设计文档的推断，**不是基于引用图**。真实引用图显示它们均无生产消费者。`docs/design/design-occam-pruning.md` 的"已接线对照组"需按此修正为"有实现、无生产接线"。
- **`gatekeeper` 的裁决不可信**：它把 `pbo 0.15`、`DSR 1.5`、`trials 10` 和两串写死的收益直接喂给验证中间件。哪怕有人跑报表看到"允许上线"，也不代表该策略通过了任何检查。
- **危险的语义错觉**：`approval_gate`（危险动作审批）看着像已生效，实际没有调用方。任何依赖它拦"危险动作"的假设都不成立。

## 4. 处置方案（按奥卡姆顺序，全部待人工/RES 决策）

**P1｜先定权威（不写代码，只需一句结论）**
承认 `account_risk.py` 是当前唯一权威闸；把它的 `accountRisk.*` 词表与限额口径定为**契约**。所有 core 侧闸要么对齐它，要么退出。理由：它是唯一有真实副作用的实现（`_mark_failed` + 通知 + 日志 + `phases["account_risk"]` 审计轨迹），其余皆为纯函数。

**P2｜`pretrade_gate` + `gate_shadow`：走既定的 shadow→cutover，而非重写**
现有 `live-trading-gates-and-reconciliation-design.md:171` 已写了正确顺序：后端取数与限额回退不动，先并行跑 core 判定只记 warning，一致后再切。**前提**是把 `gate_shadow.compare_snapshot` 真正接进 worker 一次（这一步会改实盘前置路径的日志行为，需人工确认）。在接线前，这两个模块的价值=0，不应再为它们加功能。

**P3｜`gatekeeper` + `verification_middleware`：定位为"上线评审工具"，禁止接入每笔路径**
它的输入应该是真实回测产物（PBO/DSR/trials 来自实验登记，收益序列来自回测导出），而不是 `:142-149` 的常量。当前实现属**演示级**：先把假数据换成真实来源，否则应显式标注"报表仅供参考、不构成上线依据"。

**P4｜`economics_gate` / `deployment_guard` / `approval_gate`：接线或归档，二选一**
三者都是干净的纯函数、有单测、`fail-closed`：
- `economics_gate`：本应放在下单前的成本-边际校验，属"每笔可用"，与 `pretrade_gate` 同一时点，可一并接线；
- `deployment_guard`：本应放在 registry 状态流转处，属"上线时可用"，不与每笔路径冲突；
- `approval_gate`：本应放在危险动作执行边界（配置写、运行时控制、交易），属"操作时可用"。
若在 3 个月内无接线计划，按 #333 规则出**归档清单**（不删除，删除由人执行），避免继续在死代码上补测试。

## 5. 未做 / 剩余风险

- 本轮**未改任何代码**，只出核查与方案；`docs/agent/MCP_SETUP.md:49` 的"已固化"表述未改（属文档口径，需与 P4 决策同步回填，避免现在改成"未接线"后又因接线再改一次）。
- 若采纳 P2 的 worker 接线，属于**实盘前置路径变更**，必须由人显式确认，且需要先在 demo/影子环境验证 `only_core`/`only_backend` 差异为空。
- `account_risk.py` 的限额口径是否真的与 `core` 的 `RiskLimits` 同构，本轮只做了词表比对（8 个违规码名一致），未逐字段核对数值语义——若 P2 要切，必须先做字段级对照。
