"""工单处理器 - 通过Telegram提交和查询工单（支持测试工单转发到供应商群）"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters
)
from loguru import logger
from datetime import datetime
import uuid
import os

# 导入服务相关
from bot.services.api_client import APIClient
from bot.utils import get_group_ids

# 对话状态
TICKET_TYPE, TICKET_TITLE, TICKET_DESC = range(3)
# 测试工单专用状态
TEST_SELECT_TEMPLATE, TEST_INPUT_PHONE, TEST_INPUT_CONTENT, TEST_INPUT_SENDER = range(3, 7)

# 工单类型
TICKET_TYPES = {
    'test': '测试申请',
    'registration': '开户申请',
    'recharge': '充值申请',
    'technical': '技术支持',
    'billing': '账务问题',
    'feedback': '意见反馈',
    'other': '其他'
}


def generate_ticket_no() -> str:
    """生成工单号"""
    now = datetime.now()
    return f"TK{now.strftime('%Y%m%d%H%M%S')}{str(uuid.uuid4().hex)[:6].upper()}"


async def get_user_account(tg_id: int):
    """获取用户绑定的有效账户"""
    client = APIClient()
    res = await client.get_binding_internal(tg_id=tg_id)
    if res.get("success") and res.get("account"):
        # 兼容旧代码，将字典转为简易对象或直接返回字典
        from types import SimpleNamespace
        return SimpleNamespace(**res["account"])
    return None


async def get_admin_user(tg_id: int):
    """获取绑定的管理员"""
    client = APIClient()
    res = await client.get_admin_internal(tg_id=tg_id)
    if res.get("success") and res.get("admin"):
        from types import SimpleNamespace
        return SimpleNamespace(**res["admin"])
    return None


async def ticket_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """开始创建工单"""
    user_id = update.effective_user.id
    
    # 检查用户类型
    account = await get_user_account(user_id)
    admin = await get_admin_user(user_id)
    
    if not account and not admin:
        await update.message.reply_text(
            "❌ 您还未绑定账户或不是管理员，请先注册或联系管理员。"
        )
        return ConversationHandler.END
    
    # 存储身份信息
    if admin:
        context.user_data['user_type'] = 'admin'
        context.user_data['user_id'] = admin.id
    else:
        context.user_data['user_type'] = 'account'
        context.user_data['user_id'] = account.id
        context.user_data['account_id'] = account.id
    
    # 显示工单类型选择
    keyboard = []
    for i, (type_key, type_name) in enumerate(TICKET_TYPES.items()):
        if i % 2 == 0:
            keyboard.append([])
        keyboard[-1].append(InlineKeyboardButton(type_name, callback_data=f"ticket_type_{type_key}"))
    
    keyboard.append([InlineKeyboardButton("❌ 取消", callback_data="ticket_cancel")])
    
    await update.message.reply_text(
        "📝 *创建工单*\n\n"
        "请选择工单类型：",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return TICKET_TYPE


async def ticket_type_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """选择工单类型后"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "ticket_cancel":
        await query.edit_message_text("已取消创建工单。")
        return ConversationHandler.END
    
    ticket_type = query.data.replace("ticket_type_", "")
    context.user_data['ticket_type'] = ticket_type
    
    await query.edit_message_text(
        f"📝 *创建工单*\n\n"
        f"工单类型: {TICKET_TYPES.get(ticket_type, '其他')}\n\n"
        f"请输入工单标题（简要描述您的问题）：",
        parse_mode='Markdown'
    )
    return TICKET_TITLE


async def ticket_title_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """输入工单标题"""
    title = update.message.text.strip()
    if len(title) < 5:
        await update.message.reply_text("标题太短，请输入至少5个字符的标题：")
        return TICKET_TITLE
    
    if len(title) > 200:
        await update.message.reply_text("标题太长，请控制在200个字符以内：")
        return TICKET_TITLE
    
    context.user_data['ticket_title'] = title
    
    await update.message.reply_text(
        f"📝 *创建工单*\n\n"
        f"工单类型: {TICKET_TYPES.get(context.user_data['ticket_type'], '其他')}\n"
        f"标题: {title}\n\n"
        f"请详细描述您的问题或需求（输入 /cancel 取消）：",
        parse_mode='Markdown'
    )
    return TICKET_DESC


