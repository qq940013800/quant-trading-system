"""OKX transient-retry classification and throttling/signature error mapping.

Covers:
- pure helpers ``is_retryable_transient`` / ``retry_delay_sec``;
- read-only GET transient-failure backoff (network errors, HTTP 5xx/429);
- adapter error-code mapping for 50011/50061 (throttle), 50113 (signature/timestamp),
  and the pre-existing 51008 (insufficient margin) regression.
"""

from __future__ import annotations

import requests
import pytest

from app.services.live_trading.base import (
    LiveTradingError,
    is_retryable_transient,
    retry_delay_sec,
)
from app.services.live_trading.okx import OkxClient


def _client() -> OkxClient:
    return OkxClient(api_key="k", secret_key="s", passphrase="p")


# --- pure retry helpers ---


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_retryable_transient_http_status(status):
    assert is_retryable_transient(status) is True


@pytest.mark.parametrize("status", [400, 401, 403, 404, 451])
def test_non_retryable_client_error_status(status):
    assert is_retryable_transient(status) is False


def test_retryable_throttle_exchange_code():
    assert is_retryable_transient(200, "50011") is True
    assert is_retryable_transient(200, "50061") is True
    assert is_retryable_transient(200, "51008") is False


def test_retry_delay_exponential_and_capped():
    assert retry_delay_sec(0) == pytest.approx(0.4)
    assert retry_delay_sec(1) == pytest.approx(0.8)
    assert retry_delay_sec(2) == pytest.approx(1.6)
    assert retry_delay_sec(6) == pytest.approx(1.6)  # capped


# --- readonly GET retry wrapper ---


def test_readonly_get_retries_transient_network_then_succeeds(monkeypatch):
    monkeypatch.setattr("app.services.live_trading.okx.time.sleep", lambda *_: None)
    c = _client()
    calls = {"n": 0}

    def fake_request(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise requests.exceptions.ConnectionError("boom")
        return 200, {"code": "0", "data": []}, ""

    monkeypatch.setattr(c, "_request", fake_request)
    code, data, _ = c._request_readonly_with_retry("GET", "/api/v5/public/time")
    assert code == 200
    assert data == {"code": "0", "data": []}
    assert calls["n"] == 2


def test_readonly_get_retries_http_5xx_then_succeeds(monkeypatch):
    monkeypatch.setattr("app.services.live_trading.okx.time.sleep", lambda *_: None)
    c = _client()
    calls = {"n": 0}

    def fake_request(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            return 503, {"code": "50011", "data": []}, "busy"
        return 200, {"code": "0", "data": []}, ""

    monkeypatch.setattr(c, "_request", fake_request)
    code, _, _ = c._request_readonly_with_retry("GET", "/api/v5/account/balance")
    assert code == 200
    assert calls["n"] == 3


def test_readonly_get_raises_after_max_retries(monkeypatch):
    monkeypatch.setattr("app.services.live_trading.okx.time.sleep", lambda *_: None)
    c = _client()

    def fake_request(*args, **kwargs):
        raise requests.exceptions.Timeout("slow")

    monkeypatch.setattr(c, "_request", fake_request)
    with pytest.raises(LiveTradingError):
        c._request_readonly_with_retry("GET", "/api/v5/account/balance", max_retries=2)


# --- adapter error-code mapping via _signed_request ---


def test_signed_request_maps_throttle_code(monkeypatch):
    c = _client()

    def fake_readonly(method, path, **kwargs):
        return 200, {"code": "50011", "msg": "Too many requests", "data": []}, ""

    monkeypatch.setattr(c, "_request_readonly_with_retry", fake_readonly)
    with pytest.raises(LiveTradingError) as ei:
        c._signed_request("GET", "/api/v5/account/balance")
    assert "rate-limit" in str(ei.value).lower()


def test_signed_request_maps_subaccount_throttle_code(monkeypatch):
    c = _client()

    def fake_readonly(method, path, **kwargs):
        return 200, {"code": "50061", "msg": "Sub-account limit", "data": []}, ""

    monkeypatch.setattr(c, "_request_readonly_with_retry", fake_readonly)
    with pytest.raises(LiveTradingError) as ei:
        c._signed_request("GET", "/api/v5/account/config")
    assert "rate-limit" in str(ei.value).lower()


def test_signed_request_maps_signature_code(monkeypatch):
    c = _client()

    def fake_readonly(method, path, **kwargs):
        return 200, {"code": "50113", "msg": "Invalid sign", "data": []}, ""

    monkeypatch.setattr(c, "_request_readonly_with_retry", fake_readonly)
    with pytest.raises(LiveTradingError) as ei:
        c._signed_request("GET", "/api/v5/account/config")
    assert "signature" in str(ei.value).lower()


def test_signed_request_keeps_insufficient_margin_mapping(monkeypatch):
    c = _client()

    def fake_readonly(method, path, **kwargs):
        return 200, {"code": "1", "data": [{"sCode": "51008", "sMsg": "Insufficient margin"}]}, ""

    monkeypatch.setattr(c, "_request_readonly_with_retry", fake_readonly)
    with pytest.raises(LiveTradingError) as ei:
        c._signed_request("GET", "/api/v5/account/balance")
    assert "margin" in str(ei.value).lower()
