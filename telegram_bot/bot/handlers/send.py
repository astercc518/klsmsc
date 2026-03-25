"""
发送短信处理器
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
from bot.utils import get_session, get_valid_customer_binding_and_account

# 会话状态
PHONE, MESSAGE = range(2)


async def send_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """开始发送短信"""
    user = update.effective_user

    # 检查是否已绑定账户
    account = await get_user_account(user.id)
    if not account or not account.api_key:
        await update.message.reply_text(
            "❌ 您还未绑定账户或账户未激活\n\n"
            "请联系销售获取邀请码并使用 /start 绑定账户"
        )
        return ConversationHandler.END

    context.user_data['account_id'] = account.id
    context.user_data['account_api_key'] = account.api_key
    
    logger.info(f"用户 {user.id} 开始发送短信")
    
    await update.message.reply_text(
        "📱 发送短信\n\n"
        "请输入目标电话号码（E.164格式，如 +8613800138000）："
    )
    
    return PHONE


async def send_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """接收电话号码"""
    phone = update.message.text.strip()
    
    # 验证号码格式
    if not phone.startswith('+'):
        await update.message.reply_text(
            "❌ 号码必须以+开头（E.164格式）\n\n"
            "例如: +8613800138000\n\n"
            "请重新输入："
        )
        return PHONE
    
    if len(phone) < 8 or len(phone) > 20:
        await update.message.reply_text(
            "❌ 号码长度不正确\n\n"
            "请重新输入："
        )
        return PHONE
    
    # 保存号码
    context.user_data['phone'] = phone
    logger.info(f"用户 {update.effective_user.id} 输入号码: {phone}")
    
    await update.message.reply_text(
        f"✅ 号码已保存: {phone}\n\n"
        f"请输入短信内容："
    )
    
    return MESSAGE


async def send_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """接收短信内容并发送"""
    message = update.message.text.strip()
    
    if not message:
        await update.message.reply_text(
            "❌ 短信内容不能为空，请重新输入："
        )
        return MESSAGE
    
    if len(message) > 1000:
        await update.message.reply_text(
            "❌ 短信内容太长（最多1000字符），请重新输入："
        )
        return MESSAGE
    
    # 发送中
    await update.message.reply_text("⏳ 正在发送...")
    
    try:
        api_client = APIClient()
        api_key = context.user_data.get('account_api_key')
        result = await api_client.send_sms(
            api_key=api_key,
            phone_number=context.user_data['phone'],
            message=message
        )
        
        if result.get('success'):
            logger.info(f"用户 {update.effective_user.id} 发送成功: {result.get('message_id')}")
            
            await update.message.reply_text(
                f"✅ 发送成功！\n\n"
                f"📱 号码: {context.user_data['phone']}\n"
                f"📄 消息ID: {result.get('message_id')}\n"
                f"📊 状态: {result.get('status')}\n"
                f"💰 费用: {result.get('cost')} {result.get('currency')}\n"
                f"📝 条数: {result.get('message_count')}\n\n"
                f"使用 /send 继续发送"
            )
        else:
            error = result.get('error', {})
            await update.message.reply_text(
                f"❌ 发送失败\n\n"
                f"错误: {error.get('message', '未知错误')}\n\n"
                f"使用 /send 重试"
            )
            
    except Exception as e:
        logger.error(f"发送失败: {str(e)}", exc_info=e)
        await update.message.reply_text(
            f"❌ 发送失败: {str(e)}\n\n"
            f"请稍后重试"
        )
    
    # 清理数据
    context.user_data.pop('phone', None)
    context.user_data.pop('account_api_key', None)
    context.user_data.pop('account_id', None)
    
    return ConversationHandler.END


async def send_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """取消发送"""
    logger.info(f"用户 {update.effective_user.id} 取消发送")
    
    context.user_data.pop('phone', None)
    
    await update.message.reply_text(
        "❌ 已取消发送\n\n"
        "使用 /send 可以重新开始"
    )
    
    return ConversationHandler.END


def send_conversation():
    """创建发送短信会话处理器"""
    return ConversationHandler(
        entry_points=[CommandHandler('send', send_start)],
        states={
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_phone)],
            MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_message)],
        },
        fallbacks=[CommandHandler('cancel', send_cancel)],
    )


async def get_user_account(tg_id: int):
    """获取用户绑定的有效账户（未删除且非 closed）"""
    async with get_session() as db:
        _, account = await get_valid_customer_binding_and_account(db, tg_id)
        return account

