"""
Pytest配置和共享fixtures
"""
import pytest
import asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

from app.main import app
from app.database import get_db, Base
from app.config import settings
from app.modules.common.account import Account
from app.modules.sms.channel import Channel
from app.modules.sms.country_pricing import CountryPricing
from app.modules.sms.routing_rule import RoutingRule

# 测试数据库URL（使用内存数据库或测试数据库）
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# 创建测试数据库引擎
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    future=True
)

TestSessionLocal = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False
)


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    创建测试数据库会话
    """
    # 创建所有表
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # 创建会话
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()
    
    # 清理表
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def test_account(db_session: AsyncSession) -> Account:
    """创建测试账户"""
    account = Account(
        account_name="测试账户",
        email="test@example.com",
        password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5Gy5ZN8xVXHq6",  # test123
        balance=1000.0000,
        currency="USD",
        status="active",
        api_key="test_api_key_12345",
        api_secret="test_api_secret_12345"
    )
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)
    return account


@pytest.fixture
async def test_channel(db_session: AsyncSession) -> Channel:
    """创建测试通道"""
    channel = Channel(
        channel_code="TEST-CHANNEL-01",
        channel_name="测试通道",
        protocol="HTTP",
        host="test.example.com",
        port=8080,
        username="test_user",
        password="test_password",
        priority=100,
        weight=100,
        status="active",
        default_sender_id="TEST"
    )
    db_session.add(channel)
    await db_session.commit()
    await db_session.refresh(channel)
    return channel


@pytest.fixture
async def test_pricing(db_session: AsyncSession, test_channel: Channel) -> CountryPricing:
    """创建测试价格规则"""
    pricing = CountryPricing(
        channel_id=test_channel.id,
        country_code="CN",
        country_name="中国",
        price_per_sms=0.0500,
        currency="USD"
    )
    db_session.add(pricing)
    await db_session.commit()
    await db_session.refresh(pricing)
    return pricing


@pytest.fixture
async def test_routing_rule(db_session: AsyncSession, test_channel: Channel) -> RoutingRule:
    """创建测试路由规则"""
    rule = RoutingRule(
        channel_id=test_channel.id,
        country_code="CN",
        priority=100,
        is_active=True
    )
    db_session.add(rule)
    await db_session.commit()
    await db_session.refresh(rule)
    return rule


@pytest.fixture
def client(db_session: AsyncSession):
    """创建测试客户端"""
    # 覆盖get_db依赖
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as test_client:
        yield test_client
    
    # 清理
    app.dependency_overrides.clear()


@pytest.fixture
def mock_redis():
    """Mock Redis客户端"""
    with patch('app.utils.cache.get_redis_client') as mock:
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.set = AsyncMock()
        redis_mock.setex = AsyncMock()
        redis_mock.delete = AsyncMock()
        redis_mock.keys = AsyncMock(return_value=[])
        redis_mock.incr = AsyncMock(return_value=1)
        redis_mock.expire = AsyncMock()
        redis_mock.ping = AsyncMock(return_value=True)
        mock.return_value = redis_mock
        yield redis_mock


@pytest.fixture
def mock_cache_manager(mock_redis):
    """Mock缓存管理器"""
    with patch('app.utils.cache.get_cache_manager') as mock:
        cache_mock = AsyncMock()
        cache_mock.get = AsyncMock(return_value=None)
        cache_mock.set = AsyncMock()
        cache_mock.delete = AsyncMock()
        mock.return_value = cache_mock
        yield cache_mock
