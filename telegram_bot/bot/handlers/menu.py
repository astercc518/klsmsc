"""
菜单处理器 - 使用按钮菜单替代命令
"""
import time

from telegram import Message, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from bot.utils import (
    logger,
    edit_and_log,
    send_and_log,
    dedupe_country_codes_from_templates,
    get_group_ids,
)
from bot.services.api_client import APIClient
from datetime import datetime, timedelta, date
import os
import re
import secrets
import html as html_escape
from typing import Any

api = APIClient()

# 已处理的供应商审核回复消息 (chat_id, message_id)，防止重复转发
_processed_sms_reply_ids: set = set()
_MAX_PROCESSED_IDS = 5000

# 「我的客户」分页：单页条数（避免超过 Telegram 4096 字与键盘体积）
_MY_CUSTOMERS_PAGE_SIZE = 20

# 短信审核「等待回复」会话：user_data 在部分客户端/群场景会丢失，用 bot_data 双写备份
SMS_APPROVAL_SESSION_TTL = 3600


def _sms_approval_data_key(user_id: int) -> str:
    return f"sms_approval_session:{user_id}"


def _store_sms_approval_session(
    context: ContextTypes.DEFAULT_TYPE, user_id: int, approval_id: int, approved: bool
) -> None:
    """写入等待回复状态（user_data + bot_data）"""
    context.user_data["waiting_for"] = "sms_approval_reply"
    context.user_data["sms_approval_id"] = approval_id
    context.user_data["sms_approval_approved"] = approved
    context.application.bot_data[_sms_approval_data_key(user_id)] = {
        "approval_id": approval_id,
        "approved": approved,
        "ts": time.time(),
    }


