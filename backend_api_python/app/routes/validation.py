"""AI验证层API路由。

诚实展示契约（与前端空态隔离一致）：
- 未接实时探针/持久化事件源的模块，details 置空、status 标 pending，
  不回填编造的指标数字（PBO/DSR/准确率/形态数/滑点偏差/策略池计数/延迟等）。
- 审计日志只回持久化决策/风控事件；当前无对应事件表时返回空列表，不生成模拟留痕。
- 压力测试为内置演示情景模板，显式标记 data_kind='demo'；前端仅在
  data_kind=='real'（基于真实持仓/权益完成冲击测算）时才渲染。
"""
from flask import jsonify, request
from app.openapi.blueprint import HumanBlueprint as Blueprint
from datetime import datetime

validation_bp = Blueprint('validation', __name__)


# 验证模块能力清单。status=registered/pending 表示模块已登记但实时探针
# 尚未接入；details 仅在后端有真实度量来源时回填，缺源一律置空。
_MODULE_REGISTRY = [
    ("overfitting_defense", "过拟合防御系统 (PBO/DSR/CPCV)", "high"),
    ("lookahead_bias", "前视偏差自动检测器", "medium"),
    ("drift_monitor", "策略漂移监控（数据+概念）", "medium"),
    ("ab_testing", "AB测试框架（统计显著性）", "medium"),
    ("explainability", "决策可解释性（8层追溯）", "medium"),
    ("stop_loss", "四层止损体系", "high"),
    ("market_structure", "BOS/CHoCH市场结构识别", "low"),
    ("candlestick_patterns", "K线形态识别库（24形态）", "low"),
    ("slippage_model", "滑点成本模型", "low"),
    ("strategy_lifecycle", "策略生命周期管理", "low"),
    ("auto_optimization", "自动策略优化引擎", "low"),
    ("diagnostic_framework", "五层系统诊断框架", "low"),
    ("api_bridge", "QuantDinger API桥接器", "high"),
]


@validation_bp.route('/status', methods=['GET'])
def get_validation_status():
    """获取核心验证模块状态。

    实时探针指标待后端接入；当前返回模块登记清单，details 为空、status 为
    pending，前端据此展示空态/待接入，不把未度量项渲染成演示数值。
    """
    now = datetime.now().isoformat()
    modules = [
        {
            "id": mod_id,
            "name": name,
            "status": "pending",
            "level": level,
            "last_check": now,
            "details": "",
        }
        for mod_id, name, level in _MODULE_REGISTRY
    ]

    return jsonify({
        "code": 1,
        "data": {
            "modules": modules,
            "total": len(modules),
            "healthy": sum(1 for m in modules if m['status'] == 'healthy'),
            "connected": sum(1 for m in modules if m['status'] == 'connected'),
            "pending": sum(1 for m in modules if m['status'] == 'pending'),
        }
    })


@validation_bp.route('/audit-logs', methods=['GET'])
def get_audit_logs():
    """获取决策审计日志。

    当前验证/风控事件尚无独立持久化事件表，返回空列表；前端展示空态，
    不生成模拟 PASS/测试通过/PBO 等编造留痕。事件表落地后改为只读查询。
    """
    limit = request.args.get('limit', 20, type=int)
    if not isinstance(limit, int) or limit < 1:
        limit = 20
    limit = min(limit, 100)

    return jsonify({
        "code": 1,
        "data": {
            "logs": [],
            "total": 0,
            "limit": limit,
        }
    })


@validation_bp.route('/stress-test', methods=['GET'])
def get_stress_test():
    """获取极端情景压力测试结果（演示模板，非真实冲击测算）。

    data_kind 固定为 'demo'：前端仅在 'real'（基于真实持仓/权益完成冲击
    测算）时渲染。综合评分/风险等级/结论在真实引擎落地前置空，不输出演示
    评分或回撤结论。
    """
    scenarios = [
        {"id": "financial_crisis_2008", "name": "2008金融危机", "status": "demo"},
        {"id": "covid_2020", "name": "2020新冠暴跌", "status": "demo"},
        {"id": "flash_crash_2010", "name": "2010闪电崩盘", "status": "demo"},
        {"id": "rate_shock", "name": "利率冲击", "status": "demo"},
        {"id": "commodity_squeeze", "name": "大宗商品逼空", "status": "demo"},
    ]

    return jsonify({
        "code": 1,
        "data": {
            "data_kind": "demo",
            "scenarios": scenarios,
            "total_scenarios": len(scenarios),
            "survived": 0,
            "overall_risk_score": None,
            "risk_level": None,
            "summary": "演示情景模板，待后端基于真实持仓/权益接入冲击测算引擎。",
        }
    })