async def ticket_desc_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """输入工单描述"""
    desc = update.message.text.strip()
    
    user_type = context.user_data.get('user_type')
    user_db_id = context.user_data.get('user_id')
    account_id = context.user_data.get('account_id') # 仅Account用户有此字段
    
    # 创建工单
    try:
        client = APIClient()
        res = await client.create_ticket_internal(
            ticket_no=generate_ticket_no(),
            account_id=account_id,
            tg_user_id=update.effective_user.id,
            ticket_type=context.user_data['ticket_type'],
            priority='normal',
            title=context.user_data['ticket_title'],
            description=desc,
            created_by_type=user_type,
            created_by_id=user_db_id
        )
        
        if not res.get("success"):
            await update.message.reply_text(f"❌ 创建工单失败: {res.get('message')}")
            return ConversationHandler.END

        t_no = res.get("ticket_no")
        await update.message.reply_text(
            f"✅ *工单创建成功*\n\n"
            f"工单号: `{t_no}`\n"
            f"类型: {TICKET_TYPES.get(context.user_data['ticket_type'], '其他')}\n"
            f"标题: {context.user_data['ticket_title']}\n\n"
            f"我们会尽快处理您的工单，您可以使用 /tickets 查看工单状态。",
            parse_mode='Markdown'
        )
        
        # 通知技术群
        gids = await get_group_ids()
        staff_gid = gids.get('tech_group_id') or gids.get('admin_group_id')
        if staff_gid:
            try:
                admin_text = (
                    f"🆕 *新工单通知*\n"
                    f"------------------\n"
                    f"工单号: `{t_no}`\n"
                    f"类型: {TICKET_TYPES.get(context.user_data['ticket_type'], '其他')}\n"
                    f"标题: {context.user_data['ticket_title']}\n"
                    f"用户: `{update.effective_user.id}`\n"
                    f"描述: {desc}\n"
                )
                keyboard = [[InlineKeyboardButton("🙋‍♂️ 接单", callback_data=f"take_ticket_{res.get('ticket_id')}")]]
                await context.bot.send_message(
                    chat_id=staff_gid,
                    text=admin_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"通知技术群失败: {e}")
            
    except Exception as e:
        logger.error(f"创建工单失败: {e}")
        await update.message.reply_text("❌ 创建工单失败，请稍后重试。")
    
    # 清理用户数据
    context.user_data.clear()
    return ConversationHandler.END


async def ticket_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """取消创建工单"""
    context.user_data.clear()
    await update.message.reply_text("已取消创建工单。")
    return ConversationHandler.END


