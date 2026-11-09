# -*- coding: utf-8 -*-
"""tests.test_strategies.test_registry —— 策略工厂注册器名称/版本/可调用守卫。"""
from __future__ import annotations

import pytest

from core.strategies.registry import (
    get_strategy,
    list_strategies,
    register_strategy,
    strategy_version,
)


def _fake_factory(**params):
    return {"params": params}


class TestRegisterGuards:
    @pytest.mark.parametrize("bad", ["", "  ", None, 123, object()])
    def test_name_must_be_nonempty_str(self, bad):
        with pytest.raises(ValueError):
            register_strategy(bad, _fake_factory, version="v1")

    @pytest.mark.parametrize("bad", [None, 123, {"a": 1}, "not-callable"])
    def test_factory_must_be_callable(self, bad):
        with pytest.raises(ValueError):
            register_strategy("guard_noncallable", bad, version="v1")

    @pytest.mark.parametrize("bad", ["", "  ", None])
    def test_version_must_be_nonempty_str(self, bad):
        with pytest.raises(ValueError):
            register_strategy("guard_bad_version", _fake_factory, version=bad)

    def test_valid_register_and_resolve(self):
        register_strategy("guard_fake", _fake_factory, version="v9.9")
        try:
            assert "guard_fake" in list_strategies()
            assert strategy_version("guard_fake") == "v9.9"
            inst = get_strategy("guard_fake", k=1)
            assert inst == {"params": {"k": 1}}
        finally:
            from core.strategies import registry as _reg
            _reg._REGISTRY.pop("guard_fake", None)

    def test_duplicate_registration_rejected(self):
        register_strategy("guard_dup", _fake_factory, version="v1")
        try:
            with pytest.raises(ValueError):
                register_strategy("guard_dup", _fake_factory, version="v2")
        finally:
            from core.strategies import registry as _reg
            _reg._REGISTRY.pop("guard_dup", None)

    def test_unknown_strategy_raises_keyerror(self):
        with pytest.raises(KeyError):
            get_strategy("guard_no_such_strategy")
        with pytest.raises(KeyError):
            strategy_version("guard_no_such_strategy")
