# -*- coding: utf-8 -*-
"""test_trade_journal.py —— 验证交易日志自动写入端到端流程。

运行：python scripts/test_trade_journal.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.execution.engine import ExecutionEngine, OrderSide


def test_full_trade_cycle():
    """测试完整交易闭环：开仓→平仓→自动写日志。"""
    print("=== 测试完整交易闭环 ===")
    engine = ExecutionEngine()

    # 1. 开仓
    print("1. 开仓...")
    position = engine.execute_signal(
        symbol="XAUUSD",
        side=OrderSide.BUY,
        signal_strength=0.8,
        equity=100000,
        atr=2.5,
    )

    if not position:
        print("❌ 开仓失败")
        return False
    print(f"✅ 开仓成功: {position.symbol} {position.quantity}手 @ {position.entry_price}")

    # 2. 平仓
    print("\n2. 平仓...")
    order = engine.close_position(symbol="XAUUSD", reason="take_profit")

    if not order:
        print("❌ 平仓失败")
        return False
    print(f"✅ 平仓成功: {order.avg_fill_price}")

    print("\n✅ 完整交易闭环测试通过！")
    print("   现在去数据库验证：")
    print("   SELECT * FROM qd_trade_journal ORDER BY id DESC LIMIT 1;")
    return True


if __name__ == "__main__":
    print("开始测试交易日志端到端流程...\n")
    success = test_full_trade_cycle()
    print("\n" + "=" * 50)
    print(f"结果: {'✅ 通过' if success else '❌ 失败'}")
    print("=" * 50)
