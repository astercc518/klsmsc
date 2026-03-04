"""
注册账户处理器
"""
from telegram import Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters
)
from loguru import logger
from bot.services.api_client import APIClient

# 会话状态
EMAIL, PASSWORD, ACCOUNT_NAME = range(3)


async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """开始注册"""
    user = update.effective_user
    logger.info(f"用户 {user.id} 开始注册")
    
    await update.message.reply_text(
        "📝 开始注册新账户\n\n"
        "请输入你的邮箱地址："
    )
    
    return EMAIL


async def register_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """接收邮箱"""
    email = update.message.text.strip()
    
    # 简单验证邮箱格式
    if '@' not in email or '.' not in email:
        await update.message.reply_text(
            "❌ 邮箱格式不正确，请重新输入："
        )
        return EMAIL
    
    # 保存到context
    context.user_data['email'] = email
    logger.info(f"用户 {update.effective_user.id} 输入邮箱: {email}")
    
    await update.message.reply_text(
        "✅ 邮箱已保存\n\n"
        "请设置密码（至少8个字符）："
    )
    
    return PASSWORD


async def register_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """接收密码"""
    password = update.message.text.strip()
    
    # 验证密码长度
    if len(password) < 8:
        await update.message.reply_text(
            "❌ 密码至少需要8个字符，请重新输入："
        )
        return PASSWORD
    
    # 保存到context
    context.user_data['password'] = password
    logger.info(f"用户 {update.effective_user.id} 设置了密码")
    
    # 删除包含密码的消息
    try:
        await update.message.delete()
    except:
        pass
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="✅ 密码已保存\n\n请输入账户名称（公司名或个人名）："
    )
    
    return ACCOUNT_NAME


async def register_complete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """完成注册"""
    account_name = update.message.text.strip()
    
    if len(account_name) < 2:
        await update.message.reply_text(
            "❌ 账户名称至少需要2个字符，请重新输入："
        )
        return ACCOUNT_NAME
    
    context.user_data['account_name'] = account_name
    
    # 调用API注册
    await update.message.reply_text("⏳ 正在创建账户...")
    
    try:
        api_client = APIClient()
        result = await api_client.register_account(
            email=context.user_data['email'],
            password=context.user_data['password'],
            account_name=account_name
        )
        
        if result['success']:
            # 保存API Key到用户数据
            api_key = result['api_key']
            context.user_data['api_key'] = api_key
            context.user_data['account_id'] = result['account_id']
            
            logger.info(f"用户 {update.effective_user.id} 注册成功，账户ID: {result['account_id']}")
            
            await update.message.reply_text(
                f"✅ 注册成功！\n\n"
                f"📧 邮箱: {context.user_data['email']}\n"
                f"👤 账户名: {account_name}\n"
                f"🆔 账户ID: {result['account_id']}\n\n"
                f"🔑 你的API Key:\n`{api_key}`\n\n"
                f"⚠️ 请妥善保管API Key，它将用于API调用。\n\n"
                f"现在你可以使用 /send 发送短信了！",
                parse_mode='Markdown'
            )
        else:
            error_msg = result.get('error', {}).get('message', '未知错误')
            await update.message.reply_text(
                f"❌ 注册失败: {error_msg}\n\n"
                f"请使用 /register 重试"
            )
            
    except Exception as e:
        logger.error(f"注册失败: {str(e)}", exc_info=e)
        await update.message.reply_text(
            f"❌ 注册失败: {str(e)}\n\n"
            f"请稍后重试或联系管理员"
        )
    
    # 清理敏感数据
    context.user_data.pop('password', None)
    
    return ConversationHandler.END


async def register_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """取消注册"""
    logger.info(f"用户 {update.effective_user.id} 取消注册")
    
    # 清理数据
    context.user_data.clear()
    
    await update.message.reply_text(
        "❌ 已取消注册\n\n"
        "使用 /register 可以重新开始注册"
    )
    
    return ConversationHandler.END


def register_conversation():
    """创建注册会话处理器"""
    return ConversationHandler(
        entry_points=[CommandHandler('register', register_start)],
        states={
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_email)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_password)],
            ACCOUNT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_complete)],
        },
        fallbacks=[CommandHandler('cancel', register_cancel)],
    )

