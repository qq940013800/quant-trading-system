"""
综合市场分析API路由

提供L1-L5五层市场识别的API接口
"""
from __future__ import annotations

from flask import jsonify, request
from app.openapi.blueprint import HumanBlueprint as Blueprint
from app.services.comprehensive_market_analyzer import ComprehensiveMarketAnalyzer
from app.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint('market_analysis', __name__)

# 初始化分析器
analyzer = ComprehensiveMarketAnalyzer()


@bp.route('/api/market-analysis/demo', methods=['GET'])
def demo_market_analysis():
    """
    演示用综合市场分析
    
    返回模拟的K线数据和分析结果
    """
    # 生成演示K线数据
    import random
    demo_klines = []
    base_price = 80000
    
    for i in range(100):
        change = random.uniform(-0.02, 0.02)
        open_price = base_price
        close_price = base_price * (1 + change)
        high = max(open_price, close_price) * 1.005
        low = min(open_price, close_price) * 0.995
        volume = random.uniform(100, 1000)
        
        demo_klines.append({
            'open': open_price,
            'high': high,
            'low': low,
            'close': close_price,
            'volume': volume
        })
        base_price = close_price
    
    # 运行分析
    result = analyzer.analyze(demo_klines)
    summary = analyzer.get_summary(result)
    
    return jsonify({
        'code': 0,
        'data': summary,
        'message': 'demo market analysis success'
    })


@bp.route('/api/market-analysis/layers', methods=['GET'])
def get_market_layers():
    """
    获取五层市场识别说明
    
    返回L1-L5每层的职责和当前状态
    """
    layers = [
        {
            'level': 'L1',
            'name': '市场状态识别',
            'module': 'market_regime.py',
            'status': '✅ 已完成',
            'description': '识别当前市场是趋势市、震荡市还是危机市，决定用什么策略'
        },
        {
            'level': 'L2',
            'name': '市场结构识别',
            'module': 'market_structure.py',
            'status': '✅ 已完成',
            'description': '识别高低点、支撑阻力位、结构突破，决定在哪里入场止损'
        },
        {
            'level': 'L3',
            'name': '市场趋势识别',
            'module': 'market_trend.py',
            'status': '✅ 已完成',
            'description': '识别趋势方向、强度、阶段，决定方向和仓位大小'
        },
        {
            'level': 'L4',
            'name': '价格行为识别',
            'module': 'price_action.py',
            'status': '✅ 已完成',
            'description': '识别吞没、针形线、内包线等价格形态，决定精确入场时机'
        },
        {
            'level': 'L5',
            'name': 'K线形态识别',
            'module': 'candlestick_patterns.py',
            'status': '✅ 已完成',
            'description': '识别早晨之星、黄昏之星、三只乌鸦等经典K线组合，决定最终入场信号'
        }
    ]
    
    return jsonify({
        'code': 0,
        'data': {
            'layers': layers,
            'total': len(layers),
            'completed': sum(1 for l in layers if '✅' in l['status'])
        },
        'message': 'market layers info'
    })
