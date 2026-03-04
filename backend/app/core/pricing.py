"""
计费引擎模块
"""
from decimal import Decimal
from typing import Dict, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.sms.country_pricing import CountryPricing
from app.modules.common.account_pricing import AccountPricing
from app.modules.common.account import Account
from app.modules.sms.channel import Channel
from app.modules.common.balance_log import BalanceLog
from app.utils.errors import InsufficientBalanceError, PricingNotFoundError
from app.utils.logger import get_logger
from app.utils.cache import get_cache_manager
import json

logger = get_logger(__name__)


class PricingEngine:
    """计费引擎"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def calculate_and_charge(
        self,
        account_id: int,
        channel_id: int,
        country_code: str,
        message: str,
        mnc: Optional[str] = None
    ) -> Dict:
        """
        计算费用并扣款
        """
        try:
            # 1. 计算短信条数
            message_count = self._count_sms_parts(message)
            logger.debug(f"短信条数: {message_count}")
            
            # 2. 查询销售价格 (Selling Price) - 传入 account_id
            price_info = await self.get_price(channel_id, country_code, mnc, account_id)
            if not price_info:
                raise PricingNotFoundError(country_code, channel_id)
            
            price_per_sms = Decimal(str(price_info['price']))
            currency = price_info['currency']
            
            # 3. 查询成本价格 (Cost Price) - 从通道基础费率获取
            channel_result = await self.db.execute(
                select(Channel).where(Channel.id == channel_id)
            )
            channel = channel_result.scalar_one_or_none()
            base_cost_per_sms = channel.cost_rate if channel and channel.cost_rate else Decimal('0.0000')
            
            # 4. 计算总费用
            total_sell_price = price_per_sms * message_count
            total_base_cost = base_cost_per_sms * message_count
            
            logger.info(f"计费: Sell={total_sell_price}, Cost={total_base_cost}")
            
            # 5. 获取账户并检查余额（带缓存）
            cache_manager = await get_cache_manager()
            balance_cache_key = f"account:{account_id}:balance"
            
            # 尝试从缓存获取余额
            cached_balance = await cache_manager.get(balance_cache_key)
            account = None
            
            if cached_balance is not None:
                cached_balance_value = Decimal(str(cached_balance))
                if cached_balance_value < total_sell_price:
                    raise InsufficientBalanceError(
                        required=float(total_sell_price),
                        available=float(cached_balance_value)
                    )
            
            # 从数据库查询账户
            result = await self.db.execute(
                select(Account).where(Account.id == account_id)
            )
            account = result.scalar_one_or_none()
            
            if not account:
                return {'success': False, 'error': 'Account not found'}
            
            if account.balance < total_sell_price:
                raise InsufficientBalanceError(
                    required=float(total_sell_price),
                    available=float(account.balance)
                )
            
            # 6. 扣减余额
            account.balance -= total_sell_price
            
            # 7. 记录余额变动
            balance_log = BalanceLog(
                account_id=account_id,
                change_type='charge',
                amount=-total_sell_price,
                balance_after=account.balance,
                description=f"SMS charge: {message_count} parts to {country_code} ({currency})"
            )
            self.db.add(balance_log)
            
            await self.db.commit()
            
            # 更新余额缓存
            await cache_manager.set(balance_cache_key, float(account.balance), ttl=60)
            
            return {
                'success': True,
                'total_cost': float(total_sell_price),
                'total_base_cost': float(total_base_cost),
                'message_count': message_count,
                'price_per_sms': float(price_per_sms),
                'base_cost_per_sms': float(base_cost_per_sms),
                'currency': currency,
                'balance_after': float(account.balance)
            }
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"扣款失败: {str(e)}", exc_info=e)
            raise
    
    async def get_price(
        self,
        channel_id: int,
        country_code: str,
        mnc: Optional[str] = None,
        account_id: Optional[int] = None
    ) -> Optional[Dict]:
        """
        查询销售价格
        优先级：账户统一单价 > 账户专属国家定价 > 国家级定价
        """
        cache_manager = await get_cache_manager()
        # 缓存Key增加 account_id
        cache_key = f"price:{account_id or 'all'}:{channel_id}:{country_code}:{mnc or 'default'}"
        
        cached = await cache_manager.get(cache_key)
        if cached is not None:
            return cached
        
        # 1. 检查账户统一单价 (Account Unit Price) - 最高优先级
        if account_id:
            result = await self.db.execute(
                select(Account).where(Account.id == account_id)
            )
            account = result.scalar_one_or_none()
            
            if account and account.unit_price and float(account.unit_price) > 0:
                price_info = {
                    'price': float(account.unit_price),
                    'currency': account.currency or 'USD',
                    'source': 'account_unit_price'
                }
                logger.info(f"使用账户统一单价: account={account_id}, price={account.unit_price}")
                await cache_manager.set(cache_key, price_info, ttl=3600)
                return price_info
            
        # 2. 检查账户专属国家定价 (Account Specific Country Pricing)
        if account_id:
            query = select(AccountPricing).where(
                AccountPricing.account_id == account_id,
                AccountPricing.country_code == country_code,
                AccountPricing.business_type == 'sms'
            )
            result = await self.db.execute(query)
            acc_pricing = result.scalar_one_or_none()
            
            if acc_pricing:
                price_info = {
                    'price': float(acc_pricing.price),
                    'currency': 'USD',
                    'source': 'account_country_pricing'
                }
                await cache_manager.set(cache_key, price_info, ttl=3600)
                return price_info
        
        # 3. 国家级定价 (Country Level)
        query = select(CountryPricing).where(
            CountryPricing.channel_id == channel_id,
            CountryPricing.country_code == country_code
        ).order_by(CountryPricing.effective_date.desc()).limit(1)
        
        result = await self.db.execute(query)
        pricing = result.scalar_one_or_none()
        
        if pricing:
            price_info = {
                'price': float(pricing.price_per_sms),
                'currency': pricing.currency,
                'country': pricing.country_name
            }
            await cache_manager.set(cache_key, price_info, ttl=3600)
            return price_info
        
        return None
    
    def _count_sms_parts(self, message: str) -> int:
        """计算短信条数"""
        if self._is_gsm7(message):
            if len(message) <= 160:
                return 1
            else:
                return (len(message) + 152) // 153
        else:
            if len(message) <= 70:
                return 1
            else:
                return (len(message) + 66) // 67
    
    def _is_gsm7(self, message: str) -> bool:
        gsm7_chars = set(
            "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
            "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
        )
        return all(c in gsm7_chars for c in message)
