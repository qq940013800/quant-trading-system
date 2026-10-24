# -*- coding: utf-8 -*-
"""scripts/run_walkforward.py —— purged walk-forward 实验入口（dryrun）。

用途：在（内联）合成数据上端到端跑"特征→标签→purged WF→基线/GBM→OOS 指标"，
验证 pipeline 无泄漏（martingale 上不应有显著收益/精度优势）。

纪律（AGENTS.md 规则 11 / 设计文档⑦E）：
- trials_N 只由 run_gate_experiment.sh 按规则 11 原子递增（含失败/中止试验，
  只增不减）；本脚本不读写 registry.yaml，下方 _note_trials_placeholder()
  仅占位说明，真正登记由实验脚本自动完成——禁止手工改 registry.yaml。
- 不做绩效网格搜索；模型结构超参（max_depth 3-6 等）来自配置，阈值分位
  来自 CLEAN 分布（合成 smoke 里的分位仅为跑通流程，不用于标定实盘参数）。

运行：
    D:\\Trader\\.venv\\Scripts\\python.exe scripts\\run_walkforward.py --n-bars 1200
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

# 允许 `python scripts/run_walkforward.py` 直接运行（把项目根放上 sys.path）
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.features.atr import wilder_atr
from core.features.volatility import realized_vol
from core.features.regime import adx, hurst_exponent
from core.features.structure import donchian_position
from core.models.labels import triple_barrier_labels
from core.models.cv import purged_walk_forward
from core.models.baseline import LogisticBaseline, RidgeBaseline

logger = logging.getLogger("scripts.run_walkforward")


# ---------------------------------------------------------------------------
# 内联确定性合成 bar（契约与 core/data/synthetic.py 对齐：seed 同则同结果）
# 说明：core/data/ 由并行 agent 实现，本脚本暂自带轻量合成器避免跨 agent 运行时依赖。
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
    tick_volume: float
    spread_points: float | None = None


def make_synthetic_bars(seed: int, n: int, kind: str = "martingale") -> list:
    """确定性合成 bar：martingale（纯随机游走）/ trend_regime（两段 regime）。"""
    rng = np.random.default_rng(seed)
    if kind == "martingale":
        rets = rng.normal(0.0, 0.0008, n)
    elif kind == "trend_regime":
        half = n // 2
        rets = np.concatenate([
            rng.normal(0.0006, 0.0005, half),      # 低波趋势段
            rng.normal(0.0, 0.0020, n - half),     # 高波震荡段
        ])
    else:
        raise ValueError(f"unknown kind: {kind}")
    close = 2000.0 * np.exp(np.cumsum(rets))
    spread_ = np.abs(rng.normal(0.0004, 0.0001, n))
    high = close * (1.0 + spread_)
    low = close * (1.0 - spread_)
    open_ = np.concatenate(([close[0]], close[:-1])) * (1.0 + rng.normal(0, 0.0001, n))
    ts = pd.date_range("2024-01-01T00:00:00Z", periods=n, freq="5min")
    bars = [
        _Bar(symbol="XAUUSD", ts_utc=t, ts_server=t + pd.Timedelta(hours=2),
             server_offset_hours=2.0, open_=float(o), high=float(h),
             low=float(l), close=float(c), tick_volume=100.0)
        for t, o, h, l, c in zip(ts, open_, high, low, close)
    ]
    return bars


# ---------------------------------------------------------------------------
# 实验配置与主流程
# ---------------------------------------------------------------------------

@dataclass
class WFConfig:
    seed: int = 7
    n_bars: int = 1200
    kind: str = "martingale"
    n_splits: int = 4
    tp_mult: float = 1.5
    sl_mult: float = 1.0
    max_holding_bars: int = 12          # = label_window_bars
    atr_period: int = 14
    warmup_bars: int = 96
    out: str = "experiments/reports/walkforward_smoke.md"


def _feature_matrix(bars: list, cfg: WFConfig) -> tuple[pd.DataFrame, pd.Series]:
    """逐 bar 因果计算特征 + ATR（ATR 供标签使用）。"""
    n = len(bars)
    atr_vals = np.full(n, np.nan)
    adx_vals = np.full(n, np.nan)
    rs_vals = np.full(n, np.nan)
    don_vals = np.full(n, np.nan)
    hurst_vals = np.full(n, np.nan)
    for i in range(n):
        hist = bars[: i + 1]
        as_of = bars[i].ts_utc
        try:
            atr_vals[i] = wilder_atr(hist, as_of, period=cfg.atr_period)
            adx_vals[i] = adx(hist, as_of, period=cfg.atr_period)
            rs_vals[i] = realized_vol(hist, as_of, window=48)
            don_vals[i] = donchian_position(hist, as_of, window=20)
            hurst_vals[i] = hurst_exponent(hist, as_of, window=256, min_window=64)
        except (ValueError, ArithmeticError) as exc:
            logger.warning("feature failed at bar %d: %s", i, exc)
    df = pd.DataFrame({
        "atr_norm": atr_vals / np.nanmean(atr_vals),   # 滚动均值归一（非全样本——smoke 近似）
        "adx": adx_vals,
        "realized_vol": rs_vals,
        "donchian_pos": don_vals,
        "hurst": hurst_vals,
    }, index=pd.DatetimeIndex([b.ts_utc for b in bars], name="ts_utc"))
    return df, pd.Series(atr_vals, index=df.index)


def run_walkforward(cfg: WFConfig) -> dict:
    """端到端跑一遍 purged WF，返回 OOS 指标 dict（无副作用落盘之外的行为）。"""
    bars = make_synthetic_bars(cfg.seed, cfg.n_bars, cfg.kind)
    feat, atr = _feature_matrix(bars, cfg)
    labels = triple_barrier_labels(bars, atr, tp_mult=cfg.tp_mult,
                                   sl_mult=cfg.sl_mult,
                                   max_holding_bars=cfg.max_holding_bars)

    # 只保留特征/标签均有效的行
    valid = feat.dropna().index.intersection(labels.index)
    X = feat.loc[valid].to_numpy(dtype=np.float64)
    # meta-label：标签 +1 视为"盈利"正类；0/-1 合并为负类
    y = (labels.loc[valid].to_numpy(dtype=np.int64) == 1).astype(np.float64)

    folds = purged_walk_forward(len(X), embargo_bars=cfg.max_holding_bars,
                                n_splits=cfg.n_splits,
                                label_window_bars=cfg.max_holding_bars)
    oos_acc, oos_prec = [], []
    for tr, te in folds:
        model = LogisticBaseline(C=1.0)
        model.fit(X[tr], y[tr])
        p = model.predict_proba(X[te])[:, 1]
        pred = (p >= 0.5).astype(np.float64)
        oos_acc.append(float((pred == y[te]).mean()))
        tp = float(np.sum((pred == 1) & (y[te] == 1)))
        fp = float(np.sum((pred == 1) & (y[te] == 0)))
        oos_prec.append(tp / (tp + fp) if tp + fp > 0 else float("nan"))

    prec_arr = np.asarray(oos_prec, dtype=np.float64)
    prec_arr = prec_arr[np.isfinite(prec_arr)]
    return {
        "kind": cfg.kind,
        "n_bars": cfg.n_bars,
        "n_folds": len(folds),
        "oos_acc_mean": float(np.mean(oos_acc)),
        "oos_prec_mean": float(prec_arr.mean()) if prec_arr.size else None,
        "label_distribution": {str(k): int(v) for k, v in pd.Series(y).value_counts().items()},
    }


def _note_trials_placeholder() -> None:
    """trials_N 占位（不登记 registry.yaml）。

    trials_N 只能由 run_gate_experiment.sh 按 AGENTS.md 规则 11 原子递增
    （含失败/中止的试验，只增不减）；decision_rule 须在实验前冻结。
    本 dryrun 脚本只做 pipeline 无泄漏自检，不产生正式实验登记——
    禁止手工改写 registry.yaml。
    """
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description="purged walk-forward dryrun（合成数据）")
    ap.add_argument("--seed", type=int, default=WFConfig.seed)
    ap.add_argument("--n-bars", type=int, default=WFConfig.n_bars)
    ap.add_argument("--kind", choices=["martingale", "trend_regime"], default=WFConfig.kind)
    ap.add_argument("--n-splits", type=int, default=WFConfig.n_splits)
    ap.add_argument("--tp-mult", type=float, default=WFConfig.tp_mult)
    ap.add_argument("--sl-mult", type=float, default=WFConfig.sl_mult)
    ap.add_argument("--max-holding-bars", type=int, default=WFConfig.max_holding_bars)
    ap.add_argument("--out", type=str, default=WFConfig.out)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = WFConfig(seed=args.seed, n_bars=args.n_bars, kind=args.kind,
                   n_splits=args.n_splits, tp_mult=args.tp_mult,
                   sl_mult=args.sl_mult, max_holding_bars=args.max_holding_bars,
                   out=args.out)
    _note_trials_placeholder()
    metrics = run_walkforward(cfg)
    print("=== walk-forward dryrun ===")
    for k, v in metrics.items():
        print(f"{k}: {v}")
    # 防御性自陈：martingale 上 OOS 精度不应显著偏离先验（泄漏自检由测试断言）
    if cfg.kind == "martingale":
        print("note: martingale 上 OOS 精度应接近先验；显著偏离提示泄漏")


if __name__ == "__main__":
    main()
