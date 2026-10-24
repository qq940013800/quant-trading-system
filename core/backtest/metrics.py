# -*- coding: utf-8 -*-
"""core.backtest.metrics —— 标准绩效指标。

输入：equity_curve（pd.Series，index=ts_utc）与 trades（每笔 dict，含 pnl_usd）。
输出：Sharpe / Sortino / MaxDD / Calmar / ProfitFactor / 胜率 / 期望值 / 交易数。
年化按 bars_per_year（由周期决定，config 传入，禁止写死）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_metrics(equity_curve: pd.Series, trades: list[dict],
                    bars_per_year: int = 74880, risk_free: float = 0.0) -> dict:
    if not isinstance(equity_curve, pd.Series):
        raise TypeError({"layer": "backtest.metrics", "detail":
                         "equity_curve must be pd.Series"})

    eq = equity_curve.astype(float)
    rets = eq.pct_change().dropna()

    n = int(rets.size)
    if n == 0:
        sharpe = sortino = calmar = 0.0
    else:
        excess = rets - risk_free
        sd = rets.std(ddof=1) if n > 1 else 0.0
        downside = rets[rets < 0].std(ddof=1) if (rets < 0).sum() > 1 else 0.0
        ann = float(np.sqrt(max(bars_per_year, 1)))
        sharpe = float(excess.mean() / sd * ann) if sd and sd > 0 else 0.0
        sortino = float(rets.mean() / downside * ann) if downside and downside > 0 else 0.0

    # 最大回撤
    rolling_max = eq.cummax()
    dd = eq / rolling_max - 1.0
    max_dd = float(dd.min()) if dd.size else 0.0

    # 年化收益（几何近似）
    if eq.size >= 2 and eq.iloc[0] > 0:
        total_ret = eq.iloc[-1] / eq.iloc[0] - 1.0
        years = max(len(eq) / float(bars_per_year), 1e-9)
        ann_return = (1.0 + total_ret) ** (1.0 / years) - 1.0
    else:
        ann_return = 0.0
    calmar = float(ann_return / abs(max_dd)) if max_dd < 0 else 0.0

    # 逐笔盈亏
    pnls = np.array([float(t.get("pnl_usd", 0.0)) for t in trades], dtype=float)
    n_trades = int(pnls.size)
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    gross_win = float(wins.sum())
    gross_loss = float(-losses.sum())
    profit_factor = float(gross_win / gross_loss) if gross_loss > 0 else (
        float("inf") if gross_win > 0 else 0.0)
    win_rate = float((pnls > 0).sum()) / n_trades if n_trades else 0.0
    expectancy = float(pnls.mean()) if n_trades else 0.0

    return {
        "n_trades": n_trades,
        "final_equity": float(eq.iloc[-1]) if eq.size else 0.0,
        "total_return": float(eq.iloc[-1] / eq.iloc[0] - 1.0)
                        if eq.size >= 2 and eq.iloc[0] > 0 else 0.0,
        "annual_return": float(ann_return),
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": max_dd,
        "calmar": calmar,
        "profit_factor": profit_factor,
        "win_rate": win_rate,
        "expectancy_usd": expectancy,
    }
