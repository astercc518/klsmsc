"""短信落地测试 Handler

员工发起流程：
  /sms_test → 选择国家 → 选择供应商 → 输入文案（不含中文）→ 转发至供应商群

供应商回图片流程：
  供应商群内 Reply bot 消息 + 图片 → bot 转发截图给员工
"""
import html
import re

from loguru import logger
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.services.api_client import APIClient
from bot.utils import COUNTRY_NAMES as _COUNTRY_NAMES

SELECT_COUNTRY = 0
SELECT_SUPPLIER = 1
INPUT_CONTENT = 2

_CHINESE_RE = re.compile(r'[一-鿿㐀-䶿豈-﫿⺀-⻿]')


def _country_label(code: str) -> str:
    """返回 '中文名 (CODE)' 格式，无映射时直接返回 CODE。"""
    name = _COUNTRY_NAMES.get(code.upper())
    return f"{name} ({code})" if name else code


async def _get_admin(tg_id: int):
    api = APIClient()
    res = await api.get_admin_internal(tg_id=tg_id)
    if res.get("success") and res.get("admin"):
        from types import SimpleNamespace
        return SimpleNamespace(**res["admin"])
    return None


_POPULAR_COUNTRIES = [
    "TH", "VN", "MY", "ID", "PH", "IN", "BD", "PK", "MM", "KH",
    "SG", "AE", "SA", "QA", "KW", "BH", "EG", "JO", "IQ", "LB",
    "KR", "JP", "TW", "HK", "MO", "CN",
    "BR", "MX", "CO", "AR", "PE", "CL",
    "NG", "GH", "KE", "ZA", "ET", "TZ",
    "GB", "US", "CA", "AU", "DE", "FR", "IT", "ES",
]


def _sort_countries(countries: list) -> list:
    """字母排序在前，热门国家追加在后。"""
    code_set = set(countries)
    popular = [c for c in _POPULAR_COUNTRIES if c in code_set]
    popular_set = set(popular)
    rest = sorted(c for c in countries if c not in popular_set)
    return rest + popular


def _country_keyboard(countries: list) -> InlineKeyboardMarkup:
    """每行两个国家按钮（显示中文名），底部附「其他」和「取消」。"""
    sorted_list = _sort_countries(countries)
    rows = []
    for i in range(0, len(sorted_list), 2):
        row = [InlineKeyboardButton(_country_label(sorted_list[i]), callback_data=f"stest_ctry_{sorted_list[i]}")]
        if i + 1 < len(sorted_list):
            row.append(InlineKeyboardButton(_country_label(sorted_list[i + 1]), callback_data=f"stest_ctry_{sorted_list[i + 1]}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("🔤 其他（手动输入）", callback_data="stest_ctry_other")])
    rows.append([InlineKeyboardButton("❌ 取消", callback_data="stest_cancel")])
    return InlineKeyboardMarkup(rows)


def _supplier_keyboard(suppliers: list) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(s['supplier_name'], callback_data=f"stest_sup_{s['id']}")]
        for s in suppliers
    ]
    keyboard.append([InlineKeyboardButton("⬅️ 重新选择国家", callback_data="stest_back_country")])
    keyboard.append([InlineKeyboardButton("❌ 取消", callback_data="stest_cancel")])
    return InlineKeyboardMarkup(keyboard)


# ── 公共入口逻辑 ─────────────────────────────────────────

async def _start_flow(tg_id: int, send_fn, context: ContextTypes.DEFAULT_TYPE) -> int:
    """验证身份，展示国家选择键盘。send_fn 可以是 message.reply_text 或 query.edit_message_text。"""
    admin = await _get_admin(tg_id)
    if not admin:
        await send_fn("❌ 此功能仅限内部员工使用。")
        return ConversationHandler.END

    api = APIClient()
    res = await api.get_sms_test_all_countries()
    countries = res.get("countries", [])

    if not countries:
        await send_fn("⚠️ 目前没有可用的测试国家，请联系管理员配置供应商费率。")
        return ConversationHandler.END

    context.user_data['stest_countries'] = countries
    context.user_data['stest_country_input_mode'] = False

    await send_fn(
        "📱 *SMS Landing Test*\n\nStep 1/3 — 请选择测试国家：",
        reply_markup=_country_keyboard(countries),
        parse_mode='Markdown',
    )
    return SELECT_COUNTRY


# ── Entry ────────────────────────────────────────────────

async def sms_test_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """入口：/sms_test 命令"""
    tg_id = update.effective_user.id
    context.user_data['stest_admin_name'] = (
        update.effective_user.full_name or update.effective_user.username or str(tg_id)
    )
    return await _start_flow(tg_id, update.message.reply_text, context)


