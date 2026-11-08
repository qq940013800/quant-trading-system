# -*- coding: utf-8 -*-
"""core.audit.evolution_rules —— 系统可进化主线的确定性规则纯函数。

第一性原理：
    系统必须能从成功与失败中学习：亏损触发复盘、故障沉淀知识、衰减触发退役建议。
    这些判定规则必须可单测、可审计，且与 DB 读写/日志编排解耦。

纯逻辑约束：
    - 不读 DB、文件、网络或向量服务；不构造连接；
    - 只做判定、分类、评分与分级；不反推新的风控阈值；
    - 阈值作为参数传入，缺省对齐既有占位默认（ReviewThresholds / 健康监控常量）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .knowledge_normalize import normalize_text


# ------------------------------------------------------------------
# 复盘触发规则
# ------------------------------------------------------------------
@dataclass(frozen=True)
class ReviewThresholds:
    """复盘触发阈值（对齐 ReviewMonitor 既有默认占位值）。"""

    single_loss_r_multiple: float = -3.0
    consecutive_losses: int = 5
    daily_loss_pct: float = 5.0


def evaluate_review_triggers(net_pnl: float,
                             r_multiple: float,
                             equity: float,
                             consecutive_losses: int,
                             thresholds: Optional[ReviewThresholds] = None) -> list[dict]:
    """评估一笔平仓是否触发复盘。

    纯判定：不写库、不维护连续亏损计数；计数由编排类持有并传入。

    Args:
        net_pnl: 净盈亏（负为亏损）。
        r_multiple: 入场冻结的 R 倍数。
        equity: 当前权益。
        consecutive_losses: 截至当前的连续亏损笔数。
        thresholds: 阈值配置；缺省用 :class:`ReviewThresholds` 默认值。

    Returns:
        触发项列表，每项含 ``type/severity/message``；无触发返回空列表。
    """
    t = thresholds or ReviewThresholds()
    triggers: list[dict] = []

    if r_multiple <= t.single_loss_r_multiple:
        triggers.append({
            "type": "single_big_loss",
            "severity": "P1",
            "message": f"单笔亏损{r_multiple}R，超过阈值{t.single_loss_r_multiple}R",
        })

    if consecutive_losses >= t.consecutive_losses:
        triggers.append({
            "type": "consecutive_losses",
            "severity": "P1",
            "message": f"连续{consecutive_losses}笔亏损，超过阈值{t.consecutive_losses}笔",
        })

    daily_loss_pct = abs(net_pnl) / equity * 100 if equity > 0 else 0.0
    if daily_loss_pct >= t.daily_loss_pct and net_pnl < 0:
        triggers.append({
            "type": "daily_big_loss",
            "severity": "P2",
            "message": f"单笔亏损占权益{daily_loss_pct:.1f}%，超过阈值{t.daily_loss_pct}%",
        })

    return triggers


# ------------------------------------------------------------------
# 故障分类规则
# ------------------------------------------------------------------
_FAULT_KEYWORD_ORDER: tuple[tuple[tuple[str, ...], str], ...] = (
    (("connection", "connect"), "连接问题"),
    (("timeout", "timed out"), "超时"),
    (("permission", "denied"), "权限问题"),
    (("data", "empty", "missing"), "数据问题"),
    (("order", "trade"), "下单问题"),
    (("risk", "margin"), "风控问题"),
    (("config", "setting"), "配置问题"),
)


def classify_fault(error_type: str, error_msg: str) -> str:
    """按错误信息关键词做故障归类（纯分类）。

    Args:
        error_type: 异常类名（当前分类不使用，保留入参对齐调用方）。
        error_msg: 异常消息文本。

    Returns:
        中文分类标签；未命中既有规则归为 ``系统问题``。
    """
    msg = normalize_text(error_msg)
    for keywords, label in _FAULT_KEYWORD_ORDER:
        if any(kw in msg for kw in keywords):
            return label
    return "系统问题"


# ------------------------------------------------------------------
# 策略健康度评分 / 告警 / 分级规则
# ------------------------------------------------------------------
def score_health(metrics: dict[str, Any]) -> int:
    """按胜率 / Profit Factor / 平均 R 计算健康度基础评分（0-100）。

    口径对齐 StrategyHealthMonitor 既有内联评分；阈值为既有占位默认。
    """
    score = 50

    win_rate = metrics.get("win_rate_pct", 0) or 0
    if win_rate >= 55:
        score += 30
    elif win_rate >= 50:
        score += 20
    elif win_rate >= 45:
        score += 10

    pf = metrics.get("profit_factor") or 0
    if pf >= 1.5:
        score += 40
    elif pf >= 1.3:
        score += 30
    elif pf >= 1.1:
        score += 15

    avg_r = metrics.get("avg_r") or 0
    if avg_r >= 1.5:
        score += 30
    elif avg_r >= 1.0:
        score += 20
    elif avg_r >= 0.5:
        score += 10

    return min(100, score)


def detect_health_warnings(metrics: dict[str, Any]) -> list[str]:
    """检测健康预警信号（胜率/PF/平均 R 过低）。"""
    warnings: list[str] = []
    win_rate = metrics.get("win_rate_pct", 0) or 0
    pf = metrics.get("profit_factor") or 0
    avg_r = metrics.get("avg_r") or 0

    if win_rate < 45:
        warnings.append(f"胜率过低: {win_rate}%")
    if pf < 1.1:
        warnings.append(f"Profit Factor过低: {pf}")
    if avg_r < 0.5:
        warnings.append(f"平均R倍数过低: {avg_r}")

    return warnings


def classify_health(score: int) -> str:
    """按健康度评分分级：green / yellow / red。"""
    if score >= 80:
        return "green"
    if score >= 60:
        return "yellow"
    return "red"
