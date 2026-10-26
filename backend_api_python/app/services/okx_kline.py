"""
OKX K线数据服务
从OKX拉取真实历史K线数据
"""
import requests
from typing import List, Dict, Optional
from datetime import datetime


class OKXKlineService:
    """OKX K线数据获取服务"""
    
    BASE_URL = "https://www.okx.com"
    
    # OKK Bar间隔映射
    BAR_MAP = {
        '1m': '1m',
        '5m': '5m',
        '15m': '15m',
        '30m': '30m',
        '1H': '1H',
        '4H': '4H',
        '1D': '1D',
    }
    
    @classmethod
    def get_kline(cls, symbol: str = 'BTC-USDT', bar: str = '1H', limit: int = 100) -> List[Dict]:
        """
        获取K线数据
        返回格式: [{'time': timestamp, 'open': o, 'high': h, 'low': l, 'close': c, 'volume': v}, ...]
        """
        try:
            okx_bar = cls.BAR_MAP.get(bar, '1H')
            inst_id = symbol
            
            url = f"{cls.BASE_URL}/api/v5/market/candles"
            params = {
                'instId': inst_id,
                'bar': okx_bar,
                'limit': str(limit)
            }
            
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if data.get('code') == '0':
                candles = data.get('data', [])
                # OKX返回格式: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
                # 反转一下，按时间正序
                candles.reverse()
                
                result = []
                for c in candles:
                    result.append({
                        'time': int(c[0]) // 1000,  # 毫秒转秒
                        'open': float(c[1]),
                        'high': float(c[2]),
                        'low': float(c[3]),
                        'close': float(c[4]),
                        'volume': float(c[5])
                    })
                
                return result
            else:
                print(f"OKX K线获取失败: {data.get('msg')}")
                return []
                
        except Exception as e:
            print(f"OKX K线异常: {e}")
            return []
    
    @classmethod
    def get_ticker(cls, symbol: str = 'BTC-USDT') -> Optional[Dict]:
        """获取最新价格"""
        try:
            url = f"{cls.BASE_URL}/api/v5/market/ticker"
            params = {'instId': symbol}
            
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if data.get('code') == '0':
                t = data.get('data', [{}])[0]
                return {
                    'symbol': symbol,
                    'last': float(t.get('last', 0)),
                    'bid': float(t.get('bidPx', 0)),
                    'ask': float(t.get('askPx', 0)),
                    'volume_24h': float(t.get('vol24h', 0)),
                    'high_24h': float(t.get('high24h', 0)),
                    'low_24h': float(t.get('low24h', 0)),
                }
            return None
        except Exception as e:
            print(f"OKX ticker异常: {e}")
            return None
