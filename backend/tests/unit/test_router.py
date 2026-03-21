"""
路由引擎单元测试
"""
import pytest
from app.core.router import RoutingEngine
from app.utils.errors import ChannelNotAvailableError


@pytest.mark.asyncio
@pytest.mark.unit
async def test_select_channel_by_priority(
    db_session,
    test_channel,
    test_routing_rule
):
    """测试按优先级选择通道"""
    engine = RoutingEngine(db_session)
    
    channel = await engine.select_channel(
        country_code="CN",
        strategy="priority"
    )
    
    assert channel is not None
    assert channel.id == test_channel.id
    assert channel.channel_code == test_channel.channel_code


@pytest.mark.asyncio
@pytest.mark.unit
async def test_select_channel_no_available(db_session):
    """测试无可用通道时抛出异常"""
    engine = RoutingEngine(db_session)
    
    with pytest.raises(ChannelNotAvailableError):
        await engine.select_channel(country_code="XX")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_select_preferred_channel(db_session, test_channel):
    """测试指定通道"""
    engine = RoutingEngine(db_session)
    
    channel = await engine.select_channel(
        country_code="CN",
        preferred_channel=test_channel.id
    )
    
    assert channel is not None
    assert channel.id == test_channel.id


@pytest.mark.asyncio
@pytest.mark.unit
async def test_select_by_quality(db_session, test_channel, test_routing_rule):
    """测试按质量选择通道"""
    # 设置成功率
    test_channel.success_rate = 95.5
    await db_session.commit()
    
    engine = RoutingEngine(db_session)
    
    channel = await engine.select_channel(
        country_code="CN",
        strategy="quality"
    )
    
    assert channel is not None
    assert channel.id == test_channel.id


@pytest.mark.asyncio
@pytest.mark.unit
async def test_select_by_weight(db_session, test_channel, test_routing_rule):
    """测试按权重负载均衡"""
    test_channel.weight = 80
    await db_session.commit()
    
    engine = RoutingEngine(db_session)
    
    channel = await engine.select_channel(
        country_code="CN",
        strategy="load_balance"
    )
    
    assert channel is not None
    assert channel.id == test_channel.id