async def sms_test_start_from_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """入口：菜单按钮 menu_sms_test 回调"""
    query = update.callback_query
    await query.answer()
    tg_id = update.effective_user.id
    context.user_data['stest_admin_name'] = (
        update.effective_user.full_name or update.effective_user.username or str(tg_id)
    )
    return await _start_flow(tg_id, query.edit_message_text, context)


# ── Step 1: 选择国家 ─────────────────────────────────────

async def country_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理国家按钮点击（包含「其他」和「取消」）"""
    query = update.callback_query
    await query.answer()

    if query.data == "stest_cancel":
        context.user_data.clear()
        await query.edit_message_text("已取消落地测试。")
        return ConversationHandler.END

    if query.data == "stest_ctry_other":
        context.user_data['stest_country_input_mode'] = True
        await query.edit_message_text(
            "📱 *SMS Landing Test*\n\nStep 1/3 — 请输入测试国家名称或代码（如 MY / Malaysia）：",
            parse_mode='Markdown',
        )
        return SELECT_COUNTRY

    country = query.data.removeprefix("stest_ctry_")
    return await _load_suppliers_for_country(country, query.edit_message_text, context)


async def country_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理手动输入的国家"""
    if not context.user_data.get('stest_country_input_mode'):
        return SELECT_COUNTRY

    country = update.message.text.strip()
    if not country:
        await update.message.reply_text("请输入有效的国家名称或代码。")
        return SELECT_COUNTRY

    context.user_data['stest_country_input_mode'] = False
    return await _load_suppliers_for_country(country, update.message.reply_text, context)


async def _load_suppliers_for_country(country: str, send_fn, context: ContextTypes.DEFAULT_TYPE) -> int:
    """查询该国家的供应商并展示选择键盘。"""
    api = APIClient()
    res = await api.get_sms_test_country_suppliers(country)
    suppliers = res.get("suppliers", [])

    if not suppliers:
        await send_fn(
            f"⚠️ 国家 *{country}* 暂无可用供应商，请选择其他国家或联系管理员。\n\n"
            f"发送 /sms\\_test 重新开始。",
            parse_mode='Markdown',
        )
        return ConversationHandler.END

    context.user_data['stest_country'] = country
    context.user_data['stest_suppliers'] = {str(s['id']): s for s in suppliers}

    await send_fn(
        f"✅ 已选择国家：*{country}*\n\nStep 2/3 — 请选择供应商：",
        reply_markup=_supplier_keyboard(suppliers),
        parse_mode='Markdown',
    )
    return SELECT_SUPPLIER


# ── Step 2: 选择供应商 ────────────────────────────────────

async def supplier_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "stest_cancel":
        context.user_data.clear()
        await query.edit_message_text("已取消落地测试。")
        return ConversationHandler.END

    # 返回重选国家
    if query.data == "stest_back_country":
        countries = context.user_data.get('stest_countries', [])
        if not countries:
            api = APIClient()
            res = await api.get_sms_test_all_countries()
            countries = res.get("countries", [])
            context.user_data['stest_countries'] = countries

        context.user_data['stest_country_input_mode'] = False
        await query.edit_message_text(
            "📱 *SMS Landing Test*\n\nStep 1/3 — 请选择测试国家：",
            reply_markup=_country_keyboard(countries),
            parse_mode='Markdown',
        )
        return SELECT_COUNTRY

    supplier_id = query.data.removeprefix("stest_sup_")
    suppliers = context.user_data.get('stest_suppliers', {})
    supplier = suppliers.get(supplier_id)
    if not supplier:
        await query.edit_message_text("❌ 供应商信息异常，请重新发送 /sms_test 。")
        return ConversationHandler.END

    context.user_data['stest_supplier_id'] = int(supplier_id)
    context.user_data['stest_supplier_name'] = supplier['supplier_name']
    context.user_data['stest_supplier_tg_group_id'] = supplier['telegram_group_id']
    country = context.user_data.get('stest_country', '')

    await query.edit_message_text(
        f"✅ 已选择国家：*{country}*\n"
        f"✅ 已选择供应商：*{supplier['supplier_name']}*\n\n"
        f"Step 3/3 — 请输入测试短信文案（*不允许包含中文*）：",
        parse_mode='Markdown',
    )
    return INPUT_CONTENT


# ── Step 3: 输入文案 ─────────────────────────────────────

