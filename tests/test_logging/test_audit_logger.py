# -*- coding: utf-8 -*-
"""tests.test_logging.test_audit_logger —— 审计日志系统测试。"""
from __future__ import annotations

import json
import pytest
import tempfile
from pathlib import Path

from core.logging.audit_logger import (
    AuditLogger,
    LogLevel,
    LogCategory,
)


@pytest.fixture
def temp_logger():
    """创建临时日志目录的日志器。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = AuditLogger(
            strategy_name="test_strategy",
            strategy_version="v1.0.0",
            log_dir=tmpdir,
        )
        yield logger, tmpdir


class TestBasicLogging:
    def test_info_log_writes_file(self, temp_logger):
        """INFO日志应该写入文件。"""
        logger, tmpdir = temp_logger
        logger.log_info(LogCategory.SYSTEM, "系统启动")

        log_file = Path(tmpdir) / f"trading_{__import__('datetime').datetime.now().strftime('%Y%m%d')}.log"
        assert log_file.exists()
        content = log_file.read_text(encoding="utf-8")
        assert "系统启动" in content

    def test_log_entry_is_json(self, temp_logger):
        """日志条目应该是JSON格式。"""
        logger, tmpdir = temp_logger
        logger.log_info(LogCategory.SYSTEM, "测试JSON格式")

        log_file = Path(tmpdir) / f"trading_{__import__('datetime').datetime.now().strftime('%Y%m%d')}.log"
        first_line = log_file.read_text(encoding="utf-8").strip().split("\n")[0]
        entry = json.loads(first_line)  # 能解析就是JSON
        assert entry["message"] == "测试JSON格式"
        assert entry["strategy_name"] == "test_strategy"


class TestTradeLogging:
    def test_trade_log_writes_separate_file(self, temp_logger):
        """交易日志应该写入专门的文件。"""
        logger, tmpdir = temp_logger
        logger.log_trade(
            action="OPEN",
            symbol="XAUUSD",
            side="buy",
            price=2000.0,
            quantity=0.1,
            reason="趋势突破",
        )

        trade_file = Path(tmpdir) / f"trades_{__import__('datetime').datetime.now().strftime('%Y%m%d')}.jsonl"
        assert trade_file.exists()

        trades = logger.get_trade_history()
        assert len(trades) == 1
        assert trades[0]["extra"]["action"] == "OPEN"
        assert trades[0]["symbol"] == "XAUUSD"

    def test_decision_log_records_inputs_outputs(self, temp_logger):
        """决策日志应该记录输入和输出（审计用）。"""
        logger, tmpdir = temp_logger
        logger.log_decision(
            layer="signal",
            decision="GO_LONG",
            inputs={"atr": 2.5, "structure": "bullish"},
            outputs={"strength": 0.8, "stop_loss": 1995.0},
        )

        logs = logger.get_recent_logs()
        assert len(logs) >= 1
        decision_log = [l for l in logs if "DECISION" in l["message"]][0]
        assert decision_log["extra"]["inputs"]["atr"] == 2.5
        assert decision_log["extra"]["outputs"]["strength"] == 0.8


class TestLogLevelFilter:
    def test_debug_filtered_by_default(self, temp_logger):
        """DEBUG日志默认应该被过滤掉。"""
        logger, tmpdir = temp_logger
        logger.log_debug(LogCategory.SYSTEM, "这是debug日志")

        logs = logger.get_recent_logs()
        # 默认min_level是INFO，debug应该被过滤
        assert len(logs) == 0