async def list_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看我的工单列表"""
    user_id = update.effective_user.id
    account = await get_user_account(user_id)
    admin = await get_admin_user(user_id)
    
    if not account and not admin:
        await update.message.reply_text(
            "❌ 您还未绑定账户或不是管理员。"
        )
        return
    
    try:
        client = APIClient()
        res = await client.get_tickets_internal(
            account_id=account.id if account else None,
            admin_id=admin.id if admin else None
        )
        
        if not res.get("success"):
            await update.message.reply_text(f"❌ 获取工单列表失败: {res.get('message')}")
            return

        tickets = res.get("tickets", [])
        if not tickets:
            await update.message.reply_text(
                "📭 您还没有相关工单记录。\n\n"
                "使用 /ticket 创建新工单。"
            )
            return
        
        # 状态映射
        status_map = {
            'open': '⏳ 待处理',
            'assigned': '👤 已分配',
            'in_progress': '🔄 处理中',
            'pending_user': '💬 等待回复',
            'resolved': '✅ 已解决',
            'closed': '🔒 已关闭',
            'cancelled': '❌ 已取消'
        }
        
        title_prefix = "我的工单 (管理员)" if admin else "我的工单"
        text = f"📋 *{title_prefix}*\n\n"
        for t in tickets:
            status = status_map.get(t['status'], t['status'])
            created = t.get('created_at', '-')[:16].replace('T', ' ')
            text += f"• `{t['ticket_no']}`\n"
            text += f"  {t['title'][:30]}{'...' if len(t['title']) > 30 else ''}\n"
            text += f"  {status} | {created}\n\n"
        
        # 添加按钮
        keyboard = [
            [InlineKeyboardButton("➕ 创建新工单", callback_data="new_ticket")],
        ]
        
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"获取工单列表失败: {e}")
        await update.message.reply_text("❌ 获取工单列表失败，请稍后重试。")


async def view_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看工单详情 - /ticket_view <ticket_no>"""
    if not context.args:
        await update.message.reply_text("请提供工单号: /ticket_view <工单号>")
        return
    
    ticket_no = context.args[0]
    user_id = update.effective_user.id
    account = await get_user_account(user_id)
    admin = await get_admin_user(user_id)
    
    if not account and not admin:
        await update.message.reply_text("❌ 您还未绑定账户或不是管理员。")
        return
    
    try:
        client = APIClient()
        res = await client.get_ticket_detail_internal(
            ticket_no=ticket_no,
            account_id=account.id if account else None
        )
        
        if not res.get("success"):
            await update.message.reply_text(f"❌ 获取工单详情失败: {res.get('message')}")
            return

        ticket = res.get("ticket")
        replies = res.get("replies", [])
        
        status_map = {
            'open': '⏳ 待处理',
            'assigned': '👤 已分配',
            'in_progress': '🔄 处理中',
            'pending_user': '💬 等待回复',
            'resolved': '✅ 已解决',
            'closed': '🔒 已关闭'
        }
        
        text = f"📋 *工单详情*\n\n"
        text += f"工单号: `{ticket['ticket_no']}`\n"
        text += f"类型: {TICKET_TYPES.get(ticket['ticket_type'], '其他')}\n"
        text += f"状态: {status_map.get(ticket['status'], ticket['status'])}\n"
        text += f"标题: {ticket['title']}\n\n"
        text += f"*描述:*\n{ticket.get('description') or '无'}\n\n"
        
        if ticket.get("resolution"):
            text += f"*解决方案:*\n{ticket['resolution']}\n\n"
        
        if replies:
            text += f"*沟通记录 ({len(replies)}):*\n"
            for r in replies[-5:]:  # 只显示最近5条
                author = "客服" if r['reply_by_type'] == 'admin' else "我"
                time = r['created_at'][:16].replace('T', ' ') if r.get('created_at') else ''
                text += f"[{author}] {time}\n{r['content'][:100]}{'...' if len(r['content']) > 100 else ''}\n\n"
        
        # 如果工单未关闭，显示回复按钮
        keyboard = []
        if ticket['status'] not in ['closed', 'cancelled', 'resolved']:
            keyboard.append([
                InlineKeyboardButton("💬 回复工单", callback_data=f"reply_ticket_{ticket['id']}")
            ])
        
        # 管理员操作按钮
        if admin:
            admin_buttons = []
            if ticket['status'] == 'open':
                admin_buttons.append(
                    InlineKeyboardButton("🙋‍♂️ 接单", callback_data=f"take_ticket_{ticket['id']}")
                )
            
            if ticket['status'] in ['assigned', 'in_progress', 'pending_user'] and ticket.get('assigned_to') == admin.id:
                admin_buttons.append(
                    InlineKeyboardButton("✅ 解决", callback_data=f"resolve_ticket_{ticket['id']}")
                )
            
            if admin_buttons:
                keyboard.append(admin_buttons)
        
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"获取工单详情失败: {e}")
        await update.message.reply_text("❌ 获取工单详情失败，请稍后重试。")


async def ticket_action_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理工单动作 (接单/解决)"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = update.effective_user.id
    admin = await get_admin_user(user_id)
    
    if not admin:
        await context.bot.send_message(chat_id=user_id, text="❌ 您不是管理员，无法操作。")
        return

    try:
        action, ticket_id_str = data.split('_ticket_')
        ticket_id = int(ticket_id_str)
    except ValueError:
        return
    
    try:
        client = APIClient()
        res = await client.ticket_action_internal(
            ticket_id=ticket_id,
            action=action,
            admin_id=admin.id
        )
        
        if res.get("success"):
            label = "已接单" if action == 'take' else "已标记解决"
            await context.bot.send_message(chat_id=user_id, text=f"✅ 您{label} (工单号: {res.get('ticket_no')})")
        else:
            await context.bot.send_message(chat_id=user_id, text=f"❌ 操作失败: {res.get('message')}")
                
    except Exception as e:
        logger.error(f"工单操作失败: {e}")
        await context.bot.send_message(chat_id=user_id, text="❌ 操作失败，请稍后重试。")


