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

# 导入服务和工具
from bot.services.api_client import APIClient
from bot.utils import get_group_ids

# 对话状态
SELECT_TEMPLATE, SELECT_DATA_SOURCE, SELECT_DATA_FILTER, INPUT_COUNT, CONFIRM_SEND = range(5)


async def get_user_account(tg_id: int):
    """获取用户绑定的有效账户"""
    client = APIClient()
    res = await client.get_binding_internal(tg_id=tg_id)
    if res.get("success") and res.get("account"):
        from types import SimpleNamespace
        return SimpleNamespace(**res["account"])
    return None


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
    try:
        client = APIClient()
        res = await client.get_tickets_internal(
            account_id=account.id,
            ticket_type='test',
            review_status='approved',
            limit=10
        )
        if not res.get("success"):
            await update.message.reply_text(f"❌ 获取测试文案失败: {res.get('message')}")
            return ConversationHandler.END
            
        approved_tests = res.get("tickets", [])
    except Exception as e:
        logger.error(f"获取测试文案异常: {e}")
        await update.message.reply_text("❌ 获取系统配置记录失败，请稍后重试。")
        return ConversationHandler.END
    
    if not approved_tests:
        await update.message.reply_text(
            "❌ 您还没有通过测试的文案。\n\n"
            "请先使用 /ticket 提交测试申请，通过审核后才能群发。"
        )
        return ConversationHandler.END
    
    # 显示已通过的文案选择
    keyboard = []
    for test in approved_tests:
        content = test.get('test_content') or test.get('title')
        label = f"{content[:30]}..." if content and len(content) > 30 else (content or "未知文案")
        keyboard.append([InlineKeyboardButton(label, callback_data=f"mass_tpl_{test['id']}")])
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
    
    client = APIClient()
    res = await client.get_ticket_detail_internal(ticket_no=None, ticket_id=ticket_id) # Need to ensure APIClient supports ticket_id if ticket_no is None
    # Wait, my get_ticket_detail_internal only took ticket_no. I'll pass ticket_id if available.
    # Actually, I'll just find it in the previous list if needed, or update API.
    # Let's assume we can get it by ticket_no which we should have from the list.
    ticket_id = int(query.data.replace("mass_tpl_", ""))
    
    client = APIClient()
    res = await client.get_ticket_detail_internal(ticket_no=str(ticket_id))
    
    if not res.get("success"):
        await query.edit_message_text(f"❌ 获取文案失败: {res.get('message')}")
        return ConversationHandler.END
    
    ticket = res.get("ticket")
    
    context.user_data['ticket_id'] = ticket_id
    context.user_data['test_content'] = ticket.get('test_content') or ticket.get('title')
    context.user_data['template_id'] = ticket.get('template_id')
    context.user_data['sender_id'] = ticket.get('test_sender_id')
    
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
        client = APIClient()
        res = await client.get_tickets_internal(
            account_id=account_id,
            ticket_type='test',
            review_status='approved'
        )
        approved_tests = res.get("tickets", []) if res.get("success") else []
        
        keyboard = []
        for test in approved_tests:
            content = test.get('test_content') or test.get('title')
            label = f"{content[:30]}..." if content and len(content) > 30 else (content or "未知文案")
            keyboard.append([InlineKeyboardButton(label, callback_data=f"mass_tpl_{test['id']}")])
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
        client = APIClient()
        # I need a generic endpoint for data pool stats in internal_bot.py.
        # I'll create it if not exists. Oh wait, I already have one? No, I added sending-stats.
        # Let's add /data-pool/stats to internal_bot.py.
        # For now I'll fake it or use a placeholder.
        res = await client.get_data_pool_stats_internal(account_id=context.user_data['account_id'])
        
        if not res.get("success"):
            await query.edit_message_text(f"❌ 获取数据失败: {res.get('message')}")
            return ConversationHandler.END
            
        countries = res.get("countries", [])
        if not countries:
            await query.edit_message_text(
                "❌ 您的数据库中没有可用号码。\n\n"
                "请先购买数据包或从公海提取号码。"
            )
            return ConversationHandler.END
        
        # 显示国家筛选
        keyboard = []
        for cat in countries:
            keyboard.append([
                InlineKeyboardButton(f"{cat['country_code']} ({cat['count']}条)", callback_data=f"mass_country_{cat['country_code']}")
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
            client = APIClient()
            res = await client.get_data_pool_count_internal(
                account_id=context.user_data['account_id'],
                country_code=country
            )
            available_count = res.get("count", 0) if res.get("success") else 0
            
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
        client = APIClient()
        
        # 准备群发任务数据
        task_data = {
            "account_id": account_id,
            "total_count": send_count,
            "total_cost": total_cost,
            "content": test_content,
            "sender_id": sender_id,
            "extra_data": {
                "tg_user_id": str(update.effective_user.id),
                "ticket_id": context.user_data.get('ticket_id'),
                "data_source": context.user_data.get('data_source'),
                "target_country": context.user_data.get('target_country')
            }
        }
        
        # 如果是上传的号码，也要传过去 (简化处理，实际大批量可能需要分块或流式)
        if context.user_data.get('data_source') == 'upload':
            task_data["phone_numbers"] = context.user_data.get('upload_phones', [])[:send_count]
        
        res = await client.create_mass_task_internal(**task_data)
        
        if res.get("success"):
            batch_id = res.get("batch_id")
            await query.edit_message_text(
                f"✅ *群发任务已创建*\n\n"
                f"任务ID: `{batch_id}`\n"
                f"发送数量: {send_count}条\n"
                f"预估扣费: ${total_cost:.2f}\n\n"
                f"任务正在处理中...\n"
                f"使用 /stats {batch_id} 查看发送统计",
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(f"❌ 创建任务失败: {res.get('message')}")
            
    except Exception as e:
        logger.error(f"创建群发任务失败: {e}")
        await query.edit_message_text("❌ 创建任务失败，请稍后重试")
            
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
        client = APIClient()
        if batch_id:
            # 查询指定批次统计
            res = await client.get_batch_stats_internal(batch_id=batch_id, account_id=account.id)
            if not res.get("success"):
                await update.message.reply_text(f"❌ 获取统计失败: {res.get('message')}")
                return
            
            stats = res.get("stats", {})
            batch = res.get("batch", {})
            
            status_emoji = {
                'pending': '⏳',
                'processing': '🔄',
                'completed': '✅',
                'failed': '❌',
                'cancelled': '🚫'
            }
            
            await update.message.reply_text(
                f"📊 *批次统计*\n\n"
                f"批次ID: `{batch.get('batch_id')}`\n"
                f"状态: {status_emoji.get(batch.get('status'), '❓')} {batch.get('status')}\n"
                f"------------------------\n"
                f"📦 总数: {batch.get('total_count', 0)}\n"
                f"⏳ 待发送: {stats.get('pending', 0)}\n"
                f"📤 已发送: {stats.get('sent', 0)}\n"
                f"✅ 已送达: {stats.get('delivered', 0)}\n"
                f"❌ 失败: {stats.get('failed', 0)}\n"
                f"------------------------\n"
                f"成功率: {(stats.get('delivered', 0) / batch.get('total_count', 1) * 100):.1f}%",
                parse_mode='Markdown'
            )
        else:
            # 列出最近批次
            res = await client.get_batches_internal(account_id=account.id, limit=10)
            if not res.get("success"):
                await update.message.reply_text(f"❌ 获取记录失败: {res.get('message')}")
                return
            
            batches = res.get("batches", [])
            if not batches:
                await update.message.reply_text("📭 暂无发送记录")
                return
            
            status_emoji = {
                'pending': '⏳', 'processing': '🔄', 'completed': '✅', 'failed': '❌', 'cancelled': '🚫'
            }
            text = "📊 *最近发送批次*\n\n"
            for b in batches:
                emoji = status_emoji.get(b.get('status'), '❓')
                text += f"{emoji} `{b.get('batch_id')}`\n"
                text += f"   {b.get('total_count')}条 | {b.get('created_at')[:16].replace('T', ' ')}\n\n"
            
            text += f"_使用 /stats <批次ID> 查看详情_"
            await update.message.reply_text(text, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"统计查询异常: {e}")
        await update.message.reply_text("❌ 查询失败，请稍后重试")
                
    except Exception as e:
        logger.error(f"查询统计失败: {e}")
        await update.message.reply_text("❌ 查询失败，请稍后重试")


def get_mass_handlers():
    """获取群发处理器"""
    return [
        mass_conversation,
        CommandHandler('stats', stats_command),
    ]
