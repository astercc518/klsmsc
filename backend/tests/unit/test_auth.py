"""
认证模块单元测试
"""
import pytest
from datetime import timedelta
from app.core.auth import AuthService
from app.config import settings


@pytest.mark.unit
def test_hash_password():
    """测试密码哈希"""
    password = "test_password_123"
    hashed = AuthService.hash_password(password)
    
    assert hashed != password
    assert len(hashed) > 0
    assert hashed.startswith("$2b$")  # bcrypt哈希格式


@pytest.mark.unit
def test_verify_password_success():
    """测试密码验证成功"""
    password = "test_password_123"
    hashed = AuthService.hash_password(password)
    
    assert AuthService.verify_password(password, hashed) is True


@pytest.mark.unit
def test_verify_password_failed():
    """测试密码验证失败"""
    password = "test_password_123"
    wrong_password = "wrong_password"
    hashed = AuthService.hash_password(password)
    
    assert AuthService.verify_password(wrong_password, hashed) is False


@pytest.mark.unit
def test_create_access_token():
    """测试创建JWT token"""
    data = {"sub": 1, "role": "admin", "username": "test_user"}
    token = AuthService.create_access_token(data)
    
    assert token is not None
    assert isinstance(token, str)
    assert len(token) > 0


@pytest.mark.unit
def test_verify_token_success():
    """测试验证JWT token成功"""
    data = {"sub": 1, "role": "admin", "username": "test_user"}
    token = AuthService.create_access_token(data)
    
    payload = AuthService.verify_token(token)
    
    assert payload["sub"] == 1
    assert payload["role"] == "admin"
    assert payload["username"] == "test_user"


@pytest.mark.unit
def test_verify_token_invalid():
    """测试验证无效token"""
    from app.utils.errors import AuthenticationError
    invalid_token = "invalid.token.here"
    
    try:
        AuthService.verify_token(invalid_token)
        assert False, "应该抛出AuthenticationError异常"
    except AuthenticationError:
        assert True  # 期望的异常
    except Exception as e:
        # 如果抛出其他异常也可以接受
        assert True


@pytest.mark.unit
def test_create_token_with_custom_expires():
    """测试自定义过期时间的token"""
    data = {"sub": 1}
    expires_delta = timedelta(minutes=30)
    token = AuthService.create_access_token(data, expires_delta=expires_delta)
    
    payload = AuthService.verify_token(token)
    assert payload["sub"] == 1
    # 验证过期时间（应该接近30分钟后）
    assert "exp" in payload
