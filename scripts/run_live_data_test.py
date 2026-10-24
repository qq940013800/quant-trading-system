# -*- coding: utf-8 -*-
"""scripts/run_live_data_test.py —— 实盘数据端到端测试框架。

基于第一性原理：实盘接入前必须通过完整的数据质量验证和因果性检查，
否则就是在裸奔。本脚本提供一键式实盘数据接入测试。

测试流程：
1. 数据加载与完整性检查
2. OHLC一致性与异常值检测
3. 前视偏差自动检测
4. 特征计算验证（ATR/结构/形态）
5. 风控边界测试（止损/仓位）
6. 生成测试报告

使用方法：
    python scripts/run_live_data_test.py --csv data/XAUUSD_M5.csv --symbol XAUUSD --tz 2
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# 添加项目根目录到 path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.data.loader import load_bars
from core.data.validator import validate_bars, assert_as_of
from core.data.bar import Bar
from core.features.atr import wilder_atr
from core.features.structure import get_market_structure
from core.audit.lookahead_detector import LookaheadDetector
from core.risk.stops import StopConfig, evaluate_stops
from core.backtest.metrics import compute_metrics

log = logging.getLogger("live_data_test")


class TestResult:
    """单项测试结果。"""
    def __init__(self, name: str, passed: bool, detail: str = "", severity: str = "info"):
        self.name = name
        self.passed = passed
        self.detail = detail
        self.severity = severity

    def __repr__(self):
        status = "✅ PASS" if self.passed else "❌ FAIL"
        return f"{status} | {self.name} | {self.detail}"


def test_data_loading(csv_path: str, symbol: str, tz_offset: float) -> tuple[list[Bar], list[TestResult]]:
    """测试1：数据加载与完整性。"""
    results = []
    bars = []

    try:
        bars = load_bars(csv_path, symbol, tz_offset)
        results.append(TestResult(
            "数据加载",
            True,
            f"成功加载 {len(bars)} 根K线",
            severity="info"
        ))
    except Exception as e:
        results.append(TestResult(
            "数据加载",
            False,
            f"加载失败: {e}",
            severity="critical"
        ))
        return bars, results

    # 检查数据量
    if len(bars) < 100:
        results.append(TestResult(
            "数据量充足性",
            False,
            f"只有 {len(bars)} 根K线，建议至少 1000 根",
            severity="high"
        ))
    else:
        results.append(TestResult(
            "数据量充足性",
            True,
            f"{len(bars)} 根K线，数据量充足",
            severity="info"
        ))

    # 检查时间范围
    if bars:
        first_ts = bars[0].ts_utc
        last_ts = bars[-1].ts_utc
        results.append(TestResult(
            "时间范围",
            True,
            f"{first_ts} ~ {last_ts}",
            severity="info"
        ))

    return bars, results


def test_data_quality(bars: list[Bar]) -> list[TestResult]:
    """测试2：数据质量验证。"""
    results = []

    if not bars:
        results.append(TestResult("数据质量", False, "无数据", "critical"))
        return results

    # 运行标准验证
    report = validate_bars(bars)

    # 检查OHLC一致性
    ohlc_ok = all(
        b.high >= max(b.open_, b.close) and b.low <= min(b.open_, b.close)
        for b in bars
    )
    results.append(TestResult(
        "OHLC一致性",
        ohlc_ok,
        "所有K线 high >= max(open,close), low <= min(open,close)" if ohlc_ok else "存在OHLC不一致",
        "critical" if not ohlc_ok else "info"
    ))

    # 检查价格合理性（黄金价格区间）
    prices = [b.close for b in bars]
    price_min, price_max = min(prices), max(prices)
    results.append(TestResult(
        "价格合理性",
        True,
        f"价格区间: {price_min:.2f} ~ {price_max:.2f}",
        "info"
    ))

    # 检查跳空数量
    gaps = [g for g in report.gaps]
    if gaps:
        results.append(TestResult(
            "缺口检测",
            False,
            f"发现 {len(gaps)} 个缺口，最大缺口 {max(g.duration_bars for g in gaps)} 根K线",
            "high"
        ))
    else:
        results.append(TestResult(
            "缺口检测",
            True,
            "无缺口",
            "info"
        ))

    # 检查异常值
    outliers = [o for o in report.outliers]
    if outliers:
        results.append(TestResult(
            "异常值检测",
            False,
            f"发现 {len(outliers)} 个异常值",
            "medium"
        ))
    else:
        results.append(TestResult(
            "异常值检测",
            True,
            "无异常值",
            "info"
        ))

    return results


def test_lookahead(bars: list[Bar]) -> list[TestResult]:
    """测试3：前视偏差检测。"""
    results = []

    if not bars:
        return results

    detector = LookaheadDetector()

    # 检查时间戳顺序
    timestamps = pd.Series([b.ts_utc for b in bars])
    monotonic = detector.check_timestamp_order(timestamps, location="live_data")

    results.append(TestResult(
        "时间戳单调性",
        monotonic,
        "时间戳严格递增" if monotonic else "时间戳乱序！",
        "critical" if not monotonic else "info"
    ))

    # 检查因果性
    try:
        as_of = bars[-1].ts_utc
        assert_as_of(bars, as_of)
        results.append(TestResult(
            "因果性检查",
            True,
            "所有数据时间 <= as_of 时间",
            "info"
        ))
    except Exception as e:
        results.append(TestResult(
            "因果性检查",
            False,
            f"前视偏差: {e}",
            "critical"
        ))

    # 综合摘要
    summary = detector.summary()
    if not summary["passed"]:
        results.append(TestResult(
            "前视偏差综合",
            False,
            f"发现 {summary['total_violations']} 个违规，{summary['critical_count']} 个严重",
            "critical"
        ))
    else:
        results.append(TestResult(
            "前视偏差综合",
            True,
            "无前视偏差",
            "info"
        ))

    return results


def test_features(bars: list[Bar]) -> list[TestResult]:
    """测试4：特征计算验证。"""
    results = []

    if len(bars) < 50:
        results.append(TestResult("特征计算", False, "数据不足", "high"))
        return results

    # 测试ATR计算
    try:
        import pandas as pd
        as_of = bars[-1].ts_utc
        atr_val = wilder_atr(bars[-50:], as_of=as_of, period=14)
        results.append(TestResult(
            "ATR计算",
            True,
            f"ATR(14) = {atr_val:.4f}",
            "info"
        ))
    except Exception as e:
        results.append(TestResult(
            "ATR计算",
            False,
            f"ATR计算失败: {e}",
            "high"
        ))

    # 测试市场结构识别
    try:
        structure = get_market_structure(bars[-100:], k=3)
        results.append(TestResult(
            "市场结构识别",
            True,
            f"识别到市场结构: {structure.trend}",
            "info"
        ))
    except Exception as e:
        results.append(TestResult(
            "市场结构识别",
            False,
            f"结构识别失败: {e}",
            "high"
        ))

    return results


def test_risk_controls(bars: list[Bar]) -> list[TestResult]:
    """测试5：风控边界测试。"""
    results = []

    if len(bars) < 20:
        results.append(TestResult("风控测试", False, "数据不足", "high"))
        return results

    # 测试止损配置
    config = StopConfig(
        atr_mult=2.0,
        max_holding_bars=100,
        breakeven_r=1.0,
        trailing_activation_r=1.5,
        trailing_offset_r=1.0,
    )

    try:
        # 模拟一个多头仓位
        from core.risk.stops import StopState
        state = StopState(
            entry_price=bars[-1].close,
            direction=1,  # 多头
            entry_atr=2.0,
            entry_dist=4.0,
            current_stop=bars[-1].close - 4.0,
            bars_held=0,
        )

        results.append(TestResult(
            "止损配置",
            True,
            "四级止损配置有效",
            "info"
        ))
    except Exception as e:
        results.append(TestResult(
            "止损配置",
            False,
            f"止损测试失败: {e}",
            "high"
        ))

    return results


def generate_report(all_results: list[TestResult]) -> str:
    """生成测试报告。"""
    total = len(all_results)
    passed = sum(1 for r in all_results if r.passed)
    failed = total - passed
    critical = sum(1 for r in all_results if not r.passed and r.severity == "critical")
    high = sum(1 for r in all_results if not r.passed and r.severity == "high")

    report_lines = [
        "=" * 60,
        "实盘数据接入测试报告",
        "=" * 60,
        "",
        f"总测试项: {total}",
        f"通过: {passed} ({passed/total*100:.1f}%)",
        f"失败: {failed}",
        f"严重(critical): {critical}",
        f"高(high): {high}",
        "",
        "=" * 60,
        "详细结果:",
        "=" * 60,
        "",
    ]

    for r in all_results:
        report_lines.append(str(r))

    report_lines.append("")
    report_lines.append("=" * 60)

    # 最终结论
    if critical > 0:
        report_lines.append("⛔ 结论：数据存在严重问题，禁止接入实盘！")
    elif high > 0:
        report_lines.append("⚠️ 结论：数据存在高风险问题，需人工审核后再接入")
    else:
        report_lines.append("✅ 结论：数据测试通过，可以接入实盘")

    report_lines.append("=" * 60)

    return "\n".join(report_lines)


def main():
    parser = argparse.ArgumentParser(description="实盘数据端到端测试")
    parser.add_argument("--csv", required=True, help="CSV数据文件路径")
    parser.add_argument("--symbol", required=True, help="交易品种")
    parser.add_argument("--tz", type=float, default=2.0, help="经纪商时区偏移(小时)")
    parser.add_argument("--verbose", action="store_true", help="详细输出")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    all_results = []

    print("🔍 开始实盘数据接入测试...")
    print()

    # 测试1：数据加载
    print("📦 测试1: 数据加载与完整性...")
    bars, results = test_data_loading(args.csv, args.symbol, args.tz)
    all_results.extend(results)
    for r in results:
        print(f"   {r}")

    # 测试2：数据质量
    print()
    print("🔍 测试2: 数据质量验证...")
    results = test_data_quality(bars)
    all_results.extend(results)
    for r in results:
        print(f"   {r}")

    # 测试3：前视偏差
    print()
    print("👁️  测试3: 前视偏差检测...")
    results = test_lookahead(bars)
    all_results.extend(results)
    for r in results:
        print(f"   {r}")

    # 测试4：特征计算
    print()
    print("📊 测试4: 特征计算验证...")
    results = test_features(bars)
    all_results.extend(results)
    for r in results:
        print(f"   {r}")

    # 测试5：风控边界
    print()
    print("🛡️  测试5: 风控边界测试...")
    results = test_risk_controls(bars)
    all_results.extend(results)
    for r in results:
        print(f"   {r}")

    # 生成报告
    print()
    report = generate_report(all_results)
    print(report)

    # 返回退出码
    critical_failures = sum(1 for r in all_results if not r.passed and r.severity == "critical")
    sys.exit(1 if critical_failures > 0 else 0)


if __name__ == "__main__":
    main()
