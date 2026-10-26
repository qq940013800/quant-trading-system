"""
OKX API客户端模块
负责OKX交易所的连接测试、账户查询、交易执行
"""
import hmac
import base64
import hashlib
import requests
from datetime import datetime
from typing import Dict, Optional, Tuple


class OKXClient:
    """OKX交易所API客户端"""
    
    BASE_URL = "https://www.okx.com"
    
    def __init__(self, api_key: str, api_secret: str, passphrase: str, is_demo: bool = False):
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.is_demo = is_demo
        self.session = requests.Session()
    
    def _get_timestamp(self) -> str:
        """获取ISO格式时间戳"""
        return datetime.utcnow().isoformat(timespec='milliseconds') + 'Z'
    
    def _sign(self, timestamp: str, method: str, request_path: str, body: str = '') -> str:
        """生成OKX API签名"""
        message = timestamp + method.upper() + request_path + body
        mac = hmac.new(
            bytes(self.api_secret, encoding='utf-8'),
            bytes(message, encoding='utf-8'),
            digestmod=hashlib.sha256
        )
        return base64.b64encode(mac.digest()).decode()
    
    def _get_headers(self, method: str, request_path: str, body: str = '') -> Dict:
        """生成请求头"""
        timestamp = self._get_timestamp()
        sign = self._sign(timestamp, method, request_path, body)
        
        headers = {
            'OK-ACCESS-KEY': self.api_key,
            'OK-ACCESS-SIGN': sign,
            'OK-ACCESS-TIMESTAMP': timestamp,
            'OK-ACCESS-PASSPHRASE': self.passphrase,
            'Content-Type': 'application/json'
        }
        
        if self.is_demo:
            headers['x-simulated-trading'] = '1'
        
        return headers
    
    def test_connection(self) -> Tuple[bool, str, Optional[Dict]]:
        """
        测试API连接是否正常
        返回: (成功与否, 消息, 数据)
        """
        try:
            # 查询账户余额
            request_path = '/api/v5/account/balance'
            headers = self._get_headers('GET', request_path)
            
            response = self.session.get(
                self.BASE_URL + request_path,
                headers=headers,
                timeout=10
            )
            
            data = response.json()
            
            if data.get('code') == '0':
                # 成功
                details = data.get('data', [{}])[0]
                total_eq = details.get('totalEq', '0')
                return True, f"连接成功，账户总权益: ${float(total_eq):.2f}", {
                    'balance': f"${float(total_eq):.2f}",
                    'total_eq': total_eq,
                    'details': details
                }
            else:
                # 失败
                error_msg = data.get('msg', '未知错误')
                return False, f"连接失败: {error_msg}", None
                
        except requests.exceptions.ConnectionError:
            return False, "连接失败：网络无法到达OKX服务器（可能被墙）", None
        except requests.exceptions.Timeout:
            return False, "连接超时：OKX服务器响应太慢", None
        except Exception as e:
            return False, f"连接异常: {str(e)}", None
    
    def get_balance(self) -> Tuple[bool, str, Optional[Dict]]:
        """获取账户余额"""
        return self.test_connection()
    
    def get_positions(self) -> Tuple[bool, str, Optional[list]]:
        """获取当前持仓"""
        try:
            request_path = '/api/v5/account/positions'
            headers = self._get_headers('GET', request_path)
            
            response = self.session.get(
                self.BASE_URL + request_path,
                headers=headers,
                timeout=10
            )
            
            data = response.json()
            
            if data.get('code') == '0':
                positions = data.get('data', [])
                return True, f"查询成功，共{len(positions)}个持仓", positions
            else:
                error_msg = data.get('msg', '未知错误')
                return False, f"查询失败: {error_msg}", None
                
        except Exception as e:
            return False, f"查询异常: {str(e)}", None
    
    def place_order(self, symbol: str, side: str, size: float, price: float = None,
                    ord_type: str = None, tgt_ccy: str = None) -> Tuple[bool, str, Optional[Dict]]:
        """
        下单
        symbol: 交易对，如 BTC-USDT
        side: buy/sell
        size: 数量
        price: 价格（限价单需要）
        ord_type: limit/market，默认自动判断
        tgt_ccy: 市价单买入时指定计价货币（USDT），如 'quote_ccy'
        """
        try:
            request_path = '/api/v5/trade/order'
            
            # 自动判断订单类型
            if ord_type is None:
                ord_type = 'limit' if price else 'market'
            
            body = {
                'instId': symbol,
                'tdMode': 'cash',  # 现货交易
                'side': side,
                'ordType': ord_type,
                'sz': str(size)
            }
            
            if price and ord_type == 'limit':
                body['px'] = str(price)
            
            # 市价买入时，支持用USDT金额下单
            if ord_type == 'market' and side == 'buy' and tgt_ccy:
                body['tgtCcy'] = tgt_ccy
            
            # 加client order id方便排查
            import time
            body['clOrdId'] = f"qd{int(time.time()*1000)}"
            
            import json
            body_str = json.dumps(body)
            headers = self._get_headers('POST', request_path, body_str)
            
            response = self.session.post(
                self.BASE_URL + request_path,
                headers=headers,
                data=body_str,
                timeout=10
            )
            
            data = response.json()
            
            if data.get('code') == '0':
                order_data = data.get('data', [{}])[0]
                sCode = order_data.get('sCode', '0')
                sMsg = order_data.get('sMsg', '')
                if sCode == '0':
                    order_id = order_data.get('ordId', '未知')
                    return True, f"下单成功！订单号: {order_id}", order_data
                else:
                    return False, f"下单失败（交易所返回）: {sMsg}", order_data
            else:
                error_msg = data.get('msg', '未知错误')
                # 常见错误提示
                if '51001' in str(data):
                    error_msg = '余额不足，请先充值或检查最小下单金额'
                elif '51002' in str(data):
                    error_msg = '交易对不存在或未开通交易权限'
                elif '51008' in str(data):
                    error_msg = '模拟盘模式下该交易对不可用，请检查账户设置'
                return False, f"下单失败: {error_msg} (code={data.get('code')})", None
                
        except Exception as e:
            return False, f"下单异常: {str(e)}", None


# 全局账户配置存储（临时，后续存数据库）
_account_configs = {}


def save_account_config(name: str, exchange: str, api_key: str, api_secret: str, 
                       passphrase: str, permissions: Dict, is_demo: bool = False) -> Dict:
    """保存账户配置"""
    _account_configs[name] = {
        'name': name,
        'exchange': exchange,
        'api_key': api_key[:8] + '****' + api_key[-4:],  # 脱敏
        'passphrase': '****',  # 不保存明文
        'permissions': permissions,
        'is_demo': is_demo,
        'created_at': datetime.now().isoformat()
    }
    
    # 实际密钥单独存储（内存中，不返回）
    _account_configs[name]['_full_config'] = {
        'api_key': api_key,
        'api_secret': api_secret,
        'passphrase': passphrase
    }
    
    return {
        'success': True,
        'message': f'账户 {name} 已保存',
        'data': _account_configs[name]
    }


def get_account_list() -> list:
    """获取账户列表（脱敏）"""
    result = []
    for name, config in _account_configs.items():
        result.append({
            'name': config['name'],
            'exchange': config['exchange'],
            'api_key': config['api_key'],
            'permissions': config['permissions'],
            'is_demo': config['is_demo']
        })
    return result
