# -*- coding: utf-8 -*-
"""tests.test_errors —— 统一异常体系测试。"""
from __future__ import annotations

import pytest

from core.errors import (
    QuantTraderError,
    DataLayerError,
    ValidationError,
    LookAheadError,
    FeatureLayerError,
    AsOfContractError,
    ModelLayerError,
    PurgedCVError,
    RiskLayerError,
    StopWideningError,
    AuditLayerError,
    SignalLikeError,
    ReplayMismatch,
    ok,
    err,
)


class TestErrorHierarchy:
    def test_base_error(self):
        e = QuantTraderError("something wrong")
        assert "core" in str(e)
        assert "something wrong" in str(e)

    def test_layer_override(self):
        e = QuantTraderError("detail here", layer="custom.layer")
        assert e.layer == "custom.layer"
        assert "custom.layer" in str(e)

    def test_extra_fields(self):
        e = QuantTraderError("bad input", symbol="XAUUSD", price=2300.5)
        assert "symbol='XAUUSD'" in str(e)
        assert "price=2300.5" in str(e)

    def test_data_layer_error(self):
        e = DataLayerError("missing column")
        assert e.layer == "data"
        assert isinstance(e, QuantTraderError)

    def test_validation_error(self):
        e = ValidationError("price must be positive")
        assert e.layer == "data.validation"
        assert isinstance(e, DataLayerError)

    def test_lookahead_error(self):
        e = LookAheadError("future data leaked")
        assert e.layer == "data.lookahead"
        assert isinstance(e, DataLayerError)

    def test_feature_layer_error(self):
        e = FeatureLayerError("bad feature")
        assert e.layer == "features"
        assert isinstance(e, QuantTraderError)

    def test_as_of_contract_error(self):
        e = AsOfContractError("as_of must be tz-aware")
        assert e.layer == "features.as_of"
        assert isinstance(e, FeatureLayerError)

    def test_model_layer_error(self):
        e = ModelLayerError("model not fitted")
        assert e.layer == "models"
        assert isinstance(e, QuantTraderError)

    def test_purged_cv_error(self):
        e = PurgedCVError("n_splits must be >= 2")
        assert e.layer == "models.cv"
        assert isinstance(e, ModelLayerError)

    def test_risk_layer_error(self):
        e = RiskLayerError("risk limit hit")
        assert e.layer == "risk"
        assert isinstance(e, QuantTraderError)

    def test_stop_widening_error(self):
        e = StopWideningError("stop moved wrong", symbol="XAUUSD")
        assert e.layer == "risk.stops"
        assert isinstance(e, RiskLayerError)

    def test_audit_layer_error(self):
        e = AuditLayerError("audit write failed")
        assert e.layer == "audit"
        assert isinstance(e, QuantTraderError)

    def test_signal_like_error(self):
        e = SignalLikeError("expected Decision, got dict")
        assert e.layer == "audit.signal"
        assert isinstance(e, AuditLayerError)

    def test_replay_mismatch(self):
        e = ReplayMismatch("recorded 100.5, recomputed 100.6")
        assert e.layer == "audit.replay"
        assert isinstance(e, AuditLayerError)


class TestOkErr:
    def test_ok_with_value(self):
        success, result = ok(42)
        assert success is True
        assert result == 42

    def test_ok_none(self):
        success, result = ok()
        assert success is True
        assert result is None

    def test_err(self):
        success, message = err("something broke", code=500)
        assert success is False
        assert message == "something broke"

    def test_try_catch_base(self):
        """所有自定义异常都应该能通过基类捕获。"""
        try:
            raise LookAheadError("leak detected")
        except QuantTraderError as e:
            assert "lookahead" in str(e).lower()
        else:
            pytest.fail("should have raised")
