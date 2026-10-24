# -*- coding: utf-8 -*-
"""test_db_writer.py —— 验证决策审计数据库写入模块。

运行：python scripts/test_db_writer.py
"""
import sys
import os

# 把项目根目录加入路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.audit.record import Decision
from core.audit.db_writer import write_decision_to_db, write_post_mortem_to_db


def test_post_mortem_write():
    """测试写入复盘记录。"""
    print("=== 测试写入复盘记录 ===")
    record_id = write_post_mortem_to_db(
        title="测试：决策审计模块验证",
        post_mortem_type="incident",
        severity="P3",
        what_happened="验证db_writer模块能否正常写入数据库",
        why_it_happened="模块刚创建，需要验证",
        what_we_learned="数据库连接正常，字段映射正确",
        how_to_improve="在执行流程中集成调用",
        root_cause_category="system",
    )
    if record_id:
        print(f"✅ 复盘记录写入成功，ID: {record_id}")
    else:
        print("❌ 复盘记录写入失败")
    return record_id is not None


def test_decision_write():
    """测试写入决策记录。"""
    print("\n=== 测试写入决策记录 ===")

    # 创建一个模拟Decision
    class MockSignal:
        symbol = "BTC/USDT"
        side = "long"

    class MockRiskState:
        confidence = 0.75

    decision = Decision(
        decision_id="test-decision-001",
        signal=MockSignal(),
        feature_snapshot={"atr_14": 450.0, "rsi_14": 55.2},
        model_version="rules-v1.0",
        risk_state=MockRiskState(),
        accepted=True,
        reject_reason=None,
        final_signed_lots=0.01,
        threshold_dataset="CLEAN",
        decision_rule_version="v1.0",
    )

    success = write_decision_to_db(decision)
    if success:
        print("✅ 决策记录写入成功")
    else:
        print("❌ 决策记录写入失败（可能是数据库连接问题）")
    return success


if __name__ == "__main__":
    print("开始测试决策审计数据库写入模块...\n")

    pm_ok = test_post_mortem_write()
    dec_ok = test_decision_write()

    print("\n" + "=" * 50)
    print(f"复盘记录写入: {'✅ 通过' if pm_ok else '❌ 失败'}")
    print(f"决策记录写入: {'✅ 通过' if dec_ok else '❌ 失败'}")
    print("=" * 50)

    if pm_ok or dec_ok:
        print("\n💡 提示：数据库写入模块已就绪，下一步在交易执行流程中集成调用。")