def _clear_sms_approval_session(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    context.user_data.pop("waiting_for", None)
    context.user_data.pop("sms_approval_id", None)
    context.user_data.pop("sms_approval_approved", None)
    context.application.bot_data.pop(_sms_approval_data_key(user_id), None)


def _peek_sms_approval_pending(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    if context.user_data.get("waiting_for") == "sms_approval_reply":
        return True
    key = _sms_approval_data_key(user_id)
    pack = context.application.bot_data.get(key)
    if not pack:
        return False
    if time.time() - pack.get("ts", 0) > SMS_APPROVAL_SESSION_TTL:
        context.application.bot_data.pop(key, None)
        return False
    return True


def _take_sms_approval_session(
    context: ContextTypes.DEFAULT_TYPE, user_id: int
) -> tuple[int | None, bool | None]:
    """取出并清除会话；approved=False 表示拒绝。"""
    ud = context.user_data
    key = _sms_approval_data_key(user_id)
    if ud.get("waiting_for") == "sms_approval_reply":
        a_id = ud.pop("sms_approval_id", None)
        appr = ud.pop("sms_approval_approved", None)
        ud["waiting_for"] = None
        context.application.bot_data.pop(key, None)
        if a_id is not None and appr is not None:
            return a_id, appr
    pack = context.application.bot_data.pop(key, None)
    if not pack:
        return None, None
    if time.time() - pack.get("ts", 0) > SMS_APPROVAL_SESSION_TTL:
        return None, None
    ud["waiting_for"] = None
    return pack["approval_id"], pack["approved"]


# 国家名称映射（避免编码问题，用于报价查询等展示）
COUNTRY_NAMES = {
    'CN': '中国', 'US': '美国', 'GB': '英国', 'SG': '新加坡', 'JP': '日本', 'KR': '韩国',
    'TH': '泰国', 'VN': '越南', 'MY': '马来西亚', 'ID': '印尼', 'PH': '菲律宾', 'IN': '印度',
    'AU': '澳大利亚', 'CA': '加拿大', 'DE': '德国', 'FR': '法国', 'IT': '意大利', 'ES': '西班牙',
    'RU': '俄罗斯', 'BR': '巴西', 'MX': '墨西哥', 'HK': '香港', 'TW': '台湾', 'AE': '阿联酋',
    'SA': '沙特', 'BD': '孟加拉', 'PK': '巴基斯坦', 'EG': '埃及', 'ZA': '南非', 'KE': '肯尼亚',
    'NG': '尼日利亚', 'CL': '智利', 'CO': '哥伦比亚', 'PE': '秘鲁', 'AR': '阿根廷', 'TR': '土耳其',
    'IL': '以色列', 'QA': '卡塔尔', 'KW': '科威特', 'OM': '阿曼', 'BH': '巴林', 'LB': '黎巴嫩',
    'DK': '丹麦', 'SE': '瑞典', 'NO': '挪威', 'FI': '芬兰', 'NL': '荷兰', 'BE': '比利时',
    'CH': '瑞士', 'AT': '奥地利', 'PL': '波兰', 'CZ': '捷克', 'RO': '罗马尼亚', 'HU': '匈牙利',
    'GR': '希腊', 'PT': '葡萄牙', 'IE': '爱尔兰', 'NZ': '新西兰', 'VE': '委内瑞拉', 'EC': '厄瓜多尔',
    'BO': '玻利维亚', 'KH': '柬埔寨', 'LA': '老挝', 'MM': '缅甸', 'BN': '文莱', 'LK': '斯里兰卡',
    'KZ': '哈萨克斯坦', 'LT': '立陶宛', 'GH': '加纳', 'MA': '摩洛哥', 'DZ': '阿尔及利亚',
    'TN': '突尼斯', 'UG': '乌干达', 'TZ': '坦桑尼亚', 'ET': '埃塞俄比亚', 'SN': '塞内加尔',
    'CM': '喀麦隆', 'CI': '科特迪瓦', 'ZM': '赞比亚', 'JO': '约旦',
    'BJ': '贝宁',
}

# 反向映射：国家名称 → 国家代码
NAME_TO_COUNTRY = {name: code for code, name in COUNTRY_NAMES.items()}


# ============ 主菜单 ============

def get_main_menu_customer():
    """客户主菜单"""
    keyboard = [
        [
            InlineKeyboardButton("📱 发送短信", callback_data="menu_send_sms"),
            InlineKeyboardButton("📝 短信审核", callback_data="menu_sms_audit"),
        ],
        [
            InlineKeyboardButton("📊 发送记录", callback_data="menu_history"),
            InlineKeyboardButton("💬 问题反馈", callback_data="ticket_type_feedback"),
        ],
        [
            InlineKeyboardButton("📊 数据业务", callback_data="kb_cat_data"),
            InlineKeyboardButton("📞 语音业务", callback_data="kb_cat_voice"),
        ],
        [
            InlineKeyboardButton("💳 申请充值", callback_data="menu_recharge"),
            InlineKeyboardButton("👤 账户信息", callback_data="menu_account_info"),
        ],
        [
            InlineKeyboardButton("❓ 帮助", callback_data="menu_help"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_main_menu_sales():
    """销售主菜单"""
    keyboard = [
        [
            InlineKeyboardButton("🎯 创建开户邀请", callback_data="menu_invite"),
        ],
        [
            InlineKeyboardButton("👥 我的客户", callback_data="menu_my_customers"),
            InlineKeyboardButton("📋 业务工单", callback_data="menu_biz_tickets"),
        ],
        [
            InlineKeyboardButton("📊 业绩统计", callback_data="menu_sales_stats"),
            InlineKeyboardButton("📚 业务知识", callback_data="menu_business_knowledge"),
        ],
        [
            InlineKeyboardButton("📋 报价查询", callback_data="menu_pricing"),
            InlineKeyboardButton("❓ 帮助", callback_data="menu_help"),
        ],
        [
            InlineKeyboardButton("📱 短信落地测试", callback_data="menu_sms_test"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_main_menu_tech():
    """技术/管理员主菜单"""
    keyboard = [
        [
            InlineKeyboardButton("📋 待审核工单", callback_data="menu_pending_tickets"),
            InlineKeyboardButton("💳 待审核充值", callback_data="menu_pending_recharge"),
        ],
        [
            InlineKeyboardButton("📊 系统统计", callback_data="menu_system_stats"),
            InlineKeyboardButton("👥 用户管理", callback_data="menu_user_manage"),
        ],
        [
            InlineKeyboardButton("🎯 创建邀请", callback_data="menu_invite"),
            InlineKeyboardButton("📋 报价查询", callback_data="menu_pricing"),
            InlineKeyboardButton("❓ 帮助", callback_data="menu_help"),
        ],
        [
            InlineKeyboardButton("📱 短信落地测试", callback_data="menu_sms_test"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


async def get_main_menu_guest():
    """游客菜单 — 授权码开户为主入口；「联系客服」用回调拉轮询链接，避免部分客户端 inline url 无反应"""
    keyboard = [
        [
            InlineKeyboardButton("🔑 输入授权码开户", callback_data="menu_enter_invite"),
        ],
        [
            InlineKeyboardButton("🔗 绑定已有账户", callback_data="menu_bind_account"),
            InlineKeyboardButton("👔 员工绑定", callback_data="menu_bind_staff"),
        ],
        [
            InlineKeyboardButton("❓ 帮助", callback_data="menu_help"),
            InlineKeyboardButton("💬 联系客服", callback_data="menu_guest_contact_cs"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def _get_biz_ticket_top_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 短信工单", callback_data="btk_sms"),
         InlineKeyboardButton("📞 语音工单", callback_data="btk_voice")],
        [InlineKeyboardButton("📊 数据工单", callback_data="btk_data")],
        [InlineKeyboardButton("📂 我的业务工单", callback_data="bizt_my")],
        [InlineKeyboardButton("🔙 返回", callback_data="menu_main")],
    ])


def _get_biz_ticket_category_keyboard(biz_type: str) -> InlineKeyboardMarkup:
    opts = {
        'sms':   ('🏢 短信开户', '🧪 短信测试', '💬 发送反馈'),
        'voice': ('🏢 语音开户', '🧪 语音测试', '📞 通话反馈'),
        'data':  ('🏢 数据开户', '🧪 数据测试', '📊 效果反馈'),
    }
    names = opts.get(biz_type, ('开户', '测试', '反馈'))
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(names[0], callback_data=f"btk_{biz_type}_register")],
        [InlineKeyboardButton(names[1], callback_data=f"btk_{biz_type}_test")],
        [InlineKeyboardButton(names[2], callback_data=f"btk_{biz_type}_feedback")],
        [InlineKeyboardButton("⬅️ 返回", callback_data="menu_biz_tickets"),
         InlineKeyboardButton("🏠 主菜单", callback_data="menu_main")],
    ])


def get_ticket_type_menu():
    """工单类型菜单"""
    keyboard = [
        [
            InlineKeyboardButton("📝 测试申请", callback_data="ticket_type_test"),
            InlineKeyboardButton("🔧 技术支持", callback_data="ticket_type_technical"),
        ],
        [
            InlineKeyboardButton("💳 账务问题", callback_data="ticket_type_billing"),
            InlineKeyboardButton("💬 意见反馈", callback_data="ticket_type_feedback"),
        ],
        [
            InlineKeyboardButton("🔙 返回主菜单", callback_data="menu_main"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_business_type_menu():
    """业务类型菜单（用于邀请）"""
    keyboard = [
        [
            InlineKeyboardButton("📱 短信 SMS", callback_data="biz_sms"),
            InlineKeyboardButton("📞 语音 Voice", callback_data="biz_voice"),
        ],
        [
            InlineKeyboardButton("📊 数据 Data", callback_data="biz_data"),
        ],
        [
            InlineKeyboardButton("❌ 取消", callback_data="menu_main"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_back_menu():
    """返回菜单"""
    keyboard = [
        [InlineKeyboardButton("🔙 返回主菜单", callback_data="menu_main")],
    ]
    return InlineKeyboardMarkup(keyboard)



async def show_pricing_all(query, context):
    """显示我的资费详情"""
    tg_id = query.from_user.id
    client = APIClient()
    user_info = await client.verify_bot_user(tg_id)
    # verify-user 客户为 account_id / account.id，无顶层 id
    acc_id = user_info.get("account_id") or (user_info.get("account") or {}).get("id")
    if not user_info or user_info.get("role") != "customer" or not acc_id:
        await query.edit_message_text("❌ 无效绑定的账户", reply_markup=get_back_menu())
        return
    res = await client.get_account_pricing(acc_id)
    if not res.get("success"):
        await query.edit_message_text(f"❌ {res.get('msg', '获取资费失败')}", reply_markup=get_back_menu())
        return
    
    pricing = res.get("pricing", [])
    if not pricing:
        await query.edit_message_text("💰 资费详情\n\n暂无资费信息。", reply_markup=get_back_menu())
        return
    
    lines = ["💰 <b>资费详情</b>\n"]
    for p in pricing:
        def_mark = " (默认)" if p.get("is_default") else ""
        lines.append(f"• {p.get('channel_name')}: ${p.get('unit_price'):.4f}/条{def_mark}")
    
    await query.edit_message_text("\n".join(lines), reply_markup=get_back_menu(), parse_mode='HTML')


async def _notify_customer_approved(context, approval):
    """通知客户短信审核通过"""
    acc_id = approval.get("account_id")
    client = APIClient()
    res = await client.get_account_bindings(acc_id)
    if res.get("success"):
        for b in res.get("bindings", []):
            try:
                await context.bot.send_message(
                    chat_id=b["tg_id"],
                    text=f"✅您的短信审核已通过！\n\n内容: {approval.get('content')}\n\n您可以点击底部菜单「立即发送」开始发送任务。"
                )
            except Exception as e:
                logger.error(f"通知客户失败: {e}")


async def _notify_customer_rejected(context, approval):
    """通知客户短信审核拒绝"""
    acc_id = approval.get("account_id")
    client = APIClient()
    res = await client.get_account_bindings(acc_id)
    if res.get("success"):
        for b in res.get("bindings", []):
            try:
                await context.bot.send_message(
                    chat_id=b["tg_id"],
                    text=f"❌您的短信审核被拒绝。\n\n内容: {approval.get('content')}\n\n如有疑问请联系客服。"
                )
            except Exception as e:
                logger.error(f"通知客户失败: {e}")


# ============ 菜单处理 ============

async def handle_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理菜单回调"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = update.effective_user
    tg_id = user.id
    
    logger.info(f"Menu callback: {data} from user {tg_id}")

    # 销售：快捷登录名下客户（网页模拟登录）
    if data.startswith("sales_login_"):
        await handle_sales_quick_login(query, context)
        return

    # OKCC 刷新余额
    if data.startswith("okcc_refresh_"):
        await handle_okcc_refresh(query, context)
        return
    
    # 返回主菜单（清除待填号码等状态）
    if data == "menu_main":
        context.user_data.pop('pending_approval_id', None)
        context.user_data.pop('waiting_for', None)
        await show_main_menu(query, context)
        return
    
    # 帮助
    if data == "menu_help":
        await show_help(query, context)
        return

    # 游客户服：已在上方 answer；此处勿重复 answer
    if data == "menu_guest_contact_cs":
        client = APIClient()
        info = await client.get_next_guest_cs_staff_bundle()
        cs_url = (info.get("url") or "").strip()
        bot_u = (os.getenv("TELEGRAM_BOT_USERNAME") or "kaolachbot").strip().lstrip("@")
        if not cs_url.startswith("https://"):
            cs_url = f"https://t.me/{bot_u}" if bot_u else "https://t.me/kaolachbot"

        src = info.get("source")
        if src == "staff":
            head = "💬 已按轮询为您分配当班客服，请打开 Telegram 私信："
        elif src == "fallback":
            hint = info.get("hint_zh") or ""
            head = (
                "⚠️ 未从公司员工中分配到带 Telegram 用户名的坐席，无法直接打开人工私信。\n"
                f"{hint}\n"
            )
            if bot_u and bot_u.lower() in cs_url.lower():
                head += "\n当前链接指向本业务 Bot，无法替代真人客服；请管理员在后台为员工填写 tg_username，或在服务器环境变量 TELEGRAM_CS_FALLBACK_URL 中填写销售个人 t.me 链接。\n"
        else:
            head = (info.get("hint_zh") or "暂时无法获取客服链接。") + "\n"

        await query.message.reply_text(
            f"{head}\n{cs_url}",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("➡️ 打开客服对话", url=cs_url)]]
            ),
        )
        return

    # 查询余额
    if data == "menu_balance":
        await show_balance(query, context)
        return
    
    # 申请充值
    if data == "menu_recharge":
        await start_recharge(query, context)
        return
    
    # 发送短信（直接发送，或根据配置走审核）
    if data == "menu_send_sms":
        context.user_data['sms_submit_mode'] = 'direct'
        await edit_and_log(
            query,
            "📱 发送短信\n\n"
            "请发送：**号码 内容**（号码与内容用空格或换行分隔）\n\n"
            "号码需以 + 开头的 E.164 格式，例如：\n"
            "`+8613800138000 您的验证码是123456`",
            parse_mode='Markdown',
            reply_markup=get_back_menu()
        )
        context.user_data['waiting_for'] = 'sms_content'
        return
    
    # 短信审核（只审核文案，不要求号码）
    if data == "menu_sms_audit":
        context.user_data['sms_submit_mode'] = 'audit'
        await edit_and_log(
            query,
            "📝 短信审核\n\n"
            "请直接发送需审核的**文案内容**（无需号码）\n\n"
            "例如：\n"
            "`ลงทะเบียนเพื่อรับโบนัสปี 1995 ที่สามารถถอนได้ shorturl.asia/NACBZ`\n\n"
            "或：\n"
            "`您的验证码是123456，5分钟内有效`",
            parse_mode='Markdown',
            reply_markup=get_back_menu()
        )
        context.user_data['waiting_for'] = 'sms_audit_content'
        return
    
    # 发送语音
    if data == "menu_send_voice":
        await query.edit_message_text(
            "📞 发送语音\n\n"
            "请直接发送以下格式的消息：\n"
            "`号码 语音内容`\n\n"
            "例如：\n"
            "`+8613800138000 您有一个新订单请注意查收`",
            parse_mode='Markdown',
            reply_markup=get_back_menu()
        )
        context.user_data['waiting_for'] = 'voice_content'
        return
    
    # 发送记录
    if data == "menu_history":
        await show_history(query, context)
        return
    
    # 工单列表
    if data == "menu_tickets":
        await show_tickets(query, context)
        return
    
    # 新建工单
    if data == "menu_new_ticket":
        await query.edit_message_text(
            "📝 提交工单\n\n请选择工单类型：",
            reply_markup=get_ticket_type_menu()
        )
        return
    
    # 语音/数据开户
    if data in ("menu_open_voice", "menu_open_data"):
        from bot.handlers.account_opening import opening_start
        biz = data.replace("menu_open_", "")
        await opening_start(update, context, biz_type=biz)
        return

    # 创建邀请 - 转到sales模块的邀请流程
    if data == "menu_invite":
        # 检查是否是销售
        client = APIClient()
        user_info = await client.verify_user(tg_id)
        
        if not user_info or not user_info.get("is_admin") or user_info.get("role") not in ['sales', 'super_admin', 'admin']:
            await query.edit_message_text(
                "❌ 您没有创建邀请的权限",
                reply_markup=get_back_menu()
            )
            return
        
        context.user_data['sales_id'] = user_info.get("user_id")
        context.user_data['sales_name'] = user_info.get("real_name")
        
        await query.edit_message_text(
            "🎯 创建开户邀请\n\n请选择业务类型：",
            reply_markup=get_business_type_menu()
        )
        return
    
    # 处理业务类型选择（邀请流程）
    if data.startswith("biz_"):
        biz_type = data.replace("biz_", "")

        # 语音/数据 → 走开户订单流程（发技术群+建工单）
        if biz_type in ("voice", "data"):
            from bot.handlers.account_opening import opening_start
            await opening_start(update, context, biz_type=biz_type)
            return

        # 短信 → 继续走邀请码流程
        context.user_data['business_type'] = biz_type
        
        biz_label = {"sms": "短信", "voice": "语音", "data": "数据"}.get(biz_type, biz_type)
        
        # 获取该业务类型下的所有国家
        client = APIClient()
        templates = await client.get_templates_internal(biz_type=biz_type)
        raw_codes = [t.get("country_code") for t in templates]
        country_codes = dedupe_country_codes_from_templates(raw_codes)
        
        if not country_codes:
            await query.edit_message_text(
                f"❌ 暂无 {biz_label} 业务的可用模板\n\n请联系管理员在后台添加账户模板",
                reply_markup=get_back_menu()
            )
            return
        
        # 显示国家选择（全球 * 置顶）
        keyboard = []
        has_global = '*' in country_codes
        if has_global:
            keyboard.append([InlineKeyboardButton("🌍 全球（所有国家）", callback_data="country_*")])
        row = []
        for country_code in country_codes:
            if country_code == '*':
                continue
            label = COUNTRY_NAMES.get(country_code, country_code)
            row.append(InlineKeyboardButton(label, callback_data=f"country_{country_code}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("🔙 返回", callback_data="menu_invite")])
        
        await query.edit_message_text(
            f"🎯 创建开户邀请\n\n"
            f"业务类型: {biz_label}\n\n"
            f"请选择国家/地区：",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # 我的客户（分类概览或全部）
    if data == "menu_my_customers":
        await show_my_customers(query, context)
        return

    # 按业务类型查看客户（支持分页：my_cust_voice、my_cust_voice_p1）
    if data.startswith("my_cust_"):
        m = re.match(r"^my_cust_(sms|voice|data|all)(?:_p(\d+))?$", data)
        if m:
            await show_my_customers(
                query, context, biz_filter=m.group(1), page=int(m.group(2) or 0)
            )
        return
    
    # 业务知识
    if data == "menu_business_knowledge":
        await show_business_knowledge(query, context, category=None)
        return
    if data.startswith("kb_cat_"):
        cat = data.replace("kb_cat_", "")
        await show_business_knowledge(query, context, category=cat)
        return
    if data.startswith("kb_article_"):
        article_id = int(data.replace("kb_article_", ""))
        await show_knowledge_article(query, context, article_id)
        return
    if data.startswith("kb_dl_"):
        att_id = int(data.replace("kb_dl_", ""))
        await send_knowledge_attachment(query, context, att_id)
        return
    if data == "kb_noop":
        return
    
    # 游客输入授权码开户
    if data == "menu_enter_invite":
        await query.edit_message_text(
            "🔑 *授权码开户*\n\n"
            "请输入销售提供的授权码（8位字母数字）：\n\n"
            "例如：`K2THWKBO`",
            parse_mode='Markdown',
            reply_markup=get_back_menu()
        )
        context.user_data['waiting_for'] = 'invite_code'
        return
    
    # 客户绑定已有账户
    if data == "menu_bind_account":
        await query.edit_message_text(
            "🔗 绑定已有账户\n\n"
            "请按照以下步骤操作：\n"
            "1. 登录网页端【账户设置】\n"
            "2. 点击【生成绑定码】\n"
            "3. 在此输入6位绑定码\n\n"
            "请输入绑定码：",
            reply_markup=get_back_menu()
        )
        context.user_data['waiting_for'] = 'account_bind_code'
        return

    # 账户信息
    if data == "menu_account_info":
        await show_account_info(query, context)
        return

    # 员工绑定
    if data == "menu_bind_staff":
        await query.edit_message_text(
            "👔 绑定员工账号\n\n"
            "请发送您的账号和密码，格式：\n"
            "`用户名 密码`\n\n"
            "例如：\n"
            "`KL01 mypassword`",
            parse_mode='Markdown',
            reply_markup=get_back_menu()
        )
        context.user_data['waiting_for'] = 'staff_credentials'
        return
    
    # 待审核工单
    if data == "menu_pending_tickets":
        await show_pending_tickets(query, context)
        return
    
    # 待审核充值
    if data == "menu_pending_recharge":
        await show_pending_recharge(query, context)
        return
    
    # 报价查询（销售/技术）
    if data == "menu_pricing":
        await show_pricing_menu(query, context, tg_id)
        return
    
    # 报价查询 - 按业务类型选国家
    if data.startswith("pricing_biz_"):
        rest = data.replace("pricing_biz_", "")
        if rest in ("sms", "voice", "data"):
            await show_pricing_country_by_biz(query, context, rest)
        elif rest.startswith("country_"):
            # pricing_biz_country_sms_CN 格式
            sub = rest.replace("country_", "", 1)
            if "_" in sub:
                biz_type, country_code = sub.split("_", 1)
                await show_pricing_by_biz_country(query, context, biz_type, country_code)
        return
    
    # 报价查询 - 查看全部
    if data == "pricing_all":
        await show_pricing_all(query, context)
        return
    
    # 处理国家选择（邀请流程，支持 * = 全球）
    if data.startswith("country_"):
        country_code = data.replace("country_", "").strip()
        if country_code != '*':
            country_code = country_code.upper()
        context.user_data['country_code'] = country_code
        biz_type = context.user_data.get('business_type', 'sms')
        
        biz_label = {"sms": "短信", "voice": "语音", "data": "数据"}.get(biz_type, biz_type)
        
        # 获取该国家的模板（* 代表全球通配）
        client = APIClient()
        all_templates = await client.get_templates_internal(biz_type=biz_type, country_code=country_code)
        # 过滤 active（列表接口与详情字段名见 internal_bot /templates）
        templates = [
            t for t in all_templates
            if isinstance(t, dict) and (t.get("status") == "active" or t.get("status") is None)
        ]

        if not templates:
            await query.edit_message_text(
                f"❌ 该国家暂无可用模板",
                reply_markup=get_back_menu()
            )
            return

        keyboard = []
        for tpl in templates:
            tname = (tpl.get("template_name") or tpl.get("name") or "").strip() or "未命名模板"
            raw_price = tpl.get("default_price") if tpl.get("default_price") is not None else tpl.get("price", 0)
            try:
                price = float(raw_price or 0)
            except (TypeError, ValueError):
                price = 0.0
            tid = tpl.get("id")
            if tid is None:
                continue
            label = f"{tname}  ${price:.4f}"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"tpl_{tid}")])
        keyboard.append([InlineKeyboardButton("🔙 返回", callback_data=f"biz_{biz_type}")])

        country_label = '全球（所有国家）' if country_code == '*' else COUNTRY_NAMES.get(country_code, country_code)
        await query.edit_message_text(
            f"🎯 创建开户授权码\n\n"
            f"📦 业务类型: {biz_label}\n"
            f"🌍 国家: {country_label}\n\n"
            f"请选择开户模板：",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # 处理模板选择（邀请流程；须与 country_ 同级，此前误写在 country_ 内 return 之后导致永不可达）
    if data.startswith("tpl_"):
        try:
            template_id = int(data.replace("tpl_", "").strip())
        except ValueError:
            await query.edit_message_text("❌ 无效的模板选项", reply_markup=get_back_menu())
            return
        context.user_data["template_id"] = template_id

        client = APIClient()
        template = await client.get_template_internal(template_id)

        # 详情接口失败时，用当前国家下的模板列表回退（与列表字段 name/price 一致）
        if not template or not template.get("id"):
            biz_type = context.user_data.get("business_type", "sms")
            cc = context.user_data.get("country_code")
            lst = await client.get_templates_internal(biz_type=biz_type, country_code=cc)
            tpl_row = next(
                (t for t in (lst or []) if isinstance(t, dict) and int(t.get("id") or 0) == template_id),
                None,
            )
            if tpl_row:
                try:
                    raw_p = tpl_row.get("default_price") if tpl_row.get("default_price") is not None else tpl_row.get("price", 0)
                    price_fb = float(raw_p or 0)
                except (TypeError, ValueError):
                    price_fb = 0.0
                template = {
                    "id": tpl_row.get("id"),
                    "template_name": tpl_row.get("template_name") or tpl_row.get("name"),
                    "country_code": tpl_row.get("country_code"),
                    "default_price": price_fb,
                }

        if not template or not template.get("id"):
            await query.edit_message_text(
                "❌ 模板不存在或暂时无法拉取详情，请返回上一步重新选择，或联系管理员检查模板 ID 与 internal API。",
                reply_markup=get_back_menu(),
            )
            return

        country_code = template.get("country_code")
        template_name = template.get("template_name") or template.get("name")
        raw_price = template.get("default_price")
        if raw_price is None:
            raw_price = template.get("price", 0)
        try:
            price = float(raw_price or 0)
        except (TypeError, ValueError):
            price = 0.0

        country_label = "全球（所有国家）" if country_code == "*" else COUNTRY_NAMES.get(country_code, country_code)
        template_name = (template_name or "").strip() or f"{country_label}标准版"

        context.user_data["template_info"] = {
            "name": template_name,
            "default_price": price,
            "country": country_code,
        }
        context.user_data["template_name"] = template_name

        if country_code == "*":
            await query.edit_message_text(
                f"🎯 创建开户授权码\n\n"
                f"📋 模板: {template_name}\n"
                f"💰 底价: ${price:.4f}\n\n"
                f"请输入 <b>国家名称</b> 和 <b>客户单价（USD）</b>，用空格分隔：\n"
                f"例如: <code>中国 0.05</code>  或  <code>美国 0</code>\n\n"
                f"输入 0 表示免费",
                reply_markup=get_back_menu(),
                parse_mode="HTML",
            )
            context.user_data["waiting_for"] = "invite_country_price"
            return

        await query.edit_message_text(
            f"🎯 创建开户授权码\n\n"
            f"📋 模板: {template_name}\n"
            f"🌍 国家: {country_label}\n"
            f"💰 底价: ${price:.4f}\n\n"
            f"请输入客户单价（USD），输入 0 表示免费：\n"
            f"例如: 0.05",
            reply_markup=get_back_menu()
        )
        context.user_data["waiting_for"] = "invite_price"
        return

    # 短信内容审核 - 通过
    if data.startswith("approve_sms_"):
        approval_id = int(data.replace("approve_sms_", ""))
        await handle_sms_approval_callback(query, context, approval_id, True)
        return

    # 短信内容审核 - 拒绝
    if data.startswith("reject_sms_"):
        approval_id = int(data.replace("reject_sms_", ""))
        await handle_sms_approval_callback(query, context, approval_id, False)
        return

    # 短信审核回复 - 跳过
    if data.startswith("sms_approval_skip_"):
        parts = data.replace("sms_approval_skip_", "").split("_")
        if len(parts) >= 2:
            approval_id = int(parts[0])
            approved = parts[1] == "1"
            _clear_sms_approval_session(context, query.from_user.id)
            
            client = APIClient()
            # 获取详情
            approval = await client.get_sms_approval_internal(approval_id)
            if approval and approval.get("id"):
                if approved:
                    await _notify_customer_approved(context, approval)
                else:
                    await _notify_customer_rejected(context, approval)
            
            if query.message:
                await query.message.reply_text("✅ 已跳过，已通知客户")
        return

    # 客户点击「立即发送」执行审核通过的短信
    if data.startswith("send_approved_sms_"):
        approval_id = int(data.replace("send_approved_sms_", ""))
        await execute_approved_sms(query, context, approval_id)
        return

    # 审批充值 - 通过
    if data.startswith("approve_recharge_"):
        order_id = int(data.replace("approve_recharge_", ""))
        await approve_recharge(query, context, order_id, True)
        return
    
    # 审批充值 - 拒绝
    if data.startswith("reject_recharge_"):
        order_id = int(data.replace("reject_recharge_", ""))
        await approve_recharge(query, context, order_id, False)
        return
    
    # 处理工单
    if data.startswith("process_ticket_"):
        ticket_id = int(data.replace("process_ticket_", ""))
        await show_ticket_detail(query, context, ticket_id, is_admin=True)
        return
    
    # 查看工单详情
    if data.startswith("ticket_detail_"):
        ticket_id = int(data.replace("ticket_detail_", ""))
        await show_ticket_detail(query, context, ticket_id, is_admin=False)
        return
    
    # 关闭工单
    if data.startswith("close_ticket_"):
        ticket_id = int(data.replace("close_ticket_", ""))
        await close_ticket(query, context, ticket_id)
        return
    
    # 系统统计
    if data == "menu_system_stats":
        await show_system_stats(query, context)
        return
    
    # 销售业绩统计
    if data == "menu_sales_stats":
        await show_sales_stats(query, context)
        return
    
    # 客户工单（旧入口，保留兼容）
    if data == "menu_customer_tickets":
        await show_customer_tickets(query, context)
        return

    # 业务工单顶层菜单
    if data == "menu_biz_tickets":
        await query.edit_message_text(
            "📋 业务工单\n\n请选择工单类型：",
            reply_markup=_get_biz_ticket_top_keyboard()
        )
        return

    # 业务工单类别选择
    if data in ("btk_sms", "btk_voice", "btk_data"):
        biz = data[4:]
        biz_label = {"sms": "短信", "voice": "语音", "data": "数据"}[biz]
        await query.edit_message_text(
            f"📋 {biz_label}工单\n\n请选择工单类别：",
            reply_markup=_get_biz_ticket_category_keyboard(biz)
        )
        return

    # 业务工单具体操作入口（btk_*_register/test/feedback）由 biz_ticket.py 的 ConversationHandler 接管

    # 工单类型选择后创建工单
    if data.startswith("ticket_type_"):
        ticket_type = data.replace("ticket_type_", "")
        context.user_data['ticket_type'] = ticket_type
        
        type_labels = {
            'test': '测试申请',
            'technical': '技术支持',
            'billing': '账务问题',
            'feedback': '意见反馈'
        }
        
        await query.edit_message_text(
            f"📝 提交工单 - {type_labels.get(ticket_type, ticket_type)}\n\n"
            f"请输入工单标题：",
            reply_markup=get_back_menu()
        )
        context.user_data['waiting_for'] = 'ticket_title'
        return


async def show_account_info(query, context):
    """显示客户账户信息"""
    tg_id = query.from_user.id

    client = APIClient()
    user_info = await client.verify_user(tg_id)

    if not user_info or not user_info.get("valid") or user_info.get("role") != "customer":
        await edit_and_log(
            query,
            "❌ 未绑定有效账户或该账户已停用/删除，请使用授权码开户或重新绑定。",
            reply_markup=get_back_menu()
        )
        return

    account_id = user_info.get("account_id")
    account_name = user_info.get("account_name")
    balance = user_info.get("balance", 0)
    currency = user_info.get("currency", "USD")
    status = user_info.get("status", "active")
    tg_username = user_info.get("tg_username")
    created_at_str = user_info.get("created_at")

    tg_bound = "已绑定" if user_info.get("tg_id") else "未绑定"
    tg_info = f"@{tg_username}" if tg_username else str(user_info.get("tg_id") or "-")

    await query.edit_message_text(
        f"👤 账户信息\n\n"
        f"🆔 账户ID: {account_id}\n"
        f"👤 用户名: {account_name}\n"
        f"💰 余额: ${float(balance):.4f} {currency}\n"
        f"📊 状态: {'正常' if status == 'active' else status}\n"
        f"📱 Telegram: {tg_bound} ({tg_info})\n"
        f"📅 创建时间: {created_at_str[:10] if created_at_str else 'N/A'}",
        reply_markup=get_back_menu()
    )


async def show_main_menu(query, context: ContextTypes.DEFAULT_TYPE):
    """显示主菜单 (通过 API)"""
    tg_id = query.from_user.id
    client = APIClient()
    
    # 获取用户身份（销售主菜单不再内嵌本月业绩，见「业绩统计」）
    user_info = await client.verify_bot_user(tg_id, include_monthly_performance=False)
    if not user_info:
        context.user_data.pop("account_id", None)
        context.user_data.pop("user_type", None)
        await query.edit_message_text(
            "👋 欢迎使用 TG 业务助手\n\n"
            "您的账户未绑定或已停用，请使用授权码开户或重新绑定。\n\n"
            "客服: 请使用主菜单「联系客服」或官网 https://www.kaolach.com/",
            reply_markup=get_back_menu()
        )
        return

    role = user_info.get("role")
    real_name = user_info.get("real_name") or user_info.get("username") or "用户"
    
    # 1. 处理员工 (Admin/Sales/...)
    if user_info.get("is_admin"):
        role_map = {
            'super_admin': '超级管理员',
            'admin': '管理员', 
            'sales': '销售',
            'finance': '财务',
            'tech': '技术'
        }
        role_label = role_map.get(role, role)
        
        if role in ['super_admin', 'admin', 'tech']:
            menu = get_main_menu_tech()
            msg = f"👋 {real_name}\n🔐 {role_label}\n\n请选择操作："
        else:
            menu = get_main_menu_sales()
            # 主菜单不展示本月业绩/佣金，避免首屏拉数；详情见「📊 业绩统计」
            msg = (
                f"👋 姓名: {real_name}\n"
                f"🔐 角色: {role_label}\n\n"
                f"请选择操作：\n\n"
                f"📈 本月业绩与佣金请点下方「📊 业绩统计」查看。\n\n"
                f"📢 全行业短信群发，AI语音，渗透数据！\n"
                f"所有信息以官网 https://www.kaolach.com/ 展示为准！"
            )
        await edit_and_log(query, msg, reply_markup=menu)
        return
        
    # 2. 处理客户
    if role == "customer":
        balance = user_info.get("balance", 0.0)
        account_id = user_info.get("account_id")
        context.user_data["account_id"] = account_id
        context.user_data["user_type"] = "customer"
        
        await query.edit_message_text(
            f"👋 欢迎回来\n"
            f"💰 余额: ${balance:.2f}\n\n"
            f"📢 全行业短信群发，AI语音，渗透数据！\n"
            f"官网: https://www.kaolach.com/\n\n"
            f"请选择操作：",
            reply_markup=get_main_menu_customer()
        )
        return

    # 3. 其他 (未授权)
    else:
        await query.edit_message_text(
            "👋 欢迎使用 TG 业务助手\n\n"
            "您的账户状态异常或已停用，请使用授权码开户或重新绑定。\n\n"
            "请选择操作：",
            reply_markup=await get_main_menu_guest()
        )


async def show_help(query, context):
    """显示帮助"""
    help_text = """
❓ 帮助信息

📱 短信业务 - 发送国际短信
📞 语音业务 - 发送语音通知
📊 数据业务 - 数据查询服务

💰 充值流程:
1. 点击"申请充值"
2. 输入金额并上传凭证
3. 等待财务审核
4. 到账后收到通知

📋 工单流程:
1. 点击"提交工单"
2. 选择类型并描述问题
3. 等待处理
4. 收到回复通知

如有问题请提交工单联系客服
"""
    await query.edit_message_text(help_text, reply_markup=get_back_menu())


async def show_balance(query, context: ContextTypes.DEFAULT_TYPE):
    """显示余额 (通过 API)"""
    tg_id = query.from_user.id
    client = APIClient()
    
    res = await client.get_customer_balance(tg_id)
    if not res.get("success"):
        await query.edit_message_text(
            f"❌ {res.get('msg', '获取余额失败')}",
            reply_markup=get_back_menu()
        )
        return

    await query.edit_message_text(
        f"💰 账户余额\n\n"
        f"账户: {res.get('account_name')}\n"
        f"余额: ${res.get('balance'):.4f} {res.get('currency')}\n"
        f"状态: {'正常' if res.get('status') == 'active' else '已冻结'}",
        reply_markup=get_back_menu()
    )


async def start_recharge(query, context):
    """开始充值"""
    await query.edit_message_text(
        "💳 申请充值\n\n"
        "请发送充值金额（美元）：\n"
        "例如: `100` 或 `50.5`",
        parse_mode='Markdown',
        reply_markup=get_back_menu()
    )
    context.user_data['waiting_for'] = 'recharge_amount'


async def show_history(query, context):
    """显示发送记录 (通过 API)"""
    tg_id = query.from_user.id
    client = APIClient()
    
    res = await client.get_customer_sms_stats(tg_id)
    if not res.get("success"):
        await query.edit_message_text(
            f"❌ {res.get('msg', '获取统计失败')}",
            reply_markup=get_back_menu()
        )
        return

    total = res.get("total", 0)
    success = res.get("success_count", 0)
    failed = res.get("failed_count", 0)
    cost = res.get("total_cost", 0.0)
    success_rate = (success / total * 100) if total > 0 else 0
    
    await query.edit_message_text(
        f"📊 发送统计 (近7天)\n\n"
        f"📤 总发送: {total} 条\n"
        f"✅ 成功: {success} 条\n"
        f"❌ 失败: {failed} 条\n"
        f"📈 成功率: {success_rate:.1f}%\n"
        f"💰 消费: ${cost:.4f}\n\n"
        f"更多详情请登录Web后台查看",
        reply_markup=get_back_menu()
    )


async def show_tickets(query, context: ContextTypes.DEFAULT_TYPE):
    """显示工单列表 (通过 API)"""
    tg_id = query.from_user.id
    client = APIClient()
    
    # 首先验证用户并获取 account_id
    user_info = await client.verify_bot_user(tg_id)
    if not user_info or user_info.get("role") != "customer":
        await query.edit_message_text(
            "❌ 未绑定有效账户或该账户已停用/删除。",
            reply_markup=get_back_menu()
        )
        return
        
    account_id = user_info.get("account_id")
    res = await client.get_bot_tickets(account_id=account_id)
    if not res.get("success"):
        await query.edit_message_text(
            "📋 我的工单\n\n暂无工单记录",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 提交工单", callback_data="menu_new_ticket")],
                [InlineKeyboardButton("🔙 返回主菜单", callback_data="menu_main")]
            ])
        )
        return

    tickets = res.get("tickets", [])
    if not tickets:
        await query.edit_message_text(
            "📋 我的工单\n\n暂无工单记录",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 提交工单", callback_data="menu_new_ticket")],
                [InlineKeyboardButton("🔙 返回主菜单", callback_data="menu_main")]
            ])
        )
        return
        
    status_map = {
        'open': '⏳待处理',
        'assigned': '👤已分配',
        'in_progress': '🔄处理中',
        'pending_user': '⏸️等待回复',
        'resolved': '✅已解决',
        'closed': '🔒已关闭',
        'cancelled': '❌已取消'
    }
    
    lines = ["📋 我的工单 (最近5条)\n"]
    keyboard = []
    for t in tickets[:5]:
        status_label = status_map.get(t.get("status"), t.get("status"))
        lines.append(f"• {t.get('ticket_no')}: {t.get('title')[:15]}... {status_label}")
        keyboard.append([InlineKeyboardButton(
            f"📄 {t.get('ticket_no')}", 
            callback_data=f"ticket_detail_{t.get('id')}"
        )])
        
    keyboard.append([InlineKeyboardButton("📝 提交新工单", callback_data="menu_new_ticket")])
    keyboard.append([InlineKeyboardButton("🔙 返回主菜单", callback_data="menu_main")])
    
    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# OKCC 对外 PHP 接口（与后台 admin.py 配置一致）
_OKCC_APIS = {
    "lcchcc": "https://www.lcchcc.com/smsc_api.php",
    "klchcc": "https://www.klchcc.com/smsc_api.php",
}
_OKCC_API_KEY = "smsc_okcc_sync_8f3a2d1e"


# sync_okcc_balance_to_db has been moved to Backend API.


async def handle_okcc_refresh(query, context):
    """用户点击「刷新余额」：强制再拉一次 OKCC 并刷新展示 (API)"""
    raw = query.data or ""
    try:
        account_id = int(raw.replace("okcc_refresh_", ""))
    except ValueError:
        return

    client = APIClient()
    res = await client.sync_okcc_balance(account_id)
    
    await handle_sales_quick_login(query, context, override_account_id=account_id, skip_okcc_sync=True)
    if not res.get("success") and query.message:
        await query.message.reply_text(f"⚠️ 未能从 OKCC 更新余额: {res.get('msg')}")


async def handle_sales_quick_login(query, context, override_account_id=None, skip_okcc_sync: bool = False):
    """销售点击「快捷登录」：语音/数据客户展示OKCC凭据，短信客户走模拟登录 (API)"""
    from bot.config import settings as bot_settings

    tg_id = query.from_user.id
    if override_account_id:
        account_id = override_account_id
    else:
        raw = query.data or ""
        try:
            account_id = int(raw.replace("sales_login_", ""))
        except ValueError:
            await query.edit_message_text("❌ 参数无效", reply_markup=get_back_menu())
            return

    client = APIClient()
    # 语音/数据：员工查看时先拉取最新 OKCC 余额
    if not skip_okcc_sync:
        await client.sync_okcc_balance(account_id)

    # 通过 API 获取账户详情
    res = await client.get_account_detail(account_id)
    if not res.get("success"):
        await query.edit_message_text(f"❌ {res.get('msg', '获取账户详情失败')}", reply_markup=get_back_menu())
        return

    acct = res
    # 语音/数据客户：展示完整凭据信息
    if acct.get("business_type") in ('voice', 'data'):
        creds = acct.get("supplier_credentials") or {}

        client_name = creds.get('client_name') or acct.get("account_name")
        username = creds.get('username') or 'admin'
        password = creds.get('password') or '-'
        sip_range = creds.get('sip_range') or creds.get('agent_range') or '-'
        sip_password = creds.get('sip_password') or '-'
        sip_domain = creds.get('sip_domain') or creds.get('domain') or '-'
        supplier_url = acct.get("supplier_url") or '-'

        text = f"系统地址：{supplier_url}\n\n"
        text += f"企业客户登录 ─────────\n"
        text += f"客户名：{client_name}\n"
        text += f"用户名：{username}\n"
        text += f"密码：{password}\n"
        text += f"─────────────────\n"
        text += f"坐席注册\n"
        text += f"坐席号：{sip_range}\n"
        text += f"口令：{sip_password}\n"
        text += f"域名：{sip_domain}\n"
        text += f"─────────────────\n"
        text += f"坐席登录\n"
        text += f"客户名：{client_name}\n"
        text += f"用户名：{sip_range}\n"
        text += f"密码：{sip_range}\n"
        text += f"\n送号规则：国码+号码，中间不加0\n"

        # 附加余额和资费信息
        billing_pkg = creds.get('billing_package', '')
        if billing_pkg:
            text += f"\n📋 资费套餐: {billing_pkg}"
        okcc_balance = creds.get('okcc_balance')
        if okcc_balance is not None:
            synced_at = creds.get('okcc_synced_at', '')
            text += f"\n💰 OKCC余额: ¥{okcc_balance:.2f}"
            if synced_at:
                text += f" (同步: {synced_at})"

        keyboard = []
        if acct.get("supplier_url"):
            keyboard.append([InlineKeyboardButton("🌐 打开系统登录", url=acct.get("supplier_url"))])
        keyboard.append([InlineKeyboardButton("🔄 刷新余额", callback_data=f"okcc_refresh_{account_id}")])
        keyboard.append([InlineKeyboardButton("⬅️ 返回我的客户", callback_data="menu_my_customers")])

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    # 短信客户：走原有的模拟登录逻辑
    secret = (getattr(bot_settings, "TELEGRAM_STAFF_API_SECRET", None) or "").strip()
    if not secret:
        await query.edit_message_text(
            "❌ 未配置 TELEGRAM_STAFF_API_SECRET。\n\n"
            "请管理员在 API 与 Bot 容器环境变量中设置相同密钥后重试。",
            reply_markup=get_back_menu(),
        )
        return

    import httpx

    url = f"{bot_settings.API_BASE_URL.rstrip('/')}/api/v1/admin/telegram/sales-impersonate"
    try:
        async with httpx.AsyncClient(timeout=25.0) as client_httpx:
            r = await client_httpx.post(
                url,
                json={"tg_id": tg_id, "account_id": account_id},
                headers={"X-Telegram-Staff-Secret": secret},
            )
            payload = r.json()
    except Exception as e:
        logger.exception("sales impersonate 请求失败: %s", e)
        await query.edit_message_text(
            "❌ 无法连接后端，请检查 Bot 的 API_BASE_URL（Docker 内应为 http://api:8000）",
            reply_markup=get_back_menu(),
        )
        return

    if r.status_code != 200 or not payload.get("success"):
        msg = payload.get("detail")
        if isinstance(msg, list) and msg:
            msg = msg[0].get("msg", str(msg[0])) if isinstance(msg[0], dict) else str(msg[0])
        elif not isinstance(msg, str):
            msg = str(payload)
        await query.edit_message_text(
            f"❌ 无法快捷登录\n\n{msg}",
            reply_markup=get_back_menu(),
        )
        return

    login_url = payload.get("login_url") or ""
    name = payload.get("account_name", "")
    if not login_url:
        await query.edit_message_text("❌ 未返回登录链接", reply_markup=get_back_menu())
        return

    await query.edit_message_text(
        f"🔐 快捷登录 · {name}\n\n"
        f"点击下方按钮在浏览器打开客户控制台（模拟登录，请勿转发）。\n\n"
        f"账户ID: {payload.get('account_id')}",
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🌐 打开客户控制台", url=login_url)],
                [InlineKeyboardButton("🔙 返回我的客户", callback_data="menu_my_customers")],
            ]
        ),
    )


async def show_my_customers(query, context, biz_filter=None, page: int = 0):
    """显示我的客户 (API)"""
    tg_id = query.from_user.id
    client = APIClient()
    
    # 验证权限（无需本月 sms_logs 聚合，避免与「我的客户」无关的 5s 级延迟）
    admin_info = await client.verify_bot_user(tg_id, include_monthly_performance=False)
    if not admin_info or admin_info.get("role") not in ['sales', 'super_admin', 'admin']:
        await query.edit_message_text("❌ 无权限查看客户列表", reply_markup=get_back_menu())
        return

    # verify-user 员工主键为 user_id，与嵌套 admin.id 一致
    admin_id = admin_info.get("user_id") or (admin_info.get("admin") or {}).get("id")
    if not admin_id:
        await query.edit_message_text("❌ 无法识别员工身份，请重新发送 /start", reply_markup=get_back_menu())
        return
    res = await client.get_sales_customers(admin_id, biz_type=biz_filter or 'all', page=page)
    if not res.get("success"):
        await query.edit_message_text(f"❌ {res.get('msg', '获取客户列表失败')}", reply_markup=get_back_menu())
        return

    customers = res.get("customers", [])
    total_matched = res.get("total", 0)
    type_counts = res.get("type_counts", {})
    
    sms_count = type_counts.get('sms', 0)
    voice_count = type_counts.get('voice', 0)
    data_count = type_counts.get('data', 0)
    total_count = sms_count + voice_count + data_count

    if total_count == 0:
        await query.edit_message_text(
            "👥 我的客户\n\n暂无客户记录",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📞 语音开户", callback_data="menu_open_voice"),
                    InlineKeyboardButton("📊 数据开户", callback_data="menu_open_data"),
                ],
                [InlineKeyboardButton("🔙 返回", callback_data="menu_main")]
            ])
        )
        return

    # 分类概览
    if biz_filter is None:
        biz_labels = {
            'sms': f"📱 短信客户 ({sms_count})",
            'voice': f"📞 语音客户 ({voice_count})",
            'data': f"📊 数据客户 ({data_count})",
        }
        keyboard = []
        for bt, label in biz_labels.items():
            if type_counts.get(bt, 0) > 0:
                keyboard.append([InlineKeyboardButton(label, callback_data=f"my_cust_{bt}")])
        if total_count > 0:
            keyboard.append([InlineKeyboardButton("📋 全部客户", callback_data="my_cust_all")])
        keyboard.append([InlineKeyboardButton("🔙 返回", callback_data="menu_main")])

        await query.edit_message_text(
            f"👥 <b>我的客户</b>（共 {total_count} 个）\n\n"
            f"📱 短信: {sms_count}  |  📞 语音: {voice_count}  |  📊 数据: {data_count}\n\n"
            f"选择业务类型查看客户列表：",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        return

    # 客户列表：账号、国家、默认通道、单价（短信为 $/条；语音/数据仅展示账户 unit_price 数值）
    lines = [
        f"👥 客户列表 ({biz_filter})\n",
        "<i>账号 | 国家 | 通道 | 单价 | 余额</i>\n",
    ]
    unit_hint = "/条" if (biz_filter or "").lower() == "sms" else ""
    keyboard = []
    for c in customers:
        raw_cc = (c.get("country_code") or "").strip().upper()
        country_label = COUNTRY_NAMES.get(raw_cc, raw_cc) if raw_cc else "-"
        ch = (c.get("channel_name") or "").strip() or "未绑定"
        if len(ch) > 22:
            ch = ch[:20] + "…"
        try:
            up = float(c.get("unit_price") if c.get("unit_price") is not None else 0)
        except (TypeError, ValueError):
            up = 0.0
        try:
            bal = float(c.get("balance") if c.get("balance") is not None else 0)
        except (TypeError, ValueError):
            bal = 0.0
        acct = c.get("account_name") or "-"
        acct_e = html_escape.escape(str(acct))
        country_e = html_escape.escape(str(country_label))
        ch_e = html_escape.escape(str(ch))
        lines.append(
            f"• <b>{acct_e}</b>\n"
            f"  🌍 {country_e}  📡 {ch_e}  💵 ${up:.4f}{html_escape.escape(unit_hint)}  💰 ${bal:.2f}"
        )
        btn_label = acct if len(acct) <= 28 else (acct[:26] + "…")
        keyboard.append(
            [InlineKeyboardButton(f"🔐 快捷登录: {btn_label}", callback_data=f"sales_login_{c.get('id')}")]
        )

    # 简化分页处理 (如果需要可以做得更复杂)
    keyboard.append([InlineKeyboardButton("🔙 返回分类", callback_data="menu_my_customers")])
    keyboard.append([InlineKeyboardButton("🏠 返回主菜单", callback_data="menu_main")])

    body = "\n".join(lines)
    if len(body) > 4000:
        body = body[:3950] + "\n\n…(仅展示部分，请缩小筛选或联系管理员导出)"
    await query.edit_message_text(body, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def show_business_knowledge(query, context, category=None):
    """显示业务知识库 (通过 API)"""
    client = APIClient()
    cat_map = {"sms": "📱短信知识", "voice": "📞语音知识", "data": "📊数据知识", "general": "📋通用知识"}

    if category is None:
        keyboard = [
            [InlineKeyboardButton("📱 短信知识", callback_data="kb_cat_sms")],
            [InlineKeyboardButton("📞 语音知识", callback_data="kb_cat_voice")],
            [InlineKeyboardButton("📊 数据知识", callback_data="kb_cat_data")],
            [InlineKeyboardButton("📋 通用知识", callback_data="kb_cat_general")],
            [InlineKeyboardButton("🔙 返回", callback_data="menu_main")],
        ]
        text = "📚 业务知识\n\n请选择业务类型："
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    res = await client.get_knowledge_articles(category)
    if not res.get("success"):
        await query.edit_message_text(f"❌ {res.get('msg', '获取内容失败')}", reply_markup=get_back_menu())
        return

    articles = res.get("articles", [])
    if not articles:
        cat_label = cat_map.get(category, category)
        text = f"📚 {cat_label}\n\n暂无内容。"
        keyboard = [
            [InlineKeyboardButton("🔙 返回知识库", callback_data="menu_business_knowledge")],
            [InlineKeyboardButton("🔙 返回主菜单", callback_data="menu_main")],
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    cat_label = cat_map.get(category, category)
    keyboard = []
    for a in articles:
        title = a.get("title", "无标题")
        label = (title[:20] + "...") if len(title) > 20 else title
        keyboard.append([InlineKeyboardButton(label, callback_data=f"kb_article_{a.get('id')}")])
    keyboard.append([InlineKeyboardButton("🔙 返回知识库", callback_data="menu_business_knowledge")])
    keyboard.append([InlineKeyboardButton("🔙 返回主菜单", callback_data="menu_main")])

    text = f"📚 {cat_label}\n\n请选择要查阅的内容："
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def show_knowledge_article(query, context, article_id: int):
    """显示单篇知识文章详情 (通过 API)"""
    client = APIClient()
    res = await client.get_knowledge_article(article_id)
    if not res.get("success"):
        await query.edit_message_text(f"❌ {res.get('msg', '获取详情失败')}", reply_markup=get_back_menu())
        return

    article = res.get("article", {})
    content = (article.get("content") or "").strip() or "（无正文）"
    if len(content) > 3500:
        content = content[:3500] + "\n\n...(内容过长，请登录Web端查看全文)"

    att_text = ""
    attachments = article.get("attachments", [])
    if attachments:
        att_text = "\n\n📎 附件（点击下方按钮下载）："

    cat_map = {"sms": "📱短信知识", "voice": "📞语音知识", "data": "📊数据知识", "general": "📋通用知识"}
    cat_label = cat_map.get(article.get("category") or "general", article.get("category"))
    text = f"📚 {article.get('title')}\n\n{cat_label} | 浏览 {article.get('view_count', 0)}\n\n{content}{att_text}"[:4090]

    keyboard = []
    for att in attachments[:10]:
        fname = att.get("file_name", "附件")
        short_name = (fname[:25] + "…") if len(fname) > 25 else fname
        keyboard.append([InlineKeyboardButton(f"📥 {short_name}", callback_data=f"kb_dl_{att.get('id')}")])
    
    if len(attachments) > 10:
        keyboard.append([InlineKeyboardButton("...更多附件请登录Web端下载", callback_data="kb_noop")])
    
    keyboard.append([InlineKeyboardButton("🔙 返回知识库", callback_data=f"kb_cat_{article.get('category') or 'general'}")])
    keyboard.append([InlineKeyboardButton("🔙 返回主菜单", callback_data="menu_main")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def send_knowledge_attachment(query, context, attachment_id: int):
    """发送知识库附件给用户（Telegram 文档）

    注意：handle_menu_callback 开头已对 callback 执行过 query.answer()，
    此处禁止再次 answer，否则 Telegram 报错并中断，用户表现为「点击无反应」。
    """
    from bot.services.api_client import APIClient
    from pathlib import Path

    api = APIClient()
    raw = await api.get_knowledge_attachment(attachment_id)
    if not raw.get("success"):
        err = raw.get("msg", "无法获取附件信息")
        if query.message:
            await query.message.reply_text(f"❌ {err}")
        return

    att = raw.get("attachment") or {}
    rel_path = (att.get("file_path") or "").strip()
    file_name = att.get("file_name") or "附件"
    if not rel_path:
        if query.message:
            await query.message.reply_text("❌ 附件路径为空，请联系管理员检查知识库数据")
        return

    # 知识库文件路径（与 backend 一致）
    KNOWLEDGE_DIR = Path("/app/data/knowledge")
    file_path = KNOWLEDGE_DIR / rel_path

    if not file_path.exists():
        if query.message:
            await query.message.reply_text(
                f"❌ 服务器上未找到文件：{rel_path}\n请确认 Bot 容器已挂载 data/knowledge 与后台一致。"
            )
        return

    try:
        with open(file_path, "rb") as f:
            await context.bot.send_document(
                chat_id=query.message.chat_id,
                document=f,
                filename=file_name,
                caption=f"📎 {file_name}",
            )
    except Exception as e:
        logger.exception("发送知识附件失败: %s", e)
        if query.message:
            await query.message.reply_text("❌ 发送失败，请稍后重试或联系管理员。")


async def show_commission(query, context):
    """显示佣金"""
    tg_id = query.from_user.id
    
    user_info = await api.verify_user(tg_id)
    if not user_info or not user_info.get("is_admin") or user_info.get("role") not in ['sales', 'finance', 'super_admin']:
        await query.edit_message_text("❌ 无法获取佣金信息", reply_markup=get_back_menu())
        return

    admin_id = user_info.get("user_id")
    # verify-user 已含本月业绩/佣金/提成比例，避免再打一遍 sales/stats
    if "monthly_profit" in user_info:
        monthly_profit = float(user_info["monthly_profit"])
        monthly_comm = float(user_info.get("monthly_commission") or 0)
        if "commission_rate" in user_info:
            rate = float(user_info["commission_rate"])
        elif monthly_profit:
            rate = round((monthly_comm / monthly_profit) * 100, 2)
        else:
            rate = 0.0
        await query.edit_message_text(
            f"💰 我的佣金与业绩\n\n"
            f"📊 本月预计业绩: ${monthly_profit:.2f}\n"
            f"📈 本月预计佣金: ${monthly_comm:.2f}\n"
            f"💵 当前提成比例: {rate:.1f}%\n\n"
            f"💡 业绩统计仅包含真实通道已送达的消息利润。\n"
            f"最终结算以每月15日财务核算为准。",
            reply_markup=get_back_menu(),
        )
        return

    stats_resp = await api.get_sales_stats(admin_id)
    if stats_resp.get("success"):
        monthly_profit = stats_resp["monthly_profit"]
        monthly_comm = stats_resp["monthly_commission"]
        rate = stats_resp.get("commission_rate", 0)

        await query.edit_message_text(
            f"💰 我的佣金与业绩\n\n"
            f"📊 本月预计业绩: ${monthly_profit:.2f}\n"
            f"📈 本月预计佣金: ${monthly_comm:.2f}\n"
            f"💵 当前提成比例: {float(rate):.1f}%\n\n"
            f"💡 业绩统计仅包含真实通道已送达的消息利润。\n"
            f"最终结算以每月15日财务核算为准。",
            reply_markup=get_back_menu(),
        )
    else:
        await query.edit_message_text(
            f"❌ 获取佣金失败: {stats_resp.get('msg', '未知错误')}",
            reply_markup=get_back_menu(),
        )


async def show_pending_tickets(query, context):
    """显示待审核工单"""
    client = APIClient()
    # 查询待处理工单 (可以模糊 status 或者取 open)
    tickets = await client.get_tickets(status='open')
    # 也可以根据业务逻辑取 ['assigned', 'in_progress']，这里先取 open

    if not tickets:
        await query.edit_message_text(
            "📋 待处理工单\n\n"
            "🎉 暂无待处理工单",
            reply_markup=get_back_menu()
        )
        return

    priority_emoji = {
        'urgent': '🔴',
        'high': '🟠',
        'normal': '🟢',
        'low': '⚪'
    }

    lines = [f"📋 待处理工单 ({len(tickets)}条)\n"]

    for t in tickets:
        emoji = priority_emoji.get(t.get("priority"), '🟢')
        type_label = {'test': '测试', 'technical': '技术', 'billing': '账务', 'feedback': '反馈'}.get(t.get("ticket_type"), t.get("ticket_type"))
        lines.append(f"{emoji} {t.get('ticket_no')} [{type_label}] {t.get('title', '')[:12]}...")

    # 构建按钮
    keyboard = []
    for t in tickets[:5]:
        keyboard.append([InlineKeyboardButton(
            f"处理 {t.get('ticket_no')}",
            callback_data=f"process_ticket_{t.get('id')}"
        )])
    keyboard.append([InlineKeyboardButton("🔙 返回", callback_data="menu_main")])

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_pending_recharge(query, context):
    """显示待审核充值"""
    client = APIClient()
    # 查询待审核充值
    orders = await client.get_recharge_orders(status='pending')

    if not orders:
        await query.edit_message_text(
            "💳 待审核充值\n\n"
            "🎉 暂无待审核充值申请",
            reply_markup=get_back_menu()
        )
        return

    lines = [f"💳 待审核充值 ({len(orders)}笔)\n"]

    for order in orders:
        # 后端待审核列表字段为 username，兼容 account_name
        acct = order.get("account_name") or order.get("username") or "-"
        lines.append(f"• {order.get('id')}: ${order.get('amount')} ({acct})")

    # 构建按钮
    keyboard = []
    for order in orders[:5]:
        keyboard.append([
            InlineKeyboardButton(f"✅ 通过 {order.get('id')}", callback_data=f"approve_recharge_{order.get('id')}"),
            InlineKeyboardButton(f"❌ 拒绝", callback_data=f"reject_recharge_{order.get('id')}")
        ])
    keyboard.append([InlineKeyboardButton("🔙 返回", callback_data="menu_main")])

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_pricing_menu(query, context, tg_id: int):
    """报价查询入口 - 销售/技术/管理员可用"""
    client = APIClient()
    verify = await client.verify_bot_user(tg_id, include_monthly_performance=False)

    allowed_roles = ("sales", "super_admin", "admin", "tech")
    if not verify.get("authorized") or verify.get("role") not in allowed_roles:
        await query.edit_message_text(
            "❌ 仅销售/技术/管理员可使用报价查询",
            reply_markup=get_back_menu()
        )
        return

    keyboard = [
        [InlineKeyboardButton("📱 短信", callback_data="pricing_biz_sms")],
        [InlineKeyboardButton("📞 语音", callback_data="pricing_biz_voice")],
        [InlineKeyboardButton("📊 数据", callback_data="pricing_biz_data")],
        [InlineKeyboardButton("🔙 返回", callback_data="menu_main")],
    ]
    await query.edit_message_text(
        "📋 报价查询\n\n"
        "请先选择业务类型，再选择国家：",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


BIZ_LABELS = {"sms": "短信", "voice": "语音", "data": "数据"}


async def _get_bot_config() -> dict:
    """从 API 获取 Bot 配置"""
    resp = await api.get_system_config()
    default_config = {
        'admin_group_id': os.getenv('TELEGRAM_ADMIN_GROUP_ID', ''),
        'enable_sms_content_review': True,
    }
    if not resp.get("success"):
        return default_config
    
    config_data = resp.get("config", {})
    return {
        'admin_group_id': config_data.get('telegram_admin_group_id', default_config['admin_group_id']),
        'enable_sms_content_review': str(config_data.get('telegram_enable_sms_content_review', 'true')).lower() == 'true'
    }


async def _resolve_supplier_group_for_account(db, account_id: int, admin_group_id: str) -> str:
    """
    通过 API 获取账户关联的渠道供应商 Telegram 群组 ID。
    """
    client = APIClient()
    res = await client.get_supplier_group_internal(account_id)
    if res.get("success") and res.get("supplier_group_id"):
        return str(res.get("supplier_group_id")).strip()
    return (admin_group_id or '').strip()


async def _get_test_countries_for_account(account_id: int) -> str:
    """通过 API 获取可测试国家列表"""
    client = APIClient()
    res = await client.get_test_countries_internal(account_id)
    return res.get("countries", "-")


def _voice_unit(billing_model: str) -> str:
    """语音计费模式转显示单位：1+1=按秒，60+60=按分钟，6+1/6+6/30+6等=按计费块"""
    t = (billing_model or "").strip()
    if t == "1+1":
        return "/秒"
    if t == "60+60":
        return "/分钟"
    if re.match(r"^\d+\+\d+$", t):
        return f"({t}s)"
    return "/分钟"


async def show_pricing_country_by_biz(query, context, biz_type: str):
    """按业务类型显示有报价的国家列表 (通过 API)"""
    biz_label = BIZ_LABELS.get(biz_type, biz_type)
    client = APIClient()
    res = await client.get_pricing_countries(biz_type)
    if not res.get("success"):
        await query.edit_message_text(
            f"❌ 查询失败: {res.get('msg', '获取数据失败')}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="menu_pricing")]])
        )
        return

    countries = res.get("countries", [])
    if not countries:
        await query.edit_message_text(
            f"📋 {biz_label} 报价\n\n暂无{biz_label}报价数据。",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="menu_pricing")]])
        )
        return

    keyboard = []
    row = []
    for country_code in countries:
        label = COUNTRY_NAMES.get(country_code, country_code)
        row.append(InlineKeyboardButton(label, callback_data=f"pricing_biz_country_{biz_type}_{country_code}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 返回", callback_data="menu_pricing")])

    await query.edit_message_text(
        f"📋 {biz_label} 报价 - 选择国家\n\n请选择国家：",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_sms_approval_callback(query, context, approval_id: int, approved: bool):
    """处理短信审核通过/拒绝：通过 API 更新状态"""
    reviewer_name = query.from_user.full_name or query.from_user.username or "管理员"
    client = APIClient()
    
    # 1. 提交审核
    res = await client.review_sms_approval_internal(approval_id, approved, query.from_user.id)
    if not res.get("success"):
        err = res.get("message", "未知错误")
        if query.message:
            await query.message.reply_text(f"❌ 操作失败: {err}")
        return

    # 2. 更新显示
    status_text = "✅ *已通过*" if approved else "❌ *已拒绝*"
    test_countries = await _get_test_countries_for_account(res.get("account_id"))
    
    # 获取全文预览
    approval_data = await client.get_sms_approval_internal(approval_id)
    content = approval_data.get("content", "")
    
    await query.edit_message_text(
        f"{status_text}\n\n"
        f"🌍 测试国家: {test_countries}\n"
        f"📝 内容: {content[:500]}\n\n"
        f"审核人: {reviewer_name}",
        parse_mode='Markdown',
    )
    
    # 3. 提示输入补充信息或跳过
    _store_sms_approval_session(context, query.from_user.id, approval_id, approved)
    skip_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏭️ 跳过", callback_data=f"sms_approval_skip_{approval_id}_{1 if approved else 0}")],
    ])
    prompt = "💬 请输入回复内容或发送图片（将转发给客户），或点击【跳过】" if approved else "💬 请输入拒绝原因（将转发给客户），或点击【跳过】"
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=prompt,
        reply_markup=skip_keyboard,
    )


async def show_pricing_by_biz_country(query, context, biz_type: str, country_code: str):
    """显示指定业务类型+国家的报价（走 internal/bot 报价详情接口）"""
    biz_label = BIZ_LABELS.get(biz_type, biz_type)
    country_label = COUNTRY_NAMES.get(country_code, country_code)
    client = APIClient()
    res = await client.get_pricing_detail(biz_type, country_code)

    if not res.get("success"):
        await query.edit_message_text(
            f"❌ 查询失败: {res.get('msg', '未知错误')}",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 返回", callback_data=f"pricing_biz_{biz_type}")]]
            ),
        )
        return

    rates = res.get("rates") or []
    if not rates:
        await query.edit_message_text(
            f"📋 {biz_label} · {country_label} ({country_code})\n\n暂无供应商报价。",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 返回国家列表", callback_data=f"pricing_biz_{biz_type}")]]
            ),
        )
        return

    lines = [f"📋 {biz_label} · {country_label} ({country_code})\n"]
    for r in rates[:25]:
        sn = r.get("supplier_name") or "-"
        cp = r.get("cost_price")
        bm = (r.get("billing_model") or "").strip()
        note = (r.get("note") or "").strip()[:120]
        try:
            cp_f = float(cp)
            cp_s = f"{cp_f:.6f}".rstrip("0").rstrip(".")
        except (TypeError, ValueError):
            cp_s = str(cp)
        lines.append(f"• {sn}\n  成本: {cp_s} USD  计费: {bm or '-'}")
        if note:
            lines.append(f"  备注: {note}")
    if len(rates) > 25:
        lines.append(f"\n(共 {len(rates)} 条，仅展示前 25 条)")

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3950] + "\n\n...(内容过长已截断)"

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔙 返回国家列表", callback_data=f"pricing_biz_{biz_type}")]]
        ),
    )


