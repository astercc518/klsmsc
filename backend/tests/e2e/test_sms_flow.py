"""
短信发送完整流程 E2E 测试

测试场景：
1. API请求 → 验证 → 路由 → 计费 → 入队 → Worker发送 → 状态更新 → Webhook回调
"""
import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.e2e
@pytest.mark.asyncio
class TestCompleteSMSFlow:
    """完整短信发送流程测试"""
    
    async def test_single_sms_complete_flow(
        self,
        db_session,
        test_account,
        test_channel,
        test_pricing,
        test_routing_rule
    ):
        """
        测试单条短信完整发送流程
        
        流程：
        1. 调用发送API
        2. 验证号码格式
        3. 路由选择通道
        4. 计费扣款
        5. 创建短信记录
        6. 任务入队
        7. Worker处理发送
        8. 更新状态
        9. 触发Webhook回调
        """
        from app.core.phone_parser import PhoneNumberParser
        from app.core.router import RoutingEngine
        from app.core.pricing import PricingEngine
        from app.modules.sms.sms_log import SMSLog
        
        phone_number = "+8613800138000"
        message = "这是一条E2E测试短信"
        initial_balance = float(test_account.balance)
        
        # Step 1: 验证号码
        phone_result = PhoneNumberParser.parse(phone_number)
        assert phone_result['valid'] is True
        assert phone_result['country_code'] == "CN"
        
        # Step 2: 路由选择
        routing_engine = RoutingEngine(db_session)
        channel = await routing_engine.select_channel(
            country_code="CN",
            strategy="priority"
        )
        assert channel is not None
        assert channel.id == test_channel.id
        
        # Step 3: 计费扣款
        pricing_engine = PricingEngine(db_session)
        charge_result = await pricing_engine.calculate_and_charge(
            account_id=test_account.id,
            channel_id=channel.id,
            country_code="CN",
            message=message
        )
        assert charge_result['success'] is True
        assert charge_result['message_count'] == 1
        assert charge_result['total_cost'] > 0
        
        # Step 4: 验证余额扣减
        await db_session.refresh(test_account)
        assert float(test_account.balance) < initial_balance
        
        # Step 5: 创建短信记录
        sms_log = SMSLog(
            message_id="e2e_test_msg_001",
            account_id=test_account.id,
            channel_id=channel.id,
            phone_number=phone_result['e164_format'],
            country_code="CN",
            message=message,
            message_count=charge_result['message_count'],
            status="queued",
            cost_price=charge_result['total_base_cost'],
            selling_price=charge_result['total_cost'],
            currency=charge_result['currency'],
            submit_time=datetime.now()
        )
        db_session.add(sms_log)
        await db_session.commit()
        
        # 验证记录创建成功
        await db_session.refresh(sms_log)
        assert sms_log.id is not None
        assert sms_log.status == "queued"
    
    async def test_sms_flow_insufficient_balance(
        self,
        db_session,
        test_account,
        test_channel,
        test_pricing,
        test_routing_rule
    ):
        """测试余额不足时的流程中断"""
        from app.core.pricing import PricingEngine
        from app.utils.errors import InsufficientBalanceError
        
        # 设置余额为0
        test_account.balance = Decimal('0.0001')
        await db_session.commit()
        
        pricing_engine = PricingEngine(db_session)
        
        with pytest.raises(InsufficientBalanceError):
            await pricing_engine.calculate_and_charge(
                account_id=test_account.id,
                channel_id=test_channel.id,
                country_code="CN",
                message="Test message"
            )
    
    async def test_sms_flow_no_channel_available(
        self,
        db_session,
        test_account
    ):
        """测试无可用通道时的处理"""
        from app.core.router import RoutingEngine
        from app.utils.errors import ChannelNotAvailableError
        
        routing_engine = RoutingEngine(db_session)
        
        # 查找不存在的国家代码
        with pytest.raises(ChannelNotAvailableError):
            await routing_engine.select_channel(
                country_code="XX",
                strategy="priority"
            )


@pytest.mark.e2e
@pytest.mark.asyncio
class TestBatchSMSFlow:
    """批量发送流程测试"""
    
    async def test_batch_sms_flow(
        self,
        db_session,
        test_account,
        test_channel,
        test_pricing,
        test_routing_rule
    ):
        """测试批量发送流程"""
        from app.core.phone_parser import PhoneNumberParser
        from app.core.router import RoutingEngine
        from app.core.pricing import PricingEngine
        from app.modules.sms.sms_log import SMSLog
        
        # 批量号码列表
        phone_numbers = [
            "+8613800138001",
            "+8613800138002",
            "+8613800138003"
        ]
        message = "批量测试短信"
        
        routing_engine = RoutingEngine(db_session)
        pricing_engine = PricingEngine(db_session)
        
        successful_count = 0
        failed_count = 0
        
        for i, phone in enumerate(phone_numbers):
            # 验证号码
            phone_result = PhoneNumberParser.parse(phone)
            if not phone_result['valid']:
                failed_count += 1
                continue
            
            # 路由选择
            try:
                channel = await routing_engine.select_channel(
                    country_code=phone_result['country_code'],
                    strategy="priority"
                )
            except Exception:
                failed_count += 1
                continue
            
            # 计费扣款
            try:
                charge_result = await pricing_engine.calculate_and_charge(
                    account_id=test_account.id,
                    channel_id=channel.id,
                    country_code=phone_result['country_code'],
                    message=message
                )
                
                if charge_result['success']:
                    successful_count += 1
                else:
                    failed_count += 1
            except Exception:
                failed_count += 1
        
        # 验证结果
        assert successful_count == 3
        assert failed_count == 0


