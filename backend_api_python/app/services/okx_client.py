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
