import sys
import os
from typing import Any, Optional, Tuple

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

async def log_outgoing_message(user_id: int, content: str, chat_id: Optional[int] = None):
    """记录发出消息异步助手"""
    from bot.services.message_service import MessageService
    await MessageService.log_outgoing(user_id, content, chat_id)

async def send_and_log(context: Any, chat_id: int, text: str, **kwargs):
    """发送并记录消息"""
    message = await context.bot.send_message(chat_id=chat_id, text=text, **kwargs)
    # 异步记录，不阻塞发送
    import asyncio
    asyncio.create_task(log_outgoing_message(chat_id, text, chat_id))
    return message

async def edit_and_log(query: Any, text: str, **kwargs):
    """编辑并记录消息"""
    message = await query.edit_message_text(text=text, **kwargs)
    # 异步记录
    import asyncio
    chat_id = query.message.chat_id if query.message else None
    user_id = query.from_user.id
    asyncio.create_task(log_outgoing_message(user_id, text, chat_id))
    return message

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



from sqlalchemy import select


async def get_group_ids() -> dict:
    """
    从 system_config 读取各 TG 群组 ID（优先数据库，回退环境变量）
    返回 {'tech_group_id': '...', 'billing_group_id': '...', 'admin_group_id': '...'}
    """
    from app.modules.common.system_config import SystemConfig
    ids = {
        'admin_group_id': os.getenv('TELEGRAM_ADMIN_GROUP_ID', ''),
        'tech_group_id': os.getenv('STAFF_GROUP_ID', ''),
        'billing_group_id': '',
    }
    try:
        async with async_session_maker() as session:
            result = await session.execute(
                select(SystemConfig.config_key, SystemConfig.config_value).where(
                    SystemConfig.config_key.in_([
                        'telegram_admin_group_id',
                        'telegram_tech_group_id',
                        'telegram_billing_group_id',
                    ])
                )
            )
            for k, v in result.fetchall():
                if v and v.strip():
                    if k == 'telegram_admin_group_id':
                        ids['admin_group_id'] = v.strip()
                    elif k == 'telegram_tech_group_id':
                        ids['tech_group_id'] = v.strip()
                    elif k == 'telegram_billing_group_id':
                        ids['billing_group_id'] = v.strip()
    except Exception as e:
        logger.warning(f"读取群组ID配置失败，使用环境变量: {e}")
    return ids


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
