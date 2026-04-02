"""
数据库连接管理

Schema 变更统一通过 Alembic 迁移管理，应用启动时不再执行 create_all 或 ALTER TABLE。
部署流程：docker-compose up 前先执行 alembic upgrade head。
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.config import settings
from app.utils.logger import get_logger

_logger = get_logger(__name__)

# 创建异步引擎参数
engine_kwargs = {
    "echo": (settings.APP_DEBUG and settings.APP_ENV == "development"),
}

# SQLite 不支持 pool_size 和 max_overflow
if "sqlite" not in settings.SQLALCHEMY_DATABASE_URL:
    engine_kwargs.update({
        "pool_size": settings.DATABASE_POOL_SIZE,
        "max_overflow": settings.DATABASE_MAX_OVERFLOW,
        "pool_pre_ping": True,
        "pool_recycle": 3600
    })

engine = create_async_engine(
    settings.SQLALCHEMY_DATABASE_URL,
    **engine_kwargs
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
    """
    应用启动时的数据库连通性验证。
    Schema 变更已统一由 Alembic 管理，不再执行 create_all / ALTER TABLE。
    """
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        _logger.info("数据库连接验证成功")
    except Exception as e:
        _logger.error("数据库连接验证失败: %s", e)
        raise


async def close_db():
    """关闭数据库连接"""
    await engine.dispose()


