# -*- coding: utf-8 -*-
"""core/logging/audit_logger.py —— 结构化审计日志系统。

基于第一性原理：
    量化交易系统的日志不是普通的print，它的核心作用是：
    1. 审计——每笔决策都能完整还原（AGENTS.md硬规则：决策可审计）
    2. 调试——出问题时能快速定位到哪一层哪一步出错
    3. 监控——异常能及时告警
    4. 复盘——事后能复盘改进策略

    核心原则：
    - 结构化日志（JSON格式），不是纯文本
    - 每笔交易记录完整决策链：数据→特征→信号→风控→执行
    - 带时间戳、策略版本、参数版本，可追溯
    - 分级：DEBUG / INFO / WARNING / ERROR / CRITICAL
"""
from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Any


# ------------------------------------------------------------------
# 枚举与数据类
# ------------------------------------------------------------------
class LogLevel(Enum):
    """日志级别。"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogCategory(Enum):
    """日志分类——按系统层级分类，方便过滤和查询。"""
    DATA = "data"                # 数据层
    FEATURE = "feature"          # 特征层
    SIGNAL = "signal"            # 信号层
    RISK = "risk"                # 风控层
    EXECUTION = "execution"      # 执行层
    STRATEGY = "strategy"        # 策略层
    MONITOR = "monitor"          # 监控层
    SYSTEM = "system"            # 系统层


@dataclass
class LogEntry:
    """结构化日志条目。"""
    timestamp: str
    level: str
    category: str
    message: str
    strategy_name: Optional[str] = None
    strategy_version: Optional[str] = None
    symbol: Optional[str] = None
    pnl: Optional[float] = None
    extra: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


# ------------------------------------------------------------------
# 审计日志器
# ------------------------------------------------------------------
class AuditLogger:
    """结构化审计日志器。

    用法：
        logger = AuditLogger("trend_v1", "v1.2.0")
        logger.log_signal(
            category=LogCategory.SIGNAL,
            message="趋势突破信号",
            symbol="XAUUSD",
            extra={"strength": 0.8, "atr": 2.5},
        )
        logger.log_trade(
            action="OPEN",
            symbol="XAUUSD",
            side="buy",
            price=2000.0,
            quantity=0.1,
        )
    """

    def __init__(self,
                 strategy_name: str = "unknown",
                 strategy_version: str = "dev",
                 log_dir: Optional[str] = None,
                 min_level: LogLevel = LogLevel.INFO):
        self.strategy_name = strategy_name
        self.strategy_version = strategy_version
        self.min_level = min_level

        # 设置日志目录
        if log_dir is None:
            log_dir = "logs"
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # 当天的日志文件
        self.log_file = self.log_dir / f"trading_{datetime.now().strftime('%Y%m%d')}.log"

        # 交易日志（单独的交易记录文件）
        self.trade_log_file = self.log_dir / f"trades_{datetime.now().strftime('%Y%m%d')}.jsonl"

    def _write(self, entry: LogEntry):
        """写入日志条目。"""
        # 级别过滤
        level_order = {lvl: i for i, lvl in enumerate(LogLevel)}
        if level_order[LogLevel(entry.level)] < level_order[self.min_level]:
            return

        # 写入主日志文件
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(entry.to_json() + "\n")

        # 同时输出到控制台
        print(f"[{entry.timestamp}] {entry.level:8s} {entry.category:10s} | {entry.message}")

    def log(self,
            level: LogLevel,
            category: LogCategory,
            message: str,
            symbol: Optional[str] = None,
            extra: Optional[dict] = None):
        """通用日志方法。"""
        entry = LogEntry(
            timestamp=datetime.now().isoformat(),
            level=level.value,
            category=category.value,
            message=message,
            strategy_name=self.strategy_name,
            strategy_version=self.strategy_version,
            symbol=symbol,
            extra=extra or {},
        )
        self._write(entry)

    def log_debug(self, category: LogCategory, message: str, **kwargs):
        """DEBUG级别日志。"""
        self.log(LogLevel.DEBUG, category, message, **kwargs)

    def log_info(self, category: LogCategory, message: str, **kwargs):
        """INFO级别日志。"""
        self.log(LogLevel.INFO, category, message, **kwargs)

    def log_warning(self, category: LogCategory, message: str, **kwargs):
        """WARNING级别日志。"""
        self.log(LogLevel.WARNING, category, message, **kwargs)

    def log_error(self, category: LogCategory, message: str, **kwargs):
        """ERROR级别日志。"""
        self.log(LogLevel.ERROR, category, message, **kwargs)

    def log_critical(self, category: LogCategory, message: str, **kwargs):
        """CRITICAL级别日志（如爆仓、系统故障）。"""
        self.log(LogLevel.CRITICAL, category, message, **kwargs)

    # ------------------------------------------------------------------
    # 专用日志方法（方便交易审计）
    # ------------------------------------------------------------------
    def log_trade(self,
                   action: str,
                   symbol: str,
                   side: str,
                   price: float,
                   quantity: float,
                   pnl: Optional[float] = None,
                   reason: str = ""):
        """记录交易（开仓/平仓）。

        这是最核心的审计日志——每笔交易都必须记录完整信息。
        """
        entry = LogEntry(
            timestamp=datetime.now().isoformat(),
            level=LogLevel.INFO.value,
            category=LogCategory.EXECUTION.value,
            message=f"TRADE {action}: {side} {quantity} {symbol} @ {price}",
            strategy_name=self.strategy_name,
            strategy_version=self.strategy_version,
            symbol=symbol,
            pnl=pnl,
            extra={
                "action": action,
                "side": side,
                "price": price,
                "quantity": quantity,
                "reason": reason,
            },
        )
        self._write(entry)

        # 交易同时写入专门的交易日志文件（JSON Lines格式）
        with open(self.trade_log_file, "a", encoding="utf-8") as f:
            f.write(entry.to_json() + "\n")

    def log_decision(self,
                      layer: str,
                      decision: str,
                      inputs: dict,
                      outputs: dict):
        """记录决策过程（审计用——能还原每一步）。

        用法：
            logger.log_decision(
                layer="signal",
                decision="GO_LONG",
                inputs={"atr": 2.5, "structure": "bullish"},
                outputs={"strength": 0.8, "stop_loss": 1995.0},
            )
        """
        self.log_info(
            LogCategory.SIGNAL,
            f"DECISION [{layer}]: {decision}",
            extra={"inputs": inputs, "outputs": outputs},
        )

    # ------------------------------------------------------------------
    # 查询与统计
    # ------------------------------------------------------------------
    def get_recent_logs(self, n: int = 100,
                         category: Optional[LogCategory] = None) -> list[dict]:
        """读取最近的日志。"""
        if not self.log_file.exists():
            return []

        logs = []
        with open(self.log_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    if category is None or entry["category"] == category.value:
                        logs.append(entry)
                except json.JSONDecodeError:
                    continue

        return logs[-n:]

    def get_trade_history(self) -> list[dict]:
        """读取交易历史。"""
        if not self.trade_log_file.exists():
            return []

        trades = []
        with open(self.trade_log_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    trades.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue
        return trades
