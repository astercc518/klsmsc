"""
充值申请处理器
"""
import uuid
from datetime import datetime
from telegram import Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters
)
from bot.utils import get_session, logger
from app.modules.common.recharge_order import RechargeOrder
from app.modules.common.account import Account
from app.modules.common.telegram_binding import TelegramBinding
from sqlalchemy import select

# 会话状态
AMOUNT, PROOF = range(2)


async def recharge_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """开始充值申请 /recharge"""
    user = update.effective_user
    tg_id = user.id
    
    # 检查是否绑定账户
    account_id = context.user_data.get('account_id')
    if not account_id:
        await update.message.reply_text(
            "❌ 您尚未绑定账户\n\n"
            "请先使用邀请链接激活账户，或发送 /start 查看状态"
        )
        return ConversationHandler.END
    
    logger.info(f"用户 {tg_id} 开始充值申请，账户: {account_id}")
    
    await update.message.reply_text(
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
        await update.message.reply_text(
            f"❌ 金额格式错误: {e}\n\n"
            "请输入正确的金额（如：100 或 50.5）："
        )
        return AMOUNT
    
    context.user_data['recharge_amount'] = amount
    logger.info(f"用户 {update.effective_user.id} 输入充值金额: ${amount}")
    
    await update.message.reply_text(
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
    
    # 生成订单号
    order_no = f"RCH_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6].upper()}"
    
    async with get_session() as db:
        # 获取账户信息
        acc_result = await db.execute(
            select(Account).where(Account.id == account_id)
        )
        account = acc_result.scalar_one_or_none()
        
        if not account:
            await update.message.reply_text("❌ 账户不存在，请联系客服")
            return ConversationHandler.END
        
        # 创建充值工单
        order = RechargeOrder(
            order_no=order_no,
            account_id=account_id,
            amount=amount,
            currency="USD",
            payment_proof=proof,
            status="pending"
        )
        db.add(order)
        await db.commit()
        
        logger.info(f"充值工单已创建: {order_no}, 账户: {account_id}, 金额: ${amount}")
    
    await update.message.reply_text(
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
