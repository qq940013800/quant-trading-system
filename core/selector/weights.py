# -*- coding: utf-8 -*-
"""core.selector.weights —— 带滞回的状态加权混合（决策 #8 / O06）。

研究依据（docs/trading/STRATEGY_AUTO_MATCHING_DEEP_DIVE.md 第 2.3/阶段 3 节）：
- O06（已证实机制）：硬切换在阈值附近反复挨打（threshold whipsaw）；
  推荐「状态隶属概率 → 连续加权混合 + 双向 deadband + 连续 N bar 确认」，
  权重用 EMA 慢更新；
- 决策 #8：regime 输出连续概率向量，deadband 加权混合而非硬切换；
- 决策 #9 / O07：所有平滑参数（alpha / deadband / confirm_n）全部由调用方
  从 CLEAN 分布校准后经构造参数冻结传入——本模块内不出现任何按绩效网格
  搜索出来的字面量。

不变量：
- 任何一步 ``update`` 之后返回的权重向量和恒为 1（归一化投影兜底）；
- deadband 内的状态「不向目标靠拢」（双向滞回），进入更新只在连续
  ``confirm_n`` 根已收盘 bar 同侧偏离时触发；
- 因果性：本状态机只接收 ``on_bar_close`` 喂进来的 target_probs，本身
  不读取行情、不保存跨 bar 的其它状态（权重向量 + 确认计数器两个字段）。
"""
from __future__ import annotations

import math
from typing import Dict, Optional, Sequence


class WeightStateError(ValueError):
    """权重状态机构造/更新契约违反，携带上下文 dict（硬规则 9）。"""

    def __init__(self, context: dict):
        self.context = context
        super().__init__(f"WeightStateError: {context}")


def _finite_num(name: str, val) -> float:
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise WeightStateError({
            "layer": "selector.weights",
            "detail": f"{name} must be a number: {val!r}"})
    f = float(val)
    if not math.isfinite(f):
        raise WeightStateError({
            "layer": "selector.weights",
            "detail": f"{name} must be finite: {val!r}"})
    return f


class DeadbandWeightState:
    """一阶 EMA 平滑 + 双向 deadband + 连续 N bar 确认的权重状态机。

    Parameters
    ----------
    keys :
        权重键集合（如 regime 三键或策略名列表）；target_probs 必须与之一致。
    alpha :
        EMA 步长 ∈ (0,1]。alpha=1 表示无平滑（目标即权重）；
        生产路径由 CLEAN 分布派生半衰期换算后冻结传入。
    deadband :
        双向滞回带宽 ≥ 0。某状态 |target - 当前| <= deadband 时该状态本根
        不向目标靠拢（灰区维持现状）；严格 > deadband 才进入确认计数。
    confirm_n :
        连续确认根数 ≥ 1。目标必须连续 confirm_n 根已收盘 bar 处于
        「超出 deadband 且同侧」才真正触发 EMA 更新；期间任一根落回
        deadband 或反向，计数清零。
    initial :
        初始权重（默认均匀）。reset() 回到该快照。
    """

    def __init__(self, keys: Sequence[str], *,
                 alpha: float = 0.3,
                 deadband: float = 0.05,
                 confirm_n: int = 1,
                 initial: Optional[Dict[str, float]] = None) -> None:
        keys = tuple(keys)
        if not keys or len(set(keys)) != len(keys):
            raise WeightStateError({
                "layer": "selector.weights",
                "detail": f"keys must be non-empty and unique, got {keys!r}"})
        if not 0.0 < float(alpha) <= 1.0:
            raise WeightStateError({
                "layer": "selector.weights", "detail":
                f"alpha must be in (0,1], got {alpha!r}"})
        if float(deadband) < 0.0:
            raise WeightStateError({
                "layer": "selector.weights", "detail":
                f"deadband must be >= 0, got {deadband!r}"})
        if int(confirm_n) < 1:
            raise WeightStateError({
                "layer": "selector.weights", "detail":
                f"confirm_n must be >= 1, got {confirm_n!r}"})
        self._keys = keys
        self.alpha = float(alpha)
        self.deadband = float(deadband)
        self.confirm_n = int(confirm_n)
        if initial is None:
            self._initial = {k: 1.0 / len(keys) for k in keys}
        else:
            self._initial = dict(initial)
            self._validate_target(self._initial)
        # 运行时状态（仅这两个字段——因果可重放的最小账本）
        self._w: Dict[str, float] = dict(self._initial)
        self._confirm: Dict[str, tuple[int, int]] = {
            k: (0, 0) for k in keys}   # (方向符号, 连续计数)
        self.applied_updates: int = 0   # 累计 per-key EMA 应用次数（审计/测试）

    # ------------------------------------------------------------------ #
    # 内部
    # ------------------------------------------------------------------ #
    def _validate_target(self, target: Dict[str, float]) -> None:
        if set(target.keys()) != set(self._keys):
            raise WeightStateError({
                "layer": "selector.weights",
                "detail": f"target keys {sorted(target)} != state keys "
                           f"{sorted(self._keys)}"})
        if any(v < 0.0 for v in target.values()):
            raise WeightStateError({
                "layer": "selector.weights",
                "detail": f"target weights must be >= 0: {target}"})
        if any(not math.isfinite(float(v)) for v in target.values()):
            raise WeightStateError({
                "layer": "selector.weights",
                "detail": f"target weights must be finite: {target}"})
        total = float(sum(target.values()))
        if abs(total - 1.0) > 1e-6:
            raise WeightStateError({
                "layer": "selector.weights",
                "detail": f"target weights must sum to 1, got {total!r}"})

    # ------------------------------------------------------------------ #
    # 公开接口
    # ------------------------------------------------------------------ #
    def reset(self) -> None:
        """回到初始权重快照、清零确认计数器（新回测段/新折调用）。"""
        self._w = dict(self._initial)
        self._confirm = {k: (0, 0) for k in self._keys}

    def weights(self) -> Dict[str, float]:
        """当前平滑权重的浅拷贝（和恒为 1）。"""
        return dict(self._w)

    def update(self, target_probs: Dict[str, float]) -> Dict[str, float]:
        """喂入本根已收盘 bar 的目标权重，返回当前平滑权重（浅拷贝）。

        逐键逻辑：
        1. |delta| <= deadband → 该键本根冻结，确认计数清零；
        2. |delta| > deadband 且与上一根同侧 → 连续计数 +1；反向或刚出带
           则计数重置为 1；
        3. 连续计数 >= confirm_n → EMA 应用：w <- w + alpha·delta；
        4. 全部键处理完后归一化投影（保证和恒为 1）。
        """
        self._validate_target(target_probs)
        for k in self._keys:
            w = float(self._w[k])
            delta = float(target_probs[k]) - w
            if abs(delta) <= self.deadband:
                self._confirm[k] = (0, 0)
                continue
            d = 1 if delta > 0 else -1
            prev_d, prev_n = self._confirm[k]
            if prev_d == d:
                n = prev_n + 1
            else:
                n = 1
            self._confirm[k] = (d, n)
            if n >= self.confirm_n:
                self._w[k] = w + self.alpha * delta
                self.applied_updates += 1
        # 归一化投影：冻结键被其余键的更新轻微重标定，和恒为 1
        total = float(sum(self._w.values()))
        if total <= 0.0:
            raise WeightStateError({
                "layer": "selector.weights",
                "detail": f"weight state degenerate (sum={total}); "
                          "targets must stay non-negative"})
        for k in self._keys:
            self._w[k] /= total
        return self.weights()


