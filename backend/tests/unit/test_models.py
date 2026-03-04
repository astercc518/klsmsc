"""
数据模型单元测试
"""
import pytest
from datetime import datetime
from decimal import Decimal
from app.modules.common.account import Account
from app.modules.sms.channel import Channel
from app.modules.sms.country_pricing import CountryPricing
from app.modules.sms.sms_log import SMSLog


@pytest.mark.unit
def test_account_model_repr(db_session, test_account):
    """测试Account模型的__repr__方法"""
    repr_str = repr(test_account)
    assert "Account" in repr_str
    assert str(test_account.id) in repr_str or test_account.email in repr_str


@pytest.mark.unit
def test_channel_model_creation(db_session, test_channel):
    """测试Channel模型创建"""
    assert test_channel.id is not None
    assert test_channel.channel_code == "TEST-CHANNEL-01"
    assert test_channel.status == "active"
    assert test_channel.priority == 100


@pytest.mark.unit
def test_country_pricing_model_creation(db_session, test_channel, test_pricing):
    """测试CountryPricing模型创建"""
    assert test_pricing.id is not None
    assert test_pricing.channel_id == test_channel.id
    assert test_pricing.country_code == "CN"
    assert test_pricing.price_per_sms == Decimal('0.0500')


@pytest.mark.asyncio
@pytest.mark.unit
async def test_sms_log_model_creation(db_session, test_account, test_channel):
    """测试SMSLog模型创建"""
    from app.modules.sms.sms_log import SMSLog
    import uuid
    
    sms_log = SMSLog(
        message_id=str(uuid.uuid4()),
        account_id=test_account.id,
        channel_id=test_channel.id,
        phone_number="+8613800138000",
        country_code="CN",
        message="测试消息",
        status="pending"
    )
    
    db_session.add(sms_log)
    await db_session.commit()
    await db_session.refresh(sms_log)
    
    assert sms_log.id is not None
    assert sms_log.status == "pending"
    assert sms_log.account_id == test_account.id
