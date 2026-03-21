"""
OKCC语音系统对接客户端
"""
import httpx
import hashlib
import time
import json
from typing import Optional, Dict, Any
from pydantic import BaseModel
from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class OKCCConfig(BaseModel):
    """OKCC配置"""
    api_url: str = ""
    api_key: str = ""
    api_secret: str = ""
    timeout: int = 30


class OKCCAccountInfo(BaseModel):
    """OKCC账户信息"""
    external_id: str
    account: str
    password: str
    balance: float = 0.0
    status: str = "active"
    country_code: str = ""
    extra_data: Optional[Dict[str, Any]] = None


class OKCCClient:
    """
    OKCC语音系统API客户端
    
    用于对接OKCC系统，实现账户创建、充值、余额查询等功能。
    实际API实现需要根据OKCC提供的文档进行调整。
    """
    
    def __init__(self, config: Optional[OKCCConfig] = None):
        if config:
            self.config = config
        else:
            # 从环境变量获取配置
            self.config = OKCCConfig(
                api_url=getattr(settings, 'OKCC_API_URL', ''),
                api_key=getattr(settings, 'OKCC_API_KEY', ''),
                api_secret=getattr(settings, 'OKCC_API_SECRET', ''),
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
        # 按key排序
        sorted_params = sorted(params.items())
        # 拼接参数
        param_str = '&'.join([f"{k}={v}" for k, v in sorted_params])
        # 加上secret
        sign_str = f"{param_str}&secret={self.config.api_secret}"
        # MD5签名
        return hashlib.md5(sign_str.encode()).hexdigest().upper()
    
    async def _request(self, endpoint: str, data: dict) -> dict:
        """发送API请求"""
        if not self.config.api_url:
            logger.warning("OKCC API未配置")
            return {"success": False, "message": "OKCC API未配置"}
        
        url = f"{self.config.api_url.rstrip('/')}/{endpoint.lstrip('/')}"
        
        # 添加通用参数
        data['api_key'] = self.config.api_key
        data['timestamp'] = str(int(time.time()))
        data['sign'] = self._generate_signature(data)
        
        try:
            response = await self.client.post(url, json=data)
            response.raise_for_status()
            result = response.json()
            logger.debug(f"OKCC API响应: {endpoint} -> {result}")
            return result
        except httpx.HTTPError as e:
            logger.error(f"OKCC API请求失败: {endpoint} -> {e}")
            return {"success": False, "message": str(e)}
        except Exception as e:
            logger.error(f"OKCC API异常: {endpoint} -> {e}")
            return {"success": False, "message": str(e)}
    
    async def create_account(self, data: dict) -> dict:
        """
        创建OKCC账户
        
        Args:
            data: {
                "account_name": "客户名称",
                "country_code": "国家代码",
                "contact_phone": "联系电话",
                "contact_email": "联系邮箱",
                "product_id": "产品ID (可选)"
            }
            
        Returns:
            {
                "success": True,
                "data": {
                    "external_id": "OKCC系统账户ID",
                    "account": "登录账号",
                    "password": "初始密码",
                    "status": "active"
                }
            }
        """
        result = await self._request('/api/account/create', {
            'account_name': data.get('account_name'),
            'country_code': data.get('country_code'),
            'contact_phone': data.get('contact_phone', ''),
            'contact_email': data.get('contact_email', ''),
            'product_id': data.get('product_id', ''),
        })
        
        if not result.get('success', False):
            # 模拟成功响应（用于开发测试）
            if not self.config.api_url:
                mock_id = f"OKCC_{int(time.time())}"
                return {
                    "success": True,
                    "data": OKCCAccountInfo(
                        external_id=mock_id,
                        account=f"voice_{data.get('account_name', 'user')}",
                        password="initial_password_123",
                        balance=0.0,
                        status="active",
                        country_code=data.get('country_code', '')
                    ).model_dump()
                }
        
        return result
    
    async def recharge(self, account_id: str, amount: float) -> dict:
        """
        账户充值
        
        Args:
            account_id: OKCC系统账户ID
            amount: 充值金额
            
        Returns:
            {
                "success": True,
                "data": {
                    "transaction_id": "交易ID",
                    "new_balance": 100.00
                }
            }
        """
        result = await self._request('/api/account/recharge', {
            'account_id': account_id,
            'amount': str(amount)
        })
        
        if not result.get('success', False):
            # 模拟成功响应
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
        
        Args:
            account_id: OKCC系统账户ID
            
        Returns:
            余额金额
        """
        result = await self._request('/api/account/balance', {
            'account_id': account_id
        })
        
        if result.get('success'):
            return float(result.get('data', {}).get('balance', 0))
        
        # 模拟返回
        if not self.config.api_url:
            return 0.0
        
        return 0.0
    
    async def sync_status(self, account_id: str) -> dict:
        """
        同步账户状态
        
        Args:
            account_id: OKCC系统账户ID
            
        Returns:
            {
                "success": True,
                "data": {
                    "status": "active",
                    "balance": 100.00,
                    "last_call_time": "2024-01-01 12:00:00",
                    "total_calls": 100,
                    "total_minutes": 500
                }
            }
        """
        result = await self._request('/api/account/status', {
            'account_id': account_id
        })
        
        if not result.get('success', False):
            # 模拟返回
            if not self.config.api_url:
                return {
                    "success": True,
                    "data": {
                        "status": "active",
                        "balance": 0.0,
                        "last_call_time": None,
                        "total_calls": 0,
                        "total_minutes": 0
                    }
                }
        
        return result
    
    async def get_call_records(
        self, 
        account_id: str, 
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        page: int = 1,
        page_size: int = 50
    ) -> dict:
        """
        获取通话记录
        
        Args:
            account_id: OKCC系统账户ID
            start_time: 开始时间
            end_time: 结束时间
            page: 页码
            page_size: 每页数量
            
        Returns:
            {
                "success": True,
                "data": {
                    "total": 100,
                    "records": [...]
                }
            }
        """
        params = {
            'account_id': account_id,
            'page': str(page),
            'page_size': str(page_size)
        }
        
        if start_time:
            params['start_time'] = start_time
        if end_time:
            params['end_time'] = end_time
        
        result = await self._request('/api/cdr/list', params)
        
        if not result.get('success', False):
            # 模拟返回
            if not self.config.api_url:
                return {
                    "success": True,
                    "data": {
                        "total": 0,
                        "records": []
                    }
                }
        
        return result
    
    async def suspend_account(self, account_id: str) -> dict:
        """暂停账户"""
        return await self._request('/api/account/suspend', {
            'account_id': account_id
        })
    
    async def resume_account(self, account_id: str) -> dict:
        """恢复账户"""
        return await self._request('/api/account/resume', {
            'account_id': account_id
        })
    
    async def close(self):
        """关闭客户端连接"""
        await self.client.aclose()


# 单例实例
_okcc_client: Optional[OKCCClient] = None


def get_okcc_client() -> OKCCClient:
    """获取OKCC客户端单例"""
    global _okcc_client
    if _okcc_client is None:
        _okcc_client = OKCCClient()
    return _okcc_client
