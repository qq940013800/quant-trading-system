"""集成层：验证层与执行层之间的桥接。"""
from .bridge import (
    BridgeConfig,
    HealthStatus,
    QuantDingerBridge,
    StrategySummary,
)

__all__ = [
    "BridgeConfig",
    "HealthStatus",
    "QuantDingerBridge",
    "StrategySummary",
]
