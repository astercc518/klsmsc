"""
数据平台对接客户端
"""
import httpx
import hashlib
import time
import json
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class DataPlatformConfig(BaseModel):
    """数据平台配置"""
    api_url: str = ""
    api_key: str = ""
    api_secret: str = ""
    timeout: int = 30


class DataPlatformClient:
    """
    数据平台API客户端
    
    用于对接外部数据平台，实现账户创建、充值、数据查询和提取等功能。
    实际API实现需要根据数据平台提供的文档进行调整。
    """
    
    def __init__(self, config: Optional[DataPlatformConfig] = None):
        if config:
            self.config = config
        else:
            self.config = DataPlatformConfig(
                api_url=getattr(settings, 'DATA_PLATFORM_URL', ''),
                api_key=getattr(settings, 'DATA_PLATFORM_KEY', ''),
                api_secret=getattr(settings, 'DATA_PLATFORM_SECRET', ''),
            )
        
        self.client = httpx.AsyncClient(
            timeout=self.config.timeout,
            headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
        )
    
    def _generate_signature(self, params: dict) -> str:
        """生成API签名"""
        sorted_params = sorted(params.items())
        param_str = '&'.join([f"{k}={v}" for k, v in sorted_params])
        sign_str = f"{param_str}&secret={self.config.api_secret}"
        return hashlib.md5(sign_str.encode()).hexdigest().upper()
    
    async def _request(self, endpoint: str, data: dict) -> dict:
        """发送API请求"""
        if not self.config.api_url:
            logger.warning("数据平台API未配置")
            return {"success": False, "message": "数据平台API未配置"}
        
        url = f"{self.config.api_url.rstrip('/')}/{endpoint.lstrip('/')}"
        
        data['api_key'] = self.config.api_key
        data['timestamp'] = str(int(time.time()))
        data['sign'] = self._generate_signature(data)
        
        try:
            response = await self.client.post(url, json=data)
            response.raise_for_status()
            result = response.json()
            logger.debug(f"数据平台API响应: {endpoint} -> {result}")
            return result
        except httpx.HTTPError as e:
            logger.error(f"数据平台API请求失败: {endpoint} -> {e}")
            return {"success": False, "message": str(e)}
        except Exception as e:
            logger.error(f"数据平台API异常: {endpoint} -> {e}")
            return {"success": False, "message": str(e)}
    
    async def create_account(self, data: dict) -> dict:
        """
        创建数据平台账户
        
        Args:
            data: {
                "account_name": "客户名称",
                "country_code": "国家代码",
            }
        """
        result = await self._request('/api/account/create', {
            'account_name': data.get('account_name'),
            'country_code': data.get('country_code', ''),
        })
        
        if not result.get('success', False):
            if not self.config.api_url:
                mock_id = f"DATA_{int(time.time())}"
                return {
                    "success": True,
                    "data": {
                        "external_id": mock_id,
                        "account": f"data_{data.get('account_name', 'user')}",
                        "token": f"token_{mock_id}",
                        "balance": 0.0,
                        "status": "active"
                    }
                }
        
        return result
    
    async def recharge(self, account_id: str, amount: float) -> dict:
        """
        账户充值
        """
        result = await self._request('/api/account/recharge', {
            'account_id': account_id,
            'amount': str(amount)
        })
        
        if not result.get('success', False):
            if not self.config.api_url:
                return {
                    "success": True,
                    "data": {
                        "transaction_id": f"TRX_{int(time.time())}",
                        "new_balance": amount
                    }
                }
        
        return result
    
    async def get_balance(self, account_id: str) -> float:
        """
        查询账户余额
        """
        result = await self._request('/api/account/balance', {
            'account_id': account_id
        })
        
        if result.get('success'):
            return float(result.get('data', {}).get('balance', 0))
        
        return 0.0
    
    async def query_data(self, filters: dict) -> dict:
        """
        查询可用数据
        
        Args:
            filters: {
                "country_code": "国家代码",
                "carrier": "运营商",
                "gender": "性别",
                "age_min": 最小年龄,
                "age_max": 最大年龄,
                "city": "城市",
            }
            
        Returns:
            {
                "success": True,
                "data": {
                    "total_available": 10000,
                    "unit_price": 0.01,
                    "filters_applied": {...}
                }
            }
        """
        result = await self._request('/api/data/query', filters)
        
        if not result.get('success', False):
            if not self.config.api_url:
                return {
                    "success": True,
                    "data": {
                        "total_available": 10000,
                        "unit_price": 0.01,
                        "filters_applied": filters
                    }
                }
        
        return result
    
    async def extract_data(
        self, 
        account_id: str, 
        filters: dict, 
        count: int
    ) -> dict:
        """
        提取数据
        
        Args:
            account_id: 账户ID
            filters: 筛选条件
            count: 提取数量
            
        Returns:
            {
                "success": True,
                "data": {
                    "extracted_count": 100,
                    "total_cost": 1.0,
                    "numbers": [
                        {"phone": "+861380001111", "country": "CN", ...},
                        ...
                    ]
                }
            }
        """
        params = {
            'account_id': account_id,
            'count': str(count),
            **filters
        }
        
        result = await self._request('/api/data/extract', params)
        
        if not result.get('success', False):
            if not self.config.api_url:
                # 模拟返回
                mock_numbers = [
                    {
                        "phone": f"+861380000{i:04d}",
                        "country_code": filters.get('country_code', 'CN'),
                        "carrier": "China Mobile",
                        "gender": "unknown"
                    }
                    for i in range(min(count, 10))  # 模拟最多10条
                ]
                return {
                    "success": True,
                    "data": {
                        "extracted_count": len(mock_numbers),
                        "total_cost": len(mock_numbers) * 0.01,
                        "numbers": mock_numbers
                    }
                }
        
        return result
    
    async def get_extraction_history(
        self,
        account_id: str,
        page: int = 1,
        page_size: int = 20
    ) -> dict:
        """
        获取提取历史
        """
        result = await self._request('/api/data/history', {
            'account_id': account_id,
            'page': str(page),
            'page_size': str(page_size)
        })
        
        if not result.get('success', False):
            if not self.config.api_url:
                return {
                    "success": True,
                    "data": {
                        "total": 0,
                        "records": []
                    }
                }
        
        return result
    
    async def close(self):
        """关闭客户端连接"""
        await self.client.aclose()


# 单例实例
_data_client: Optional[DataPlatformClient] = None


def get_data_platform_client() -> DataPlatformClient:
    """获取数据平台客户端单例"""
    global _data_client
    if _data_client is None:
        _data_client = DataPlatformClient()
    return _data_client
