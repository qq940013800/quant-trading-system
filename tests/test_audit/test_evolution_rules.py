# -*- coding: utf-8 -*-
"""tests.test_audit.test_evolution_rules —— 可进化规则纯函数测试。"""
from __future__ import annotations

import pytest

from core.audit.evolution_rules import (
    ReviewThresholds,
    classify_fault,
    classify_health,
    detect_health_warnings,
    evaluate_review_triggers,
    score_health,
)


class TestReviewTriggers:
    def test_single_big_loss_triggers(self):
        triggers = evaluate_review_triggers(net_pnl=-3000, r_multiple=-3.5,
                                            equity=100000, consecutive_losses=1)
        types = [t["type"] for t in triggers]
        assert "single_big_loss" in types

    def test_consecutive_losses_trigger(self):
        triggers = evaluate_review_triggers(net_pnl=-500, r_multiple=-1.0,
                                            equity=100000, consecutive_losses=5)
        assert any(t["type"] == "consecutive_losses" for t in triggers)

    def test_daily_big_loss_triggers(self):
        # 净亏 6000 / 100000 = 6%，超 5% 阈值
        triggers = evaluate_review_triggers(net_pnl=-6000, r_multiple=-1.0,
                                            equity=100000, consecutive_losses=1)
        assert any(t["type"] == "daily_big_loss" for t in triggers)

    def test_profitable_trade_no_trigger(self):
        triggers = evaluate_review_triggers(net_pnl=2000, r_multiple=1.5,
                                            equity=100000, consecutive_losses=0)
        assert triggers == []

    def test_zero_equity_does_not_crash(self):
        triggers = evaluate_review_triggers(net_pnl=-100, r_multiple=-1.0,
                                            equity=0, consecutive_losses=0)
        assert triggers == []

    def test_custom_thresholds_apply(self):
        tight = ReviewThresholds(single_loss_r_multiple=-2.0,
                                consecutive_losses=3, daily_loss_pct=2.0)
        triggers = evaluate_review_triggers(net_pnl=-2500, r_multiple=-2.5,
                                            equity=100000, consecutive_losses=3,
                                            thresholds=tight)
        assert len(triggers) >= 2


class TestFaultClassification:
    @pytest.mark.parametrize("msg,label", [
        ("Connection refused", "连接问题"),
        ("Request timed out", "超时"),
        ("Permission denied", "权限问题"),
        ("empty response missing data", "数据问题"),
        ("order rejected trade failed", "下单问题"),
        ("margin risk insufficient", "风控问题"),
        ("config setting applied", "配置问题"),
    ])
    def test_keyword_mapping(self, msg, label):
        assert classify_fault("Exception", msg) == label

    def test_unknown_fault_falls_back_to_system(self):
        assert classify_fault("RuntimeError", "something exploded") == "系统问题"

    def test_error_type_is_not_used_for_classification(self):
        # 异常类名是 TimeoutError，但消息按连接关键词归类；分类只看消息文本
        assert classify_fault("TimeoutError", "connection refused") == "连接问题"


class TestHealthRules:
    def test_high_metrics_score_high(self):
        score = score_health({"win_rate_pct": 58, "profit_factor": 1.6, "avg_r": 1.6})
        assert score >= 80

    def test_low_metrics_score_low(self):
        score = score_health({"win_rate_pct": 30, "profit_factor": 0.8, "avg_r": 0.2})
        assert score < 60

    def test_score_capped_at_100(self):
        score = score_health({"win_rate_pct": 100, "profit_factor": 9.9, "avg_r": 9.9})
        assert score == 100

    def test_detect_warnings_all_three(self):
        warnings = detect_health_warnings({"win_rate_pct": 40, "profit_factor": 0.9, "avg_r": 0.3})
        assert len(warnings) == 3

    def test_detect_warnings_empty_when_healthy(self):
        warnings = detect_health_warnings({"win_rate_pct": 55, "profit_factor": 1.4, "avg_r": 1.2})
        assert warnings == []

    @pytest.mark.parametrize("score,expected", [
        (90, "green"),
        (80, "green"),
        (70, "yellow"),
        (60, "yellow"),
        (59, "red"),
        (30, "red"),
    ])
    def test_classify_boundaries(self, score, expected):
        assert classify_health(score) == expected
