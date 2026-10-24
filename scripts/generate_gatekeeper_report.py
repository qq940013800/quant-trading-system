# -*- coding: utf-8 -*-
"""守门员报告生成器 —— 运行验证层检查，输出JSON报告。

使用方式：
    python scripts/generate_gatekeeper_report.py

输出：
    dashboard_data/gatekeeper_report.json
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

# 把项目根目录加入路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.integration.bridge import QuantDingerBridge, BridgeConfig
from core.integration.gatekeeper import Gatekeeper

# QuantDinger Agent Token（只允许读+回测，只允许模拟交易）
AGENT_TOKEN = 'qd_agent_wEJoyJYDxyLpHzgYwzlRJxIjuEKtPT2zUcRW4nj1yeI'


def generate_report() -> dict:
    """生成守门员报告。"""
    # 配置桥接模块，带上auth_token
    bridge_config = BridgeConfig(auth_token=AGENT_TOKEN)
    bridge = QuantDingerBridge(config=bridge_config)
    gate = Gatekeeper(bridge=bridge)
    summary = gate.run_full_gate()

    # 转换成JSON可序列化的格式
    report = {
        "timestamp": datetime.now().isoformat(),
        "bridge_health": {
            "reachable": summary.bridge_health.reachable,
            "status": summary.bridge_health.status,
            "latency_ms": summary.bridge_health.latency_ms,
            "error": summary.bridge_health.error,
        },
        "summary": {
            "total_strategies": summary.total_strategies,
            "pass_count": summary.pass_count,
            "warn_count": summary.warn_count,
            "downgrade_count": summary.downgrade_count,
            "reject_count": summary.reject_count,
            "pass_rate": summary.pass_rate,
        },
        "strategies": [],
    }

    for result in summary.results:
        report["strategies"].append({
            "strategy_id": result.strategy_id,
            "strategy_name": result.strategy_name,
            "can_deploy": result.can_deploy,
            "recommended_action": result.recommended_action,
            "overall_decision": result.gate_report.overall_decision.value,
            "findings": [
                {
                    "check_name": f.check_name,
                    "decision": f.decision.value,
                    "score": f.score,
                    "message": f.message,
                }
                for f in result.gate_report.findings
            ],
        })

    return report


def main():
    """主函数。"""
    print("=" * 60)
    print("守门员报告生成器")
    print("=" * 60)

    report = generate_report()

    # 输出目录
    output_dir = project_root / "dashboard_data"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "gatekeeper_report.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"报告已生成: {output_file}")
    print()
    print(f"桥接健康: {'✅ 可达' if report['bridge_health']['reachable'] else '❌ 不可达'}")
    print(f"策略总数: {report['summary']['total_strategies']}")
    print(f"通过率: {report['summary']['pass_rate']:.1%}")
    print()
    print(f"✅ PASS: {report['summary']['pass_count']}")
    print(f"⚠️  WARN: {report['summary']['warn_count']}")
    print(f"⬇️  DOWNGRADE: {report['summary']['downgrade_count']}")
    print(f"❌ REJECT: {report['summary']['reject_count']}")
    print()

    for s in report["strategies"]:
        emoji = {"pass": "✅", "warn": "⚠️", "downgrade": "⬇️", "reject": "❌"}.get(s["overall_decision"], "❓")
        print(f"{emoji} {s['strategy_name']}: {s['overall_decision']}")

    print()
    print("=" * 60)


if __name__ == "__main__":
    main()
