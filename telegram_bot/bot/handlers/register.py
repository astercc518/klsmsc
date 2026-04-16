"""
TG Bot 注册账户处理器
支持 /register 命令和菜单按钮两种入口
注册后自动绑定 Telegram，直接进入客户菜单
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
import re

from bot.utils import logger
from bot.handlers.menu import get_main_menu_customer, get_back_menu
from bot.services.api_client import APIClient


# 会话状态
REG_NAME, REG_EMAIL, REG_PASSWORD, REG_CONFIRM = range(4)

_EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

_CANCEL_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("❌ 取消注册", callback_data="reg_cancel")]
])

api = APIClient()


async def _is_already_bound(tg_id: int) -> bool:
    """检查用户是否已有绑定账户"""
    user_info = await api.verify_user(tg_id)
    return user_info.get("valid", False)


async def register_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """注册入口 — 支持 /register 命令"""
    return await _start_register(update, context, is_callback=False)


async def register_entry_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """注册入口 — 支持菜单按钮回调"""
    query = update.callback_query
    await query.answer()
    return await _start_register(update, context, is_callback=True)


async def _start_register(update: Update, context: ContextTypes.DEFAULT_TYPE, is_callback: bool):
    """通用注册起始逻辑"""
    user = update.effective_user
    tg_id = user.id

    if await _is_already_bound(tg_id):
        msg = (
            "⚠️ 您已绑定了账户，无需重复注册。\n\n"
            "发送 /start 返回主菜单。"
        )
        if is_callback:
            await update.callback_query.edit_message_text(msg, reply_markup=get_back_menu())
        else:
            await update.message.reply_text(msg)
        return ConversationHandler.END

    logger.info(f"用户 {user.username}({tg_id}) 开始注册")

    welcome = (
        "📝 **注册新账户**\n\n"
        "请按步骤填写信息（可随时点击取消）\n\n"
        "**第 1/3 步** — 请输入账户名称：\n"
        "_(公司名或您的称呼，2-50字符)_"
    )
    if is_callback:
        await update.callback_query.edit_message_text(
            welcome, parse_mode="Markdown", reply_markup=_CANCEL_KB
        )
    else:
        await update.message.reply_text(
            welcome, parse_mode="Markdown", reply_markup=_CANCEL_KB
        )
    return REG_NAME


async def recv_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """接收账户名称"""
    name = update.message.text.strip()
    if len(name) < 2 or len(name) > 50:
        await update.message.reply_text(
            "❌ 名称长度需在 2-50 字符之间，请重新输入：",
            reply_markup=_CANCEL_KB,
        )
        return REG_NAME

    context.user_data["reg_name"] = name

    await update.message.reply_text(
        f"✅ 账户名称: {name}\n\n"
        "**第 2/3 步** — 请输入邮箱地址：",
        parse_mode="Markdown",
        reply_markup=_CANCEL_KB,
    )
    return REG_EMAIL


async def recv_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """接收邮箱"""
    email = update.message.text.strip().lower()

    if not _EMAIL_RE.match(email):
        await update.message.reply_text(
            "❌ 邮箱格式不正确，请重新输入：",
            reply_markup=_CANCEL_KB,
        )
        return REG_EMAIL

    context.user_data["reg_email"] = email

    await update.message.reply_text(
        f"✅ 邮箱: {email}\n\n"
        "**第 3/3 步** — 请设置登录密码：\n"
        "_(至少 8 个字符，建议包含数字和字母)_",
        parse_mode="Markdown",
        reply_markup=_CANCEL_KB,
    )
    return REG_PASSWORD


async def recv_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """接收密码"""
    password = update.message.text.strip()

    # 立即删除包含密码的消息
    try:
        await update.message.delete()
    except Exception:
        pass

    if len(password) < 8:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ 密码至少需要 8 个字符，请重新输入：",
            reply_markup=_CANCEL_KB,
        )
        return REG_PASSWORD

    context.user_data["reg_password"] = password

    name = context.user_data["reg_name"]
    email = context.user_data["reg_email"]

    confirm_kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ 确认注册", callback_data="reg_confirm"),
            InlineKeyboardButton("❌ 取消", callback_data="reg_cancel"),
        ]
    ])

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            "📋 **请确认注册信息**\n\n"
            f"👤 账户名称: {name}\n"
            f"📧 邮箱: {email}\n"
            f"🔑 密码: {'*' * len(password)}\n\n"
            "确认无误后点击「确认注册」"
        ),
        parse_mode="Markdown",
        reply_markup=confirm_kb,
    )
    return REG_CONFIRM


async def confirm_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """确认并执行注册"""
    query = update.callback_query
    await query.answer()

    name = context.user_data.get("reg_name", "")
    email = context.user_data.get("reg_email", "")
    password = context.user_data.get("reg_password", "")
    user = update.effective_user
    tg_id = user.id
    tg_username = user.username or user.first_name or str(tg_id)

    await query.edit_message_text("⏳ 正在创建账户...")

    try:
        result = await api.register_internal(
            name=name,
            email=email,
            password=password,
            tg_id=tg_id,
            tg_username=tg_username
        )
        
        if not result.get("success"):
            await query.edit_message_text(
                f"❌ 注册失败: {result.get('message', '未知错误')}\n\n请稍后使用 /register 重试。",
                reply_markup=get_back_menu(),
            )
            _clear_reg_data(context)
            return ConversationHandler.END

        account_id = result.get("account_id")
        api_key = result.get("api_key")
        
        # 设置用户会话
        context.user_data["account_id"] = account_id
        context.user_data["user_type"] = "customer"

        await query.edit_message_text(
            f"🎉 **注册成功！**\n\n"
            f"👤 账户名称: {name}\n"
            f"📧 邮箱: {email}\n"
            f"🆔 账户ID: `{account_id}`\n"
            f"🔑 API Key: `{api_key}`\n\n"
            f"⚠️ 请妥善保存 API Key，丢失后需重新生成。\n\n"
            f"账户已自动绑定您的 Telegram，下面开始使用吧 👇",
            parse_mode="Markdown",
            reply_markup=get_main_menu_customer(),
        )

    except Exception as e:
        logger.error(f"TG注册失败: {e}", exc_info=True)
        await query.edit_message_text(
            f"❌ 注册异常: {str(e)}\n\n请稍后使用 /register 重试。",
            reply_markup=get_back_menu(),
        )

    _clear_reg_data(context)
    return ConversationHandler.END


async def cancel_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """取消注册 — 命令方式"""
    _clear_reg_data(context)
    await update.message.reply_text(
        "❌ 已取消注册\n\n发送 /start 返回主菜单。",
    )
    return ConversationHandler.END


async def cancel_register_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """取消注册 — 按钮回调"""
    query = update.callback_query
    await query.answer()
    _clear_reg_data(context)
    await query.edit_message_text(
        "❌ 已取消注册\n\n发送 /start 返回主菜单。",
        reply_markup=get_back_menu(),
    )
    return ConversationHandler.END


def _clear_reg_data(context: ContextTypes.DEFAULT_TYPE):
    """清理注册临时数据"""
    for key in ("reg_name", "reg_email", "reg_password"):
        context.user_data.pop(key, None)


def register_conversation():
    """创建注册会话处理器"""
    return ConversationHandler(
        entry_points=[
            CommandHandler("register", register_entry),
            CallbackQueryHandler(register_entry_callback, pattern=r"^menu_register$"),
        ],
        states={
            REG_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, recv_name),
                CallbackQueryHandler(cancel_register_callback, pattern=r"^reg_cancel$"),
            ],
            REG_EMAIL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, recv_email),
                CallbackQueryHandler(cancel_register_callback, pattern=r"^reg_cancel$"),
            ],
            REG_PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, recv_password),
                CallbackQueryHandler(cancel_register_callback, pattern=r"^reg_cancel$"),
            ],
            REG_CONFIRM: [
                CallbackQueryHandler(confirm_register, pattern=r"^reg_confirm$"),
                CallbackQueryHandler(cancel_register_callback, pattern=r"^reg_cancel$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_register),
            CallbackQueryHandler(cancel_register_callback, pattern=r"^reg_cancel$"),
        ],
    )
