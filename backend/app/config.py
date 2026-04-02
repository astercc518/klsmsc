"""
配置管理模块
"""
import secrets
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator


class Settings(BaseSettings):
    """应用配置"""
    
    # 应用配置
    APP_NAME: str = "考拉出海 Gateway"
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    
    # CORS 允许的来源（生产环境必须设置为具体域名）
    CORS_ORIGINS: str = ""
    
    @property
    def cors_origin_list(self) -> List[str]:
        """将逗号分隔的 CORS_ORIGINS 转为列表"""
        if not self.CORS_ORIGINS:
            if self.APP_ENV == "development":
                return ["*"]
            return []
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]
    
    # 数据库配置
    DATABASE_HOST: str = "localhost"
    DATABASE_PORT: int = 3306
    DATABASE_USER: str = "smsuser"
    DATABASE_PASSWORD: str = "smspass"
    DATABASE_NAME: str = "sms_system"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10
    
    # 数据库连接 URL (如果设置了环境变量 DATABASE_URL，则优先使用)
    DATABASE_URL: str = ""
    
    # 最终使用的数据库连接 URL（内部属性）
    @property
    def SQLALCHEMY_DATABASE_URL(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"mysql+asyncmy://{self.DATABASE_USER}:{self.DATABASE_PASSWORD}"
            f"@{self.DATABASE_HOST}:{self.DATABASE_PORT}/{self.DATABASE_NAME}?charset=utf8mb4"
        )
    
    # Redis配置
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    REDIS_MAX_CONNECTIONS: int = 50
    
    @property
    def REDIS_URL(self) -> str:
        """生成Redis连接URL"""
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
    
    # RabbitMQ配置
    RABBITMQ_HOST: str = "localhost"
    RABBITMQ_PORT: int = 5672
    RABBITMQ_USER: str = "smsc_mq"
    RABBITMQ_PASSWORD: str = "smsc_mq_pass"
    RABBITMQ_VHOST: str = "/"
    
    @property
    def RABBITMQ_URL(self) -> str:
        """生成RabbitMQ连接URL"""
        return (
            f"amqp://{self.RABBITMQ_USER}:{self.RABBITMQ_PASSWORD}"
            f"@{self.RABBITMQ_HOST}:{self.RABBITMQ_PORT}{self.RABBITMQ_VHOST}"
        )
    
    # JWT配置（默认值仅用于开发，生产必须通过环境变量覆盖）
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    
    @field_validator("JWT_SECRET_KEY", mode="before")
    @classmethod
    def _ensure_jwt_secret(cls, v: str) -> str:
        if not v:
            return secrets.token_urlsafe(48)
        return v
    
    # API限流
    RATE_LIMIT_PER_MINUTE: int = 1000
    
    # 日志配置
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/app.log"
    
    # 监控配置
    PROMETHEUS_PORT: int = 9090
    
    # AI 文案生成配置
    AI_API_KEY: Optional[str] = None
    AI_API_URL: str = "https://api.deepseek.com/v1/chat/completions"
    AI_MODEL: str = "deepseek-chat"

    # DLR 回调安全配置
    DLR_CALLBACK_TOKEN: Optional[str] = None
    DLR_CALLBACK_IP_WHITELIST: str = ""
    # 设为 true/1 时允许无认证回调（上游不支持 Token 时使用，生产环境建议用 Token 或 IP 白名单）
    DLR_CALLBACK_OPEN: bool = False

    @property
    def dlr_callback_ip_list(self) -> List[str]:
        """将逗号分隔的 DLR IP 白名单转为列表"""
        if not self.DLR_CALLBACK_IP_WHITELIST:
            return []
        return [ip.strip() for ip in self.DLR_CALLBACK_IP_WHITELIST.split(",") if ip.strip()]

    # Telegram Bot配置
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_ADMIN_GROUP_ID: Optional[str] = None
    # 业务助手「销售快捷登录」：Bot 调用 /admin/telegram/sales-impersonate 时校验，须与 Bot 环境变量一致
    TELEGRAM_STAFF_API_SECRET: Optional[str] = None
    # 生成客户模拟登录链接用的前端基址（无尾斜杠）
    PUBLIC_WEB_BASE_URL: str = "https://www.kaolach.com"

    # SMPP：多 Celery 子进程会并发 bind，上游单会话时易 ESME 13。为 True 时用 Redis 全局锁串行化，
    # 且提交成功后立即断开 TCP 以释放 bind——会导致无法在同连接上收到 deliver_sm，送达多依赖 HTTP 拉取/回调。
    # 默认 False：配合 worker-sms --concurrency=1 可兼顾「单会话 bind」与 SMPP 长连收 DLR（延迟断开）。
    # 高并发且仅 HTTP 回执时，可设 True 并在 compose 中提高 worker-sms concurrency。
    SMPP_REDIS_CLUSTER_LOCK: bool = False

    # submit_sm 发出后等待 submit_sm_resp 的最长秒数（入站可被 deliver_sm 插队，需 drain 至同 sequence 应答）
    SMPP_SUBMIT_RESP_WAIT_SECONDS: float = Field(default=8.0, ge=1.0, le=120.0)

    # 非集群锁模式下，发送后保持 SMPP 连接的最长秒数以便接收 deliver_sm（快通道可改短，慢通道可至 24h；更久需靠 HTTP 拉取/回调）
    SMPP_DLR_SOCKET_HOLD_SECONDS: int = Field(default=300, ge=60, le=86400)

    # sent 状态超过此时长未收到终态 DLR 则标记为 expired（快通道可改短；慢通道可设 72～168；最大 720h≈30 天）
    DLR_SENT_TIMEOUT_HOURS: int = Field(default=72, ge=4, le=720)

    # 定时拉取上游 DLR 报告的 HTTP 超时（秒）
    DLR_PULL_HTTP_TIMEOUT_SECONDS: float = Field(default=60.0, ge=10.0, le=300.0)

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


# 全局配置实例
settings = Settings()

