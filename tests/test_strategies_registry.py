# -*- coding: utf-8 -*-
"""tests/test_strategies_registry.py —— 工厂注册器单测。

覆盖：内置策略登记 / 按名取实例（params 透传）/ 未注册报错带上下文 /
重复注册报错带上下文 / 自定义工厂登记与版本查询。
"""
from __future__ import annotations

import pytest

from core.strategies import registry as reg
from core.strategies.structure_break import StructureBreakStrategy
from core.strategies.supply_demand import SupplyDemandStrategy


def test_builtins_registered():
    names = reg.list_strategies()
    assert "supply_demand" in names
    assert "structure_break" in names


def test_get_strategy_returns_instance_with_params():
    strat = reg.get_strategy("supply_demand", cons_bars=5, zone_valid_bars=10)
    assert isinstance(strat, SupplyDemandStrategy)
    schema = strat.params_schema()
    assert strat._params["cons_bars"] == 5
    assert schema["cons_bars"]["default"] == 8  # schema 默认值不受实例影响


def test_get_strategy_unknown_raises_with_context():
    with pytest.raises(KeyError) as exc:
        reg.get_strategy("no_such_strategy")
    ctx = exc.value.args[0]
    assert "unknown strategy" in ctx["detail"]
    assert "supply_demand" in ctx["detail"]  # 已注册清单附在上下文里


def test_duplicate_registration_raises_with_context():
    class _Dummy:
        pass

    reg.register_strategy("zz_dummy_test", _Dummy, version="t1")
    try:
        with pytest.raises(ValueError) as exc:
            reg.register_strategy("zz_dummy_test", _Dummy, version="t2")
        ctx = exc.value.args[0]
        assert "duplicate registration" in ctx["detail"]
        assert "t1" in ctx["detail"]
    finally:
        # 清理：只删本测试登记的 dummy 键，不动内置策略
        reg._REGISTRY.pop("zz_dummy_test", None)


def test_custom_factory_and_version():
    def factory(**params):
        return StructureBreakStrategy(**params)

    reg.register_strategy("zz_factory_test", factory,
                         version=StructureBreakStrategy.strategy_version)
    try:
        assert reg.strategy_version("zz_factory_test") == "structure_break-v1"
        inst = reg.get_strategy("zz_factory_test", k=5)
        assert isinstance(inst, StructureBreakStrategy)
        assert inst._params["k"] == 5
    finally:
        reg._REGISTRY.pop("zz_factory_test", None)


def test_get_strategy_rejects_unknown_params():
    with pytest.raises(ValueError) as exc:
        reg.get_strategy("supply_demand", not_a_param=1)
    assert "unknown params" in str(exc.value)
