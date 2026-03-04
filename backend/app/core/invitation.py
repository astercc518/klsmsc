"""
邀请与开户服务 - 支持多业务类型自动开户
"""
import json
import secrets
import string
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.common.invitation_code import InvitationCode
from app.modules.common.account import Account
from app.modules.common.account_pricing import AccountPricing
from app.modules.common.telegram_binding import TelegramBinding
from app.modules.common.telegram_user import TelegramUser
from app.modules.voice.voice_account import VoiceAccount
from app.utils.logger import get_logger

logger = get_logger(__name__)

class InvitationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _generate_code(self, length=8) -> str:
        """生成随机邀请码"""
        chars = string.ascii_uppercase + string.digits
        return ''.join(secrets.choice(chars) for _ in range(length))

    async def create_code(
        self, 
        sales_id: int, 
        pricing_config: Dict, 
        valid_hours: int = 24
    ) -> str:
        """
        生成邀请码
        pricing_config example: {"business_type": "sms", "country": "CN", "price": 0.06}
        """
        code = self._generate_code()
        # 确保唯一性逻辑略（几率极低）
        
        invite = InvitationCode(
            code=code,
            sales_id=sales_id,
            pricing_config=pricing_config, # SQLAlchemy JSON type handles dict automatically
            status="unused",
            expires_at=datetime.now() + timedelta(hours=valid_hours)
        )
        self.db.add(invite)
        await self.db.commit()
        return code

    async def get_valid_code(self, code_str: str) -> Optional[InvitationCode]:
        """获取并校验邀请码"""
        result = await self.db.execute(
            select(InvitationCode).where(InvitationCode.code == code_str)
        )
        invite = result.scalar_one_or_none()
        
        if not invite:
            return None
            
        if invite.status != 'unused':
            return None
            
        if invite.expires_at and invite.expires_at < datetime.now():
            return None
            
        return invite

    async def activate_code(self, code_str: str, tg_id: int) -> Tuple[Optional[Account], str, Dict[str, Any]]:
        """
        激活邀请码：创建账户、绑定TG、应用定价
        对于语音/数据业务，自动创建外部系统账户
        
        Returns: (Account, Plain API Key, Extra Info)
        """
        invite = await self.get_valid_code(code_str)
        if not invite:
            raise ValueError("无效或已过期的邀请码")
        
        # 解析配置
        config = invite.pricing_config
        if isinstance(config, str):
            config = json.loads(config)
        
        business_type = config.get('business_type', 'sms')
        country_code = config.get('country', 'global')
        template_id = config.get('template_id')
        
        # 1. 创建账户
        api_key_plain = secrets.token_hex(32)
        account_name = f"TG_{tg_id}_{secrets.token_hex(2)}"
        
        new_account = Account(
            account_name=account_name,
            sales_id=invite.sales_id,
            status='active',
            balance=0,
            api_key=api_key_plain,
            rate_limit=1000
        )
        self.db.add(new_account)
        await self.db.flush()  # 获取 ID
        
        # 2. 绑定 TG
        binding = TelegramBinding(
            tg_id=tg_id,
            account_id=new_account.id,
            is_active=True
        )
        self.db.add(binding)
        
        # 3. 应用定价配置
        pricing = AccountPricing(
            account_id=new_account.id,
            country_code=country_code,
            business_type=business_type,
            price=config.get('price', 0.05)
        )
        self.db.add(pricing)
        
        # 4. 额外信息（用于返回给用户）
        extra_info = {
            "business_type": business_type,
            "country_code": country_code
        }
        
        # 5. 根据业务类型创建外部系统账户
        if business_type == 'voice':
            voice_info = await self._create_voice_account(
                new_account, country_code, template_id
            )
            extra_info['voice'] = voice_info
            
        elif business_type == 'data':
            data_info = await self._create_data_account(
                new_account, country_code, template_id
            )
            extra_info['data'] = data_info
        
        # 6. 更新邀请码状态
        invite.status = 'used'
        invite.used_by_account_id = new_account.id
        invite.used_at = datetime.now()
        
        await self.db.commit()
        
        return new_account, api_key_plain, extra_info
    
    async def _create_voice_account(
        self, 
        account: Account, 
        country_code: str,
        template_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        创建语音账户（对接OKCC系统）
        """
        from app.services.okcc_client import get_okcc_client
        
        okcc = get_okcc_client()
        
        try:
            # 调用OKCC创建账户
            result = await okcc.create_account({
                'account_name': account.account_name,
                'country_code': country_code,
            })
            
            if result.get('success'):
                data = result.get('data', {})
                
                # 创建本地语音账户记录
                voice_account = VoiceAccount(
                    account_id=account.id,
                    okcc_account=data.get('account'),
                    okcc_password=data.get('password'),  # 实际应加密存储
                    external_id=data.get('external_id'),
                    country_code=country_code,
                    template_id=template_id,
                    status='active',
                    balance=0
                )
                self.db.add(voice_account)
                
                logger.info(f"语音账户创建成功: {account.account_name} -> OKCC:{data.get('account')}")
                
                return {
                    "success": True,
                    "okcc_account": data.get('account'),
                    "okcc_password": data.get('password'),
                    "message": "语音账户已创建，请使用以上信息登录OKCC系统"
                }
            else:
                logger.error(f"OKCC账户创建失败: {result.get('message')}")
                return {
                    "success": False,
                    "message": f"语音账户创建失败: {result.get('message')}"
                }
                
        except Exception as e:
            logger.error(f"创建语音账户异常: {e}")
            return {
                "success": False,
                "message": f"语音账户创建异常: {str(e)}"
            }
    
    async def _create_data_account(
        self,
        account: Account,
        country_code: str,
        template_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        创建数据账户（对接数据平台）
        """
        from app.services.data_platform_client import get_data_platform_client
        
        try:
            client = get_data_platform_client()
            
            result = await client.create_account({
                'account_name': account.account_name,
                'country_code': country_code,
            })
            
            if result.get('success'):
                data = result.get('data', {})
                
                # 创建本地数据账户记录（稍后实现模型）
                logger.info(f"数据账户创建成功: {account.account_name}")
                
                return {
                    "success": True,
                    "platform_account": data.get('account'),
                    "message": "数据账户已创建"
                }
            else:
                return {
                    "success": False,
                    "message": f"数据账户创建失败: {result.get('message')}"
                }
                
        except Exception as e:
            logger.error(f"创建数据账户异常: {e}")
            return {
                "success": False,
                "message": f"数据账户创建异常: {str(e)}"
            }
