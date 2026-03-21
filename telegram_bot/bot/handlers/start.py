"""
/start命令处理器
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from loguru import logger


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理/start命令"""
    user = update.effective_user
    logger.info(f"用户 {user.id} ({user.username}) 启动Bot")
    
    # 创建欢迎消息
    welcome_message = f"""
👋 欢迎使用国际短信网关Bot！

你好 {user.first_name}！

🌟 我可以帮你：
• 📱 发送国际短信
• 💰 查询账户余额
• 📊 查看发送记录
• 💳 管理账户

🔧 使用以下命令开始：
/register - 注册新账户
/send - 发送短信
/balance - 查询余额
/help - 查看帮助

---
需要注册才能使用服务，使用 /register 开始注册。
"""
    
    # 创建按钮
    keyboard = [
        [InlineKeyboardButton("📝 注册账户", callback_data="register")],
        [InlineKeyboardButton("📱 发送短信", callback_data="send")],
        [InlineKeyboardButton("💰 查询余额", callback_data="balance")],
        [InlineKeyboardButton("❓ 帮助", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_message,
        reply_markup=reply_markup
    )

