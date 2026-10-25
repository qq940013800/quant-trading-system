"""
P2模块 API路由：拥挤度监控 + 可观测性 + CI/CD
"""
from __future__ import annotations

from flask import jsonify, request
from app.openapi.blueprint import HumanBlueprint as Blueprint

from app.services.crowding_monitor import get_crowding_monitor
from app.services.observability import get_observability
from app.services.cicd import get_cicd_service
from app.services.websocket_gateway import get_websocket_gateway
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


# ========== WebSocket实时网关 ==========

@p2_bp.route("/websocket/status", methods=["GET"])
def get_websocket_status():
    """获取WebSocket网关状态"""
    try:
        gateway = get_websocket_gateway()
        status = gateway.get_gateway_status()
        return jsonify({"success": True, "data": status})
    except Exception as e:
        logger.error(f"获取WebSocket状态失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@p2_bp.route("/websocket/degradation", methods=["GET"])
def get_degradation_info():
    """获取降级策略信息"""
    try:
        gateway = get_websocket_gateway()
        info = gateway.get_degradation_info()
        return jsonify({"success": True, "data": info})
    except Exception as e:
        logger.error(f"获取降级策略失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@p2_bp.route("/websocket/demo", methods=["GET"])
def websocket_gateway_demo():
    """WebSocket实时网关演示"""
    demo_data = {
        "title": "私有数据WebSocket实时网关",
        "principle": "持仓、订单、策略状态是私有数据，不能靠轮询（太慢、太浪费）",
        "core_idea": "事件驱动：有变化才推，没变化不推",
        "channels": [
            {
                "name": "positions",
                "display_name": "持仓更新",
                "what_pushes": "持仓盈亏变化、仓位变动、止损触发",
                "frequency": "实时（毫秒级）",
                "why_needed": "风控要实时响应，不能等5秒轮询"
            },
            {
                "name": "orders",
                "display_name": "订单状态变更",
                "what_pushes": "订单提交、部分成交、全部成交、撤单",
                "frequency": "实时",
                "why_needed": "用户要知道订单有没有成交，不能刷新页面"
            },
            {
                "name": "strategy",
                "display_name": "策略运行状态",
                "what_pushes": "策略启动、停止、信号触发、异常告警",
                "frequency": "实时",
                "why_needed": "策略出问题要第一时间知道"
            },
            {
                "name": "risk_alerts",
                "display_name": "风控告警",
                "what_pushes": "止损触发、回撤预警、持仓超限",
                "frequency": "实时（最高优先级）",
                "why_needed": "风控是生死线，必须秒级响应"
            }
        ],
        "degradation_strategy": {
            "primary": "WebSocket实时推送",
            "fallback": "轮询（5秒间隔）",
            "auto_switch": True,
            "reconnect": "自动重连3次，间隔3秒",
            "grace_period": "断开后3秒内不切轮询，可能只是网络抖动"
        },
        "institutions": [
            "Jane Street：毫秒级实时行情推送，延迟敏感",
            "Citadel：私有数据实时推送，风控实时响应",
            "Two Sigma：Pub/Sub架构，数据变更自动广播",
            "Binance/OKX：标准WebSocket API，行业标准"
        ],
        "common_mistakes": [
            "❌ 所有数据都用WebSocket —— 浪费资源，低频数据用轮询就行",
            "❌ 没有降级方案 —— WebSocket断了页面就死了",
            "❌ 没有心跳检测 —— 连接断了不知道，假死状态",
            "❌ 没有鉴权 —— 私有数据谁都能看，安全漏洞",
            "❌ 推送太频繁 —— 客户端处理不过来，反而更慢"
        ]
    }
    return jsonify({"success": True, "data": demo_data})