async def content_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if not text:
        await update.message.reply_text("文案不能为空，请重新输入：")
        return INPUT_CONTENT

    if _CHINESE_RE.search(text):
        await update.message.reply_text("❌ 文案中不允许包含中文，请修改后重新输入：")
        return INPUT_CONTENT

    supplier_name = context.user_data.get('stest_supplier_name', '')
    supplier_id = context.user_data.get('stest_supplier_id')
    supplier_tg_group_id = context.user_data.get('stest_supplier_tg_group_id')
    country = context.user_data.get('stest_country', '')
    requester_name = context.user_data.get('stest_admin_name', '')
    requester_tg_id = update.effective_user.id

    forward_text = (
        f"📱 <b>短信落地测试请求</b>\n\n"
        f"国家：{html.escape(_country_label(country))}\n"
        f"供应商：{html.escape(supplier_name)}\n\n"
        f"测试内容：\n<code>{html.escape(text)}</code>\n\n"
        f"<i>请回复此消息并附上落地截图。</i>"
    )

    try:
        sent = await update.get_bot().send_message(
            chat_id=int(supplier_tg_group_id),
            text=forward_text,
            parse_mode='HTML',
        )
    except Exception as e:
        logger.error(f"发送至供应商群失败 group={supplier_tg_group_id}: {e}")
        await update.message.reply_text("❌ 转发至供应商群失败，请检查 Bot 是否已加入该群。")
        context.user_data.clear()
        return ConversationHandler.END

    api = APIClient()
    try:
        await api.create_sms_test_request(
            requester_tg_id=requester_tg_id,
            requester_name=requester_name,
            supplier_id=supplier_id,
            country=country,
            sms_content=text,
            forwarded_message_id=sent.message_id,
        )
    except Exception as e:
        logger.error(f"创建落地测试记录失败: {e}")

    await update.message.reply_text(
        f"✅ *测试请求已发送至供应商群*\n\n"
        f"国家：{country}\n"
        f"供应商：{supplier_name}\n\n"
        f"请等待供应商回传落地截图，截图将直接发送至您的私信。",
        parse_mode='Markdown',
    )

    context.user_data.clear()
    return ConversationHandler.END


# ── Cancel ──────────────────────────────────────────────

async def sms_test_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("已取消短信落地测试。")
    return ConversationHandler.END


# ── 供应商群图片回复处理器 ────────────────────────────────

async def handle_supplier_photo_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """检测供应商群内 Reply bot 消息的图片，转发截图给员工"""
    msg = update.message
    if not msg or not msg.photo or not msg.reply_to_message:
        return

    bot_user = await context.bot.get_me()
    if msg.reply_to_message.from_user.id != bot_user.id:
        return

    group_id = str(update.effective_chat.id)
    reply_to_id = msg.reply_to_message.message_id

    api = APIClient()
    try:
        result = await api.find_sms_test_by_message(group_id, reply_to_id)
    except Exception as e:
        logger.error(f"查询落地测试记录失败: {e}")
        return

    if not result.get("success"):
        return

    test_id = result["id"]
    requester_tg_id = result["requester_tg_id"]
    supplier_name = result.get("supplier_name", "")
    country = result.get("country", "")

    best_photo = msg.photo[-1]
    note = msg.caption or None

    try:
        await api.complete_sms_test(test_id, [best_photo.file_id], note=note)
    except Exception as e:
        logger.error(f"完成落地测试记录失败 test_id={test_id}: {e}")

    caption = (
        f"📸 落地测试截图\n"
        f"国家：{_country_label(country)}\n"
        f"供应商：{supplier_name}"
    )
    if note:
        caption += f"\n备注：{note}"

    try:
        await context.bot.send_photo(
            chat_id=requester_tg_id,
            photo=best_photo.file_id,
            caption=caption,
        )
    except Exception as e:
        logger.error(f"转发截图至员工失败 tg_id={requester_tg_id}: {e}")
        await msg.reply_text("⚠️ 截图转发失败，请手动联系员工。")
        return

    await msg.reply_text("✅ 截图已收到并转发给员工。")


# ── 导出 ────────────────────────────────────────────────

def get_sms_test_handlers():
    conv = ConversationHandler(
        entry_points=[
            CommandHandler("sms_test", sms_test_start),
            CallbackQueryHandler(sms_test_start_from_menu, pattern=r'^menu_sms_test$'),
        ],
        states={
            SELECT_COUNTRY: [
                CallbackQueryHandler(country_selected, pattern=r'^stest_ctry_|^stest_cancel$'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, country_text_input),
            ],
            SELECT_SUPPLIER: [
                CallbackQueryHandler(supplier_selected,
                                     pattern=r'^stest_sup_|^stest_cancel$|^stest_back_country$'),
            ],
            INPUT_CONTENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, content_input),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", sms_test_cancel),
            CallbackQueryHandler(sms_test_start_from_menu, pattern=r'^menu_sms_test$'),
        ],
        per_user=True,
        allow_reentry=True,
    )
    return [conv]
