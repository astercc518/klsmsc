"""
SMS Worker 单元测试
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_sms_async_message_not_found(db_session):
    """测试短信记录不存在时的处理"""
    from app.workers.sms_worker import _send_sms_async
    
    result = await _send_sms_async("non_existent_message_id")
    
    assert result["success"] is False
    assert "not found" in result["error"].lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_sms_async_channel_not_found(db_session, test_account):
    """测试通道不存在时的处理"""
    from app.workers.sms_worker import _send_sms_async
    from app.modules.sms.sms_log import SMSLog
    
    # 创建短信记录，但通道ID无效
    sms_log = SMSLog(
        message_id="test_msg_001",
        account_id=test_account.id,
        channel_id=99999,  # 不存在的通道
        phone_number="+8613800138000",
        country_code="CN",
        message="Test message",
        message_count=1,
        status="queued",
        cost_price=0.01,
        selling_price=0.05,
        currency="USD",
        submit_time=datetime.now()
    )
    db_session.add(sms_log)
    await db_session.commit()
    
    result = await _send_sms_async("test_msg_001")
    
    assert result["success"] is False
    assert "channel" in result["error"].lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_sms_async_http_channel_success(
    db_session, test_account, test_channel
):
    """测试HTTP通道发送成功"""
    from app.workers.sms_worker import _send_sms_async
    from app.modules.sms.sms_log import SMSLog
    
    # 设置通道为HTTP协议
    test_channel.protocol = "HTTP"
    test_channel.api_url = "https://api.example.com/sms"
    await db_session.commit()
    
    # 创建短信记录
    sms_log = SMSLog(
        message_id="test_msg_http_001",
        account_id=test_account.id,
        channel_id=test_channel.id,
        phone_number="+8613800138000",
        country_code="CN",
        message="Test HTTP message",
        message_count=1,
        status="queued",
        cost_price=0.01,
        selling_price=0.05,
        currency="USD",
        submit_time=datetime.now()
    )
    db_session.add(sms_log)
    await db_session.commit()
    
    # Mock HTTP Adapter
    with patch('app.workers.sms_worker._send_via_http') as mock_http:
        mock_http.return_value = True
        
        result = await _send_sms_async("test_msg_http_001")
        
        # 验证HTTP发送被调用
        mock_http.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_sms_async_smpp_channel_success(
    db_session, test_account, test_channel
):
    """测试SMPP通道发送成功"""
    from app.workers.sms_worker import _send_sms_async
    from app.modules.sms.sms_log import SMSLog
    
    # 设置通道为SMPP协议
    test_channel.protocol = "SMPP"
    await db_session.commit()
    
    # 创建短信记录
    sms_log = SMSLog(
        message_id="test_msg_smpp_001",
        account_id=test_account.id,
        channel_id=test_channel.id,
        phone_number="+8613800138000",
        country_code="CN",
        message="Test SMPP message",
        message_count=1,
        status="queued",
        cost_price=0.01,
        selling_price=0.05,
        currency="USD",
        submit_time=datetime.now()
    )
    db_session.add(sms_log)
    await db_session.commit()
    
    # Mock SMPP Adapter
    with patch('app.workers.sms_worker._send_via_smpp') as mock_smpp:
        mock_smpp.return_value = True
        
        result = await _send_sms_async("test_msg_smpp_001")
        
        # 验证SMPP发送被调用
        mock_smpp.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_sms_async_unsupported_protocol(
    db_session, test_account, test_channel
):
    """测试不支持的协议"""
    from app.workers.sms_worker import _send_sms_async
    from app.modules.sms.sms_log import SMSLog
    
    # 设置通道为不支持的协议
    test_channel.protocol = "UNKNOWN"
    await db_session.commit()
    
    # 创建短信记录
    sms_log = SMSLog(
        message_id="test_msg_unknown_001",
        account_id=test_account.id,
        channel_id=test_channel.id,
        phone_number="+8613800138000",
        country_code="CN",
        message="Test message",
        message_count=1,
        status="queued",
        cost_price=0.01,
        selling_price=0.05,
        currency="USD",
        submit_time=datetime.now()
    )
    db_session.add(sms_log)
    await db_session.commit()
    
    result = await _send_sms_async("test_msg_unknown_001")
    
    # 验证短信状态被更新为失败
    await db_session.refresh(sms_log)
    assert sms_log.status == "failed"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_sms_status_update_on_success(
    db_session, test_account, test_channel
):
    """测试发送成功后状态更新"""
    from app.workers.sms_worker import _send_sms_async
    from app.modules.sms.sms_log import SMSLog
    
    test_channel.protocol = "HTTP"
    test_channel.api_url = "https://api.example.com/sms"
    await db_session.commit()
    
    sms_log = SMSLog(
        message_id="test_msg_status_001",
        account_id=test_account.id,
        channel_id=test_channel.id,
        phone_number="+8613800138000",
        country_code="CN",
        message="Test message",
        message_count=1,
        status="queued",
        cost_price=0.01,
        selling_price=0.05,
        currency="USD",
        submit_time=datetime.now()
    )
    db_session.add(sms_log)
    await db_session.commit()
    
    with patch('app.workers.sms_worker._send_via_http') as mock_http:
        mock_http.return_value = True
        
        await _send_sms_async("test_msg_status_001")
        
        # 验证状态已更新
        await db_session.refresh(sms_log)
        assert sms_log.status in ["sent", "delivered"]
        assert sms_log.sent_time is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_sms_status_update_on_failure(
    db_session, test_account, test_channel
):
    """测试发送失败后状态更新"""
    from app.workers.sms_worker import _send_sms_async
    from app.modules.sms.sms_log import SMSLog
    
    test_channel.protocol = "HTTP"
    test_channel.api_url = "https://api.example.com/sms"
    await db_session.commit()
    
    sms_log = SMSLog(
        message_id="test_msg_fail_001",
        account_id=test_account.id,
        channel_id=test_channel.id,
        phone_number="+8613800138000",
        country_code="CN",
        message="Test message",
        message_count=1,
        status="queued",
        cost_price=0.01,
        selling_price=0.05,
        currency="USD",
        submit_time=datetime.now()
    )
    db_session.add(sms_log)
    await db_session.commit()
    
    with patch('app.workers.sms_worker._send_via_http') as mock_http:
        mock_http.return_value = False
        
        await _send_sms_async("test_msg_fail_001")
        
        # 验证状态已更新为失败
        await db_session.refresh(sms_log)
        assert sms_log.status == "failed"


@pytest.mark.unit
def test_celery_task_registration():
    """测试Celery任务注册"""
    from app.workers.celery_app import celery_app
    
    # 验证send_sms_task已注册
    registered_tasks = celery_app.tasks.keys()
    assert 'send_sms_task' in registered_tasks


@pytest.mark.unit
def test_celery_task_retry_config():
    """测试Celery任务重试配置"""
    from app.workers.sms_worker import send_sms_task
    
    # 验证最大重试次数
    assert send_sms_task.max_retries == 3