async def execute_approved_sms(query, context, approval_id: int):
    """客户点击「立即发送」后，执行审核通过的短信发送"""
    tg_id = query.from_user.id
    client = APIClient()
    
    approval_data = await client.get_sms_approval_internal(approval_id)
    if not approval_data:
        if query.message:
            await query.message.reply_text("❌ 记录不存在")
        return
        
    if str(approval_data.get("tg_user_id")) != str(tg_id):
        if query.message:
            await query.message.reply_text("❌ 无权操作")
        return
        
    if approval_data.get("status") != 'approved':
        if query.message:
            await query.message.reply_text("该短信未通过审核或已发送")
        return
        
    if approval_data.get("message_id"):
        if query.message:
            await query.message.reply_text("该短信已发送")
        return
        
    # 只审核文案时无号码，需先让用户填写
    phone = approval_data.get("phone_number")
    content = approval_data.get("content")
    
    if not (phone or (phone and phone.strip())):
        context.user_data['waiting_for'] = 'sms_approval_phone'
        context.user_data['pending_approval_id'] = approval_id
        await query.edit_message_text(
            f"📤 *填写接收号码*\n\n"
            f"📝 内容: {content[:80] if content else ''}...\n\n"
            f"请发送接收号码（E.164 格式，如 +66812345678）：",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 取消", callback_data="menu_main")],
            ]),
        )
        return
    
    # 调用 API 发送 (原有逻辑维持 APIClient.send_sms，但后续更新也要 API)
    send_result = await client.send_sms(
        api_key=approval_data.get("api_key"),
        phone_number=phone,
        message=content,
    )
    
    if send_result.get('success'):
        msg_id = send_result.get('message_id', '-')
        await client.finalize_sms_send_internal(approval_id, message_id=msg_id)
        
        await query.edit_message_text(
            f"✅ *发送成功*\n\n"
            f"📱 号码: {phone}\n"
            f"📄 消息ID: `{msg_id}`\n"
            f"💰 费用: {send_result.get('cost', '-')} {send_result.get('currency', 'USD')}\n\n"
            f"可在【发送记录】中查看详情。",
            parse_mode='Markdown',
            reply_markup=get_main_menu_customer(),
        )
    else:
        err = send_result.get('error', {})
        err_msg = err.get('message', str(err)) if isinstance(err, dict) else str(err)
        await client.finalize_sms_send_internal(approval_id, error=err_msg[:500])
        
        await query.edit_message_text(
            f"❌ *发送失败*\n\n{err_msg}\n\n请检查后重试或联系客服。",
            parse_mode='Markdown',
            reply_markup=get_main_menu_customer(),
        )


