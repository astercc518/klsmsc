"""
查询余额处理器
"""
from telegram import Update
from telegram.ext import ContextTypes
from bot.utils import get_session, get_valid_customer_binding_and_account, logger
from app.modules.common.account import Account
from sqlalchemy import select


async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理/balance命令"""
    user = update.effective_user
    tg_id = user.id
    
    logger.info(f"用户 {tg_id} 查询余额")
    
    account_id = context.user_data.get("account_id")

    async with get_session() as db:
        _, acc_valid = await get_valid_customer_binding_and_account(db, tg_id)
        if acc_valid:
            account_id = acc_valid.id
            context.user_data["account_id"] = account_id
        else:
            context.user_data.pop("account_id", None)
            await update.message.reply_text(
                "❌ 未绑定有效账户或该账户已停用/删除。\n\n"
                "请使用邀请链接激活账户，或发送 /start 查看状态"
            )
            return

    await update.message.reply_text("⏳ 查询中...")

    try:
        async with get_session() as db:
            result = await db.execute(select(Account).where(Account.id == account_id))
            account = result.scalar_one_or_none()

            if not account or account.is_deleted or account.status == "closed":
                await update.message.reply_text(
                    "❌ 账户不存在\n\n"
                    "请联系客服处理"
                )
                return
            
            balance = float(account.balance) if account.balance else 0.0
            currency = account.currency or 'USD'
            threshold = float(account.low_balance_threshold) if account.low_balance_threshold else 100.0
            
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
                f"📊 账户ID: {account.id}\n"
                f"👤 账户名: {account.account_name}\n\n"
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
