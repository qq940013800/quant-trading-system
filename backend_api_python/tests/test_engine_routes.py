"""Tests for core-engine read-only summary honest-display contract.

The market-layers and strategy-health views are read-only summaries. Without a
real live-probe or registered-strategy snapshot, the contract is:
- layer status stays ``pending`` (no "completed/online" claim);
- health overview returns zero counts and no fabricated Sharpe / win-rate /
  health-score / sizing recommendation.

No live order, position or balance path is touched.
"""


def test_market_layers_are_pending_without_completion_claim(client):
    resp = client.get("/api/p1/market-layers/summary")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    data = payload["data"]

    layers = data["layers"]
    assert len(layers) == 5
    assert data["data_kind"] == "registered"

    for layer in layers:
        assert layer["status"] == "pending"
        assert "已完成" not in layer["status"]
        assert "已上线" not in layer["status"]


def test_strategy_health_summary_is_empty_without_fabricated_strategies(client):
    resp = client.get("/api/p1/strategy-health/summary")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    data = payload["data"]

    assert data["data_kind"] == "empty"
    assert data["total"] == 0
    assert data["active"] == 0
    assert data["watch"] == 0
    assert data["suspended"] == 0
    # No fabricated average health score when there are no registered strategies.
    assert not data.get("avg_health_score")

    body = resp.get_data(as_text=True)
    for token in ["趋势跟踪策略", "均值回归策略", "突破交易策略", "85.0", "55.0", "90.0"]:
        assert token not in body, f"fabricated demo token present: {token}"