async def approve_recharge(query, context, order_id: int, approved: bool):
    """审批充值"""
    tg_id = query.from_user.id
    client = APIClient()
    
    # 提交审核
    res = await client.review_recharge_order_internal(order_id, approved, tg_id)
    if not res or not res.get("success"):
        error_msg = res.get("message", "未知错误") if res else "API连接失败"
        await query.edit_message_text(
            f"❌ 审批操作失败: {error_msg}",
            reply_markup=get_back_menu()
        )
        return

    # 显示结果
    if approved:
        await query.edit_message_text(
            f"✅ 充值已通过\n\n"
            f"订单号: {res.get('order_no', '-')}\n"
            f"金额: ${res.get('amount', '0.00')}\n"
            f"账户: {res.get('account_name', '-')}\n"
            f"新余额: ${res.get('new_balance', '0.00')}",
            reply_markup=get_back_menu()
        )
    else:
        await query.edit_message_text(
            f"❌ 充值已拒绝\n\n"
            f"订单号: {res.get('order_no', '-')}\n"
            f"金额: ${res.get('amount', '0.00')}",
            reply_markup=get_back_menu()
        )


async def show_ticket_detail(query, context, ticket_id: int, is_admin: bool = False):
    """显示工单详情"""
    client = APIClient()
    res = await client.get_ticket_by_id_internal(ticket_id)
    
    if not res or not res.get("id"):
        await query.edit_message_text(
            "❌ 工单不存在或获取失败",
            reply_markup=get_back_menu()
        )
        return
        
    status_map = {
        'open': '⏳待处理',
        'assigned': '👤已分配',
        'in_progress': '🔄处理中',
        'pending_user': '⏸️等待回复',
        'resolved': '✅已解决',
        'closed': '🔒已关闭',
        'cancelled': '❌已取消'
    }
    
    type_map = {
        'test': '测试申请',
        'technical': '技术支持',
        'billing': '账务问题',
        'feedback': '意见反馈',
        'other': '其他'
    }
    
    created_at_str = res.get("created_at", "N/A")
    try:
        from datetime import datetime
        if "T" in created_at_str:
            dt = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            created_at_str = dt.strftime('%Y-%m-%d %H:%M')
    except Exception:
        pass

    text = f"""📄 工单详情

工单号: {res.get('ticket_no', '-')}
类型: {type_map.get(res.get('ticket_type'), res.get('ticket_type', '-'))}
状态: {status_map.get(res.get('status'), res.get('status', '-'))}
优先级: {res.get('priority', '-')}

标题: {res.get('title', '-')}

描述:
{res.get('description') or '无'}

创建时间: {created_at_str}"""
    
    if res.get("resolution"):
        text += f"\n\n处理结果:\n{res.get('resolution')}"
    
    # 构建按钮
    keyboard = []
    if is_admin and res.get("status") in ['open', 'assigned', 'in_progress']:
        keyboard.append([InlineKeyboardButton("✅ 关闭工单", callback_data=f"close_ticket_{ticket_id}")])
    keyboard.append([InlineKeyboardButton("🔙 返回", callback_data="menu_tickets" if not is_admin else "menu_pending_tickets")])
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def close_ticket(query, context, ticket_id: int):
    """关闭工单"""
    tg_id = query.from_user.id
    client = APIClient()
    
    # 执行操作
    res = await client.ticket_action_internal(ticket_id, 'resolve', tg_id)
    if not res or not res.get("success"):
        await query.edit_message_text(
            f"❌ 操作失败: {res.get('message', '权限不足或系统错误')}",
            reply_markup=get_back_menu()
        )
        return
        
    await query.edit_message_text(
        f"✅ 工单已处理\n\n工单ID: {ticket_id}",
        reply_markup=get_back_menu()
    )


