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
from app.modules.common.account import Account, AccountChannel
from app.modules.common.account_pricing import AccountPricing
from app.modules.common.account_template import AccountTemplate
from app.modules.common.telegram_binding import TelegramBinding
from app.modules.common.telegram_user import TelegramUser
from app.core.auth import AuthService
from app.utils.logger import get_logger

logger = get_logger(__name__)

class InvitationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _generate_code(self, length=8) -> str:
        """生成随机邀请码"""
        chars = string.ascii_uppercase + string.digits
        return ''.join(secrets.choice(chars) for _ in range(length))

    async def _gen_account_name(self, sales_id: int, country_code: str) -> str:
        """生成账户名: TG{员工工号数字}{国家区号3位}V{序号02d}，确保全局唯一"""
        import re as _re
        from sqlalchemy import func as _func
        from app.utils.country_code import get_dial_code
        from app.modules.common.admin_user import AdminUser
        from app.modules.common.account import Account

        admin_username = (await self.db.execute(
            select(AdminUser.username).where(AdminUser.id == sales_id)
        )).scalar_one_or_none() or ""
        m = _re.search(r'\d+$', admin_username)
        num_part = m.group(0) if m else ""

        cc = (country_code or "").upper()
        if cc == "GLOBAL":
            cc = ""
        dial = get_dial_code(cc) if cc else "000"

        prefix = f"TG{num_part}{dial}V"

        # 查已存在的同前缀账户最大序号（含已删除），确保序号单调递增不重用
        existing = (await self.db.execute(
            select(Account.account_name).where(
                Account.account_name.like(f"{prefix}%")
            )
        )).scalars().all()

        used_seqs = set()
        for name in existing:
            suffix = name[len(prefix):]
            if suffix.isdigit():
                used_seqs.add(int(suffix))

        seq = 1
        while seq in used_seqs:
            seq += 1

        return f"{prefix}{seq:02d}"

    async def create_code(
        self, 
        sales_id: int, 
        pricing_config: Dict, 
        valid_hours: int = 72
    ) -> str:
        """
        生成邀请码（默认 72 小时有效期）
        pricing_config example: {"business_type": "sms", "country": "PH", "price": 0.035}
        """
        for _ in range(5):
            code = self._generate_code()
            existing = await self.db.execute(
                select(InvitationCode).where(InvitationCode.code == code)
            )
            if not existing.scalar_one_or_none():
                break

        invite = InvitationCode(
            code=code,
            sales_id=sales_id,
            pricing_config=pricing_config,
            status="unused",
            expires_at=datetime.now() + timedelta(hours=valid_hours),
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

    async def activate_code(
        self,
        code_str: str,
        tg_id: int,
        tg_username: Optional[str] = None,
        tg_first_name: Optional[str] = None,
    ) -> Tuple[Optional[Account], str, Dict[str, Any]]:
        """
        激活邀请码：创建账户、绑定TG、应用定价
        自动设置 tg_id / tg_username 并创建 TelegramUser

        Returns: (Account, Plain API Key, Extra Info)
        """
        invite = await self.get_valid_code(code_str)
        if not invite:
            raise ValueError("无效或已过期的邀请码")

        config = invite.pricing_config
        if isinstance(config, str):
            config = json.loads(config)

        business_type = config.get('business_type', 'sms')
        country_code = config.get('country', 'global')
        template_id = config.get('template_id')

        # 1. 创建账户（含登录密码）
        api_key_plain = secrets.token_hex(32)
        login_password = secrets.token_urlsafe(10)
        account_name = await self._gen_account_name(invite.sales_id, country_code)

        # 根据业务类型构建 services（短信账户默认同步开通数据服务）
        svc_list = [business_type]
        if business_type == 'sms' and 'data' not in svc_list:
            svc_list.append('data')

        # 新开短信账户默认赠送 1 USD
        initial_balance = 1.0 if business_type == 'sms' else 0.0

        new_account = Account(
            account_name=account_name,
            sales_id=invite.sales_id,
            status='active',
            balance=initial_balance,
            api_key=api_key_plain,
            password_hash=AuthService.hash_password(login_password),
            rate_limit=1000,
            business_type=business_type,
            services=','.join(svc_list),
            country_code=country_code if country_code != 'global' else None,
            unit_price=config.get('price', 0.05),
            tg_id=tg_id,
            tg_username=tg_username,
        )
        self.db.add(new_account)
        await self.db.flush()

        # 新开短信账户赠送 1U：记录余额日志
        if initial_balance > 0:
            from app.modules.common.balance_log import BalanceLog
            self.db.add(BalanceLog(
                account_id=new_account.id,
                change_type='deposit',
                amount=initial_balance,
                balance_after=initial_balance,
                description='新开短信账户赠送',
            ))

        # 2. 将该 TG 用户的旧绑定全部置为非活跃，再创建新绑定
        from sqlalchemy import update as sa_update
        await self.db.execute(
            sa_update(TelegramBinding)
            .where(TelegramBinding.tg_id == tg_id)
            .values(is_active=False)
        )
        binding = TelegramBinding(
            tg_id=tg_id,
            account_id=new_account.id,
            is_active=True,
        )
        self.db.add(binding)

        # 3. 创建 / 更新 TelegramUser
        result = await self.db.execute(
            select(TelegramUser).where(TelegramUser.tg_id == tg_id)
        )
        tg_user = result.scalar_one_or_none()
        if tg_user:
            tg_user.account_id = new_account.id
            tg_user.first_name = tg_first_name
            tg_user.username = tg_username
        else:
            tg_user = TelegramUser(
                tg_id=tg_id,
                username=tg_username,
                first_name=tg_first_name,
                account_id=new_account.id,
            )
            self.db.add(tg_user)

        # 4. 应用定价配置
        pricing = AccountPricing(
            account_id=new_account.id,
            country_code=country_code,
            business_type=business_type,
            price=config.get('price', 0.05),
        )
        self.db.add(pricing)

        # 5. 根据模板绑定通道
        if template_id:
            try:
                tpl_result = await self.db.execute(
                    select(AccountTemplate).where(AccountTemplate.id == template_id)
                )
                template = tpl_result.scalar_one_or_none()
                if template and template.channel_ids:
                    ch_ids = template.channel_ids
                    if isinstance(ch_ids, str):
                        ch_ids = json.loads(ch_ids)
                    for idx, ch_id in enumerate(ch_ids):
                        ac = AccountChannel(
                            account_id=new_account.id,
                            channel_id=int(ch_id),
                            is_default=(idx == 0),
                            priority=idx,
                        )
                        self.db.add(ac)
                    logger.info(f"账户 {new_account.id} 绑定通道: {ch_ids}")
            except Exception as e:
                logger.warning(f"绑定模板通道失败: {e}")

        # 6. 同步创建数据账户（短信账户默认开通数据服务）
        if 'data' in new_account.services:
            try:
                from app.modules.data.data_account import DataAccount
                da = DataAccount(
                    account_id=new_account.id,
                    country_code=country_code if country_code != 'global' else '',
                    balance=0,
                    total_extracted=0,
                    total_spent=0,
                    status='active',
                )
                self.db.add(da)
            except Exception as e:
                logger.warning(f"自动创建数据账户失败: {e}")

        # 6. 额外信息（含登录凭据，仅首次返回）
        extra_info = {
            "business_type": business_type,
            "country_code": country_code,
            "template_name": config.get('template_name', ''),
            "login_account": account_name,
            "login_password": login_password,
        }


        # 7. 更新邀请码状态
        invite.status = 'used'
        invite.used_by_account_id = new_account.id
        invite.used_at = datetime.now()

        await self.db.commit()

        return new_account, api_key_plain, extra_info
    
    
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
