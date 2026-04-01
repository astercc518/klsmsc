"""
菜单处理器 - 使用按钮菜单替代命令
"""
import time

from telegram import Message, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from bot.utils import get_session, get_valid_customer_binding_and_account, logger
from app.modules.common.telegram_binding import TelegramBinding
from app.modules.common.account import Account, AccountChannel
from app.modules.sms.channel import Channel
from app.modules.common.admin_user import AdminUser
from app.modules.common.ticket import Ticket
from app.modules.common.recharge_order import RechargeOrder
from app.modules.common.sms_content_approval import SmsContentApproval
from app.modules.common.system_config import SystemConfig
from sqlalchemy import select, func, desc, text
from datetime import datetime, timedelta
import os
import re
import secrets

# 已处理的供应商审核回复消息 (chat_id, message_id)，防止重复转发
_processed_sms_reply_ids: set = set()
_MAX_PROCESSED_IDS = 5000

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
}


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
            InlineKeyboardButton("📋 客户工单", callback_data="menu_customer_tickets"),
        ],
        [
            InlineKeyboardButton("📊 业绩统计", callback_data="menu_sales_stats"),
            InlineKeyboardButton("📚 业务知识", callback_data="menu_business_knowledge"),
        ],
        [
            InlineKeyboardButton("📋 报价查询", callback_data="menu_pricing"),
            InlineKeyboardButton("❓ 帮助", callback_data="menu_help"),
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
    ]
    return InlineKeyboardMarkup(keyboard)


