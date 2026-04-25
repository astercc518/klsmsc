"""业务工单处理器

员工通过菜单发起 9 类业务工单（短信/语音/数据 × 开户/测试/反馈），
ConversationHandler 接管描述输入，避开其他 conversation 拦截 TEXT。

发起后推送至技术群，技术点击接单/完成时通知发起人，群消息按钮联动。
"""
import re

from loguru import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.services.api_client import APIClient
from bot.utils import get_group_ids


BIZ_DESC = 0

CAT_LABELS = {'sms': '短信', 'voice': '语音', 'data': '数据'}
ACT_LABELS = {'register': '开户', 'test': '测试', 'feedback': '反馈'}
ACT_TYPE_MAP = {'register': 'registration', 'test': 'test', 'feedback': 'feedback'}

CAT_EMOJI = {'sms': '📱', 'voice': '📞', 'data': '📊'}

STATUS_LABELS = {
    'open': '⏳ 待处理',
    'assigned': '👤 已分配',
    'in_progress': '🔄 处理中',
    'pending_user': '💬 等待回复',
    'resolved': '✅ 已完成',
    'closed': '🔒 已关闭',
    'cancelled': '❌ 已取消',
}


def _biz_top_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 短信工单", callback_data="btk_sms"),
         InlineKeyboardButton("📞 语音工单", callback_data="btk_voice")],
        [InlineKeyboardButton("📊 数据工单", callback_data="btk_data")],
        [InlineKeyboardButton("📂 我的业务工单", callback_data="bizt_my")],
        [InlineKeyboardButton("🔙 返回", callback_data="menu_main")],
    ])


def _cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ 取消", callback_data="bizt_cancel")]])


async def _get_admin(tg_id: int):
    api = APIClient()
    res = await api.get_admin_internal(tg_id=tg_id)
    if res.get("success") and res.get("admin"):
        from types import SimpleNamespace
        return SimpleNamespace(**res["admin"])
    return None


# ── 1. 入口：选择具体子类型 ───────────────────────────────────

