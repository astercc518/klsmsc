"""
路由引擎模块
"""
from typing import Optional, List
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.sms.channel import Channel
from app.modules.sms.routing_rule import RoutingRule
from app.modules.common.account import AccountChannel
from app.utils.errors import ChannelNotAvailableError
from app.utils.logger import get_logger
from app.utils.cache import get_cache_manager
from app.utils.phone_utils import country_to_dial_code, dial_to_country_code
import random

logger = get_logger(__name__)


class RoutingEngine:
    """路由引擎"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def select_channel(
        self, 
        country_code: str, 
        preferred_channel: Optional[int] = None,
        strategy: str = 'priority',
        account_id: Optional[int] = None
    ) -> Optional[Channel]:
        """
        选择最优通道
        
        Args:
            country_code: 国家代码
            preferred_channel: 指定通道ID（可选）
            strategy: 路由策略 (priority/cost/quality/load_balance)
            account_id: 账户ID（可选）。若账户已绑定通道，则仅在绑定通道中路由
            
        Returns:
            Channel对象或None
            
        Raises:
            ChannelNotAvailableError: 无可用通道
        """
        # 1. 如果指定了通道，验证并返回（需在账户绑定范围内）
        if preferred_channel:
            channel = await self._get_channel_if_available(
                preferred_channel, country_code, account_id
            )
            if channel:
                logger.info(f"使用指定通道: {channel.channel_code}")
                return channel
            logger.warning(f"指定通道不可用: {preferred_channel}")
        
        # 2. 获取可用通道列表
        channels = await self._get_available_channels(country_code)
        if not channels:
            raise ChannelNotAvailableError(f"No available channel for country {country_code}")
        
        # 2.5 若账户已绑定通道，仅在其绑定通道中筛选
        if account_id:
            bound_ids, channels = await self._filter_by_account_channels(channels, account_id)
            if bound_ids and not channels:
                raise ChannelNotAvailableError(
                    f"账户 {account_id} 绑定的通道不支持国家 {country_code}，请检查路由规则或账户通道绑定"
                )
        
        logger.debug(f"找到 {len(channels)} 个可用通道")
        
        # 3. 根据策略选择通道
        if strategy == 'priority':
            channel = self._select_by_priority(channels)
        elif strategy == 'quality':
            channel = self._select_by_quality(channels)
        elif strategy == 'load_balance':
            channel = self._select_by_weight(channels)
        else:
            channel = channels[0]
        
        logger.info(f"选择通道: {channel.channel_code} (策略: {strategy})")
        return channel
    
    async def _get_channel_if_available(
        self, channel_id: int, country_code: str, account_id: Optional[int]
    ) -> Optional[Channel]:
        """验证通道可用，且若账户有绑定则需在绑定范围内"""
        result = await self.db.execute(
            select(Channel).where(
                Channel.id == channel_id,
                Channel.status == 'active',
                Channel.is_deleted == False
            )
        )
        channel = result.scalar_one_or_none()
        if not channel:
            return None
        if account_id:
            _, bound = await self._filter_by_account_channels([channel], account_id)
            return bound[0] if bound else None
        return channel
    
    async def _filter_by_account_channels(
        self, channels: List[Channel], account_id: int
    ) -> tuple:
        """
        仅保留账户绑定的通道
        Returns:
            (bound_ids, filtered_channels)
            当 bound_ids 为空时表示未绑定，返回全部 channels
        """
        result = await self.db.execute(
            select(AccountChannel.channel_id).where(
                AccountChannel.account_id == account_id
            )
        )
        bound_ids = {r[0] for r in result.all()}
        if not bound_ids:
            return set(), channels  # 未绑定通道，不限制
        filtered = [ch for ch in channels if ch.id in bound_ids]
        if filtered != channels:
            logger.info(
                f"账户 {account_id} 通道过滤: 绑定={list(bound_ids)}, "
                f"路由候选={[c.channel_code for c in channels]}, 筛选后={[c.channel_code for c in filtered]}"
            )
        return bound_ids, filtered
    
    async def _get_available_channels(self, country_code: str) -> List[Channel]:
        """
        获取支持该国家的可用通道列表（带缓存）
        
        通过路由规则表和通道表联合查询
        缓存时间: 5分钟
        """
        cache_manager = await get_cache_manager()
        # 路由支持国码(66)或ISO(TH)，统一生成缓存键
        codes_to_try = [country_code]
        if country_code.isdigit():
            codes_to_try.append(dial_to_country_code(country_code))
        else:
            codes_to_try.append(country_to_dial_code(country_code))
        cache_key = f"route:{country_code}"
        
        # 尝试从缓存获取
        cached = await cache_manager.get(cache_key)
        if cached is not None:
            # 从缓存中恢复Channel对象
            # 注意：由于Channel是SQLAlchemy对象，我们需要重新查询
            # 但可以缓存通道ID列表，然后批量查询
            channel_ids = cached.get('channel_ids', [])
            route_priorities = cached.get('route_priorities', [])
            if channel_ids:
                result = await self.db.execute(
                    select(Channel).where(
                        Channel.id.in_(channel_ids),
                        Channel.status == 'active',
                        Channel.is_deleted == False
                    )
                )
                channels = list(result.scalars().all())
                # 恢复路由优先级
                priority_map = dict(zip(channel_ids, route_priorities)) if route_priorities else {}
                for ch in channels:
                    ch._route_priority = priority_map.get(ch.id, 0)
                # 按路由优先级排序
                channels.sort(key=lambda x: x._route_priority or 0, reverse=True)
                logger.debug(f"从缓存获取通道: {country_code}, 数量: {len(channels)}")
                return channels
        
        # 缓存未命中，从数据库查询
        # 路由规则支持国码(66)或ISO(TH)，两种格式均可匹配
        result = await self.db.execute(
            select(Channel, RoutingRule.priority.label('route_priority')).join(
                RoutingRule,
                Channel.id == RoutingRule.channel_id
            ).where(
                or_(
                    RoutingRule.country_code.in_(codes_to_try),
                    RoutingRule.country_code == '*',
                ),
                Channel.status == 'active',
                Channel.is_deleted == False,
                RoutingRule.is_active == True
            ).order_by(
                RoutingRule.priority.desc(),
                Channel.priority.desc()
            )
        )
        
        # 结果包含 (Channel, route_priority) 元组；同一通道若同时命中具体国家与 *，保留较高路由优先级
        rows = result.all()
        merged: dict = {}
        for row in rows:
            channel = row[0]
            route_priority = row[1]
            cid = channel.id
            prev = merged.get(cid)
            if prev is None or route_priority > prev[1]:
                merged[cid] = (channel, route_priority)
        ordered = sorted(
            merged.values(),
            key=lambda x: (x[1], x[0].priority or 0),
            reverse=True,
        )
        channels = []
        for channel, route_priority in ordered:
            channel._route_priority = route_priority
            channels.append(channel)
        
        # 存入缓存（只缓存通道ID和基本信息，避免序列化SQLAlchemy对象）
        if channels:
            cache_data = {
                'channel_ids': [ch.id for ch in channels],
                'channel_codes': [ch.channel_code for ch in channels],
                'priorities': [ch.priority or 0 for ch in channels],
                'route_priorities': [getattr(ch, '_route_priority', 0) or 0 for ch in channels]
            }
            await cache_manager.set(cache_key, cache_data, ttl=300)  # 5分钟
            logger.debug(f"通道信息已缓存: {country_code}, 数量: {len(channels)}")
        
        return channels
    
    def _select_by_priority(self, channels: List[Channel]) -> Channel:
        """按优先级选择（路由规则优先级最高的）"""
        # 优先使用路由规则优先级，如果没有则使用通道优先级
        return max(channels, key=lambda x: getattr(x, '_route_priority', None) or x.priority or 0)
    
    def _select_by_quality(self, channels: List[Channel]) -> Channel:
        """按质量选择（成功率最高的）"""
        return max(channels, key=lambda x: x.success_rate or 0)
    
    def _select_by_weight(self, channels: List[Channel]) -> Channel:
        """按权重负载均衡"""
        weights = [ch.weight or 100 for ch in channels]
        return random.choices(channels, weights=weights)[0]

