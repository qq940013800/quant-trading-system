# -*- coding: utf-8 -*-
"""core.execution.reconcile —— 订单/持仓对账（实盘安全的关键闭环）。

第一性原理：
    "本地以为的持仓"与"经纪商实际持仓"是两套独立事实。两者不一致时，
    任何策略决策都建立在错误状态上——幽灵持仓、漏单、重复下单都由此而来。

本模块只做纯函数比较 + 报告 + 触发开关，不做网络 I/O：
    - 本地订单（core.execution.engine.Order）/ 本地持仓（Position）
    - 经纪商回报（mapping 或对象，字段见 OrderView/PositionView）
    - 输出 ReconcileReport；非空即触发 KillSwitch（由调用方决定是否 enforce）

对账口径：
    - 订单按 order_id 匹配；比较 side / quantity / filled_quantity（容忍度内视为一致）；
    - 持仓按 symbol 匹配；比较 side / quantity；
    - 缺失（本地有、经纪商无）与多余（经纪商有、本地无）都算严重问题；
    - 重复 id 单独标记（数据完整性错误）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from core.control.kill_switch import KillSwitch

_DEFAULT_QTY_ABS = 1e-6
_DEFAULT_QTY_REL = 1e-4


@dataclass(frozen=True)
class Tolerance:
    """数量比较容忍度：绝对 + 相对，取较大者。"""

    qty_abs: float = _DEFAULT_QTY_ABS
    qty_rel: float = _DEFAULT_QTY_REL

    def equals(self, a: float, b: float) -> bool:
        limit = max(self.qty_abs, self.qty_rel * max(abs(float(a)), abs(float(b))))
        return abs(float(a) - float(b)) <= limit


@dataclass(frozen=True)
class OrderView:
    """对账用的订单视图（本地/经纪商统一口径）。"""

    order_id: str
    symbol: str
    side: str            # "buy" / "sell"
    quantity: float
    filled_quantity: float = 0.0
    status: str = ""


@dataclass(frozen=True)
class PositionView:
    """对账用的持仓视图（本地/经纪商统一口径）。"""

    symbol: str
    side: str            # "buy" / "sell"
    quantity: float
    entry_price: float = 0.0


@dataclass
class ReconcileReport:
    """对账结果。任一分项非空都表示必须人工/自动处置。"""

    tolerance: Tolerance = field(default_factory=Tolerance)
    missing_orders: list[str] = field(default_factory=list)          # 本地有、经纪商无
    unknown_orders: list[str] = field(default_factory=list)          # 经纪商有、本地无
    duplicate_local_orders: list[str] = field(default_factory=list)
    duplicate_broker_orders: list[str] = field(default_factory=list)
    order_mismatches: list[dict[str, Any]] = field(default_factory=list)
    missing_positions: list[str] = field(default_factory=list)
    unknown_positions: list[str] = field(default_factory=list)
    position_mismatches: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not self.critical_codes()

    def critical_codes(self) -> list[str]:
        """返回所有严重问题的代码列表（顺序稳定，便于审计比对）。"""
        codes: list[str] = []
        if self.missing_orders:
            codes.append("ORDER_MISSING")
        if self.unknown_orders:
            codes.append("ORDER_UNKNOWN")
        if self.duplicate_local_orders:
            codes.append("ORDER_DUPLICATE_LOCAL")
        if self.duplicate_broker_orders:
            codes.append("ORDER_DUPLICATE_BROKER")
        if self.order_mismatches:
            codes.append("ORDER_MISMATCH")
        if self.missing_positions:
            codes.append("POSITION_MISSING")
        if self.unknown_positions:
            codes.append("POSITION_UNKNOWN")
        if self.position_mismatches:
            codes.append("POSITION_MISMATCH")
        return codes

    def summary(self) -> str:
        if self.is_clean:
            return "reconcile clean"
        parts = [f"{k}={len(v)}" for k, v in {
            "missing_orders": self.missing_orders,
            "unknown_orders": self.unknown_orders,
            "order_mismatches": self.order_mismatches,
            "missing_positions": self.missing_positions,
            "unknown_positions": self.unknown_positions,
            "position_mismatches": self.position_mismatches,
        }.items() if v]
        return "reconcile mismatch: " + ", ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_clean": self.is_clean,
            "codes": self.critical_codes(),
            "summary": self.summary(),
            "missing_orders": list(self.missing_orders),
            "unknown_orders": list(self.unknown_orders),
            "duplicate_local_orders": list(self.duplicate_local_orders),
            "duplicate_broker_orders": list(self.duplicate_broker_orders),
            "order_mismatches": list(self.order_mismatches),
            "missing_positions": list(self.missing_positions),
            "unknown_positions": list(self.unknown_positions),
            "position_mismatches": list(self.position_mismatches),
            "tolerance": {"qty_abs": self.tolerance.qty_abs,
                          "qty_rel": self.tolerance.qty_rel},
        }


# ----------------------------------------------------------------------
# 归一化：接受 dataclass / mapping / 带属性对象
# ----------------------------------------------------------------------
def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def normalize_side(value: Any) -> str:
    """把 OrderSide/±1/"long"/"BUY" 统一成 "buy"/"sell"；未知值原样小写返回。"""
    if value is None:
        return ""
    if hasattr(value, "value"):
        value = value.value
    text = str(value).strip().lower()
    if text in {"buy", "b", "long", "+1", "1"}:
        return "buy"
    if text in {"sell", "s", "short", "-1"}:
        return "sell"
    return text


def as_order_view(obj: Any) -> OrderView:
    oid = _get(obj, "order_id")
    if oid is None:
        oid = _get(obj, "id")
    if oid is None:
        raise ValueError(f"order has no order_id: {obj!r}")
    return OrderView(
        order_id=str(oid),
        symbol=str(_get(obj, "symbol", "")),
        side=normalize_side(_get(obj, "side")),
        quantity=float(_get(obj, "quantity", 0.0)),
        filled_quantity=float(_get(obj, "filled_quantity", 0.0)),
        status=str(_get(obj, "status", "") or ""),
    )


def as_position_view(obj: Any) -> PositionView:
    if isinstance(obj, PositionView):
        return obj
    symbol = _get(obj, "symbol")
    if symbol is None:
        raise ValueError(f"position has no symbol: {obj!r}")
    direction = _get(obj, "direction")
    side_raw = _get(obj, "side", direction)
    qty_raw = _get(obj, "quantity", None)
    if qty_raw is None:
        qty_raw = _get(obj, "lots", 0.0)  # 兼容 core.backtest.engine.Position
    return PositionView(
        symbol=str(symbol),
        side=normalize_side(side_raw),
        quantity=abs(float(qty_raw)),
        entry_price=float(_get(obj, "entry_price", 0.0) or 0.0),
    )


def _normalize_positions(positions: Any) -> list[PositionView]:
    """持仓输入可以是 mapping(symbol->position)、序列或单个对象。"""
    if positions is None:
        return []
    if isinstance(positions, Mapping):
        return [as_position_view(v) for v in positions.values()]
    if isinstance(positions, PositionView):
        return [positions]
    return [as_position_view(p) for p in positions]


# ----------------------------------------------------------------------
# 主函数
# ----------------------------------------------------------------------
def reconcile(
    local_orders: Iterable[Any] | None,
    local_positions: Any,
    broker_orders: Iterable[Any] | None,
    broker_positions: Any,
    tolerance: Tolerance | None = None,
) -> ReconcileReport:
    """比较本地状态与经纪商状态，返回 ReconcileReport。纯函数、无副作用。"""
    tol = tolerance or Tolerance()
    report = ReconcileReport(tolerance=tol)

    # ---- 订单 ----
    local_map: dict[str, OrderView] = {}
    for obj in local_orders or []:
        view = as_order_view(obj)
        if view.order_id in local_map:
            if view.order_id not in report.duplicate_local_orders:
                report.duplicate_local_orders.append(view.order_id)
            continue
        local_map[view.order_id] = view

    broker_map: dict[str, OrderView] = {}
    for obj in broker_orders or []:
        view = as_order_view(obj)
        if view.order_id in broker_map:
            if view.order_id not in report.duplicate_broker_orders:
                report.duplicate_broker_orders.append(view.order_id)
            continue
        broker_map[view.order_id] = view

    report.missing_orders = sorted(set(local_map) - set(broker_map))
    report.unknown_orders = sorted(set(broker_map) - set(local_map))

    for oid in sorted(set(local_map) & set(broker_map)):
        lo, bo = local_map[oid], broker_map[oid]
        if lo.side != bo.side:
            report.order_mismatches.append({
                "order_id": oid, "field": "side",
                "local": lo.side, "broker": bo.side,
            })
        if not tol.equals(lo.quantity, bo.quantity):
            report.order_mismatches.append({
                "order_id": oid, "field": "quantity",
                "local": lo.quantity, "broker": bo.quantity,
                "delta": bo.quantity - lo.quantity,
            })
        if not tol.equals(lo.filled_quantity, bo.filled_quantity):
            report.order_mismatches.append({
                "order_id": oid, "field": "filled_quantity",
                "local": lo.filled_quantity, "broker": bo.filled_quantity,
                "delta": bo.filled_quantity - lo.filled_quantity,
            })

    # ---- 持仓 ----
    local_pos: dict[str, PositionView] = {}
    for view in _normalize_positions(local_positions):
        if view.symbol in local_pos:
            # 同一 symbol 多条持仓：本系统采用净持仓模型，视为数据错误
            report.position_mismatches.append({
                "symbol": view.symbol, "field": "duplicate_local_position",
            })
            continue
        local_pos[view.symbol] = view

    broker_pos: dict[str, PositionView] = {}
    for view in _normalize_positions(broker_positions):
        if view.symbol in broker_pos:
            report.position_mismatches.append({
                "symbol": view.symbol, "field": "duplicate_broker_position",
            })
            continue
        broker_pos[view.symbol] = view

    report.missing_positions = sorted(set(local_pos) - set(broker_pos))
    report.unknown_positions = sorted(set(broker_pos) - set(local_pos))

    for symbol in sorted(set(local_pos) & set(broker_pos)):
        lp, bp = local_pos[symbol], broker_pos[symbol]
        if lp.side != bp.side:
            report.position_mismatches.append({
                "symbol": symbol, "field": "side",
                "local": lp.side, "broker": bp.side,
            })
        if not tol.equals(lp.quantity, bp.quantity):
            report.position_mismatches.append({
                "symbol": symbol, "field": "quantity",
                "local": lp.quantity, "broker": bp.quantity,
                "delta": bp.quantity - lp.quantity,
            })

    return report


def enforce(
    report: ReconcileReport,
    kill_switch: KillSwitch,
    *,
    source: str = "execution.reconcile",
) -> ReconcileReport:
    """对账不干净即触发 KillSwitch（返回原报告，便于调用方记录）。"""
    if not report.is_clean:
        kill_switch.trigger(
            reason=report.summary(), source=source,
            metadata={"codes": report.critical_codes()},
        )
    return report


# ----------------------------------------------------------------------
# 成交腿流水 → 净持仓视图聚合（#155 纯函数切片）
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class FillAggregation:
    """成交腿聚合结果：净持仓视图列表 + 无法归一的丢弃行（留痕，不静默跳过）。"""

    positions: list[PositionView]
    dropped: list[dict[str, Any]]


def aggregate_fills_to_positions(
    fills: Iterable[Any] | None,
    *,
    flat_net: float = 1e-12,
) -> FillAggregation:
    """把成交腿流水按 symbol 聚合为净持仓 `PositionView`（纯函数、无 I/O）。

    - 净额 `net = Σbuy qty − Σsell qty`；`net > flat_net` → buy，`net < -flat_net` → sell `|net|`；
      净额在 `[-flat_net, flat_net]` 内视为已平仓，不产出持仓。
    - 缺 `symbol` / 侧别无法归一 / 数量非正的行进 `dropped`（带索引与原因），不静默跳过；
      缺失行由适配器归入对账 mismatch/unknown 口径。
    - `entry_price` 不在此层推断（无 VWAP 口径），置 0.0；加权成本由需要的适配器自行计算。
    - 列名别名映射（lots/direction 等）属适配器职责；本函数只接受已归一的
      `symbol/side/quantity` 字段。
    """
    net: dict[str, float] = {}
    dropped: list[dict[str, Any]] = []

    for index, raw in enumerate(fills or []):
        symbol = _get(raw, "symbol")
        if symbol is None or str(symbol).strip() == "":
            dropped.append({"index": index, "reason": "missing_symbol", "raw": raw})
            continue
        symbol = str(symbol).strip()
        side = normalize_side(_get(raw, "side", _get(raw, "direction")))
        if side not in ("buy", "sell"):
            dropped.append({"index": index, "reason": "missing_side", "symbol": symbol, "raw": raw})
            continue
        qty_raw = _get(raw, "quantity", _get(raw, "lots", None))
        try:
            qty = abs(float(qty_raw))
        except (TypeError, ValueError):
            dropped.append({"index": index, "reason": "invalid_quantity", "symbol": symbol, "raw": raw})
            continue
        if qty <= 0.0:
            dropped.append({"index": index, "reason": "nonpositive_quantity", "symbol": symbol, "raw": raw})
            continue
        net[symbol] = net.get(symbol, 0.0) + (qty if side == "buy" else -qty)

    positions: list[PositionView] = []
    for symbol in sorted(net):
        value = net[symbol]
        if abs(value) <= flat_net:
            continue
        positions.append(PositionView(
            symbol=symbol,
            side="buy" if value > 0 else "sell",
            quantity=abs(value),
            entry_price=0.0,
        ))

    return FillAggregation(positions=positions, dropped=dropped)
