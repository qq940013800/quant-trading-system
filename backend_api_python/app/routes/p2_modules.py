"""
P2模块 API路由：拥挤度监控 + 可观测性 + CI/CD
"""
from __future__ import annotations

from flask import jsonify, request
from app.openapi.blueprint import HumanBlueprint as Blueprint

from app.services.crowding_monitor import get_crowding_monitor
from app.services.observability import get_observability
from app.services.cicd import get_cicd_service
from app.utils.logger import get_logger

logger = get_logger(__name__)

p2_bp = Blueprint("p2_modules", __name__)


# ========== 策略拥挤度监控 ==========

@p2_bp.route("/crowding/summary", methods=["GET"])
def get_crowding_summary():
    """获取拥挤度汇总"""
    try:
        monitor = get_crowding_monitor()
        summary = monitor.get_crowding_summary()
        return jsonify({"success": True, "data": summary})
    except Exception as e:
        logger.error(f"获取拥挤度汇总失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@p2_bp.route("/crowding/strategies", methods=["GET"])
def get_strategies_crowding():
    """获取所有策略拥挤度状态"""
    try:
        monitor = get_crowding_monitor()
        strategies = monitor.get_all_strategies_status()
        return jsonify({"success": True, "data": strategies})
    except Exception as e:
        logger.error(f"获取策略拥挤度失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@p2_bp.route("/crowding/update", methods=["POST"])
def update_crowding_metrics():
    """更新拥挤度指标"""
    try:
        data = request.get_json()
        monitor = get_crowding_monitor()

        metrics = monitor.update_metrics(
            strategy_name=data.get("strategy_name", "unknown"),
            symbol=data.get("symbol", "BTCUSDT"),
            signal_correlation=float(data.get("signal_correlation", 0)),
            transaction_cost_change=float(data.get("transaction_cost_change", 0)),
            alpha_decay=float(data.get("alpha_decay", 0)),
            sharpe_trend=float(data.get("sharpe_trend", 0)),
        )

        return jsonify({
            "success": True,
            "data": {
                "crowding_score": metrics.crowding_score,
                "crowding_level": metrics.crowding_level.value,
                "recommendation": metrics.recommendation,
            },
        })
    except Exception as e:
        logger.error(f"更新拥挤度指标失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ========== 可观测性与监控告警 ==========

@p2_bp.route("/observability/golden-signals", methods=["GET"])
def get_golden_signals():
    """获取黄金四指标"""
    try:
        obs = get_observability()
        signals = obs.get_golden_signals()
        return jsonify({"success": True, "data": signals})
    except Exception as e:
        logger.error(f"获取黄金指标失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@p2_bp.route("/observability/alerts", methods=["GET"])
def get_alerts():
    """获取告警列表"""
    try:
        obs = get_observability()
        limit = int(request.args.get("limit", 20))
        alerts = obs.get_recent_alerts(limit)
        return jsonify({"success": True, "data": alerts})
    except Exception as e:
        logger.error(f"获取告警失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@p2_bp.route("/observability/summary", methods=["GET"])
def get_observability_summary():
    """获取可观测性汇总"""
    try:
        obs = get_observability()
        summary = obs.get_alert_summary()
        return jsonify({"success": True, "data": summary})
    except Exception as e:
        logger.error(f"获取可观测性汇总失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ========== CI/CD与部署运维 ==========

@p2_bp.route("/cicd/status", methods=["GET"])
def get_cicd_status():
    """获取CI/CD状态"""
    try:
        cicd = get_cicd_service()
        status = cicd.get_current_status()
        return jsonify({"success": True, "data": status})
    except Exception as e:
        logger.error(f"获取CI/CD状态失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@p2_bp.route("/cicd/deployments", methods=["GET"])
def get_deployment_history():
    """获取部署历史"""
    try:
        cicd = get_cicd_service()
        limit = int(request.args.get("limit", 20))
        history = cicd.get_deployment_history(limit)
        return jsonify({"success": True, "data": history})
    except Exception as e:
        logger.error(f"获取部署历史失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
