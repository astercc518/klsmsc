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
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30        # access token 30 分钟
    JWT_REFRESH_TOKEN_EXPIRE_HOURS: int = 24         # refresh token 24 小时

    _ALLOWED_JWT_ALGORITHMS = {"HS256", "HS384", "HS512", "RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}

    @field_validator("JWT_ALGORITHM", mode="before")
    @classmethod
    def _validate_jwt_algorithm(cls, v: str) -> str:
        if v not in cls._ALLOWED_JWT_ALGORITHMS:
            raise ValueError(
                f"不支持的 JWT 算法 '{v}'，允许值：{sorted(cls._ALLOWED_JWT_ALGORITHMS)}"
            )
        return v

    @field_validator("JWT_SECRET_KEY", mode="before")
    @classmethod
    def _ensure_jwt_secret(cls, v: str, info) -> str:
        if not v:
            env = (info.data or {}).get("APP_ENV", "development")
            if env == "production":
                raise ValueError(
                    "生产环境必须显式配置 JWT_SECRET_KEY（建议：openssl rand -hex 48）"
                )
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
    # 业务 Bot 游客「联系客服」无可用员工 tg 时的默认跳转（t.me 或 https 链接）
    # 游客户服兜底：勿用不存在的 @用户名；默认与落地页一致指向业务 Bot
    TELEGRAM_CS_FALLBACK_URL: str = "https://t.me/kaolachbot"
    # 生成客户模拟登录链接用的前端基址（无尾斜杠）
    PUBLIC_WEB_BASE_URL: str = "https://www.kaolach.com"

    # 对外 SMPP 服务配置（客户连接用）
    SMPP_SERVER_HOST: str = "smpp.kaolach.com"
    SMPP_SERVER_PORT: int = 2775

    # 内部端点共享密钥：Go SMPP 入站网关回调 /api/v1/_internal/smpp_submit 时携带 X-Internal-Token
    # 生产环境必须改为 openssl rand -hex 32 生成的强随机值
    INTERNAL_TOKEN: str = "change-me-internal-token"

    @field_validator("INTERNAL_TOKEN", mode="before")
    @classmethod
    def _validate_internal_token(cls, v: str, info) -> str:
        env = (info.data or {}).get("APP_ENV", "development")
        if env == "production" and v in {"change-me-internal-token", "", "changeme"}:
            raise ValueError(
                "生产环境必须显式配置 INTERNAL_TOKEN（建议：openssl rand -hex 32）"
            )
        return v

    # 通道管理「真实 SMPP bind」：由 go-smpp-gateway 内网 HTTP 执行（须与网关 SMPP_PROBE_TOKEN 一致）
    SMPP_GATEWAY_PROBE_URL: Optional[str] = None  # 例 http://smpp-gateway:8090
    SMPP_PROBE_TOKEN: Optional[str] = None

    # SMPP：多 Celery 子进程会并发 bind，上游单会话时易 ESME 13。为 True 时用 Redis 全局锁串行化，
    # 且提交成功后立即断开 TCP 以释放 bind——会导致无法在同连接上收到 deliver_sm，送达多依赖 HTTP 拉取/回调。
    # 默认 False：配合 worker-sms --concurrency=1 可兼顾「单会话 bind」与 SMPP 长连收 DLR（延迟断开）。
    # 高并发且仅 HTTP 回执时，可设 True 并在 compose 中提高 worker-sms concurrency。
    SMPP_REDIS_CLUSTER_LOCK: bool = False

    # submit_sm 发出后等待 submit_sm_resp 的最长秒数（入站可被 deliver_sm 插队，需 drain 至同 sequence 应答）
    SMPP_SUBMIT_RESP_WAIT_SECONDS: float = Field(default=8.0, ge=1.0, le=120.0)

    # 非集群锁模式下，发送后保持 SMPP 连接的最长秒数以便接收 deliver_sm（快通道可改短，慢通道可至 24h；更久需靠 HTTP 拉取/回调）
    SMPP_DLR_SOCKET_HOLD_SECONDS: int = Field(default=300, ge=60, le=86400)

    # SMPP 窗口化批量发送：一次持锁内连续发出的 submit_sm 条数（建议 10-50）
    SMPP_WINDOW_SIZE: int = Field(default=50, ge=1, le=100)

    # sent 状态超过此时长未收到终态 DLR 则标记为 expired（快通道可改短；慢通道可设 72～168；最大 720h≈30 天）
    DLR_SENT_TIMEOUT_HOURS: int = Field(default=72, ge=4, le=720)

    # 定时拉取上游 DLR 报告的 HTTP 超时（秒）
    DLR_PULL_HTTP_TIMEOUT_SECONDS: float = Field(default=60.0, ge=10.0, le=300.0)

    # HTTP 通道单条请求超过该秒数时 worker 打 WARNING，便于区分「Redis max_tps 未跑满」与「上游/网络慢」
    SMS_HTTP_SLOW_WARN_SECONDS: float = Field(default=1.5, ge=0.5, le=120.0)

    # OKCC 语音客户全量同步：由 Celery Beat 按间隔触发（与手动「同步OKCC余额」相同逻辑）
    OKCC_BEAT_SYNC_ENABLED: bool = True
    OKCC_BEAT_SYNC_INTERVAL_SECONDS: int = Field(default=300, ge=60, le=86400)  # 默认 5 分钟

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


# 全局配置实例
settings = Settings()

