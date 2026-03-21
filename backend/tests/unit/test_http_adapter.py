"""
HTTP Adapter 单元测试
"""
import pytest
import json
from unittest.mock import MagicMock, patch, AsyncMock


@pytest.fixture
def mock_http_channel():
    """创建Mock HTTP通道对象"""
    channel = MagicMock()
    channel.id = 1
    channel.channel_code = "TEST-HTTP"
    channel.api_url = "https://api.test.com/sms/send"
    channel.username = "test_user"
    channel.password = "test_pass"
    channel.api_key = "test_api_key_12345"
    channel.default_sender_id = "TestSID"
    channel.config_json = json.dumps({
        "payload_template": "default",
        "auth_type": "bearer"
    })
    return channel


@pytest.fixture
def mock_sms_log():
    """创建Mock短信日志对象"""
    sms_log = MagicMock()
    sms_log.message_id = "http_test_msg_001"
    sms_log.phone_number = "+8613800138000"
    sms_log.message = "Test HTTP message"
    sms_log.sender_id = "TEST"
    return sms_log


class TestHTTPAdapterInit:
    """HTTP适配器初始化测试"""
    
    @pytest.mark.unit
    def test_adapter_init(self, mock_http_channel):
        """测试适配器初始化"""
        from app.workers.adapters.http_adapter import HTTPAdapter
        
        adapter = HTTPAdapter(mock_http_channel)
        
        assert adapter.channel == mock_http_channel
        assert adapter.config is not None
    
    @pytest.mark.unit
    def test_parse_config_valid_json(self, mock_http_channel):
        """测试解析有效配置"""
        from app.workers.adapters.http_adapter import HTTPAdapter
        
        adapter = HTTPAdapter(mock_http_channel)
        
        assert adapter.config.get("payload_template") == "default"
        assert adapter.config.get("auth_type") == "bearer"
    
    @pytest.mark.unit
    def test_parse_config_invalid_json(self, mock_http_channel):
        """测试解析无效配置"""
        from app.workers.adapters.http_adapter import HTTPAdapter
        
        mock_http_channel.config_json = "invalid json {"
        
        adapter = HTTPAdapter(mock_http_channel)
        
        assert adapter.config == {}
    
    @pytest.mark.unit
    def test_parse_config_none(self, mock_http_channel):
        """测试空配置"""
        from app.workers.adapters.http_adapter import HTTPAdapter
        
        mock_http_channel.config_json = None
        
        adapter = HTTPAdapter(mock_http_channel)
        
        assert adapter.config == {}


class TestHTTPAdapterSend:
    """HTTP发送测试"""
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_success(self, mock_http_channel, mock_sms_log):
        """测试发送成功"""
        from app.workers.adapters.http_adapter import HTTPAdapter
        
        adapter = HTTPAdapter(mock_http_channel)
        
        # Mock httpx响应
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message_id": "external_123"}
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            
            success, msg_id, error = await adapter.send(mock_sms_log)
            
            assert success is True
            assert msg_id == "external_123"
            assert error is None
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_success_201(self, mock_http_channel, mock_sms_log):
        """测试201响应也算成功"""
        from app.workers.adapters.http_adapter import HTTPAdapter
        
        adapter = HTTPAdapter(mock_http_channel)
        
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": "created_123"}
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            
            success, msg_id, error = await adapter.send(mock_sms_log)
            
            assert success is True
            assert msg_id == "created_123"
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_failure_400(self, mock_http_channel, mock_sms_log):
        """测试400错误响应"""
        from app.workers.adapters.http_adapter import HTTPAdapter
        
        adapter = HTTPAdapter(mock_http_channel)
        
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request: Invalid phone number"
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            
            success, msg_id, error = await adapter.send(mock_sms_log)
            
            assert success is False
            assert msg_id is None
            assert "400" in error
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_failure_500(self, mock_http_channel, mock_sms_log):
        """测试500服务器错误"""
        from app.workers.adapters.http_adapter import HTTPAdapter
        
        adapter = HTTPAdapter(mock_http_channel)
        
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            
            success, msg_id, error = await adapter.send(mock_sms_log)
            
            assert success is False
            assert "500" in error
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_timeout(self, mock_http_channel, mock_sms_log):
        """测试请求超时"""
        import httpx
        from app.workers.adapters.http_adapter import HTTPAdapter
        
        adapter = HTTPAdapter(mock_http_channel)
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.TimeoutException("Request timeout")
            )
            
            success, msg_id, error = await adapter.send(mock_sms_log)
            
            assert success is False
            assert "timeout" in error.lower()
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_connection_error(self, mock_http_channel, mock_sms_log):
        """测试连接错误"""
        from app.workers.adapters.http_adapter import HTTPAdapter
        
        adapter = HTTPAdapter(mock_http_channel)
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=Exception("Connection refused")
            )
            
            success, msg_id, error = await adapter.send(mock_sms_log)
            
            assert success is False
            assert error is not None


