"""
群发任务流程 Handler - 通过TG Bot创建群发任务
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters
)
from loguru import logger
from datetime import datetime
from decimal import Decimal
import uuid

from app.database import AsyncSessionLocal
from app.modules.common.account import Account
from bot.utils import get_session, get_valid_customer_binding_and_account
from app.modules.common.ticket import Ticket
from app.modules.sms.sms_batch import SmsBatch
from app.modules.sms.sms_template import SmsTemplate
from app.modules.data.models import DataNumber
from sqlalchemy import select, func

# 对话状态
SELECT_TEMPLATE, SELECT_DATA_SOURCE, SELECT_DATA_FILTER, INPUT_COUNT, CONFIRM_SEND = range(5)


async def get_user_account(tg_id: int):
    """获取用户绑定的有效账户（未删除且非 closed）"""
    async with get_session() as db:
        _, account = await get_valid_customer_binding_and_account(db, tg_id)
        return account


async def mass_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /mass - 开始创建群发任务
    """
    user_id = update.effective_user.id
    
    # 验证用户
    account = await get_user_account(user_id)
    if not account:
        await update.message.reply_text(
            "❌ 您还未绑定账户，请先使用 /start <邀请码> 注册。"
        )
        return ConversationHandler.END
    
    context.user_data['account_id'] = account.id
    context.user_data['account_name'] = account.account_name
    context.user_data['balance'] = float(account.balance) if account.balance else 0
    
    # 获取已通过测试的文案（从工单中提取）
    async with AsyncSessionLocal() as session:
        # 查找已通过的测试工单
        result = await session.execute(
            select(Ticket).where(
                Ticket.account_id == account.id,
                Ticket.ticket_type == 'test',
                Ticket.review_status == 'approved',
                Ticket.status.in_(['resolved', 'in_progress'])
            ).order_by(Ticket.created_at.desc()).limit(10)
        )
        approved_tests = result.scalars().all()
    
    if not approved_tests:
        await update.message.reply_text(
            "❌ 您还没有通过测试的文案。\n\n"
            "请先使用 /ticket 提交测试申请，通过审核后才能群发。"
        )
        return ConversationHandler.END
    
    # 显示已通过的文案选择
    keyboard = []
    for test in approved_tests:
        label = f"{test.test_content[:30]}..." if test.test_content and len(test.test_content) > 30 else (test.test_content or "未知文案")
        keyboard.append([InlineKeyboardButton(label, callback_data=f"mass_tpl_{test.id}")])
    keyboard.append([InlineKeyboardButton("❌ 取消", callback_data="mass_cancel")])
    
    await update.message.reply_text(
        f"📤 *创建群发任务*\n\n"
        f"账户: {account.account_name}\n"
        f"余额: ${context.user_data['balance']:.2f}\n\n"
        f"请选择已通过测试的文案：",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return SELECT_TEMPLATE


async def select_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """选择文案模板"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "mass_cancel":
        await query.edit_message_text("❌ 已取消群发任务")
        return ConversationHandler.END
    
    ticket_id = int(query.data.replace("mass_tpl_", ""))
    
    async with AsyncSessionLocal() as session:
        ticket = await session.get(Ticket, ticket_id)
        if not ticket:
            await query.edit_message_text("❌ 文案不存在")
            return ConversationHandler.END
    
    context.user_data['ticket_id'] = ticket_id
    context.user_data['test_content'] = ticket.test_content
    context.user_data['template_id'] = ticket.template_id
    context.user_data['sender_id'] = ticket.test_sender_id
    
    # 选择数据来源
    keyboard = [
        [InlineKeyboardButton("📦 从数据包提取", callback_data="data_pool")],
        [InlineKeyboardButton("📁 上传号码文件", callback_data="data_upload")],
        [InlineKeyboardButton("⬅️ 返回", callback_data="mass_back_template")],
    ]
    
    await query.edit_message_text(
        f"📤 *群发任务*\n\n"
        f"文案: {ticket.test_content[:100]}...\n\n"
        f"请选择号码数据来源：",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return SELECT_DATA_SOURCE


async def select_data_source(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """选择数据来源"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "mass_back_template":
        # 返回文案选择
        account_id = context.user_data['account_id']
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Ticket).where(
                    Ticket.account_id == account_id,
                    Ticket.ticket_type == 'test',
                    Ticket.review_status == 'approved',
                    Ticket.status.in_(['resolved', 'in_progress'])
                ).order_by(Ticket.created_at.desc()).limit(10)
            )
            approved_tests = result.scalars().all()
        
        keyboard = []
        for test in approved_tests:
            label = f"{test.test_content[:30]}..." if test.test_content and len(test.test_content) > 30 else (test.test_content or "未知文案")
            keyboard.append([InlineKeyboardButton(label, callback_data=f"mass_tpl_{test.id}")])
        keyboard.append([InlineKeyboardButton("❌ 取消", callback_data="mass_cancel")])
        
        await query.edit_message_text(
            f"📤 *创建群发任务*\n\n"
            f"请选择已通过测试的文案：",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return SELECT_TEMPLATE
    
    if data == "data_pool":
        context.user_data['data_source'] = 'pool'
        # 获取可用的数据筛选条件
        async with AsyncSessionLocal() as session:
            # 获取账户拥有的数据国家
            result = await session.execute(
                select(DataNumber.country_code, func.count(DataNumber.id).label('count'))
                .where(
                    DataNumber.owner_account_id == context.user_data['account_id'],
                    DataNumber.status == 'available'
                )
                .group_by(DataNumber.country_code)
            )
            countries = result.all()
        
        if not countries:
            await query.edit_message_text(
                "❌ 您的数据库中没有可用号码。\n\n"
                "请先购买数据包或从公海提取号码。"
            )
            return ConversationHandler.END
        
        # 显示国家筛选
        keyboard = []
        for country, count in countries:
            keyboard.append([
                InlineKeyboardButton(f"{country} ({count}条)", callback_data=f"mass_country_{country}")
            ])
        keyboard.append([InlineKeyboardButton("⬅️ 返回", callback_data="mass_back_source")])
        
        await query.edit_message_text(
            f"📤 *群发任务 - 选择数据*\n\n"
            f"请选择发送的目标国家：",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return SELECT_DATA_FILTER
    
    if data == "data_upload":
        context.user_data['data_source'] = 'upload'
        await query.edit_message_text(
            f"📤 *群发任务 - 上传号码*\n\n"
            f"请发送包含号码的文件（TXT或CSV），每行一个号码。\n\n"
            f"格式示例:\n"
            f"`+8613800138000`\n"
            f"`+8613900139000`\n\n"
            f"发送 /cancel 取消",
            parse_mode='Markdown'
        )
        return SELECT_DATA_FILTER


async def select_data_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """选择数据筛选/处理上传"""
    query = update.callback_query
    
    if query:
        await query.answer()
        data = query.data
        
        if data == "mass_back_source":
            keyboard = [
                [InlineKeyboardButton("📦 从数据包提取", callback_data="data_pool")],
                [InlineKeyboardButton("📁 上传号码文件", callback_data="data_upload")],
                [InlineKeyboardButton("⬅️ 返回", callback_data="mass_back_template")],
            ]
            await query.edit_message_text(
                f"📤 *群发任务*\n\n"
                f"文案: {context.user_data['test_content'][:100]}...\n\n"
                f"请选择号码数据来源：",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return SELECT_DATA_SOURCE
        
        if data.startswith("mass_country_"):
            country = data.replace("mass_country_", "")
            context.user_data['target_country'] = country
            
            # 获取该国家可用号码数量
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(func.count(DataNumber.id)).where(
                        DataNumber.owner_account_id == context.user_data['account_id'],
                        DataNumber.country_code == country,
                        DataNumber.status == 'available'
                    )
                )
                available_count = result.scalar() or 0
            
            context.user_data['available_count'] = available_count
            
            await query.edit_message_text(
                f"📤 *群发任务 - 设置数量*\n\n"
                f"目标国家: {country}\n"
                f"可用号码: {available_count}条\n\n"
                f"请输入要发送的数量（最大{available_count}）：",
                parse_mode='Markdown'
            )
            return INPUT_COUNT
    
    return SELECT_DATA_FILTER


async def handle_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理号码文件上传"""
    if context.user_data.get('data_source') != 'upload':
        return SELECT_DATA_FILTER
    
    document = update.message.document
    if not document:
        await update.message.reply_text("❌ 请发送文件（TXT或CSV格式）")
        return SELECT_DATA_FILTER
    
    # 下载文件
    try:
        file = await document.get_file()
        file_content = await file.download_as_bytearray()
        content = file_content.decode('utf-8')
        
        # 解析号码
        lines = content.strip().split('\n')
        phones = []
        for line in lines:
            phone = line.strip().replace('"', '').replace(',', '')
            if phone and (phone.startswith('+') or phone.isdigit()):
                if not phone.startswith('+'):
                    phone = '+' + phone
                phones.append(phone)
        
        if not phones:
            await update.message.reply_text("❌ 未能从文件中解析出有效号码，请检查格式。")
            return SELECT_DATA_FILTER
        
        context.user_data['upload_phones'] = phones
        context.user_data['available_count'] = len(phones)
        
        await update.message.reply_text(
            f"✅ 已解析 {len(phones)} 个号码\n\n"
            f"请输入要发送的数量（最大{len(phones)}）：",
            parse_mode='Markdown'
        )
        return INPUT_COUNT
        
    except Exception as e:
        logger.error(f"解析号码文件失败: {e}")
        await update.message.reply_text("❌ 文件解析失败，请检查文件格式。")
        return SELECT_DATA_FILTER


async def input_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """输入发送数量"""
    text = update.message.text.strip()
    
    try:
        count = int(text)
    except ValueError:
        await update.message.reply_text("❌ 请输入有效的数字：")
        return INPUT_COUNT
    
    available = context.user_data.get('available_count', 0)
    if count <= 0:
        await update.message.reply_text("❌ 数量必须大于0：")
        return INPUT_COUNT
    
    if count > available:
        await update.message.reply_text(f"❌ 数量超过可用号码数（{available}），请重新输入：")
        return INPUT_COUNT
    
    context.user_data['send_count'] = count
    
    # 计算费用（假设从模板获取单价）
    # 这里简化处理，实际应该从通道配置获取
    unit_price = 0.05  # 默认单价
    total_cost = count * unit_price
    balance = context.user_data.get('balance', 0)
    
    context.user_data['unit_price'] = unit_price
    context.user_data['total_cost'] = total_cost
    
    if total_cost > balance:
        await update.message.reply_text(
            f"❌ *余额不足*\n\n"
            f"发送{count}条需要: ${total_cost:.2f}\n"
            f"当前余额: ${balance:.2f}\n\n"
            f"请先充值或减少发送数量。",
            parse_mode='Markdown'
        )
        return INPUT_COUNT
    
    # 显示确认信息
    keyboard = [
        [InlineKeyboardButton("✅ 确认发送", callback_data="mass_confirm")],
        [InlineKeyboardButton("❌ 取消", callback_data="mass_cancel")]
    ]
    
    await update.message.reply_text(
        f"📤 *确认群发任务*\n\n"
        f"文案: {context.user_data['test_content'][:80]}...\n"
        f"发送数量: {count}条\n"
        f"单价: ${unit_price:.4f}\n"
        f"总费用: ${total_cost:.2f}\n"
        f"余额: ${balance:.2f} → ${balance - total_cost:.2f}\n\n"
        f"确认提交群发任务？",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return CONFIRM_SEND


async def confirm_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """确认并创建群发任务"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "mass_cancel":
        await query.edit_message_text("❌ 已取消群发任务")
        return ConversationHandler.END
    
    if query.data != "mass_confirm":
        return CONFIRM_SEND
    
    # 创建群发任务
    account_id = context.user_data['account_id']
    send_count = context.user_data['send_count']
    total_cost = context.user_data['total_cost']
    test_content = context.user_data['test_content']
    sender_id = context.user_data.get('sender_id')
    
    try:
        async with AsyncSessionLocal() as session:
            # 检查余额
            account = await session.get(Account, account_id)
            if float(account.balance) < total_cost:
                await query.edit_message_text("❌ 余额不足，任务取消")
                return ConversationHandler.END
            
            # 获取号码列表
            phones = []
            data_source = context.user_data.get('data_source')
            
            if data_source == 'upload':
                phones = context.user_data.get('upload_phones', [])[:send_count]
            else:
                # 从数据池提取
                country = context.user_data.get('target_country')
                result = await session.execute(
                    select(DataNumber).where(
                        DataNumber.owner_account_id == account_id,
                        DataNumber.country_code == country,
                        DataNumber.status == 'available'
                    ).limit(send_count)
                )
                data_numbers = result.scalars().all()
                phones = [dn.phone_number for dn in data_numbers]
                
                # 标记号码为已使用
                for dn in data_numbers:
                    dn.status = 'used'
            
            # 创建批次
            batch_id = f"MASS{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:6].upper()}"
            
            batch = SmsBatch(
                batch_id=batch_id,
                account_id=account_id,
                message=test_content,
                sender_id=sender_id,
                total_count=len(phones),
                phone_numbers=phones,
                status='pending',
                source='telegram',
                extra_data={
                    'tg_user_id': str(update.effective_user.id),
                    'ticket_id': context.user_data.get('ticket_id'),
                    'data_source': data_source
                }
            )
            session.add(batch)
            
            # 扣除费用
            account.balance = Decimal(str(float(account.balance) - total_cost))
            
            await session.commit()
            
            await query.edit_message_text(
                f"✅ *群发任务已创建*\n\n"
                f"任务ID: `{batch_id}`\n"
                f"发送数量: {len(phones)}条\n"
                f"扣费: ${total_cost:.2f}\n\n"
                f"任务正在处理中...\n"
                f"使用 /stats {batch_id} 查看发送统计",
                parse_mode='Markdown'
            )
            
    except Exception as e:
        logger.error(f"创建群发任务失败: {e}")
        await query.edit_message_text("❌ 创建任务失败，请稍后重试")
    
    context.user_data.clear()
    return ConversationHandler.END


async def cancel_mass(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """取消群发"""
    context.user_data.clear()
    await update.message.reply_text("❌ 已取消群发任务")
    return ConversationHandler.END


# 创建群发对话处理器
mass_conversation = ConversationHandler(
    entry_points=[CommandHandler('mass', mass_start)],
    states={
        SELECT_TEMPLATE: [CallbackQueryHandler(select_template, pattern=r'^mass_')],
        SELECT_DATA_SOURCE: [CallbackQueryHandler(select_data_source)],
        SELECT_DATA_FILTER: [
            CallbackQueryHandler(select_data_filter),
            MessageHandler(filters.Document.ALL, handle_file_upload),
        ],
        INPUT_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_count)],
        CONFIRM_SEND: [CallbackQueryHandler(confirm_send, pattern=r'^mass_')],
    },
    fallbacks=[CommandHandler('cancel', cancel_mass)],
    per_user=True,
    per_chat=True
)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /stats [batch_id] - 查询发送统计
    """
    user_id = update.effective_user.id
    
    # 验证用户
    account = await get_user_account(user_id)
    if not account:
        await update.message.reply_text("❌ 您还未绑定账户")
        return
    
    batch_id = context.args[0] if context.args else None
    
    try:
        async with AsyncSessionLocal() as session:
            if batch_id:
                # 查询指定批次
                result = await session.execute(
                    select(SmsBatch).where(
                        SmsBatch.batch_id == batch_id,
                        SmsBatch.account_id == account.id
                    )
                )
                batch = result.scalar_one_or_none()
                
                if not batch:
                    await update.message.reply_text(f"❌ 批次 {batch_id} 不存在或无权查看")
                    return
                
                # 获取详细统计
                from app.modules.sms.sms_log import SMSLog
                
                # 统计各状态数量
                stats_result = await session.execute(
                    select(SMSLog.status, func.count(SMSLog.id))
                    .where(SMSLog.batch_id == batch.id)
                    .group_by(SMSLog.status)
                )
                stats = dict(stats_result.all())
                
                pending = stats.get('pending', 0)
                sent = stats.get('sent', 0)
                delivered = stats.get('delivered', 0)
                failed = stats.get('failed', 0)
                
                status_emoji = {
                    'pending': '⏳',
                    'processing': '🔄',
                    'completed': '✅',
                    'failed': '❌',
                    'cancelled': '🚫'
                }
                
                await update.message.reply_text(
                    f"📊 *批次统计*\n\n"
                    f"批次ID: `{batch.batch_id}`\n"
                    f"状态: {status_emoji.get(batch.status, '❓')} {batch.status}\n"
                    f"创建时间: {batch.created_at.strftime('%Y-%m-%d %H:%M') if batch.created_at else '-'}\n"
                    f"------------------------\n"
                    f"📦 总数: {batch.total_count}\n"
                    f"⏳ 待发送: {pending}\n"
                    f"📤 已发送: {sent}\n"
                    f"✅ 已送达: {delivered}\n"
                    f"❌ 失败: {failed}\n"
                    f"------------------------\n"
                    f"成功率: {(delivered / batch.total_count * 100):.1f}%" if batch.total_count > 0 else "成功率: -",
                    parse_mode='Markdown'
                )
            else:
                # 列出最近的批次
                result = await session.execute(
                    select(SmsBatch).where(
                        SmsBatch.account_id == account.id
                    ).order_by(SmsBatch.created_at.desc()).limit(10)
                )
                batches = result.scalars().all()
                
                if not batches:
                    await update.message.reply_text("📭 暂无发送记录")
                    return
                
                status_emoji = {
                    'pending': '⏳',
                    'processing': '🔄',
                    'completed': '✅',
                    'failed': '❌',
                    'cancelled': '🚫'
                }
                
                text = "📊 *最近发送批次*\n\n"
                for batch in batches:
                    emoji = status_emoji.get(batch.status, '❓')
                    time_str = batch.created_at.strftime('%m/%d %H:%M') if batch.created_at else '-'
                    text += f"{emoji} `{batch.batch_id}`\n"
                    text += f"   {batch.total_count}条 | {time_str}\n\n"
                
                text += f"_使用 /stats <批次ID> 查看详情_"
                
                await update.message.reply_text(text, parse_mode='Markdown')
                
    except Exception as e:
        logger.error(f"查询统计失败: {e}")
        await update.message.reply_text("❌ 查询失败，请稍后重试")


def get_mass_handlers():
    """获取群发处理器"""
    return [
        mass_conversation,
        CommandHandler('stats', stats_command),
    ]
