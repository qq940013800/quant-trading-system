"""
账户管理API路由
处理交易所账户绑定、测试连接、查询余额等
"""
from flask import request, jsonify
from app.openapi.blueprint import HumanBlueprint as Blueprint
from app.services.okx_client import OKXClient, save_account_config, get_account_list
from app.services.okx_kline import OKXKlineService

bp = Blueprint('account', __name__)


@bp.route('/account/test-connection', methods=['POST'])
def test_connection():
    """测试交易所API连接"""
    try:
        data = request.get_json()
        exchange = data.get('exchange', 'okx')
        api_key = data.get('api_key', '')
        api_secret = data.get('api_secret', '')
        passphrase = data.get('passphrase', '')
        
        if not api_key or not api_secret:
            return jsonify({
                'success': False,
                'message': '请填写完整的API Key和Secret'
            }), 400
        
        if exchange == 'okx':
            client = OKXClient(api_key, api_secret, passphrase, is_demo=True)
            success, message, balance_data = client.test_connection()
            
            return jsonify({
                'success': success,
                'message': message,
                'data': balance_data or {}
            })
        else:
            return jsonify({
                'success': False,
                'message': f'暂不支持{exchange}交易所'
            }), 400
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'测试连接异常: {str(e)}'
        }), 500


@bp.route('/account/save', methods=['POST'])
def save_account():
    """保存交易所账户配置"""
    try:
        data = request.get_json()
        name = data.get('name', '')
        exchange = data.get('exchange', 'okx')
        api_key = data.get('api_key', '')
        api_secret = data.get('api_secret', '')
        passphrase = data.get('passphrase', '')
        permissions = data.get('permissions', {'read': True, 'trade': False})
        
        if not name or not api_key:
            return jsonify({
                'success': False,
                'message': '请填写账户名称和API Key'
            }), 400
        
        result = save_account_config(name, exchange, api_key, api_secret, 
                                   passphrase, permissions, is_demo=True)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'保存账户异常: {str(e)}'
        }), 500


@bp.route('/account/list', methods=['GET'])
def list_accounts():
    """获取已绑定的账户列表"""
    try:
        accounts = get_account_list()
        return jsonify({
            'success': True,
            'data': {
                'accounts': accounts,
                'total': len(accounts)
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取账户列表异常: {str(e)}'
        }), 500


@bp.route('/market/kline', methods=['GET'])
def get_kline():
    """获取OKX真实K线数据"""
    try:
        symbol = request.args.get('symbol', 'BTC-USDT')
        bar = request.args.get('bar', '1H')
        limit = int(request.args.get('limit', '100'))
        
        candles = OKXKlineService.get_kline(symbol, bar, limit)
        
        return jsonify({
            'success': True,
            'data': {
                'symbol': symbol,
                'bar': bar,
                'candles': candles,
                'count': len(candles)
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取K线异常: {str(e)}'
        }), 500


@bp.route('/market/ticker', methods=['GET'])
def get_ticker():
    """获取OKX最新价格"""
    try:
        symbol = request.args.get('symbol', 'BTC-USDT')
        ticker = OKXKlineService.get_ticker(symbol)
        
        if ticker:
            return jsonify({
                'success': True,
                'data': ticker
            })
        else:
            return jsonify({
                'success': False,
                'message': '获取价格失败'
            }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取价格异常: {str(e)}'
        }), 500


@bp.route('/account/place-order', methods=['POST'])
def place_order():
    """OKX下单（DEMO测试用）"""
    try:
        data = request.get_json()
        symbol = data.get('symbol', 'BTC-USDT')
        side = data.get('side', 'buy')
        size = float(data.get('size', '0.001'))
        price = data.get('price')
        
        # 使用之前保存的DEMO账户密钥
        from app.services.okx_client import _account_configs
        if 'DEMO' not in _account_configs:
            return jsonify({
                'success': False,
                'message': '未找到DEMO账户配置，请先绑定API账户'
            }), 400
        
        config = _account_configs['DEMO']['_full_config']
        client = OKXClient(config['api_key'], config['api_secret'], config['passphrase'], is_demo=True)
        
        success, message, order_data = client.place_order(symbol, side, size, float(price) if price else None)
        
        return jsonify({
            'success': success,
            'message': message,
            'data': order_data or {}
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'下单异常: {str(e)}'
        }), 500


@bp.route('/account/positions', methods=['GET'])
def get_positions():
    """获取OKX账户真实持仓"""
    try:
        from app.services.okx_client import _account_configs
        if 'DEMO' not in _account_configs:
            return jsonify({
                'success': False,
                'message': '未绑定账户',
                'data': {'positions': []}
            })
        
        config = _account_configs['DEMO']['_full_config']
        client = OKXClient(config['api_key'], config['api_secret'], config['passphrase'], is_demo=True)
        
        # 先查余额
        success, message, balance_data = client.test_connection()
        
        positions = []
        if success and balance_data:
            details = balance_data.get('details', [])
            for d in details:
                ccy = d.get('ccy', '')
                eq = float(d.get('eq', 0))
                eq_usd = float(d.get('eqUsd', 0))
                if eq > 0:
                    positions.append({
                        'symbol': ccy,
                        'amount': eq,
                        'value_usd': eq_usd
                    })
        
        return jsonify({
            'success': True,
            'data': {
                'total_equity': balance_data.get('balance', '$0') if balance_data else '$0',
                'positions': positions,
                'count': len(positions)
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取持仓异常: {str(e)}',
            'data': {'positions': []}
        }), 500
