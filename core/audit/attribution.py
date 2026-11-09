# -*- coding: utf-8 -*-
"""core.audit.attribution —— 单笔/组合复盘归因拆分（纯逻辑，无 DB/网络/实盘）。

第一性原理：
    一笔已平仓交易的净盈亏，可以拆成三个可审计、可加和的分量：

        net_pnl = market_component + alpha_component + cost_component

    - market_component：被动敞口在同一持仓窗口内赚到的"贝塔"。
      多头 = notional * benchmark_return；空头 = -notional * benchmark_return。
      benchmark_return 是参考标的在持仓窗口内的买入持有收益（分数），
      由调用方在平仓时点之前冻结传入，函数内不读取任何未来数据。
    - alpha_component：剔除被动敞口与成本后的残差，包含入场/出场择时、
      标的选择与执行质量。单笔残差同时混合了能力与运气，不能在单笔层面
      宣称"技能"；技能证据必须在聚合层面看 alpha 的持续性（见
      :func:`aggregate_attribution`）。
    - cost_component：手续费 + 滑点，恒为非正。

因果约束：
    所有输入都是平仓时点已确定的纯数值；本模块不建连接、不读文件、
    不做绩效网格搜索，阈值/基准由调用方传入。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Sequence

VALID_SIDES = ("buy", "sell")


class AttributionError(ValueError):
    """归因输入非法，携带上下文（硬规则 9：异常带上下文记录）。"""

    def __init__(self, detail: str, **context):
        self.context = {"layer": "audit.attribution", "detail": detail, **context}
        super().__init__(f"AttributionError: {self.context}")


def _finite(name: str, value: float) -> float:
    v = float(value)
    if not math.isfinite(v):
        raise AttributionError(f"{name} must be finite", **{name: value})
    return v


def _finite_num(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value):
        raise AttributionError(f"{name} must be finite number", **{name: value})
    return float(value)


def _opt_finite(name: str, value: object) -> Optional[float]:
    if value is None:
        return None
    return _finite_num(name, value)


def _opt_nonneg_int(name: str, value: object) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AttributionError(f"{name} must be non-negative int", **{name: value})
    return value


@dataclass(frozen=True)
class AttributionResult:
    """单笔交易归因结果（可审计快照）。"""

    pnl: float                       # 净盈亏（扣费后）
    side: str
    entry_price: float
    exit_price: float
    benchmark_return: float          # 参考标的窗口买入持有收益（分数）
    notional: float                  # 入场敞口（金额）
    cost: float                      # 手续费 + 滑点（非负金额）
    market_component: float          # 被动贝塔分量
    alpha_component: float           # 残差（择时/选择/执行；单笔混合运气）
    cost_component: float            # 成本分量（非正）
    own_directional_return: float    # 本标的方向收益（多为正、空为负）
    gross_pnl: float                 # 扣费前盈亏 = pnl + cost
    holding_period: Optional[float] = None
    holding_bars: Optional[int] = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.side not in VALID_SIDES:
            raise AttributionError(f"side must be one of {VALID_SIDES}",
                                   side=self.side)
        for name in ("pnl", "entry_price", "exit_price", "benchmark_return",
                     "notional", "cost", "market_component", "alpha_component",
                     "cost_component", "own_directional_return", "gross_pnl"):
            _finite_num(name, getattr(self, name))
        if self.entry_price <= 0:
            raise AttributionError("entry_price must be > 0",
                                   entry_price=self.entry_price)
        if self.notional < 0:
            raise AttributionError("notional must be >= 0",
                                   notional=self.notional)
        if self.cost < 0:
            raise AttributionError("cost must be >= 0", cost=self.cost)
        _opt_finite("holding_period", self.holding_period)
        _opt_nonneg_int("holding_bars", self.holding_bars)
        if not isinstance(self.notes, tuple) \
                or any(not isinstance(n, str) for n in self.notes):
            raise AttributionError("notes must be tuple of str",
                                   notes=self.notes)

    def decomposition_residual(self, tol: float = 1e-6) -> float:
        """三分量加和与净盈亏的残差（应≈0）。"""
        return self.pnl - (self.market_component + self.alpha_component
                           + self.cost_component)

    def shares(self) -> dict[str, float]:
        """各分量占扣费前盈亏的比例；gross 为 0 时比例记 0，避免除零。"""
        gross = self.gross_pnl
        if gross == 0:
            return {"market": 0.0, "alpha": 0.0, "cost": 0.0}
        return {
            "market": self.market_component / gross,
            "alpha": self.alpha_component / gross,
            "cost": self.cost_component / gross,
        }

    def to_dict(self) -> dict:
        return {
            "pnl": self.pnl,
            "side": self.side,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "benchmark_return": self.benchmark_return,
            "notional": self.notional,
            "cost": self.cost,
            "market_component": self.market_component,
            "alpha_component": self.alpha_component,
            "cost_component": self.cost_component,
            "own_directional_return": self.own_directional_return,
            "gross_pnl": self.gross_pnl,
            "holding_period": self.holding_period,
            "holding_bars": self.holding_bars,
            "shares": self.shares(),
            "notes": list(self.notes),
        }


def split_trade_outcome(
    pnl: float,
    side: str,
    entry_price: float,
    exit_price: float,
    benchmark_return: float,
    notional: float,
    cost: float = 0.0,
    holding_period: Optional[float] = None,
    holding_bars: Optional[int] = None,
) -> AttributionResult:
    """把单笔已平仓交易拆成市场 / 成本 / 策略残差三个分量。

    Args:
        pnl: 净盈亏（扣费后，金额）。
        side: "buy" 或 "sell"。
        entry_price: 入场价（冻结快照）。
        exit_price: 出场价。
        benchmark_return: 参考标的在持仓窗口内的买入持有收益（分数），
            如 0.012 表示 +1.2%；由调用方在平仓时点冻结传入。
        notional: 入场敞口金额（仓位 * 入场价 * 点值）。
        cost: 手续费 + 滑点（非负金额）。
        holding_period: 持仓时长（单位由调用方约定，纯记录用）。
        holding_bars: 持仓 bar 数（纯记录用）。

    Returns:
        AttributionResult；三分量加和与 pnl 的残差可由
        :meth:`AttributionResult.decomposition_residual` 复核。
    """
    if side not in VALID_SIDES:
        raise AttributionError(f"side must be one of {VALID_SIDES}", side=side)

    pnl_v = _finite("pnl", pnl)
    entry = _finite("entry_price", entry_price)
    exit_ = _finite("exit_price", exit_price)
    bench = _finite("benchmark_return", benchmark_return)
    notional_v = _finite("notional", notional)
    cost_v = _finite("cost", cost)

    if entry <= 0:
        raise AttributionError("entry_price must be > 0", entry_price=entry)
    if notional_v < 0:
        raise AttributionError("notional must be >= 0", notional=notional_v)
    if cost_v < 0:
        raise AttributionError("cost must be >= 0", cost=cost_v)

    direction = 1.0 if side == "buy" else -1.0

    # 本标的方向收益：多头看涨跌，空头看跌涨
    own_directional_return = direction * (exit_ - entry) / entry

    gross_pnl = pnl_v + cost_v

    # 被动敞口贝塔：同方向持有参考标的在窗口内的盈亏
    market_component = notional_v * bench * direction

    # 残差：择时 / 选择 / 执行；单笔混合能力与运气
    alpha_component = gross_pnl - market_component

    cost_component = -cost_v

    notes: list[str] = []
    if alpha_component != 0:
        notes.append("单笔 alpha 混合能力与运气，需聚合后看持续性，不可单笔归因技能。")
    if holding_bars is not None and holding_bars <= 0:
        notes.append("持仓 bar 数非正，请核对入场/出场时间戳。")

    return AttributionResult(
        pnl=pnl_v,
        side=side,
        entry_price=entry,
        exit_price=exit_,
        benchmark_return=bench,
        notional=notional_v,
        cost=cost_v,
        market_component=market_component,
        alpha_component=alpha_component,
        cost_component=cost_component,
        own_directional_return=own_directional_return,
        gross_pnl=gross_pnl,
        holding_period=holding_period,
        holding_bars=holding_bars,
        notes=tuple(notes),
    )


def aggregate_attribution(
    results: Sequence[AttributionResult],
) -> dict:
    """聚合多笔归因结果，给出分量合计与 alpha 持续性（纯统计，不做显著性检验）。

    技能证据口径：alpha 合计为正且 alpha 为正的交易占比偏高；
    是否统计显著须在 CLEAN 集上另行检验，本函数不下显著性结论。
    """
    n = len(results)
    if n == 0:
        return {
            "n_trades": 0,
            "pnl_total": 0.0,
            "market_total": 0.0,
            "alpha_total": 0.0,
            "cost_total": 0.0,
            "gross_total": 0.0,
            "alpha_positive_share": 0.0,
            "market_positive_share": 0.0,
            "alpha_share_of_gross": 0.0,
            "note": "无交易样本。",
        }

    pnl_total = sum(r.pnl for r in results)
    market_total = sum(r.market_component for r in results)
    alpha_total = sum(r.alpha_component for r in results)
    cost_total = sum(r.cost_component for r in results)
    gross_total = sum(r.gross_pnl for r in results)

    alpha_pos = sum(1 for r in results if r.alpha_component > 0)
    market_pos = sum(1 for r in results if r.market_component > 0)

    return {
        "n_trades": n,
        "pnl_total": pnl_total,
        "market_total": market_total,
        "alpha_total": alpha_total,
        "cost_total": cost_total,
        "gross_total": gross_total,
        "alpha_positive_share": alpha_pos / n,
        "market_positive_share": market_pos / n,
        "alpha_share_of_gross": (alpha_total / gross_total) if gross_total != 0 else 0.0,
        "note": "alpha 持续性为描述性口径；显著性须在 CLEAN 集上另行检验，"
                "单笔残差不等同于技能。",
    }