def get_main_menu_guest():
    """游客菜单 — 授权码开户为主入口"""
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
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


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
        await query.edit_message_text(
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
        await query.edit_message_text(
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
    
    # 创建邀请 - 转到sales模块的邀请流程
    if data == "menu_invite":
        # 检查是否是销售
        async with get_session() as db:
            admin_result = await db.execute(
                select(AdminUser).where(
                AdminUser.tg_id == tg_id,
                AdminUser.status == 'active'
            )
            )
            admin = admin_result.scalar_one_or_none()
            
            if not admin or admin.role not in ['sales', 'super_admin', 'admin']:
                await query.edit_message_text(
                    "❌ 您没有创建邀请的权限",
                    reply_markup=get_back_menu()
                )
                return
            
            context.user_data['sales_id'] = admin.id
            context.user_data['sales_name'] = admin.real_name
        
        await query.edit_message_text(
            "🎯 创建开户邀请\n\n请选择业务类型：",
            reply_markup=get_business_type_menu()
        )
        return
    
    # 处理业务类型选择（邀请流程）
    if data.startswith("biz_"):
        biz_type = data.replace("biz_", "")
        context.user_data['business_type'] = biz_type
        
        biz_label = {"sms": "短信", "voice": "语音", "data": "数据"}.get(biz_type, biz_type)
        
        # 获取该业务类型下的所有国家
        from app.modules.common.account_template import AccountTemplate
        
        async with get_session() as db:
            result = await db.execute(
                select(AccountTemplate.country_code, AccountTemplate.country_name)
                .where(
                    AccountTemplate.business_type == biz_type,
                    AccountTemplate.status == "active"
                )
                .distinct()
                .order_by(AccountTemplate.country_code)
            )
            countries = result.all()
        
        if not countries:
            await query.edit_message_text(
                f"❌ 暂无 {biz_label} 业务的可用模板\n\n请联系管理员在后台添加账户模板",
                reply_markup=get_back_menu()
            )
            return
        
        # 显示国家选择
        keyboard = []
        row = []
        for country_code, _ in countries:
            # 使用映射表获取中文名称，避免编码问题
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
    
    # 我的客户
    if data == "menu_my_customers":
        await show_my_customers(query, context)
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
        await query.answer()
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
    
    # 处理国家选择（邀请流程）
    if data.startswith("country_"):
        country_code = data.replace("country_", "")
        context.user_data['country_code'] = country_code
        biz_type = context.user_data.get('business_type', 'sms')
        
        biz_label = {"sms": "短信", "voice": "语音", "data": "数据"}.get(biz_type, biz_type)
        
        # 获取该国家的模板
        from app.modules.common.account_template import AccountTemplate
        
        async with get_session() as db:
            result = await db.execute(
                select(AccountTemplate)
                .where(
                    AccountTemplate.business_type == biz_type,
                    AccountTemplate.country_code == country_code,
                    AccountTemplate.status == "active"
                )
                .order_by(AccountTemplate.template_name)
            )
            templates = result.scalars().all()
        
        if not templates:
            await query.edit_message_text(
                f"❌ 该国家暂无可用模板",
                reply_markup=get_back_menu()
            )
            return
        
        keyboard = []
        for tpl in templates:
            price = float(tpl.default_price) if tpl.default_price else 0
            label = f"{tpl.template_name}  ${price:.4f}"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"tpl_{tpl.id}")])
        keyboard.append([InlineKeyboardButton("🔙 返回", callback_data=f"biz_{biz_type}")])

        country_label = COUNTRY_NAMES.get(country_code, country_code)
        await query.edit_message_text(
            f"🎯 创建开户授权码\n\n"
            f"📦 业务类型: {biz_label}\n"
            f"🌍 国家: {country_label}\n\n"
            f"请选择开户模板：",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # 处理模板选择（邀请流程）
    if data.startswith("tpl_"):
        template_id = int(data.replace("tpl_", ""))
        context.user_data['template_id'] = template_id
        
        from app.modules.common.account_template import AccountTemplate
        
        async with get_session() as db:
            result = await db.execute(
                select(AccountTemplate).where(AccountTemplate.id == template_id)
            )
            template = result.scalar_one_or_none()
        
        if not template:
            await query.edit_message_text(
                "❌ 模板不存在",
                reply_markup=get_back_menu()
            )
            return
        
        country_label = COUNTRY_NAMES.get(template.country_code, template.country_code)
        template_name = template.template_name or f"{country_label}标准版"
        price = float(template.default_price) if template.default_price else 0

        context.user_data['template_info'] = {
            'name': template_name,
            'default_price': price,
            'country': template.country_code,
        }
        context.user_data['template_name'] = template_name

        await query.edit_message_text(
            f"🎯 创建开户授权码\n\n"
            f"📋 模板: {template_name}\n"
            f"🌍 国家: {country_label}\n"
            f"💰 底价: ${price:.4f}\n\n"
            f"请输入客户单价（USD）：\n"
            f"例如: 0.05",
            reply_markup=get_back_menu()
        )
        context.user_data['waiting_for'] = 'invite_price'
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
            async with get_session() as db:
                result = await db.execute(
                    select(SmsContentApproval, Account)
                    .join(Account, SmsContentApproval.account_id == Account.id)
                    .where(SmsContentApproval.id == approval_id)
                )
                row = result.first()
                if row:
                    approval, account = row
                    if approved:
                        await _notify_customer_approved(context, approval, account)
                    else:
                        await _notify_customer_rejected(context, approval)
            await query.answer("已跳过，已通知客户")
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
    
    # 客户工单
    if data == "menu_customer_tickets":
        await show_customer_tickets(query, context)
        return
    
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

    async with get_session() as db:
        binding, account = await get_valid_customer_binding_and_account(db, tg_id)

        if not binding or not account:
            await query.edit_message_text(
                "❌ 未绑定有效账户或该账户已停用/删除，请使用授权码开户或重新绑定。",
                reply_markup=get_back_menu()
            )
            return

        tg_bound = "已绑定" if account.tg_id else "未绑定"
        tg_info = f"@{account.tg_username}" if account.tg_username else str(account.tg_id or "-")

        await query.edit_message_text(
            f"👤 账户信息\n\n"
            f"🆔 账户ID: {account.id}\n"
            f"👤 用户名: {account.account_name}\n"
            f"💰 余额: ${float(account.balance or 0):.4f} {account.currency}\n"
            f"📊 状态: {'正常' if account.status == 'active' else account.status}\n"
            f"📱 Telegram: {tg_bound} ({tg_info})\n"
            f"📅 创建时间: {account.created_at.strftime('%Y-%m-%d') if account.created_at else 'N/A'}",
            reply_markup=get_back_menu()
        )


async def show_main_menu(query, context: ContextTypes.DEFAULT_TYPE):
    """显示主菜单"""
    tg_id = query.from_user.id
    
    async with get_session() as db:
        # 检查是否是员工
        admin_result = await db.execute(
            select(AdminUser).where(
                AdminUser.tg_id == tg_id,
                AdminUser.status == 'active'
            )
        )
        admin = admin_result.scalar_one_or_none()
        
        if admin:
            role_map = {
                'super_admin': '超级管理员',
                'admin': '管理员', 
                'sales': '销售',
                'finance': '财务',
                'tech': '技术'
            }
            role_label = role_map.get(admin.role, admin.role)
            
            if admin.role in ['super_admin', 'admin', 'tech']:
                menu = get_main_menu_tech()
                msg = f"👋 {admin.real_name or admin.username}\n🔐 {role_label}\n\n请选择操作："
            else:
                menu = get_main_menu_sales()
                monthly = float(admin.monthly_commission or 0)
                msg = (
                    f"👋 姓名: {admin.real_name or admin.username}\n"
                    f"🔐 角色: {role_label}\n"
                    f"💰 本月佣金: ${monthly:.2f}\n\n"
                    f"请选择操作：\n\n"
                    f"📢 全行业短信群发，AI语音，渗透数据！\n"
                    f"所有信息以官网 https://www.kaolach.com/ 展示为准！"
                )
            await query.edit_message_text(msg, reply_markup=menu)
            return
        
        # 检查是否是客户（须账户未删除且非 closed，与 /start 一致）
        binding, account = await get_valid_customer_binding_and_account(db, tg_id)

        if binding and account:
            balance_str = f"${account.balance:.2f}"
            context.user_data["account_id"] = account.id
            context.user_data["user_type"] = "customer"
            await query.edit_message_text(
                f"👋 欢迎回来\n"
                f"💰 余额: {balance_str}\n\n"
                f"📢 全行业短信群发，AI语音，渗透数据！\n"
                f"所有信息以官网 https://www.kaolach.com/ 展示为准！\n\n"
                f"请选择操作：",
                reply_markup=get_main_menu_customer()
            )
            return

        context.user_data.pop("account_id", None)
        context.user_data.pop("user_type", None)
        await query.edit_message_text(
            "👋 欢迎使用 TG 业务助手\n\n"
            "您的账户已停用或已删除，请使用授权码开户或重新绑定。\n\n"
            "请选择操作：",
            reply_markup=get_main_menu_guest()
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


async def show_balance(query, context):
    """显示余额"""
    tg_id = query.from_user.id
    
    async with get_session() as db:
        _binding, account = await get_valid_customer_binding_and_account(db, tg_id)

        if not account:
            await query.edit_message_text(
                "❌ 未绑定有效账户或该账户已停用/删除。",
                reply_markup=get_back_menu()
            )
            return

        await query.edit_message_text(
            f"💰 账户余额\n\n"
            f"账户: {account.account_name}\n"
            f"余额: ${account.balance:.4f} {account.currency}\n"
            f"状态: {'正常' if account.status == 'active' else '已冻结'}",
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
    """显示发送记录"""
    tg_id = query.from_user.id
    
    async with get_session() as db:
        binding, account = await get_valid_customer_binding_and_account(db, tg_id)
        if not binding or not account:
            await query.edit_message_text(
                "❌ 未绑定有效账户或该账户已停用/删除。",
                reply_markup=get_back_menu()
            )
            return

        # 查询最近7天发送统计
        from app.modules.sms.sms_log import SmsLog
        
        seven_days_ago = datetime.now() - timedelta(days=7)
        
        # 总发送数
        total_result = await db.execute(
            select(func.count(SmsLog.id)).where(
                SmsLog.account_id == binding.account_id,
                SmsLog.created_at >= seven_days_ago
            )
        )
        total_count = total_result.scalar() or 0
        
        # 成功数
        success_result = await db.execute(
            select(func.count(SmsLog.id)).where(
                SmsLog.account_id == binding.account_id,
                SmsLog.created_at >= seven_days_ago,
                SmsLog.status == 'delivered'
            )
        )
        success_count = success_result.scalar() or 0
        
        # 失败数
        failed_result = await db.execute(
            select(func.count(SmsLog.id)).where(
                SmsLog.account_id == binding.account_id,
                SmsLog.created_at >= seven_days_ago,
                SmsLog.status == 'failed'
            )
        )
        failed_count = failed_result.scalar() or 0
        
        # 费用统计
        cost_result = await db.execute(
            select(func.sum(SmsLog.cost)).where(
                SmsLog.account_id == binding.account_id,
                SmsLog.created_at >= seven_days_ago
            )
        )
        total_cost = cost_result.scalar() or 0
        
        success_rate = (success_count / total_count * 100) if total_count > 0 else 0
        
        await query.edit_message_text(
            f"📊 发送统计 (近7天)\n\n"
            f"📤 总发送: {total_count} 条\n"
            f"✅ 成功: {success_count} 条\n"
            f"❌ 失败: {failed_count} 条\n"
            f"📈 成功率: {success_rate:.1f}%\n"
            f"💰 消费: ${total_cost:.4f}\n\n"
            f"更多详情请登录Web后台查看",
            reply_markup=get_back_menu()
        )


async def show_tickets(query, context):
    """显示工单列表"""
    tg_id = query.from_user.id
    
    async with get_session() as db:
        binding, account = await get_valid_customer_binding_and_account(db, tg_id)
        if not binding or not account:
            await query.edit_message_text(
                "❌ 未绑定有效账户或该账户已停用/删除。",
                reply_markup=get_back_menu()
            )
            return

        # 查询最近工单
        tickets_result = await db.execute(
            select(Ticket).where(
                Ticket.account_id == binding.account_id
            ).order_by(desc(Ticket.created_at)).limit(5)
        )
        tickets = tickets_result.scalars().all()
        
        if not tickets:
            await query.edit_message_text(
                "📋 我的工单\n\n"
                "暂无工单记录\n\n"
                "点击下方按钮提交新工单",
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
        for t in tickets:
            status_label = status_map.get(t.status, t.status)
            lines.append(f"• {t.ticket_no}: {t.title[:15]}... {status_label}")
        
        # 构建按钮，显示每个工单详情
        keyboard = []
        for t in tickets:
            keyboard.append([InlineKeyboardButton(
                f"📄 {t.ticket_no}", 
                callback_data=f"ticket_detail_{t.id}"
            )])
        keyboard.append([InlineKeyboardButton("📝 提交新工单", callback_data="menu_new_ticket")])
        keyboard.append([InlineKeyboardButton("🔙 返回主菜单", callback_data="menu_main")])
        
        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def handle_sales_quick_login(query, context):
    """销售点击「快捷登录」：调用后端签发模拟登录链接"""
    from bot.config import settings as bot_settings

    tg_id = query.from_user.id
    raw = query.data or ""
    try:
        account_id = int(raw.replace("sales_login_", ""))
    except ValueError:
        await query.edit_message_text("❌ 参数无效", reply_markup=get_back_menu())
        return

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
        async with httpx.AsyncClient(timeout=25.0) as client:
            r = await client.post(
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


async def show_my_customers(query, context):
    """显示我的客户（基本信息 + 快捷登录）"""
    tg_id = query.from_user.id
    
    async with get_session() as db:
        # 获取销售员工信息
        admin_result = await db.execute(
            select(AdminUser).where(
                AdminUser.tg_id == tg_id,
                AdminUser.status == 'active'
            )
        )
        admin = admin_result.scalar_one_or_none()
        
        if not admin or admin.role not in ['sales', 'super_admin', 'admin']:
            await query.edit_message_text(
                "❌ 仅销售可使用「我的客户」",
                reply_markup=get_back_menu()
            )
            return
        
        # 查询该销售名下客户（未删除、正常）；单条展示字段较多，限制条数避免超出 Telegram 4096 字
        customers_result = await db.execute(
            select(Account).where(
                Account.sales_id == admin.id,
                Account.status == 'active',
                Account.is_deleted == False,  # noqa: E712
            ).order_by(desc(Account.created_at)).limit(20)
        )
        all_customers = customers_result.scalars().all()

        if not all_customers:
            await query.edit_message_text(
                "👥 我的客户\n\n"
                "暂无客户记录\n\n"
                "通过「创建开户邀请」邀请新客户",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🎯 创建邀请", callback_data="menu_invite")],
                    [InlineKeyboardButton("🔙 返回", callback_data="menu_main")]
                ])
            )
            return

        total_customers = len(all_customers)
        total_balance = sum(float(c.balance or 0) for c in all_customers)
        display_note = ""
        customers = all_customers
        if len(all_customers) > 10:
            display_note = f"\n（仅展示前 10 位，共 {total_customers} 位，其余请登录管理后台查看）\n"
            customers = all_customers[:10]

        # 批量解析各账户优先通道（默认优先，其次 priority）
        acc_ids = [c.id for c in customers]
        channel_best: dict = {}
        if acc_ids:
            ch_rows = await db.execute(
                select(
                    AccountChannel.account_id,
                    AccountChannel.is_default,
                    AccountChannel.priority,
                    Channel.channel_name,
                    Channel.channel_code,
                )
                .join(Channel, Channel.id == AccountChannel.channel_id)
                .where(AccountChannel.account_id.in_(acc_ids))
            )
            for aid, is_def, pri, ch_name, ch_code in ch_rows.all():
                score = (1 if is_def else 0, pri or 0)
                if aid not in channel_best or score > channel_best[aid][0]:
                    channel_best[aid] = (score, ch_name or "", ch_code or "")

        def _channel_line(aid: int) -> str:
            t = channel_best.get(aid)
            if not t:
                return "-"
            _, nm, code = t
            if nm and code:
                return f"{nm} ({code})"
            return nm or code or "-"

        lines = [
            f"👥 我的客户（共 {total_customers} 个）\n",
            f"💰 总余额: ${total_balance:.2f}",
            display_note,
            "────────\n",
        ]

        keyboard = []
        for c in customers:
            balance = float(c.balance or 0)
            up = float(c.unit_price or 0)
            cc = (c.country_code or "").strip().upper()
            country_label = COUNTRY_NAMES.get(cc, cc) if cc else "-"
            if cc and country_label != cc:
                country_disp = f"{country_label} ({cc})"
            elif cc:
                country_disp = cc
            else:
                country_disp = "-"
            if c.tg_username:
                tg_disp = f"@{c.tg_username}"
            elif c.tg_id:
                tg_disp = str(c.tg_id)
            else:
                tg_disp = "-"

            lines.append(
                f"名称：{c.account_name}\n"
                f"TG：{tg_disp}\n"
                f"国家：{country_disp}\n"
                f"通道：{_channel_line(c.id)}\n"
                f"单价：${up:.4f}/条\n"
                f"余额：${balance:.2f}\n"
                "────────\n"
            )
            # 按钮文案须短；callback_data ≤64 字节
            btn_text = c.account_name.strip() if c.account_name else str(c.id)
            if len(btn_text) > 16:
                btn_text = btn_text[:14] + "…"
            keyboard.append(
                [InlineKeyboardButton(f"🔐 {btn_text}", callback_data=f"sales_login_{c.id}")]
            )

        lines.append("点击对应「🔐」生成浏览器登录链接（模拟登录客户）。")
        
        keyboard.append([InlineKeyboardButton("🎯 创建新邀请", callback_data="menu_invite")])
        keyboard.append([InlineKeyboardButton("🔙 返回", callback_data="menu_main")])
        
        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def show_business_knowledge(query, context, category=None):
    """显示业务知识库：按语音/短信/数据分类，或按分类展示文章列表"""
    from app.modules.common.knowledge import KnowledgeArticle, KnowledgeAttachment
    from sqlalchemy.orm import selectinload

    cat_map = {"sms": "📱短信知识", "voice": "📞语音知识", "data": "📊数据知识", "general": "📋通用知识"}

    # 第一层：无 category 时显示业务类型选择
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

    # 第二层：按分类展示文章列表
    async with get_session() as db:
        result = await db.execute(
            select(KnowledgeArticle)
            .options(selectinload(KnowledgeArticle.attachments))
            .where(KnowledgeArticle.status == "published", KnowledgeArticle.category == category)
            .order_by(KnowledgeArticle.updated_at.desc())
            .limit(20)
        )
        articles = result.scalars().all()

    if not articles:
        cat_label = cat_map.get(category, category)
        text = f"📚 {cat_label}\n\n暂无知识内容。"
        keyboard = [
            [InlineKeyboardButton("🔙 返回知识库", callback_data="menu_business_knowledge")],
            [InlineKeyboardButton("🔙 返回主菜单", callback_data="menu_main")],
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    cat_label = cat_map.get(category, category)
    keyboard = []
    for a in articles:
        label = (a.title[:20] + "...") if len(a.title or "") > 20 else (a.title or "无标题")
        keyboard.append([InlineKeyboardButton(label, callback_data=f"kb_article_{a.id}")])
    keyboard.append([InlineKeyboardButton("🔙 返回知识库", callback_data="menu_business_knowledge")])
    keyboard.append([InlineKeyboardButton("🔙 返回主菜单", callback_data="menu_main")])

    text = f"📚 {cat_label}\n\n请选择要查阅的内容："
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def show_knowledge_article(query, context, article_id: int):
    """显示单篇知识文章详情，并提供附件下载按钮"""
    from app.modules.common.knowledge import KnowledgeArticle, KnowledgeAttachment
    from sqlalchemy.orm import selectinload

    async with get_session() as db:
        result = await db.execute(
            select(KnowledgeArticle)
            .options(selectinload(KnowledgeArticle.attachments))
            .where(KnowledgeArticle.id == article_id, KnowledgeArticle.status == "published")
        )
        article = result.scalar_one_or_none()

    if not article:
        await query.edit_message_text("❌ 文章不存在或已下架", reply_markup=get_back_menu())
        return

    # 增加浏览次数
    async with get_session() as db:
        r = await db.execute(select(KnowledgeArticle).where(KnowledgeArticle.id == article_id))
        a = r.scalar_one_or_none()
        if a:
            a.view_count = (a.view_count or 0) + 1
            await db.commit()

    content = (article.content or "").strip() or "（无正文）"
    # Telegram 消息长度限制 4096
    if len(content) > 3500:
        content = content[:3500] + "\n\n...(内容过长，请登录Web端查看全文)"

    att_text = ""
    if article.attachments:
        att_text = "\n\n📎 附件（点击下方按钮下载）："

    cat_map = {"sms": "📱短信知识", "voice": "📞语音知识", "data": "📊数据知识", "general": "📋通用知识"}
    cat_label = cat_map.get(article.category or "general", article.category)
    text = f"📚 {article.title}\n\n{cat_label} | 浏览 {article.view_count or 0}\n\n{content}{att_text}"[:4090]

    # 每个附件一个下载按钮
    keyboard = []
    for att in (article.attachments or [])[:10]:
        short_name = att.file_name[:25] + "…" if len(att.file_name or "") > 25 else (att.file_name or "附件")
        keyboard.append([InlineKeyboardButton(f"📥 {short_name}", callback_data=f"kb_dl_{att.id}")])
    if len(article.attachments or []) > 10:
        keyboard.append([InlineKeyboardButton("...更多附件请登录Web端下载", callback_data="kb_noop")])
    keyboard.append([InlineKeyboardButton("🔙 返回知识库", callback_data=f"kb_cat_{article.category or 'general'}")])
    keyboard.append([InlineKeyboardButton("🔙 返回主菜单", callback_data="menu_main")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def send_knowledge_attachment(query, context, attachment_id: int):
    """发送知识库附件给用户（Telegram 文档）"""
    from app.modules.common.knowledge import KnowledgeAttachment
    from pathlib import Path

    await query.answer("正在发送文件...")

    async with get_session() as db:
        result = await db.execute(select(KnowledgeAttachment).where(KnowledgeAttachment.id == attachment_id))
        att = result.scalar_one_or_none()

    if not att:
        await query.answer("附件不存在", show_alert=True)
        return

    # 知识库文件路径（与 backend 一致）
    KNOWLEDGE_DIR = Path("/app/data/knowledge")
    file_path = KNOWLEDGE_DIR / att.file_path

    if not file_path.exists():
        await query.answer("文件不存在或已删除", show_alert=True)
        return

    try:
        with open(file_path, "rb") as f:
            await context.bot.send_document(
                chat_id=query.message.chat_id,
                document=f,
                filename=att.file_name,
                caption=f"📎 {att.file_name}",
            )
        await query.answer("已发送", show_alert=False)
    except Exception as e:
        logger.exception("发送知识附件失败: %s", e)
        await query.answer("发送失败，请稍后重试", show_alert=True)


async def show_commission(query, context):
    """显示佣金"""
    tg_id = query.from_user.id
    
    async with get_session() as db:
        admin_result = await db.execute(
            select(AdminUser).where(
                AdminUser.tg_id == tg_id,
                AdminUser.status == 'active'
            )
        )
        admin = admin_result.scalar_one_or_none()
        
        if admin:
            await query.edit_message_text(
                f"💰 我的佣金\n\n"
                f"本月佣金: ${admin.monthly_commission or 0:.2f}\n"
                f"佣金比例: {(admin.commission_rate or 0) * 100:.1f}%\n\n"
                f"佣金每月15日结算",
                reply_markup=get_back_menu()
            )
        else:
            await query.edit_message_text(
                "❌ 无法获取佣金信息",
                reply_markup=get_back_menu()
            )


async def show_pending_tickets(query, context):
    """显示待审核工单"""
    async with get_session() as db:
        # 查询待处理工单
        tickets_result = await db.execute(
            select(Ticket).where(
                Ticket.status.in_(['open', 'assigned', 'in_progress'])
            ).order_by(desc(Ticket.created_at)).limit(10)
        )
        tickets = tickets_result.scalars().all()
        
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
            emoji = priority_emoji.get(t.priority, '🟢')
            type_label = {'test': '测试', 'technical': '技术', 'billing': '账务', 'feedback': '反馈'}.get(t.ticket_type, t.ticket_type)
            lines.append(f"{emoji} {t.ticket_no} [{type_label}] {t.title[:12]}...")
        
        # 构建按钮
        keyboard = []
        for t in tickets[:5]:
            keyboard.append([InlineKeyboardButton(
                f"处理 {t.ticket_no}", 
                callback_data=f"process_ticket_{t.id}"
            )])
        keyboard.append([InlineKeyboardButton("🔙 返回", callback_data="menu_main")])
        
        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def show_pending_recharge(query, context):
    """显示待审核充值"""
    async with get_session() as db:
        # 查询待审核充值
        recharge_result = await db.execute(
            select(RechargeOrder, Account)
            .join(Account, RechargeOrder.account_id == Account.id)
            .where(RechargeOrder.status == 'pending')
            .order_by(desc(RechargeOrder.created_at))
            .limit(10)
        )
        orders = recharge_result.all()
        
        if not orders:
            await query.edit_message_text(
                "💳 待审核充值\n\n"
                "🎉 暂无待审核充值申请",
                reply_markup=get_back_menu()
            )
            return
        
        lines = [f"💳 待审核充值 ({len(orders)}笔)\n"]
        
        for order, account in orders:
            lines.append(f"• {order.order_no}: ${order.amount} ({account.account_name})")
        
        # 构建按钮
        keyboard = []
        for order, account in orders[:5]:
            keyboard.append([
                InlineKeyboardButton(f"✅ 通过 {order.order_no[:8]}", callback_data=f"approve_recharge_{order.id}"),
                InlineKeyboardButton(f"❌ 拒绝", callback_data=f"reject_recharge_{order.id}")
            ])
        keyboard.append([InlineKeyboardButton("🔙 返回", callback_data="menu_main")])
        
        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def show_pricing_menu(query, context, tg_id: int):
    """报价查询入口 - 仅销售/技术可用"""
    async with get_session() as db:
        admin_result = await db.execute(
            select(AdminUser).where(
                AdminUser.tg_id == tg_id,
                AdminUser.status == 'active'
            )
        )
        admin = admin_result.scalar_one_or_none()
        if not admin or admin.role not in ['sales', 'super_admin', 'admin']:
            await query.edit_message_text(
                "❌ 仅销售/管理员可使用报价查询",
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


async def _get_bot_config(db) -> dict:
    """从 system_config 获取 Bot 配置"""
    result = await db.execute(
        select(SystemConfig.config_key, SystemConfig.config_value).where(
            SystemConfig.config_key.in_([
                'telegram_admin_group_id',
                'telegram_enable_sms_content_review',
            ])
        )
    )
    rows = result.fetchall()
    config = {
        'admin_group_id': os.getenv('TELEGRAM_ADMIN_GROUP_ID', ''),
        'enable_sms_content_review': True,
    }
    for k, v in rows:
        if k == 'telegram_admin_group_id' and v:
            config['admin_group_id'] = v
        elif k == 'telegram_enable_sms_content_review':
            config['enable_sms_content_review'] = (v or 'true').lower() == 'true'
    return config


async def _resolve_supplier_group_for_account(db, account_id: int, admin_group_id: str) -> str:
    """
    从客户账号配置的通道对应的供应商获取 Telegram 群组 ID。
    优先使用资源报价/供应商管理中配置的 telegram_group_id，否则回退到全局 admin_group_id。
    """
    from app.modules.common.account import AccountChannel
    from app.modules.sms.channel import Channel
    from app.modules.sms.supplier import SupplierChannel, Supplier
    from sqlalchemy import text

    try:
        # 1. 优先：获取账户绑定的通道（按优先级）
        ac_result = await db.execute(
            select(AccountChannel.channel_id)
            .where(AccountChannel.account_id == account_id)
            .order_by(AccountChannel.priority.desc())
        )
        channel_ids = [r[0] for r in ac_result.all()]

        # 2. 若账户未绑定通道，则从所有可用通道中查找（账户使用全部通道时）
        if not channel_ids:
            ch_result = await db.execute(
                select(Channel.id)
                .where(
                    Channel.status == 'active',
                    Channel.is_deleted == False
                )
                .order_by(Channel.priority.desc())
            )
            channel_ids = [r[0] for r in ch_result.all()]

        if not channel_ids:
            logger.info("供应商群解析: account_id=%s 无可用通道", account_id)
            return (admin_group_id or '').strip()

        # 3. 使用原生 SQL 直接查询，避免 ORM 加载问题
        placeholders = ",".join([str(int(cid)) for cid in channel_ids])
        sql = text(f"""
            SELECT s.telegram_group_id, s.supplier_name, sc.channel_id
            FROM supplier_channels sc
            JOIN suppliers s ON sc.supplier_id = s.id
            WHERE sc.channel_id IN ({placeholders})
              AND sc.status = 'active'
              AND s.is_deleted = 0
              AND s.telegram_group_id IS NOT NULL
              AND TRIM(s.telegram_group_id) != ''
            LIMIT 1
        """)
        raw_result = await db.execute(sql)
        row = raw_result.first()
        if row and row[0]:
            tg = str(row[0]).strip()
            logger.info("供应商群解析: account_id=%s 解析到 supplier=%s tg=%s", account_id, row[1], tg)
            return tg

        # 4. 回退：ORM 方式再试一次
        for ch_id in channel_ids:
            sc_result = await db.execute(
                select(Supplier.telegram_group_id, Supplier.supplier_name)
                .select_from(SupplierChannel)
                .join(Supplier, SupplierChannel.supplier_id == Supplier.id)
                .where(
                    SupplierChannel.channel_id == ch_id,
                    SupplierChannel.status == 'active',
                    Supplier.is_deleted == False
                )
                .limit(1)
            )
            sc_row = sc_result.first()
            if sc_row and sc_row[0] and str(sc_row[0]).strip():
                tg = str(sc_row[0]).strip()
                logger.info("供应商群解析(ORM): account_id=%s channel_id=%s supplier=%s tg=%s", account_id, ch_id, sc_row[1], tg)
                return tg
    except Exception as e:
        logger.warning("解析账户通道对应供应商群组失败: %s", e)
    return (admin_group_id or '').strip()


async def _get_test_countries_for_account(db, account_id: int) -> str:
    """从账户绑定通道获取测试国家列表（用于审核消息展示，不暴露用户信息）"""
    from app.modules.common.account import AccountChannel
    from app.modules.sms.channel_relations import ChannelCountry

    try:
        ac_result = await db.execute(
            select(AccountChannel.channel_id)
            .where(AccountChannel.account_id == account_id)
            .order_by(AccountChannel.priority.desc())
        )
        channel_ids = [r[0] for r in ac_result.all()]
        if not channel_ids:
            return "-"

        placeholders = ",".join([str(int(cid)) for cid in channel_ids])
        sql = text(f"""
            SELECT DISTINCT cc.country_code, cc.country_name
            FROM channel_countries cc
            WHERE cc.channel_id IN ({placeholders})
              AND cc.status = 'active'
            ORDER BY cc.channel_id
            LIMIT 10
        """)
        raw = await db.execute(sql)
        rows = raw.all()
        if not rows:
            return "-"
        names = []
        seen = set()
        for r in rows:
            code = (r[0] or "").strip().upper()[:2]
            name = (r[1] or "").strip()
            if not name and code:
                name = COUNTRY_NAMES.get(code, code)
            if name and name not in seen:
                seen.add(name)
                names.append(name)
        return "、".join(names) if names else "-"
    except Exception as e:
        logger.warning("获取账户测试国家失败: %s", e)
        return "-"


def _voice_unit(resource_type: str) -> str:
    """语音计费模式转显示单位：1+1=按秒，60+60=按分钟，6+1/6+6/30+6等=按计费块"""
    t = (resource_type or "").strip()
    if t == "1+1":
        return "/秒"
    if t == "60+60":
        return "/分钟"
    if re.match(r"^\d+\+\d+$", t):
        return f"/{t}秒"
    return "/分钟"


async def show_pricing_country_by_biz(query, context, biz_type: str):
    """按业务类型显示有报价的国家列表"""
    biz_label = BIZ_LABELS.get(biz_type, biz_type)
    try:
        async with get_session() as db:
            result = await db.execute(
                text("""
                    SELECT DISTINCT country_code FROM supplier_rates
                    WHERE status = 'active' AND business_type = :biz
                    ORDER BY country_code
                """),
                {"biz": biz_type}
            )
            countries = result.fetchall()
    except Exception as e:
        logger.exception("报价国家列表查询失败: %s", e)
        await query.edit_message_text(
            f"❌ 查询失败: {str(e)[:100]}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="menu_pricing")]])
        )
        return

    if not countries:
        await query.edit_message_text(
            f"📋 {biz_label} 报价\n\n暂无{biz_label}报价数据，请先在【资源报价】页面导入",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="menu_pricing")]])
        )
        return

    keyboard = []
    row = []
    for r in countries:
        country_code = r[0]
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


async def show_pricing_by_biz_country(query, context, biz_type: str, country_code: str):
    """显示指定业务类型+国家的报价（数据来源：资源报价 supplier_rates）"""
    country_code = country_code.upper()
    biz_label = BIZ_LABELS.get(biz_type, biz_type)
    try:
        async with get_session() as db:
            result = await db.execute(
                text("""
                    SELECT r.cost_price, r.sell_price, r.currency, s.supplier_name, r.resource_type
                    FROM supplier_rates r
                    JOIN suppliers s ON r.supplier_id = s.id
                    WHERE r.country_code = :cc AND r.business_type = :biz AND r.status = 'active'
                      AND (s.is_deleted = 0 OR s.is_deleted IS NULL)
                    ORDER BY r.cost_price
                """),
                {"cc": country_code, "biz": biz_type}
            )
            rows = result.fetchall()
    except Exception as e:
        logger.exception("报价查询失败: %s", e)
        await query.edit_message_text(
            f"❌ 查询失败: {str(e)[:100]}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data=f"pricing_biz_{biz_type}")]])
        )
        return

    if not rows:
        country_label = COUNTRY_NAMES.get(country_code, country_code)
        await query.edit_message_text(
            f"📋 {biz_label} - {country_label} ({country_code})\n\n暂无报价数据",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data=f"pricing_biz_{biz_type}")]])
        )
        return

    country_label = COUNTRY_NAMES.get(country_code, country_code)
    lines = [f"📋 {biz_label} - {country_label} ({country_code}) 资源报价\n"]
    for row in rows:
        cost = float(row[0])
        sell = float(row[1]) if row[1] else cost
        curr = row[2] or "USD"
        supplier_name = row[3] or "-"
        resource_type = (row[4] or "").strip() if len(row) > 4 else ""
        # 语音业务按时间计费：1+1=按秒，60+60=按分钟，6+1/6+6/30+6等=按计费块；短信/数据按条计费
        unit = _voice_unit(resource_type) if biz_type == "voice" else "/条"
        lines.append(f"• {supplier_name}: 成本 ${cost:.4f} 售价 ${sell:.4f} {curr}{unit}")

    keyboard = [[InlineKeyboardButton("🔙 返回", callback_data=f"pricing_biz_{biz_type}")]]
    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_pricing_all(query, context):
    """显示全部报价（按国家分组，数据来源：资源报价 supplier_rates，使用原生 SQL）"""
    try:
        async with get_session() as db:
            result = await db.execute(
                text("""
                    SELECT r.country_code, r.cost_price, r.sell_price, r.currency, s.supplier_name,
                           r.business_type, r.resource_type
                    FROM supplier_rates r
                    JOIN suppliers s ON r.supplier_id = s.id
                    WHERE r.status = 'active' AND (s.is_deleted = 0 OR s.is_deleted IS NULL)
                    ORDER BY r.country_code, r.cost_price
                """)
            )
            rows = result.fetchall()
    except Exception as e:
        logger.exception("全部报价查询失败: %s", e)
        await query.edit_message_text(
            f"❌ 查询失败: {str(e)[:100]}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="menu_pricing")]])
        )
        return

    if not rows:
        await query.edit_message_text(
            "📋 全部报价\n\n暂无报价数据，请先在【资源报价】页面导入成本表",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="menu_pricing")]])
        )
        return

    # 按国家分组
    by_country = {}
    for row in rows:
        cc, cost_price, sell_price, curr, supplier_name = row[0], row[1], row[2], row[3], row[4]
        biz_type = row[5] if len(row) > 5 else "sms"
        resource_type = (row[6] or "").strip() if len(row) > 6 else ""
        if cc not in by_country:
            by_country[cc] = []
        by_country[cc].append((cost_price, sell_price, curr or "USD", supplier_name or "-", biz_type, resource_type))

    lines = ["📋 全部报价（资源报价）\n"]
    for cc in sorted(by_country.keys()):
        country_label = COUNTRY_NAMES.get(cc, cc)
        lines.append(f"\n🌍 {country_label} ({cc})")
        for item in by_country[cc]:
            cost_price, sell_price, curr, supplier_name = item[0], item[1], item[2], item[3]
            biz_type = item[4] if len(item) > 4 else "sms"
            resource_type = item[5] if len(item) > 5 else ""
            cost = float(cost_price)
            sell = float(sell_price) if sell_price else cost
            unit = _voice_unit(resource_type) if biz_type == "voice" else "/条"
            lines.append(f"  • {supplier_name}: 成本 ${cost:.4f} 售价 ${sell:.4f} {curr}{unit}")

    # Telegram 消息长度限制约 4096
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3997] + "\n\n...(已截断)"

    keyboard = [[InlineKeyboardButton("🔙 返回", callback_data="menu_pricing")]]
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def _notify_customer_approved(context, approval, account):
    """通知客户审核通过（带立即发送按钮）"""
    try:
        has_phone = approval.phone_number and approval.phone_number.strip()
        content_preview = (approval.content or '')[:80] + ('...' if len(approval.content or '') > 80 else '')
        if has_phone:
            notify_text = f"✅ *短信审核已通过*\n\n📱 号码: {approval.phone_number}\n📝 内容: {content_preview}\n\n请点击下方按钮立即发送："
        else:
            notify_text = f"✅ *短信审核已通过*\n\n📝 内容: {content_preview}\n\n请点击「立即发送」，然后填写接收号码。"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 立即发送", callback_data=f"send_approved_sms_{approval.id}")],
            [InlineKeyboardButton("🔙 返回主菜单", callback_data="menu_main")],
        ])
        await context.bot.send_message(
            chat_id=int(approval.tg_user_id),
            text=notify_text,
            parse_mode='Markdown',
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.exception("通知客户审核通过失败: %s", e)


async def _notify_customer_rejected(context, approval):
    """通知客户审核被拒绝"""
    try:
        await context.bot.send_message(
            chat_id=int(approval.tg_user_id),
            text="❌ 您的短信审核未通过\n\n如有疑问请联系客服。",
            reply_markup=get_main_menu_customer(),
        )
    except Exception as e:
        logger.exception("通知客户审核拒绝失败: %s", e)


async def _sync_ticket_for_sms_approval(
    db,
    approval: SmsContentApproval,
    account: Account,
    approved: bool,
    reviewer_name: str,
) -> None:
    """将短信审核结果同步到关联工单（工单管理列表依赖 Ticket.status / review_status）"""
    result = await db.execute(
        select(Ticket)
        .where(
            Ticket.account_id == account.id,
            Ticket.ticket_type == 'test',
        )
        .order_by(desc(Ticket.created_at))
    )
    ano = approval.approval_no or ''
    for ticket in result.scalars().all():
        ex = ticket.extra_data or {}
        linked = ex.get('sms_approval_id') == approval.id
        if not linked and ano and ticket.title and ano in ticket.title:
            linked = True
        if not linked:
            continue
        now = datetime.now()
        if approved:
            ticket.review_status = 'approved'
            ticket.reviewed_at = now
            ticket.review_note = f"业务助手审核通过 — {reviewer_name}"
            ticket.status = 'resolved'
            ticket.resolved_at = now
            ticket.resolution = f"短信内容审核已通过（供应商）。审核人: {reviewer_name}"
        else:
            ticket.review_status = 'rejected'
            ticket.reviewed_at = now
            ticket.review_note = f"业务助手审核拒绝 — {reviewer_name}"
            ticket.status = 'closed'
            ticket.closed_at = now
        break


async def handle_sms_approval_callback(query, context, approval_id: int, approved: bool):
    """处理短信审核通过/拒绝：更新状态、通知客户（通过时带「立即发送」按钮）"""
    reviewer_name = query.from_user.full_name or query.from_user.username or "供应商"
    
    async with get_session() as db:
        result = await db.execute(
            select(SmsContentApproval, Account)
            .join(Account, SmsContentApproval.account_id == Account.id)
            .where(SmsContentApproval.id == approval_id)
        )
        row = result.first()
        
        if not row:
            await query.answer("❌ 审核记录不存在", show_alert=True)
            return
        
        approval, account = row
        
        if approval.status != 'pending':
            await query.answer("该审核已处理", show_alert=True)
            return
        
        if approved:
            approval.status = 'approved'
            approval.reviewed_at = datetime.now()
            approval.reviewed_by_name = reviewer_name
            await _sync_ticket_for_sms_approval(db, approval, account, True, reviewer_name)
            await db.commit()
            
            # 更新供应商群消息（移除按钮）
            try:
                test_countries = await _get_test_countries_for_account(db, account.id)
                await query.edit_message_text(
                    f"✅ *已通过*\n\n"
                    f"🌍 测试国家: {test_countries}\n"
                    f"📝 测试内容:\n{(approval.content or '')[:500]}{'...' if len(approval.content or '') > 500 else ''}\n\n"
                    f"审核人: {reviewer_name}",
                    parse_mode='Markdown',
                )
            except Exception:
                pass
            
            # 提示输入回复内容（将转发给客户），或点击跳过
            try:
                _store_sms_approval_session(context, query.from_user.id, approval.id, True)
                skip_keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("⏭️ 跳过", callback_data=f"sms_approval_skip_{approval.id}_1")],
                ])
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="💬 请输入回复内容或发送图片（将转发给客户），或点击【跳过】",
                    reply_markup=skip_keyboard,
                )
            except Exception as e:
                logger.exception("发送回复提示失败: %s", e)
                await _notify_customer_approved(context, approval, account)
            
            await query.answer("✅ 已通过，请输入回复或点击跳过")
        else:
            approval.status = 'rejected'
            approval.reviewed_at = datetime.now()
            approval.reviewed_by_name = reviewer_name
            await _sync_ticket_for_sms_approval(db, approval, account, False, reviewer_name)
            await db.commit()
            
            try:
                test_countries = await _get_test_countries_for_account(db, account.id)
                await query.edit_message_text(
                    f"❌ *已拒绝*\n\n"
                    f"🌍 测试国家: {test_countries}\n"
                    f"📝 测试内容:\n{(approval.content or '')[:500]}{'...' if len(approval.content or '') > 500 else ''}\n\n"
                    f"审核人: {reviewer_name}",
                    parse_mode='Markdown',
                )
            except Exception:
                pass
            
            # 提示输入拒绝原因（将转发给客户），或点击跳过
            try:
                _store_sms_approval_session(context, query.from_user.id, approval.id, False)
                skip_keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("⏭️ 跳过", callback_data=f"sms_approval_skip_{approval.id}_0")],
                ])
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="💬 请输入拒绝原因或发送图片（将转发给客户），或点击【跳过】",
                    reply_markup=skip_keyboard,
                )
            except Exception as e:
                logger.exception("发送回复提示失败: %s", e)
                await _notify_customer_rejected(context, approval)
            
            await query.answer("❌ 已拒绝，请输入原因或点击跳过")