async def on_btk_action_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 btk_<biz>_<action> 回调，进入描述输入阶段。"""
    query = update.callback_query
    await query.answer()
    m = re.match(r'^btk_(sms|voice|data)_(register|test|feedback)$', query.data)
    if not m:
        return ConversationHandler.END

    biz, action = m.group(1), m.group(2)
    label = f"{CAT_LABELS[biz]}{ACT_LABELS[action]}"

    context.user_data['biz_ctx'] = {'biz': biz, 'action': action, 'label': label}

    await query.edit_message_text(
        f"📋 {label}工单\n\n请输入需求/问题描述（5–2000 字）：",
        reply_markup=_cancel_keyboard()
    )
    return BIZ_DESC


# ── 2. 描述输入：创建工单 + 推送技术群 ─────────────────────────

async def on_biz_desc_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if len(text) < 5:
        await update.message.reply_text("描述太短，请至少输入 5 个字符：", reply_markup=_cancel_keyboard())
        return BIZ_DESC
    if len(text) > 2000:
        await update.message.reply_text("描述过长，请控制在 2000 字以内：", reply_markup=_cancel_keyboard())
        return BIZ_DESC

    ctx = context.user_data.pop('biz_ctx', None)
    if not ctx:
        await update.message.reply_text("会话已过期，请重新进入业务工单菜单。")
        return ConversationHandler.END

    biz, action, label = ctx['biz'], ctx['action'], ctx['label']
    tg_id = update.effective_user.id
    requester_name = update.effective_user.full_name or str(tg_id)

    title = f"【{label}】{text[:80]}"

    api = APIClient()
    res = await api.create_ticket_internal(
        tg_id=tg_id,
        title=title,
        description=text,
        ticket_type=ACT_TYPE_MAP[action],
        category=biz,
    )
    if not res.get("success"):
        logger.error(f"业务工单创建失败: {res}")
        await update.message.reply_text("❌ 工单提交失败，请稍后重试。")
        return ConversationHandler.END

    ticket_id = res.get("ticket_id")
    ticket_no = res.get("ticket_no")

    biz_store = context.application.bot_data.setdefault('biz_tickets', {})
    biz_store[ticket_id] = {
        'ticket_no': ticket_no,
        'requester_tg_id': tg_id,
        'requester_name': requester_name,
        'label': label,
        'biz': biz,
        'action': action,
        'title_short': text[:60],
        'status': 'open',
    }

    # 推送技术群
    gids = await get_group_ids()
    tech_gid = gids.get('tech_group_id') or gids.get('admin_group_id')
    if tech_gid:
        notify = (
            f"🆕 新业务工单\n"
            f"━━━━━━━━━━━━\n"
            f"工单号：{ticket_no}\n"
            f"类型：{CAT_EMOJI.get(biz, '')} {label}\n"
            f"发起人：{requester_name}\n"
            f"描述：{text[:500]}"
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🙋 接单", callback_data=f"bizt_take_{ticket_id}")]])
        try:
            sent = await context.bot.send_message(chat_id=tech_gid, text=notify, reply_markup=kb)
            biz_store[ticket_id]['group_chat_id'] = sent.chat_id
            biz_store[ticket_id]['group_msg_id'] = sent.message_id
        except Exception as e:
            logger.error(f"推送技术群失败: {e}")
    else:
        logger.warning("未配置技术群 ID，工单仅入库")

    await update.message.reply_text(
        f"✅ 业务工单已提交\n\n"
        f"工单号：{ticket_no}\n"
        f"类型：{label}\n\n"
        f"技术团队将尽快处理，进展会在此通知您。"
    )
    return ConversationHandler.END


# ── 3. 取消 ──────────────────────────────────────────────

async def on_cancel_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.pop('biz_ctx', None)
    await query.edit_message_text(
        "📋 业务工单\n\n请选择工单类型：",
        reply_markup=_biz_top_keyboard()
    )
    return ConversationHandler.END


async def on_cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop('biz_ctx', None)
    await update.message.reply_text("已取消业务工单。", reply_markup=_biz_top_keyboard())
    return ConversationHandler.END


# ── 4. 接单 ──────────────────────────────────────────────

async def on_take(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    m = re.match(r'^bizt_take_(\d+)$', query.data)
    if not m:
        await query.answer()
        return
    ticket_id = int(m.group(1))

    admin = await _get_admin(update.effective_user.id)
    if not admin:
        await query.answer("❌ 仅管理员可接单", show_alert=True)
        return

    biz_store = context.application.bot_data.setdefault('biz_tickets', {})
    rec = biz_store.get(ticket_id)
    if not rec:
        await query.answer("工单数据丢失", show_alert=True)
        return
    if rec.get('status') == 'in_progress':
        await query.answer(f"已被 {rec.get('taken_by_name', '某人')} 接单")
        return
    if rec.get('status') == 'resolved':
        await query.answer("工单已完成")
        return

    api = APIClient()
    res = await api.ticket_action_internal(
        ticket_id=ticket_id, action='take', admin_tg_id=update.effective_user.id
    )
    if not res.get("success"):
        await query.answer(f"❌ {res.get('message', '接单失败')}", show_alert=True)
        return

    admin_name = getattr(admin, 'real_name', None) or getattr(admin, 'username', None) or str(update.effective_user.id)
    rec['status'] = 'in_progress'
    rec['taken_by_name'] = admin_name
    rec['taken_by_tg_id'] = update.effective_user.id

    await query.answer("已接单")

    new_text = (query.message.text or "") + f"\n\n👤 接单：{admin_name}"
    new_kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ 完成", callback_data=f"bizt_done_{ticket_id}")]])
    try:
        await query.edit_message_text(text=new_text, reply_markup=new_kb)
    except Exception as e:
        logger.warning(f"编辑群消息失败: {e}")

    try:
        await context.bot.send_message(
            chat_id=rec['requester_tg_id'],
            text=(
                f"📌 工单进展\n"
                f"工单号：{rec['ticket_no']}\n"
                f"类型：{rec['label']}\n\n"
                f"已被 {admin_name} 接单，正在处理中。"
            )
        )
    except Exception as e:
        logger.warning(f"通知发起人接单失败 tg_id={rec['requester_tg_id']}: {e}")


# ── 5. 完成 ──────────────────────────────────────────────

async def on_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    m = re.match(r'^bizt_done_(\d+)$', query.data)
    if not m:
        await query.answer()
        return
    ticket_id = int(m.group(1))

    admin = await _get_admin(update.effective_user.id)
    if not admin:
        await query.answer("❌ 仅管理员可操作", show_alert=True)
        return

    biz_store = context.application.bot_data.setdefault('biz_tickets', {})
    rec = biz_store.get(ticket_id)
    if not rec:
        await query.answer("工单数据丢失", show_alert=True)
        return
    if rec.get('status') == 'resolved':
        await query.answer("工单已完成")
        return

    api = APIClient()
    res = await api.ticket_action_internal(
        ticket_id=ticket_id, action='resolve', admin_tg_id=update.effective_user.id
    )
    if not res.get("success"):
        await query.answer(f"❌ {res.get('message', '操作失败')}", show_alert=True)
        return

    admin_name = getattr(admin, 'real_name', None) or getattr(admin, 'username', None) or str(update.effective_user.id)
    rec['status'] = 'resolved'
    rec['resolved_by_name'] = admin_name

    await query.answer("已完成")

    new_text = (query.message.text or "") + f"\n\n✅ 已完成 by {admin_name}"
    try:
        await query.edit_message_text(text=new_text, reply_markup=None)
    except Exception as e:
        logger.warning(f"编辑群消息失败: {e}")

    try:
        await context.bot.send_message(
            chat_id=rec['requester_tg_id'],
            text=(
                f"✅ 工单已完成\n"
                f"工单号：{rec['ticket_no']}\n"
                f"类型：{rec['label']}\n"
                f"处理人：{admin_name}\n\n"
                f"如需进一步沟通，请重新发起工单。"
            )
        )
    except Exception as e:
        logger.warning(f"通知发起人完成失败 tg_id={rec['requester_tg_id']}: {e}")


# ── 6. 我的业务工单 ──────────────────────────────────────

async def on_my_biz_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tg_id = update.effective_user.id
    biz_store = context.application.bot_data.get('biz_tickets', {}) or {}

    mine = [
        (tid, rec) for tid, rec in biz_store.items()
        if rec.get('requester_tg_id') == tg_id
    ]
    mine.sort(key=lambda x: x[0], reverse=True)

    if not mine:
        await query.edit_message_text(
            "📂 我的业务工单\n\n您还没有提交过业务工单。",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="menu_biz_tickets")]])
        )
        return

    lines = [f"📂 我的业务工单（共 {len(mine)} 条，按时间倒序）\n"]
    for tid, rec in mine[:20]:
        status = STATUS_LABELS.get(rec.get('status', 'open'), rec.get('status', 'open'))
        lines.append(
            f"• {rec.get('ticket_no')}\n"
            f"  {CAT_EMOJI.get(rec.get('biz'), '')} {rec.get('label')} | {status}\n"
            f"  {rec.get('title_short', '')[:50]}"
        )
        if rec.get('taken_by_name') and rec.get('status') != 'resolved':
            lines.append(f"  接单：{rec['taken_by_name']}")
        lines.append("")

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="menu_biz_tickets")]])
    )


# ── 导出 ─────────────────────────────────────────────────

def get_biz_ticket_handlers():
    conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(on_btk_action_entry,
                                 pattern=r'^btk_(sms|voice|data)_(register|test|feedback)$')
        ],
        states={
            BIZ_DESC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, on_biz_desc_text),
                CallbackQueryHandler(on_cancel_button, pattern=r'^bizt_cancel$'),
            ],
        },
        fallbacks=[
            CommandHandler('cancel', on_cancel_command),
            CallbackQueryHandler(on_cancel_button, pattern=r'^bizt_cancel$'),
        ],
        per_user=True,
        per_chat=True,
        allow_reentry=True,
        name="biz_ticket_conversation",
        persistent=False,
    )
    return [
        conv,
        CallbackQueryHandler(on_take, pattern=r'^bizt_take_\d+$'),
        CallbackQueryHandler(on_done, pattern=r'^bizt_done_\d+$'),
        CallbackQueryHandler(on_my_biz_tickets, pattern=r'^bizt_my$'),
    ]
