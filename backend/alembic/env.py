"""
Alembic 迁移环境配置

支持同步和异步两种模式：
  - alembic upgrade head          （同步，使用 PyMySQL）
  - alembic -x async=true upgrade head （异步）
"""
import asyncio
import os
from pathlib import Path
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import pool, engine_from_config, create_engine
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

# 在 backend/ 下执行 alembic 时 cwd 可能没有 .env，从仓库根目录加载
_repo_root = Path(__file__).resolve().parents[2]
load_dotenv(_repo_root / ".env", override=False)

# 根目录 .env 常用 MYSQL_*，与 Settings 的 DATABASE_* 对齐
if not (os.getenv("DATABASE_URL") or "").strip():
    if os.getenv("MYSQL_USER"):
        os.environ.setdefault("DATABASE_USER", os.environ["MYSQL_USER"])
    if os.getenv("MYSQL_PASSWORD"):
        os.environ.setdefault("DATABASE_PASSWORD", os.environ["MYSQL_PASSWORD"])
    if os.getenv("MYSQL_DATABASE"):
        os.environ.setdefault("DATABASE_NAME", os.environ["MYSQL_DATABASE"])

from app.config import settings
from app.database import Base

# 导入所有模型，确保 Base.metadata 中包含全部表定义
from app.modules.common.account import Account, AccountChannel  # noqa: F401
from app.modules.common.admin_user import AdminUser  # noqa: F401
from app.modules.common.api_key import *  # noqa: F401,F403
from app.modules.common.notification import *  # noqa: F401,F403
from app.modules.common.security_log import *  # noqa: F401,F403
from app.modules.common.system_config import *  # noqa: F401,F403
from app.modules.common.ticket import *  # noqa: F401,F403
from app.modules.common.package import *  # noqa: F401,F403
from app.modules.common.balance_log import *  # noqa: F401,F403
from app.modules.common.recharge_order import *  # noqa: F401,F403
from app.modules.common.invitation_code import *  # noqa: F401,F403
from app.modules.common.telegram_binding import *  # noqa: F401,F403
from app.modules.common.telegram_message import *  # noqa: F401,F403
from app.modules.common.telegram_user import *  # noqa: F401,F403
from app.modules.common.account_template import *  # noqa: F401,F403
from app.modules.common.account_pricing import *  # noqa: F401,F403
from app.modules.sms.channel import Channel  # noqa: F401
from app.modules.sms.sms_log import SMSLog  # noqa: F401
from app.modules.sms.sms_batch import *  # noqa: F401,F403
from app.modules.sms.sms_template import *  # noqa: F401,F403
from app.modules.sms.routing_rule import RoutingRule  # noqa: F401
from app.modules.sms.sender_id import *  # noqa: F401,F403
from app.modules.sms.supplier import *  # noqa: F401,F403
from app.modules.sms.country_pricing import *  # noqa: F401,F403
from app.modules.sms.channel_relations import *  # noqa: F401,F403
from app.modules.data.models import *  # noqa: F401,F403
from app.models.settlement import *  # noqa: F401,F403
from app.models.scheduled_task import *  # noqa: F401,F403
from app.models.sub_account import *  # noqa: F401,F403
from app.modules.common.knowledge import *  # noqa: F401,F403

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# 同步 URL（将 asyncmy 驱动替换为 pymysql）；未显式设置 DATABASE_URL 时用应用拼接串
_db_url = (settings.DATABASE_URL or "").strip()
if not _db_url:
    _db_url = settings.SQLALCHEMY_DATABASE_URL or ""
SYNC_DB_URL = _db_url.replace("+asyncmy", "+pymysql")


def run_migrations_offline() -> None:
    """离线模式：生成 SQL 脚本而不连接数据库"""
    context.configure(
        url=SYNC_DB_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：连接数据库执行迁移"""
    connectable = create_engine(SYNC_DB_URL, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