async def execute_approved_sms(query, context, approval_id: int):
    """客户点击「立即发送」后，执行审核通过的短信发送"""
    tg_id = query.from_user.id
    
    async with get_session() as db:
        result = await db.execute(
            select(SmsContentApproval, Account)
            .join(Account, SmsContentApproval.account_id == Account.id)
            .where(SmsContentApproval.id == approval_id)
        )
        row = result.first()
        
        if not row:
            await query.answer("❌ 记录不存在", show_alert=True)
            return
        
        approval, account = row
        
        if str(approval.tg_user_id) != str(tg_id):
            await query.answer("❌ 无权操作", show_alert=True)
            return
        
        if approval.status != 'approved':
            await query.answer("该短信未通过审核或已发送", show_alert=True)
            return
        
        if approval.message_id:
            await query.answer("该短信已发送", show_alert=True)
            return
        
        # 只审核文案时无号码，需先让用户填写
        if not (approval.phone_number or approval.phone_number.strip()):
            await query.answer()
            context.user_data['waiting_for'] = 'sms_approval_phone'
            context.user_data['pending_approval_id'] = approval_id
            await query.edit_message_text(
                f"📤 *填写接收号码*\n\n"
                f"📝 内容: {(approval.content or '')[:80]}{'...' if len(approval.content or '') > 80 else ''}\n\n"
                f"请发送接收号码（E.164 格式，如 +66812345678）：",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 取消", callback_data="menu_main")],
                ]),
            )
            return
        
        await query.answer("正在发送...")
        
        # 调用 API 发送
        from bot.services.api_client import APIClient
        api_client = APIClient()
        send_result = await api_client.send_sms(
            api_key=account.api_key,
            phone_number=approval.phone_number,
            message=approval.content,
        )
        
        if send_result.get('success'):
            approval.message_id = send_result.get('message_id', '')
            approval.send_error = None
            await db.commit()
            
            await query.edit_message_text(
                f"✅ *发送成功*\n\n"
                f"📱 号码: {approval.phone_number}\n"
                f"📄 消息ID: `{send_result.get('message_id', '-')}`\n"
                f"💰 费用: {send_result.get('cost', '-')} {send_result.get('currency', 'USD')}\n\n"
                f"可在【发送记录】中查看详情。",
                parse_mode='Markdown',
                reply_markup=get_main_menu_customer(),
            )
        else:
            err = send_result.get('error', {})
            err_msg = err.get('message', str(err)) if isinstance(err, dict) else str(err)
            if 'connection' in str(err_msg).lower() or 'connect' in str(err_msg).lower():
                err_msg = "无法连接后端服务，请检查 Bot 的 API_BASE_URL 配置（Docker 环境应使用 http://api:8000）"
            approval.send_error = err_msg[:500]
            await db.commit()
            
            await query.edit_message_text(
                f"❌ *发送失败*\n\n{err_msg}\n\n请检查后重试或联系客服。",
                parse_mode='Markdown',
                reply_markup=get_main_menu_customer(),
            )


