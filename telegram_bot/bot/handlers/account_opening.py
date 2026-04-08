"""
语音/数据开户流程 Handler
语音开户：选国家 → 多选线路(toggle) → 逐条设卖价 → 确认 → 发技术群+建工单
数据开户：选国家 → 单选模板 → 确认 → 发技术群+建工单
技术回复 → 转发销售 + 存储客户
"""
import os
import json
import secrets
import string
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters
)
from bot.utils import get_session, logger, dedupe_country_codes_from_templates
from app.modules.common.admin_user import AdminUser
from app.modules.common.account_template import AccountTemplate
from app.modules.common.account import Account
from app.modules.common.ticket import Ticket, TicketReply
from app.core.auth import AuthService
from sqlalchemy import select, desc, func
from app.database import AsyncSessionLocal

from bot.utils import get_group_ids

# 对话状态（保留兼容，实际用独立 CallbackQueryHandler）
(
    OPEN_SELECT_BIZ,
    OPEN_SELECT_COUNTRY,
    OPEN_SELECT_TEMPLATE,
    OPEN_CONFIRM,
    OPEN_WAIT_REMARK,
) = range(5)

COUNTRY_NAMES = {
    'CN': '中国', 'US': '美国', 'GB': '英国', 'SG': '新加坡', 'JP': '日本', 'KR': '韩国',
    'TH': '泰国', 'VN': '越南', 'MY': '马来西亚', 'ID': '印尼', 'PH': '菲律宾', 'IN': '印度',
    'AU': '澳大利亚', 'CA': '加拿大', 'DE': '德国', 'FR': '法国', 'IT': '意大利', 'ES': '西班牙',
    'RU': '俄罗斯', 'BR': '巴西', 'MX': '墨西哥', 'HK': '香港', 'TW': '台湾', 'AE': '阿联酋',
    'SA': '沙特', 'BD': '孟加拉', 'PK': '巴基斯坦', 'EG': '埃及', 'ZA': '南非',
    'KE': '肯尼亚', 'NG': '尼日利亚', 'TR': '土耳其', 'IL': '以色列',
    'NL': '荷兰', 'NZ': '新西兰', 'SE': '瑞典', 'FI': '芬兰', 'PT': '葡萄牙',
    'RO': '罗马尼亚', 'PL': '波兰', 'CZ': '捷克', 'LT': '立陶宛', 'KW': '科威特',
    'MM': '缅甸', 'MX': '墨西哥', 'PE': '秘鲁', 'CO': '哥伦比亚', 'ET': '埃塞俄比亚',
    'IE': '爱尔兰',
    'BJ': '贝宁',
}

BIZ_LABELS = {"voice": "📞 语音", "data": "📊 数据", "sms": "📱 短信"}


def _gen_ticket_no() -> str:
    now = datetime.now()
    rand = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
    return f"TK{now.strftime('%Y%m%d%H%M%S')}{rand}"


def _country_label(code: str) -> str:
    name = COUNTRY_NAMES.get(code.upper(), "")
    return f"{name} ({code})" if name else code


# ============================================================
#  入口：从菜单触发
# ============================================================

async def opening_start(update: Update, context: ContextTypes.DEFAULT_TYPE, biz_type: str = None):
    """从菜单回调启动开户流程"""
    query = update.callback_query
    tg_id = query.from_user.id

    async with get_session() as db:
        admin_result = await db.execute(
            select(AdminUser).where(
                AdminUser.tg_id == tg_id,
                AdminUser.status == 'active'
            )
        )
        admin = admin_result.scalar_one_or_none()

        if not admin or admin.role not in ('sales', 'super_admin', 'admin'):
            await query.edit_message_text("❌ 仅销售/管理员可使用此功能")
            return None

        context.user_data['opening_sales_id'] = admin.id
        context.user_data['opening_sales_name'] = admin.real_name or admin.username
        context.user_data['opening_sales_tg_id'] = tg_id

    # 清理上次的多选状态
    for k in ('opening_selected', 'opening_available_templates',
              'opening_price_list', 'opening_price_idx', 'opening_current_price_tpl'):
        context.user_data.pop(k, None)

    if biz_type:
        context.user_data['opening_biz_type'] = biz_type
        return await _show_country_list(query, context, biz_type)

    keyboard = [
        [
            InlineKeyboardButton("📞 语音开户", callback_data="open_biz_voice"),
            InlineKeyboardButton("📊 数据开户", callback_data="open_biz_data"),
        ],
        [InlineKeyboardButton("🔙 返回", callback_data="menu_main")],
    ]
    await query.edit_message_text(
        "🏢 <b>开户申请</b>\n\n请选择业务类型：",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )
    return OPEN_SELECT_BIZ


