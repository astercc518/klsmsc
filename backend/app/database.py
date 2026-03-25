"""
数据库连接管理
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.config import settings
from app.utils.logger import get_logger

_schema_logger = get_logger(__name__)

# 创建异步引擎（仅开发环境开启 SQL echo，避免泄露敏感信息）
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=(settings.APP_DEBUG and settings.APP_ENV == "development"),
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=3600
)

# 创建会话工厂
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

# 声明基类
Base = declarative_base()


async def get_db() -> AsyncSession:
    """获取数据库会话"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """初始化数据库"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def ensure_channel_dlr_preference_columns():
    """
    与 Channel ORM 对齐：补齐 channels 表 DLR 相关列。
    未执行手工迁移时，SELECT Channel 会因 Unknown column 导致整站 500；启动时自动 ALTER。
    仅处理 MySQL / MariaDB。
    """
    url = (settings.DATABASE_URL or "").lower()
    if "mysql" not in url and "mariadb" not in url:
        return
    col_defs = [
        (
            "smpp_dlr_socket_hold_seconds",
            "INT NULL DEFAULT NULL COMMENT 'SMPP发送成功后保持TCP秒数以接收deliver_sm'",
        ),
        (
            "dlr_sent_timeout_hours",
            "INT NULL DEFAULT NULL COMMENT 'sent状态最长等待终态DLR小时数'",
        ),
    ]
    try:
        async with engine.begin() as conn:
            for col_name, col_sql in col_defs:
                r = await conn.execute(
                    text(
                        "SELECT COUNT(*) AS c FROM information_schema.COLUMNS "
                        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'channels' "
                        "AND COLUMN_NAME = :col"
                    ),
                    {"col": col_name},
                )
                row = r.first()
                if row and (row[0] or 0) > 0:
                    continue
                await conn.execute(
                    text(f"ALTER TABLE channels ADD COLUMN `{col_name}` {col_sql}")
                )
                _schema_logger.info("已自动补齐 channels 列: %s", col_name)
    except Exception as e:
        _schema_logger.warning(
            "自动补齐 channels DLR 列失败（请手动执行 scripts/add_channel_dlr_columns.sql）: %s",
            e,
        )


async def close_db():
    """关闭数据库连接"""
    await engine.dispose()

