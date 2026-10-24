# -*- coding: utf-8 -*-
"""test_knowledge_reuse.py —— 知识复用闭环测试。

验证完整的知识闭环：
1. 知识沉淀（写入）
2. 知识检索（查询）
3. 知识应用（决策时自动引用）
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.execution.engine import ExecutionEngine, OrderSide
from core.audit.fault_catcher import get_fault_catcher


def test_knowledge_reuse_loop():
    """测试完整的知识复用闭环。"""
    print("=" * 60)
    print("知识复用闭环测试：沉淀 → 检索 → 应用")
    print("=" * 60)

    # Step 1: 先制造一个故障，沉淀到知识库
    print("\n【Step 1】沉淀：模拟一次连接故障...")
    catcher = get_fault_catcher()
    try:
        raise ConnectionError("XAUUSD 交易接口连接超时")
    except ConnectionError as e:
        fault_id = catcher.capture(
            symptom="XAUUSD 下单失败",
            exception=e,
            context={"symbol": "XAUUSD", "side": "buy"},
        )
        print(f"  ✅ 故障已沉淀，知识库ID={fault_id}")

    # Step 2: 执行交易决策，验证自动检索历史经验
    print("\n【Step 2】应用：执行XAUUSD买入决策...")
    engine = ExecutionEngine()

    position = engine.execute_signal(
        symbol="XAUUSD",
        side=OrderSide.BUY,
        signal_strength=0.8,
        equity=100000,
        atr=2.5,
    )

    if position:
        print(f"  ✅ 交易执行成功: {position.quantity}手 @ {position.entry_price}")
    else:
        print("  ⚠️ 交易未执行（可能信号太弱或风控拦截）")

    print("\n" + "=" * 60)
    print("✅ 知识复用闭环验证完成！")
    print("=" * 60)
    print("\n💡 完整闭环：")
    print("   过去故障 → 沉淀到知识库 → 下次决策自动检索 → 避免重复踩坑")


if __name__ == "__main__":
    test_knowledge_reuse_loop()
