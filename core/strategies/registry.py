# -*- coding: utf-8 -*-
"""core.strategies.registry —— 统一策略接口的运行时工厂注册器。

与 core.registry 的分工（不重复造轮子）：
- ``core.registry.strategy_registry.StrategyRegistry`` 是**元数据治理**：
  StrategyVersion 快照、状态机（draft→…→retired）、参数冻结、性能快照；
- 本模块是**运行时工厂表**：``name -> factory(**params) -> strategy instance``，
  服务于本分片定义的统一 ``Strategy`` Protocol（requires_features /
  params_schema / on_bar_close）。两者通过 strategy 命名对齐，由上层把
  工厂实例与 StrategyVersion 元数据挂接（不在此模块内耦合）。

纪律：
- 重复注册抛带上下文 ValueError（含已存在版本号）——注册即冻结，
  不支持静默覆盖（决策可审计）；
- 未注册策略抛 KeyError，detail 附已注册清单（调用方可自查）；
- 内置统一接口策略由 ``_ensure_builtins()`` 幂等登记；既有
  ``TrendBreakoutStrategy`` / ``MeanReversionStrategy``（旧构造参数式接口）
  保持原样，不强制迁入本表（鸭子兼容由 tests/test_strategies_base.py 证明）。
"""
from __future__ import annotations

_REGISTRY: dict = {}
_BUILTINS_ENSURED: bool = False


def register_strategy(name: str, factory, *, version: str = "v1") -> None:
    """登记策略工厂 ``factory(**params) -> strategy instance``。"""
    if name in _REGISTRY:
        existing = _REGISTRY[name]
        raise ValueError({
            "layer": "strategies.registry",
            "strategy": name,
            "detail": f"duplicate registration: '{name}' already registered "
                      f"(version={existing.get('version')!r}); "
                      f"override intentionally unsupported",
        })
    _REGISTRY[name] = {"factory": factory, "version": str(version)}


def get_strategy(name: str, **params):
    """按名取策略实例（params 透传给工厂构造器）。"""
    _ensure_builtins()
    if name not in _REGISTRY:
        raise KeyError({
            "layer": "strategies.registry",
            "detail": f"unknown strategy '{name}'; registered: {list_strategies()}",
        })
    return _REGISTRY[name]["factory"](**params)


def list_strategies() -> list:
    """已注册策略名（排序，稳定输出）。"""
    _ensure_builtins()
    return sorted(_REGISTRY)


def strategy_version(name: str) -> str:
    """查询注册版本（审计用）。"""
    _ensure_builtins()
    if name not in _REGISTRY:
        raise KeyError({
            "layer": "strategies.registry",
            "detail": f"unknown strategy '{name}'; registered: {list_strategies()}",
        })
    return _REGISTRY[name]["version"]


def _ensure_builtins() -> None:
    """幂等登记本分片的统一接口策略（延迟 import，避免包级循环依赖）。"""
    global _BUILTINS_ENSURED
    if _BUILTINS_ENSURED:
        return
    from .structure_break import StructureBreakStrategy
    from .supply_demand import SupplyDemandStrategy

    register_strategy("supply_demand", SupplyDemandStrategy,
                     version=SupplyDemandStrategy.strategy_version)
    register_strategy("structure_break", StructureBreakStrategy,
                     version=StructureBreakStrategy.strategy_version)
    _BUILTINS_ENSURED = True


__all__ = ["register_strategy", "get_strategy", "list_strategies",
           "strategy_version"]
