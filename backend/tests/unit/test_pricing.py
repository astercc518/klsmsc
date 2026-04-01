"""
计费引擎单元测试
"""
import pytest
from decimal import Decimal
from app.core.pricing import PricingEngine
from app.utils.errors import InsufficientBalanceError, PricingNotFoundError


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_price(db_session, test_channel, test_pricing):
    """测试查询价格"""
    engine = PricingEngine(db_session)
    
    price_info = await engine.get_price(
        channel_id=test_channel.id,
        country_code="CN"
    )
    
    assert price_info is not None
    assert price_info['price'] == 0.05
    assert price_info['currency'] == "USD"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_price_not_found(db_session, test_channel):
    """测试价格不存在"""
    engine = PricingEngine(db_session)
    
    price_info = await engine.get_price(
        channel_id=test_channel.id,
        country_code="XX"
    )
    
    assert price_info is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_calculate_and_charge_success(
    db_session,
    test_account,
    test_channel,
    test_pricing
):
    """测试成功扣费"""
    engine = PricingEngine(db_session)
    
    initial_balance = test_account.balance
    
    result = await engine.calculate_and_charge(
        account_id=test_account.id,
        channel_id=test_channel.id,
        country_code="CN",
        message="Test message"
    )
    
    assert result['success'] is True
    assert result['total_cost'] > 0
    assert result['message_count'] == 1
    
    # 验证余额已扣减
    await db_session.refresh(test_account)
    assert test_account.balance < initial_balance


@pytest.mark.asyncio
@pytest.mark.unit
async def test_calculate_and_charge_insufficient_balance(
    db_session,
    test_account,
    test_channel,
    test_pricing
):
    """测试余额不足"""
    # 设置余额为0
    test_account.balance = Decimal('0.0001')
    await db_session.commit()
    
    engine = PricingEngine(db_session)
    
    with pytest.raises(InsufficientBalanceError):
        await engine.calculate_and_charge(
            account_id=test_account.id,
            channel_id=test_channel.id,
            country_code="CN",
            message="Test message"
        )


@pytest.mark.asyncio
@pytest.mark.unit
def test_count_sms_parts_gsm7():
    """测试GSM-7编码短信条数计算"""
    engine = PricingEngine(None)
    
    # 单条短信
    assert engine._count_sms_parts("Short message") == 1
    
    # 长短信（160字符）
    long_message = "A" * 160
    assert engine._count_sms_parts(long_message) == 1
    
    # 超长短信（200字符）
    very_long_message = "A" * 200
    assert engine._count_sms_parts(very_long_message) == 2


@pytest.mark.asyncio
@pytest.mark.unit
def test_count_sms_parts_ucs2():
    """测试UCS-2编码短信条数计算"""
    engine = PricingEngine(None)
    
    # 中文单条短信
    chinese_message = "这是一条测试短信"
    assert engine._count_sms_parts(chinese_message) == 1
    
    # 超长中文短信（100字符）
    long_chinese = "测试" * 50
    assert engine._count_sms_parts(long_chinese) == 2


@pytest.mark.asyncio
@pytest.mark.unit
def test_count_sms_parts_normalizes_invisible_chars():
    """NBSP / 零宽等规范化后按 GSM-7 计条，避免英文文案误判为 UCS-2"""
    engine = PricingEngine(None)
    sample = (
        "We are recruiting 100 trial users in Africa. We offer a $100 trial bonus "
        "and promise to earn $20 in 5 days. Add us on WhatsApp. https://wa.me/"
    )
    assert engine._count_sms_parts(sample) == 1
    # 全部普通空格改为 NBSP：未规范化时整段非 GSM-7，规范化后仍为 1 条
    assert engine._count_sms_parts(sample.replace(" ", "\u00a0")) == 1
    assert engine._count_sms_parts("Hello\u200bWorld") == 1