async def show_system_stats(query, context):
    """显示系统统计"""
    stats = await api.get_system_stats_internal()
    if not stats:
        if query.message:
            await query.message.reply_text("❌ 无法获取系统统计")
        return
        
    await query.edit_message_text(
        f"📊 系统统计\n\n"
        f"👥 总账户数: {stats.get('total_accounts', 0)}\n"
        f"💰 今日充值: ${stats.get('today_recharge_usd', 0.0):.2f}\n"
        f"📋 待处理工单: {stats.get('pending_tickets', 0)}\n"
        f"💳 待审核充值: {stats.get('pending_recharge', 0)}",
        reply_markup=get_back_menu()
    )


async def show_sales_stats(query, context):
    """显示销售业绩统计"""
    tg_id = query.from_user.id

    # 仅鉴权与取 admin_id；跳过 verify-user 内本月 sms_logs 聚合（与 get_sales_stats 重复，曾导致约双倍延迟）
    user_info = await api.verify_user(tg_id, include_monthly_performance=False)
    if not user_info or not user_info.get("is_admin"):
        await query.edit_message_text("❌ 无法获取统计信息", reply_markup=get_back_menu())
        return

    admin_id = user_info.get("user_id") or (user_info.get("admin") or {}).get("id")
    if not admin_id:
        await query.edit_message_text("❌ 无法识别员工身份", reply_markup=get_back_menu())
        return
    resp = await api.get_sales_stats(admin_id)
    
    if resp.get("success"):
        await query.edit_message_text(
            f"📊 我的业绩统计\n\n"
            f"👤 总客户数: {resp.get('total_customers', 0)}\n"
            f"🆕 本月新增: {resp.get('new_customers', 0)}\n"
            f"💰 客户总余额: ${resp.get('total_balance', 0.0):.2f}\n"
            f"📊 本月预计业绩: ${resp.get('monthly_profit', 0.0):.2f}\n"
            f"📈 本月预计佣金: ${resp.get('monthly_commission', 0.0):.2f}\n"
            f"💵 提成比例: {float(resp.get('commission_rate', 0)):.1f}%",
            reply_markup=get_back_menu()
        )
    else:
        await query.edit_message_text(
            f"❌ 获取统计失败: {resp.get('msg', '未知错误')}",
            reply_markup=get_back_menu()
        )


