"""
交易成本分析与数据治理 API 路由

提供：
1. TCA交易成本分析
2. 数据质量检查
3. 回测vs实盘差距诊断
"""
from __future__ import annotations

from flask import jsonify, request
from app.openapi.blueprint import HumanBlueprint as Blueprint

from app.services.trading_cost_analysis import get_tca_analyzer, OrderType
from app.services.data_governance import get_data_governance
from app.utils.logger import get_logger

logger = get_logger(__name__)

tca_bp = Blueprint("tca", __name__)


@tca_bp.route("/estimate-cost", methods=["POST"])
def estimate_order_cost():
    """估算订单交易成本"""
    try:
        data = request.get_json()
        analyzer = get_tca_analyzer()

        order = analyzer.estimate_order_cost(
            symbol=data.get("symbol", "BTCUSDT"),
            side=data.get("side", "buy"),
            quantity=float(data.get("quantity", 1.0)),
            price=float(data.get("price", 50000.0)),
            order_type=OrderType(data.get("order_type", "market")),
            volatility=float(data.get("volatility", 0.02)),
        )

        return jsonify({
            "success": True,
            "data": {
                "order_id": order.order_id,
                "total_cost": order.total_cost,
                "cost_bps": order.cost_bps,
                "breakdown": {
                    "commission": order.commission,
                    "spread": order.spread_cost,
                    "slippage": order.slippage_cost,
                    "market_impact": order.market_impact,
                    "timing_risk": order.timing_risk,
                },
            },
        })
    except Exception as e:
        logger.error(f"成本估算失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@tca_bp.route("/cost-summary", methods=["GET"])
def get_cost_summary():
    """获取成本汇总统计"""
    try:
        analyzer = get_tca_analyzer()
        summary = analyzer.get_cost_summary()
        return jsonify({"success": True, "data": summary})
    except Exception as e:
        logger.error(f"获取成本汇总失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@tca_bp.route("/diagnose-gap", methods=["POST"])
def diagnose_backtest_gap():
    """诊断回测和实盘的收益差距"""
    try:
        data = request.get_json()
        analyzer = get_tca_analyzer()

        result = analyzer.diagnose_backtest_vs_live_gap(
            backtest_returns=float(data.get("backtest_returns", 0.5)),
            live_returns=float(data.get("live_returns", 0.1)),
            total_trades=int(data.get("total_trades", 100)),
        )

        return jsonify({"success": True, "data": result})
    except Exception as e:
        logger.error(f"差距诊断失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@tca_bp.route("/data-quality-check", methods=["POST"])
def check_data_quality():
    """检查数据质量"""
    try:
        data = request.get_json()
        governance = get_data_governance()

        report = governance.check_quality(
            dataset_name=data.get("dataset_name", "unknown"),
            data=data.get("data", []),
        )

        return jsonify({
            "success": True,
            "data": {
                "quality_score": report.quality_score,
                "quality_level": report.quality_level.value,
                "dimensions": {
                    "completeness": report.completeness_score,
                    "accuracy": report.accuracy_score,
                    "consistency": report.consistency_score,
                    "timeliness": report.timeliness_score,
                    "uniqueness": report.uniqueness_score,
                },
                "issue_count": len(report.issues),
                "recommendations": report.recommendations,
            },
        })
    except Exception as e:
        logger.error(f"数据质量检查失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