async def approve_recharge(query, context, order_id: int, approved: bool):
    """审批充值"""
    tg_id = query.from_user.id
    
    async with get_session() as db:
        # 验证管理员权限
        admin_result = await db.execute(
            select(AdminUser).where(
                AdminUser.tg_id == tg_id,
                AdminUser.status == 'active'
            )
        )
        admin = admin_result.scalar_one_or_none()
        
        if not admin or admin.role not in ['super_admin', 'admin', 'finance']:
            await query.edit_message_text(
                "❌ 您没有审批权限",
                reply_markup=get_back_menu()
            )
            return
        
        # 获取充值订单
        order_result = await db.execute(
            select(RechargeOrder, Account)
            .join(Account, RechargeOrder.account_id == Account.id)
            .where(RechargeOrder.id == order_id)
        )
        result = order_result.first()
        
        if not result:
            await query.edit_message_text(
                "❌ 充值订单不存在",
                reply_markup=get_back_menu()
            )
            return
        
        order, account = result
        
        if order.status != 'pending':
            await query.edit_message_text(
                f"❌ 该订单已被处理，状态: {order.status}",
                reply_markup=get_back_menu()
            )
            return
        
        if approved:
            # 通过 - 更新订单状态和账户余额
            order.status = 'completed'
            order.finance_audit_by = admin.id
            order.finance_audit_at = datetime.now()
            
            account.balance = float(account.balance or 0) + float(order.amount)
            
            await db.commit()
            
            await query.edit_message_text(
                f"✅ 充值已通过\n\n"
                f"订单号: {order.order_no}\n"
                f"金额: ${order.amount}\n"
                f"账户: {account.account_name}\n"
                f"新余额: ${account.balance:.2f}",
                reply_markup=get_back_menu()
            )
        else:
            # 拒绝
            order.status = 'rejected'
            order.finance_audit_by = admin.id
            order.finance_audit_at = datetime.now()
            
            await db.commit()
            
            await query.edit_message_text(
                f"❌ 充值已拒绝\n\n"
                f"订单号: {order.order_no}\n"
                f"金额: ${order.amount}",
                reply_markup=get_back_menu()
            )


