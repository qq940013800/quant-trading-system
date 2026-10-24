"""QuantDinger API 桥接模块。

第一性原理：验证层和执行层之间需要一座桥——
不是把两层混在一起，是让它们能对话。

核心职责：
1. 封装 QuantDinger API 的 HTTP 调用
2. 统一数据格式，让我们的验证模块能消费
3. 处理认证、重试、错误降级
4. 提供健康检查

三大不变量（继承自项目）：
- 因果单向：只取 available_at <= bar.close 的数据
- 决策可审计：每次 API 调用都记录
- 阈值来自分布：不硬编码任何业务参数
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urljoin

import requests

logger = logging.getLogger(__name__)


@dataclass
class BridgeConfig:
    """桥接配置。所有阈值来自配置，不硬编码。"""
    base_url: str = "http://localhost:5000"
    api_prefix: str = "/api/agent/v1"
    timeout_seconds: float = 10.0
    max_retries: int = 2
    retry_backoff: float = 0.5
    auth_token: Optional[str] = None
    request_log_enabled: bool = True


@dataclass
class HealthStatus:
    """健康状态。"""
    reachable: bool
    status: str
    version: str
    timestamp: Optional[datetime] = None
    latency_ms: float = 0.0
    error: Optional[str] = None


@dataclass
class StrategySummary:
    """策略摘要——从 QuantDinger 数据投影成我们的格式。"""
    strategy_id: str
    name: str
    strategy_type: str
    symbol: str
    timeframe: str
    status: str
    market_category: str = ""
    execution_mode: str = "paper"
    initial_capital: float = 0.0
    leverage: float = 1.0
    raw: dict = field(default_factory=dict)


class QuantDingerBridge:
    """QuantDinger API 桥接器。

    设计原则：
    - 只读封装：默认只读，写操作需要显式开启
    - 降级容错：API 挂了不能把我们的验证层也搞挂
    - 可观测：每次调用都有日志和耗时
    """

    def __init__(self, config: Optional[BridgeConfig] = None):
        self.config = config or BridgeConfig()
        self._session = requests.Session()
        if self.config.auth_token:
            self._session.headers["Authorization"] = f"Bearer {self.config.auth_token}"

    @property
    def _base_url(self) -> str:
        return urljoin(self.config.base_url, self.config.api_prefix + "/")

    def _request(self, method: str, path: str, **kwargs) -> dict:
        """统一请求方法：带重试、日志、错误处理。"""
        url = urljoin(self._base_url, path.lstrip("/"))
        kwargs.setdefault("timeout", self.config.timeout_seconds)

        last_error: Optional[Exception] = None
        for attempt in range(self.config.max_retries + 1):
            t0 = time.perf_counter()
            try:
                resp = self._session.request(method, url, **kwargs)
                latency_ms = (time.perf_counter() - t0) * 1000

                if self.config.request_log_enabled:
                    logger.info(
                        f"[bridge] {method} {path} -> {resp.status_code} "
                        f"({latency_ms:.1f}ms) attempt={attempt+1}"
                    )

                resp.raise_for_status()
                data = resp.json()

                # QuantDinger 用 envelope 格式：{"data": ..., "error": null}
                if isinstance(data, dict) and "data" in data:
                    return data["data"]
                return data

            except Exception as e:
                last_error = e
                latency_ms = (time.perf_counter() - t0) * 1000
                logger.warning(
                    f"[bridge] {method} {path} failed ({latency_ms:.1f}ms): {e} "
                    f"attempt={attempt+1}/{self.config.max_retries+1}"
                )
                if attempt < self.config.max_retries:
                    time.sleep(self.config.retry_backoff * (2 ** attempt))

        # 所有重试都失败了——降级，不抛异常
        logger.error(f"[bridge] {method} {path} gave up after {self.config.max_retries+1} attempts: {last_error}")
        return {"_error": str(last_error), "_degraded": True}

    # ------------------------------------------------------------------
    # 健康检查
    # ------------------------------------------------------------------

    def health(self) -> HealthStatus:
        """检查 QuantDinger 是否可达。不需要 token。"""
        # /health 在 api_prefix 外面
        url = urljoin(self.config.base_url, "/health")
        t0 = time.perf_counter()
        try:
            resp = self._session.get(url, timeout=self.config.timeout_seconds)
            latency_ms = (time.perf_counter() - t0) * 1000
            resp.raise_for_status()
            data = resp.json()
            return HealthStatus(
                reachable=True,
                status=data.get("status", "unknown"),
                version=data.get("version", "unknown"),
                timestamp=datetime.now(timezone.utc),
                latency_ms=latency_ms,
            )
        except Exception as e:
            latency_ms = (time.perf_counter() - t0) * 1000
            return HealthStatus(
                reachable=False,
                status="unreachable",
                version="unknown",
                latency_ms=latency_ms,
                error=str(e),
            )

    # ------------------------------------------------------------------
    # 策略相关
    # ------------------------------------------------------------------

    def list_strategies(self, limit: int = 50) -> list[StrategySummary]:
        """列出所有策略，投影成我们的格式。"""
        data = self._request("GET", "/strategies", params={"limit": limit})
        # 降级时 _request 返回带 _degraded 的 dict；正常返回可能是 list
        if isinstance(data, dict) and data.get("_degraded"):
            return []

        rows = data if isinstance(data, list) else data.get("items", [])
        results = []
        for row in rows:
            results.append(StrategySummary(
                strategy_id=str(row.get("id", "")),
                name=row.get("strategy_name", ""),
                strategy_type=row.get("strategy_type", ""),
                symbol=row.get("symbol", ""),
                timeframe=row.get("timeframe", ""),
                status=row.get("status", ""),
                market_category=row.get("market_category", ""),
                execution_mode=row.get("execution_mode", "paper"),
                initial_capital=float(row.get("initial_capital", 0) or 0),
                leverage=float(row.get("leverage", 1) or 1),
                raw=row,
            ))
        return results

    def get_strategy(self, strategy_id: str) -> Optional[StrategySummary]:
        """获取单个策略详情。"""
        data = self._request("GET", f"/strategies/{strategy_id}")
        if data.get("_degraded"):
            return None
        return StrategySummary(
            strategy_id=str(data.get("id", strategy_id)),
            name=data.get("strategy_name", ""),
            strategy_type=data.get("strategy_type", ""),
            symbol=data.get("symbol", ""),
            timeframe=data.get("timeframe", ""),
            status=data.get("status", ""),
            raw=data,
        )

    # ------------------------------------------------------------------
    # 组合 / 持仓
    # ------------------------------------------------------------------

    def get_portfolio(self) -> dict:
        """获取组合概览。降级时返回空。"""
        data = self._request("GET", "/portfolio")
        if data.get("_degraded"):
            return {"positions": [], "total_equity": 0, "_degraded": True}
        return data

    # ------------------------------------------------------------------
    # 回测相关
    # ------------------------------------------------------------------

    def list_backtests(self, limit: int = 20) -> list[dict]:
        """列出最近的回测记录。"""
        data = self._request("GET", "/backtests", params={"limit": limit})
        if data.get("_degraded"):
            return []
        return data if isinstance(data, list) else []

    # ------------------------------------------------------------------
    # 诊断
    # ------------------------------------------------------------------

    def diagnose(self) -> dict:
        """一键诊断：桥接层自己的健康报告。"""
        h = self.health()
        strategies = self.list_strategies(limit=5)
        return {
            "bridge": "quantdinger",
            "config": {
                "base_url": self.config.base_url,
                "timeout": self.config.timeout_seconds,
                "has_token": bool(self.config.auth_token),
            },
            "health": {
                "reachable": h.reachable,
                "status": h.status,
                "latency_ms": round(h.latency_ms, 1),
                "error": h.error,
            },
            "strategies_count": len(strategies),
            "sample_strategies": [s.name for s in strategies[:5]],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
