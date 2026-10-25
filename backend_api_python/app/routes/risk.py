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
from app.services.market_structure import get_structure_detector
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


@risk_bp.route("/structure", methods=["GET"])
def get_market_structure():
    """
    获取市场结构识别结果（L2）
    
    包含：
    - 当前趋势方向
    - 最近的摆动高低点
    - 最近的结构事件（BOS/CHoCH）
    - 关键支撑阻力位
    """
    try:
        detector = get_structure_detector()
        summary = detector.get_structure_summary()
        return jsonify({"success": True, "data": summary})
    except Exception as e:
        logger.error(f"获取市场结构失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@risk_bp.route("/structure/demo", methods=["GET"])
def market_structure_demo():
    """市场结构识别演示数据"""
    demo_data = {
        "title": "市场结构识别（L2）— 第一性原理",
        "principle": "价格不是随机走的，是沿着高低点结构前进的",
        "core_concepts": [
            {
                "name": "摆动高低点 (Swing High/Low)",
                "definition": "连续N根K线中的最高/最低点，是市场结构的基本积木",
                "why": "高低点是多空双方博弈留下的痕迹，是市场情绪的可视化"
            },
            {
                "name": "BOS (Break of Structure) 结构突破",
                "definition": "趋势延续：突破前一个同向结构点，说明趋势还在继续",
                "why": "聪明钱沿着结构方向加仓，突破确认趋势健康"
            },
            {
                "name": "CHoCH (Change of Character) 特征变化",
                "definition": "趋势反转：突破前一个反向结构点，说明趋势可能要变了",
                "why": "是最早的反转信号，比技术指标早很多"
            },
            {
                "name": "支撑阻力位 (Support/Resistance)",
                "definition": "多次测试过的价格位，价格到这里容易反弹或回落",
                "why": "这些位置聚集了大量订单，是机构的攻防阵地"
            }
        ],
        "trend_phases": {
            "accumulation": "积累阶段 — 横盘震荡，聪明钱悄悄建仓",
            "markup": "上涨阶段 — 趋势明确，顺势做多",
            "distribution": "分配阶段 — 高位震荡，聪明钱悄悄出货",
            "markdown": "下跌阶段 — 趋势明确，顺势做空"
        },
        "top_firm_practice": [
            "ICT (Inner Circle Trader)：Smart Money Concepts 核心框架",
            "Wyckoff Method：积累/趋势/分配三阶段理论",
            "机构交易员：不先看指标，先看结构位置",
            "价格行为交易：结构是道，指标是术"
        ],
        "common_mistakes": [
            "❌ 不看结构，只看指标 — 指标滞后于结构",
            "❌ 把震荡当趋势 — 在区间中间追涨杀跌",
            "❌ 错过CHoCH信号 — 反转了还在顺势交易",
            "❌ 忽略支撑阻力 — 在关键位逆势开仓",
            "❌ 结构识别太主观 — 同样的图两个人看出两个样"
        ]
    }
    return jsonify({"success": True, "data": demo_data})
