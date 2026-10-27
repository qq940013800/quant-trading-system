# -*- coding: utf-8 -*-
"""core.registry.strategy_router —— 策略权重路由（regime → 策略权重）。

与已有模块的边界：
- ``core.registry.strategy_registry.StrategyRegistry``：策略**版本生命周期**管理
  （draft→backtest→paper→live→retired 状态机），不关心市场状态。
- ``core.registry.strategy_matcher.StrategyMatcher``：根据市场状态给策略**打分排序**，
  输出排名（rank），不输出归一化资金权重。
- 本模块（``strategy_router``）：输入离散市场状态（regime），输出**归一化策略权重**，
  供上层组合分配/门控使用。权重表是路由配置（静态声明），**不是**绩效网格搜索产物。

第一性原理：
1. 没有万能策略——不同 regime 下不同策略的期望夏普不同
2. 权重是配置，来自策略画像（best/worst regime），不来自 PnL 拟合
3. 权重必须归一化（和为 1），否则组合分配会泄漏
4. 未注册策略绝不出现在路由结果里（白名单）
5. 因果单向：本模块只读 regime 标签，不回写策略定义
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


# 支持的市场状态（与 core.registry.strategy_matcher.MarketRegime 对齐）
# trend=趋势市, range=震荡市, volatile=高波动, quiet=低波平静
SUPPORTED_REGIMES: tuple[str, ...] = ("trend", "range", "volatile", "quiet")

# 止损类型枚举（字符串，避免硬编码到策略逻辑里）
STOP_TYPES: tuple[str, ...] = (
    "atr_initial",       # 初始 ATR 止损
    "atr_trailing",      # ATR 跟踪止损（只向盈利方向移动）
    "bollinger_band",   # 布林带边缘止损
    "fixed_pct",         # 固定百分比
)


@dataclass(frozen=True)
class StrategyDescriptor:
    """策略元数据（路由用快照）。

    字段对应任务要求：
    - name / version：唯一标识
    - regime_profile：dict[regime -> base_weight]，该策略在各 regime 下的基础权重
    - symbols：适用品种白名单（空列表 = 不限品种）
    - params：冻结的参数字典（来自 StrategyConfig 或 CLI，不来自绩效网格）
    - stop_loss_type：止损类型（STOP_TYPES 之一）
    - implementation_ref：实现位置（"module:Class" 字符串，用于审计追溯）
    - description：人类可读描述
    """
    name: str
    version: str
    regime_profile: dict[str, float]
    symbols: tuple[str, ...] = ()
    params: dict[str, Any] = field(default_factory=dict)
    stop_loss_type: str = "atr_initial"
    implementation_ref: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        # 校验 regime 键合法
        for k in self.regime_profile:
            if k not in SUPPORTED_REGIMES:
                raise ValueError(
                    f"未知 regime '{k}'（策略 {self.name}）；"
                    f"支持的 regime: {SUPPORTED_REGIMES}"
                )
        # 校验止损类型
        if self.stop_loss_type not in STOP_TYPES:
            raise ValueError(
                f"未知止损类型 '{self.stop_loss_type}'（策略 {self.name}）；"
                f"支持: {STOP_TYPES}"
            )
        # 权重非负
        for k, v in self.regime_profile.items():
            if v < 0:
                raise ValueError(
                    f"regime_profile[{k}] 权重不能为负（策略 {self.name}）"
                )

    def base_weight(self, regime: str) -> float:
        """返回该策略在指定 regime 下的基础权重（未归一化）。"""
        return float(self.regime_profile.get(regime, 0.0))


class StrategyWeightRouter:
    """策略权重路由器。

    职责：
    1. 注册策略描述符（白名单）
    2. 给定 regime，输出归一化权重 dict[str, float]（和为 1）
    3. 未注册策略不出现在结果里

    用法：
        router = StrategyWeightRouter()
        router.register(descriptor)
        weights = router.route("trend")
        # {"demo_breakout": 0.45, "ml_trend_meta": 0.45, "demo_mean_reversion": 0.10}
    """

    def __init__(self) -> None:
        self._descriptors: dict[str, StrategyDescriptor] = {}

    def register(self, descriptor: StrategyDescriptor) -> None:
        """注册一个策略描述符。name 必须唯一。"""
        if descriptor.name in self._descriptors:
            raise ValueError(f"策略已注册: {descriptor.name}")
        self._descriptors[descriptor.name] = descriptor

    def unregister(self, name: str) -> None:
        """移除注册（用于测试/下线）。"""
        self._descriptors.pop(name, None)

    def list_registered(self) -> list[str]:
        """列出所有已注册策略名。"""
        return sorted(self._descriptors.keys())

    def get(self, name: str) -> StrategyDescriptor | None:
        return self._descriptors.get(name)

    def route(self, regime: str) -> dict[str, float]:
        """输入 regime，输出归一化权重。

        规则：
        1. regime 必须在 SUPPORTED_REGIMES 内
        2. 取每个已注册策略的 base_weight(regime)
        3. 若总和为 0（该 regime 下所有策略基础权重都是 0），抛错
           —— 绝不静默返回全 0 权重
        4. 归一化：weight_i = base_i / total
        5. 只返回 base_weight > 0 的策略（零权重策略不出现，避免组合分配歧义）
        """
        if regime not in SUPPORTED_REGIMES:
            raise ValueError(
                f"未知 regime '{regime}'；支持: {SUPPORTED_REGIMES}"
            )

        raw: dict[str, float] = {}
        for name, desc in self._descriptors.items():
            w = desc.base_weight(regime)
            if w > 0:
                raw[name] = w

        total = sum(raw.values())
        if total <= 0:
            raise ValueError(
                f"regime='{regime}' 下所有已注册策略基础权重均为 0；"
                f"请检查策略画像或补充策略"
            )

        return {name: w / total for name, w in raw.items()}

    def route_all_regimes(self) -> dict[str, dict[str, float]]:
        """返回所有 regime 的路由表（用于审计/文档）。"""
        return {r: self.route(r) for r in SUPPORTED_REGIMES}


# ------------------------------------------------------------------
# 内置演示策略注册（3 个）
# ------------------------------------------------------------------
def build_demo_router() -> StrategyWeightRouter:
    """构造内置演示路由：注册 3 个演示策略并返回路由器。

    3 个策略来源（诚实标注）：
    1. demo_breakout —— 真实实现：core/backtest/engine.py::DemoBreakoutStrategy
    2. ml_trend_meta —— 真实实现：core/models/ml_trend_strategy.py::MLTrendStrategy
    3. demo_mean_reversion —— 仅在 gatekeeper 模拟数据中引用（type=mean_reversion），
       尚未有完整策略类；此处按其 regime 画像登记为路由占位，**不代表已可交易**。
    """
    router = StrategyWeightRouter()

    # 1) 唐奇安突破趋势策略
    #    趋势市权重高，震荡市权重低；ATR 初始止损
    router.register(StrategyDescriptor(
        name="demo_breakout",
        version="v1.0.0",
        regime_profile={
            "trend": 0.45,
            "range": 0.10,
            "volatile": 0.25,
            "quiet": 0.15,
        },
        symbols=("XAUUSD", "BTCUSD"),
        params={
            "lookback": 20,
            "atr_n": 14,
            "entry_dist_mult": 2.0,
        },
        stop_loss_type="atr_initial",
        implementation_ref="core.backtest.engine:DemoBreakoutStrategy",
        description="唐奇安通道突破趋势策略（演示用，pipeline 自检）",
    ))

    # 2) ML 增强 meta-label 趋势策略
    #    趋势市+高波市权重高（ML 过滤在波动中更有价值），震荡市低
    router.register(StrategyDescriptor(
        name="ml_trend_meta",
        version="ml-trend-meta-label-v1",
        regime_profile={
            "trend": 0.45,
            "range": 0.20,
            "volatile": 0.55,
            "quiet": 0.35,
        },
        symbols=("XAUUSD",),
        params={
            "entry_period": 20,
            "exit_period": 10,
            "atr_period": 14,
            "meta_C": 1.0,
            "meta_threshold": 0.55,
            "risk_per_trade": 0.01,
            "atr_stop_mult": 2.0,
            "atr_trail_mult": 3.0,
        },
        stop_loss_type="atr_trailing",
        implementation_ref="core.models.ml_trend_strategy:MLTrendStrategy",
        description="海龟突破初级信号 + 逻辑回归 meta-label 过滤（López de Prado 架构）",
    ))

    # 3) 均值回归策略（路由占位：尚无完整策略类实现）
    #    震荡市/低波市权重高，趋势市低
    router.register(StrategyDescriptor(
        name="demo_mean_reversion",
        version="v0.1.0",
        regime_profile={
            "trend": 0.10,
            "range": 0.70,
            "volatile": 0.20,
            "quiet": 0.50,
        },
        symbols=("EURUSD",),
        params={
            "rsi_period": 14,
            "bollinger_period": 20,
        },
        stop_loss_type="bollinger_band",
        implementation_ref="(未实现；gatekeeper 模拟数据 type=mean_reversion)",
        description="均值回归（RSI/布林带反向）—— 路由占位，尚未有可交易实现",
    ))

    return router


__all__ = [
    "SUPPORTED_REGIMES",
    "STOP_TYPES",
    "StrategyDescriptor",
    "StrategyWeightRouter",
    "build_demo_router",
]
