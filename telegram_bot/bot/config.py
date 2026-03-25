"""
Telegram Bot配置
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class BotSettings(BaseSettings):
    """Bot配置"""
    
    # Telegram配置
    TELEGRAM_BOT_TOKEN: str = Field(..., description="Telegram Bot Token")
    
    # 后端API配置
    API_BASE_URL: str = Field(default="http://localhost:8000", description="后端API地址")
    # 与后端 Settings.TELEGRAM_STAFF_API_SECRET 一致，用于「我的客户」快捷登录
    TELEGRAM_STAFF_API_SECRET: Optional[str] = Field(default=None, description="销售快捷登录共享密钥")
    
    # 日志配置
    LOG_LEVEL: str = Field(default="INFO", description="日志级别")
    LOG_FILE: str = Field(default="logs/bot.log", description="日志文件路径")
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = BotSettings()

