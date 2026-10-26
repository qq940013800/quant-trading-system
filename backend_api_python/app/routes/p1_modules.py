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
from app.services.position_sizing import get_sizing_engine, TradeSetup, SizingMethod
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


# ========== 仓位管理引擎 ==========

@p1_bp.route("/position-sizing/summary", methods=["GET"])
def get_position_sizing_summary():
    """获取仓位配置摘要"""
    try:
        engine = get_sizing_engine()
        summary = engine.get_sizing_summary()
        return jsonify({"success": True, "data": summary})
    except Exception as e:
        logger.error(f"获取仓位配置失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@p1_bp.route("/position-sizing/calculate", methods=["POST"])
def calculate_position_size():
    """计算建议仓位大小"""
    try:
        data = request.get_json() or {}
        
        setup = TradeSetup(
            symbol=data.get("symbol", "BTCUSDT"),
            side=data.get("side", "long"),
            entry_price=float(data.get("entry_price", 100000)),
            stop_loss_price=float(data.get("stop_loss_price", 99000)),
            atr=float(data.get("atr", 500)),
            historical_volatility=float(data.get("volatility", 30)),
            win_rate=float(data.get("win_rate", 0.4)),
            avg_win_loss_ratio=float(data.get("win_loss_ratio", 2.0))
        )
        
        engine = get_sizing_engine()
        result = engine.calculate_position_size(setup)
        
        return jsonify({
            "success": True,
            "data": {
                "position_size": result.position_size,
                "position_value": result.position_value,
                "position_pct": result.position_pct,
                "risk_amount": result.risk_amount,
                "risk_pct": result.risk_pct,
                "method_used": result.method_used
            }
        })
    except Exception as e:
        logger.error(f"仓位计算失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@p1_bp.route("/position-sizing/demo", methods=["GET"])
def position_sizing_demo():
    """仓位管理引擎演示"""
    demo_data = {
        "title": "仓位管理引擎 — 第一性原理",
        "principle": "仓位管理比选股重要100倍，再好的策略，仓位不对也白搭",
        "core_idea": "截断亏损靠止损，让利润奔跑靠仓位",
        "methods": [
            {
                "name": "固定风险法",
                "how": "每笔交易只冒总资金1%的风险，止损亏完就走",
                "best_for": "新手默认，最简单最安全",
                "pros": "简单、可预测、不会一次大亏",
                "cons": "不考虑波动率，波动大的时候风险其实更大"
            },
            {
                "name": "波动率目标法",
                "how": "波动大的少做，波动小的多做，保持风险恒定",
                "best_for": "多策略组合，想要稳定风险敞口",
                "pros": "风险恒定，不会因为波动突然变大而爆仓",
                "cons": "需要准确的波动率估计"
            },
            {
                "name": "分数Kelly法",
                "how": "根据胜率和盈亏比计算最优仓位，用1/4 Kelly更安全",
                "best_for": "有历史数据，知道策略的胜率和盈亏比",
                "pros": "理论最优，长期收益最大化",
                "cons": "对参数敏感，估计错了就会过度下注"
            }
        ],
        "golden_rules": [
            "1. 单笔风险永远不超过总资金的1%——一次亏1%，要亏100次才爆仓",
            "2. 用分数Kelly（1/4），不用全Kelly——全凯利会心理崩溃",
            "3. 回撤大了自动减仓——回撤10%仓位打9折，回撤20%打8折",
            "4. 永远不要加仓摊平亏损——亏了就是错了，错了就认",
            "5. 仓位是按风险算的，不是按资金算的——止损距离远的少做"
        ],
        "institutions": [
            "Renaissance：每个策略的风险贡献独立计算，严格控制",
            "Two Sigma：风险平价分配，不是等权分配",
            "Citadel：实时仓位调整，根据波动率变化动态调整",
            "Millennium：PM对自己的仓位负责，公司层面风控兜底"
        ],
        "common_mistakes": [
            "❌ 满仓梭哈 —— 一次判断错了就没了",
            "❌ 亏损加仓摊平 —— 越亏越加，越加越亏",
            "❌ 不设止损 —— 小亏变大亏，一次回到解放前",
            "❌ 仓位随机 —— 看心情开仓，想做多少做多少",
            "❌ 用全Kelly —— 理论最优但实战会亏到怀疑人生",
            "❌ 回撤了不减仓 —— 越亏越做，越做越亏"
        ]
    }
    return jsonify({"success": True, "data": demo_data})


# ========== 数据桥接：L1+L2综合市场分析 ==========

@p1_bp.route("/market-analysis/demo", methods=["GET"])
def market_analysis_demo():
    """
    市场综合分析演示（用模拟数据跑通L1+L2流程）
    
    第一性原理：
    - L1市场状态 + L2市场结构 = 完整的市场判断
    - 没有数据的时候先用演示数据跑通流程
    - 等接入真实K线数据后，直接替换数据源
    """
    try:
        from app.services.data_bridge import get_data_bridge
        bridge = get_data_bridge()
        
        symbol = request.args.get("symbol", "BTCUSDT")
        result = bridge.analyze_with_demo_data(symbol)
        
        return jsonify({
            "success": True,
            "data": {
                "symbol": result.symbol,
                "current_price": round(result.current_price, 2),
                "timestamp": result.timestamp.isoformat(),
                
                # L1 市场状态
                "regime": result.regime,
                "regime_confidence": round(result.regime_confidence, 3),
                "regime_features": {k: round(v, 4) for k, v in result.regime_features.items()},
                
                # L2 市场结构
                "structure_bias": result.structure_bias,
                "support_levels": [round(s, 2) for s in result.support_levels],
                "resistance_levels": [round(r, 2) for r in result.resistance_levels],
                "recent_swing_high": round(result.recent_swing_high, 2) if result.recent_swing_high else None,
                "recent_swing_low": round(result.recent_swing_low, 2) if result.recent_swing_low else None,
                
                # 技术指标
                "atr": round(result.atr, 2),
                "volatility": round(result.volatility, 4),
                "trend_strength": round(result.trend_strength, 4),
                
                # 说明
                "note": "演示数据，接入真实K线后自动切换"
            }
        })
    except Exception as e:
        logger.error(f"市场分析演示失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ========== L3/L4/L5 五层市场识别 ==========

@p1_bp.route("/market-layers/summary", methods=["GET"])
def market_layers_summary():
    """五层市场识别架构总览"""
    layers = [
        {"level": "L1", "name": "市场状态识别", "module": "market_regime.py",
         "status": "✅ 已完成", "desc": "趋势市/震荡市/危机市，决定用什么策略"},
        {"level": "L2", "name": "市场结构识别", "module": "market_structure.py",
         "status": "✅ 已完成", "desc": "支撑阻力/高低点/结构突破，决定在哪里入场止损"},
        {"level": "L3", "name": "市场趋势识别", "module": "market_trend.py",
         "status": "✅ 已完成", "desc": "趋势方向/强度/阶段，决定方向和仓位"},
        {"level": "L4", "name": "价格行为识别", "module": "price_action.py",
         "status": "✅ 已完成", "desc": "吞没/针形线/内包线，决定精确入场时机"},
        {"level": "L5", "name": "K线形态识别", "module": "candlestick_patterns.py",
         "status": "✅ 已完成", "desc": "早晨之星/黄昏之星/三只乌鸦，决定最终入场信号"},
    ]
    return jsonify({"success": True, "data": {
        "layers": layers, "total": len(layers),
        "core_principle": "从上到下过滤，多层共振才入场"
    }})


@p1_bp.route("/market-layers/demo", methods=["GET"])
def market_layers_demo():
    """五层市场识别演示（综合分析器）"""
    try:
        from app.services.comprehensive_market_analyzer import ComprehensiveMarketAnalyzer
        import random
        
        analyzer = ComprehensiveMarketAnalyzer()
        
        # 生成演示K线数据
        demo_klines = []
        base_price = 80000.0
        for i in range(100):
            change = random.uniform(-0.015, 0.015)
            o = base_price
            c = base_price * (1 + change)
            h = max(o, c) * 1.003
            l = min(o, c) * 0.997
            v = random.uniform(500, 2000)
            demo_klines.append({"open": o, "high": h, "low": l, "close": c, "volume": v})
            base_price = c
        
        result = analyzer.analyze(demo_klines)
        summary = analyzer.get_summary(result)
        return jsonify({"success": True, "data": summary})
    except Exception as e:
        logger.error(f"五层市场识别演示失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ========== 策略优化引擎 ==========

@p1_bp.route("/optimizer/status", methods=["GET"])
def optimizer_status():
    """策略优化引擎状态"""
    try:
        from app.services.strategy_optimizer import StrategyOptimizationEngine
        engine = StrategyOptimizationEngine()
        status = engine.get_engine_status()
        return jsonify({"success": True, "data": status})
    except Exception as e:
        logger.error(f"优化引擎状态失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@p1_bp.route("/optimizer/factors", methods=["GET"])
def optimizer_factors():
    """因子库列表"""
    try:
        from app.services.factor_library import FactorLibrary
        lib = FactorLibrary()
        factors = lib.get_factor_summary()
        return jsonify({"success": True, "data": {
            "factors": factors,
            "total": len(factors),
            "categories": list(set(f["category"] for f in factors))
        }})
    except Exception as e:
        logger.error(f"因子库列表失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@p1_bp.route("/optimizer/history", methods=["GET"])
def optimizer_history():
    """优化历史"""
    try:
        from app.services.strategy_optimizer import StrategyOptimizationEngine
        engine = StrategyOptimizationEngine()
        history = engine.get_optimization_history()
        return jsonify({"success": True, "data": {"history": history, "total": len(history)}})
    except Exception as e:
        logger.error(f"优化历史失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ========== 过拟合防御 ==========

@p1_bp.route("/overfitting/status", methods=["GET"])
def overfitting_status():
    """过拟合防御状态"""
    try:
        from app.services.overfitting_defense import get_overfitting_defense
        defense = get_overfitting_defense()
        status = defense.get_defense_summary()
        return jsonify({"success": True, "data": status})
    except Exception as e:
        logger.error(f"过拟合防御状态失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ========== 策略健康度 ==========

@p1_bp.route("/strategy-health/summary", methods=["GET"])
def strategy_health_summary():
    """策略健康度摘要"""
    try:
        from app.services.strategy_health import health_monitor, StrategyHealth
        demo_strategies = [
            StrategyHealth(
                strategy_id="1", strategy_name="趋势跟踪策略",
                status="active", health_score=85.0,
                recent_sharpe=1.8, recent_drawdown=8.0, win_rate=45.0, trade_count=120,
                sharpe_decay=0.1, performance_trend="stable",
                recommendation="继续运行", next_review="2026-11-01"
            ),
            StrategyHealth(
                strategy_id="2", strategy_name="均值回归策略",
                status="watch", health_score=55.0,
                recent_sharpe=0.9, recent_drawdown=15.0, win_rate=52.0, trade_count=200,
                sharpe_decay=0.35, performance_trend="declining",
                recommendation="减少仓位，观察", next_review="2026-10-28"
            ),
            StrategyHealth(
                strategy_id="3", strategy_name="突破交易策略",
                status="active", health_score=90.0,
                recent_sharpe=2.1, recent_drawdown=6.0, win_rate=38.0, trade_count=80,
                sharpe_decay=0.05, performance_trend="improving",
                recommendation="可加仓", next_review="2026-11-05"
            ),
        ]
        summary = health_monitor.get_portfolio_overview(demo_strategies)
        return jsonify({"success": True, "data": summary})
    except Exception as e:
        logger.error(f"策略健康度失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
