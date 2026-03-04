"""
群发处理 Handler
"""
import os
import aiofiles
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters, ConversationHandler
from bot.utils import get_session, logger
from app.core.pricing import PricingEngine
from app.core.audit import AuditService
from app.utils.validator import Validator
from app.modules.common.account import Account
from sqlalchemy import select

# States
FILE_UPLOADED = 1
CONTENT_RECEIVED = 2

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """取消操作"""
    await update.message.reply_text("❌ 操作已取消")
    return ConversationHandler.END

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理文件上传"""
    user = update.effective_user
    doc = update.message.document
    
    # 检查是否绑定账户
    account_id = context.user_data.get('account_id')
    if not account_id:
        await update.message.reply_text("请先使用 /start 绑定或激活账户。")
        return ConversationHandler.END
        
    if not doc.file_name.endswith('.txt'):
        await update.message.reply_text("❌ 仅支持 .txt 格式文件 (一行一个号码)")
        return ConversationHandler.END
        
    file = await doc.get_file()
    
    # 保存文件
    # 路径: /tmp/smsc_batches/{account_id}_{ts}.txt
    os.makedirs("/tmp/smsc_batches", exist_ok=True)
    file_path = f"/tmp/smsc_batches/{account_id}_{doc.file_unique_id}.txt"
    await file.download_to_drive(file_path)
    
    # 简单解析统计 (这里应该异步处理，避免阻塞)
    # 为了演示直接处理
    valid_count = 0
    total_count = 0
    
    async with aiofiles.open(file_path, mode='r') as f:
        async for line in f:
            line = line.strip()
            if line:
                total_count += 1
                # 简单验证
                if line.isdigit() or line.startswith('+'):
                    valid_count += 1
    
    context.user_data['bulk_file'] = file_path
    context.user_data['bulk_valid_count'] = valid_count
    
    await update.message.reply_text(
        f"📄 **文件接收成功**\n"
        f"总行数: {total_count}\n"
        f"有效号码: **{valid_count}**\n\n"
        f"请直接发送 **短信内容**:",
        parse_mode='Markdown'
    )
    
    return FILE_UPLOADED

async def handle_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理文案输入"""
    content = update.message.text
    account_id = context.user_data.get('account_id')
    valid_count = context.user_data.get('bulk_valid_count')
    file_path = context.user_data.get('bulk_file')
    
    if not content:
        await update.message.reply_text("内容不能为空")
        return FILE_UPLOADED
        
    # 验证内容
    is_valid, err, info = Validator.validate_content(content)
    if not is_valid:
        await update.message.reply_text(f"❌ 文案违规: {err}")
        return FILE_UPLOADED
        
    parts = info['parts']
    encoding = info['encoding']
    
    # 估算费用
    # 取一个参考单价 (例如取该账户 CN 价格，或默认)
    # 实际应该遍历文件里所有号码算，太慢。
    # 简化：取该账户的默认 AccountPricing (如果有)，否则取 global default
    
    estimated_price = 0.05 # Fallback
    currency = "USD"
    
    async with get_session() as db:
        # 获取账户默认配置 (假设大部分发CN)
        # 这里为了演示，先取一个固定值或查 AccountPricing
        pricing_engine = PricingEngine(db)
        # 模拟查询
        price_info = await pricing_engine.get_price(1, 'CN', account_id=account_id)
        if price_info:
            estimated_price = price_info['price']
            
    total_cost = valid_count * parts * estimated_price
    
    context.user_data['bulk_content'] = content
    context.user_data['bulk_cost'] = total_cost
    context.user_data['bulk_parts'] = parts
    
    await update.message.reply_text(
        f"💰 **订单确认**\n\n"
        f"👥 号码数: {valid_count}\n"
        f"📝 内容: {content[:20]}... ({info['length']}字, {encoding})\n"
        f"🧩 条数: {parts} 条/人\n"
        f"💵 预估总价: **${total_cost:.2f}**\n\n"
        f"发送 /confirm 确认提交，或 /cancel 取消。",
        parse_mode='Markdown'
    )
    
    return CONTENT_RECEIVED

async def confirm_batch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """确认提交"""
    account_id = context.user_data.get('account_id')
    file_path = context.user_data.get('bulk_file')
    content = context.user_data.get('bulk_content')
    total_cost = context.user_data.get('bulk_cost')
    valid_count = context.user_data.get('bulk_valid_count')
    
    import uuid
    batch_id = f"BATCH_{uuid.uuid4().hex[:8].upper()}"
    
    async with get_session() as db:
        audit_service = AuditService(db)
        batch = await audit_service.submit_batch(
            account_id=account_id,
            file_path=file_path,
            content=content,
            total_count=valid_count,
            total_cost=total_cost,
            batch_id=batch_id
        )
        
        status_msg = "✅ **已通过自动审核，正在发送**" if batch.status == 'sending' else "⏳ **已提交人工审核**"
        
        await update.message.reply_text(
            f"🚀 **提交成功**\n"
            f"批次号: `{batch_id}`\n"
            f"{status_msg}",
            parse_mode='Markdown'
        )
        
        # TODO: 如果 pending_audit，通知销售
        
    return ConversationHandler.END

bulk_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Document.MimeType("text/plain"), handle_document)],
    states={
        FILE_UPLOADED: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_content)],
        CONTENT_RECEIVED: [CommandHandler("confirm", confirm_batch)]
    },
    fallbacks=[CommandHandler("cancel", cancel)]
)
