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
        """将逗号分隔的 CORS_ORIGINS 转为列表。

        历史上 dev 环境为空时回落到 ["*"]，但一旦 APP_ENV 被误设为
        development 即等同于关闭 CORS，所以现在所有环境都强制显式声明；
        dev 同学需在 .env.local 写 `CORS_ORIGINS=http://localhost:5173`。
        """
        if not self.CORS_ORIGINS:
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

    @field_validator("JWT_ALGORITHM", mode="before")
    @classmethod
    def _validate_jwt_algorithm(cls, v: str) -> str:
        allowed = {"HS256", "HS384", "HS512", "RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}
        if v not in allowed:
            raise ValueError(
                f"不支持的 JWT 算法 '{v}'，允许值：{sorted(allowed)}"
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
    # AI_PROVIDER: "openai"=OpenAI 兼容接口(DeepSeek 等)；"google"/"gemini"=Google Gemini 原生接口
    AI_PROVIDER: str = "openai"
    AI_API_KEY: Optional[str] = None
    AI_API_URL: str = "https://api.deepseek.com/v1/chat/completions"
    AI_MODEL: str = "deepseek-chat"
    # Google Gemini 专用（AI_PROVIDER=google 时使用；未单独设置则回退到 AI_API_KEY/AI_MODEL）
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_API_BASE: str = "https://generativelanguage.googleapis.com/v1beta"
    # 可选出口代理：Gemini 免费接口对机房/部分地区 IP 做地域封锁，
    # 设置后 AI 调用经此代理出网（如 http://user:pass@host:port）
    AI_HTTP_PROXY: Optional[str] = None

    # 注水注册验证码求解 (CapSolver — GeeTest v4)
    CAPSOLVER_API_KEY: Optional[str] = None
    CAPSOLVER_API_URL: str = "https://api.capsolver.com"

    # DLR 回调安全配置
    DLR_CALLBACK_TOKEN: Optional[str] = None
    DLR_CALLBACK_IP_WHITELIST: str = ""
    # 设为 true/1 时允许无认证回调（上游不支持 Token 时使用，生产环境建议用 Token 或 IP 白名单）
    DLR_CALLBACK_OPEN: bool = False

    @field_validator("DLR_CALLBACK_OPEN", mode="before")
    @classmethod
    def _validate_dlr_open(cls, v, info) -> bool:
        env = (info.data or {}).get("APP_ENV", "development")
        is_open = str(v).lower() in {"1", "true", "yes", "y"} if not isinstance(v, bool) else bool(v)
        if env == "production" and is_open:
            raise ValueError(
                "生产环境禁止 DLR_CALLBACK_OPEN=true（任何人能伪造 DLR 篡改投递状态）。"
                "请改为配置 DLR_CALLBACK_TOKEN 或 DLR_CALLBACK_IP_WHITELIST"
            )
        return is_open

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

    # 软件授权(License)：公钥内嵌于 core/license.py，此处仅供 env 覆盖
    LICENSE_PUBLIC_KEY: Optional[str] = None
    # 机器指纹来源(docker 建议挂宿主 /etc/machine-id 到此路径)
    LICENSE_MACHINE_ID_FILE: str = "/etc/host-machine-id"
    # 可选:首次安装前从该 .lic 文件路径读取授权(后台上传后以 DB 为准)
    LICENSE_FILE: Optional[str] = None
    # 是否强制要求已安装授权:False(默认)未装证=宽松放行+横幅提醒,避免未发证即自锁;
    # 客户私有/OEM 分发版应设 True,使"未安装/被删除授权"也全停(防盗用裸跑)。
    LICENSE_REQUIRE: bool = False

    # 短链追踪配置
    # SHORT_LINK_BASE_URL：短链对外访问前缀，如 https://www.kaolach.com/s 或 https://go.kaolach.com/s
    SHORT_LINK_BASE_URL: str = "https://www.kaolach.com/s"
    # 占位符 {{TRACK_URL}}（不含内嵌 URL）时使用的兜底目标
    SHORT_LINK_DEFAULT_TARGET_URL: str = ""

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

    # 每通道独立发送队列：True 时 SMPP 整包/单条按 channel_id 投到 sms_send_smpp.{id}，
    # Go 网关每通道独立 consumer 消费，消除单一 sms_send_smpp FIFO 的 head-of-line 阻塞
    # （一个被上游限流的慢通道不再饿死其它通道）。默认 False，行为与改造前一致。
    # 灰度：先在 smpp-gateway 容器设 SMPP_PER_CHANNEL_QUEUES=1（消费者就绪），再在 api/worker
    # 容器设同名 env（生产端开始投递每通道队列）。queue.py / batch_inspector.py 直接读同名 env。
    SMPP_PER_CHANNEL_QUEUES: bool = False

    # sent 状态超过此时长未收到终态 DLR 则标记为 expired（快通道可改短；慢通道可设 72～168；最大 720h≈30 天）
    DLR_SENT_TIMEOUT_HOURS: int = Field(default=72, ge=4, le=720)

    # DLR 归属过滤（Python 侧，与 Go 网关 DLR_OWNERSHIP_FILTER 同名同义）：
    # =True 时，未匹配到 sms_log 的 DLR 在写入重试缓冲前，用网关写的归属键
    # dlr_owned:{channel_id}:{upstream_id} 复核——键不存在=共用上游账号的「外来回执」，
    # 直接丢弃不进缓冲，避免网关 IsOwned fail-open 窗口漏进来的外来回执 churn 满 1h 缓冲、
    # 放大成 sms_dlr 积压（2026-06 ch64/ch82 事故）。Redis 异常时 fail-open（仍缓冲，不误丢自家）。
    # 默认 False：行为与改造前一致；启用前须确认网关 DLR_OWNERSHIP_FILTER 已开且归属键已回填。
    DLR_OWNERSHIP_FILTER: bool = False

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

