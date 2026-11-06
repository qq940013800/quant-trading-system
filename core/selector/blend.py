# -*- coding: utf-8 -*-
"""core.selector.blend —— RegimeBlendedStrategy：状态加权混合策略（决策 #8）。

把「已 fit 的 RegimeClassifier」与专家策略库接成一个满足 engine.Strategy
协议的混合策略：

  on_bar_close(history, bar):
    1. regime = classifier.predict(history, bar.ts_utc)
       —— @as_of 特征装饰器对任何 ts > bar.ts_utc 的 bar 抛 LookAheadError；
    2. regime.probs 经 expert_regime_map 累加映射成策略级目标权重并归一化；
    3. DeadbandWeightState.update(target) 得滞回平滑权重（O06：连续加权
       混合，不硬切换）；
    4. 各专家 on_bar_close 得候选方向；
    5. 净方向 = sign(Σ w_i·dir_i)，strength = |Σ w_i·dir_i|；
       strength < min_strength 或无任何候选 → 本根不出信号（低置信降频）；
    6. atr0 / entry_dist / l1_in_zone 取「权重最高且有信号」的主导专家；
    7. selection 快照落 JSONL（core.selector.audit），每根都落。

因果纪律（硬规则 1/5）：
- 除 weight_state 的平滑权重与确认计数器外，本类不保存任何跨 bar 状态；
- classifier 与全部专家只被喂 history（== bars[:i+1]）；
- 同一 blend 实例按时间顺序喂同一 bar 序列，结果可重放。
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

import pandas as pd

from ..regime import STATES
from ..regime.output import RegimeOutput
from ..strategies.signal import StrategySignal
from .audit import SelectionRecord, write_selection
from .weights import DeadbandWeightState, blend_strength

logger = logging.getLogger("core.selector")


class BlendConfigError(ValueError):
    """混合层构造契约违反，携带上下文 dict（硬规则 9）。"""

    def __init__(self, context: dict):
        self.context = context
        super().__init__(f"BlendConfigError: {context}")


class BlendedSignal(StrategySignal):
    """带 selection 审计字典的混合信号（引擎按属性鸭子消费，忽略多余字段）。

    StrategySignal 本身是非 frozen dataclass，故这里不走 dataclass 继承，
    直接在 __init__ 末尾挂 selection 属性（__post_init__ 校验照常执行）。
    """

    def __init__(self, *, selection: Optional[dict] = None, **kwargs):
        super().__init__(**kwargs)
        self.selection: dict = dict(selection or {})


def _build_expert(name: str, params: dict):
    """按名取专家实例：先查运行时工厂表，再兼容两个旧接口专家。

    旧接口 TrendBreakoutStrategy / MeanReversionStrategy 未迁入
    registry（上游分片约定保持原样），这里按名直接构造——两者与
    registry 专家实现同一 ``on_bar_close(history, bar)`` 鸭子协议。
    """
    from ..strategies.registry import get_strategy
    try:
        return get_strategy(name, **params)
    except KeyError:
        if name == "trend_breakout":
            from ..strategies.trend_breakout import TrendBreakoutStrategy
            return TrendBreakoutStrategy(**params)
        if name == "mean_reversion":
            from ..strategies.mean_reversion import MeanReversionStrategy
            return MeanReversionStrategy(**params)
        raise BlendConfigError({
            "layer": "selector.blend", "strategy": name,
            "detail": "unknown strategy (not in registry and not a legacy expert)"})


class RegimeBlendedStrategy:
    """regime 状态加权混合策略（engine Strategy 协议）。"""

    expert = "regime_blend"
    expert_tag = "regime_blend_v1"
    version = "regime_blend-v1"

    def __init__(self, *,
                 regime_classifier,
                 strategy_names: List[str],
                 expert_regime_map: Dict[str, object],
                 weight_state: DeadbandWeightState,
                 min_strength: float = 0.0,
                 expert_params: Optional[Dict[str, dict]] = None,
                 audit_path: Optional[str] = None,
                 symbol: str = "XAUUSD") -> None:
        if not strategy_names:
            raise BlendConfigError({
                "layer": "selector.blend",
                "detail": "strategy_names must be non-empty"})
        missing = [n for n in strategy_names if n not in expert_regime_map]
        if missing:
            raise BlendConfigError({
                "layer": "selector.blend", "detail":
                f"expert_regime_map missing strategies: {missing}"})
        for name, reg in expert_regime_map.items():
            keys = (reg,) if isinstance(reg, str) else tuple(reg)
            bad = [k for k in keys if k not in STATES]
            if bad:
                raise BlendConfigError({
                    "layer": "selector.blend", "strategy": name,
                    "detail": f"regime keys {bad} not in {STATES}"})
        if float(min_strength) < 0.0 or float(min_strength) > 1.0:
            raise BlendConfigError({
                "layer": "selector.blend",
                "detail": f"min_strength must be in [0,1], got {min_strength!r}"})
        self._classifier = regime_classifier
        self._names = list(strategy_names)
        self._map = {n: ((expert_regime_map[n],)
                         if isinstance(expert_regime_map[n], str)
                         else tuple(expert_regime_map[n]))
                     for n in self._names}
        self._weight_state = weight_state
        self.min_strength = float(min_strength)
        self.audit_path = audit_path
        self.symbol = str(symbol)
        params = expert_params or {}
        self._experts = {n: _build_expert(n, dict(params.get(n, {})))
                         for n in self._names}

    # ------------------------------------------------------------------ #
    # 目标权重：regime.probs → 策略级权重（累加后归一化）
    # ------------------------------------------------------------------ #
    def _target_weights(self, probs: Dict[str, float]) -> Dict[str, float]:
        raw = {n: float(sum(probs[r] for r in self._map[n]))
               for n in self._names}
        total = sum(raw.values())
        if total <= 0.0:
            # 中性兜底：均匀（灰区不偏袒任何专家）
            return {n: 1.0 / len(self._names) for n in self._names}
        return {n: v / total for n, v in raw.items()}

    # ------------------------------------------------------------------ #
    # engine.Strategy 协议
    # ------------------------------------------------------------------ #
    def on_bar_close(self, history: list, bar):
        # 因果守卫：history 必须以当前已收盘 bar 结尾（混入未来 bar 显式失败）
        if not history or history[-1].ts_utc != bar.ts_utc:
            raise ValueError({
                "layer": "selector.blend",
                "ts_utc": str(bar.ts_utc),
                "history_last_ts_utc": str(history[-1].ts_utc) if history else None,
                "detail": "history must end at the current closed bar "
                          "(no future bars)",
            })
        # 1. regime（@as_of 装饰器对未来 bar 抛 LookAheadError）
        regime: RegimeOutput = self._classifier.predict(history, bar.ts_utc)

        # 2. 策略级目标权重 + 3. 滞回平滑
        target = self._target_weights(regime.probs)
        smooth = self._weight_state.update(target)

        # 4. 各专家候选信号
        candidates: Dict[str, object] = {}
        summaries: Dict[str, dict] = {}
        for n in self._names:
            sig = self._experts[n].on_bar_close(history, bar)
            candidates[n] = sig
            if sig is None:
                summaries[n] = {"has_signal": False, "direction": None,
                                "atr0": None, "entry_dist": None}
            else:
                summaries[n] = {"has_signal": True,
                                "direction": int(sig.direction),
                                "atr0": float(sig.atr0),
                                "entry_dist": float(sig.entry_dist)}

        # 5. 合成方向与强度
        directions = {n: int(candidates[n].direction)
                      for n in self._names if candidates[n] is not None}
        strength = blend_strength(directions, smooth)
        net = sum(smooth[n] * directions[n] for n in directions)

        strategy_versions = {
            n: str(getattr(self._experts[n], "strategy_version",
                           f"{n}-legacy"))
            for n in self._names}

        selection = {
            "state": regime.state,
            "regime_probs": dict(regime.probs),
            "regime_version": regime.version,
            "threshold_dataset": regime.threshold_dataset,
            "target_weights": target,
            "strategy_weights": dict(smooth),
            "expert_signals": summaries,
            "blend_strength": strength,
            "strategy_versions": strategy_versions,
            "degraded": regime.degraded,
            "weight_state": {
                "alpha": self._weight_state.alpha,
                "deadband": self._weight_state.deadband,
                "confirm_n": self._weight_state.confirm_n,
                "applied_updates": self._weight_state.applied_updates,
            },
        }

        signal = None
        if directions and strength >= self.min_strength and net != 0.0:
            # 6. 主导专家：权重最高且有信号者
            dom_name = max(directions, key=lambda n: smooth[n])
            dom = candidates[dom_name]
            direction = 1 if net > 0 else -1
            # regime_weights 回投到 regime 三键（引擎/审计层消费口径）
            regime_level = {s: 0.0 for s in STATES}
            for n, w in smooth.items():
                for r in self._map[n]:
                    regime_level[r] += w
            signal = BlendedSignal(
                signal_id=f"{self.symbol}_{bar.ts_utc.isoformat()}_"
                          f"regime_blend_{direction}",
                bar_ts_utc=bar.ts_utc,
                expert=self.expert_tag,
                direction=direction,
                price_ref=float(bar.close),
                atr0=float(dom.atr0),
                entry_dist=float(dom.entry_dist),
                l1_in_zone=bool(dom.l1_in_zone),
                regime_weights=dict(regime_level),
                meta_p=None,
                strategy_version=self.version,
                selection=selection,
            )

        # 7. 审计：每根评估都落快照（含低置信未出信号的 bar）
        if self.audit_path:
            rec = SelectionRecord(
                ts_utc=bar.ts_utc.isoformat(),
                state=regime.state,
                regime_probs=dict(regime.probs),
                strategy_weights=dict(smooth),
                expert_signals=summaries,
                blend_strength=float(strength),
                strategy_versions=strategy_versions,
                degraded=bool(regime.degraded),
                signal_id=(signal.signal_id if signal is not None else None),
            )
            write_selection(self.audit_path, rec)
        return signal


__all__ = ["RegimeBlendedStrategy", "BlendedSignal", "BlendConfigError"]
