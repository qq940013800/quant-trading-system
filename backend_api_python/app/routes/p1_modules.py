"""
高可用、交易日志、安全合规 API 路由
"""
from __future__ import annotations

from flask import jsonify, request
from app.openapi.blueprint import HumanBlueprint as Blueprint

from app.services.business_continuity import get_business_continuity, HealthStatus
from app.services.trade_journal import get_trade_journal
from app.services.security import get_security_service
from app.services.strategy_matcher import get_strategy_matcher
from app.utils.logger import get_logger

logger = get_logger(__name__)

p1_bp = Blueprint("p1_modules", __name__)


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


# ========== 策略匹配引擎 ==========

@p1_bp.route("/strategy-matcher/summary", methods=["GET"])
def get_strategy_match_summary():
    """获取策略匹配结果摘要"""
    try:
        matcher = get_strategy_matcher()
        summary = matcher.get_match_summary()
        return jsonify({"success": True, "data": summary})
    except Exception as e:
        logger.error(f"获取策略匹配摘要失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@p1_bp.route("/strategy-matcher/match", methods=["POST"])
def run_strategy_match():
    """运行策略匹配（根据当前市场状态推荐策略组合）"""
    try:
        data = request.get_json() or {}
        regime = data.get("regime", "range")
        
        matcher = get_strategy_matcher()
        from app.services.strategy_matcher import MarketRegimeType
        
        # 转换枚举
        try:
            regime_enum = MarketRegimeType(regime)
        except:
            regime_enum = MarketRegimeType.RANGE
        
        matches = matcher.match_strategies(regime_enum)
        
        return jsonify({
            "success": True,
            "data": {
                "current_regime": regime,
                "matches": [
                    {
                        "strategy_id": m.strategy_id,
                        "strategy_name": m.strategy_name,
                        "match_score": m.match_score,
                        "allocation_pct": m.allocation_pct,
                        "reason": m.reason
                    }
                    for m in matches
                ]
            }
        })
    except Exception as e:
        logger.error(f"策略匹配失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@p1_bp.route("/strategy-matcher/demo", methods=["GET"])
def strategy_matcher_demo():
    """策略匹配引擎演示"""
    demo_data = {
        "title": "策略匹配规则引擎 — Millennium模式",
        "principle": "没有万能策略，只有适合当前市场状态的策略",
        "core_idea": "根据路况自动选车：趋势市用趋势策略，震荡市用均值回归策略",
        "strategy_types": [
            {
                "type": "trend_following",
                "name": "趋势跟踪",
                "best_regimes": "强趋势上涨/下跌",
                "worst_regimes": "震荡市、危机市",
                "logic": "跟着趋势走，涨多了还会涨，跌多了还会跌"
            },
            {
                "type": "mean_reversion",
                "name": "均值回归",
                "best_regimes": "震荡市",
                "worst_regimes": "强趋势市",
                "logic": "涨多了会跌，跌多了会涨，高抛低吸"
            },
            {
                "type": "breakout",
                "name": "突破交易",
                "best_regimes": "趋势启动期、区间突破",
                "worst_regimes": "阴跌阴涨",
                "logic": "突破关键位后会有大行情，追突破"
            },
            {
                "type": "arbitrage",
                "name": "套利",
                "best_regimes": "所有状态（尤其是危机）",
                "worst_regimes": "无",
                "logic": "找定价错误的机会，低风险稳定收益"
            }
        ],
        "matching_logic": [
            "1. 输入：当前市场状态（趋势/震荡/危机）",
            "2. 计算每个策略和市场状态的匹配度（0~1）",
            "3. 根据匹配度归一化分配资金比例",
            "4. 冷却期60分钟，防止策略频繁切换（防抖动）",
            "5. 绩效得分高的策略获得更多资金（优胜劣汰）"
        ],
        "institutions": [
            "Millennium Management：PM动态资金分配，优胜劣汰的典范",
            "Renaissance：多策略集成，根据状态自动切换权重",
            "Two Sigma：策略组合优化，风险平价分配",
            "Citadel：实时策略调度，根据市场状态调整"
        ],
        "common_mistakes": [
            "❌ 只用一个策略 —— 策略有生命周期，总有失效的时候",
            "❌ 不看市场状态 —— 震荡市做趋势，来回打脸",
            "❌ 频繁切换策略 —— 一天换8次，手续费都亏死",
            "❌ 平均分配资金 —— 好策略和差策略拿一样多的钱",
            "❌ 不看绩效 —— 差策略一直在亏钱还在给它钱"
        ]
    }
    return jsonify({"success": True, "data": demo_data})