async def show_ticket_detail(query, context, ticket_id: int, is_admin: bool = False):
    """显示工单详情"""
    async with get_session() as db:
        ticket_result = await db.execute(
            select(Ticket).where(Ticket.id == ticket_id)
        )
        ticket = ticket_result.scalar_one_or_none()
        
        if not ticket:
            await query.edit_message_text(
                "❌ 工单不存在",
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
        
        text = f"""📄 工单详情

工单号: {ticket.ticket_no}
类型: {type_map.get(ticket.ticket_type, ticket.ticket_type)}
状态: {status_map.get(ticket.status, ticket.status)}
优先级: {ticket.priority}

标题: {ticket.title}

描述:
{ticket.description or '无'}

创建时间: {ticket.created_at.strftime('%Y-%m-%d %H:%M') if ticket.created_at else 'N/A'}"""
        
        if ticket.resolution:
            text += f"\n\n处理结果:\n{ticket.resolution}"
        
        # 构建按钮
        keyboard = []
        if is_admin and ticket.status in ['open', 'assigned', 'in_progress']:
            keyboard.append([InlineKeyboardButton("✅ 关闭工单", callback_data=f"close_ticket_{ticket.id}")])
        keyboard.append([InlineKeyboardButton("🔙 返回", callback_data="menu_tickets" if not is_admin else "menu_pending_tickets")])
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def close_ticket(query, context, ticket_id: int):
    """关闭工单"""
    tg_id = query.from_user.id
    
    async with get_session() as db:
        # 验证权限
        admin_result = await db.execute(
            select(AdminUser).where(
                AdminUser.tg_id == tg_id,
                AdminUser.status == 'active'
            )
        )
        admin = admin_result.scalar_one_or_none()
        
        if not admin:
            await query.edit_message_text(
                "❌ 您没有权限关闭工单",
                reply_markup=get_back_menu()
            )
            return
        
        # 获取工单
        ticket_result = await db.execute(
            select(Ticket).where(Ticket.id == ticket_id)
        )
        ticket = ticket_result.scalar_one_or_none()
        
        if not ticket:
            await query.edit_message_text(
                "❌ 工单不存在",
                reply_markup=get_back_menu()
            )
            return
        
        ticket.status = 'resolved'
        ticket.resolved_at = datetime.now()
        ticket.resolved_by = admin.id
        
        await db.commit()
        
        await query.edit_message_text(
            f"✅ 工单已关闭\n\n"
            f"工单号: {ticket.ticket_no}\n"
            f"标题: {ticket.title}",
            reply_markup=get_back_menu()
        )


async def show_system_stats(query, context):
    """显示系统统计"""
    async with get_session() as db:
        # 今日数据
        today = datetime.now().date()
        today_start = datetime.combine(today, datetime.min.time())
        
        # 账户总数
        account_count = await db.execute(select(func.count(Account.id)))
        total_accounts = account_count.scalar() or 0
        
        # 今日充值
        recharge_result = await db.execute(
            select(func.sum(RechargeOrder.amount)).where(
                RechargeOrder.status == 'completed',
                RechargeOrder.created_at >= today_start
            )
        )
        today_recharge = recharge_result.scalar() or 0
        
        # 待处理工单
        pending_tickets = await db.execute(
            select(func.count(Ticket.id)).where(
                Ticket.status.in_(['open', 'assigned', 'in_progress'])
            )
        )
        pending_count = pending_tickets.scalar() or 0
        
        # 待审核充值
        pending_recharge = await db.execute(
            select(func.count(RechargeOrder.id)).where(
                RechargeOrder.status == 'pending'
            )
        )
        pending_recharge_count = pending_recharge.scalar() or 0
        
        await query.edit_message_text(
            f"📊 系统统计\n\n"
            f"👥 总账户数: {total_accounts}\n"
            f"💰 今日充值: ${today_recharge:.2f}\n"
            f"📋 待处理工单: {pending_count}\n"
            f"💳 待审核充值: {pending_recharge_count}",
            reply_markup=get_back_menu()
        )


async def show_sales_stats(query, context):
    """显示销售业绩统计"""
    tg_id = query.from_user.id
    
    async with get_session() as db:
        admin_result = await db.execute(
            select(AdminUser).where(
                AdminUser.tg_id == tg_id,
                AdminUser.status == 'active'
            )
        )
        admin = admin_result.scalar_one_or_none()
        
        if not admin:
            await query.edit_message_text(
                "❌ 无法获取员工信息",
                reply_markup=get_back_menu()
            )
            return
        
        # 本月数据
        today = datetime.now()
        month_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # 我的客户数 (非删除状态)
        customer_count = await db.execute(
            select(func.count(Account.id)).where(
                Account.sales_id == admin.id,
                Account.is_deleted == False
            )
        )
        total_customers = customer_count.scalar() or 0
        
        # 本月新增客户 (非删除状态)
        new_customers = await db.execute(
            select(func.count(Account.id)).where(
                Account.sales_id == admin.id,
                Account.created_at >= month_start,
                Account.is_deleted == False
            )
        )
        new_count = new_customers.scalar() or 0
        
        # 客户总余额
        balance_result = await db.execute(
            select(func.sum(Account.balance)).where(
                Account.sales_id == admin.id,
                Account.is_deleted == False
            )
        )
        total_balance = balance_result.scalar() or 0
        
        await query.edit_message_text(
            f"📊 我的业绩统计\n\n"
            f"👤 总客户数: {total_customers}\n"
            f"🆕 本月新增: {new_count}\n"
            f"💰 客户总余额: ${total_balance:.2f}\n"
            f"📈 本月佣金: ${admin.monthly_commission or 0:.2f}\n"
            f"💵 佣金比例: {float(admin.commission_rate or 0):.1f}%",
            reply_markup=get_back_menu()
        )


async def show_customer_tickets(query, context):
    """显示销售的客户工单"""
    tg_id = query.from_user.id
    
    async with get_session() as db:
        admin_result = await db.execute(
            select(AdminUser).where(
                AdminUser.tg_id == tg_id,
                AdminUser.status == 'active'
            )
        )
        admin = admin_result.scalar_one_or_none()
        
        if not admin:
            await query.edit_message_text(
                "❌ 无法获取员工信息",
                reply_markup=get_back_menu()
            )
            return
        
        # 查询该销售客户的工单
        tickets_result = await db.execute(
            select(Ticket, Account)
            .join(Account, Ticket.account_id == Account.id)
            .where(Account.sales_id == admin.id)
            .order_by(desc(Ticket.created_at))
            .limit(10)
        )
        results = tickets_result.all()
        
        if not results:
            await query.edit_message_text(
                "📋 客户工单\n\n"
                "暂无客户工单",
                reply_markup=get_back_menu()
            )
            return
        
        # 与工单详情 show_ticket_detail 一致，展示可读的处理状态（仅 emoji 用户难以理解）
        status_map = {
            'open': '⏳待处理',
            'assigned': '👤已分配',
            'in_progress': '🔄处理中',
            'pending_user': '⏸️等待回复',
            'resolved': '✅已解决',
            'closed': '🔒已关闭',
            'cancelled': '❌已取消',
        }
        
        lines = [f"📋 客户工单 ({len(results)}条)\n"]
        for ticket, account in results:
            status_label = status_map.get(ticket.status, ticket.status or '未知')
            acct_name = (account.account_name or '')[:12]
            lines.append(
                f"• {status_label}\n"
                f"  {ticket.ticket_no} · {acct_name}"
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
    approval: SmsContentApproval,
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

    async with get_session() as db:
        result = await db.execute(
            select(SmsContentApproval, Account)
            .join(Account, SmsContentApproval.account_id == Account.id)
            .where(SmsContentApproval.id == approval_id)
        )
        row = result.first()
        if not row:
            return
        approval, _ = row
        try:
            await _notify_customer_sms_approval_reply(
                context, approval, approved, reply_note, media_message=msg
            )
        except Exception as e:
            logger.exception("短信审核媒体转发客户失败: %s", e)
    await update.message.reply_text("✅ 回复已转发给客户")


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
        async with get_session() as db:
            result = await db.execute(
                select(SmsContentApproval, Account)
                .join(Account, SmsContentApproval.account_id == Account.id)
                .where(SmsContentApproval.id == approval_id)
            )
            row = result.first()
            if not row:
                return
            approval, account = row
            try:
                await _notify_customer_sms_approval_reply(
                    context, approval, approved, reply_text
                )
            except Exception as e:
                logger.exception("通知客户审核结果失败: %s", e)
        await update.message.reply_text("✅ 回复已转发给客户")
        return

    # 处理审核通过后填写号码（只审核文案流程）
    if waiting_for == 'sms_approval_phone':
        approval_id = context.user_data.pop('pending_approval_id', None)
        context.user_data['waiting_for'] = None
        if not approval_id:
            await update.message.reply_text("❌ 会话已过期，请重新点击「立即发送」", reply_markup=get_main_menu_customer())
            return
        phone = text.strip()
        try:
            from app.utils.validator import Validator
            is_valid, err_msg, _ = Validator.validate_phone_number(phone)
            if not is_valid:
                context.user_data['waiting_for'] = 'sms_approval_phone'
                context.user_data['pending_approval_id'] = approval_id
                await update.message.reply_text(f"❌ 号码格式错误\n\n{err_msg}\n\n请重新发送，如 +66812345678")
                return
        except Exception as e:
            logger.warning("号码校验异常: %s", e)
        async with get_session() as db:
            result = await db.execute(
                select(SmsContentApproval, Account)
                .join(Account, SmsContentApproval.account_id == Account.id)
                .where(SmsContentApproval.id == approval_id)
            )
            row = result.first()
            if not row:
                await update.message.reply_text("❌ 记录不存在", reply_markup=get_main_menu_customer())
                return
            approval, account = row
            if str(approval.tg_user_id) != str(tg_id):
                await update.message.reply_text("❌ 无权操作", reply_markup=get_main_menu_customer())
                return
            if approval.status != 'approved' or approval.message_id:
                await update.message.reply_text("该短信已发送或状态已变更", reply_markup=get_main_menu_customer())
                return
            approval.phone_number = phone
            await db.commit()
        from bot.services.api_client import APIClient
        api_client = APIClient()
        send_result = await api_client.send_sms(
            api_key=account.api_key,
            phone_number=phone,
            message=approval.content,
        )
        if send_result.get('success'):
            async with get_session() as db:
                a = await db.get(SmsContentApproval, approval_id)
                if a:
                    a.message_id = send_result.get('message_id', '')
                    a.send_error = None
                    await db.commit()
            await update.message.reply_text(
                f"✅ *发送成功*\n\n"
                f"📱 号码: {phone}\n"
                f"📄 消息ID: `{send_result.get('message_id', '-')}`\n"
                f"💰 费用: {send_result.get('cost', '-')} {send_result.get('currency', 'USD')}\n\n"
                f"可在【发送记录】中查看详情。",
                parse_mode='Markdown',
                reply_markup=get_main_menu_customer(),
            )
        else:
            err = send_result.get('error', {})
            err_msg = err.get('message', str(err)) if isinstance(err, dict) else str(err)
            if 'connection' in str(err_msg).lower() or 'connect' in str(err_msg).lower():
                err_msg = "无法连接后端服务，请检查 Bot 配置"
            await update.message.reply_text(f"❌ 发送失败\n\n{err_msg}", reply_markup=get_main_menu_customer())
        return
    
    # 处理邀请价格输入
    if waiting_for == 'invite_price':
        try:
            price = float(text)
            if price <= 0:
                await update.message.reply_text("❌ 价格必须大于0，请重新输入：")
                return
            
            context.user_data['customer_price'] = price
            template_info = context.user_data.get('template_info', {})
            
            # 生成邀请码
            from app.core.invitation import InvitationService
            
            async with get_session() as db:
                service = InvitationService(db)
                tpl_name = context.user_data.get('template_name', '')
                config = {
                    'business_type': context.user_data.get('business_type', 'sms'),
                    'country': context.user_data.get('country_code', ''),
                    'template_id': context.user_data.get('template_id'),
                    'template_name': tpl_name,
                    'price': price,
                }
                code = await service.create_code(
                    context.user_data.get('sales_id'),
                    config,
                    valid_hours=72
                )
            
            import os
            bot_username = os.getenv('TELEGRAM_BOT_USERNAME', 'kaolachbot')
            invite_link = f"https://t.me/{bot_username}?start={code}"
            biz_type = context.user_data.get('business_type', 'sms')
            biz_label = {'sms': '短信', 'voice': '语音', 'data': '数据'}.get(biz_type, biz_type)
            country = context.user_data.get('country_code', '')
            country_label = COUNTRY_NAMES.get(country, country)

            await update.message.reply_text(
                f"✅ <b>授权码创建成功！</b>\n\n"
                f"📋 授权码: <code>{code}</code>\n"
                f"🔗 开户链接:\n{invite_link}\n\n"
                f"📦 模板: {tpl_name}\n"
                f"🌍 国家/地区: {country_label}\n"
                f"💰 客户单价: ${price}\n"
                f"⏰ 有效期: 72小时\n\n"
                f"━━━━━━━━━━━━\n"
                f"📤 将上方链接转发给客户\n"
                f"客户点击链接即可自动开户",
                parse_mode='HTML',
                reply_markup=get_back_menu(),
            )
            context.user_data['waiting_for'] = None
            
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

        from app.core.invitation import InvitationService

        try:
            async with get_session() as db:
                service = InvitationService(db)
                account, api_key, extra_info = await service.activate_code(
                    code,
                    tg_id,
                    tg_username=user.username,
                    tg_first_name=user.first_name,
                )

                context.user_data['account_id'] = account.id
                context.user_data['user_type'] = 'customer'
                context.user_data['waiting_for'] = None

                biz_type = extra_info.get('business_type', 'sms')
                biz_label = {'sms': '短信', 'voice': '语音', 'data': '数据'}.get(biz_type, biz_type)
                country_label = COUNTRY_NAMES.get(extra_info.get('country_code', ''), extra_info.get('country_code', ''))
                tpl_name = extra_info.get('template_name', '')
                login_account = extra_info.get('login_account', account.account_name)
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
                    f"🆔 账户ID: <code>{account.id}</code>\n"
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

        except ValueError:
            await update.message.reply_text(
                "❌ 授权码无效或已过期\n\n请联系销售获取新的授权码。",
                reply_markup=get_main_menu_guest(),
            )
            context.user_data['waiting_for'] = None
        except Exception as e:
            logger.error(f"Activation error: {e}", exc_info=True)
            await update.message.reply_text(
                "❌ 系统错误，请稍后重试",
                reply_markup=get_back_menu(),
            )
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
        
        async with get_session() as db:
            result = await db.execute(
                select(AdminUser).where(
                AdminUser.username == username,
                AdminUser.status == 'active'
            )
            )
            admin = result.scalar_one_or_none()
            
            if not admin:
                await update.message.reply_text(
                    "❌ 用户名不存在",
                    reply_markup=get_back_menu()
                )
                return
            
            # 简化密码验证（直接比较，因为bcrypt有问题）
            # TODO: 修复bcrypt验证
            # 直接绑定，同时保存 tg_username 以便在员工管理页面显示
            admin.tg_id = tg_id
            admin.tg_username = update.effective_user.username or update.effective_user.first_name or str(tg_id)
            await db.commit()
            
            role_map = {
                'super_admin': '超级管理员',
                'admin': '管理员',
                'sales': '销售',
                'finance': '财务',
                'tech': '技术'
            }
            role_label = role_map.get(admin.role, admin.role)
            
            context.user_data['user_type'] = 'admin'
            context.user_data['user_id'] = admin.id
            context.user_data['user_role'] = admin.role
            
            if admin.role in ['super_admin', 'admin', 'tech']:
                menu = get_main_menu_tech()
                msg = (
                    f"✅ 绑定成功！\n\n"
                    f"👤 {admin.real_name or admin.username}\n"
                    f"🔐 {role_label}\n\n"
                    f"请选择操作："
                )
            else:
                menu = get_main_menu_sales()
                monthly = float(admin.monthly_commission or 0)
                msg = (
                    f"✅ 绑定成功！\n\n"
                    f"👋 姓名: {admin.real_name or admin.username}\n"
                    f"🔐 角色: {role_label}\n"
                    f"💰 本月佣金: ${monthly:.2f}\n\n"
                    f"请选择操作：\n\n"
                    f"📢 全行业短信群发，AI语音，渗透数据！\n"
                    f"所有信息以官网 https://www.kaolach.com/ 展示为准！"
                )
            await update.message.reply_text(msg, reply_markup=menu)
            context.user_data['waiting_for'] = None
        return
    
    # 处理账户绑定码输入
    if waiting_for == 'account_bind_code':
        code = text.strip()
        if not code.isdigit() or len(code) != 6:
            await update.message.reply_text("❌ 请输入6位数字绑定码")
            return

        import redis as redis_lib
        try:
            r = redis_lib.Redis(host="redis", port=6379, decode_responses=True)
            redis_key = f"acct_tg_bind:{code}"
            account_id_str = r.get(redis_key)

            if not account_id_str:
                await update.message.reply_text(
                    "❌ 绑定码无效或已过期，请重新生成。",
                    reply_markup=get_back_menu()
                )
                return

            account_id = int(account_id_str)
            r.delete(redis_key)

            async with get_session() as db:
                acc_result = await db.execute(select(Account).where(Account.id == account_id))
                account = acc_result.scalar_one_or_none()
                if not account:
                    await update.message.reply_text("❌ 账户不存在。", reply_markup=get_back_menu())
                    return

                account.tg_id = tg_id
                account.tg_username = update.effective_user.username or update.effective_user.first_name

                existing = await db.execute(
                    select(TelegramBinding).where(
                        TelegramBinding.tg_id == tg_id,
                        TelegramBinding.account_id == account_id
                    )
                )
                binding = existing.scalar_one_or_none()
                if binding:
                    binding.is_active = True
                else:
                    db.add(TelegramBinding(tg_id=tg_id, account_id=account_id, is_active=True))
                await db.commit()

            context.user_data['account_id'] = account_id
            context.user_data['user_type'] = 'customer'
            context.user_data['waiting_for'] = None

            await update.message.reply_text(
                f"✅ 绑定成功！\n\n"
                f"📦 账户: {account.account_name}\n"
                f"🆔 ID: {account_id}\n\n"
                f"发送 /start 返回主菜单。",
                reply_markup=get_main_menu_customer()
            )
        except Exception as e:
            logger.error(f"account_bind_code error: {e}", exc_info=True)
            await update.message.reply_text("❌ 绑定失败，请稍后重试。", reply_markup=get_back_menu())
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
    
    # 处理工单描述输入
    if waiting_for == 'ticket_description':
        ticket_type = context.user_data.get('ticket_type', 'other')
        ticket_title = context.user_data.get('ticket_title', '无标题')
        
        async with get_session() as db:
            binding, account = await get_valid_customer_binding_and_account(db, tg_id)
            if not binding or not account:
                await update.message.reply_text(
                    "❌ 未绑定有效账户或该账户已停用/删除，无法提交工单。",
                    reply_markup=get_main_menu_guest(),
                )
                context.user_data["waiting_for"] = None
                return

            # 生成工单号
            ticket_no = f"TK{datetime.now().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(2).upper()}"

            # 创建工单
            new_ticket = Ticket(
                ticket_no=ticket_no,
                account_id=binding.account_id,
                tg_user_id=str(tg_id),
                ticket_type=ticket_type,
                priority='normal',
                title=ticket_title,
                description=text,
                status='open',
                created_by_type='telegram',
                created_by_id=tg_id
            )
            db.add(new_ticket)
            await db.commit()
            
            type_labels = {
                'test': '测试申请',
                'technical': '技术支持',
                'billing': '账务问题',
                'feedback': '意见反馈'
            }
            
            await update.message.reply_text(
                f"✅ 工单提交成功！\n\n"
                f"📋 工单号: {ticket_no}\n"
                f"📝 类型: {type_labels.get(ticket_type, ticket_type)}\n"
                f"📌 标题: {ticket_title}\n\n"
                f"我们会尽快处理您的工单，请耐心等待。",
                reply_markup=get_main_menu_customer()
            )
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
        phone = None  # 只审核文案，不填号码
        try:
            async with get_session() as db:
                tg_id_int = int(tg_id) if tg_id is not None else None
                binding, account = await get_valid_customer_binding_and_account(db, tg_id_int)
                if not binding or not account:
                    logger.warning("短信审核未绑定: tg_id=%s (type=%s)", tg_id, type(tg_id).__name__)
                    await update.message.reply_text(
                        f"❌ 未绑定有效账户或该账户已停用/删除\n\n"
                        f"您的 Telegram ID: `{tg_id}`\n"
                        f"请使用邀请链接激活账户，或联系管理员将您的 ID 与账户绑定。",
                        reply_markup=get_back_menu(),
                        parse_mode='Markdown',
                    )
                    return
                if float(account.balance or 0) <= 0:
                    await update.message.reply_text(
                        f"❌ 余额不足\n\n当前余额: ${account.balance:.4f}\n请先充值后再发送",
                        reply_markup=get_main_menu_customer()
                    )
                    return
                bot_config = await _get_bot_config(db)
                admin_group_id = (bot_config.get('admin_group_id') or '').strip()
                # 从账户绑定通道对应的供应商获取群组 ID，否则用全局配置
                target_group_id = await _resolve_supplier_group_for_account(db, account.id, admin_group_id)
                approval_no = f"SA{datetime.now().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(2).upper()}"
                approval = SmsContentApproval(
                    approval_no=approval_no,
                    account_id=account.id,
                    tg_user_id=str(tg_id),
                    phone_number=None,
                    content=content,
                    status='pending',
                )
                db.add(approval)
                await db.commit()
                await db.refresh(approval)
                ticket_no = f"TK{datetime.now().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(2).upper()}"
                sms_ticket = Ticket(
                    ticket_no=ticket_no,
                    account_id=account.id,
                    tg_user_id=str(tg_id),
                    ticket_type='test',
                    priority='normal',
                    title=f"短信审核-{approval_no}",
                    description=f"内容: {content[:500]}",
                    status='open',
                    created_by_type='telegram',
                    created_by_id=tg_id,
                    test_phone=None,
                    test_content=content,
                    review_status='pending',
                    forwarded_to_group=target_group_id if target_group_id else None,
                    extra_data={"sms_approval_id": approval.id},
                )
                db.add(sms_ticket)
                await db.commit()
                if target_group_id:
                    try:
                        test_countries = await _get_test_countries_for_account(db, account.id)
                        msg_text = (
                            f"📋 *短信文案待审核*\n\n"
                            f"🌍 测试国家: {test_countries}\n"
                            f"📝 测试内容:\n{content[:500]}{'...' if len(content) > 500 else ''}"
                        )
                        keyboard = InlineKeyboardMarkup([
                            [
                                InlineKeyboardButton("✅ 通过", callback_data=f"approve_sms_{approval.id}"),
                                InlineKeyboardButton("❌ 拒绝", callback_data=f"reject_sms_{approval.id}"),
                            ]
                        ])
                        fwd_msg = await context.bot.send_message(
                            chat_id=int(target_group_id),
                            text=msg_text,
                            parse_mode='Markdown',
                            reply_markup=keyboard,
                        )
                        approval.forwarded_to_group = target_group_id
                        approval.forwarded_message_id = fwd_msg.message_id
                        sms_ticket.forwarded_to_group = target_group_id
                        sms_ticket.review_status = 'forwarded'
                        await db.commit()
                    except Exception as e:
                        logger.exception("转发审核消息失败: %s", e)
                        await update.message.reply_text(
                            "❌ 转发至供应商群失败，审核记录和工单已创建。",
                            reply_markup=get_main_menu_customer()
                        )
                        context.user_data['waiting_for'] = None
                        return
                else:
                    await update.message.reply_text(
                        "⚠️ 审核已记录，但供应商群未配置。请确保：1) 账户已绑定通道；2) 通道已关联供应商；3) 在「供应商管理」中为该供应商配置「Telegram 群组 ID」。或联系管理员在 Bot 配置中设置全局供应商群 ID。",
                        reply_markup=get_main_menu_customer()
                    )
                    context.user_data['waiting_for'] = None
                    return
                await update.message.reply_text(
                    f"📤 *文案已提交审核*\n\n"
                    f"📋 工单号: {ticket_no}\n"
                    f"📝 内容: {content[:50]}{'...' if len(content) > 50 else ''}\n\n"
                    f"已转发至供应商群，审核通过后会通知您，届时需填写号码并点击「立即发送」。",
                    reply_markup=get_main_menu_customer(),
                    parse_mode='Markdown',
                )
            context.user_data['waiting_for'] = None
        except Exception as e:
            logger.exception("短信审核提交异常: %s", e)
            context.user_data['waiting_for'] = None
            await update.message.reply_text(
                "❌ 系统错误，请稍后重试。",
                reply_markup=get_main_menu_customer(),
            )
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
        try:
            from app.utils.validator import Validator
            is_valid, err_msg, _ = Validator.validate_phone_number(phone)
            if not is_valid:
                await update.message.reply_text(
                    f"❌ 号码格式错误\n\n{err_msg}\n\n正确示例: +8613800138000 或 +66812345678",
                    reply_markup=get_back_menu()
                )
                return
        except Exception as e:
            logger.warning("号码校验异常: %s", e)
        if len(content) > 1000:
            await update.message.reply_text("❌ 短信内容最多1000字符", reply_markup=get_back_menu())
            return
        try:
            async with get_session() as db:
                binding, account = await get_valid_customer_binding_and_account(db, tg_id)
                if not binding or not account:
                    await update.message.reply_text(
                        "❌ 未绑定有效账户或该账户已停用/删除。",
                        reply_markup=get_back_menu()
                    )
                    return

                if float(account.balance or 0) <= 0:
                    await update.message.reply_text(
                        f"❌ 余额不足\n\n当前余额: ${account.balance:.4f}\n请先充值后再发送",
                        reply_markup=get_main_menu_customer()
                    )
                    return
                
                bot_config = await _get_bot_config(db)
                enable_review = bot_config.get('enable_sms_content_review', True)
                admin_group_id = (bot_config.get('admin_group_id') or '').strip()
                sms_submit_mode = context.user_data.get('sms_submit_mode', 'direct')
                
                # 从账户绑定通道对应供应商获取群组 ID，有号码时再按国家路由细化
                target_group_id = await _resolve_supplier_group_for_account(db, account.id, admin_group_id)
                try:
                    from app.utils.validator import Validator
                    from app.core.router import RoutingEngine
                    from app.modules.sms.supplier import Supplier
                    from app.modules.sms.channel import Channel
                    from app.modules.sms.supplier import SupplierChannel
                    
                    is_valid, _, phone_info = Validator.validate_phone_number(phone)
                    if is_valid and phone_info:
                        country_code = phone_info.get('country_code', '')
                        if country_code:
                            routing = RoutingEngine(db)
                            channel = await routing.select_channel(
                                country_code=country_code,
                                account_id=account.id
                            )
                            if channel:
                                sc_result = await db.execute(
                                    select(SupplierChannel, Supplier)
                                    .join(Supplier, SupplierChannel.supplier_id == Supplier.id)
                                    .where(
                                        SupplierChannel.channel_id == channel.id,
                                        SupplierChannel.status == 'active',
                                        Supplier.is_deleted == False
                                    )
                                    .limit(1)
                                )
                                sc_row = sc_result.first()
                                if sc_row:
                                    _, supplier = sc_row
                                    if getattr(supplier, 'telegram_group_id', None):
                                        target_group_id = (supplier.telegram_group_id or '').strip()
                except Exception as e:
                    logger.debug("解析供应商群组失败，使用全局配置: %s", e)
                
                if not target_group_id:
                    target_group_id = admin_group_id
                
                # 短信审核入口（发送短信菜单）：若启用审核则创建审核记录
                force_audit = (sms_submit_mode == 'audit')
                
                if force_audit or (enable_review and (target_group_id or admin_group_id)):
                    # 需要审核：创建审核记录，转发到供应商群
                    approval_no = f"SA{datetime.now().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(2).upper()}"
                    approval = SmsContentApproval(
                        approval_no=approval_no,
                        account_id=account.id,
                        tg_user_id=str(tg_id),
                        phone_number=phone,
                        content=content,
                        status='pending',
                    )
                    db.add(approval)
                    await db.commit()
                    await db.refresh(approval)
                    
                    # 自动生成短信测试工单
                    ticket_no = f"TK{datetime.now().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(2).upper()}"
                    sms_ticket = Ticket(
                        ticket_no=ticket_no,
                        account_id=account.id,
                        tg_user_id=str(tg_id),
                        ticket_type='test',
                        priority='normal',
                        title=f"短信审核-{approval_no}",
                        description=f"号码: {phone}\n内容: {content[:500]}",
                        status='open',
                        created_by_type='telegram',
                        created_by_id=tg_id,
                        test_phone=phone,
                        test_content=content,
                        review_status='pending',
                        forwarded_to_group=target_group_id if target_group_id else None,
                        extra_data={"sms_approval_id": approval.id},
                    )
                    db.add(sms_ticket)
                    await db.commit()
                    
                    # 转发到供应商群（若已配置）
                    if target_group_id:
                        try:
                            test_countries = await _get_test_countries_for_account(db, account.id)
                            msg_text = (
                                f"📋 *短信内容待审核*\n\n"
                                f"🌍 测试国家: {test_countries}\n"
                                f"📝 测试内容:\n{content[:500]}{'...' if len(content) > 500 else ''}"
                            )
                            keyboard = InlineKeyboardMarkup([
                                [
                                    InlineKeyboardButton("✅ 通过", callback_data=f"approve_sms_{approval.id}"),
                                    InlineKeyboardButton("❌ 拒绝", callback_data=f"reject_sms_{approval.id}"),
                                ]
                            ])
                            fwd_msg = await context.bot.send_message(
                                chat_id=int(target_group_id),
                                text=msg_text,
                                parse_mode='Markdown',
                                reply_markup=keyboard,
                            )
                            approval.forwarded_to_group = target_group_id
                            approval.forwarded_message_id = fwd_msg.message_id
                            sms_ticket.forwarded_to_group = target_group_id
                            sms_ticket.review_status = 'forwarded'
                            await db.commit()
                        except Exception as e:
                            logger.exception("转发审核消息失败: %s", e)
                            await update.message.reply_text(
                                f"❌ 转发至供应商群失败，请检查 Bot 配置中的供应商群 ID。审核记录和工单已创建。",
                                reply_markup=get_main_menu_customer()
                            )
                            context.user_data['waiting_for'] = None
                            return
                    else:
                        await update.message.reply_text(
                            "⚠️ 审核已记录，但供应商群未配置。请确保：1) 账户已绑定通道；2) 通道已关联供应商；3) 在「供应商管理」中为该供应商配置「Telegram 群组 ID」。或联系管理员在 Bot 配置中设置全局供应商群 ID。",
                            reply_markup=get_main_menu_customer()
                        )
                        context.user_data['waiting_for'] = None
                        return
                    
                    await update.message.reply_text(
                        f"📤 *短信已提交审核*\n\n"
                        f"📋 工单号: {ticket_no}\n"
                        f"📱 接收号码: {phone}\n"
                        f"📝 内容: {content[:50]}{'...' if len(content) > 50 else ''}\n\n"
                        f"已转发至供应商群，审核通过后会通知您，请点击「立即发送」进行发送。",
                        reply_markup=get_main_menu_customer(),
                        parse_mode='Markdown',
                    )
                else:
                    # 无需审核：直接发送
                    from bot.services.api_client import APIClient
                    api_client = APIClient()
                    api_key = account.api_key
                    send_result = await api_client.send_sms(
                        api_key=api_key,
                        phone_number=phone,
                        message=content,
                    )
                    if send_result.get('success'):
                        await update.message.reply_text(
                            f"✅ *发送成功*\n\n"
                            f"📱 号码: {phone}\n"
                            f"📄 消息ID: `{send_result.get('message_id')}`\n"
                            f"💰 费用: {send_result.get('cost')} {send_result.get('currency')}",
                            reply_markup=get_main_menu_customer(),
                            parse_mode='Markdown',
                        )
                    else:
                        err = send_result.get('error', {})
                        err_msg = err.get('message', '未知错误') if isinstance(err, dict) else str(err)
                        if 'connection' in err_msg.lower() or 'connect' in err_msg.lower():
                            err_msg = "无法连接后端服务，请检查 Bot 的 API_BASE_URL 配置（Docker 环境应使用 http://api:8000）"
                        await update.message.reply_text(
                            f"❌ 发送失败\n\n{err_msg}",
                            reply_markup=get_main_menu_customer(),
                        )
                context.user_data['waiting_for'] = None
        except Exception as e:
            logger.exception("短信提交异常: %s", e)
            context.user_data['waiting_for'] = None
            await update.message.reply_text(
                "❌ 系统错误，请稍后重试。如持续出现请联系客服。",
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
        pattern=r'^(?!menu_register$|reg_)(?:sales_login_|menu_|biz_|kb_|ticket_type_|country_|tpl_|pricing_|approve_|reject_|send_approved_sms_|process_|ticket_detail_|close_ticket_|back_)'
    ),
    # 短信审核回复：图片与图片类文档需在 TEXT 之外单独处理
    MessageHandler(
        _sms_approval_media_filters & ~filters.COMMAND,
        handle_sms_approval_reply_media,
    ),
    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input),
]
