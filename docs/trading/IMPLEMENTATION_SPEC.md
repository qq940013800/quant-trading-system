# 实现接口级补充 Spec（IMPLEMENTATION_SPEC）

> 本文是 `AI_ML_SYSTEM_DESIGN.md` 的接口级补充：实现 agent 必须遵守的编码纪律、命名约定、测试夹具用法与边界确认。主设计文档已足够冻结架构；本文只补"实现时最容易做歪"的细则。

---

## 1. 模块实现顺序（依赖拓扑，逐层配单测）

```
core/data/  (bar, timezone, validator, splits, synthetic)
    → core/features/base.py (as_of 装饰器最先，所有特征依赖它)
        → core/features/ (atr, volatility, regime, structure, patterns)
            → core/models/ (labels → baseline → cv → gbm → meta_label → drift)
                → core/risk/ (stops → sizing → circuit)
                    → core/backtest/ (costs → broker → engine → metrics)
                        → core/audit/ (record → replay)
                            → scripts/ 入口串联
```

每层完成先过对应 pytest，再进下一层。禁止先写回测再补因果守卫。

## 2. 命名与约定

- 特征函数统一签名：`def feat_x(history: list[Bar], as_of: pd.Timestamp) -> float | pd.Series`，用 `@as_of` 装饰；**禁止**出现"全序列 DataFrame 一次性算完再切片"的写法（那是泄漏高发路径）。
- 时间戳一律 timezone-aware UTC（`pd.Timestamp(tz="UTC")`）；naive 时间戳进 `load_bars` 即报错。
- 阈值/参数走 `core/config.py` 加载 dict；函数签名中出现 `threshold: float` 形参，调用方从 config 取——禁止模块内 `0.5`、`20`、`0.03` 这类字面量（配置注释除外）。
- 日志：`logging.getLogger("core.<module>")`；异常必须带 `{"symbol","ts_utc","layer","detail"}` 上下文，禁止裸 `raise` / 空 except。

## 3. 既有黄金夹具复用（tests/fixtures/causal_guard/）

`tests/fixtures/causal_guard/answer_key.json` 与 c01–c06 六组夹具对应 AGENTS.md 的因果守卫断言：

| 夹具 | 断言语义 | 本设计对应测试 |
|---|---|---|
| c01_shift_neg | 特征/标签不得平移偷看 | test_features_causal |
| c02_center_true | 中心价不得当未来信息 | test_features_causal |
| c03_stop_widen | 止损放宽必被拒 | test_risk_monotonic（复用） |
| c04_atr_recompute | R 不得用重算 ATR | test_atr0_freeze（复用） |
| c05_clean | CLEAN 集统计正确 | test_regime_no_lookahead |
| c06_intrabar | intra-bar 不决策 | test_backtest_costs |

**黄金集断言不得放宽**（AGENTS.md 硬规则10）；新增断言只能加不能改阈值。

## 4. 关键接口的"必须行为"清单（实现即验收点）

1. `as_of` 装饰器：`history` 中任一 bar.ts_utc > as_of → `raise LookAheadError`。单测：打乱时间索引后必抛。
2. `triple_barrier_labels`：tp/sl 屏障用 `atr0` 倍数、时间屏障用 max_holding_bars；标签方向 = 先触屏障方向。单测：构造已知路径断言标签。
3. `purged_walk_forward`：每个 test 块之后剔除 `embargo_bars` 个训练样本；单测：embargo 宽度 < 标签窗口时 raise（防止实现忘记约束）。
4. `update_stop`：多头 new_stop < current_stop → `raise StopWideningError`；空头对称。
5. `target_lots`：输出向下对齐 `lot_step`；`risk_pct × atr0 × point_value` 超 kelly_cap 时按 cap 截断。
6. `write_decision`：单行 JSONL；replay 后必须能还原 `feature_snapshot/model_version/final_signed_lots/reject_reason` 五要素。
7. `spread_at`：新闻窗口内返回值 > 平静窗口默认点差；单测断言该不等式（防成本模型被旁路成常数）。

## 5. 明确不做（第二阶段范围外）

- 不实现 DL/DRL/LLM 信号路径（留接口位 `models/base.py::Model` protocol 即可）。
- 不写 `mt5/` 实盘代码；MQL5 只交付 `docs/trading/ea/` 骨架。
- 不改 `configs/`、`registry.yaml`、既有 `docs/` 文件；缺口 gate 产物只写到 `experiments/`。
- 不做绩效网格搜索；`calibrate_regime.py` 只走 `--mode distribution`。

## 6. 未验证项（实现报告必须显式标注）

- MT5 实盘执行（retcode 重试、幂等、滑点、时区对拍）——**未验证**。
- 经纪商差异（点差、合约规格、DST 表）——**未验证**。
- GBM/meta-labeling 在 XAUUSD M5 的 OOS 相对线性基线增益——**未验证**。
- real-ticks 成本参数校准——依赖经纪商历史 tick，**未验证**。