async def quick_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """快速发送短信 - /quick <号码> <内容>"""
    if len(context.args) < 2:
        await update.message.reply_text(
            "📲 *快速发送短信*\n\n"
            "用法: `/quick <手机号> <短信内容>`\n\n"
            "示例: `/quick +8613800138000 您的验证码是123456`",
            parse_mode='Markdown'
        )
        return
    
    phone = context.args[0]
    content = ' '.join(context.args[1:])
    
    # 获取用户账户
    user_id = update.effective_user.id
    account = await get_user_account(user_id)
    admin = await get_admin_user(user_id)
    
    if not account:
        if admin:
             await update.message.reply_text("❌ 管理员请使用管理后台或绑定客户账户进行发送测试。")
        else:
             await update.message.reply_text("❌ 您还未绑定账户，请先注册或绑定。")
        return
    
    # 验证手机号格式
    if not phone.startswith('+'):
        phone = '+' + phone
    
    # 发送状态消息
    status_msg = await update.message.reply_text(
        f"📤 正在发送短信...\n\n"
        f"号码: `{phone}`\n"
        f"内容: {content[:50]}{'...' if len(content) > 50 else ''}",
        parse_mode='Markdown'
    )
    
    try:
        # 调用后端API发送
        from bot.services.api_client import APIClient
        client = APIClient()
        result = await client.send_sms(
            api_key=account.api_key,
            phone_number=phone,
            message=content
        )
        
        if result.get('success'):
            await status_msg.edit_text(
                f"✅ *短信发送成功*\n\n"
                f"号码: `{phone}`\n"
                f"内容: {content[:50]}{'...' if len(content) > 50 else ''}\n"
                f"消息ID: `{result.get('message_id', '-')}`",
                parse_mode='Markdown'
            )
        else:
            await status_msg.edit_text(
                f"❌ *发送失败*\n\n"
                f"原因: {result.get('message', '未知错误')}",
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"快速发送短信失败: {e}")
        await status_msg.edit_text(f"❌ 发送失败: {str(e)}")


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看发送历史 - /history"""
    account = await get_user_account(update.effective_user.id)
    if not account:
        await update.message.reply_text("❌ 您还未绑定账户。")
        return
    
    try:
        client = APIClient()
        res = await client.get_sms_history_internal(account_id=account.id)
        
        if not res.get("success"):
            await update.message.reply_text(f"❌ 获取记录失败: {res.get('message')}")
            return

        logs = res.get("logs", [])
        if not logs:
            await update.message.reply_text("📭 暂无发送记录。")
            return
        
        status_icons = {
            'pending': '⏳',
            'sent': '📤',
            'delivered': '✅',
            'failed': '❌'
        }
        
        text = "📋 *最近发送记录*\n\n"
        for log in logs:
            icon = status_icons.get(log['status'], '❓')
            time = log['submit_time'][:16].replace('T', ' ') if log.get('submit_time') else '-'
            phone = log['phone_number'][:8] + '****' if log.get('phone_number') else '-'
            text += f"{icon} `{phone}` | {time}\n"
            text += f"   {log['message'][:30]}{'...' if len(log.get('message') or '') > 30 else ''}\n\n"
        
        await update.message.reply_text(text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"获取发送历史失败: {e}")
        await update.message.reply_text("❌ 获取发送历史失败，请稍后重试。")


# 创建工单对话处理器
ticket_conversation = ConversationHandler(
    entry_points=[CommandHandler('ticket', ticket_start)],
    states={
        TICKET_TYPE: [
            CallbackQueryHandler(ticket_type_selected, pattern=r'^ticket_')
        ],
        TICKET_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ticket_title_input)],
        TICKET_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, ticket_desc_input)],
    },
    fallbacks=[CommandHandler('cancel', ticket_cancel)],
    per_user=True,
    per_chat=True
)


def get_handlers():
    """获取所有处理器"""
    return [
        ticket_conversation,
        CommandHandler('tickets', list_tickets),
        CommandHandler('ticket_view', view_ticket),
        CommandHandler('quick', quick_send),
        CommandHandler('history', history),
        CallbackQueryHandler(ticket_action_handler, pattern=r'^(take|resolve)_ticket_'),
    ]