async def show_customer_tickets(query, context):
    """显示销售的客户工单列表（数据来自销售统计接口）。"""
    tg_id = query.from_user.id
    client = APIClient()

    res = await client.get_sales_stats_internal(tg_id)
    if not res:
        if query.message:
            await query.message.reply_text("❌ 无法获取销售统计")
        return
        
    tickets = res.get("tickets", [])
    if not tickets:
        await query.edit_message_text(
            "📋 客户工单\n\n暂无客户工单",
            reply_markup=get_back_menu()
        )
        return
        
    status_map = {
        'open': '⏳待处理',
        'assigned': '👤已分配',
        'in_progress': '🔄处理中',
        'pending_user': '⏸️等待回复',
        'resolved': '✅已解决',
        'closed': '🔒已关闭',
        'cancelled': '❌已取消',
    }
    
    lines = [f"📋 客户工单 ({len(tickets)}条)\n"]
    for t in tickets:
        status_label = status_map.get(t.get('status'), t.get('status') or '未知')
        acct_name = (t.get('account_name') or '')[:12]
        lines.append(
            f"• {status_label}\n"
            f"  {t.get('ticket_no')} · {acct_name}"
        )
    
    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=get_back_menu()
    )


async def _forward_message_media_as_fallback(
    context: ContextTypes.DEFAULT_TYPE, customer_chat: int, msg: Message
) -> None:
    """copy_message 失败时按类型重发（兼容各类媒体）"""
    cap = (msg.caption or "")[:1024] if msg.caption else None
    if msg.photo:
        await context.bot.send_photo(
            chat_id=customer_chat,
            photo=msg.photo[-1].file_id,
            caption=cap,
        )
        return
    if msg.video:
        await context.bot.send_video(
            chat_id=customer_chat,
            video=msg.video.file_id,
            caption=cap,
        )
        return
    if msg.animation:
        await context.bot.send_animation(
            chat_id=customer_chat,
            animation=msg.animation.file_id,
            caption=cap,
        )
        return
    if msg.document:
        await context.bot.send_document(
            chat_id=customer_chat,
            document=msg.document.file_id,
            caption=cap,
        )
        return
    if msg.sticker:
        await context.bot.send_sticker(chat_id=customer_chat, sticker=msg.sticker.file_id)
        return
    if msg.video_note:
        await context.bot.send_video_note(
            chat_id=customer_chat,
            video_note=msg.video_note.file_id,
        )
        return


