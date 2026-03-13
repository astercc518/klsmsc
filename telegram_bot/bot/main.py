"""
Telegram Bot 主程序
"""
import sys
import os

# Ensure backend is in path - Docker环境下backend挂载在 /backend
docker_backend_path = "/backend"
current_dir = os.path.dirname(os.path.abspath(__file__))
local_backend_path = os.path.abspath(os.path.join(current_dir, "../../backend"))

for path in [docker_backend_path, local_backend_path]:
    if os.path.exists(path) and path not in sys.path:
        sys.path.insert(0, path)

# Try direct import
try:
    from bot.config import settings
except ImportError:
    # Fallback for when running as script inside the package
    from config import settings

import asyncio
import aiomysql
from telegram.ext import ApplicationBuilder, PicklePersistence, CommandHandler
from bot.utils import logger
from bot.handlers.auth import auth_handlers
from bot.handlers.sales import sales_handlers
from bot.handlers.bulk import bulk_handler
from bot.handlers.recharge import recharge_handler
from bot.handlers.balance import balance_command
from bot.handlers.help import help_command, sales_help, tech_help
from bot.handlers.menu import menu_handlers
# 注册处理器
from bot.handlers.register import register_conversation
# 发送短信处理器
from bot.handlers.send import send_conversation
# 新增处理器
from bot.handlers.ticket import get_handlers as get_ticket_handlers
# 审核处理器
from bot.handlers.review import review_handlers
# 群发任务处理器
from bot.handlers.mass_send import get_mass_handlers
# 数据操作处理器
from bot.handlers.data_ops import data_handlers

async def get_bot_token_from_db() -> str:
    """从数据库 system_config 读取 Bot Token"""
    try:
        conn = await aiomysql.connect(
            host=os.environ.get("DATABASE_HOST", "mysql"),
            port=int(os.environ.get("DATABASE_PORT", 3306)),
            user=os.environ.get("DATABASE_USER", "smsuser"),
            password=os.environ.get("DATABASE_PASSWORD", "smspass123"),
            db=os.environ.get("DATABASE_NAME", "sms_system"),
        )
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT config_value FROM system_config WHERE config_key = 'telegram_bot_token'"
            )
            row = await cur.fetchone()
        conn.close()
        if row and row[0]:
            logger.info("从数据库读取到 Bot Token")
            return row[0]
    except Exception as e:
        logger.warning(f"从数据库读取 Bot Token 失败: {e}")
    return ""


def resolve_bot_token() -> str:
    """优先数据库 → 回退环境变量"""
    db_token = asyncio.get_event_loop().run_until_complete(get_bot_token_from_db())
    if db_token:
        return db_token
    logger.info("使用环境变量中的 Bot Token")
    return settings.TELEGRAM_BOT_TOKEN


def main():
    """启动Bot"""
    logger.info("Starting Telegram Bot...")
    
    bot_token = resolve_bot_token()
    if not bot_token:
        logger.error("未找到有效的 Bot Token，退出")
        sys.exit(1)

    persistence = PicklePersistence(filepath="bot_data.pickle")
    
    app = ApplicationBuilder().token(bot_token).persistence(persistence).build()
    
    # 注册 Handlers
    for handler in auth_handlers:
        app.add_handler(handler)
        
    for handler in sales_handlers:
        app.add_handler(handler)
        
    app.add_handler(bulk_handler)
    app.add_handler(recharge_handler)
    app.add_handler(CommandHandler('balance', balance_command))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('sales_help', sales_help))
    app.add_handler(CommandHandler('tech_help', tech_help))
    app.add_handler(register_conversation())
    # 菜单处理器需在 send_conversation 之前，确保「短信审核」等菜单流程的文本输入优先处理
    for handler in menu_handlers:
        app.add_handler(handler)
    
    app.add_handler(send_conversation())
    
    # 注册工单和便捷发送处理器
    for handler in get_ticket_handlers():
        app.add_handler(handler)
    
    # 注册审核处理器 (供应商群用)
    for handler in review_handlers:
        app.add_handler(handler)
    
    # 注册群发任务处理器
    for handler in get_mass_handlers():
        app.add_handler(handler)
    
    # 注册数据操作处理器
    for handler in data_handlers:
        app.add_handler(handler)
    
    logger.info("Bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()
