"""
HTTP通道适配器
"""
import httpx
import json
from typing import Dict, Optional
from app.modules.sms.sms_log import SMSLog
from app.modules.sms.channel import Channel
from app.utils.logger import get_logger
from app.utils.phone_utils import format_sms_dest_phone, strip_leading_plus_enabled

logger = get_logger(__name__)


class HTTPAdapter:
    """HTTP通道适配器"""
    
    def __init__(self, channel: Channel):
        self.channel = channel
        self.config = self._parse_config()
    
    def _parse_config(self) -> dict:
        """解析通道配置"""
        # config_json 字段可能不存在，使用 getattr 安全访问
        config_json = getattr(self.channel, 'config_json', None)
        if config_json:
            try:
                return json.loads(config_json)
            except:
                return {}
        return {}

    def _dest_phone_for_payload(self, phone: str | None) -> str:
        """按通道 config_json.strip_leading_plus 格式化目的号码。"""
        return format_sms_dest_phone(
            phone,
            strip_leading_plus=strip_leading_plus_enabled(self.config),
        )

    async def send(self, sms_log: SMSLog) -> tuple[bool, Optional[str], Optional[str]]:
        """
        发送短信
        
        Returns:
            (成功标志, 通道消息ID, 错误信息)
        """
        try:
            logger.info(f"HTTP适配器发送: {sms_log.message_id} via {self.channel.channel_code}")
            
            # 构造请求
            payload = self._build_payload(sms_log)
            headers = self._build_headers()
            
            logger.info(f"发送payload: {json.dumps(payload, ensure_ascii=False)}")
            logger.info(f"API地址: {self.channel.api_url}")
            
            # 发送请求
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.channel.api_url,
                    json=payload,
                    headers=headers
                )
                
                logger.info(f"HTTP响应: {response.status_code}")
                logger.info(f"响应内容: {response.text[:500] if response.text else 'empty'}")
                
                if response.status_code in [200, 201]:
                    try:
                        result = response.json()
                    except:
                        result = {"raw_response": response.text}
                    
                    # 检查业务层面是否成功
                    if self._check_response_success(result):
                        channel_message_id = self._extract_message_id(result)
                        logger.info(f"发送成功: {sms_log.message_id}, 通道消息ID: {channel_message_id}, 响应: {result}")
                        return True, channel_message_id, None
                    else:
                        # HTTP 200 但业务失败
                        error_msg = f"业务错误: {json.dumps(result, ensure_ascii=False)}"
                        logger.error(f"发送失败: {error_msg}")
                        return False, None, error_msg
                else:
                    error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                    logger.error(f"发送失败: {error_msg}")
                    return False, None, error_msg
                    
        except httpx.TimeoutException:
            error_msg = "Request timeout"
            logger.error(f"请求超时: {sms_log.message_id}")
            return False, None, error_msg
        except Exception as e:
            error_msg = str(e)
            logger.error(f"发送异常: {error_msg}", exc_info=e)
            return False, None, error_msg
    
    def _build_payload(self, sms_log: SMSLog) -> dict:
        """构造请求payload"""
        # 根据通道配置或API地址自动检测格式
        template = self.config.get('payload_template', 'auto')
        
        # 自动检测：根据api_url判断通道类型
        if template == 'auto':
            api_url = self.channel.api_url or ''
            if 'kaola' in api_url.lower():
                template = 'kaola'
            elif 'twilio' in api_url.lower():
                template = 'twilio'
            elif 'nexmo' in api_url.lower():
                template = 'nexmo'
            else:
                template = 'default'
        
        # SMSLog 模型无 sender_id 字段，优先从 channel 配置获取
        sender = getattr(sms_log, 'sender_id', None) or self.channel.default_sender_id or ''

        if template == 'kaola':
            account = (self.channel.username or '').strip()
            password = (self.channel.password or self.channel.api_key or '').strip()
            mobile = self._dest_phone_for_payload(sms_log.phone_number)
            return {
                "action": "send",
                "account": account,
                "password": password,
                "mobile": mobile,
                "content": sms_log.message,
                "extno": sender,
            }
        elif template == 'twilio':
            return {
                "To": self._dest_phone_for_payload(sms_log.phone_number),
                "From": sender,
                "Body": sms_log.message,
            }
        elif template == 'nexmo':
            return {
                "to": self._dest_phone_for_payload(sms_log.phone_number),
                "from": sender,
                "text": sms_log.message,
            }
        else:
            return {
                "phone_number": self._dest_phone_for_payload(sms_log.phone_number),
                "message": sms_log.message,
                "sender_id": sender,
                "message_id": sms_log.message_id,
            }
    
    def _build_headers(self) -> dict:
        """构造请求头"""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "SMSC-Gateway/1.0"
        }
        
        # API Key认证
        if self.channel.api_key:
            auth_type = self.config.get('auth_type', 'bearer')
            if auth_type == 'bearer':
                headers["Authorization"] = f"Bearer {self.channel.api_key}"
            elif auth_type == 'basic':
                import base64
                credentials = f"{self.channel.username}:{self.channel.api_key}"
                encoded = base64.b64encode(credentials.encode()).decode()
                headers["Authorization"] = f"Basic {encoded}"
            elif auth_type == 'header':
                key_name = self.config.get('auth_header_name', 'X-API-Key')
                headers[key_name] = self.channel.api_key
        
        # 自定义头
        custom_headers = self.config.get('custom_headers', {})
        headers.update(custom_headers)
        
        return headers
    
    def _extract_message_id(self, response: dict) -> Optional[str]:
        """从响应中提取消息ID"""
        # 尝试常见的字段名
        for key in ['message_id', 'messageId', 'id', 'sid', 'msg_id', 'taskid', 'msgid']:
            if key in response:
                return str(response[key])
        
        # 检查嵌套结构
        if 'data' in response and isinstance(response['data'], dict):
            for key in ['message_id', 'id', 'taskid']:
                if key in response['data']:
                    return str(response['data'][key])
        
        # Kaola格式：从list中提取
        if 'list' in response and isinstance(response['list'], list) and len(response['list']) > 0:
            item = response['list'][0]
            if isinstance(item, dict):
                for key in ['msgid', 'id', 'taskid']:
                    if key in item:
                        return str(item[key])
        
        return None
    
    def _check_response_success(self, response: dict) -> bool:
        """检查响应是否表示成功"""
        # Kaola格式：status=0 表示成功
        if 'status' in response:
            return response['status'] == 0
        
        # 其他常见格式
        if 'code' in response:
            return response['code'] in [0, 200, '0', '200', 'OK', 'success']
        if 'success' in response:
            return response['success'] == True
        if 'result' in response:
            return response['result'] in [0, 'success', 'ok', True]
        
        # 默认认为成功（HTTP 200 已经通过了）
        return True