# --------------------------------------------------------------------------- #
# 参数收缩（James-Stein 思路，决策 #9 / O07）
# --------------------------------------------------------------------------- #
def shrink_params(global_defaults: Dict[str, float],
                  local_estimates: Dict[str, float],
                  lam: float) -> Dict[str, float]:
    """参数向全局默认收缩：out = lam·global + (1-lam)·local。

    - lam=1 → 全用全局默认参数；
    - lam=0 → 全用局部估计参数；
    - 中间线性收缩。

    **生产路径固定 lam=1**：禁止按 regime 绩效网格搜索局部参数
    （O07：DSR 已证同一数据上多次试验期望最大 Sharpe 严格为正；
    决策 #9：阈值来自分布而非绩效）。lam<1 仅在 CLEAN 集参数稳定性
    分析（阶段 4）中离线使用，线上默认不开放。
    """
    if not isinstance(global_defaults, dict) or not isinstance(local_estimates, dict):
        raise WeightStateError({
            "layer": "selector.weights",
            "detail": "global_defaults/local_estimates must be dicts"})
    lam = _finite_num("lam", lam)
    if not 0.0 <= lam <= 1.0:
        raise WeightStateError({
            "layer": "selector.weights",
            "detail": f"lam must be in [0,1], got {lam!r}"})
    if set(global_defaults.keys()) != set(local_estimates.keys()):
        raise WeightStateError({
            "layer": "selector.weights",
            "detail": f"key mismatch: global={sorted(global_defaults)} "
                      f"local={sorted(local_estimates)}"})
    for k, v in global_defaults.items():
        _finite_num(f"global_defaults[{k!r}]", v)
    for k, v in local_estimates.items():
        _finite_num(f"local_estimates[{k!r}]", v)
    return {k: lam * float(global_defaults[k])
            + (1.0 - lam) * float(local_estimates[k])
            for k in global_defaults}


# --------------------------------------------------------------------------- #
# 合成强度（低置信无信号判断）
# --------------------------------------------------------------------------- #
def blend_strength(directions: Dict[str, int],
                   weights: Dict[str, float]) -> float:
    """加权合成强度 ``|Σ w_i · dir_i|``（仅对出信号的专家计方向）。

    directions : {策略名: ±1}（只有产生候选信号的专家进入该 dict）；
    weights    : 当前平滑权重（缺省键按 0 计）。

    强度低于 min_strength 时混合层不出手（专家方向相互抵消 = 低置信）。
    """
    net = 0.0
    for name, d in directions.items():
        if d not in (-1, 1):
            raise WeightStateError({
                "layer": "selector.weights",
                "detail": f"direction must be -1 or 1: {name!r}={d!r}"})
        w = float(weights.get(name, 0.0))
        if not math.isfinite(w):
            raise WeightStateError({
                "layer": "selector.weights",
                "detail": f"weight must be finite: {name!r}={w!r}"})
        net += w * int(d)
    return abs(net)


__all__ = ["DeadbandWeightState", "WeightStateError",
           "shrink_params", "blend_strength"]
