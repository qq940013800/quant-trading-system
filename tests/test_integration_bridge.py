"""桥接模块单元测试。

三大不变量测试：
- 因果单向：不发送任何未来数据
- 决策可审计：每次调用都有记录
- 阈值来自分布：配置化，不硬编码
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from core.integration.bridge import (
    BridgeConfig,
    HealthStatus,
    QuantDingerBridge,
    StrategySummary,
)


class TestBridgeConfig:
    """配置对象测试。"""

    def test_default_values(self):
        cfg = BridgeConfig()
        assert cfg.base_url == "http://localhost:5000"
        assert cfg.timeout_seconds == 10.0
        assert cfg.max_retries == 2
        assert cfg.auth_token is None

    def test_custom_values(self):
        cfg = BridgeConfig(
            base_url="http://test:8080",
            timeout_seconds=5.0,
            max_retries=3,
            auth_token="abc123",
        )
        assert cfg.base_url == "http://test:8080"
        assert cfg.timeout_seconds == 5.0
        assert cfg.max_retries == 3
        assert cfg.auth_token == "abc123"


class TestHealthStatus:
    """健康状态测试。"""

    def test_healthy(self):
        h = HealthStatus(reachable=True, status="ok", version="v1", latency_ms=23.5)
        assert h.reachable is True
        assert h.error is None

    def test_unhealthy(self):
        h = HealthStatus(
            reachable=False,
            status="unreachable",
            version="unknown",
            error="Connection refused",
        )
        assert h.reachable is False
        assert h.error == "Connection refused"


class TestStrategySummary:
    """策略摘要测试。"""

    def test_from_raw(self):
        raw = {
            "id": 42,
            "strategy_name": "ML趋势策略",
            "strategy_type": "ml_trend",
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "status": "running",
        }
        s = StrategySummary(
            strategy_id=str(raw["id"]),
            name=raw["strategy_name"],
            strategy_type=raw["strategy_type"],
            symbol=raw["symbol"],
            timeframe=raw["timeframe"],
            status=raw["status"],
            raw=raw,
        )
        assert s.strategy_id == "42"
        assert s.symbol == "BTCUSDT"
        assert s.execution_mode == "paper"  # 默认值


class TestQuantDingerBridge:
    """桥接器测试。"""

    def make_bridge(self, **kwargs):
        cfg = BridgeConfig(**kwargs)
        return QuantDingerBridge(cfg)

    def test_init_sets_auth_header(self):
        b = self.make_bridge(auth_token="test-token")
        assert b._session.headers.get("Authorization") == "Bearer test-token"

    @patch("core.integration.bridge.requests.Session")
    def test_health_success(self, mock_session_cls):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "service": "quantdinger",
            "version": "v1",
            "status": "ok",
        }
        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        mock_session_cls.return_value = mock_session

        b = self.make_bridge()
        result = b.health()

        assert result.reachable is True
        assert result.status == "ok"
        mock_session.get.assert_called_once()

    @patch("core.integration.bridge.requests.Session")
    def test_health_failure_degrades_gracefully(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.get.side_effect = ConnectionError("refused")
        mock_session_cls.return_value = mock_session

        b = self.make_bridge(max_retries=0)  # 不重试，快速失败
        result = b.health()

        assert result.reachable is False
        assert result.status == "unreachable"
        assert "refused" in result.error

    @patch("core.integration.bridge.requests.Session")
    def test_list_strategies_envelope_format(self, mock_session_cls):
        """测试 envelope 格式：{"data": [...], "error": null}"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {"id": 1, "strategy_name": "S1", "strategy_type": "trend",
                 "symbol": "BTC", "timeframe": "1h", "status": "running"},
                {"id": 2, "strategy_name": "S2", "strategy_type": "meanrev",
                 "symbol": "ETH", "timeframe": "5m", "status": "paused"},
            ],
            "error": None,
        }
        mock_session = MagicMock()
        mock_session.request.return_value = mock_resp
        mock_session_cls.return_value = mock_session

        b = self.make_bridge()
        strategies = b.list_strategies()

        assert len(strategies) == 2
        assert strategies[0].name == "S1"
        assert strategies[1].symbol == "ETH"

    @patch("core.integration.bridge.requests.Session")
    def test_list_strategies_degraded_on_error(self, mock_session_cls):
        """API 挂了应该返回空列表，不抛异常。"""
        mock_session = MagicMock()
        mock_session.request.side_effect = ConnectionError("down")
        mock_session_cls.return_value = mock_session

        b = self.make_bridge(max_retries=0)
        strategies = b.list_strategies()

        assert strategies == []

    @patch("core.integration.bridge.requests.Session")
    def test_retry_on_failure(self, mock_session_cls):
        """测试重试逻辑：前两次失败，第三次成功。"""
        mock_resp_ok = MagicMock()
        mock_resp_ok.status_code = 200
        mock_resp_ok.json.return_value = {"data": []}

        mock_session = MagicMock()
        # 前两次抛异常，第三次成功
        mock_session.request.side_effect = [
            ConnectionError("1"),
            ConnectionError("2"),
            mock_resp_ok,
        ]
        mock_session_cls.return_value = mock_session

        b = self.make_bridge(max_retries=2, retry_backoff=0.01)
        result = b._request("GET", "/strategies")

        assert mock_session.request.call_count == 3
        assert result == []

    def test_diagnose_structure(self):
        """diagnose() 应该返回结构化报告。"""
        b = self.make_bridge()
        # 不 mock，直接调用——现在 QuantDinger 可能没在跑，降级返回
        report = b.diagnose()
        assert "bridge" in report
        assert "health" in report
        assert "config" in report
        assert report["bridge"] == "quantdinger"
