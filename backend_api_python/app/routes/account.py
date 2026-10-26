"""
账户管理API路由
处理交易所账户绑定、测试连接、查询余额等
"""
from flask import request, jsonify
from app.openapi.blueprint import HumanBlueprint as Blueprint
from app.services.okx_client import OKXClient, save_account_config, get_account_list

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
