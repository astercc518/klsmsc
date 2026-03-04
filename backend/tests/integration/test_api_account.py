"""
账户API集成测试
"""
import pytest
from fastapi import status


@pytest.mark.integration
def test_register_account(client, db_session):
    """测试账户注册"""
    response = client.post(
        "/api/v1/account/register",
        json={
            "account_name": "新用户",
            "email": "newuser@example.com",
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
def test_login_success(client, test_account):
    """测试登录成功"""
    response = client.post(
        "/api/v1/account/login",
        json={
            "email": "test@example.com",
            "password": "test123"
        }
    )
    
    # 注意：这里需要实际密码，但测试账户使用的是哈希
    # 实际测试时需要正确的密码验证逻辑
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.integration
def test_get_balance(client, test_account):
    """测试查询余额"""
    response = client.get(
        "/api/v1/account/balance",
        headers={"X-API-Key": test_account.api_key}
    )
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "balance" in data
    assert "currency" in data


@pytest.mark.integration
def test_get_account_info(client, test_account):
    """测试查询账户信息"""
    response = client.get(
        "/api/v1/account/info",
        headers={"X-API-Key": test_account.api_key}
    )
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == test_account.id
    assert data["email"] == test_account.email
