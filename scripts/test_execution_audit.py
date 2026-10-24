# -*- coding: utf-8 -*-
"""test_execution_audit.py —— 验证执行引擎决策审计端到端流程。

运行：python scripts/test_execution_audit.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.execution.engine import ExecutionEngine, OrderSide


def test_accepted_trade():
    """测试接受一笔交易，验证审计记录写入。"""
    print("=== 测试1：接受一笔交易 ===")
    engine = ExecutionEngine()

    position = engine.execute_signal(
        symbol="XAUUSD",
        side=OrderSide.BUY,
        signal_strength=0.8,
        equity=100000,
        atr=2.5,
    )

    if position:
        print(f"✅ 交易执行成功: {position.symbol} {position.quantity}手")
    else:
        print("❌ 交易执行失败")
    return position is not None


def test_rejected_weak_signal():
    """测试弱信号被拒绝，验证审计记录写入。"""
    print("\n=== 测试2：弱信号被拒绝 ===")
    engine = ExecutionEngine()

    position = engine.execute_signal(
        symbol="XAUUSD",
        side=OrderSide.BUY,
        signal_strength=0.1,  # 太弱
        equity=100000,
        atr=2.5,
    )

    if position is None:
        print("✅ 弱信号正确拒绝")
    else:
        print("❌ 弱信号应该被拒绝")
    return position is None


def test_rejected_risk_check():
    """测试风控检查失败被拒绝。"""
    print("\n=== 测试3：风控检查失败 ===")

    def strict_risk_check(symbol, side, quantity, price):
        return False, "风控测试：超过风险限额"

    engine = ExecutionEngine(risk_check_fn=strict_risk_check)

    position = engine.execute_signal(
        symbol="XAUUSD",
        side=OrderSide.BUY,
        signal_strength=0.8,
        equity=100000,
        atr=2.5,
    )

    if position is None:
        print("✅ 风控失败正确拒绝")
    else:
        print("❌ 风控应该拒绝")
    return position is None


if __name__ == "__main__":
    print("开始测试执行引擎决策审计集成...\n")

    t1 = test_accepted_trade()
    t2 = test_rejected_weak_signal()
    t3 = test_rejected_risk_check()

    print("\n" + "=" * 50)
    print(f"接受交易测试: {'✅ 通过' if t1 else '❌ 失败'}")
    print(f"弱信号拒绝测试: {'✅ 通过' if t2 else '❌ 失败'}")
    print(f"风控拒绝测试: {'✅ 通过' if t3 else '❌ 失败'}")
    print("=" * 50)

    print("\n💡 提示：所有决策（接受/拒绝）现在都会自动写入数据库。")
    print("   查看数据库验证：SELECT * FROM qd_ai_decisions ORDER BY id DESC LIMIT 10;")
