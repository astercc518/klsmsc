import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters
)
from bot.utils import logger, send_and_log, is_internal_staff_from_verify
from bot.services.api_client import APIClient

# 会话状态
AMOUNT, PROOF = range(2)


async def recharge_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """开始充值申请 /recharge"""
    user = update.effective_user
    tg_id = user.id
    
    api = APIClient()
    user_info = await api.verify_user(tg_id, include_monthly_performance=False)

    if is_internal_staff_from_verify(user_info):
        bot_user = (os.environ.get("TELEGRAM_BOT_USERNAME") or "").strip().lstrip("@")
        text = (
            "ℹ️ <b>您是内部员工</b>\n\n"
            "<code>/recharge</code> 用于<b>客户本人</b>在已绑定账户的前提下提交充值申请；"
            "员工无法代替客户走此流程（便于审计与归属）。\n\n"
            "<b>您可以：</b>\n"
            "• 发送 /start → 主菜单「待审核充值」审核客户工单（财务/管理员）。\n"
            "• 引导客户在已绑定的 Telegram 中向本机器人发送 /recharge 自助申请。\n\n"
            "客户未绑定时请先完成开户绑定。"
        )
        kb = None
        if bot_user:
            kb = InlineKeyboardMarkup(
                [[InlineKeyboardButton("打开主菜单（机器人）", url=f"https://t.me/{bot_user}")]]
            )
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)
        return ConversationHandler.END

    if not user_info or user_info.get("role") != "customer":
        await send_and_log(
            context,
            tg_id,
            "❌ 未绑定有效账户或该账户已停用/删除。\n\n"
            "请先使用邀请链接激活账户，或发送 /start 查看状态"
        )
        return ConversationHandler.END
    
    account_id = user_info.get("account_id")
    context.user_data["account_id"] = account_id

    logger.info(f"用户 {tg_id} 开始充值申请，账户: {account_id}")
    
    await send_and_log(
        context,
        tg_id,
        "💰 **充值申请**\n\n"
        "请输入充值金额（USD）：\n"
        "例如：100 或 50.5\n\n"
        "发送 /cancel 取消操作",
        parse_mode='Markdown'
    )
    
    return AMOUNT


async def recharge_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """接收充值金额"""
    text = update.message.text.strip()
    
    try:
        amount = float(text)
        if amount <= 0:
            raise ValueError("金额必须大于0")
        if amount > 100000:
            raise ValueError("单次充值不能超过 $100,000")
    except ValueError as e:
        await send_and_log(
            context,
            update.effective_user.id,
            f"❌ 金额格式错误: {e}\n\n"
            "请输入正确的金额（如：100 或 50.5）："
        )
        return AMOUNT
    
    context.user_data['recharge_amount'] = amount
    logger.info(f"用户 {update.effective_user.id} 输入充值金额: ${amount}")
    
    await send_and_log(
        context,
        update.effective_user.id,
        f"✅ 充值金额: **${amount:.2f} USD**\n\n"
        "请上传付款凭证（截图/照片）\n"
        "或发送 /skip 跳过（稍后补充）",
        parse_mode='Markdown'
    )
    
    return PROOF


async def recharge_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """接收付款凭证（图片）"""
    photo = update.message.photo
    document = update.message.document
    
    proof_url = None
    
    if photo:
        # 获取最大尺寸的图片
        file = await photo[-1].get_file()
        proof_url = file.file_path
        logger.info(f"用户上传图片凭证: {proof_url}")
    elif document:
        file = await document.get_file()
        proof_url = file.file_path
        logger.info(f"用户上传文件凭证: {proof_url}")
    
    context.user_data['recharge_proof'] = proof_url
    
    # 提交充值申请
    return await submit_recharge(update, context)


async def recharge_skip_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """跳过上传凭证"""
    context.user_data['recharge_proof'] = None
    return await submit_recharge(update, context)


async def submit_recharge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """提交充值申请"""
    account_id = context.user_data.get('account_id')
    amount = context.user_data.get('recharge_amount')
    proof = context.user_data.get('recharge_proof')
    
    try:
        api = APIClient()
        res = await api.create_recharge_order(
            account_id=account_id,
            amount=amount,
            payment_proof=proof
        )
        
        if not res.get("success"):
            await update.message.reply_text(f"❌ 提交审核失败: {res.get('msg', '未知错误')}")
            return ConversationHandler.END

        order_no = res.get("order_no")
        logger.info(f"充值工单已创建: {order_no}, 账户: {account_id}, 金额: ${amount}")
    
        await send_and_log(
            context,
            update.effective_user.id,
            f"✅ **充值申请已提交！**\n\n"
            f"📋 工单号: `{order_no}`\n"
            f"💰 金额: ${amount:.2f} USD\n"
            f"📎 凭证: {'已上传' if proof else '未上传'}\n"
            f"📊 状态: 待审核\n\n"
            f"财务审核通过后，余额将自动到账。\n"
            f"您会收到通知消息。\n\n"
            f"发送 /balance 查询当前余额",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"提交充值申请失败: {e}")
        await update.message.reply_text("❌ 提交充值申请失败，请稍后重试")
    
    # 清理数据
    context.user_data.pop('recharge_amount', None)
    context.user_data.pop('recharge_proof', None)
    
    return ConversationHandler.END


async def recharge_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """取消充值"""
    logger.info(f"用户 {update.effective_user.id} 取消充值")
    
    context.user_data.pop('recharge_amount', None)
    context.user_data.pop('recharge_proof', None)
    
    await update.message.reply_text(
        "❌ 已取消充值申请\n\n"
        "发送 /recharge 重新申请"
    )
    
    return ConversationHandler.END


# 创建充值会话处理器
recharge_handler = ConversationHandler(
    entry_points=[CommandHandler('recharge', recharge_start)],
    states={
        AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, recharge_amount)],
        PROOF: [
            MessageHandler(filters.PHOTO | filters.Document.ALL, recharge_proof),
            CommandHandler('skip', recharge_skip_proof)
        ],
    },
    fallbacks=[CommandHandler('cancel', recharge_cancel)],
)