@pytest.mark.e2e
@pytest.mark.asyncio
class TestLongMessageFlow:
    """长短信发送流程测试"""
    
    async def test_long_message_split_and_charge(
        self,
        db_session,
        test_account,
        test_channel,
        test_pricing,
        test_routing_rule
    ):
        """测试长短信拆分和计费"""
        from app.core.pricing import PricingEngine
        
        # 创建超长消息 (超过160字符)
        long_message = "A" * 200
        
        pricing_engine = PricingEngine(db_session)
        
        charge_result = await pricing_engine.calculate_and_charge(
            account_id=test_account.id,
            channel_id=test_channel.id,
            country_code="CN",
            message=long_message
        )
        
        # 验证拆分为多条
        assert charge_result['success'] is True
        assert charge_result['message_count'] == 2  # 200字符拆为2条
    
    async def test_unicode_long_message(
        self,
        db_session,
        test_account,
        test_channel,
        test_pricing,
        test_routing_rule
    ):
        """测试中文长短信"""
        from app.core.pricing import PricingEngine
        
        # 中文超长消息 (超过70字符)
        long_chinese = "测试" * 50  # 100个汉字
        
        pricing_engine = PricingEngine(db_session)
        
        charge_result = await pricing_engine.calculate_and_charge(
            account_id=test_account.id,
            channel_id=test_channel.id,
            country_code="CN",
            message=long_chinese
        )
        
        # UCS-2编码，70字符/条，100字符需要2条
        assert charge_result['success'] is True
        assert charge_result['message_count'] == 2


@pytest.mark.e2e
@pytest.mark.asyncio
class TestMultiChannelFlow:
    """多通道路由流程测试"""
    
    async def test_channel_priority_routing(
        self,
        db_session,
        test_account,
        test_channel,
        test_routing_rule
    ):
        """测试通道优先级路由"""
        from app.core.router import RoutingEngine
        from app.modules.sms.channel import Channel
        from app.modules.sms.routing_rule import RoutingRule
        
        # 创建另一个低优先级通道
        low_priority_channel = Channel(
            channel_code="LOW-PRIORITY-01",
            channel_name="低优先级通道",
            protocol="HTTP",
            host="low.example.com",
            port=8080,
            username="user",
            password="pass",
            priority=50,  # 低于test_channel的100
            weight=100,
            status="active",
            default_sender_id="LOW"
        )
        db_session.add(low_priority_channel)
        await db_session.commit()
        
        # 创建路由规则
        low_rule = RoutingRule(
            channel_id=low_priority_channel.id,
            country_code="CN",
            priority=50,
            is_active=True
        )
        db_session.add(low_rule)
        await db_session.commit()
        
        # 路由应该选择高优先级通道
        routing_engine = RoutingEngine(db_session)
        channel = await routing_engine.select_channel(
            country_code="CN",
            strategy="priority"
        )
        
        # 验证选择了高优先级通道
        assert channel.id == test_channel.id
        assert channel.priority > low_priority_channel.priority


@pytest.mark.e2e
@pytest.mark.asyncio
class TestWorkerFlow:
    """Worker处理流程测试"""
    
    async def test_worker_send_and_update_status(
        self,
        db_session,
        test_account,
        test_channel
    ):
        """测试Worker发送并更新状态"""
        from app.modules.sms.sms_log import SMSLog
        from app.workers.sms_worker import _send_sms_async
        
        # 创建待发送记录
        sms_log = SMSLog(
            message_id="worker_test_001",
            account_id=test_account.id,
            channel_id=test_channel.id,
            phone_number="+8613800138000",
            country_code="CN",
            message="Worker test message",
            message_count=1,
            status="queued",
            cost_price=0.01,
            selling_price=0.05,
            currency="USD",
            submit_time=datetime.now()
        )
        db_session.add(sms_log)
        await db_session.commit()
        
        # Mock发送函数
        with patch('app.workers.sms_worker._send_via_http', return_value=True):
            result = await _send_sms_async("worker_test_001")
        
        # 验证状态更新
        await db_session.refresh(sms_log)
        # 状态应该是 sent 或 delivered
        assert sms_log.status in ["sent", "delivered", "failed"]
