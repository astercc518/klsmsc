"""
后端API客户端
"""
import httpx
from typing import Dict, Optional
from loguru import logger
from bot.config import settings


class APIClient:
    """API客户端"""
    
    def __init__(self):
        self.base_url = settings.API_BASE_URL
        self.timeout = 30.0
    
    async def register_account(
        self,
        email: str,
        password: str,
        account_name: str,
        company_name: Optional[str] = None
    ) -> Dict:
        """
        注册账户
        
        Returns:
            {
                'success': bool,
                'account_id': int,
                'api_key': str,
                'error': dict (if failed)
            }
        """
        url = f"{self.base_url}/api/v1/account/register"
        payload = {
            "email": email,
            "password": password,
            "account_name": account_name,
            "company_name": company_name
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload)
                result = response.json()
                
                if response.status_code == 200:
                    logger.info(f"账户注册成功: {email}")
                    return result
                else:
                    logger.error(f"账户注册失败: {response.status_code} {result}")
                    return {"success": False, "error": result}
                    
        except Exception as e:
            logger.error(f"API请求异常: {str(e)}", exc_info=e)
            return {"success": False, "error": {"message": str(e)}}
    
    async def send_sms(
        self,
        api_key: str,
        phone_number: str,
        message: str,
        sender_id: Optional[str] = None
    ) -> Dict:
        """
        发送短信
        
        Returns:
            {
                'success': bool,
                'message_id': str,
                'status': str,
                'cost': float,
                'currency': str,
                'message_count': int,
                'error': dict (if failed)
            }
        """
        url = f"{self.base_url}/api/v1/sms/send"
        payload = {
            "phone_number": phone_number,
            "message": message,
            "sender_id": sender_id
        }
        headers = {
            "X-API-Key": api_key
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
                result = response.json()
                
                if response.status_code == 200:
                    logger.info(f"短信发送成功: {result.get('message_id')}")
                else:
                    logger.error(f"短信发送失败: {response.status_code} {result}")
                
                return result
                
        except Exception as e:
            logger.error(f"API请求异常: {str(e)}", exc_info=e)
            return {"success": False, "error": {"message": str(e)}}
    
    async def get_balance(self, api_key: str) -> Dict:
        """
        查询余额
        
        Returns:
            {
                'success': bool,
                'account_id': int,
                'balance': float,
                'currency': str,
                'low_balance_threshold': float,
                'error': str (if failed)
            }
        """
        url = f"{self.base_url}/api/v1/account/balance"
        headers = {
            "X-API-Key": api_key
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=headers)
                
                if response.status_code == 200:
                    result = response.json()
                    result['success'] = True
                    return result
                else:
                    logger.error(f"查询余额失败: {response.status_code}")
                    return {"success": False, "error": f"HTTP {response.status_code}"}
                    
        except Exception as e:
            logger.error(f"API请求异常: {str(e)}", exc_info=e)
            return {"success": False, "error": str(e)}