async def handle_select_biz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理业务类型选择"""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "menu_main":
        return ConversationHandler.END

    biz_type = data.replace("open_biz_", "")
    context.user_data['opening_biz_type'] = biz_type
    return await _show_country_list(query, context, biz_type)


async def _show_country_list(query, context, biz_type):
    """展示国家列表"""
    async with get_session() as db:
        result = await db.execute(
            select(AccountTemplate.country_code).where(
                AccountTemplate.business_type == biz_type,
                AccountTemplate.status == "active",
                AccountTemplate.country_code.isnot(None),
            )
        )
        raw_codes = [r[0] for r in result.all()]
        country_codes = dedupe_country_codes_from_templates(raw_codes)

    if not country_codes:
        biz_label = BIZ_LABELS.get(biz_type, biz_type)
        await query.edit_message_text(f"❌ 暂无 {biz_label} 业务的可用模板")
        return ConversationHandler.END

    keyboard = []
    row = []
    for cc in country_codes:
        label = COUNTRY_NAMES.get(cc, cc)
        row.append(InlineKeyboardButton(label, callback_data=f"open_cc_{cc}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("⬅️ 返回", callback_data="open_back_biz")])

    biz_label = BIZ_LABELS.get(biz_type, biz_type)
    await query.edit_message_text(
        f"📍 <b>{biz_label} 开户 — 选择国家</b>\n\n请选择目标国家：",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )
    return OPEN_SELECT_COUNTRY


# ============================================================
#  国家选择 → 分流：语音多选 / 数据单选
# ============================================================

async def handle_select_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理国家选择"""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "open_back_biz":
        keyboard = [
            [
                InlineKeyboardButton("📞 语音开户", callback_data="open_biz_voice"),
                InlineKeyboardButton("📊 数据开户", callback_data="open_biz_data"),
            ],
            [InlineKeyboardButton("🔙 返回", callback_data="menu_main")],
        ]
        await query.edit_message_text(
            "🏢 <b>开户申请</b>\n\n请选择业务类型：",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        return

    cc = data.replace("open_cc_", "").strip().upper()
    context.user_data['opening_country_code'] = cc
    biz_type = context.user_data.get('opening_biz_type', '')

    if biz_type == 'voice':
        # 语音开户 → 多选线路模式
        context.user_data['opening_selected'] = {}
        return await _show_voice_multi_select(query, context, cc)

    # 数据/其他 → 单选模板
    return await _show_data_template_list(query, context, cc, biz_type)


# ============================================================
#  语音开户：多选线路
# ============================================================

async def _show_voice_multi_select(query, context, cc):
    """加载语音线路并展示多选列表"""
    async with get_session() as db:
        result = await db.execute(
            select(AccountTemplate)
            .where(
                AccountTemplate.business_type == 'voice',
                func.upper(AccountTemplate.country_code) == cc,
                AccountTemplate.status == "active"
            )
            .order_by(AccountTemplate.template_name)
        )
        templates = result.scalars().all()

    if not templates:
        await query.edit_message_text("❌ 该国家暂无语音线路模板")
        return

    avail = {}
    for tpl in templates:
        pr = tpl.pricing_rules or {}
        avail[tpl.id] = {
            'id': tpl.id,
            'name': tpl.template_name,
            'code': tpl.template_code,
            'cost_price': float(tpl.default_price) if tpl.default_price else 0,
            'billing_model': pr.get('billing_model', ''),
            'line_desc': pr.get('line_desc', ''),
            'pricing_rules': pr,
            'country_name': tpl.country_name or _country_label(cc),
        }
    context.user_data['opening_available_templates'] = avail
    await _render_voice_keyboard(query, context, cc)


async def _render_voice_keyboard(query, context, cc):
    """渲染语音多选键盘"""
    avail = context.user_data.get('opening_available_templates', {})
    selected = context.user_data.get('opening_selected', {})

    keyboard = []
    for tpl_id, info in avail.items():
        icon = "✅" if tpl_id in selected else "☐"
        bm = info.get('billing_model', '')
        ld = info.get('line_desc', '')
        cost = info.get('cost_price', 0)
        parts = [info['name']]
        if bm:
            parts.append(bm)
        if ld:
            parts.append(ld)
        label = f"{icon} {' | '.join(parts)} ${cost:.4f}"
        if len(label) > 60:
            label = label[:57] + "..."
        keyboard.append([InlineKeyboardButton(label, callback_data=f"open_toggle_{tpl_id}")])

    sel_count = len(selected)
    if sel_count > 0:
        keyboard.append([InlineKeyboardButton(
            f"➡️ 继续设置卖价 ({sel_count}条线路)",
            callback_data="open_proceed_price"
        )])
    keyboard.append([InlineKeyboardButton("⬅️ 返回选国家", callback_data="open_back_country")])

    await query.edit_message_text(
        f"📋 <b>📞 语音开户 — 选择线路</b> ({_country_label(cc)})\n\n"
        f"点击线路可多选，已选 <b>{sel_count}</b> 条：",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )


async def handle_toggle_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """切换语音线路选中状态"""
    query = update.callback_query
    await query.answer()

    tpl_id = int(query.data.replace("open_toggle_", ""))
    selected = context.user_data.get('opening_selected', {})
    avail = context.user_data.get('opening_available_templates', {})

    if tpl_id in selected:
        del selected[tpl_id]
    elif tpl_id in avail:
        sel = avail[tpl_id].copy()
        sel['sell_price'] = None
        selected[tpl_id] = sel

    context.user_data['opening_selected'] = selected
    cc = context.user_data.get('opening_country_code', '')
    await _render_voice_keyboard(query, context, cc)


async def handle_back_country_from_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """从语音多选返回国家列表"""
    query = update.callback_query
    await query.answer()
    biz_type = context.user_data.get('opening_biz_type', 'voice')
    return await _show_country_list(query, context, biz_type)


# ============================================================
#  语音开户：统一设置卖价
# ============================================================

async def handle_proceed_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """选完线路后进入统一设置卖价"""
    query = update.callback_query
    await query.answer()

    selected = context.user_data.get('opening_selected', {})
    if not selected:
        await query.answer("请先选择至少一条线路", show_alert=True)
        return

    await _show_unified_price_input(query, context, is_callback=True)


async def _show_unified_price_input(target, context, is_callback=True):
    """展示统一卖价输入界面"""
    selected = context.user_data.get('opening_selected', {})
    context.user_data['waiting_for'] = 'opening_sell_price'

    # 汇总已选线路
    line_items = []
    max_cost = 0
    for info in selected.values():
        bm = info.get('billing_model', '')
        ld = info.get('line_desc', '')
        cost = info.get('cost_price', 0)
        max_cost = max(max_cost, cost)
        extra = f" | {bm} {ld}".strip() if (bm or ld) else ""
        line_items.append(f"  • {info['name']}{extra}  ${cost:.4f}")

    suggest = max_cost * 1.3 if max_cost > 0 else 0.001

    text = (
        f"💰 <b>设置统一卖价</b>\n\n"
        f"已选 {len(selected)} 条线路:\n"
        + "\n".join(line_items)
        + f"\n\n请输入统一卖价（如 {suggest:.4f}）："
    )

    keyboard = [
        [InlineKeyboardButton("⬅️ 返回选线路", callback_data="open_back_voice_select")],
        [InlineKeyboardButton("❌ 取消开户", callback_data="open_cancel")],
    ]

    if is_callback:
        await target.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    else:
        await target.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')


async def handle_price_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理统一卖价文本输入（从 menu.py handle_text_input 委托调用）"""
    text = (update.message.text or "").strip()
    try:
        price = float(text)
        if price < 0:
            await update.message.reply_text("❌ 卖价不能为负数，请重新输入：")
            return
    except ValueError:
        await update.message.reply_text("❌ 请输入有效数字（如 0.003）：")
        return

    selected = context.user_data.get('opening_selected', {})
    for tpl_id in selected:
        selected[tpl_id]['sell_price'] = price

    context.user_data['waiting_for'] = None
    await _show_voice_confirm(update.message, context, is_callback=False)


# ============================================================
#  语音开户：多线路确认页
# ============================================================

async def _show_voice_confirm(target, context, is_callback=True):
    """语音开户确认页（多线路 + 卖价）"""
    ud = context.user_data
    biz_label = BIZ_LABELS.get('voice', '语音')
    cc = ud['opening_country_code']
    selected = ud.get('opening_selected', {})

    lines = [
        f"📦 <b>确认开户信息</b>\n",
        f"业务: {biz_label}",
        f"国家: {_country_label(cc)}",
        f"销售: {ud.get('opening_sales_name', '-')}\n",
        f"📋 已选线路 ({len(selected)}条):",
        "━━━━━━━━━━━━━━",
    ]
    for i, (_, info) in enumerate(selected.items(), 1):
        bm = info.get('billing_model', '')
        ld = info.get('line_desc', '')
        cost = info.get('cost_price', 0)
        sell = info.get('sell_price') or cost
        extra_parts = []
        if bm:
            extra_parts.append(bm)
        if ld:
            extra_parts.append(ld)
        extra = (" | " + " ".join(extra_parts)) if extra_parts else ""
        lines.append(
            f"{i}. {info['name']}{extra}\n"
            f"   成本: ${cost:.4f}  →  卖价: <b>${sell:.4f}</b>"
        )
    lines.append("━━━━━━━━━━━━━━")
    lines.append("\n确认后将发送开户订单到技术群并创建工单。")

    keyboard = [
        [InlineKeyboardButton("✅ 确认提交开户申请", callback_data="open_confirm_yes")],
        [InlineKeyboardButton("⬅️ 返回选择线路", callback_data="open_back_voice_select")],
        [InlineKeyboardButton("❌ 取消", callback_data="open_cancel")],
    ]

    text = "\n".join(lines)
    if is_callback:
        await target.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    else:
        await target.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')


async def handle_back_voice_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """从确认页返回语音多选页"""
    query = update.callback_query
    await query.answer()
    cc = context.user_data.get('opening_country_code', '')
    await _render_voice_keyboard(query, context, cc)


# ============================================================
#  数据开户：单选模板（原有流程保留）
# ============================================================

async def _show_data_template_list(query, context, cc, biz_type):
    """数据开户 — 展示单选模板列表"""
    async with get_session() as db:
        result = await db.execute(
            select(AccountTemplate)
            .where(
                AccountTemplate.business_type == biz_type,
                func.upper(AccountTemplate.country_code) == cc,
                AccountTemplate.status == "active"
            )
            .order_by(AccountTemplate.template_name)
        )
        templates = result.scalars().all()

    if not templates:
        await query.edit_message_text("❌ 该国家暂无可用模板")
        return

    keyboard = []
    for tpl in templates:
        price_str = f"${float(tpl.default_price):.4f}" if tpl.default_price else "待定"
        pr = tpl.pricing_rules or {}
        extra = ""
        src = pr.get('source', '')
        purpose = pr.get('purpose', '')
        if src:
            extra += f" | {src}"
        if purpose:
            extra += f"-{purpose}"

        label = f"{tpl.template_name} ({price_str}{extra})"
        if len(label) > 60:
            label = label[:57] + "..."
        keyboard.append([InlineKeyboardButton(label, callback_data=f"open_tpl_{tpl.id}")])
    keyboard.append([InlineKeyboardButton("⬅️ 返回", callback_data="open_back_country")])

    biz_label = BIZ_LABELS.get(biz_type, biz_type)
    await query.edit_message_text(
        f"📋 <b>{biz_label} 开户 — 选择模板</b> ({_country_label(cc)})\n\n请选择开户模板：",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )


async def handle_select_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理数据模板单选"""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "open_back_country":
        biz_type = context.user_data.get('opening_biz_type', '')
        return await _show_country_list(query, context, biz_type)

    tpl_id = int(data.replace("open_tpl_", ""))

    async with get_session() as db:
        result = await db.execute(
            select(AccountTemplate).where(AccountTemplate.id == tpl_id)
        )
        tpl = result.scalar_one_or_none()

    if not tpl:
        await query.edit_message_text("❌ 模板不存在")
        return

    context.user_data['opening_template_id'] = tpl.id
    context.user_data['opening_template_name'] = tpl.template_name
    context.user_data['opening_template_code'] = tpl.template_code
    context.user_data['opening_country_name'] = tpl.country_name or _country_label(tpl.country_code)
    context.user_data['opening_default_price'] = float(tpl.default_price) if tpl.default_price else 0
    context.user_data['opening_pricing_rules'] = tpl.pricing_rules or {}

    return await _show_data_confirm(query, context)


async def _show_data_confirm(query, context):
    """数据开户确认页（单模板）"""
    ud = context.user_data
    biz_type = ud['opening_biz_type']
    biz_label = BIZ_LABELS.get(biz_type, biz_type)
    cc = ud['opening_country_code']
    tpl_name = ud['opening_template_name']
    price = ud['opening_default_price']
    pr = ud.get('opening_pricing_rules', {})

    detail_lines = []
    for k, label in [('source', '来源'), ('purpose', '用途'), ('freshness', '时效')]:
        v = pr.get(k, '')
        if v:
            detail_lines.append(f"{label}: {v}")
    detail_text = "\n".join(detail_lines)
    if detail_text:
        detail_text = f"\n{detail_text}"

    keyboard = [
        [InlineKeyboardButton("✅ 确认提交开户申请", callback_data="open_confirm_yes")],
        [InlineKeyboardButton("⬅️ 返回", callback_data="open_back_template")],
        [InlineKeyboardButton("❌ 取消", callback_data="open_cancel")],
    ]

    await query.edit_message_text(
        f"📦 <b>确认开户信息</b>\n\n"
        f"业务类型: {biz_label}\n"
        f"国家: {_country_label(cc)}\n"
        f"模板: {tpl_name}\n"
        f"成本价: ${price:.4f}"
        f"{detail_text}\n"
        f"销售: {ud.get('opening_sales_name', '-')}\n\n"
        f"确认后将发送开户订单到技术群并创建工单。",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )


# ============================================================
#  确认提交 / 取消 / 返回
# ============================================================

async def handle_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """确认开户 — 统一入口"""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "open_cancel":
        context.user_data.pop('waiting_for', None)
        await query.edit_message_text("❌ 已取消开户申请")
        return

    if data == "open_back_template":
        biz_type = context.user_data.get('opening_biz_type', '')
        cc = context.user_data.get('opening_country_code', '')
        return await _show_data_template_list(query, context, cc, biz_type)

    if data != "open_confirm_yes":
        return

    ud = context.user_data
    biz_type = ud.get('opening_biz_type', '')

    if biz_type == 'voice' and ud.get('opening_selected'):
        await _submit_voice_order(query, context)
    else:
        await _submit_data_order(query, context)


# ============================================================
#  提交语音开户订单（多线路）
# ============================================================

async def _submit_voice_order(query, context):
    """提交语音开户订单 — 语音对接外部OKCC系统，等技术回复后再创建账户"""
    ud = context.user_data
    biz_label = BIZ_LABELS.get('voice', '语音')
    cc = ud['opening_country_code']
    selected = ud.get('opening_selected', {})
    sales_id = ud['opening_sales_id']
    sales_name = ud.get('opening_sales_name', '-')
    sales_tg_id = ud['opening_sales_tg_id']

    first_info = next(iter(selected.values()))
    country_name = first_info.get('country_name', _country_label(cc))

    selected_lines = []
    for tpl_id, info in selected.items():
        selected_lines.append({
            "template_id": tpl_id,
            "template_name": info['name'],
            "template_code": info.get('code', ''),
            "billing_model": info.get('billing_model', ''),
            "line_desc": info.get('line_desc', ''),
            "cost_price": info.get('cost_price', 0),
            "sell_price": info.get('sell_price') or info.get('cost_price', 0),
            "pricing_rules": info.get('pricing_rules', {}),
        })

    line_summary = ", ".join(
        f"{l.get('billing_model', '')} {l.get('line_desc', '')}".strip() or l['template_name']
        for l in selected_lines
    )
    if len(line_summary) > 60:
        line_summary = line_summary[:57] + "..."

    ticket_no = _gen_ticket_no()
    extra_data = {
        "opening_type": "voice",
        "country_code": cc,
        "country_name": country_name,
        "selected_lines": selected_lines,
        "sales_id": sales_id,
        "sales_name": sales_name,
        "sales_tg_id": sales_tg_id,
    }

    try:
        # 1. 创建工单（不创建账户，等OKCC开户后再建）
        async with AsyncSessionLocal() as session:
            ticket = Ticket(
                ticket_no=ticket_no,
                tg_user_id=str(sales_tg_id),
                ticket_type='registration',
                priority='high',
                category='voice',
                title=f"{biz_label} 开户 - {country_name} - {line_summary}",
                description=_build_voice_description(sales_name, country_name, cc, selected_lines),
                status='open',
                created_by_type='admin',
                created_by_id=sales_id,
                template_id=selected_lines[0]['template_id'] if selected_lines else None,
                extra_data=extra_data,
            )
            session.add(ticket)
            await session.commit()
            await session.refresh(ticket)
            ticket_id = ticket.id

        # 2. 发送到技术群
        group_ids = await get_group_ids()
        target_group = group_ids.get('tech_group_id') or group_ids.get('admin_group_id')
        if target_group:
            order_text = _build_voice_order_text(
                ticket_no, biz_label, country_name, cc, sales_name, selected_lines
            )
            keyboard = [
                [InlineKeyboardButton("🙋‍♂️ 接单", callback_data=f"opening_take_{ticket_id}")],
            ]
            sent_msg = await context.bot.send_message(
                chat_id=int(target_group),
                text=order_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            async with AsyncSessionLocal() as session:
                t = await session.get(Ticket, ticket_id)
                if t:
                    t.forwarded_to_group = target_group
                    t.forwarded_message_id = sent_msg.message_id
                    t.review_status = 'forwarded'
                    await session.commit()

        # 3. 通知销售
        line_names = "\n".join(
            f"  • {l['template_name']} ({l.get('billing_model', '')} {l.get('line_desc', '')}) ${l['sell_price']:.4f}"
            for l in selected_lines
        )
        await query.edit_message_text(
            f"✅ <b>语音开户申请已提交</b>\n\n"
            f"工单号: <code>{ticket_no}</code>\n"
            f"业务: {biz_label}\n"
            f"国家: {country_name}\n"
            f"线路:\n{line_names}\n\n"
            f"已发送到技术群，技术在OKCC开户完成后\n"
            f"回复OKCC账号信息，系统将自动存储并通知您。",
            parse_mode='HTML'
        )

    except Exception as e:
        logger.error(f"创建语音开户订单失败: {e}", exc_info=True)
        await query.edit_message_text(f"❌ 提交失败: {str(e)[:200]}")


def _build_voice_description(sales_name, country_name, cc, selected_lines):
    lines = [f"销售 {sales_name} 提交的语音开户申请", f"国家: {country_name} ({cc})", ""]
    for i, sl in enumerate(selected_lines, 1):
        lines.append(
            f"{i}. {sl['template_name']} | {sl.get('billing_model','')} {sl.get('line_desc','')}\n"
            f"   成本: ${sl['cost_price']:.4f}  卖价: ${sl['sell_price']:.4f}"
        )
    return "\n".join(lines)


def _build_voice_order_text(ticket_no, biz_label, country_name, cc, sales_name, selected_lines):
    """构建发到技术群的订单消息"""
    lines = [
        f"🆕 <b>{biz_label} 开户订单</b>",
        "━━━━━━━━━━━━━━",
        f"工单号: <code>{ticket_no}</code>",
        f"国家: {country_name} ({cc})",
        f"销售: {sales_name}",
        "",
        f"📋 需开通线路 ({len(selected_lines)}条):",
    ]
    for i, sl in enumerate(selected_lines, 1):
        bm = sl.get('billing_model', '')
        ld = sl.get('line_desc', '')
        extra = f" | {bm} {ld}".strip() if (bm or ld) else ""
        lines.append(
            f"  {i}. {sl['template_name']}{extra}\n"
            f"     成本 ${sl['cost_price']:.4f} → 卖价 ${sl['sell_price']:.4f}"
        )
    lines.append("")
    lines.append("━━━━━━━━━━━━━━")
    lines.append("⚠️ 技术请开户完成后 <b>回复本消息</b> 并附上客户账户信息")
    return "\n".join(lines)


# ============================================================
#  提交数据开户订单（单模板，原有逻辑）
# ============================================================

async def _submit_data_order(query, context):
    """提交数据开户订单 — 自动创建账户 + 生成登录信息"""
    ud = context.user_data
    biz_type = ud.get('opening_biz_type', 'data')
    biz_label = BIZ_LABELS.get(biz_type, biz_type)
    cc = ud['opening_country_code']
    country_name = ud.get('opening_country_name', cc)
    tpl_name = ud['opening_template_name']
    tpl_id = ud['opening_template_id']
    price = ud['opening_default_price']
    pr = ud.get('opening_pricing_rules', {})
    sales_id = ud['opening_sales_id']
    sales_name = ud.get('opening_sales_name', '-')
    sales_tg_id = ud['opening_sales_tg_id']

    ticket_no = _gen_ticket_no()

    try:
        # 1. 创建客户账户
        account, plain_pwd, api_key = await _create_account_now(
            biz_type, cc, sales_id, default_price=price
        )

        extra_data = {
            "opening_type": biz_type,
            "country_code": cc,
            "country_name": country_name,
            "template_id": tpl_id,
            "template_name": tpl_name,
            "default_price": price,
            "pricing_rules": pr,
            "sales_id": sales_id,
            "sales_name": sales_name,
            "sales_tg_id": sales_tg_id,
            "account_id": account.id,
            "account_name": account.account_name,
        }

        # 2. 创建工单
        async with AsyncSessionLocal() as session:
            ticket = Ticket(
                ticket_no=ticket_no,
                tg_user_id=str(sales_tg_id),
                ticket_type='registration',
                priority='high',
                category=biz_type,
                title=f"{biz_label} 开户 - {country_name} - {tpl_name}",
                description=(
                    f"销售 {sales_name} 提交的{biz_label}开户申请\n"
                    f"国家: {country_name} ({cc})\n"
                    f"模板: {tpl_name}\n"
                    f"成本价: ${price:.4f}\n"
                    f"账户: {account.account_name}"
                ),
                status='open',
                created_by_type='admin',
                created_by_id=sales_id,
                template_id=tpl_id,
                extra_data=extra_data,
            )
            session.add(ticket)
            await session.commit()
            await session.refresh(ticket)
            ticket_id = ticket.id

        # 3. 发送到技术群
        group_ids = await get_group_ids()
        target_group = group_ids.get('tech_group_id') or group_ids.get('admin_group_id')
        if target_group:
            detail_lines = []
            for k, label in [('source', '来源'), ('purpose', '用途'), ('freshness', '时效')]:
                v = pr.get(k, '')
                if v:
                    detail_lines.append(f"{label}: {v}")
            detail_text = "\n".join(detail_lines)
            if detail_text:
                detail_text = f"\n{detail_text}\n"
            else:
                detail_text = "\n"

            order_text = (
                f"🆕 <b>{biz_label} 开户订单</b>\n"
                f"━━━━━━━━━━━━━━\n"
                f"工单号: <code>{ticket_no}</code>\n"
                f"国家: {country_name} ({cc})\n"
                f"模板: {tpl_name}\n"
                f"成本价: ${price:.4f}\n"
                f"{detail_text}"
                f"销售: {sales_name}\n"
                f"\n📋 <b>已自动创建账户</b>\n"
                f"账户: <code>{account.account_name}</code>\n"
                f"━━━━━━━━━━━━━━\n"
                f"⚠️ 技术请开户完成后 <b>回复本消息</b> 并附上配置信息"
            )

            keyboard = [
                [InlineKeyboardButton("🙋‍♂️ 接单", callback_data=f"opening_take_{ticket_id}")],
            ]
            sent_msg = await context.bot.send_message(
                chat_id=int(target_group),
                text=order_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            async with AsyncSessionLocal() as session:
                t = await session.get(Ticket, ticket_id)
                if t:
                    t.forwarded_to_group = target_group
                    t.forwarded_message_id = sent_msg.message_id
                    t.review_status = 'forwarded'
                    await session.commit()

        # 4. 通知销售（含账户 + 登录信息）
        login_url = os.getenv('CUSTOMER_PORTAL_URL', 'https://www.kaolach.com')
        await query.edit_message_text(
            f"✅ <b>开户申请已提交</b>\n\n"
            f"工单号: <code>{ticket_no}</code>\n"
            f"业务: {biz_label}\n"
            f"国家: {country_name}\n"
            f"模板: {tpl_name}\n\n"
            f"━━━━━━━━━━━━━━\n"
            f"📋 <b>客户账户信息</b>\n"
            f"账户名: <code>{account.account_name}</code>\n"
            f"密码: <code>{plain_pwd}</code>\n"
            f"API Key: <code>{api_key}</code>\n"
            f"登录: {login_url}\n"
            f"━━━━━━━━━━━━━━\n\n"
            f"已发送到技术群，开户完成后会通知您。",
            parse_mode='HTML'
        )

    except Exception as e:
        logger.error(f"创建数据开户订单失败: {e}", exc_info=True)
        await query.edit_message_text(f"❌ 提交失败: {str(e)[:200]}")


# ============================================================
#  技术群：接单
# ============================================================

async def handle_opening_take(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """技术人员接单"""
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user

    try:
        ticket_id = int(data.replace("opening_take_", ""))
    except ValueError:
        return

    async with AsyncSessionLocal() as session:
        admin_result = await session.execute(
            select(AdminUser).where(AdminUser.tg_id == user.id, AdminUser.status == 'active')
        )
        admin = admin_result.scalar_one_or_none()
        if not admin:
            await context.bot.send_message(chat_id=user.id, text="❌ 您不是管理员，无法接单")
            return

        ticket = await session.get(Ticket, ticket_id)
        if not ticket:
            return

        if ticket.status not in ('open', 'assigned'):
            await context.bot.send_message(chat_id=user.id, text=f"ℹ️ 工单状态已变更 ({ticket.status})")
            return

        ticket.status = 'in_progress'
        ticket.assigned_to = admin.id
        ticket.assigned_at = datetime.now()
        await session.commit()

        old_text = query.message.text or query.message.caption or ""
        new_text = old_text + f"\n\n✅ 已接单: {admin.real_name or admin.username}"
        try:
            await query.edit_message_text(new_text, parse_mode='HTML')
        except Exception:
            pass

        await context.bot.send_message(
            chat_id=user.id,
            text=f"✅ 您已接单: {ticket.ticket_no}\n请开户完成后回复该消息附上客户账户信息。"
        )


# ============================================================
#  技术群：回复开户消息 → 转发给销售 + 存储客户
# ============================================================

async def handle_tech_reply_in_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """检测技术群内对开户订单消息的回复，解析供应商凭据并存储"""
    message = update.effective_message
    if not message or not message.reply_to_message:
        return

    chat_id = str(message.chat_id)
    group_ids = await get_group_ids()
    target_group = group_ids.get('tech_group_id') or group_ids.get('admin_group_id')
    if not target_group or chat_id != str(target_group):
        return

    reply_text = message.text or message.caption or ""
    if not reply_text.strip():
        return

    replied_content = message.reply_to_message.text or message.reply_to_message.caption or ""
    if "开户订单" not in replied_content:
        return

    import re
    ticket_no_match = re.search(r'TK\d{14}[A-Z0-9]{6}', replied_content)
    if not ticket_no_match:
        return

    ticket_no = ticket_no_match.group(0)
    tech_user = message.from_user

    # 解析供应商凭据（OKCC 等外部系统），同时保存原始回复
    creds = _parse_supplier_credentials(reply_text)
    creds['raw_reply'] = reply_text.strip()

    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Ticket).where(Ticket.ticket_no == ticket_no)
            )
            ticket = result.scalar_one_or_none()
            if not ticket:
                return

            if ticket.status in ('resolved', 'closed', 'cancelled'):
                return

            extra = ticket.extra_data or {}
            sales_tg_id = extra.get('sales_tg_id')
            biz_type = extra.get('opening_type', '')
            biz_label = BIZ_LABELS.get(biz_type, biz_type)
            country_name = extra.get('country_name', '')
            cc = extra.get('country_code', '')
            sales_name = extra.get('sales_name', '')
            sales_id = extra.get('sales_id')

            tpl_name = extra.get('template_name', '')
            selected_lines = extra.get('selected_lines', [])
            if selected_lines:
                tpl_name = ", ".join(sl.get('template_name', '') for sl in selected_lines[:3])
                if len(selected_lines) > 3:
                    tpl_name += f" 等{len(selected_lines)}条"

            tech_admin_result = await session.execute(
                select(AdminUser).where(AdminUser.tg_id == tech_user.id, AdminUser.status == 'active')
            )
            tech_admin = tech_admin_result.scalar_one_or_none()
            tech_name = tech_admin.real_name or tech_admin.username if tech_admin else f"TG:{tech_user.id}"

            reply_record = TicketReply(
                ticket_id=ticket.id,
                reply_by_type='admin',
                reply_by_id=tech_admin.id if tech_admin else None,
                reply_by_name=tech_name,
                content=reply_text,
                is_internal=False,
                is_solution=True,
                source='telegram',
            )
            session.add(reply_record)

            ticket.status = 'resolved'
            ticket.resolved_at = datetime.now()
            if tech_admin:
                ticket.resolved_by = tech_admin.id
            ticket.resolution = reply_text

            # 根据业务类型处理账户
            account = None
            account_id = extra.get('account_id')

            if biz_type == 'voice':
                # 语音：对接外部OKCC系统，用OKCC客户名作为账户名
                okcc_name = creds.get('client_name', '')
                if not okcc_name:
                    ent = creds.get('sections', {}).get('enterprise_login', {})
                    okcc_name = ent.get('客户名', '') or ent.get('客户名', '')
                acct_name = okcc_name or f"VOICE_{cc}_{secrets.token_hex(3).upper()}"

                if account_id:
                    account = await session.get(Account, account_id)
                    if account:
                        account.account_name = acct_name
                        account.supplier_credentials = creds
                        account.supplier_url = creds.get('system_url', '')
                else:
                    # 语音订单提交时未创建账户，此时创建
                    sell_price = 0
                    if selected_lines:
                        sell_price = selected_lines[0].get('sell_price', 0)
                    account = Account(
                        account_name=acct_name,
                        sales_id=sales_id,
                        status='active',
                        balance=0,
                        rate_limit=1000,
                        business_type='voice',
                        services='voice',
                        country_code=cc,
                        unit_price=sell_price,
                        supplier_url=creds.get('system_url', ''),
                        supplier_credentials=creds,
                    )
                    session.add(account)
                    await session.flush()
                    # 更新工单 extra_data
                    extra['account_id'] = account.id
                    extra['account_name'] = acct_name
                    ticket.extra_data = extra

            else:
                # 数据：已在提交时自动创建账户，补充供应商信息
                if account_id and creds:
                    account = await session.get(Account, account_id)
                    if account:
                        account.supplier_credentials = creds
                        account.supplier_url = creds.get('system_url', '')

            await session.commit()

            display_name = ''
            if account:
                display_name = account.account_name
            elif account_id:
                display_name = extra.get('account_name', '')

            # 构建销售信息卡
            if sales_tg_id:
                forward_text = _build_sales_info_card(
                    biz_label, ticket_no, country_name, tpl_name,
                    display_name, creds, reply_text
                )
                try:
                    await context.bot.send_message(
                        chat_id=int(sales_tg_id),
                        text=forward_text,
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logger.error(f"转发开户信息给销售失败: {e}")

            await message.reply_text(
                f"✅ 开户信息已记录并转发给销售 {sales_name}\n"
                f"工单 {ticket_no} 已自动完结。"
                + (f"\n客户账户: {display_name}" if display_name else ""),
            )

    except Exception as e:
        logger.error(f"处理技术回复失败: {e}", exc_info=True)


def _parse_supplier_credentials(text: str) -> dict:
    """
    解析技术回复中的供应商凭据，支持常见格式：
    系统地址 / 客户名 / 用户名 / 密码 / 坐席号 / 域名 / 口令 / 送号规则
    """
    import re
    creds = {}

    # 提取 URL（系统地址）
    url_match = re.search(r'https?://[^\s]+', text)
    if url_match:
        creds['system_url'] = url_match.group(0).rstrip('/')

    # 通用键值提取（中文冒号 / 英文冒号均兼容）
    kv_patterns = {
        'client_name': r'客户名[：:]\s*(.+)',
        'username': r'用户名[：:]\s*(.+)',
        'password': r'密码[：:]\s*(.+)',
        'agent_range': r'坐席号[：:]\s*(.+)',
        'agent_password': r'口令[：:]\s*(.+)',
        'domain': r'域名[：:]\s*(.+)',
        'dial_rule': r'送号规则[：:]\s*(.+)',
    }
    for key, pattern in kv_patterns.items():
        match = re.search(pattern, text)
        if match:
            val = match.group(1).strip()
            if val:
                creds[key] = val

    # 如果有多段（企业客户登录 / 坐席注册 / 坐席登录），构建分段
    sections = {}
    current_section = None
    for line in text.split('\n'):
        line_s = line.strip().strip('-')
        if not line_s:
            continue
        if '企业客户登录' in line_s:
            current_section = 'enterprise_login'
            sections[current_section] = {}
        elif '坐席注册' in line_s:
            current_section = 'agent_register'
            sections[current_section] = {}
        elif '坐席登录' in line_s:
            current_section = 'agent_login'
            sections[current_section] = {}
        elif current_section and ('：' in line_s or ':' in line_s):
            sep = '：' if '：' in line_s else ':'
            parts = line_s.split(sep, 1)
            if len(parts) == 2:
                k, v = parts[0].strip(), parts[1].strip()
                if k and v:
                    sections[current_section][k] = v

    if sections:
        creds['sections'] = sections

    return creds


def _build_sales_info_card(biz_label, ticket_no, country_name, tpl_name,
                           account_name, creds, raw_reply):
    """构建发给销售的专业开户信息卡"""
    lines = [
        f"🎉 <b>{biz_label} 开户完成</b>",
        "━━━━━━━━━━━━━━",
        f"工单号: <code>{ticket_no}</code>",
        f"国家: {country_name}",
        f"线路: {tpl_name}",
        f"客户账户: <code>{account_name}</code>",
    ]

    if creds:
        system_url = creds.get('system_url', '')
        sections = creds.get('sections', {})

        if system_url:
            lines.append(f"\n🌐 <b>OKCC 系统</b>")
            lines.append(f"地址: {system_url}")

        if 'enterprise_login' in sections:
            ent = sections['enterprise_login']
            lines.append(f"\n🏢 <b>企业客户登录</b>")
            for k, v in ent.items():
                lines.append(f"{k}: <code>{v}</code>")

        if 'agent_register' in sections:
            reg = sections['agent_register']
            lines.append(f"\n📞 <b>坐席注册</b>")
            for k, v in reg.items():
                lines.append(f"{k}: <code>{v}</code>")

        if 'agent_login' in sections:
            login = sections['agent_login']
            lines.append(f"\n👤 <b>坐席登录</b>")
            for k, v in login.items():
                lines.append(f"{k}: <code>{v}</code>")

        dial_rule = creds.get('dial_rule', '')
        if dial_rule:
            lines.append(f"\n📋 <b>送号规则</b>")
            lines.append(dial_rule)

        if not sections:
            lines.append(f"\n📋 <b>技术回复</b>")
            lines.append(raw_reply)
    else:
        lines.append(f"\n📋 <b>技术回复</b>")
        lines.append(raw_reply)

    lines.append("\n━━━━━━━━━━━━━━")
    return "\n".join(lines)


async def _create_account_now(biz_type, cc, sales_id, selected_lines=None, default_price=0):
    """
    立即创建客户账户，返回 (account, plain_password, api_key)。
    在提交订单时调用，而非等待技术回复。
    """
    if selected_lines:
        price = selected_lines[0].get('sell_price', 0) or selected_lines[0].get('cost_price', 0)
    else:
        price = default_price

    account_name = f"{biz_type.upper()}_{cc}_{secrets.token_hex(3).upper()}"
    api_key_plain = secrets.token_hex(32)
    plain_pwd = secrets.token_urlsafe(10)

    async with AsyncSessionLocal() as session:
        new_account = Account(
            account_name=account_name,
            sales_id=sales_id,
            status='active',
            balance=0,
            api_key=api_key_plain,
            password_hash=AuthService.hash_password(plain_pwd),
            rate_limit=1000,
            business_type=biz_type,
            services=biz_type,
            country_code=cc,
            unit_price=price,
        )
        session.add(new_account)

        if biz_type == 'data':
            try:
                await session.flush()
                from app.modules.data.data_account import DataAccount
                da = DataAccount(
                    account_id=new_account.id,
                    country_code=cc,
                    balance=0,
                    total_extracted=0,
                    total_spent=0,
                    status='active',
                )
                session.add(da)
            except Exception as e:
                logger.warning(f"创建数据子账户失败: {e}")

        await session.commit()
        await session.refresh(new_account)

    return new_account, plain_pwd, api_key_plain


# ============================================================
#  导出 Handler
# ============================================================

opening_handlers = [
    # 业务类型选择
    CallbackQueryHandler(handle_select_biz, pattern=r'^open_biz_(voice|data)$'),
    # 国家选择 + 返回
    CallbackQueryHandler(handle_select_country, pattern=r'^open_cc_[A-Z]{2}$'),
    CallbackQueryHandler(handle_select_country, pattern=r'^open_back_biz$'),
    # 语音：多选线路 toggle
    CallbackQueryHandler(handle_toggle_template, pattern=r'^open_toggle_\d+$'),
    # 语音：返回国家（从多选页）
    CallbackQueryHandler(handle_back_country_from_voice, pattern=r'^open_back_country$'),
    # 语音：进入统一设置卖价
    CallbackQueryHandler(handle_proceed_price, pattern=r'^open_proceed_price$'),
    # 语音：从确认页返回多选
    CallbackQueryHandler(handle_back_voice_select, pattern=r'^open_back_voice_select$'),
    # 数据：单选模板 + 返回国家
    CallbackQueryHandler(handle_select_template, pattern=r'^open_tpl_\d+$'),
    # 确认 / 取消 / 返回模板（数据）
    CallbackQueryHandler(handle_confirm, pattern=r'^open_confirm_yes$'),
    CallbackQueryHandler(handle_confirm, pattern=r'^open_cancel$'),
    CallbackQueryHandler(handle_confirm, pattern=r'^open_back_template$'),
    # 技术群接单
    CallbackQueryHandler(handle_opening_take, pattern=r'^opening_take_\d+$'),
]
