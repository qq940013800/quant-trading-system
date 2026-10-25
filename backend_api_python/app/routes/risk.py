"""
风控与市场状态 API 路由

提供：
1. 持仓风险状态查询
2. 组合风险仪表盘数据
3. 市场状态识别结果
4. 风控告警列表
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from flask import jsonify, request
from app.openapi.blueprint import HumanBlueprint as Blueprint

from app.services.risk_engine import get_risk_engine
from app.services.market_regime import get_regime_detector
from app.utils.logger import get_logger

logger = get_logger(__name__)

risk_bp = Blueprint("risk", __name__)


@risk_bp.route("/positions", methods=["GET"])
def get_position_risks():
    """获取所有持仓的风险状态"""
    try:
        engine = get_risk_engine()
        positions = engine.get_position_risk_summary()
        return jsonify({
            "success": True,
            "data": positions,
            "count": len(positions),
        })
    except Exception as e:
        logger.error(f"获取持仓风险失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@risk_bp.route("/portfolio", methods=["GET"])
def get_portfolio_risk():
    """获取组合风险仪表盘数据"""
    try:
        engine = get_risk_engine()
        summary = engine.get_portfolio_risk_summary()
        return jsonify({
            "success": True,
            "data": summary,
        })
    except Exception as e:
        logger.error(f"获取组合风险失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@risk_bp.route("/regime", methods=["GET"])
def get_market_regime():
    """获取当前市场状态"""
    try:
        detector = get_regime_detector()
        summary = detector.get_current_regime_summary()
        return jsonify({
            "success": True,
            "data": summary,
        })
    except Exception as e:
        logger.error(f"获取市场状态失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@risk_bp.route("/alerts", methods=["GET"])
def get_risk_alerts():
    """获取风控告警列表"""
    try:
        engine = get_risk_engine()
        # 转换为可序列化格式
        alerts = []
        for alert in engine.alerts[-50:]:  # 最近50条
            alerts.append({
                "alert_id": alert.alert_id,
                "timestamp": alert.timestamp.isoformat(),
                "level": alert.level.value,
                "type": alert.alert_type,
                "message": alert.message,
                "position_id": alert.position_id,
                "symbol": alert.symbol,
                "action_required": alert.action_required,
            })
        return jsonify({
            "success": True,
            "data": alerts,
            "count": len(alerts),
        })
    except Exception as e:
        logger.error(f"获取风控告警失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@risk_bp.route("/let-profit-run/demo", methods=["GET"])
def let_profit_run_demo():
    """
    演示"截断亏损让利润奔跑"的完整6阶段工作流
    
    从入场到最终止盈的完整生命周期：
    阶段1: 入场 - 初始止损设置（2ATR）
    阶段2: 保本止损 - 达到0.5R后，止损移到入场价（保证不亏）
    阶段3: 追踪止损激活 - 达到1R后，开始追踪（2ATR距离）
    阶段4: 分批止盈 - 达到2R平50%，达到3R再平25%
    阶段5: 吊灯止损 - 3ATR距离，给趋势更多呼吸空间
    阶段6: 利润回吐保护 - 从峰值回撤30%就止盈剩余仓位
    """
    demo_data = {
        "strategy": "截断亏损让利润奔跑 - 完整工作流",
        "principle": "左尾截断 + 右尾暴露 + 高频小注 = 稳定盈利",
        "stages": [
            {
                "stage": 1,
                "name": "入场初始止损",
                "trigger": "开仓时",
                "action": "设置2ATR止损，单笔风险≤1%资金",
                "math": "止损距离 = 2 × ATR，仓位 = 风险金额 / 止损距离",
                "purpose": "限制单笔最大亏损，防止一次大亏毁掉系统",
                "color": "blue"
            },
            {
                "stage": 2,
                "name": "保本止损激活",
                "trigger": "达到0.5R（赚了0.5倍初始风险）",
                "action": "止损移到入场价 + 手续费缓冲",
                "math": "新止损价 = 入场价 × (1 + 0.02%)（多头）",
                "purpose": "消除'从盈利变亏损'的心理压力，这笔交易不可能亏钱了",
                "color": "cyan"
            },
            {
                "stage": 3,
                "name": "追踪止损激活",
                "trigger": "达到1R（赚了1倍初始风险）",
                "action": "启动追踪止损，距离2ATR",
                "math": "多头：新止损 = 最高价 - 2 × ATR（只上移不下移）",
                "purpose": "开始锁定利润，同时给趋势足够的呼吸空间",
                "color": "yellow"
            },
            {
                "stage": 4,
                "name": "分批止盈",
                "trigger": "达到2R平50%，达到3R再平25%",
                "action": "先落袋一部分，心理上有安全感",
                "math": "剩余仓位 = 100% → 50% → 25%",
                "purpose": "解决'怕利润回吐太早全部止盈'的心理问题，先拿一部分，剩下的继续奔跑",
                "color": "green"
            },
            {
                "stage": 5,
                "name": "吊灯止损（Chandelier Exit）",
                "trigger": "追踪止损激活后自动启用",
                "action": "切换到3ATR宽止损，给趋势更多空间",
                "math": "吊灯止损 = 最高价 - 3 × ATR（比普通追踪止损宽50%）",
                "purpose": "趋势跟踪的核心：不被正常回调洗出去，吃到完整趋势",
                "color": "purple"
            },
            {
                "stage": 6,
                "name": "利润回吐保护",
                "trigger": "利润从峰值回撤30%",
                "action": "止盈剩余仓位，锁定大部分利润",
                "math": "触发条件 = (峰值利润 - 当前利润) / 峰值利润 ≥ 30%",
                "purpose": "防止'坐过山车'：赚了1万最后只赚1千的痛苦",
                "color": "red"
            }
        ],
        "expected_outcome": {
            "win_scenario": "趋势顺利发展：赚3R以上，分批止盈后剩余仓位吃到大趋势",
            "loss_scenario": "判断错了：最多亏1R（初始止损），保本后不可能亏钱",
            "breakeven_scenario": "震荡市：保本止损触发，不赚不亏，白玩一场",
            "long_term_expectancy": "胜率40% × 平均赚3R - 败率60% × 平均亏1R = +0.6R/笔"
        },
        "institutions": [
            "Renaissance：严格的止损纪律，不允许人工干预",
            "Citadel：风控前置，订单发出前就拦截",
            "Millennium：PM动态资金分配，优胜劣汰",
            "AQR：趋势跟踪策略的标准配置"
        ],
        "common_mistakes": [
            "❌ 不止损 - 一次大亏回到解放前",
            "❌ 止损太宽 - 小亏变大亏",
            "❌ 太早全部止盈 - 错过大趋势",
            "❌ 追踪止损太近 - 被正常回调洗出去",
            "❌ 没有保本止损 - 从盈利变亏损最痛苦",
            "❌ 情绪化交易 - 该扛的时候扛，该砍的时候砍反了"
        ]
    }
    return jsonify({"success": True, "data": demo_data})
