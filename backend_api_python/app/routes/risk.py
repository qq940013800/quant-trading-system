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
