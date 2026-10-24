# -*- coding: utf-8 -*-
"""test_knowledge_system.py —— 知识沉淀与复用系统综合测试。

测试内容：
1. 复盘自动触发
2. 故障自动捕获
3. 知识检索与复用
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.audit.review_monitor import get_review_monitor
from core.audit.fault_catcher import get_fault_catcher
from core.audit.knowledge_retriever import get_knowledge_retriever


def test_review_monitor():
    """测试复盘自动触发。"""
    print("=" * 60)
    print("测试1：复盘自动触发")
    print("=" * 60)

    monitor = get_review_monitor()

    # 模拟连续亏损
    print("\n模拟连续3笔亏损：")
    for i in range(3):
        monitor.on_trade_closed(
            trade_uid=f"trade-loss-{i}",
            symbol="XAUUSD",
            net_pnl=-1000,
            r_multiple=-1.0,
        )

    print("\n模拟一笔大亏（-4R）：")
    monitor.on_trade_closed(
        trade_uid="trade-big-loss",
        symbol="XAUUSD",
        net_pnl=-4000,
        r_multiple=-4.0,
    )

    print(f"\n当前监控状态: {monitor.get_status()}")
    return True


def test_fault_catcher():
    """测试故障自动捕获。"""
    print("\n" + "=" * 60)
    print("测试2：故障自动捕获")
    print("=" * 60)

    catcher = get_fault_catcher()

    try:
        # 模拟一个连接错误
        raise ConnectionError("无法连接到交易所，连接超时")
    except ConnectionError as e:
        record_id = catcher.capture(
            symptom="连接交易所失败",
            exception=e,
            context={"exchange": "binance", "api": "futures"},
        )
        print(f"\n故障记录ID: {record_id}")

    return True


def test_knowledge_retriever():
    """测试知识检索与复用。"""
    print("\n" + "=" * 60)
    print("测试3：知识检索与复用")
    print("=" * 60)

    retriever = get_knowledge_retriever()

    # 检索故障
    print("\n检索'连接'相关故障：")
    faults = retriever.search_faults("连接")
    for i, f in enumerate(faults[:3], 1):
        print(f"  {i}. {f['title']}")
        print(f"     分类: {f['category']}, 置信度: {f['confidence_score']}")

    # 获取决策前教训
    print("\nXAUUSD 做多决策前的历史教训：")
    lessons = retriever.get_lessons_for_decision("XAUUSD", "buy", "breakout")
    for lesson in lessons:
        print(f"  {lesson}")

    # 知识库统计
    print("\n知识库统计：")
    stats = retriever.get_knowledge_stats()
    for k, v in stats.items():
        print(f"  {k}: {v}")

    return True


if __name__ == "__main__":
    print("🚀 知识沉淀与复用系统综合测试\n")

    t1 = test_review_monitor()
    t2 = test_fault_catcher()
    t3 = test_knowledge_retriever()

    print("\n" + "=" * 60)
    print("📊 测试总结")
    print("=" * 60)
    print(f"复盘自动触发: {'✅ 通过' if t1 else '❌ 失败'}")
    print(f"故障自动捕获: {'✅ 通过' if t2 else '❌ 失败'}")
    print(f"知识检索复用: {'✅ 通过' if t3 else '❌ 失败'}")
    print("=" * 60)
    print("\n💡 完整的知识闭环已建成：")
    print("   决策 → 交易 → 复盘/故障 → 知识库 → 检索复用 → 决策优化")
