# -*- coding: utf-8 -*-
"""scripts/run_backtest.py —— 回测入口（参数化，输出标准绩效指标）。

用法（研究层，不接实盘）：
    python scripts/run_backtest.py --bars 500 --out experiments/reports/bt.json

无数据文件时用确定性合成趋势序列 + DemoBreakoutStrategy 跑通 pipeline。
成本/风控参数全部命令行传入，禁止硬编码。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.backtest.costs import CostModel
from core.backtest.engine import DemoBreakoutStrategy, run_backtest
from core.audit.replay import read_decisions, replay_decision


def _synthetic_bars(n: int):
    # 内联合成（解耦 core/data）：确定性带噪趋势
    import numpy as np
    import pandas as pd
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class _Bar:
        symbol: str; ts_utc: object; ts_server: object; server_offset_hours: float
        open_: float; high: float; low: float; close: float; tick_volume: float = 1000.0
        spread_points: object = None

    rng = np.random.default_rng(42)
    price = 1800.0
    bars = []
    for k in range(n):
        price = price + 0.3 + rng.normal(0, 0.3)
        ts = pd.Timestamp("2021-01-04", tz="UTC") + pd.Timedelta(minutes=5 * k)
        bars.append(_Bar("XAUUSD", ts, ts, 2.0, price, price + 0.1, price - 0.1, price))
    return bars


def main() -> int:
    ap = argparse.ArgumentParser(description="event-driven backtest (research layer)")
    ap.add_argument("--bars", type=int, default=400)
    ap.add_argument("--lookback", type=int, default=20)
    ap.add_argument("--initial-equity", type=float, default=10_000.0)
    ap.add_argument("--risk-pct", type=float, default=0.01)
    ap.add_argument("--kelly-cap", type=float, default=0.25)
    ap.add_argument("--point-value", type=float, default=100.0)
    ap.add_argument("--min-lot", type=float, default=0.01)
    ap.add_argument("--lot-step", type=float, default=0.01)
    ap.add_argument("--daily-loss-limit", type=float, default=0.03)
    ap.add_argument("--base-spread", type=float, default=0.20)
    ap.add_argument("--news-spread", type=float, default=0.60)
    ap.add_argument("--gap-spread", type=float, default=1.0)
    ap.add_argument("--gap-threshold", type=float, default=1.0)
    ap.add_argument("--slippage", type=float, default=0.05)
    ap.add_argument("--commission-per-lot", type=float, default=0.0)
    ap.add_argument("--bars-per-year", type=int, default=74880)
    ap.add_argument("--audit-out", type=str, default=None)
    ap.add_argument("--out", type=str, default=None)
    args = ap.parse_args()

    cost = CostModel(
        base_spread=args.base_spread, news_spread=args.news_spread,
        gap_spread=args.gap_spread, gap_threshold=args.gap_threshold,
        base_slippage=args.slippage, slippage_per_volume_frac=0.10,
        commission_per_lot=args.commission_per_lot, news_minutes=15.0)

    risk_cfg = {
        "initial_equity": args.initial_equity, "point_value": args.point_value,
        "risk_pct": args.risk_pct, "kelly_cap": args.kelly_cap,
        "min_lot": args.min_lot, "lot_step": args.lot_step,
        "daily_loss_limit": args.daily_loss_limit, "heat_limit": 1,
        "bars_per_year": args.bars_per_year, "audit_path": args.audit_out,
        "trail_enable": True,
    }

    bars = _synthetic_bars(args.bars)
    strat = DemoBreakoutStrategy(lookback=args.lookback)
    res = run_backtest(bars, strat, cost, risk_cfg)

    out = {"metrics": res.metrics,
           "n_decisions": len(res.decisions),
           "n_accepted": sum(1 for d in res.decisions if d.accepted),
           "n_rejected": sum(1 for d in res.decisions if not d.accepted)}

    # 审计回放校验：若落了 JSONL，逐条 replay 证明可还原
    if args.audit_out and Path(args.audit_out).exists():
        oks = 0
        for rec in read_decisions(args.audit_out):
            replay_decision(rec)
            oks += 1
        out["audit_replay_ok"] = oks

    print(json.dumps(out, ensure_ascii=False, indent=2))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
