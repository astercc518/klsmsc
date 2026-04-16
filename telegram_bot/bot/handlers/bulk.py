"""
群发处理 Handler
"""
import os
import aiofiles
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters, ConversationHandler
from bot.utils import logger, send_and_log
from bot.services.api_client import APIClient

# States
FILE_UPLOADED = 1
CONTENT_RECEIVED = 2

api = APIClient()

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
    os.makedirs("/tmp/smsc_batches", exist_ok=True)
    file_path = f"/tmp/smsc_batches/{account_id}_{doc.file_unique_id}.txt"
    await file.download_to_drive(file_path)
    
    # 解析号码
    phones = []
    async with aiofiles.open(file_path, mode='r') as f:
        async for line in f:
            line = line.strip()
            if line:
                # 简单验证
                if line.isdigit() or line.startswith('+'):
                    phones.append(line)
    
    if not phones:
        await update.message.reply_text("❌ 文件中未找到有效号码。")
        return ConversationHandler.END

    context.user_data['bulk_file'] = file_path
    context.user_data['bulk_phones'] = phones
    context.user_data['bulk_valid_count'] = len(phones)
    
    await update.message.reply_text(
        f"📄 **文件接收成功**\n"
        f"有效号码: **{len(phones)}**\n\n"
        f"请直接发送 **短信内容**:",
        parse_mode='Markdown'
    )
    
    return FILE_UPLOADED

async def handle_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理文案输入"""
    content = update.message.text.strip()
    account_id = context.user_data.get('account_id')
    phones = context.user_data.get('bulk_phones')
    
    if not content:
        await update.message.reply_text("内容不能为空")
        return FILE_UPLOADED
        
    # 调用后端进行验证与估价
    res = await api.bulk_validate(account_id, content, phones)
    if not res.get("success"):
        await update.message.reply_text(f"❌ 验证失败: {res.get('msg', '未知错误')}")
        return FILE_UPLOADED
    
    data = res
    total_cost = data.get('total_cost')
    parts = data.get('parts')
    
    context.user_data['bulk_content'] = content
    context.user_data['bulk_cost'] = total_cost
    context.user_data['bulk_parts'] = parts
    
    await update.message.reply_text(
        f"💰 **订单确认**\n\n"
        f"👥 号码数: {data.get('valid_count')}\n"
        f"📝 内容: {content[:20]}... ({data.get('length')}字, {data.get('encoding')})\n"
        f"🧩 条数: {parts} 条/人\n"
        f"💵 预估总价: **${total_cost:.2f}**\n\n"
        f"发送 /confirm 确认提交，或 /cancel 取消。",
        parse_mode='Markdown'
    )
    
    return CONTENT_RECEIVED

async def confirm_batch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """确认提交"""
    account_id = context.user_data.get('account_id')
    phones = context.user_data.get('bulk_phones')
    content = context.user_data.get('bulk_content')
    total_cost = context.user_data.get('bulk_cost')
    
    res = await api.create_mass_task(
        account_id=account_id,
        content=content,
        phone_numbers=phones,
        total_cost=total_cost
    )
    
    if res.get("success"):
        await update.message.reply_text(
            f"🚀 **提交成功**\n"
            f"批次号: `{res.get('batch_id')}`\n"
            f"⏳ **已入库待处理**",
            parse_mode='Markdown'
        )
        
    return ConversationHandler.END

bulk_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Document.MimeType("text/plain"), handle_document)],
    states={
        FILE_UPLOADED: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_content)],
        CONTENT_RECEIVED: [CommandHandler("confirm", confirm_batch)]
    },
    fallbacks=[CommandHandler("cancel", cancel)]
)
