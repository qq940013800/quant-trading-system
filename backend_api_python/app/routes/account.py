"""
账户管理API路由
处理交易所账户绑定、测试连接、查询余额等
"""
from typing import Any, Dict, List, Optional

from flask import g, jsonify, request

from app.openapi.blueprint import HumanBlueprint as Blueprint
from app.services.okx_client import OKXClient, save_account_config, get_account_list
from app.services.okx_kline import OKXKlineService
from app.utils.auth import login_required
from app.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint('account', __name__)


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        v = float(value)
        return v if v == v else default
    except (TypeError, ValueError):
        return default


def _build_positions_payload(
    snapshot: Optional[Dict[str, Any]], equity: Optional[float]
) -> Dict[str, Any]:
    """Map the live-trading snapshot legs onto the legacy dashboard position contract.

    Real swap holdings and spot wallet legs are kept with ``market_type`` so the frontend
    can later distinguish derivative positions from wallet stock. ``value_usd`` is a
    ``size * entry_price`` approximation (snapshot legs carry no mark price). The USDT
    cash leg is excluded from the position list; cash is already covered by the equity
    figure, and listing it as a position would misread the wallet balance as a holding.
    """
    snapshot = snapshot or {}
    legs: List[Dict[str, Any]] = []
    raw_legs = list(snapshot.get("swap_positions") or []) + list(snapshot.get("spot_positions") or [])
    for leg in raw_legs:
        if not isinstance(leg, dict):
            continue
        cash_symbol = str(leg.get("symbol") or "").upper()
        cash_inst = str(leg.get("inst_id") or "").upper()
        if cash_symbol == "USDT" or cash_inst == "USDT":
            continue
        size = _to_float(leg.get("size"))
        if size <= 0:
            continue
        entry = _to_float(leg.get("entry_price"))
        value = round(size * entry, 4) if entry > 0 else 0.0
        legs.append(
            {
                "symbol": leg.get("symbol") or leg.get("inst_id") or "",
                "amount": size,
                "value_usd": value,
                "side": leg.get("side") or "",
                "market_type": leg.get("market_type") or "",
                "inst_id": leg.get("inst_id") or "",
            }
        )
    equity_out: Optional[str]
    if equity is None:
        equity_out = None
    else:
        # Legacy dashboard calls ``.replace('$', '')`` on the equity string; keep a
        # two-decimal string (no currency symbol) instead of a raw float.
        equity_out = f"{_to_float(equity):.2f}"
    return {
        "positions": legs,
        "items": legs,
        "count": len(legs),
        "total_equity": equity_out,
        "warnings": list(snapshot.get("warnings") or []),
    }


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
@login_required
def get_positions():
    """真实持仓：凭证库 -> live_trading 主链快照。

    不再读取进程内 ``_account_configs`` 内存字典，也不再把账户余额各币种当作持仓；
    合约持仓来自 ``swap_positions``，现货钱包存量来自 ``spot_positions``，权益来自
    ``fetch_account_equity``。任一环节失败按空态兜底，不向调用方泄漏内部异常。
    """
    from app.services.live_trading.account_snapshot import fetch_account_snapshot
    from app.services.live_trading.connection import (
        fetch_account_equity,
        list_saved_credentials,
    )

    empty = {
        "positions": [],
        "items": [],
        "count": 0,
        "total_equity": None,
        "warnings": [],
    }
    user_id = getattr(g, "user_id", None)
    if user_id is None:
        return jsonify({"code": 1, "success": True, "data": empty})

    try:
        creds = list_saved_credentials(int(user_id))
        okx = next(
            (
                c
                for c in creds
                if str(c.get("exchange_id") or "").lower() in ("okx", "okex")
            ),
            None,
        )
        snapshot: Optional[Dict[str, Any]] = None
        if okx:
            snapshot = fetch_account_snapshot(
                user_id=int(user_id), credential_id=int(okx["id"])
            )
        equity = fetch_account_equity(int(user_id))
        payload = _build_positions_payload(snapshot, equity)
    except Exception as e:
        logger.warning("account positions snapshot skipped: %s", e)
        payload = empty

    return jsonify({"code": 1, "success": True, "data": payload})
