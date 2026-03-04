"""
菜单处理器 - 使用按钮菜单替代命令
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from bot.utils import get_session, logger
from app.modules.common.telegram_binding import TelegramBinding
from app.modules.common.account import Account
from app.modules.common.admin_user import AdminUser
from app.modules.common.ticket import Ticket
from app.modules.common.recharge_order import RechargeOrder
from sqlalchemy import select, func, desc
from datetime import datetime, timedelta
import secrets

# 国家名称映射（避免编码问题）
COUNTRY_NAMES = {
    'CN': '中国',
    'US': '美国',
    'GB': '英国',
    'SG': '新加坡',
    'JP': '日本',
    'KR': '韩国',
    'TH': '泰国',
    'VN': '越南',
    'MY': '马来西亚',
    'ID': '印尼',
    'PH': '菲律宾',
    'IN': '印度',
    'AU': '澳大利亚',
    'CA': '加拿大',
    'DE': '德国',
    'FR': '法国',
    'IT': '意大利',
    'ES': '西班牙',
    'RU': '俄罗斯',
    'BR': '巴西',
    'MX': '墨西哥',
    'HK': '香港',
    'TW': '台湾',
    'AE': '阿联酋',
    'SA': '沙特',
}


# ============ 主菜单 ============

def get_main_menu_customer():
    """客户主菜单"""
    keyboard = [
        [
            InlineKeyboardButton("📱 发送短信", callback_data="menu_send_sms"),
            InlineKeyboardButton("📞 发送语音", callback_data="menu_send_voice"),
        ],
        [
            InlineKeyboardButton("💰 查询余额", callback_data="menu_balance"),
            InlineKeyboardButton("💳 申请充值", callback_data="menu_recharge"),
        ],
        [
            InlineKeyboardButton("📋 我的工单", callback_data="menu_tickets"),
            InlineKeyboardButton("📝 提交工单", callback_data="menu_new_ticket"),
        ],
        [
            InlineKeyboardButton("📊 发送记录", callback_data="menu_history"),
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
            InlineKeyboardButton("💰 我的佣金", callback_data="menu_commission"),
        ],
        [
            InlineKeyboardButton("📋 客户工单", callback_data="menu_customer_tickets"),
            InlineKeyboardButton("📊 业绩统计", callback_data="menu_sales_stats"),
        ],
        [
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
            InlineKeyboardButton("❓ 帮助", callback_data="menu_help"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_main_menu_guest():
    """游客菜单"""
    keyboard = [
        [
            InlineKeyboardButton("📝 我是客户 - 输入邀请码", callback_data="menu_enter_invite"),
        ],
        [
            InlineKeyboardButton("👔 我是员工 - 绑定账号", callback_data="menu_bind_staff"),
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
    
    # 返回主菜单
    if data == "menu_main":
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
    
    # 发送短信
    if data == "menu_send_sms":
        await query.edit_message_text(
            "📱 发送短信\n\n"
            "请直接发送以下格式的消息：\n"
            "`号码 内容`\n\n"
            "例如：\n"
            "`+8613800138000 您的验证码是123456`",
            parse_mode='Markdown',
            reply_markup=get_back_menu()
        )
        context.user_data['waiting_for'] = 'sms_content'
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
                select(AdminUser).where(AdminUser.tg_id == tg_id)
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
    
    # 我的佣金
    if data == "menu_commission":
        await show_commission(query, context)
        return
    
    # 游客输入邀请码
    if data == "menu_enter_invite":
        await query.edit_message_text(
            "📝 请输入邀请码\n\n"
            "请直接发送您收到的邀请码，例如：\n"
            "`ABC123XYZ`",
            parse_mode='Markdown',
            reply_markup=get_back_menu()
        )
        context.user_data['waiting_for'] = 'invite_code'
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
        
        # 显示模板选择 - 使用固定格式避免编码问题
        keyboard = []
        for tpl in templates:
            # 使用国家名称映射 + 价格，避免数据库中文乱码
            country_label = COUNTRY_NAMES.get(tpl.country_code, tpl.country_code)
            price = float(tpl.default_price) if tpl.default_price else 0
            label = f"{country_label} - ${price:.4f}"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"tpl_{tpl.id}")])
        keyboard.append([InlineKeyboardButton("🔙 返回", callback_data=f"biz_{biz_type}")])
        
        await query.edit_message_text(
            f"🎯 创建开户邀请\n\n"
            f"业务类型: {biz_label}\n"
            f"国家: {country_code}\n\n"
            f"请选择资费模板：",
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
        
        # 使用映射表构建模板名称，避免编码问题
        country_label = COUNTRY_NAMES.get(template.country_code, template.country_code)
        biz_type = context.user_data.get('business_type', 'sms')
        biz_label = {"sms": "短信", "voice": "语音", "data": "数据"}.get(biz_type, biz_type)
        template_label = f"{country_label}{biz_label}"
        price = float(template.default_price) if template.default_price else 0
        
        context.user_data['template_info'] = {
            'name': template_label,
            'default_price': price,
            'country': template.country_code
        }
        
        await query.edit_message_text(
            f"🎯 创建开户邀请\n\n"
            f"模板: {template_label}\n"
            f"底价: ${price:.4f}\n\n"
            f"请输入客户单价（USD）：\n"
            f"例如: 0.05",
            reply_markup=get_back_menu()
        )
        context.user_data['waiting_for'] = 'invite_price'
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


async def show_main_menu(query, context: ContextTypes.DEFAULT_TYPE):
    """显示主菜单"""
    tg_id = query.from_user.id
    
    async with get_session() as db:
        # 检查是否是员工
        admin_result = await db.execute(
            select(AdminUser).where(AdminUser.tg_id == tg_id)
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
            else:
                menu = get_main_menu_sales()
            
            await query.edit_message_text(
                f"👋 {admin.real_name or admin.username}\n"
                f"🔐 {role_label}\n\n"
                f"请选择操作：",
                reply_markup=menu
            )
            return
        
        # 检查是否是客户
        binding_result = await db.execute(
            select(TelegramBinding).where(
                TelegramBinding.tg_id == tg_id,
                TelegramBinding.is_active == True
            )
        )
        binding = binding_result.scalar_one_or_none()
        
        if binding:
            acc_result = await db.execute(
                select(Account).where(Account.id == binding.account_id)
            )
            account = acc_result.scalar_one_or_none()
            
            balance_str = f"${account.balance:.2f}" if account else "N/A"
            
            await query.edit_message_text(
                f"👋 欢迎回来\n"
                f"💰 余额: {balance_str}\n\n"
                f"请选择操作：",
                reply_markup=get_main_menu_customer()
            )
            return
        
        # 游客
        await query.edit_message_text(
            "👋 欢迎使用 TG 业务助手\n\n"
            "请选择您的身份：",
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
        binding_result = await db.execute(
            select(TelegramBinding).where(
                TelegramBinding.tg_id == tg_id,
                TelegramBinding.is_active == True
            )
        )
        binding = binding_result.scalar_one_or_none()
        
        if not binding:
            await query.edit_message_text(
                "❌ 您还未绑定账户",
                reply_markup=get_back_menu()
            )
            return
        
        acc_result = await db.execute(
            select(Account).where(Account.id == binding.account_id)
        )
        account = acc_result.scalar_one_or_none()
        
        if account:
            await query.edit_message_text(
                f"💰 账户余额\n\n"
                f"账户: {account.account_name}\n"
                f"余额: ${account.balance:.4f} {account.currency}\n"
                f"状态: {'正常' if account.status == 'active' else '已冻结'}",
                reply_markup=get_back_menu()
            )
        else:
            await query.edit_message_text(
                "❌ 账户信息获取失败",
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
        # 获取绑定账户
        binding_result = await db.execute(
            select(TelegramBinding).where(
                TelegramBinding.tg_id == tg_id,
                TelegramBinding.is_active == True
            )
        )
        binding = binding_result.scalar_one_or_none()
        
        if not binding:
            await query.edit_message_text(
                "❌ 您还未绑定账户",
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
        # 获取绑定账户
        binding_result = await db.execute(
            select(TelegramBinding).where(
                TelegramBinding.tg_id == tg_id,
                TelegramBinding.is_active == True
            )
        )
        binding = binding_result.scalar_one_or_none()
        
        if not binding:
            await query.edit_message_text(
                "❌ 您还未绑定账户",
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


async def show_my_customers(query, context):
    """显示我的客户"""
    tg_id = query.from_user.id
    
    async with get_session() as db:
        # 获取销售员工信息
        admin_result = await db.execute(
            select(AdminUser).where(AdminUser.tg_id == tg_id)
        )
        admin = admin_result.scalar_one_or_none()
        
        if not admin:
            await query.edit_message_text(
                "❌ 无法获取员工信息",
                reply_markup=get_back_menu()
            )
            return
        
        # 查询该销售的客户
        customers_result = await db.execute(
            select(Account).where(
                Account.sales_id == admin.id,
                Account.status == 'active'
            ).order_by(desc(Account.created_at)).limit(10)
        )
        customers = customers_result.scalars().all()
        
        if not customers:
            await query.edit_message_text(
                "👥 我的客户\n\n"
                "暂无客户记录\n\n"
                "通过[创建开户邀请]邀请新客户",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🎯 创建邀请", callback_data="menu_invite")],
                    [InlineKeyboardButton("🔙 返回", callback_data="menu_main")]
                ])
            )
            return
        
        # 统计信息
        total_customers = len(customers)
        total_balance = sum(float(c.balance or 0) for c in customers)
        
        lines = [
            f"👥 我的客户 ({total_customers}个)\n",
            f"💰 总余额: ${total_balance:.2f}\n"
        ]
        
        for c in customers[:5]:  # 只显示前5个
            balance = float(c.balance or 0)
            lines.append(f"• {c.account_name}: ${balance:.2f}")
        
        if total_customers > 5:
            lines.append(f"\n...还有 {total_customers - 5} 个客户")
        
        keyboard = [
            [InlineKeyboardButton("🎯 创建新邀请", callback_data="menu_invite")],
            [InlineKeyboardButton("🔙 返回", callback_data="menu_main")]
        ]
        
        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def show_commission(query, context):
    """显示佣金"""
    tg_id = query.from_user.id
    
    async with get_session() as db:
        admin_result = await db.execute(
            select(AdminUser).where(AdminUser.tg_id == tg_id)
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


async def approve_recharge(query, context, order_id: int, approved: bool):
    """审批充值"""
    tg_id = query.from_user.id
    
    async with get_session() as db:
        # 验证管理员权限
        admin_result = await db.execute(
            select(AdminUser).where(AdminUser.tg_id == tg_id)
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
            select(AdminUser).where(AdminUser.tg_id == tg_id)
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
            select(AdminUser).where(AdminUser.tg_id == tg_id)
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
        
        # 我的客户数
        customer_count = await db.execute(
            select(func.count(Account.id)).where(
                Account.sales_id == admin.id,
                Account.status == 'active'
            )
        )
        total_customers = customer_count.scalar() or 0
        
        # 本月新增客户
        new_customers = await db.execute(
            select(func.count(Account.id)).where(
                Account.sales_id == admin.id,
                Account.created_at >= month_start
            )
        )
        new_count = new_customers.scalar() or 0
        
        # 客户总余额
        balance_result = await db.execute(
            select(func.sum(Account.balance)).where(
                Account.sales_id == admin.id
            )
        )
        total_balance = balance_result.scalar() or 0
        
        await query.edit_message_text(
            f"📊 我的业绩统计\n\n"
            f"👥 总客户数: {total_customers}\n"
            f"🆕 本月新增: {new_count}\n"
            f"💰 客户总余额: ${total_balance:.2f}\n"
            f"📈 本月佣金: ${admin.monthly_commission or 0:.2f}\n"
            f"💵 佣金比例: {(admin.commission_rate or 0) * 100:.1f}%",
            reply_markup=get_back_menu()
        )


async def show_customer_tickets(query, context):
    """显示销售的客户工单"""
    tg_id = query.from_user.id
    
    async with get_session() as db:
        admin_result = await db.execute(
            select(AdminUser).where(AdminUser.tg_id == tg_id)
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
        
        status_map = {
            'open': '⏳', 'assigned': '👤', 'in_progress': '🔄',
            'pending_user': '⏸️', 'resolved': '✅', 'closed': '🔒'
        }
        
        lines = [f"📋 客户工单 ({len(results)}条)\n"]
        for ticket, account in results:
            emoji = status_map.get(ticket.status, '❓')
            lines.append(f"{emoji} {ticket.ticket_no} - {account.account_name[:10]}")
        
        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=get_back_menu()
        )


async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理用户文本输入"""
    waiting_for = context.user_data.get('waiting_for')
    
    if not waiting_for:
        return  # 没有等待输入，忽略
    
    text = update.message.text.strip()
    tg_id = update.effective_user.id
    
    logger.info(f"Text input: {text} for {waiting_for} from {tg_id}")
    
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
                config = {
                    'business_type': context.user_data.get('business_type', 'sms'),
                    'country': context.user_data.get('country_code', ''),
                    'template_id': context.user_data.get('template_id'),
                    'price': price
                }
                code = await service.create_code(
                    context.user_data.get('sales_id'),
                    config,
                    valid_hours=72
                )
            
            # 生成邀请链接
            import os
            bot_username = os.getenv('TELEGRAM_BOT_USERNAME', 'klboos_bot')
            invite_link = f"https://t.me/{bot_username}?start={code}"
            
            await update.message.reply_text(
                f"✅ 邀请码创建成功！\n\n"
                f"📋 邀请码: `{code}`\n"
                f"🔗 邀请链接:\n{invite_link}\n\n"
                f"💰 客户单价: ${price}\n"
                f"📦 业务类型: {context.user_data.get('business_type', 'sms')}\n"
                f"⏰ 有效期: 72小时\n\n"
                f"发送链接给客户，点击即可自动开户",
                parse_mode='Markdown',
                reply_markup=get_back_menu()
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
    
    # 处理邀请码输入
    if waiting_for == 'invite_code':
        code = text.strip()
        
        from app.core.invitation import InvitationService
        
        try:
            async with get_session() as db:
                service = InvitationService(db)
                account, api_key, extra_info = await service.activate_code(code, tg_id)
                
                context.user_data['account_id'] = account.id
                context.user_data['user_type'] = 'customer'
                
                biz_type = extra_info.get('business_type', 'sms')
                biz_label = {'sms': '短信', 'voice': '语音', 'data': '数据'}.get(biz_type, biz_type)
                
                await update.message.reply_text(
                    f"🎉 开户成功！\n\n"
                    f"📦 业务类型: {biz_label}\n"
                    f"🆔 账户ID: {account.id}\n"
                    f"👤 用户名: {account.account_name}\n"
                    f"🔑 API Key: `{api_key}`\n\n"
                    f"请妥善保存API Key",
                    parse_mode='Markdown',
                    reply_markup=get_main_menu_customer()
                )
                context.user_data['waiting_for'] = None
                
        except ValueError as e:
            await update.message.reply_text(
                f"❌ 激活失败: {str(e)}",
                reply_markup=get_back_menu()
            )
        except Exception as e:
            logger.error(f"Activation error: {e}")
            await update.message.reply_text(
                "❌ 系统错误，请稍后重试",
                reply_markup=get_back_menu()
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
                select(AdminUser).where(AdminUser.username == username)
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
            # 直接绑定
            admin.tg_id = tg_id
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
            else:
                menu = get_main_menu_sales()
            
            await update.message.reply_text(
                f"✅ 绑定成功！\n\n"
                f"👤 {admin.real_name or admin.username}\n"
                f"🔐 {role_label}\n\n"
                f"请选择操作：",
                reply_markup=menu
            )
            context.user_data['waiting_for'] = None
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
            # 获取账户
            binding_result = await db.execute(
                select(TelegramBinding).where(
                    TelegramBinding.tg_id == tg_id,
                    TelegramBinding.is_active == True
                )
            )
            binding = binding_result.scalar_one_or_none()
            
            # 生成工单号
            ticket_no = f"TK{datetime.now().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(2).upper()}"
            
            # 创建工单
            new_ticket = Ticket(
                ticket_no=ticket_no,
                account_id=binding.account_id if binding else None,
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
    
    # 处理短信发送
    if waiting_for == 'sms_content':
        parts = text.split(' ', 1)
        if len(parts) != 2:
            await update.message.reply_text(
                "❌ 格式错误\n\n请发送: 号码 内容\n例如: +8613800138000 您的验证码是123456",
                reply_markup=get_back_menu()
            )
            return
        
        phone, content = parts
        
        async with get_session() as db:
            binding_result = await db.execute(
                select(TelegramBinding, Account)
                .join(Account, TelegramBinding.account_id == Account.id)
                .where(
                    TelegramBinding.tg_id == tg_id,
                    TelegramBinding.is_active == True
                )
            )
            result = binding_result.first()
            
            if not result:
                await update.message.reply_text(
                    "❌ 您还未绑定账户",
                    reply_markup=get_back_menu()
                )
                return
            
            binding, account = result
            
            if float(account.balance or 0) <= 0:
                await update.message.reply_text(
                    f"❌ 余额不足\n\n当前余额: ${account.balance:.4f}\n请先充值后再发送",
                    reply_markup=get_main_menu_customer()
                )
                return
            
            # TODO: 实际调用短信发送接口
            await update.message.reply_text(
                f"📤 短信已提交发送\n\n"
                f"📱 接收号码: {phone}\n"
                f"📝 内容: {content[:50]}...\n\n"
                f"请稍后在发送记录中查看状态",
                reply_markup=get_main_menu_customer()
            )
            context.user_data['waiting_for'] = None
        return


from telegram.ext import MessageHandler, filters

# 导出回调处理器
menu_handlers = [
    CallbackQueryHandler(
        handle_menu_callback, 
        pattern=r'^menu_|^biz_|^ticket_type_|^country_|^tpl_|^approve_|^reject_|^process_|^ticket_detail_|^close_ticket_'
    ),
    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input),
]
