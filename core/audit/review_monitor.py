# -*- coding: utf-8 -*-
"""core/audit/review_monitor.py —— 复盘自动触发监控。

基于第一性原理：
    为什么要等人工复盘？因为人会偷懒、会忘、会自我欺骗。
    自动监控 = 系统在该复盘的时候主动提醒你，不逃避。

触发条件（红灯信号）：
1. 单笔亏损超过阈值（默认3R）
2. 连续亏损达到次数（默认5笔）
3. 单日亏损超过权益比例（默认5%）
"""
from __future__ import annotations

import logging
from datetime import datetime, date
from typing import Optional

from .db_writer import _get_pg_conn, write_post_mortem_to_db

logger = logging.getLogger("core.audit.review")


# ------------------------------------------------------------------
# 配置阈值
# ------------------------------------------------------------------
class ReviewThresholds:
    """复盘触发阈值配置。"""
    single_loss_r_multiple: float = -3.0      # 单笔亏损超过3R触发
    consecutive_losses: int = 5               # 连续5笔亏损触发
    daily_loss_pct: float = 5.0               # 单日亏损超过5%触发


# ------------------------------------------------------------------
# 核心监控逻辑
# ------------------------------------------------------------------
class ReviewMonitor:
    """复盘自动监控器。

    用法：
        monitor = ReviewMonitor()
        # 平仓后调用
        monitor.on_trade_closed(trade_uid="trade-123", net_pnl=-3000, r_multiple=-3.5)
    """

    def __init__(self, thresholds: Optional[ReviewThresholds] = None):
        self.thresholds = thresholds or ReviewThresholds()
        self._consecutive_losses = 0

    def on_trade_closed(self,
                        trade_uid: str,
                        symbol: str,
                        net_pnl: float,
                        r_multiple: float,
                        equity: float = 100000) -> None:
        """每笔交易平仓后调用，检查是否触发复盘。

        Args:
            trade_uid: 交易ID
            symbol: 交易品种
            net_pnl: 净盈亏
            r_multiple: R倍数
            equity: 当前权益
        """
        # 1. 更新连续亏损计数
        if net_pnl < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0

        # 2. 检查触发条件
        triggers = []

        # 条件1：单笔亏损过大
        if r_multiple <= self.thresholds.single_loss_r_multiple:
            triggers.append({
                "type": "single_big_loss",
                "severity": "P1",
                "message": f"单笔亏损{r_multiple}R，超过阈值{self.thresholds.single_loss_r_multiple}R",
            })

        # 条件2：连续亏损过多
        if self._consecutive_losses >= self.thresholds.consecutive_losses:
            triggers.append({
                "type": "consecutive_losses",
                "severity": "P1",
                "message": f"连续{self._consecutive_losses}笔亏损，超过阈值{self.thresholds.consecutive_losses}笔",
            })

        # 条件3：单日亏损过大
        daily_loss_pct = abs(net_pnl) / equity * 100 if equity > 0 else 0
        if daily_loss_pct >= self.thresholds.daily_loss_pct and net_pnl < 0:
            triggers.append({
                "type": "daily_big_loss",
                "severity": "P2",
                "message": f"单笔亏损占权益{daily_loss_pct:.1f}%，超过阈值{self.thresholds.daily_loss_pct}%",
            })

        # 3. 如果有触发，自动写入复盘记录
        if triggers:
            for trigger in triggers:
                self._auto_create_post_mortem(
                    trade_uid=trade_uid,
                    symbol=symbol,
                    net_pnl=net_pnl,
                    r_multiple=r_multiple,
                    trigger_type=trigger["type"],
                    severity=trigger["severity"],
                    message=trigger["message"],
                )

    def _auto_create_post_mortem(self,
                                  trade_uid: str,
                                  symbol: str,
                                  net_pnl: float,
                                  r_multiple: float,
                                  trigger_type: str,
                                  severity: str,
                                  message: str) -> None:
        """自动创建复盘记录。"""
        try:
            title = f"[自动触发] {trigger_type}: {symbol} 亏损{abs(net_pnl):.0f}"

            record_id = write_post_mortem_to_db(
                title=title,
                post_mortem_type=trigger_type,
                severity=severity,
                what_happened=f"交易{trade_uid}发生亏损：净盈亏{net_pnl:.2f}，R倍数{r_multiple:.2f}",
                why_it_happened="待人工分析",
                what_we_learned="待复盘填写",
                how_to_improve="待复盘填写",
                root_cause_category="trade_loss",
            )

            if record_id:
                logger.warning(
                    "复盘自动触发: %s | %s | 记录ID=%d",
                    title, message, record_id
                )
                print(f"⚠️  复盘提醒: {message}")
                print(f"   已自动创建复盘记录 ID={record_id}，请及时分析填写。")

        except Exception as e:
            logger.warning("failed to auto-create post-mortem: %s", e)

    def get_status(self) -> dict:
        """获取当前监控状态。"""
        return {
            "consecutive_losses": self._consecutive_losses,
            "thresholds": {
                "single_loss_r": self.thresholds.single_loss_r_multiple,
                "consecutive_losses": self.thresholds.consecutive_losses,
                "daily_loss_pct": self.thresholds.daily_loss_pct,
            },
        }


# ------------------------------------------------------------------
# 单例模式
# ------------------------------------------------------------------
_monitor_instance: Optional[ReviewMonitor] = None


def get_review_monitor() -> ReviewMonitor:
    """获取全局复盘监控器单例。"""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = ReviewMonitor()
    return _monitor_instance
