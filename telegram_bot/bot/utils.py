import sys
import os

# 将 backend 目录添加到 path，以便可以直接引用 app 模块
# Docker中 backend 挂载在 /backend
current_dir = os.path.dirname(os.path.abspath(__file__))

# 首先尝试 Docker 环境的路径
docker_backend_path = "/backend"
# 本地开发环境的路径
local_backend_path = os.path.abspath(os.path.join(current_dir, "../../../backend"))

# 添加到 sys.path
for path in [docker_backend_path, local_backend_path]:
    if os.path.exists(path) and path not in sys.path:
        sys.path.insert(0, path)

# 尝试引用 app
try:
    from app.database import AsyncSessionLocal as async_session_maker
    from app.utils.logger import get_logger
except ImportError as e:
    print(f"Failed to import app. sys.path: {sys.path}")
    print(f"Docker backend exists: {os.path.exists(docker_backend_path)}")
    print(f"Local backend exists: {os.path.exists(local_backend_path)}")
    raise

logger = get_logger(__name__)

async def get_db_session():
    """获取数据库会话"""
    async with async_session_maker() as session:
        yield session

from contextlib import asynccontextmanager

@asynccontextmanager
async def get_session():
    async with async_session_maker() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            raise
        finally:
            await session.close()


from typing import Any, Optional, Tuple

from sqlalchemy import select


async def get_valid_customer_binding_and_account(
    db: Any, tg_id: int
) -> Tuple[Optional[Any], Optional[Any]]:
    """
    解析 TG 用户可用的短信客户账户：须未删除且非 closed。
    与 handlers/auth.py 中 /start 校验一致。
    """
    from app.modules.common.account import Account
    from app.modules.common.telegram_binding import TelegramBinding

    r = await db.execute(select(TelegramBinding).where(TelegramBinding.tg_id == tg_id))
    bindings = list(r.scalars().all())
    for b in bindings:
        acc_r = await db.execute(
            select(Account).where(
                Account.id == b.account_id,
                Account.status != "closed",
                Account.is_deleted == False,  # noqa: E712
            )
        )
        acc = acc_r.scalar_one_or_none()
        if acc:
            return b, acc

    return None, None