class TestHTTPPayloadTemplates:
    """Payload模板测试"""
    
    @pytest.mark.unit
    def test_default_payload(self, mock_http_channel, mock_sms_log):
        """测试默认payload格式"""
        from app.workers.adapters.http_adapter import HTTPAdapter
        
        mock_http_channel.config_json = json.dumps({"payload_template": "default"})
        adapter = HTTPAdapter(mock_http_channel)
        
        payload = adapter._build_payload(mock_sms_log)
        
        assert payload["phone_number"] == mock_sms_log.phone_number
        assert payload["message"] == mock_sms_log.message
        assert payload["sender_id"] == mock_sms_log.sender_id
        assert payload["message_id"] == mock_sms_log.message_id
    
    @pytest.mark.unit
    def test_twilio_payload(self, mock_http_channel, mock_sms_log):
        """测试Twilio payload格式"""
        from app.workers.adapters.http_adapter import HTTPAdapter
        
        mock_http_channel.config_json = json.dumps({"payload_template": "twilio"})
        adapter = HTTPAdapter(mock_http_channel)
        
        payload = adapter._build_payload(mock_sms_log)
        
        assert payload["To"] == mock_sms_log.phone_number
        assert payload["From"] == mock_sms_log.sender_id
        assert payload["Body"] == mock_sms_log.message
    
    @pytest.mark.unit
    def test_nexmo_payload(self, mock_http_channel, mock_sms_log):
        """测试Nexmo payload格式"""
        from app.workers.adapters.http_adapter import HTTPAdapter
        
        mock_http_channel.config_json = json.dumps({"payload_template": "nexmo"})
        adapter = HTTPAdapter(mock_http_channel)
        
        payload = adapter._build_payload(mock_sms_log)
        
        assert payload["to"] == mock_sms_log.phone_number
        assert payload["from"] == mock_sms_log.sender_id
        assert payload["text"] == mock_sms_log.message


class TestHTTPHeaders:
    """请求头构建测试"""
    
    @pytest.mark.unit
    def test_bearer_auth(self, mock_http_channel):
        """测试Bearer认证"""
        from app.workers.adapters.http_adapter import HTTPAdapter
        
        mock_http_channel.config_json = json.dumps({"auth_type": "bearer"})
        adapter = HTTPAdapter(mock_http_channel)
        
        headers = adapter._build_headers()
        
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Bearer ")
        assert mock_http_channel.api_key in headers["Authorization"]
    
    @pytest.mark.unit
    def test_basic_auth(self, mock_http_channel):
        """测试Basic认证"""
        from app.workers.adapters.http_adapter import HTTPAdapter
        import base64
        
        mock_http_channel.config_json = json.dumps({"auth_type": "basic"})
        adapter = HTTPAdapter(mock_http_channel)
        
        headers = adapter._build_headers()
        
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Basic ")
    
    @pytest.mark.unit
    def test_header_auth(self, mock_http_channel):
        """测试Header方式认证"""
        from app.workers.adapters.http_adapter import HTTPAdapter
        
        mock_http_channel.config_json = json.dumps({
            "auth_type": "header",
            "auth_header_name": "X-Custom-Key"
        })
        adapter = HTTPAdapter(mock_http_channel)
        
        headers = adapter._build_headers()
        
        assert "X-Custom-Key" in headers
        assert headers["X-Custom-Key"] == mock_http_channel.api_key
    
    @pytest.mark.unit
    def test_custom_headers(self, mock_http_channel):
        """测试自定义请求头"""
        from app.workers.adapters.http_adapter import HTTPAdapter
        
        mock_http_channel.config_json = json.dumps({
            "custom_headers": {
                "X-Trace-Id": "trace123",
                "X-Client-Version": "1.0"
            }
        })
        adapter = HTTPAdapter(mock_http_channel)
        
        headers = adapter._build_headers()
        
        assert headers["X-Trace-Id"] == "trace123"
        assert headers["X-Client-Version"] == "1.0"
    
    @pytest.mark.unit
    def test_content_type_header(self, mock_http_channel):
        """测试Content-Type头"""
        from app.workers.adapters.http_adapter import HTTPAdapter
        
        adapter = HTTPAdapter(mock_http_channel)
        headers = adapter._build_headers()
        
        assert headers["Content-Type"] == "application/json"
    
    @pytest.mark.unit
    def test_user_agent_header(self, mock_http_channel):
        """测试User-Agent头"""
        from app.workers.adapters.http_adapter import HTTPAdapter
        
        adapter = HTTPAdapter(mock_http_channel)
        headers = adapter._build_headers()
        
        assert "User-Agent" in headers
        assert "SMSC-Gateway" in headers["User-Agent"]


