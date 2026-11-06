# -*- coding: utf-8 -*-
"""scripts/run_strategy_selection.py —— 策略自动匹配「元层验证」CLI（阶段 5）。

目的：把 core.selector.RegimeBlendedStrategy 当独立系统做 purged walk-forward
验证，输出「混合层 vs 单一策略基线」的 OOS 对比报告。

验收主指标（O09 / 深度解读第 4 节阶段 5）：
    OOS 最大回撤、whipsaw（方向反转 + 连续亏损段）、成本占比；Sharpe 仅次要。

纪律（AGENTS.md / 决策 #9 O07）：
- 数据三段切分：CLEAN 段 fit RegimeClassifier（阈值 = CLEAN 分布分位 + GMM）；
  KNOWN 段构建供需区（SupplyDemandStrategy.known_end_ts 纪律）；剩余交易段跑 WF。
- purged_walk_forward（embargo >= 标签窗）；每折 test 段只评估，train 段仅作
  指标预热历史；**阈值默认沿用全局 CLEAN 校准，不在折内重估**——WF 评估的
  是「策略与混合层的绩效」，不是调参（GMM 折内重拟合为可选项，默认关闭）。
- 不做绩效网格搜索；alpha/deadband/confirm_n/min_strength 为冻结占位值
  （生产路径应由 CLEAN 分布校准，见 scripts/calibrate_regime.py --mode distribution）。
- 不读写 registry.yaml；trials_N 只由 run_gate_experiment.sh 原子递增。

运行：
    D:\\Trader\\.venv\\Scripts\\python.exe scripts\\run_strategy_selection.py \\
        --n-bars 1200 --out experiments/reports/selection_meta.md \\
        --audit-out experiments/audit/selection.jsonl
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

# 允许 `python scripts/run_strategy_selection.py` 直接运行（把项目根放上 sys.path）
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.backtest.costs import CostModel
from core.backtest.engine import run_backtest
from core.backtest.metrics import compute_metrics
from core.models.cv import purged_walk_forward
from core.regime import RegimeClassifier
from core.selector import DeadbandWeightState, RegimeBlendedStrategy
from core.strategies import MeanReversionStrategy, TrendBreakoutStrategy
from core.strategies.registry import get_strategy

logger = logging.getLogger("scripts.run_strategy_selection")


# ---------------------------------------------------------------------------
# 内联确定性多 regime 段合成数据（trend / mean_reversion / ranging 拼接）
# 说明：core/data/synthetic 仅支持 martingale/trend_regime 两种 kind，
# 三 regime 拼接无现成接口，故内联构造（seed 同则同结果）。
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class _Bar:
    symbol: str
    ts_utc: pd.Timestamp
    ts_server: pd.Timestamp
    server_offset_hours: float
    open_: float
    high: float
    low: float
    close: float
    tick_volume: float = 1000.0
    spread_points: object = None


def make_multi_regime_bars(seed: int, n: int) -> list:
    """确定性三 regime 段：趋势上行 / 均值回复振荡 / 低波随机游走。"""
    rng = np.random.default_rng(seed)
    seg1 = n // 3
    seg2 = n // 3
    seg3 = n - seg1 - seg2
    up = rng.normal(0.0008, 0.0004, seg1)                      # 趋势段（正漂移）
    osc = np.sin(np.arange(seg2) * 2.0 * np.pi / 40.0) * 0.0012 \
        + rng.normal(0.0, 0.0003, seg2)                       # MR 段（周期回复）
    flat = rng.normal(0.0, 0.0005, seg3)                      # ranging 段
    rets = np.concatenate([up, osc, flat])
    close = 2600.0 * np.exp(np.cumsum(rets))
    spread_ = np.abs(rng.normal(0.0004, 0.0001, n))
    high = close * (1.0 + spread_)
    low = close * (1.0 - spread_)
    open_ = np.concatenate(([close[0]], close[:-1])) \
        * (1.0 + rng.normal(0.0, 0.0001, n))
    ts = pd.date_range("2024-01-01T00:00:00Z", periods=n, freq="5min")
    return [
        _Bar(symbol="XAUUSD_SYN", ts_utc=t, ts_server=t, server_offset_hours=0.0,
             open_=float(o), high=float(h), low=float(l), close=float(c),
             tick_volume=float(tv))
        for t, o, h, l, c, tv in zip(ts, open_, high, low, close,
                                    rng.integers(50, 500, n))
    ]


# ---------------------------------------------------------------------------
# whipsaw / 成本派生指标（脚本内定义，口径写进报告）
# ---------------------------------------------------------------------------
def whipsaw_counts(trades: list[dict]) -> dict:
    """whipsaw 口径（文档化定义）：
    - dir_flips：按出场时间排序，相邻两笔方向相反的次数（stop-and-reverse 型）；
    - loss_runs：最大连续亏损段数（>=2 连亏的「极大段」个数）。
    """
    ordered = sorted(trades, key=lambda t: t.get("exit_ts", ""))
    dir_flips = 0
    for a, b in zip(ordered, ordered[1:]):
        if int(a.get("direction", 0)) != int(b.get("direction", 0)):
            dir_flips += 1
    loss_runs = 0
    run = 0
    for t in ordered:
        if float(t.get("pnl_usd", 0.0)) < 0:
            run += 1
        else:
            if run >= 2:
                loss_runs += 1
            run = 0
    if run >= 2:
        loss_runs += 1
    return {"dir_flips": int(dir_flips), "loss_runs": int(loss_runs)}


def _mean_finite_ratio(rows: list[dict]) -> float | None:
    """跨折平均成本/毛盈利；全部折无毛盈利（inf）时返回 None（不猜零）。"""
    finite = [r["cost_gross_ratio"] for r in rows
              if np.isfinite(r["cost_gross_ratio"])]
    return float(np.mean(finite)) if finite else None


def est_cost_usd(trades: list[dict], cost: CostModel) -> dict:
    """估算往返成本（trades 不存成本字段，按 CostModel 平静档推算）：
    往返价差 ≈ 2×(base_spread + base_slippage)（合成数据无新闻/跳空）；
    cost_usd = 价差点 × lots × point_value。成本占比 = 估算总成本 / 毛盈利。
    """
    point_per_trade = 2.0 * (float(cost.base_spread) + float(cost.base_slippage))
    total_cost = 0.0
    gross_profit = 0.0
    for t in trades:
        lots = float(t.get("lots", 0.0))
        total_cost += point_per_trade * lots * 100.0  # point_value=100 (XAUUSD)
        if float(t.get("pnl_usd", 0.0)) > 0:
            gross_profit += float(t["pnl_usd"])
    ratio = total_cost / gross_profit if gross_profit > 1e-9 else float("inf")
    return {"est_cost_usd": total_cost, "cost_gross_ratio": ratio}


# ---------------------------------------------------------------------------
# 实验配置与主流程
# ---------------------------------------------------------------------------
@dataclass
class SelectionConfig:
    seed: int = 7
    n_bars: int = 1200
    n_splits: int = 4
    label_window_bars: int = 12          # = max_holding_bars（embargo 下界）
    clean_frac: float = 0.30             # CLEAN 段占比（阈值/分类器拟合）
    known_frac: float = 0.15             # KNOWN 段占比（供需区构建）
    # 冻结占位值：生产路径应由 CLEAN 分布校准（决策 #9），此处仅跑通流程
    blend_alpha: float = 0.3
    blend_deadband: float = 0.05
    blend_confirm_n: int = 2
    min_strength: float = 0.15
    use_gmm: bool = True
    out: str = "experiments/reports/selection_meta.md"
    audit_out: str | None = None


EXPERT_REGIME_MAP = {
    "trend_breakout": "trend",
    "structure_break": "trend",
    "mean_reversion": "mean_reversion",
    "supply_demand": "mean_reversion",
}


def _make_strategy(name: str, known_end_ts):
    """构造单一基线策略实例（与 blend 内部同名字典对齐）。"""
    if name == "trend_breakout":
        return TrendBreakoutStrategy()
    if name == "mean_reversion":
        return MeanReversionStrategy()
    if name == "supply_demand":
        return get_strategy("supply_demand", known_end_ts=known_end_ts)
    if name == "structure_break":
        return get_strategy("structure_break")
    raise KeyError(f"unknown baseline {name}")


def run_selection_experiment(cfg: SelectionConfig) -> dict:
    """端到端跑元层验证；返回对比结果 dict（落盘报告由调用方/ main 负责）。"""
    bars = make_multi_regime_bars(cfg.seed, cfg.n_bars)
    clean_n = int(cfg.n_bars * cfg.clean_frac)
    known_n = int(cfg.n_bars * cfg.known_frac)
    clean_bars = bars[:clean_n]
    known_bars = bars[clean_n:clean_n + known_n]
    trade_bars = bars[clean_n + known_n:]
    if not known_bars:
        raise ValueError("known segment empty; reduce clean_frac or raise n_bars")
    known_end_ts = known_bars[-1].ts_utc

    # CLEAN 段拟合分类器（阈值一次性来自 CLEAN 分布；折内不重估）
    classifier = RegimeClassifier(use_gmm=cfg.use_gmm).fit(clean_bars)
    logger.info("regime classifier fitted on CLEAN: %d bars (gmm=%s)",
                len(clean_bars), classifier._gmm_active)

    cost = CostModel(
        base_spread=0.20, news_spread=0.60, gap_spread=1.0, gap_threshold=1.0,
        base_slippage=0.05, slippage_per_volume_frac=0.10,
        commission_per_lot=0.0, news_minutes=15.0)
    risk_cfg = {
        "initial_equity": 10_000.0, "point_value": 100.0, "risk_pct": 0.01,
        "kelly_cap": 0.25, "min_lot": 0.01, "lot_step": 0.01, "max_lot": 100.0,
        "daily_loss_limit": 0.03, "heat_limit": 1, "bars_per_year": 74880,
        "trail_enable": True,
    }

    folds = purged_walk_forward(
        len(trade_bars), embargo_bars=cfg.label_window_bars,
        n_splits=cfg.n_splits, label_window_bars=cfg.label_window_bars)

    strategy_names = list(EXPERT_REGIME_MAP.keys())
    per_strategy: dict = {n: [] for n in ["regime_blend"] + strategy_names}

    for fold_i, (_train, test_idx) in enumerate(folds):
        s = int(test_idx[0])
        e = int(test_idx[-1]) + 1
        test_start_ts = trade_bars[s].ts_utc
        # 窗口 = KNOWN 段 + 交易段前缀（供需区只在 KNOWN 纪律内构建）
        window = known_bars + trade_bars[:e]

        def _fresh_blend():
            ws = DeadbandWeightState(
                strategy_names, alpha=cfg.blend_alpha,
                deadband=cfg.blend_deadband, confirm_n=cfg.blend_confirm_n)
            return RegimeBlendedStrategy(
                regime_classifier=classifier,
                strategy_names=strategy_names,
                expert_regime_map=dict(EXPERT_REGIME_MAP),
                weight_state=ws,
                min_strength=cfg.min_strength,
                expert_params={"supply_demand": {"known_end_ts": known_end_ts}},
                audit_path=cfg.audit_out,
            )

        runners = {"regime_blend": _fresh_blend()}
        for name in strategy_names:
            runners[name] = _make_strategy(name, known_end_ts)

        for name, strat in runners.items():
            res = run_backtest(window, strat, cost, risk_cfg)
            # OOS 切片：只保留 entry 落在 test 块内的交易与对应权益段
            oos_trades = [t for t in res.trades
                          if pd.Timestamp(t["entry_ts"]) >= test_start_ts]
            eq = res.equity_curve[res.equity_curve.index >= test_start_ts]
            fold_metrics = compute_metrics(eq, oos_trades, bars_per_year=74880)
            fold_metrics.update(whipsaw_counts(oos_trades))
            fold_metrics.update(est_cost_usd(oos_trades, cost))
            fold_metrics["fold"] = fold_i
            fold_metrics["oos_trades"] = len(oos_trades)
            per_strategy[name].append(fold_metrics)
            logger.info("fold %d %s: oos_trades=%d max_dd=%.3f sharpe=%.2f",
                        fold_i, name, len(oos_trades),
                        fold_metrics["max_drawdown"], fold_metrics["sharpe"])

    # 跨折聚合（主指标取均值；交易数求和）
    summary = {}
    for name, rows in per_strategy.items():
        summary[name] = {
            "n_folds": len(rows),
            "oos_trades_total": int(sum(r["oos_trades"] for r in rows)),
            "mean_max_drawdown": float(np.mean([r["max_drawdown"] for r in rows])),
            "mean_sharpe": float(np.mean([r["sharpe"] for r in rows])),
            "mean_dir_flips": float(np.mean([r["dir_flips"] for r in rows])),
            "mean_loss_runs": float(np.mean([r["loss_runs"] for r in rows])),
            "mean_cost_usd": float(np.mean([r["est_cost_usd"] for r in rows])),
            "mean_cost_gross_ratio": _mean_finite_ratio(rows),
            "mean_win_rate": float(np.mean([r["win_rate"] for r in rows])),
        }
    return {
        "seed": cfg.seed, "n_bars": cfg.n_bars, "n_folds": len(folds),
        "clean_bars": len(clean_bars), "known_bars": len(known_bars),
        "trade_bars": len(trade_bars),
        "summary": summary,
        "fold_rows": per_strategy,
    }


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------
def render_report(result: dict, cfg: SelectionConfig) -> str:
    lines = [
        "# 策略自动匹配 · 元层验证对比报告",
        "",
        f"- seed={result['seed']}  n_bars={result['n_bars']}  "
        f"CLEAN={result['clean_bars']}  KNOWN={result['known_bars']}  "
        f"trade={result['trade_bars']}  folds={result['n_folds']}",
        "- 口径：purged walk-forward（embargo=标签窗=12 bar）；阈值一次性来自 "
        "CLEAN 分布，折内不重估（WF 评估策略/混合层绩效，非调参）",
        "- whipsaw：dir_flips=相邻同向出场交易方向反转次数；loss_runs=>=2 连亏极大段数",
        "- 成本：trades 不存成本字段，按 CostModel 平静档 2×(spread+slip)×lots×100 估算",
        "- 混合层冻结占位参数（生产路径由 CLEAN 分布校准）："
        f"alpha={cfg.blend_alpha} deadband={cfg.blend_deadband} "
        f"confirm_n={cfg.blend_confirm_n} min_strength={cfg.min_strength}",
        "",
        "| 策略 | OOS交易数 | 均OOS最大回撤 | 均Sharpe(次) | 均方向反转 | 均连亏段 | 估算成本USD | 成本/毛盈利 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    order = ["regime_blend"] + [n for n in EXPERT_REGIME_MAP]
    for name in order:
        s = result["summary"][name]
        ratio = s["mean_cost_gross_ratio"]
        ratio_s = f"{ratio:.2f}" if ratio is not None else "n/a"
        lines.append(
            f"| {name} | {s['oos_trades_total']} | "
            f"{s['mean_max_drawdown']:.4f} | {s['mean_sharpe']:.2f} | "
            f"{s['mean_dir_flips']:.1f} | {s['mean_loss_runs']:.1f} | "
            f"{s['mean_cost_usd']:.1f} | {ratio_s} |")
    lines += [
        "",
        "> 判读（O09）：成功定义 = 混合层 OOS 回撤 / whipsaw / 成本占比 低于单一基线，"
        "而非 Sharpe 更高；OOS 交易数 < 30 时统计意义不足（O08）。",
        "> 未验证：真实 XAUUSD M5 数据上的元层增益；MT5 实盘执行；经纪商点差差异。",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="策略自动匹配元层验证（合成数据 dryrun）")
    ap.add_argument("--seed", type=int, default=SelectionConfig.seed)
    ap.add_argument("--n-bars", type=int, default=SelectionConfig.n_bars)
    ap.add_argument("--n-splits", type=int, default=SelectionConfig.n_splits)
    ap.add_argument("--out", type=str, default=SelectionConfig.out)
    ap.add_argument("--audit-out", type=str, default=SelectionConfig.audit_out)
    ap.add_argument("--no-gmm", action="store_true", help="关闭 GMM 层（规则软映射降级）")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    cfg = SelectionConfig(
        seed=args.seed, n_bars=args.n_bars, n_splits=args.n_splits,
        out=args.out, audit_out=args.audit_out, use_gmm=not args.no_gmm)
    result = run_selection_experiment(cfg)
    report = render_report(result, cfg)
    print(report)
    Path(cfg.out).parent.mkdir(parents=True, exist_ok=True)
    Path(cfg.out).write_text(report, encoding="utf-8")
    logger.info("report written: %s", cfg.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
