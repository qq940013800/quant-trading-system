"""
高可用、交易日志、安全合规 API 路由
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.services.business_continuity import get_business_continuity, HealthStatus
from app.services.trade_journal import get_trade_journal
from app.services.security import get_security_service
from app.utils.logger import get_logger

logger = get_logger(__name__)

p1_bp = Blueprint("p1_modules", __name__, url_prefix="/api/p1")


# ========== 高可用与灾备 ==========

@p1_bp.route("/health", methods=["GET"])
def get_system_health():
    """获取系统健康状态"""
    try:
        bc = get_business_continuity()
        summary = bc.get_system_health_summary()
        return jsonify({"success": True, "data": summary})
    except Exception as e:
        logger.error(f"获取系统健康失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@p1_bp.route("/health/report", methods=["POST"])
def report_service_health():
    """上报服务健康状态"""
    try:
        data = request.get_json()
        bc = get_business_continuity()

        bc.report_health(
            service_name=data.get("service_name", "unknown"),
            status=HealthStatus(data.get("status", "healthy")),
            response_time_ms=float(data.get("response_time_ms", 0)),
            error_message=data.get("error_message", ""),
        )

        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"上报健康状态失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@p1_bp.route("/failures", methods=["GET"])
def get_failure_history():
    """获取故障历史"""
    try:
        bc = get_business_continuity()
        limit = int(request.args.get("limit", 50))
        history = bc.get_failure_history(limit)
        return jsonify({"success": True, "data": history})
    except Exception as e:
        logger.error(f"获取故障历史失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ========== 交易日志与绩效归因 ==========

@p1_bp.route("/journal/analyze", methods=["GET"])
def analyze_performance():
    """绩效归因分析"""
    try:
        journal = get_trade_journal()
        days = int(request.args.get("days", 30))
        strategy_id = request.args.get("strategy_id")

        result = journal.analyze_performance(
            strategy_id=int(strategy_id) if strategy_id else None,
            days=days,
        )

        return jsonify({
            "success": True,
            "data": {
                "period": result.period,
                "total_trades": result.total_trades,
                "win_rate": result.win_rate,
                "total_pnl": result.total_pnl,
                "profit_factor": result.profit_factor,
                "expectancy": result.expectancy,
                "behavioral_biases": result.behavioral_biases,
                "recommendations": result.recommendations,
            },
        })
    except Exception as e:
        logger.error(f"绩效分析失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ========== 安全与合规 ==========

@p1_bp.route("/security/summary", methods=["GET"])
def get_security_summary():
    """获取安全状态总览"""
    try:
        security = get_security_service()
        summary = security.get_security_summary()
        return jsonify({"success": True, "data": summary})
    except Exception as e:
        logger.error(f"获取安全状态失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@p1_bp.route("/security/alerts", methods=["GET"])
def get_security_alerts():
    """获取安全告警"""
    try:
        security = get_security_service()
        limit = int(request.args.get("limit", 20))
        alerts = security.get_recent_alerts(limit)
        return jsonify({"success": True, "data": alerts})
    except Exception as e:
        logger.error(f"获取安全告警失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
