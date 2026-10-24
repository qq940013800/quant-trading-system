# -*- coding: utf-8 -*-
"""core.backtest.engine —— 事件驱动 bar 回测引擎。

冻结接口（设计 3.2）：
    run_backtest(bars, strategy, cost_model, risk_cfg) -> BacktestResult

因果纪律（硬规则 5 / c06_intrabar）：
- 只在已收盘 bar 上产生信号与退出决策；信号在 bar[i] 收盘后决策，于 bar[i+1] 开盘价成交。
- 止损机械触发用已收盘 bar 的 high/low，不是"成形中 bar"。
- 任何统计量（realized vol / ATR）只在 history[:i+1] 已收盘 bar 上计算。

成本：三档点差（平静/新闻±15min/跳空）+ 滑点 + 佣金，全部来自 cost_model/config。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, Protocol

import numpy as np
import pandas as pd

from ..audit.record import Decision, write_decision
from ..risk.circuit import CircuitBreaker
from ..risk.sizing import target_lots, vol_target_scale
from ..risk.state import RiskState
from ..risk.stops import StopWideningError, initial_stop, update_stop
from .broker import simulate_fill
from .costs import CostModel, is_news_time, slippage_points, spread_at
from .metrics import compute_metrics

log = logging.getLogger("core.backtest")


class BarLike(Protocol):
    """最小 Bar 鸭子类型（与 core.data.bar.Bar schema 对齐，本包不 import 以解耦）。"""
    ts_utc: pd.Timestamp
    open_: float
    high: float
    low: float
    close: float
    tick_volume: float


@dataclass
class Position:
    symbol: str
    direction: int          # +1/-1
    entry_price: float
    lots: float
    atr0: float             # 入场冻结
    entry_dist: float        # 入场冻结，R 倍数分母
    stop_price: float
    entry_ts: pd.Timestamp
    decision_id: str


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    trades: list
    metrics: dict
    decisions: list = field(default_factory=list)


# --------------------------------------------------------------------------- #
# 策略协议：on_bar_close(已收盘 history, 当前已收盘 bar) -> Signal-like | None
# --------------------------------------------------------------------------- #
class Strategy(Protocol):
    def on_bar_close(self, history: list, bar) -> Optional[object]: ...


@dataclass
class _Signal:
    """引擎内部 Signal 鸭子类型（与设计 3.1 Signal schema 字段一致）。"""
    signal_id: str
    bar_ts_utc: pd.Timestamp
    expert: str
    direction: int
    price_ref: float
    atr0: float
    entry_dist: float
    l1_in_zone: bool
    regime_weights: dict
    meta_p: Optional[float]


def _wilder_atr(history: list, n: int = 14) -> float:
    """在已收盘 history 上计算 ATR（demo 用；不读未来 bar）。"""
    if len(history) < 2:
        return 0.0
    trs = []
    prev_close = None
    for b in history:
        hi, lo = float(b.high), float(b.low)
        if prev_close is None:
            trs.append(hi - lo)
        else:
            trs.append(max(hi - lo, abs(hi - prev_close), abs(lo - prev_close)))
        prev_close = float(b.close)
    arr = np.array(trs[-n:], dtype=float)
    return float(arr.mean()) if arr.size else 0.0


class DemoBreakoutStrategy:
    """演示用 Donchian 突破策略（非生产专家；仅用于 pipeline 自检与 CLI 可跑）。"""

    def __init__(self, lookback: int = 20, atr_n: int = 14,
                 entry_dist_mult: float = 2.0, symbol: str = "XAUUSD"):
        self.lookback = int(lookback)
        self.atr_n = int(atr_n)
        self.entry_dist_mult = float(entry_dist_mult)
        self.symbol = symbol

    def on_bar_close(self, history: list, bar) -> Optional[_Signal]:
        if len(history) < self.lookback + 2:
            return None
        win = history[-(self.lookback + 1):-1]   # 不含当前 bar，避免自比
        hh = max(float(b.high) for b in win)
        ll = min(float(b.low) for b in win)
        atr0 = _wilder_atr(history, self.atr_n)
        if atr0 <= 0:
            return None
        price = float(bar.close)
        direction = 0
        if price > hh:
            direction = +1
        elif price < ll:
            direction = -1
        if direction == 0:
            return None
        return _Signal(
            signal_id=f"{self.symbol}_{bar.ts_utc.isoformat()}_{self.__class__.__name__}_{direction}",
            bar_ts_utc=bar.ts_utc,
            expert="demo_breakout",
            direction=direction,
            price_ref=price,
            atr0=atr0,
            entry_dist=self.entry_dist_mult * atr0,
            l1_in_zone=True,
            regime_weights={"trend": 1.0, "mr": 0.0, "range": 0.0},
            meta_p=None,
        )


# --------------------------------------------------------------------------- #
# 主循环
# --------------------------------------------------------------------------- #
def run_backtest(bars: list, strategy: Strategy,
                cost_model: Optional[CostModel],
                risk_cfg: dict) -> BacktestResult:
    """事件驱动回测。bars 必须按 ts_utc 单调、且全部为已收盘 bar。"""
    cfg = risk_cfg or {}
    initial_equity = float(cfg.get("initial_equity", 10_000.0))
    point_value = float(cfg.get("point_value", 100.0))
    risk_pct = float(cfg.get("risk_pct", 0.01))
    kelly_cap = float(cfg.get("kelly_cap", 0.25))
    min_lot = float(cfg.get("min_lot", 0.01))
    lot_step = float(cfg.get("lot_step", 0.01))
    max_lot = float(cfg.get("max_lot", 100.0))
    heat_limit = int(cfg.get("heat_limit", 1))
    daily_loss_limit = float(cfg.get("daily_loss_limit", 0.03))
    cooldown_bars = int(cfg.get("cooldown_bars", 12))
    meta_p_threshold = float(cfg.get("meta_p_threshold", 0.30))
    require_zone = bool(cfg.get("require_l1_zone", True))
    target_vol = float(cfg.get("target_vol", 0.0))
    vol_lookback = int(cfg.get("vol_lookback", 60))
    trail_enable = bool(cfg.get("trail_enable", True))
    trail_after_r = float(cfg.get("trail_after_r", 1.0))
    trail_to_r = float(cfg.get("trail_to_r", 0.0))
    news_window = list(cfg.get("news_window", []) or [])
    audit_path = cfg.get("audit_path")
    bars_per_year = int(cfg.get("bars_per_year", 74880))
    decision_rule_version = str(cfg.get("decision_rule_version", "rules-v1"))
    threshold_dataset = str(cfg.get("threshold_dataset", "CLEAN"))

    equity = initial_equity
    peak_equity = initial_equity
    cb = CircuitBreaker(daily_loss_limit=daily_loss_limit, cooldown_bars=cooldown_bars)
    positions: list[Position] = []
    pending: Optional[tuple] = None
    decisions: list[Decision] = []
    trades: list[dict] = []
    eq_idx: list = []
    eq_val: list = []
    next_decision_seq = 1

    def _drawdown_tier() -> float:
        # 海龟分级降档：每回撤 -10% ×0.8（阈值来自 config，这里只做分级算术）
        if peak_equity <= 0:
            return 1.0
        dd = equity / peak_equity - 1.0
        steps = max(0, int(np.floor(-dd / 0.10)))
        return float(0.8 ** steps)

    def _realized_vol(history: list) -> float:
        if len(history) < 3:
            return 0.0
        closes = np.array([float(b.close) for b in history[-vol_lookback:]], dtype=float)
        rets = np.diff(np.log(closes))
        return float(rets.std(ddof=1)) if rets.size > 1 else 0.0

    for i, bar in enumerate(bars):
        ts = bar.ts_utc
        prev_close = float(bars[i - 1].close) if i > 0 else None

        # 0. 推进熔断（用当前权益）
        circuit_state = cb.update(equity, ts)

        # 1. 止损机械退出（用本已收盘 bar 的 high/low）
        kept: list[Position] = []
        for pos in positions:
            hit = False
            if pos.direction == +1 and float(bar.low) <= pos.stop_price:
                hit = True
                exit_ref = pos.stop_price
            elif pos.direction == -1 and float(bar.high) >= pos.stop_price:
                hit = True
                exit_ref = pos.stop_price
            if not hit:
                kept.append(pos)
                continue
            spread = spread_at(bar, news_window, prev_close, cost_model)
            slip = slippage_points(bar, pos.lots / max(float(bar.tick_volume), 1.0), cost_model)
            fill = simulate_fill(-pos.direction, exit_ref, spread, slip,
                                 0.0, pos.lots, point_value)  # 平仓不再额外计佣金往返可配
            gross = (fill.fill_price - pos.entry_price) * pos.direction * pos.lots * point_value
            pnl = gross - fill.cost
            equity += pnl
            r_mult = ((fill.fill_price - pos.entry_price) * pos.direction
                      / pos.entry_dist) if pos.entry_dist > 0 else 0.0
            trades.append({
                "decision_id": pos.decision_id, "entry_ts": str(pos.entry_ts),
                "exit_ts": str(ts), "direction": pos.direction,
                "entry_price": pos.entry_price, "exit_price": fill.fill_price,
                "lots": pos.lots, "pnl_usd": pnl, "r_multiple": r_mult,
            })
        positions = kept

        # 1b. 移动止损（trailing）：强制 update_stop 单调（放宽即抛 StopWideningError）
        if trail_enable:
            for pos in positions:
                adv_r = (float(bar.close) - pos.entry_price) * pos.direction / pos.entry_dist
                if adv_r >= trail_after_r:
                    cand = pos.entry_price + trail_to_r * pos.entry_dist * pos.direction
                    try:
                        new_stop = update_stop(pos.stop_price, cand, pos.direction,
                                              symbol=pos.symbol, ts_utc=str(ts))
                        pos.stop_price = new_stop
                    except StopWideningError:
                        # 放宽方向被拒：保持原止损（异常自带上下文，记录不吞掉）
                        log.debug("trail rejected (monotonic): pos=%s ts=%s",
                                  pos.decision_id, ts)

        # 2. 上一根 bar 决策的 pending 入场，在本 bar 开盘成交
        if pending is not None:
            sig, dec = pending
            if cb.allows_new_position and len(positions) < heat_limit:
                spread = spread_at(bar, news_window, prev_close, cost_model)
                slip = slippage_points(bar, dec.final_signed_lots / max(float(bar.tick_volume), 1.0),
                                       cost_model)
                fill = simulate_fill(sig.direction, float(bar.open_), spread, slip,
                                     float(cfg.get("commission_per_lot", 0.0)),
                                     dec.final_signed_lots, point_value)
                equity -= fill.cost
                stop = initial_stop(fill.fill_price, sig.direction, sig.entry_dist)
                positions.append(Position(
                    symbol=getattr(bar, "symbol", "XAUUSD"), direction=sig.direction,
                    entry_price=fill.fill_price, lots=dec.final_signed_lots,
                    atr0=sig.atr0, entry_dist=sig.entry_dist, stop_price=stop,
                    entry_ts=ts, decision_id=dec.decision_id))
            pending = None

        # 3. 在本已收盘 bar 上请求新信号（intra-bar 不决策）
        if cb.allows_new_position and len(positions) < heat_limit:
            sig = strategy.on_bar_close(bars[:i + 1], bar)
            if sig is not None:
                dec = _adjudicate(
                    sig, equity=equity, peak_equity=peak_equity, cb_state=circuit_state,
                    news_window=news_window, point_value=point_value, risk_pct=risk_pct,
                    kelly_cap=kelly_cap, min_lot=min_lot, lot_step=lot_step, max_lot=max_lot,
                    meta_p_threshold=meta_p_threshold, require_zone=require_zone,
                    target_vol=target_vol, realized_vol=_realized_vol(bars[:i + 1]),
                    drawdown_tier=_drawdown_tier(), seq=next_decision_seq,
                    decision_rule_version=decision_rule_version,
                    threshold_dataset=threshold_dataset, audit_path=audit_path,
                    model_version=str(cfg.get("model_version", "rules-v1")),
                )
                next_decision_seq += 1
                decisions.append(dec)
                if dec.accepted:
                    pending = (sig, dec)

        # 4. 盯市权益（bar 收盘）
        peak_equity = max(peak_equity, equity)
        unreal = 0.0
        for pos in positions:
            unreal += (float(bar.close) - pos.entry_price) * pos.direction * pos.lots * point_value
        eq_idx.append(ts)
        eq_val.append(equity + unreal)

    equity_curve = pd.Series(eq_val, index=pd.DatetimeIndex(eq_idx), name="equity")
    metrics = compute_metrics(equity_curve, trades, bars_per_year=bars_per_year)
    return BacktestResult(equity_curve=equity_curve, trades=trades,
                          metrics=metrics, decisions=decisions)


def _adjudicate(sig, *, equity, peak_equity, cb_state, news_window,
                point_value, risk_pct, kelly_cap, min_lot, lot_step, max_lot,
                meta_p_threshold, require_zone, target_vol, realized_vol,
                drawdown_tier, seq, decision_rule_version, threshold_dataset,
                audit_path, model_version) -> Decision:
    """对候选信号做风控裁决，产出 Decision（接受/拒绝都落快照）。"""
    rid = f"D{seq:08d}"
    fs = {
        "equity": float(equity), "price_ref": float(sig.price_ref),
        "atr0": float(sig.atr0), "entry_dist": float(sig.entry_dist),
        "l1_in_zone": bool(sig.l1_in_zone), "regime_weights": dict(sig.regime_weights),
        "meta_p": sig.meta_p,
        # replay 契约：sizing 输入
        "risk_pct": float(risk_pct),
        "stop_dist_price": float(sig.entry_dist),
        "point_value": float(point_value), "min_lot": float(min_lot),
        "lot_step": float(lot_step), "kelly_cap": float(kelly_cap),
        "vol_scale": 1.0, "drawdown_tier": float(drawdown_tier),
    }
    base_state = RiskState(
        equity=float(equity), atr0=float(sig.atr0), entry_dist=float(sig.entry_dist),
        stop_price=float("nan"), heat_units=0, circuit_state=cb_state,
        drawdown_tier=float(drawdown_tier))

    # --- 拒绝判定链（顺序固定，先到先拒）---
    reject = None
    if cb_state != "normal":
        reject = "circuit_breaker"
    elif is_news_time(sig.bar_ts_utc, news_window):
        reject = "news_window"
    elif require_zone and not sig.l1_in_zone:
        reject = "l1_out_of_zone"
    elif sig.meta_p is not None and sig.meta_p < meta_p_threshold:
        reject = f"meta_p<quantile_{int(meta_p_threshold*100)}"

    if reject is not None:
        dec = Decision(
            decision_id=rid, signal=sig, feature_snapshot=fs,
            model_version=model_version, risk_state=base_state,
            accepted=False, reject_reason=reject, final_signed_lots=0.0,
            threshold_dataset=threshold_dataset,
            decision_rule_version=decision_rule_version)
        if audit_path:
            write_decision(audit_path, dec)
        return dec

    # --- 接受：vol-target 叠加 + 回撤降档 + Kelly cap ---
    vol_scale = 1.0
    if target_vol > 0 and realized_vol > 0:
        vol_scale = vol_target_scale(realized_vol, target_vol)
    eff_risk_pct = float(risk_pct) * float(drawdown_tier)
    lots = target_lots(equity=equity, risk_pct=eff_risk_pct, atr0=float(sig.entry_dist),
                       point_value=point_value, min_lot=min_lot, lot_step=lot_step,
                       kelly_cap=kelly_cap, max_lot=max_lot)
    lots = round(lots * vol_scale, 8)
    lots = max(0.0, np.floor(lots / lot_step + 1e-9) * lot_step)
    fs["vol_scale"] = float(vol_scale)

    if lots <= 0:
        dec = Decision(
            decision_id=rid, signal=sig, feature_snapshot=fs,
            model_version=model_version, risk_state=base_state,
            accepted=False, reject_reason="lot_below_min", final_signed_lots=0.0,
            threshold_dataset=threshold_dataset,
            decision_rule_version=decision_rule_version)
    else:
        dec = Decision(
            decision_id=rid, signal=sig, feature_snapshot=fs,
            model_version=model_version, risk_state=base_state,
            accepted=True, reject_reason=None, final_signed_lots=float(lots),
            threshold_dataset=threshold_dataset,
            decision_rule_version=decision_rule_version)
    if audit_path:
        write_decision(audit_path, dec)
    return dec
