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
        self.internal_secret = settings.TELEGRAM_STAFF_API_SECRET
        self.timeout = 30.0
    
    def _get_internal_headers(self) -> Dict[str, str]:
        """获取内部 API 认证头"""
        return {"X-Internal-Token": self.internal_secret or ""}

    async def _get(self, endpoint: str, params: dict = None) -> Dict:
        """内部 GET 请求封装"""
        url = f"{self.base_url}/api/v1/internal_bot{endpoint}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"API GET {endpoint} failed: {e}")
            return {"success": False, "msg": str(e)}

    async def _post(self, endpoint: str, json: dict = None) -> Dict:
        """内部 POST 请求封装"""
        url = f"{self.base_url}/api/v1/internal_bot{endpoint}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=json, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"API POST {endpoint} failed: {e}")
            return {"success": False, "msg": str(e)}
    
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

    # ============ 内部 API (Internal Service) ============

    async def get_internal_settings(self) -> Dict:
        """从后端获取 Bot 系统设置"""
        url = f"{self.base_url}/api/v1/internal_bot/settings"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"获取内部设置失败: {e}")
            return {}

    async def verify_user(self, tg_id: int) -> Dict:
        """校验用户身份"""
        url = f"{self.base_url}/api/v1/internal_bot/verify-user/{tg_id}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"校验用户失败: {e}")
            return {"role": "guest", "is_admin": False}

    async def get_templates_internal(self, biz_type: str, country_code: Optional[str] = None) -> list:
        """获取模板列表"""
        url = f"{self.base_url}/api/v1/internal_bot/templates"
        params = {"biz_type": biz_type}
        if country_code:
            params["country_code"] = country_code
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"获取模板失败: {e}")
            return []

    async def create_ticket_internal(self, tg_id: int, title: str, description: str, **kwargs) -> Dict:
        """创建工单"""
        url = f"{self.base_url}/api/v1/internal_bot/tickets"
        payload = {
            "tg_id": tg_id,
            "title": title,
            "description": description,
            **kwargs
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"创建工单失败: {e}")
            return {"success": False, "message": str(e)}

    async def reply_ticket_internal(self, ticket_id: int, tg_id: int, content: str, is_internal: bool = False) -> Dict:
        """回复工单"""
        url = f"{self.base_url}/api/v1/internal_bot/tickets/{ticket_id}/reply"
        payload = {
            "tg_id": tg_id,
            "content": content,
            "is_internal": is_internal
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"回复工单失败: {e}")
            return {"success": False, "message": str(e)}

    async def take_ticket_internal(self, ticket_id: int, tg_id: int) -> Dict:
        """接单"""
        url = f"{self.base_url}/api/v1/internal_bot/tickets/{ticket_id}/take"
        payload = {"tg_id": tg_id}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.patch(url, json=payload, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"接单失败: {e}")
            return {"success": False, "message": str(e)}

    async def finalize_ticket_internal(self, tg_id: int, reply_text: str, ticket_id: int = None, ticket_no: str = None) -> Dict:
        """完结开户工单"""
        url = f"{self.base_url}/api/v1/internal_bot/tickets/finalize"
        payload = {
            "tg_id": tg_id, 
            "reply_text": reply_text,
            "ticket_id": ticket_id,
            "ticket_no": ticket_no
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"完结工单失败: {e}")
            return {"success": False, "message": str(e)}

    async def get_admin_internal(self, tg_id: int) -> Dict:
        """获取管理员信息"""
        url = f"{self.base_url}/api/v1/internal_bot/admins/{tg_id}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"获取管理员失败: {e}")
            return {"success": False, "message": str(e)}

    async def get_tickets_internal(self, account_id: int = None, admin_id: int = None, ticket_type: str = None, review_status: str = None, limit: int = 10) -> Dict:
        """获取工单列表"""
        url = f"{self.base_url}/api/v1/internal_bot/tickets"
        params = {"limit": limit}
        if account_id: params["account_id"] = account_id
        if admin_id: params["admin_id"] = admin_id
        if ticket_type: params["ticket_type"] = ticket_type
        if review_status: params["review_status"] = review_status
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"获取工单列表失败: {e}")
            return {"success": False, "message": str(e)}

    async def get_ticket_by_id_internal(self, ticket_id: int) -> Dict:
        """根据 ID 获取工单详情"""
        url = f"{self.base_url}/api/v1/internal_bot/tickets/id/{ticket_id}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"获取工单详情失败: {e}")
            return {"success": False, "message": str(e)}

    async def ticket_action_internal(self, ticket_id: int, action: str, admin_tg_id: int, resolution: str = None) -> Dict:
        """执行工单动作 (take/resolve)"""
        url = f"{self.base_url}/api/v1/internal_bot/tickets/{ticket_id}/action"
        payload = {"action": action, "admin_tg_id": admin_tg_id}
        if resolution: payload["resolution"] = resolution
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"操作工单失败: {e}")
            return {"success": False, "message": str(e)}

    async def bind_admin(self, username, password, tg_id):
        """绑定管理员/员工"""
        payload = {"username": username, "password": password, "tg_id": tg_id}
        return await self._post("/admins/bind", json=payload)

    async def get_sms_history_internal(self, account_id: int, limit: int = 10) -> Dict:
        """获取SMS历史记录"""
        url = f"{self.base_url}/api/v1/internal_bot/sms-log"
        params = {"account_id": account_id, "limit": limit}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"获取记录失败: {e}")
            return {"success": False, "message": str(e)}

    async def get_task_categories_internal(self) -> Dict:
        """获取任务分类"""
        url = f"{self.base_url}/api/v1/internal_bot/task-categories"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"获取任务分类失败: {e}")
            return {"success": False, "message": str(e)}

    async def get_sending_stats_internal(self, account_id: int) -> Dict:
        """获取发送统计信息"""
        url = f"{self.base_url}/api/v1/internal_bot/sending-stats"
        params = {"account_id": account_id}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"获取统计失败: {e}")
            return {"success": False, "message": str(e)}

    async def create_mass_task_internal(self, **kwargs) -> Dict:
        """创建群发任务"""
        url = f"{self.base_url}/api/v1/internal_bot/mass-tasks"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=kwargs, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"创建批量任务失败: {e}")
            return {"success": False, "message": str(e)}

    async def get_data_pool_stats_internal(self, account_id: int) -> Dict:
        """获取数据池统计信息"""
        url = f"{self.base_url}/api/v1/internal_bot/data-pool/stats"
        params = {"account_id": account_id}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"获取数据池统计失败: {e}")
            return {"success": False, "message": str(e)}

    async def get_data_pool_count_internal(self, account_id: int, country_code: str) -> Dict:
        """获取指定国家数据数量"""
        url = f"{self.base_url}/api/v1/internal_bot/data-pool/count"
        params = {"account_id": account_id, "country_code": country_code}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"获取数据池计数失败: {e}")
            return {"success": False, "message": str(e)}

    async def create_account_internal(self, biz_type: str, country_code: str, sales_id: int, **kwargs) -> Dict:
        """内部调用的开户接口"""
        url = f"{self.base_url}/api/v1/internal_bot/accounts"
        payload = {
            "biz_type": biz_type,
            "country_code": country_code,
            "sales_id": sales_id,
            **kwargs
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"创建账户失败: {e}")
            return {"success": False, "message": str(e)}

    async def get_sms_approvals(self) -> list:
        """获取待审核短信"""
        url = f"{self.base_url}/api/v1/internal_bot/sms-approvals"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"获取审核列表失败: {e}")
            return []

    async def action_sms_approval(self, approval_id: int, action: str, reason: Optional[str] = None) -> Dict:
        """审核短信操作"""
        url = f"{self.base_url}/api/v1/internal_bot/sms-approvals/{approval_id}/action"
        payload = {"action": action, "reason": reason}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"审核操作失败: {e}")
            return {"success": False, "message": str(e)}

    async def get_sms_approval_detail(self, approval_id: int) -> Dict:
        """获取审核详情"""
        url = f"{self.base_url}/api/v1/internal_bot/sms-approvals/{approval_id}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"获取审核详情失败: {e}")
            return {}

    async def get_test_countries(self, account_id: int) -> str:
        """获取测试国家"""
        url = f"{self.base_url}/api/v1/internal_bot/accounts/{account_id}/test-countries"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self._get_internal_headers())
                data = response.json()
                return data.get("countries", "-")
        except Exception as e:
            logger.error(f"获取测试国家失败: {e}")
            return "-"

    async def get_recharge_orders(self, status: str = 'pending') -> list:
        """获取充值记录"""
        url = f"{self.base_url}/api/v1/internal_bot/recharge-orders"
        params = {"status": status}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"获取充值订单失败: {e}")
            return []

    async def get_tickets(self, status: Optional[str] = None, tg_id: Optional[int] = None) -> list:
        """获取工单列表"""
        url = f"{self.base_url}/api/v1/internal_bot/tickets"
        params = {}
        if status: params["status"] = status
        if tg_id: params["tg_id"] = tg_id
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"获取工单列表失败: {e}")
            return []

    async def review_ticket_internal(self, ticket_no: str, action: str, user_name: str, note: str = None, chat_id: int = None) -> Dict:
        """审核测试工单"""
        url = f"{self.base_url}/api/v1/internal_bot/tickets/{ticket_no}/review"
        payload = {"action": action, "user_name": user_name, "note": note, "chat_id": chat_id}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"审核工单失败: {e}")
            return {"success": False, "message": str(e)}

    async def submit_test_result_internal(self, ticket_no: str, success: bool, user_name: str, note: str = None) -> Dict:
        """提交测试结果"""
        url = f"{self.base_url}/api/v1/internal_bot/tickets/{ticket_no}/test-result"
        payload = {"success": success, "user_name": user_name, "note": note}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"提交测试结果失败: {e}")
            return {"success": False, "message": str(e)}

    async def get_public_data_stats_internal(self, country_code: Optional[str] = None) -> Dict:
        """获取公海数据统计"""
        url = f"{self.base_url}/api/v1/internal_bot/data-pool/public-stats"
        params = {}
        if country_code: params["country_code"] = country_code
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"获取公海统计失败: {e}")
            return {"success": False, "message": str(e)}

    async def extract_data_internal(self, tg_id: int, country_code: str, count: int) -> Dict:
        """提取公海数据到私有库"""
        url = f"{self.base_url}/api/v1/internal_bot/data-pool/extract"
        payload = {"tg_id": tg_id, "country_code": country_code, "count": count}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # 显式使用 post 而不是 get
                response = await client.post(url, json=payload, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"提取数据失败: {e}")
            return {"success": False, "message": str(e)}

    async def register_internal(self, name: str, email: str, password: str, tg_id: int, tg_username: Optional[str] = None) -> Dict:
        """从 Bot 注册新账户"""
        url = f"{self.base_url}/api/v1/internal_bot/register"
        payload = {
            "name": name,
            "email": email,
            "password": password,
            "tg_id": tg_id,
            "tg_username": tg_username
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"注册账户失败: {e}")
            return {"success": False, "message": str(e)}

    async def get_template_internal(self, template_id: int) -> Dict:
        """获取账户模板详情"""
        url = f"{self.base_url}/api/v1/internal_bot/templates/{template_id}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"获取模板详情失败: {e}")
            return {"success": False, "message": str(e)}

    async def review_sms_approval_internal(self, approval_id: int, approved: bool, admin_tg_id: int = None) -> Dict:
        """处理短信内容审核"""
        url = f"{self.base_url}/api/v1/internal_bot/sms-approvals/review"
        payload = {
            "approval_id": approval_id,
            "approved": approved,
            "admin_tg_id": admin_tg_id
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"审核短信内容失败: {e}")
            return {"success": False, "message": str(e)}

    async def get_sms_approval_internal(self, approval_id: int) -> Dict:
        """获取短信审核详情"""
        url = f"{self.base_url}/api/v1/internal_bot/sms-approvals/{approval_id}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"获取短信审核详情失败: {e}")
            return {"success": False, "message": str(e)}

    async def review_recharge_order_internal(self, order_id: int, approved: bool, admin_tg_id: int) -> Dict:
        """处理充值审批"""
        url = f"{self.base_url}/api/v1/internal_bot/recharge-orders/{order_id}/review"
        payload = {
            "approved": approved,
            "admin_tg_id": admin_tg_id
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"审批充值失败: {e}")
            return {"success": False, "message": str(e)}

    async def finalize_sms_send_internal(self, approval_id: int, message_id: str = None, error: str = None) -> Dict:
        """更新发送状态"""
        url = f"{self.base_url}/api/v1/internal_bot/sms-approvals/{approval_id}/finalize-send"
        payload = {
            "message_id": message_id,
            "error": error
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"更新发送状态失败: {e}")
            return {"success": False, "message": str(e)}

    async def get_test_countries_internal(self, account_id: int) -> Dict:
        """获取账户测试国家"""
        url = f"{self.base_url}/api/v1/internal_bot/accounts/{account_id}/test-countries"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"获取测试国家失败: {e}")
            return {"countries": "-"}

    async def get_system_stats_internal(self) -> Dict:
        """获取系统统计信息"""
        url = f"{self.base_url}/api/v1/internal_bot/system-stats"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"获取系统统计失败: {e}")
            return {}

    async def get_sales_stats_internal(self, tg_id: int) -> Dict:
        """获取销售统计信息"""
        url = f"{self.base_url}/api/v1/internal_bot/sales-stats"
        params = {"tg_id": tg_id}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params, headers=self._get_internal_headers())
                return response.json()
        except Exception as e:
            logger.error(f"获取销售统计失败: {e}")
            return {}

    async def get_customer_balance(self, tg_id: int):
        """获取客户余额"""
        return await self._get(f"/customer/balance/{tg_id}")

    async def get_customer_sms_stats(self, tg_id: int):
        """获取客户最近7天短信统计"""
        return await self._get(f"/customer/sms-stats/{tg_id}")

    async def get_sales_customers(self, admin_id: int, biz_type: str = 'all', page: int = 0):
        """获取销售名下的客户列表"""
        params = {"biz_type": biz_type, "page": page}
        return await self._get(f"/sales/customers/{admin_id}", params=params)

    async def sync_okcc_balance(self, account_id: int):
        """同步 OKCC 余额"""
        return await self._post(f"/customer/sync-okcc/{account_id}")

    async def get_account_detail(self, account_id: int):
        """获取账户详情"""
        return await self._get(f"/account-detail/{account_id}")

    async def get_account_pricing(self, account_id: int):
        """获取账户资费详情"""
        return await self._get(f"/account-pricing/{account_id}")

    async def get_account_bindings(self, account_id: int):
        """获取账户绑定的 Telegram 用户"""
        return await self._get(f"/account-bindings/{account_id}")

    async def get_knowledge_articles(self, category: str = None):
        """获取知识库文章列表"""
        params = {"category": category} if category else {}
        return await self._get("/knowledge/articles", params=params)

    async def get_knowledge_article(self, article_id: int):
        """获取知识库文章详情"""
        return await self._get(f"/knowledge/articles/{article_id}")

    async def get_knowledge_attachment(self, att_id: int):
        """获取知识库附件详情"""
        return await self._get(f"/knowledge/attachments/{att_id}")

    async def get_pricing_countries(self, biz_type: str):
        """获取有报价的国家列表"""
        return await self._get(f"/pricing/countries/{biz_type}")

    async def bind_admin(self, tg_id: int, invite_code: str):
        """绑定管理员/员工"""
        return await self._post("/admin/bind", json={"tg_id": tg_id, "invite_code": invite_code})

    async def get_customer_info(self, tg_id: int):
        """获取客户账户信息"""
        return await self._get("/customer/info", params={"tg_id": tg_id})

    async def get_user_role(self, tg_id: int):
        """获取用户角色 (admin/sales/customer/guest等)"""
        return await self._get("/user/role", params={"tg_id": tg_id})

    async def bulk_validate(self, account_id: int, content: str, phones: list):
        """批量短信预审"""
        return await self._post("/bulk/validate", json={
            "account_id": account_id,
            "content": content,
            "phones": phones
        })

    async def create_mass_task(self, account_id: int, content: str, phone_numbers: list, total_cost: float, sender_id: str = None, extra_data: dict = None):
        """创建群发任务"""
        return await self._post("/mass-tasks", json={
            "account_id": account_id,
            "content": content,
            "phone_numbers": phone_numbers,
            "total_cost": total_cost,
            "sender_id": sender_id,
            "extra_data": extra_data or {}
        })

    async def get_test_countries_internal(self, account_id: int):
        """获取账户可测试的国家"""
        return await self._get(f"/account-test-countries/{account_id}")

    async def get_supplier_group_internal(self, account_id: int):
        """获取账户对应的供应商群组 ID"""
        return await self._get(f"/account-supplier-group/{account_id}")

    async def create_recharge_order(self, account_id: int, amount: float, proof: Optional[str] = None):
        """提交充值工单"""
        payload = {"account_id": account_id, "amount": amount, "proof": proof}
        return await self._post("/recharge-order", json=payload)

    async def get_pending_recharges(self):
        """获取待审核充值列表"""
        return await self._get("/recharge-orders/pending")

    async def audit_recharge_order(self, order_id: int, status: str, admin_id: int, remark: str = ""):
        """审核充值工单"""
        payload = {"status": status, "admin_id": admin_id, "remark": remark}
        return await self._post(f"/recharge-order/{order_id}/audit", json=payload)

    async def bind_sales(self, username, password, tg_id):
        """绑定销售账号"""
        payload = {"username": username, "password": password, "tg_id": tg_id}
        return await self._post("/sales/bind", json=payload)

    async def get_sales_templates(self, biz_type: Optional[str] = None, country_code: Optional[str] = None):
        """获取销售可用模板"""
        params = {}
        if biz_type: params["biz_type"] = biz_type
        if country_code: params["country_code"] = country_code
        return await self._get("/sales/templates", params=params)

    async def create_invitation(self, sales_id: int, config: dict, valid_hours: int = 72):
        """创建邀请码"""
        payload = {"sales_id": sales_id, "config": config, "valid_hours": valid_hours}
        return await self._post("/sales/invitation", json=payload)

    async def activate_invitation(self, code: str, tg_id: int, tg_username: str = None, tg_first_name: str = None):
        """激活邀请码"""
        payload = {
            "code": code,
            "tg_id": tg_id,
            "tg_username": tg_username,
            "tg_first_name": tg_first_name
        }
        return await self._post("/invitation/activate", json=payload)

    async def get_sales_stats(self, sales_id: int):
        """获取销售业绩统计"""
        return await self._get(f"/sales/stats/{sales_id}")

    async def get_user_bindings(self, tg_id: int):
        """获取用户绑定的所有账户"""
        return await self._get(f"/user/bindings/{tg_id}")

    async def switch_account(self, tg_id: int, account_id: int):
        """切换当前活跃账户"""
        payload = {"tg_id": tg_id, "account_id": account_id}
        return await self._post("/user/switch-account", json=payload)

    async def bind_account_by_code(self, code: str, tg_id: int, username: str = None):
        """通过验证码绑定账户"""
        payload = {"code": code, "tg_id": tg_id, "username": username}
        return await self._post("/user/bind-by-code", json=payload)

    async def get_system_config(self) -> dict:
        """获取系统配置"""
        return await self._get("/system/config")

    async def submit_sms_approval(self, tg_id: int, account_id: int, content: str, phone: str = None, sms_submit_mode: str = "direct") -> dict:
        """提交短信内容审核"""
        payload = {
            "tg_id": tg_id,
            "account_id": account_id,
            "content": content,
            "phone": phone,
            "sms_submit_mode": sms_submit_mode
        }
        return await self._post("/sms/submit-approval", json=payload)
    async def get_knowledge_articles(self, category: Optional[str] = None):
        """获取知识库文章列表"""
        params = {}
        if category: params["category"] = category
        return await self._get("/knowledge", params=params)

    async def get_knowledge_article(self, article_id: int):
        """获取知识库文章详情"""
        return await self._get(f"/knowledge/{article_id}")

    async def get_knowledge_attachment(self, attachment_id: int):
        """获取知识库附件元数据"""
        return await self._get(f"/knowledge/attachment/{attachment_id}")