class TestHTTPMessageIdExtraction:
    """消息ID提取测试"""
    
    @pytest.mark.unit
    def test_extract_message_id(self, mock_http_channel):
        """测试标准字段提取"""
        from app.workers.adapters.http_adapter import HTTPAdapter
        
        adapter = HTTPAdapter(mock_http_channel)
        
        response = {"message_id": "msg_123"}
        assert adapter._extract_message_id(response) == "msg_123"
    
    @pytest.mark.unit
    def test_extract_message_id_alternative_keys(self, mock_http_channel):
        """测试替代字段名"""
        from app.workers.adapters.http_adapter import HTTPAdapter
        
        adapter = HTTPAdapter(mock_http_channel)
        
        # messageId
        assert adapter._extract_message_id({"messageId": "id_1"}) == "id_1"
        
        # id
        assert adapter._extract_message_id({"id": "id_2"}) == "id_2"
        
        # sid (Twilio style)
        assert adapter._extract_message_id({"sid": "SM123"}) == "SM123"
        
        # msg_id
        assert adapter._extract_message_id({"msg_id": "id_3"}) == "id_3"
    
    @pytest.mark.unit
    def test_extract_message_id_nested(self, mock_http_channel):
        """测试嵌套结构"""
        from app.workers.adapters.http_adapter import HTTPAdapter
        
        adapter = HTTPAdapter(mock_http_channel)
        
        response = {
            "status": "ok",
            "data": {
                "message_id": "nested_123"
            }
        }
        assert adapter._extract_message_id(response) == "nested_123"
    
    @pytest.mark.unit
    def test_extract_message_id_not_found(self, mock_http_channel):
        """测试未找到消息ID"""
        from app.workers.adapters.http_adapter import HTTPAdapter
        
        adapter = HTTPAdapter(mock_http_channel)
        
        response = {"status": "ok", "result": "success"}
        assert adapter._extract_message_id(response) is None
    
    @pytest.mark.unit
    def test_extract_message_id_numeric(self, mock_http_channel):
        """测试数字类型ID转换"""
        from app.workers.adapters.http_adapter import HTTPAdapter
        
        adapter = HTTPAdapter(mock_http_channel)
        
        response = {"id": 12345}
        result = adapter._extract_message_id(response)
        
        assert result == "12345"
        assert isinstance(result, str)


class TestHTTPNoApiKey:
    """无API Key场景测试"""
    
    @pytest.mark.unit
    def test_no_api_key(self, mock_http_channel):
        """测试无API Key时不添加认证头"""
        from app.workers.adapters.http_adapter import HTTPAdapter
        
        mock_http_channel.api_key = None
        adapter = HTTPAdapter(mock_http_channel)
        
        headers = adapter._build_headers()
        
        assert "Authorization" not in headers
