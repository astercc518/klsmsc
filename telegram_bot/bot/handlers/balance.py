"""
查询余额处理器
"""
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.utils import logger, is_internal_staff_from_verify
from bot.services.api_client import APIClient

api = APIClient()

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理/balance命令"""
    user = update.effective_user
    tg_id = user.id

    logger.info(f"用户 {tg_id} 查询余额")

    try:
        # 先鉴权：员工无需「查询中」占位，也勿用客户侧「未绑定」提示误导
        user_info = await api.verify_user(tg_id, include_monthly_performance=False)

        if is_internal_staff_from_verify(user_info):
            bot_user = (os.environ.get("TELEGRAM_BOT_USERNAME") or "").strip().lstrip("@")
            text = (
                "ℹ️ <b>您是内部员工</b>\n\n"
                "<code>/balance</code> 只查询已绑定本机器人的<b>客户账户</b>余额，"
                "不会显示员工本人或未绑定会话的账户。\n\n"
                "<b>查看客户余额建议：</b>\n"
                "• 发送 /start → 主菜单「我的客户」（列表中含余额；需具备销售等权限）。\n"
                "• 或请已绑定的客户在其会话中发送 /balance。\n\n"
                "未绑定本 Bot 的客户请在官网或管理后台查询。"
            )
            kb = None
            if bot_user:
                kb = InlineKeyboardMarkup(
                    [[InlineKeyboardButton("打开主菜单（机器人）", url=f"https://t.me/{bot_user}")]]
                )
            await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)
            return

        await update.message.reply_text("⏳ 查询中...")

        if not user_info.get("account"):
            context.user_data.pop("account_id", None)
            await update.message.reply_text(
                "❌ 未绑定有效账户或该账户已停用/删除。\n\n"
                "请使用邀请链接激活账户，或发送 /start 查看状态"
            )
            return

        account = user_info["account"]
        account_id = account["id"]
        context.user_data["account_id"] = account_id
        
        balance = float(account.get("balance") or 0.0)
        currency = account.get("currency") or 'USD'
        threshold = float(account.get("low_balance_threshold") or 100.0)
        
        # 判断余额状态
        if balance < threshold:
            status_emoji = "⚠️"
            status_text = "余额不足，请充值"
        elif balance < 10:
            status_emoji = "🔴"
            status_text = "余额较低"
        else:
            status_emoji = "✅"
            status_text = "余额充足"
        
        await update.message.reply_text(
            f"💰 **账户余额**\n\n"
            f"{status_emoji} 状态: {status_text}\n"
            f"💵 余额: **${balance:.2f}** {currency}\n"
            f"📊 账户ID: {account_id}\n"
            f"👤 账户名: {account.get('account_name')}\n\n"
            f"发送 /recharge 申请充值\n"
            f"发送 /send 发送短信",
            parse_mode='Markdown'
        )
            
    except Exception as e:
        logger.error(f"查询余额失败: {str(e)}", exc_info=True)
        await update.message.reply_text(
            f"❌ 查询失败: {str(e)}\n\n"
            f"请稍后重试"
        )
