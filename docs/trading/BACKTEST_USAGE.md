# 回测 / 风控 / 决策审计使用说明（分片③）

> 范围：`core/backtest/`、`core/risk/`、`core/audit/`、`scripts/run_backtest.py`。
> 依赖仅 numpy/pandas；与 `core/data`、`core/features`、`core/models` 解耦（鸭子类型，并行实现后直接对接）。

## 1. 运行

```powershell
# 用确定性合成数据 + 演示突破策略跑通 pipeline（含审计回放校验）
D:\Trader\.venv\Scripts\python.exe scripts\run_backtest.py `
    --bars 400 --lookback 20 --risk-pct 0.01 --kelly-cap 0.25 `
    --audit-out experiments\signals\decisions_demo.jsonl `
    --out experiments\reports\demo_bt.json
```

输出指标：`n_trades / final_equity / total_return / annual_return / sharpe / sortino /
max_drawdown / calmar / profit_factor / win_rate / expectancy_usd`，以及接受/拒绝笔数与
`audit_replay_ok`（逐条回放可还原的条数）。

## 2. 接入真实策略与数据

```python
from core.backtest.engine import run_backtest
from core.backtest.costs import CostModel

cost = CostModel(base_spread=0.20, news_spread=0.60, gap_spread=1.0,
                 gap_threshold=1.0, base_slippage=0.05,
                 slippage_per_volume_frac=0.10, commission_per_lot=0.0,
                 news_minutes=15.0)
risk_cfg = {
    "initial_equity": 10_000, "point_value": 100.0,
    "risk_pct": 0.01, "kelly_cap": 0.25,
    "min_lot": 0.01, "lot_step": 0.01, "heat_limit": 1,
    "daily_loss_limit": 0.03, "cooldown_bars": 12,
    "news_window": [pd.Timestamp(...)], "audit_path": "decisions.jsonl",
}
res = run_backtest(bars, your_strategy, cost, risk_cfg)
# bars: list[Bar]（core.data 就绪后直接传入）；
# your_strategy.on_bar_close(history, bar) -> Signal-like | None
```

策略协议：`on_bar_close(history: list[Bar], bar) -> Signal-like | None`，
**只能用 `history`（全部为已收盘 bar）**；信号在 bar[i] 收盘决策，于 bar[i+1] 开盘成交。

## 3. 成本模型（三档，参数全走 config）

`spread_at(bar, news_window, prev_close, cost_model)` 优先级：跳空 > 新闻±15min > 平静。
- 新闻窗口点差必须 > 平静点差（单测断言该不等式，防止成本模型被旁路成常数）。
- `slippage_points(bar, 手数/bar成交量)`：随占比加深。
- 传 `cost_model=None` 为零成本对照（仅用于验证成本敏感性，不得用于正式绩效）。

## 4. 风控规则

- **仓位** `target_lots(equity, risk_pct, atr0, point_value, min_lot, lot_step, kelly_cap)`：
  固定分数风险预算 /（冻结止损距离 × point_value）；`risk_pct` 被 `kelly_cap`（1/4~1/2 Kelly）
  截断；输出向下对齐 `lot_step`；低于 `min_lot` 返回 0。`vol_target_scale` 叠加降仓（不放大）。
- **止损单调** `update_stop(current, new, direction)`：多头只升、空头只降；
  放宽方向抛 `StopWideningError`。`atr0/entry_dist` 入场冻结，R 倍数用冻结值。
- **熔断三态机** `CircuitBreaker`：日内回撤破 `daily_loss_limit` → breaker（禁新开仓）
  → 冷却 `cooldown_bars` → 次一交易日边界重置 normal。
- **阈值来自分布**：`quantile_threshold(values, q)` 从 CLEAN 分布取分位派生门限，禁绩效网格。

## 5. 决策审计 JSONL

每笔接受/拒绝都落一行（拒绝不省略）。结构：

```json
{"decision_id":"D00000001","signal":{...},"feature_snapshot":{...各层输入/sizing输入...},
 "model_version":"rules-v1","risk_state":{...},"accepted":true,"reject_reason":null,
 "final_signed_lots":1.08,"threshold_dataset":"CLEAN","decision_rule_version":"rules-v1",
 "r_multiple_at_close":null}
```

回放校验：`read_decisions(path)` 读回，`replay_decision(record)` 用快照里的 sizing 输入
重算手数并比对；篡改手数或缺输入会抛 `ReplayMismatch`。

## 6. 测试

```powershell
D:\Trader\.venv\Scripts\python.exe -m pytest tests\test_backtest_costs.py `
    tests\test_backtest_engine.py tests\test_backtest_metrics.py `
    tests\test_risk_stops.py tests\test_risk_sizing.py tests\test_risk_circuit.py `
    tests\test_audit_record.py tests\test_audit_replay.py -q
```

## 7. 未验证项

- MT5 实盘执行（retcode 重试 / 幂等 / 真实滑点 / 时区对拍）——**未验证**。
- 经纪商差异（点差 / 合约规格 / DST 表）——**未验证**。
- real-ticks 成本参数校准——依赖经纪商历史 tick，**未验证**。
- `point_value=100`（XAUUSD 100oz 合约）为研究层假设，实盘须走 `SymbolInfo*`——**未验证**。
