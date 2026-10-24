"""统一异常基类与错误处理约定。

第一性原理：错误应该尽早暴露，而不是藏在返回值里。

约定：
1. 参数错误 / 状态错误 / 数据损坏 → 抛异常（这是bug，应该被发现）
2. 预期内的"无结果" → 返回 None 或空集合（这是正常业务路径）
3. 外部依赖失败 → 降级处理，不抛异常（外部不可控，不能搞挂自己）

所有自定义异常都继承 QuantTraderError，方便统一捕获。
"""
from __future__ import annotations

from typing import Any, Optional


class QuantTraderError(Exception):
    """所有量化交易系统异常的基类。

    设计原则：
    - 每个异常都带 layer（出错的层级），方便定位
    - 异常信息要人类可读，不要只给错误码
    - 不要吞异常，要带上下文
    """

    layer: str = "core"

    def __init__(self, detail: str, *, layer: Optional[str] = None, **extra: Any):
        self.detail = detail
        if layer:
            self.layer = layer
        self.extra = extra
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        parts = [f"[{self.layer}]", self.detail]
        if self.extra:
            extra_str = " ".join(f"{k}={v!r}" for k, v in self.extra.items())
            parts.append(f"({extra_str})")
        return " ".join(parts)


# ------------------------------------------------------------------
# 数据层异常
# ------------------------------------------------------------------
class DataLayerError(QuantTraderError):
    """数据层错误：数据加载、验证、分割等。"""
    layer = "data"


class ValidationError(DataLayerError):
    """数据验证失败。"""
    layer = "data.validation"


class LookAheadError(DataLayerError):
    """前视偏差：发现了不应该可用的数据被使用了。

    这是最严重的错误之一——直接破坏因果单向不变量。
    """
    layer = "data.lookahead"


class SilentSetAccessError(DataLayerError):
    """静默集数据被访问了——这是严格禁止的。"""
    layer = "data.silent_set"


# ------------------------------------------------------------------
# 特征层异常
# ------------------------------------------------------------------
class FeatureLayerError(QuantTraderError):
    """特征层错误。"""
    layer = "features"


class AsOfContractError(FeatureLayerError):
    """as_of 契约违反：时间戳不对或者时区不对。"""
    layer = "features.as_of"


# ------------------------------------------------------------------
# 模型层异常
# ------------------------------------------------------------------
class ModelLayerError(QuantTraderError):
    """模型层错误。"""
    layer = "models"


class PurgedCVError(ModelLayerError):
    """Purged K-Fold 交叉验证错误。"""
    layer = "models.cv"


# ------------------------------------------------------------------
# 风控层异常
# ------------------------------------------------------------------
class RiskLayerError(QuantTraderError):
    """风控层错误。"""
    layer = "risk"


class StopWideningError(RiskLayerError):
    """止损变宽了——这是不允许的（止损只能向盈利方向移动）。"""
    layer = "risk.stops"


# ------------------------------------------------------------------
# 审计层异常
# ------------------------------------------------------------------
class AuditLayerError(QuantTraderError):
    """审计层错误。"""
    layer = "audit"


class SignalLikeError(AuditLayerError):
    """信号格式不对，无法写入审计日志。"""
    layer = "audit.signal"


class ReplayMismatch(AuditLayerError):
    """审计回放不匹配——记录的数据和重算的不一致。"""
    layer = "audit.replay"


# ------------------------------------------------------------------
# 回测层异常
# ------------------------------------------------------------------
class BacktestLayerError(QuantTraderError):
    """回测层错误。"""
    layer = "backtest"


# ------------------------------------------------------------------
# 桥接层异常
# ------------------------------------------------------------------
class BridgeLayerError(QuantTraderError):
    """桥接层错误。"""
    layer = "integration.bridge"


# ------------------------------------------------------------------
# 工厂函数
# ------------------------------------------------------------------
def ok(value: Any = None) -> tuple[bool, Any]:
    """成功返回的快捷方式。

    用于需要区分成功/失败的场景：
        success, result = compute_something()
        if not success:
            handle_error(result)
    """
    return True, value


def err(message: str, **extra: Any) -> tuple[bool, str]:
    """失败返回的快捷方式。"""
    return False, message