async def _notify_customer_sms_approval_reply(
    context: ContextTypes.DEFAULT_TYPE,
    approval: Any,
    approved: bool,
    reply_note: str,
    *,
    media_message: Message | None = None,
    photo_file_id: str | None = None,
) -> None:
    """将供应商审核回复（文字/任意媒体）转发给客户；优先 copy_message 保留从其他群复制等格式。"""
    customer_chat = int(approval.tg_user_id)
    if approved:
        base = (
            f"✅ *短信审核已通过*\n\n"
            f"📝 内容预览: {(approval.content or '')[:80]}"
            f"{'...' if len(approval.content or '') > 80 else ''}"
        )
        if reply_note:
            base += f"\n\n💬 审核备注: {reply_note}"
        base += "\n\n请点击「立即发送」进行发送。"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 立即发送", callback_data=f"send_approved_sms_{approval.id}")],
            [InlineKeyboardButton("🔙 返回主菜单", callback_data="menu_main")],
        ])
        await context.bot.send_message(
            chat_id=customer_chat,
            text=base,
            parse_mode='Markdown',
            reply_markup=keyboard,
        )
        if media_message:
            try:
                await context.bot.copy_message(
                    chat_id=customer_chat,
                    from_chat_id=media_message.chat_id,
                    message_id=media_message.message_id,
                )
            except Exception as e:
                logger.warning("短信审核 copy_message 失败，回退 send_*: %s", e)
                await _forward_message_media_as_fallback(context, customer_chat, media_message)
        elif photo_file_id:
            await context.bot.send_photo(
                chat_id=customer_chat,
                photo=photo_file_id,
                caption=((reply_note and "📎 附图") or "📎 供应商提供的图片")[:1024],
            )
    else:
        reject_msg = "❌ 您的短信审核未通过"
        if reply_note:
            reject_msg += f"\n\n💬 拒绝原因: {reply_note}"
        reject_msg += "\n\n如有疑问请联系客服。"
        await context.bot.send_message(
            chat_id=customer_chat,
            text=reject_msg,
            reply_markup=get_main_menu_customer(),
        )
        if media_message:
            try:
                await context.bot.copy_message(
                    chat_id=customer_chat,
                    from_chat_id=media_message.chat_id,
                    message_id=media_message.message_id,
                )
            except Exception as e:
                logger.warning("短信审核 copy_message 失败，回退 send_*: %s", e)
                await _forward_message_media_as_fallback(context, customer_chat, media_message)
        elif photo_file_id:
            await context.bot.send_photo(
                chat_id=customer_chat,
                photo=photo_file_id,
                caption=((reply_note and "📎 附图") or "📎 供应商提供的说明图")[:1024],
            )


async def handle_sms_approval_reply_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """供应商在短信审核流程中发送图片/视频等媒体（含从其他群复制的图），转发给客户"""
    uid = update.effective_user.id if update.effective_user else None
    if not uid:
        return
    waiting_for = context.user_data.get('waiting_for')
    chat_type = update.effective_chat.type if update.effective_chat else None
    if chat_type in ('group', 'supergroup'):
        group_only_flows = ('sms_approval_reply',)
        if waiting_for and waiting_for not in group_only_flows:
            return
    if not _peek_sms_approval_pending(context, uid):
        return

    msg = update.message
    if not msg:
        return
    if not msg.effective_attachment:
        return

    reply_note = (msg.caption or '').strip()[:500]

    logger.info(
        "短信审核媒体回复: uid=%s has_caption=%s attachment=%s",
        uid,
        bool(reply_note),
        type(msg.effective_attachment).__name__,
    )

    # 去重：与文字回复相同
    chat_id = update.effective_chat.id if update.effective_chat else None
    msg_id = msg.message_id if msg else None
    if chat_id is not None and msg_id is not None:
        key = (chat_id, msg_id)
        if key in _processed_sms_reply_ids:
            logger.debug("跳过已处理的消息: chat_id=%s message_id=%s", chat_id, msg_id)
            return
        _processed_sms_reply_ids.add(key)
        if len(_processed_sms_reply_ids) > _MAX_PROCESSED_IDS:
            _processed_sms_reply_ids.clear()

    approval_id, approved = _take_sms_approval_session(context, uid)
    if approval_id is None or approved is None:
        return

    approval, success = await api.get_sms_approval_detail(approval_id)
    if not approval or not success:
        return
        try:
            await _notify_customer_sms_approval_reply(
                context, approval, approved, reply_note, media_message=msg
            )
        except Exception as e:
            logger.exception("短信审核媒体转发客户失败: %s", e)
    await update.message.reply_text("✅ 回复已转发给客户")


async def _generate_invite_code(target, context, is_callback=True):
    """生成邀请码并展示结果（从模板选择或价格输入后统一调用）"""
    import os

    price = context.user_data.get('customer_price', 0)
    tpl_name = context.user_data.get('template_name', '')
    biz_type = context.user_data.get('business_type', 'sms')
    biz_label = {'sms': '短信', 'voice': '语音', 'data': '数据'}.get(biz_type, biz_type)
    country = context.user_data.get('country_code', '')
    country_label = '全球（所有国家）' if country == '*' else COUNTRY_NAMES.get(country, country)

    config = {
        'business_type': biz_type,
        'country': country,
        'template_id': context.user_data.get('template_id'),
        'template_name': tpl_name,
        'price': price,
    }
    
    resp = await api.create_invitation(
        sales_id=context.user_data.get('sales_id'),
        config=config,
        valid_hours=72
    )

    if not resp.get("success"):
        msg = f"❌ 创建授权码失败: {resp.get('msg', '未知错误')}"
        if is_callback:
            await target.edit_message_text(msg, reply_markup=get_back_menu())
        else:
            await target.reply_text(msg, reply_markup=get_back_menu())
        return

    code = resp["code"]
    bot_username = os.getenv('TELEGRAM_BOT_USERNAME', 'kaolachbot')
    invite_link = f"https://t.me/{bot_username}?start={code}"

    bot_username = os.getenv('TELEGRAM_BOT_USERNAME', 'kaolachbot')
    invite_link = f"https://t.me/{bot_username}?start={code}"

    price_line = f"💰 客户单价: ${price}\n" if price > 0 else "💰 客户单价: 免费\n"
    text = (
        f"✅ <b>授权码创建成功！</b>\n\n"
        f"📋 授权码: <code>{code}</code>\n"
        f"🔗 开户链接:\n{invite_link}\n\n"
        f"📦 模板: {tpl_name}\n"
        f"🌍 国家/地区: {country_label}\n"
        f"{price_line}"
        f"⏰ 有效期: 72小时\n\n"
        f"━━━━━━━━━━━━\n"
        f"📤 将上方链接转发给客户\n"
        f"客户点击链接即可自动开户"
    )
    context.user_data['waiting_for'] = None
    if is_callback:
        await target.edit_message_text(text, parse_mode='HTML', reply_markup=get_back_menu())
    else:
        await target.reply_text(text, parse_mode='HTML', reply_markup=get_back_menu())


