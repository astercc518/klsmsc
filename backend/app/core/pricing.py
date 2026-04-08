"""
计费引擎模块
"""
from decimal import Decimal
from typing import Dict, List, Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.sms.country_pricing import CountryPricing
from app.modules.common.account_pricing import AccountPricing
from app.modules.common.account import Account
from app.modules.sms.channel import Channel
from app.modules.sms.supplier import SupplierChannel, SupplierRate
from app.modules.common.balance_log import BalanceLog
from app.utils.errors import InsufficientBalanceError, PricingNotFoundError
from app.utils.sms_segment import count_sms_parts as _count_sms_parts_impl
from app.utils.sms_segment import is_gsm7_message as _is_gsm7_impl
from app.utils.country_code import get_country_variants, normalize_country_code
from app.utils.logger import get_logger
from app.utils.cache import get_cache_manager
import json

logger = get_logger(__name__)


class PricingEngine:
    """计费引擎"""
    
    def __init__(self, db: AsyncSession):
        self.db = db

    async def resolve_base_cost_per_sms(
        self,
        channel_id: int,
        country_code: str,
        channel: Optional[Channel] = None,
    ) -> Decimal:
        """
        解析上游成本单价（每条）。
        优先级：SupplierRate（通道关联供应商 + 国家 + sms）> Channel.cost_rate > 0。
        使用 get_country_variants() 做 ISO2/区号/中文名 全等价匹配。
        """
        if channel is None:
            ch_row = await self.db.execute(select(Channel).where(Channel.id == channel_id))
            channel = ch_row.scalar_one_or_none()

        codes = get_country_variants(country_code)
        if codes:
            sc_row = await self.db.execute(
                select(SupplierChannel.supplier_id).where(
                    SupplierChannel.channel_id == channel_id,
                    SupplierChannel.status == 'active',
                )
            )
            supplier_ids = [r[0] for r in sc_row.all()]
            for sid in supplier_ids:
                rate_row = await self.db.execute(
                    select(SupplierRate.cost_price)
                    .where(
                        SupplierRate.supplier_id == sid,
                        SupplierRate.business_type == 'sms',
                        SupplierRate.status == 'active',
                        SupplierRate.country_code.in_(codes),
                    )
                    .order_by(SupplierRate.id.desc())
                    .limit(1)
                )
                cp = rate_row.scalar_one_or_none()
                if cp is not None and float(cp) > 0:
                    return Decimal(str(cp))

        fallback = Decimal(str(channel.cost_rate)) if (channel and channel.cost_rate) else Decimal('0')
        if fallback <= 0:
            logger.warning(
                "成本单价为 0: channel_id=%s, country=%s, suppliers=%s — 请检查供应商费率或通道 cost_rate 配置",
                channel_id, country_code,
                [r[0] for r in (await self.db.execute(
                    select(SupplierChannel.supplier_id).where(
                        SupplierChannel.channel_id == channel_id, SupplierChannel.status == 'active')
                )).all()] if channel_id else [],
            )
        return fallback
    
    async def calculate_and_charge(
        self,
        account_id: int,
        channel_id: int,
        country_code: str,
        message: str,
        mnc: Optional[str] = None
    ) -> Dict:
        """
        计算费用并扣款（使用原子操作防止并发超扣）
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
            
            # 3. 成本单价：供应商国家费率 SupplierRate（如孟加拉 0.0066）优先，其次通道 cost_rate
            channel_result = await self.db.execute(
                select(Channel).where(Channel.id == channel_id)
            )
            channel = channel_result.scalar_one_or_none()
            base_cost_per_sms = await self.resolve_base_cost_per_sms(
                channel_id, country_code, channel
            )
            
            # 4. 计算总费用
            total_sell_price = price_per_sms * message_count
            total_base_cost = base_cost_per_sms * message_count
            
            logger.info(f"计费: Sell={total_sell_price}, Cost={total_base_cost}")
            
            # 5. 原子扣减余额：WHERE balance >= total 防止并发超扣
            stmt = (
                update(Account)
                .where(
                    Account.id == account_id,
                    Account.balance >= total_sell_price,
                )
                .values(balance=Account.balance - total_sell_price)
            )
            result = await self.db.execute(stmt)
            
            if result.rowcount == 0:
                # 扣减失败：账户不存在或余额不足
                acct_result = await self.db.execute(
                    select(Account.balance).where(Account.id == account_id)
                )
                row = acct_result.first()
                if row is None:
                    return {'success': False, 'error': 'Account not found'}
                raise InsufficientBalanceError(
                    required=float(total_sell_price),
                    available=float(row[0])
                )
            
            # 6. 查询扣减后的余额用于记录日志
            acct_result = await self.db.execute(
                select(Account.balance).where(Account.id == account_id)
            )
            balance_after = acct_result.scalar()
            
            # 7. 记录余额变动
            balance_log = BalanceLog(
                account_id=account_id,
                change_type='charge',
                amount=-total_sell_price,
                balance_after=balance_after,
                description=f"SMS charge: {message_count} parts to {country_code} ({currency})"
            )
            self.db.add(balance_log)
            
            await self.db.flush()
            
            # 更新余额缓存
            cache_manager = await get_cache_manager()
            balance_cache_key = f"account:{account_id}:balance"
            await cache_manager.set(balance_cache_key, float(balance_after), ttl=60)
            
            return {
                'success': True,
                'total_cost': float(total_sell_price),
                'total_base_cost': float(total_base_cost),
                'message_count': message_count,
                'price_per_sms': float(price_per_sms),
                'base_cost_per_sms': float(base_cost_per_sms),
                'currency': currency,
                'balance_after': float(balance_after)
            }
            
        except (InsufficientBalanceError, PricingNotFoundError):
            raise
        except Exception as e:
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
        """计算短信条数（含 NBSP/弯引号等规范化，与前端预估一致）"""
        return _count_sms_parts_impl(message)

    def _is_gsm7(self, message: str) -> bool:
        """是否为 GSM-7 可编码正文（规范化后判断）"""
        return _is_gsm7_impl(message)
