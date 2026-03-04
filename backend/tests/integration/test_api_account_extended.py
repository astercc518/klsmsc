"""
账户API扩展集成测试
"""
import pytest
from fastapi import status
from app.core.auth import AuthService


@pytest.mark.integration
def test_register_account_success(client, db_session):
    """测试账户注册成功"""
    response = client.post(
        "/api/v1/account/register",
        json={
            "account_name": "新测试用户",
            "email": "newtest@example.com",
            "password": "password123",
            "company_name": "测试公司"
        }
    )
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["success"] is True
    assert "api_key" in data
    assert "api_secret" in data


@pytest.mark.integration
def test_register_account_duplicate_email(client, test_account):
    """测试注册重复邮箱"""
    response = client.post(
        "/api/v1/account/register",
        json={
            "account_name": "重复用户",
            "email": test_account.email,  # 使用已存在的邮箱
            "password": "password123"
        }
    )
    
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.integration
def test_get_account_info(client, test_account):
    """测试获取账户信息"""
    response = client.get(
        "/api/v1/account/info",
        headers={"X-API-Key": test_account.api_key}
    )
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == test_account.id
    assert data["email"] == test_account.email
    assert data["account_name"] == test_account.account_name


@pytest.mark.integration
def test_get_balance_unauthorized(client):
    """测试未授权访问余额"""
    response = client.get("/api/v1/account/balance")
    
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.integration
def test_get_balance_invalid_api_key(client):
    """测试无效API Key"""
    response = client.get(
        "/api/v1/account/balance",
        headers={"X-API-Key": "invalid_key_12345"}
    )
    
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
