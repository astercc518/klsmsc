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

from telegram.ext import ApplicationBuilder, PicklePersistence, CommandHandler
from bot.utils import logger
from bot.handlers.auth import auth_handlers
from bot.handlers.sales import sales_handlers
from bot.handlers.bulk import bulk_handler
from bot.handlers.recharge import recharge_handler
from bot.handlers.balance import balance_command
from bot.handlers.help import help_command, sales_help, tech_help
from bot.handlers.menu import menu_handlers
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

def main():
    """启动Bot"""
    logger.info("Starting Telegram Bot...")
    
    # 持久化存储用户状态 (Conversations)
    persistence = PicklePersistence(filepath="bot_data.pickle")
    
    app = ApplicationBuilder().token(settings.TELEGRAM_BOT_TOKEN).persistence(persistence).build()
    
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
    
    # 注册菜单处理器
    for handler in menu_handlers:
        app.add_handler(handler)
    
    logger.info("Bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()
