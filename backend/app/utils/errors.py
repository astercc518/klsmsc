"""
错误处理模块
"""
from typing import Any, Dict, Optional
from fastapi import HTTPException, status


class SMSGatewayException(Exception):
    """基础异常类"""
    
    def __init__(
        self,
        message: str,
        error_code: str = "INTERNAL_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class ValidationError(SMSGatewayException):
    """参数验证错误"""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details
        )


class AuthenticationError(SMSGatewayException):
    """认证错误"""
    
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(
            message=message,
            error_code="AUTHENTICATION_ERROR",
            status_code=status.HTTP_401_UNAUTHORIZED
        )


class AuthorizationError(SMSGatewayException):
    """授权错误"""
    
    def __init__(self, message: str = "Permission denied"):
        super().__init__(
            message=message,
            error_code="AUTHORIZATION_ERROR",
            status_code=status.HTTP_403_FORBIDDEN
        )


class ResourceNotFoundError(SMSGatewayException):
    """资源不存在错误"""
    
    def __init__(self, message: str = "Resource not found"):
        super().__init__(
            message=message,
            error_code="RESOURCE_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND
        )


class InsufficientBalanceError(SMSGatewayException):
    """余额不足错误"""
    
    def __init__(self, required: float, available: float):
        super().__init__(
            message=f"Insufficient balance. Required: {required}, Available: {available}",
            error_code="INSUFFICIENT_BALANCE",
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            details={"required": required, "available": available}
        )


class ChannelNotAvailableError(SMSGatewayException):
    """通道不可用错误"""
    
    def __init__(self, message: str = "No available channel"):
        super().__init__(
            message=message,
            error_code="CHANNEL_NOT_AVAILABLE",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )


class RateLimitExceededError(SMSGatewayException):
    """限流错误"""
    
    def __init__(self, limit: int):
        super().__init__(
            message=f"Rate limit exceeded: {limit} requests per minute",
            error_code="RATE_LIMIT_EXCEEDED",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details={"limit": limit}
        )


class InvalidPhoneNumberError(ValidationError):
    """无效电话号码错误"""
    
    def __init__(self, phone_number: str):
        super().__init__(
            message=f"Invalid phone number: {phone_number}",
            details={"phone_number": phone_number}
        )


class PricingNotFoundError(SMSGatewayException):
    """未找到计费规则错误"""
    
    def __init__(self, country_code: str, channel_id: int):
        super().__init__(
            message=f"No pricing found for country {country_code} on channel {channel_id}",
            error_code="PRICING_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"country_code": country_code, "channel_id": channel_id}
        )


def error_response(exc: SMSGatewayException) -> Dict[str, Any]:
    """生成标准错误响应"""
    return {
        "success": False,
        "error": {
            "code": exc.error_code,
            "message": exc.message,
            "details": exc.details
        }
    }

