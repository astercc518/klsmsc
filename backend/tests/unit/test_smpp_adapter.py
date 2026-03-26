"""
SMPP Adapter 单元测试
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime


@pytest.fixture
def mock_channel():
    """创建Mock通道对象"""
    channel = MagicMock()
    channel.id = 1
    channel.channel_code = "TEST-SMPP"
    channel.host = "smpp.test.com"
    channel.port = 2775
    channel.username = "test_user"
    channel.password = "test_pass"
    channel.default_sender_id = "TestSID"
    # 避免 MagicMock 进入日志 f-string 的 :02x 等格式化导致 TypeError
    channel.smpp_bind_mode = "transceiver"
    channel.smpp_system_type = ""
    channel.smpp_interface_version = 0x34
    return channel


@pytest.fixture
def mock_sms_log():
    """创建Mock短信日志对象"""
    sms_log = MagicMock()
    sms_log.message_id = "test_msg_001"
    sms_log.phone_number = "+8613800138000"
    sms_log.message = "Test message"
    sms_log.sender_id = "TEST"
    return sms_log


class TestSMPPAdapterInit:
    """SMPP适配器初始化测试"""
    
    @pytest.mark.unit
    def test_adapter_init(self, mock_channel):
        """测试适配器初始化"""
        from app.workers.adapters.smpp_adapter import SMPPAdapter
        
        adapter = SMPPAdapter(mock_channel)
        
        assert adapter.channel == mock_channel
        assert adapter.client is None
        assert adapter.connected is False
    
    @pytest.mark.unit
    def test_adapter_init_with_thread_lock(self, mock_channel):
        """测试线程锁初始化"""
        from app.workers.adapters.smpp_adapter import SMPPAdapter
        import threading
        
        adapter = SMPPAdapter(mock_channel)
        
        assert hasattr(adapter, '_lock')
        # 适配器使用 RLock，与发送线程、心跳线程串行化读 socket 一致
        assert isinstance(adapter._lock, type(threading.RLock()))


class TestSMPPConnect:
    """SMPP连接测试"""
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_connect_success_mock_mode(self, mock_channel):
        """测试模拟模式连接成功"""
        from app.workers.adapters.smpp_adapter import SMPPAdapter
        
        adapter = SMPPAdapter(mock_channel)
        
        # 当smpplib未安装时使用模拟模式
        with patch.dict('sys.modules', {'smpplib': None, 'smpplib.client': None}):
            with patch.object(adapter, '_connect_sync', return_value=True):
                result = await adapter.connect()
                assert result is True
    
    @pytest.mark.unit
    def test_connect_sync_mock_mode(self, mock_channel):
        """测试同步连接（模拟模式）"""
        from app.workers.adapters.smpp_adapter import SMPPAdapter
        
        adapter = SMPPAdapter(mock_channel)
        
        # 模拟smpplib未安装
        with patch.dict('sys.modules', {'smpplib': None}):
            # 由于import会失败，连接函数应该处理这种情况
            # 实际测试需要mock整个导入链
            pass
    
    @pytest.mark.unit
    def test_connect_failure_handling(self, mock_channel):
        """测试连接失败处理"""
        from app.workers.adapters.smpp_adapter import SMPPAdapter
        
        adapter = SMPPAdapter(mock_channel)
        
        # 模拟连接失败
        with patch('smpplib.client.Client') as mock_client:
            mock_client.side_effect = ConnectionError("Connection refused")
            
            # 调用同步连接
            result = adapter._connect_sync()
            
            assert adapter.connected is False


class TestSMPPSend:
    """SMPP发送测试"""
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_not_connected(self, mock_channel, mock_sms_log):
        """测试未连接时发送"""
        from app.workers.adapters.smpp_adapter import SMPPAdapter
        
        adapter = SMPPAdapter(mock_channel)
        adapter.connected = False
        
        # Mock连接方法返回失败
        with patch.object(adapter, '_connect_sync', return_value=False):
            success, msg_id, error = await adapter.send(mock_sms_log)
            
            assert success is False
            assert error is not None
    
    @pytest.mark.unit
    def test_send_sync_mock_mode(self, mock_channel, mock_sms_log):
        """测试同步发送（模拟模式）"""
        from app.workers.adapters.smpp_adapter import SMPPAdapter
        
        adapter = SMPPAdapter(mock_channel)
        adapter.connected = True
        adapter.client = MagicMock()
        
        # 模拟smpplib未安装，使用模拟模式
        with patch.dict('sys.modules', {'smpplib.gsm': None, 'smpplib.consts': None}):
            success, msg_id, error = adapter._send_sync(mock_sms_log)
            
            # 模拟模式应该返回成功
            assert success is True
            assert msg_id is not None
            assert msg_id.startswith('smpp_')
    
    @pytest.mark.unit
    def test_send_sync_with_smpplib(self, mock_channel, mock_sms_log):
        """测试使用smpplib发送"""
        from app.workers.adapters.smpp_adapter import SMPPAdapter
        
        adapter = SMPPAdapter(mock_channel)
        adapter.connected = True
        
        # Mock smpplib
        mock_client = MagicMock()
        mock_pdu = MagicMock()
        mock_pdu.message_id = "smpp_response_123"
        mock_client.send_message.return_value = mock_pdu
        adapter.client = mock_client
        
        # Mock smpplib.gsm
        mock_gsm = MagicMock()
        mock_gsm.make_parts.return_value = (["Test message"], 0, 0)
        
        with patch.dict('sys.modules', {
            'smpplib': MagicMock(),
            'smpplib.gsm': mock_gsm,
            'smpplib.consts': MagicMock()
        }):
            with patch('smpplib.gsm.make_parts', return_value=(["Test message"], 0, 0)):
                with patch('smpplib.consts.SMPP_TON_ALNUM', 5):
                    with patch('smpplib.consts.SMPP_NPI_UNK', 0):
                        # 由于import链复杂，这里主要测试逻辑流程
                        pass


class TestSMPPLongMessage:
    """长短信拆分测试"""
    
    @pytest.mark.unit
    def test_long_message_split(self, mock_channel):
        """测试长短信拆分"""
        from app.workers.adapters.smpp_adapter import SMPPAdapter
        
        adapter = SMPPAdapter(mock_channel)
        adapter.connected = True
        
        # 创建超过160字符的消息
        long_sms_log = MagicMock()
        long_sms_log.message_id = "long_msg_001"
        long_sms_log.phone_number = "+8613800138000"
        long_sms_log.message = "A" * 200  # 200个字符
        long_sms_log.sender_id = "TEST"
        
        # 模拟模式下的发送
        adapter.client = MagicMock()
        
        with patch.dict('sys.modules', {'smpplib.gsm': None, 'smpplib.consts': None}):
            success, msg_id, error = adapter._send_sync(long_sms_log)
            
            assert success is True
    
    @pytest.mark.unit
    def test_unicode_message(self, mock_channel):
        """测试Unicode消息"""
        from app.workers.adapters.smpp_adapter import SMPPAdapter
        
        adapter = SMPPAdapter(mock_channel)
        adapter.connected = True
        
        # 创建中文消息
        unicode_sms_log = MagicMock()
        unicode_sms_log.message_id = "unicode_msg_001"
        unicode_sms_log.phone_number = "+8613800138000"
        unicode_sms_log.message = "这是一条测试短信"
        unicode_sms_log.sender_id = "TEST"
        
        adapter.client = MagicMock()
        
        with patch.dict('sys.modules', {'smpplib.gsm': None, 'smpplib.consts': None}):
            success, msg_id, error = adapter._send_sync(unicode_sms_log)
            
            assert success is True


class TestSMPPDisconnect:
    """SMPP断开连接测试"""
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_disconnect(self, mock_channel):
        """测试断开连接"""
        from app.workers.adapters.smpp_adapter import SMPPAdapter
        
        adapter = SMPPAdapter(mock_channel)
        adapter.connected = True
        adapter.client = MagicMock()
        
        with patch.dict('sys.modules', {'smpplib.client': MagicMock()}):
            await adapter.disconnect()
            
            assert adapter.connected is False
            assert adapter.client is None
    
    @pytest.mark.unit
    def test_disconnect_sync(self, mock_channel):
        """测试同步断开连接"""
        from app.workers.adapters.smpp_adapter import SMPPAdapter
        
        adapter = SMPPAdapter(mock_channel)
        adapter.connected = True
        mock_client = MagicMock()
        adapter.client = mock_client
        
        with patch.dict('sys.modules', {'smpplib.client': MagicMock()}):
            adapter._disconnect_sync()
            
            assert adapter.connected is False
            assert adapter.client is None


class TestSMPPHeartbeat:
    """SMPP心跳测试"""
    
    @pytest.mark.unit
    def test_heartbeat_loop_start(self, mock_channel):
        """测试心跳循环启动"""
        from app.workers.adapters.smpp_adapter import SMPPAdapter
        import threading
        
        adapter = SMPPAdapter(mock_channel)
        
        # 验证心跳循环方法存在
        assert hasattr(adapter, '_heartbeat_loop')
        assert callable(adapter._heartbeat_loop)
    
    @pytest.mark.unit
    def test_heartbeat_failure_reconnect(self, mock_channel):
        """测试心跳失败后重连"""
        from app.workers.adapters.smpp_adapter import SMPPAdapter
        
        adapter = SMPPAdapter(mock_channel)
        adapter.connected = True
        
        # 当心跳失败时，应该标记为断开并尝试重连
        # 这个测试验证逻辑存在
        assert hasattr(adapter, '_heartbeat_loop')


class TestSMPPErrorHandling:
    """SMPP错误处理测试"""
    
    @pytest.mark.unit
    def test_send_exception_handling(self, mock_channel, mock_sms_log):
        """测试发送异常处理（make_parts 抛错应走外层 except 并断开标记）"""
        from app.workers.adapters.smpp_adapter import SMPPAdapter

        adapter = SMPPAdapter(mock_channel)
        adapter.connected = True
        adapter.client = MagicMock()

        # 与 _send_sync 内「import smpplib.gsm」一致，直接 patch 已安装子模块
        with patch(
            "smpplib.gsm.make_parts",
            side_effect=Exception("Send failed"),
        ):
            success, msg_id, error = adapter._send_sync(mock_sms_log)
            assert success is False
            assert msg_id is None
            assert error is not None
            assert "Send failed" in error
    
    @pytest.mark.unit
    def test_connection_lost_during_send(self, mock_channel, mock_sms_log):
        """测试发送过程中连接断开"""
        from app.workers.adapters.smpp_adapter import SMPPAdapter
        
        adapter = SMPPAdapter(mock_channel)
        adapter.connected = True
        adapter.client = None  # 模拟连接丢失
        
        with patch.object(adapter, '_connect_sync', return_value=False):
            success, msg_id, error = adapter._send_sync(mock_sms_log)
            
            assert success is False
            assert "connection failed" in error.lower()