async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理用户文本输入"""
    waiting_for = context.user_data.get('waiting_for')
    chat_type = update.effective_chat.type if update.effective_chat else None

    # 群聊中仅处理短信审核回复，不处理创建邀请/充值等流程（避免误触发，如回复"1"被当作价格）
    if chat_type in ('group', 'supergroup'):
        group_only_flows = ('sms_approval_reply',)
        if waiting_for and waiting_for not in group_only_flows:
            for k in ('waiting_for', 'template_info', 'template_name', 'sales_id', 'business_type',
                      'country_code', 'template_id', 'customer_price', 'invite_price', 'recharge_amount',
                      'recharge_proof', 'pending_approval_id'):
                context.user_data.pop(k, None)
            return

    tg_id = update.effective_user.id

    # 语音开户：设置卖价（文本输入）→ 委托给 account_opening 处理
    if waiting_for == 'opening_sell_price':
        from bot.handlers.account_opening import handle_price_input
        await handle_price_input(update, context)
        return

    if not waiting_for and not _peek_sms_approval_pending(context, tg_id):
        return  # 没有等待输入，忽略

    text = (update.message.text or "").strip()
    logger.info(f"Text input: {text} for {waiting_for} from {tg_id}")
    
    # 处理供应商群审核回复（通过/拒绝后输入的回复内容，将转发给客户）
    sms_followup = waiting_for == 'sms_approval_reply' or (
        waiting_for is None
        and _sms_approval_data_key(tg_id) in context.application.bot_data
    )
    if sms_followup and _peek_sms_approval_pending(context, tg_id):
        # 去重：同一消息只处理一次，防止 Handler 被多次触发导致客户收到重复通知
        msg = update.message
        chat_id = update.effective_chat.id if update.effective_chat else None
        msg_id = msg.message_id if msg else None
        if chat_id is not None and msg_id is not None:
            key = (chat_id, msg_id)
            if key in _processed_sms_reply_ids:
                logger.debug("跳过已处理的消息: chat_id=%s message_id=%s", chat_id, msg_id)
                return
            _processed_sms_reply_ids.add(key)
            if len(_processed_sms_reply_ids) > _MAX_PROCESSED_IDS:
                _processed_sms_reply_ids.clear()

        approval_id, approved = _take_sms_approval_session(context, tg_id)
        if approval_id is None or approved is None:
            return
        reply_text = text[:500] if text else ""
        res = await api.update_sms_approval_action(approval_id, "approved" if approved else "rejected", text[:500])
        if res.get("success"):
            # 通知逻辑已迁移到后端或通过特定 API 触发，此处不再直接操作 DB
            pass
        await update.message.reply_text("✅ 已处理并转发")
        return

    # 处理审核通过后填写号码（只审核文案流程）
    if waiting_for == 'sms_approval_phone':
        approval_id = context.user_data.pop('pending_approval_id', None)
        context.user_data['waiting_for'] = None
        if not approval_id:
            await update.message.reply_text("❌ 会话已过期，请重新点击「立即发送」", reply_markup=get_main_menu_customer())
            return
        phone = text.strip()
        res = await api.send_sms_after_approval(approval_id, tg_id, phone)
        
        if res.get("success"):
            await update.message.reply_text(
                f"✅ *发送成功*\n\n"
                f"📱 号码: {phone}\n"
                f"📄 消息ID: `{res.get('message_id', '-')}`\n"
                f"💰 费用: {res.get('cost', '-')} {res.get('currency', 'USD')}\n\n"
                f"可在【发送记录】中查看详情。",
                parse_mode='Markdown',
                reply_markup=get_main_menu_customer(),
            )
        else:
            await update.message.reply_text(
                f"❌ *发送失败*\n\n"
                f"原因: {res.get('msg')}",
                reply_markup=get_main_menu_customer(),
                parse_mode='Markdown',
            )
        return
    
    # 处理全球模板：同时输入国家名称 + 价格
    if waiting_for == 'invite_country_price':
        parts = text.strip().rsplit(None, 1)  # 从右侧分割，支持多字国名如"新加坡"

        # 尝试判断用户输入了什么
        def _looks_like_price(s):
            try:
                float(s)
                return True
            except ValueError:
                return False

        def _resolve_country(s):
            """尝试将输入解析为国家代码，支持名称和代码两种方式"""
            s_stripped = s.strip()
            # 先尝试名称匹配
            if s_stripped in NAME_TO_COUNTRY:
                return NAME_TO_COUNTRY[s_stripped]
            # 再尝试代码匹配（兼容用户输入代码）
            up = s_stripped.upper()
            if up in COUNTRY_NAMES:
                return up
            return None

        if len(parts) < 2:
            if len(parts) == 1:
                p = parts[0]
                if _looks_like_price(p):
                    await update.message.reply_text(
                        "⚠️ 缺少国家名称，请同时输入 <b>国家名称</b> 和 <b>价格</b>：\n"
                        f"例如: <code>中国 {p}</code>",
                        parse_mode='HTML',
                    )
                elif _resolve_country(p):
                    cc = _resolve_country(p)
                    name = COUNTRY_NAMES.get(cc, p)
                    await update.message.reply_text(
                        f"⚠️ 缺少价格，请同时输入 <b>国家名称</b> 和 <b>价格</b>：\n"
                        f"例如: <code>{name} 0.05</code>",
                        parse_mode='HTML',
                    )
                else:
                    await update.message.reply_text(
                        "❌ 格式不正确，请输入 <b>国家名称 价格</b>（空格分隔）：\n"
                        "例如: <code>中国 0.05</code>",
                        parse_mode='HTML',
                    )
            else:
                await update.message.reply_text(
                    "❌ 请输入 <b>国家名称 价格</b>（空格分隔）：\n"
                    "例如: <code>中国 0.05</code>",
                    parse_mode='HTML',
                )
            return

        country_part, price_raw = parts[0], parts[1]

        # 如果最后一部分不是数字，可能用户格式有误
        if not _looks_like_price(price_raw):
            await update.message.reply_text(
                f"❌ 价格 <code>{price_raw}</code> 无效，请输入 <b>国家名称 价格</b>：\n"
                f"例如: <code>中国 0.05</code>",
                parse_mode='HTML',
            )
            return

        # 校验国家
        cc = _resolve_country(country_part)
        if not cc:
            await update.message.reply_text(
                f"❌ 未识别的国家 <code>{country_part}</code>，请输入正确的国家名称：\n"
                f"例如: 中国、美国、菲律宾、印尼 等",
                parse_mode='HTML',
            )
            return

        # 校验价格
        price = float(price_raw)
        if price < 0:
            await update.message.reply_text("❌ 价格不能为负数，请重新输入：")
            return

        context.user_data['country_code'] = cc
        context.user_data['customer_price'] = price
        await _generate_invite_code(update.message, context, is_callback=False)
        return

    # 处理邀请价格输入（非全球模板，已有国家）
    if waiting_for == 'invite_price':
        try:
            price = float(text)
            if price < 0:
                await update.message.reply_text("❌ 价格不能为负数，请重新输入（输入 0 表示免费）：")
                return
            context.user_data['customer_price'] = price
            await _generate_invite_code(update.message, context, is_callback=False)
        except ValueError:
            await update.message.reply_text("❌ 请输入有效的数字，例如: 0.05")
        return
    
    # 处理充值金额输入
    if waiting_for == 'recharge_amount':
        try:
            amount = float(text)
            if amount <= 0:
                await update.message.reply_text("❌ 金额必须大于0，请重新输入：")
                return
            
            context.user_data['recharge_amount'] = amount
            
            await update.message.reply_text(
                f"💳 充值金额: ${amount:.2f}\n\n"
                f"请上传付款凭证（截图/照片）\n"
                f"或发送 /skip 跳过",
                reply_markup=get_back_menu()
            )
            context.user_data['waiting_for'] = 'recharge_proof'
            
        except ValueError:
            await update.message.reply_text("❌ 请输入有效的金额，例如: 100 或 50.5")
        return
    
    # 处理授权码开户
    if waiting_for == 'invite_code':
        raw = text.strip()
        # 支持客户粘贴完整链接，自动提取授权码
        if '?start=' in raw:
            raw = raw.split('?start=')[-1].split('&')[0].split(' ')[0]
        code = raw.upper()
        user = update.effective_user

        result = await api.activate_invitation(
            code=code,
            tg_id=user.id,
            tg_username=user.username,
            tg_first_name=user.first_name
        )

        if result.get("success"):
            account = result.get("account", {})
            extra_info = result.get("extra_info", {})
            api_key = result.get("api_key")

            context.user_data['account_id'] = account.get('id')
            context.user_data['user_type'] = 'customer'
            context.user_data['waiting_for'] = None

            biz_type = account.get('business_type', 'sms')
            biz_label = {'sms': '短信', 'voice': '语音', 'data': '数据'}.get(biz_type, biz_type)
            country_label = COUNTRY_NAMES.get(extra_info.get('country_code', ''), extra_info.get('country_code', ''))
            tpl_name = extra_info.get('template_name', '')
            login_account = extra_info.get('login_account', account.get('account_name'))
            login_password = extra_info.get('login_password', '')

            msg = f"🎉 <b>开户成功！</b>\n\n"
            if tpl_name:
                msg += f"📋 模板: {tpl_name}\n"
            msg += (
                f"📦 业务类型: {biz_label}\n"
                f"🌍 国家/地区: {country_label}\n\n"
                f"━━━ 📱 平台登录信息 ━━━\n"
                f"🌐 平台地址: https://www.kaolach.com\n"
                f"👤 登录账户: <code>{login_account}</code>\n"
                f"🔒 登录密码: <code>{login_password}</code>\n\n"
                f"━━━ 🔧 API 接口信息 ━━━\n"
                f"🆔 账户ID: <code>{account.get('id')}</code>\n"
                f"🔑 API Key: <code>{login_account}</code>\n"
                f"🔐 API Secret: <code>{api_key}</code>\n\n"
                f"⚠️ <i>请妥善保存以上信息，密码和密钥不会再次显示</i>\n\n"
                f"请选择操作："
            )

            await update.message.reply_text(
                msg,
                parse_mode='HTML',
                reply_markup=get_main_menu_customer(),
            )
        else:
            await update.message.reply_text(
                f"❌ 激活失败: {result.get('msg', '授权码无效或已过期')}\n\n请联系销售获取新的授权码。",
                reply_markup=await get_main_menu_guest(),
            )
            context.user_data['waiting_for'] = None
        return
    
    # 处理员工绑定
    if waiting_for == 'staff_credentials':
        parts = text.split()
        if len(parts) != 2:
            await update.message.reply_text(
                "❌ 格式错误，请发送: 用户名 密码",
                reply_markup=get_back_menu()
            )
            return
        
        username, password = parts
        
        result = await api.bind_admin(username, password, tg_id)
        
        if result.get("success"):
            admin = result.get("admin", {})
            role = admin.get("role")
            
            role_map = {
                'super_admin': '超级管理员',
                'admin': '管理员',
                'sales': '销售',
                'finance': '财务',
                'tech': '技术'
            }
            role_label = role_map.get(role, role)
            
            context.user_data['user_type'] = 'admin'
            context.user_data['user_id'] = admin.get("id")
            context.user_data['user_role'] = role
            
            if role in ['super_admin', 'admin', 'tech']:
                menu = get_main_menu_tech()
                msg = (
                    f"✅ 绑定成功！\n\n"
                    f"👤 {admin.get('username')}\n"
                    f"🔐 {role_label}\n\n"
                    f"请选择操作："
                )
            else:
                menu = get_main_menu_sales()
                msg = (
                    f"✅ 绑定成功！\n\n"
                    f"👋 姓名: {admin.get('username')}\n"
                    f"🔐 角色: {role_label}\n\n"
                    f"请选择操作：\n\n"
                    f"📈 本月业绩与佣金请点下方「📊 业绩统计」查看。\n\n"
                    f"📢 全行业短信群发，AI语音，渗透数据！\n"
                    f"所有信息以官网 https://www.kaolach.com/ 展示为准！"
                )
            await update.message.reply_text(msg, reply_markup=menu)
            context.user_data['waiting_for'] = None
        else:
            await update.message.reply_text(
                f"❌ 绑定失败: {result.get('msg', '未知错误')}",
                reply_markup=get_back_menu()
            )
        return
    
    if waiting_for == 'account_bind_code':
        code = text.strip()
        if not code.isdigit() or len(code) != 6:
            await update.message.reply_text("❌ 请输入6位数字绑定码")
            return

        res = await api.bind_account_by_code(code, tg_id, update.effective_user.username or update.effective_user.first_name)
        if res.get("success"):
            account_id = res.get("account_id")
            context.user_data['account_id'] = account_id
            context.user_data['user_type'] = 'customer'
            context.user_data['waiting_for'] = None

            await update.message.reply_text(
                f"✅ 绑定成功！\n\n"
                f"📦 账户: {res.get('account_name')}\n"
                f"🆔 ID: {account_id}\n\n"
                f"发送 /start 返回主菜单。",
                reply_markup=get_main_menu_customer()
            )
        else:
            await update.message.reply_text(f"❌ 绑定失败: {res.get('msg', '码无效或已过期')}", reply_markup=get_back_menu())
        return

    # 处理工单标题输入
    if waiting_for == 'ticket_title':
        if len(text) < 3:
            await update.message.reply_text("❌ 标题太短，请至少输入3个字符")
            return
        
        context.user_data['ticket_title'] = text
        await update.message.reply_text(
            f"📝 工单标题: {text}\n\n"
            f"请详细描述您的问题：",
            reply_markup=get_back_menu()
        )
        context.user_data['waiting_for'] = 'ticket_description'
        return
    
    if waiting_for == 'ticket_description':
        ticket_type = context.user_data.get('ticket_type', 'other')
        ticket_title = context.user_data.get('ticket_title', '无标题')
        
        # 通过 API 获取当前活跃绑定的 account_id
        verify = await api.verify_bot_user(tg_id)
        if not verify or not verify.get("account_id"):
            await update.message.reply_text("❌ 未绑定有效账户，跳转至主菜单", reply_markup=await get_main_menu_guest())
            context.user_data["waiting_for"] = None
            return

        account_id = verify.get("account_id")
        res = await api.create_ticket_internal(
            account_id=account_id,
            tg_user_id=str(tg_id),
            ticket_type=ticket_type,
            title=ticket_title,
            description=text,
            created_by_id=tg_id
        )

        if res.get("success"):
            type_labels = {'test': '测试申请', 'technical': '技术支持', 'billing': '账务问题', 'feedback': '意见反馈'}
            await update.message.reply_text(
                f"✅ 工单提交成功！\n\n"
                f"📋 工单号: {res.get('ticket_no')}\n"
                f"📝 类型: {type_labels.get(ticket_type, ticket_type)}\n"
                f"📌 标题: {ticket_title}\n\n"
                f"我们会尽快处理您的工单，请耐心等待。",
                reply_markup=get_main_menu_customer()
            )
        else:
            await update.message.reply_text(f"❌ 工单提交失败: {res.get('message', '未知错误')}", reply_markup=get_back_menu())
        context.user_data['waiting_for'] = None
        return
    
    # 处理短信审核（只审核文案，无需号码）
    if waiting_for == 'sms_audit_content':
        content = text.strip()
        if not content:
            await update.message.reply_text("❌ 文案内容不能为空", reply_markup=get_back_menu())
            return
        if len(content) > 1000:
            await update.message.reply_text("❌ 短信内容最多1000字符", reply_markup=get_back_menu())
            return
        
        # 统一由后端处理账号查找/余额校验/审核逻辑
        res = await api.submit_sms_approval(
            tg_id=tg_id,
            account_id=context.user_data.get('account_id'),
            content=content,
            sms_submit_mode='audit'
        )
        
        if not res.get("success"):
            await update.message.reply_text(f"❌ 提交失败: {res.get('msg')}", reply_markup=get_back_menu())
            return
        
        if res.get("need_audit"):
            # 转发到 TG 群组
            target_group_id = res.get("target_group_id")
            if target_group_id:
                try:
                    msg_text = (
                        f"📋 *短信文案待审核*\n\n"
                        f"👤 客户: {update.effective_user.mention_html()}\n"
                        f"🆔 TG ID: `{tg_id}`\n"
                        f"📦 账户: {res.get('account_name')}\n"
                        f"📝 提交模式: 只审文案\n\n"
                        f"📄 内容:\n<pre>{content}</pre>"
                    )
                    kb = [
                        [
                            InlineKeyboardButton("✅ 批准", callback_data=f"sms_app_{res.get('approval_id')}_yes"),
                            InlineKeyboardButton("❌ 拒绝", callback_data=f"sms_app_{res.get('approval_id')}_no")
                        ]
                    ]
                    await context.bot.send_message(
                        chat_id=target_group_id,
                        text=msg_text,
                        parse_mode='HTML',
                        reply_markup=InlineKeyboardMarkup(kb)
                    )
                except Exception as e:
                    logger.error(f"转发审核到群组失败: {e}")

            await update.message.reply_text(
                "✅ 文案已提交人工审核，批准后我们会立即通知您。",
                reply_markup=get_main_menu_customer()
            )
        else:
            await update.message.reply_text(
                "✅ 提交成功 (免审)",
                reply_markup=get_main_menu_customer()
            )
        
        context.user_data['waiting_for'] = None
        return
    
    # 处理短信发送（发送短信入口，需号码+内容）
    if waiting_for == 'sms_content':
        parts = re.split(r'\s+', text, 1)
        if len(parts) != 2:
            await update.message.reply_text(
                "❌ 格式错误\n\n请发送: 号码 内容\n例如: +8613800138000 您的验证码是123456",
                reply_markup=get_back_menu()
            )
            return
        phone, content = parts[0].strip(), (parts[1].strip() if len(parts) > 1 else '')
        if not phone or not content:
            await update.message.reply_text("❌ 号码和内容不能为空", reply_markup=get_back_menu())
            return
        # 简化校验逻辑，生产环境应通过后端 API 校验
        import re
        if not re.match(r'^\+?[1-9]\d{1,14}$', phone):
            await update.message.reply_text(
                "❌ 号码格式错误\n\n正确示例: +8613800138000 或 +66812345678",
                reply_markup=get_back_menu()
            )
            return
        if len(content) > 1000:
            await update.message.reply_text("❌ 短信内容最多1000字符", reply_markup=get_back_menu())
            return
        try:
            # 统一由后端处理路由/审核逻辑
            res = await api.submit_sms_approval(
                tg_id=tg_id,
                account_id=context.user_data.get('account_id'),
                content=content,
                phone=phone,
                sms_submit_mode='direct'
            )
            
            if not res.get("success"):
                await update.message.reply_text(f"❌ 提交失败: {res.get('msg')}", reply_markup=get_back_menu())
                return
                
            if res.get("need_audit"):
                # 转发到 TG 群组
                target_group_id = res.get("target_group_id")
                if target_group_id:
                    try:
                        msg_text = (
                            f"📋 *短信待人工审核*\n\n"
                            f"👤 客户: {update.effective_user.mention_html()}\n"
                            f"🆔 TG ID: `{tg_id}`\n"
                            f"📦 账户: {res.get('account_name')}\n"
                            f"📱 号码: `{phone}` ({res.get('country_name', '未知')})\n\n"
                            f"📄 内容:\n<pre>{content}</pre>"
                        )
                        kb = [
                            [
                                InlineKeyboardButton("✅ 批准", callback_data=f"sms_app_{res.get('approval_id')}_yes"),
                                InlineKeyboardButton("❌ 拒绝", callback_data=f"sms_app_{res.get('approval_id')}_no")
                            ]
                        ]
                        await context.bot.send_message(
                            chat_id=target_group_id,
                            text=msg_text,
                            parse_mode='HTML',
                            reply_markup=InlineKeyboardMarkup(kb)
                        )
                    except Exception as e:
                        logger.error(f"转发审核到群组失败: {e}")

                await update.message.reply_text(
                    "✅ 已提交审核，批准后将为您自动发送，请留意通知。",
                    reply_markup=get_main_menu_customer()
                )
            else:
                # 系统免审发送成功
                msg = "✅ 发送成功"
                if res.get("message_id"):
                    msg += f"\n🆔 消息ID: `{res.get('message_id')}`"
                if res.get("cost"):
                    msg += f"\n💰 费用: {res.get('cost')} {res.get('currency', 'USD')}"
                
                await update.message.reply_text(
                    msg,
                    parse_mode='Markdown',
                    reply_markup=get_main_menu_customer()
                )
            
            context.user_data['waiting_for'] = None
            return
        except Exception as e:
            logger.exception("短信提交异常: %s", e)
            context.user_data['waiting_for'] = None
            await update.message.reply_text(
                "❌ 系统错误，请稍后重试。",
                reply_markup=get_main_menu_customer(),
            )
        return


from telegram.ext import MessageHandler, filters

# 短信审核媒体：含从其他群复制的图（任意附件形态），排除语音以免误触
_sms_approval_media_filters = filters.ChatType.GROUPS & ~filters.VOICE & (
    filters.PHOTO
    | filters.VIDEO
    | filters.ANIMATION
    | filters.Sticker.ALL
    | filters.Document.ALL
    | filters.VIDEO_NOTE
)

# 导出回调处理器
menu_handlers = [
    CallbackQueryHandler(
        handle_menu_callback,
        # kb_ 不能覆盖 kb_dl_*（第三字符为 d）；kb_noop 同理，须单独列出
        pattern=r'^(?!menu_register$|menu_sms_test$|reg_)(?:sales_login_|okcc_refresh_|menu_|biz_|btk_sms$|btk_voice$|btk_data$|kb_|kb_dl_|kb_noop|ticket_type_|country_|tpl_|pricing_|approve_|reject_|send_approved_sms_|sms_approval_skip_|process_|ticket_detail_|close_ticket_|back_|my_cust_)'
    ),
    # 短信审核回复：图片与图片类文档需在 TEXT 之外单独处理
    MessageHandler(
        _sms_approval_media_filters & ~filters.COMMAND,
        handle_sms_approval_reply_media,
    ),
    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input),
]
