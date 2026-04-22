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
async def test_send_sms_async_smpp_channel_reroutes_to_gateway_queue(
    db_session, test_account, test_channel
):
    """SMPP 在 sms_send 队列上下文：返回重路由标记与全量负载，供投递 sms_send_smpp 给 Go 网关"""
    from app.workers.sms_worker import _send_sms_async
    from app.modules.sms.sms_log import SMSLog

    test_channel.protocol = "SMPP"
    await db_session.commit()

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
        submit_time=datetime.now(),
    )
    db_session.add(sms_log)
    await db_session.commit()

    result = await _send_sms_async("test_msg_smpp_001", _current_queue="sms_send")

    assert result.get("_reroute_smpp") is True
    assert isinstance(result.get("_smpp_payload"), dict)
    assert result["_smpp_payload"].get("message_id") == "test_msg_smpp_001"


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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_virtual_dlr_single_updates_sent_to_terminal(db_session, test_account):
    """虚拟回执单条：_do_virtual_dlr 将 sent 推进为终态（delivered/failed/expired）"""
    from unittest.mock import AsyncMock, patch
    from app.modules.sms.sms_log import SMSLog
    from app.modules.sms.channel import Channel
    from app.workers.sms_worker import _do_virtual_dlr

    channel = Channel(
        channel_code="VIRT-UNIT-01",
        channel_name="虚拟单条测试",
        protocol="VIRTUAL",
        default_sender_id="TEST",
        priority=0,
        weight=100,
        status="active",
        virtual_config='{"delivery_rate_min":100,"delivery_rate_max":100,"fail_rate_min":0,"fail_rate_max":0}',
    )
    db_session.add(channel)
    await db_session.flush()

    mid = "msg_virt_unit_single"
    now = datetime.now()
    sms_log = SMSLog(
        id=910001,
        message_id=mid,
        account_id=test_account.id,
        channel_id=channel.id,
        phone_number="+84901234567",
        country_code="VN",
        message="test",
        message_count=1,
        status="sent",
        cost_price=0.01,
        selling_price=0.05,
        currency="USD",
        submit_time=now,
        sent_time=now,
    )
    db_session.add(sms_log)
    await db_session.commit()

    from sqlalchemy.ext.asyncio import AsyncEngine
    from tests.conftest import test_engine as _async_engine

    with patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=_async_engine):
        with patch.object(AsyncEngine, "dispose", new=AsyncMock()):
            with patch("app.workers.webhook_worker.trigger_webhook", new=AsyncMock()):
                with patch("app.utils.water_trigger.trigger_water_single", new=AsyncMock()):
                    out = await _do_virtual_dlr(mid, channel.id)

    assert out.get("success") is True
    assert out.get("status") == "delivered"
    await db_session.refresh(sms_log)
    assert sms_log.status == "delivered"
    assert sms_log.delivery_time is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_virtual_dlr_batch_updates_sent_rows(db_session, test_account):
    """虚拟回执批量：_do_virtual_dlr_batch 将多条 sent 推进终态"""
    from unittest.mock import AsyncMock, patch
    from app.modules.sms.sms_log import SMSLog
    from app.modules.sms.channel import Channel
    from app.workers.sms_worker import _do_virtual_dlr_batch

    channel = Channel(
        channel_code="VIRT-UNIT-02",
        channel_name="虚拟批量测试",
        protocol="VIRTUAL",
        default_sender_id="TEST",
        priority=0,
        weight=100,
        status="active",
        virtual_config='{"delivery_rate_min":100,"delivery_rate_max":100,"fail_rate_min":0,"fail_rate_max":0}',
    )
    db_session.add(channel)
    await db_session.flush()

    now = datetime.now()
    mids = []
    for i in range(3):
        mid = f"msg_virt_unit_batch_{i}"
        mids.append(mid)
        db_session.add(
            SMSLog(
                id=910010 + i,
                message_id=mid,
                account_id=test_account.id,
                channel_id=channel.id,
                phone_number=f"+8490123456{i}",
                country_code="VN",
                message="t",
                message_count=1,
                status="sent",
                cost_price=0.01,
                selling_price=0.05,
                currency="USD",
                submit_time=now,
                sent_time=now,
            )
        )
    await db_session.commit()

    from sqlalchemy.ext.asyncio import AsyncEngine
    from tests.conftest import test_engine as _async_engine

    with patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=_async_engine):
        with patch.object(AsyncEngine, "dispose", new=AsyncMock()):
            with patch("app.workers.webhook_worker.trigger_webhook", new=AsyncMock()):
                with patch("app.utils.water_trigger.trigger_water_for_delivered", new=AsyncMock()):
                    out = await _do_virtual_dlr_batch(mids, channel.id, batch_id=None)

    assert out["delivered"] == 3
    assert out["failed"] == 0
    assert out["expired"] == 0

    from sqlalchemy import select

    for mid in mids:
        r2 = await db_session.execute(select(SMSLog.status).where(SMSLog.message_id == mid))
        assert r2.scalar_one() == "delivered"


@pytest.mark.unit
def test_virtual_dlr_tasks_routed_to_sms_send():
    """确认 Celery 路由：虚拟回执相关任务走 sms_send（与 worker-sms 一致）"""
    from app.workers.celery_app import celery_app

    routes = celery_app.conf.task_routes
    assert routes.get("virtual_dlr_generate") == {"queue": "sms_send"}
    assert routes.get("virtual_dlr_batch_generate") == {"queue": "sms_send"}
    assert routes.get("virtual_submit_simulate") == {"queue": "sms_send"}
    assert routes.get("repair_virtual_batch_dlr") == {"queue": "sms_send"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_via_virtual_schedules_celery_on_sms_send_queue(db_session, test_account):
    """虚拟发送：入队 virtual_dlr_generate 且显式 queue=sms_send"""
    from unittest.mock import MagicMock, patch
    from app.modules.sms.sms_log import SMSLog
    from app.modules.sms.channel import Channel
    from app.workers.sms_worker import _send_via_virtual

    channel = Channel(
        channel_code="VIRT-UNIT-03",
        channel_name="虚拟调度测试",
        protocol="VIRTUAL",
        default_sender_id="TEST",
        priority=0,
        weight=100,
        status="active",
    )
    db_session.add(channel)
    await db_session.flush()

    sms_log = SMSLog(
        id=910020,
        message_id="msg_virt_queue_chk",
        account_id=test_account.id,
        channel_id=channel.id,
        phone_number="+84900000000",
        country_code="VN",
        message="x",
        message_count=1,
        status="sent",
        cost_price=0.01,
        selling_price=0.05,
        currency="USD",
        submit_time=datetime.now(),
    )
    db_session.add(sms_log)
    await db_session.commit()

    mock_celery = MagicMock()

    with patch("app.workers.celery_app.celery_app", mock_celery):
        ok = await _send_via_virtual(sms_log, channel)

    assert ok is True
    mock_celery.send_task.assert_called_once()
    call_kw = mock_celery.send_task.call_args
    assert call_kw[0][0] == "virtual_dlr_generate"
    assert call_kw[1].get("queue") == "sms_send"
    assert call_kw[1]["args"][0] == "msg_virt_queue_chk"
    assert call_kw[1]["args"][1] == channel.id
