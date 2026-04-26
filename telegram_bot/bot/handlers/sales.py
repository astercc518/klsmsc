from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, 
    CommandHandler, 
    ConversationHandler, 
    CallbackQueryHandler
)
from bot.utils import logger, dedupe_country_codes_from_templates
from bot.handlers.menu import COUNTRY_NAMES
from bot.services.api_client import APIClient

# 对话状态
SELECT_BIZ_TYPE, SELECT_COUNTRY, SELECT_TEMPLATE, INPUT_PRICE, CONFIRM = range(5)


async def bind_sales(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /bind_sales <username> <password>
    绑定销售账号
    """
    user = update.effective_user
    args = context.args
    
    if len(args) != 2:
        await update.message.reply_text("❌ 格式错误。请使用: `/bind_sales username password`", parse_mode='Markdown')
        return
        
    username, password = args[0], args[1]
    tg_id = user.id
    
    api = APIClient()
    res = await api.bind_sales(username, password, tg_id)
    
    if res.get("success"):
        await update.message.reply_text(f"✅ 绑定成功！欢迎销售 **{res.get('real_name')}**", parse_mode='Markdown')
    else:
        await update.message.reply_text(f"❌ 绑定失败: {res.get('msg', '未知错误')}")


async def invite_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /invite - 开始交互式邀请码生成
    """
    user = update.effective_user
    tg_id = user.id
    
    api = APIClient()
    user_info = await api.verify_user(tg_id, include_monthly_performance=False)

    if not user_info or user_info.get("role") not in ['sales', 'super_admin', 'admin']:
        await update.message.reply_text("❌ 您尚未绑定销售账号，请先使用 `/bind_sales`", parse_mode='Markdown')
        return ConversationHandler.END
    
    context.user_data['sales_id'] = user_info.get("user_id")
    context.user_data['sales_name'] = user_info.get("real_name")
    
    # 显示业务类型选择
    keyboard = [
        [
            InlineKeyboardButton("📱 短信 SMS", callback_data="biz_sms"),
            InlineKeyboardButton("📞 语音 Voice", callback_data="biz_voice"),
        ],
        [
            InlineKeyboardButton("📊 数据 Data", callback_data="biz_data"),
        ],
        [InlineKeyboardButton("❌ 取消", callback_data="cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🎯 **创建开户邀请**\n\n请选择业务类型：",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return SELECT_BIZ_TYPE


async def select_biz_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理业务类型选择"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data == "cancel":
        await query.edit_message_text("❌ 已取消")
        return ConversationHandler.END
    
    biz_type = data.replace("biz_", "")
    context.user_data['business_type'] = biz_type
    
    biz_label = {"sms": "短信", "voice": "语音", "data": "数据"}.get(biz_type, biz_type)
    
    # 获取该业务类型下的所有国家
    api = APIClient()
    res = await api.get_sales_templates(biz_type=biz_type)
    if not res.get("success"):
        await query.edit_message_text(f"❌ 获取模板失败: {res.get('msg')}")
        return ConversationHandler.END
        
    templates = res.get("templates", [])
    raw_codes = [t.get("country_code") for t in templates if t.get("country_code")]
    country_codes = dedupe_country_codes_from_templates(raw_codes)
    
    if not country_codes:
        await query.edit_message_text(
            f"❌ 暂无 {biz_label} 业务的可用模板，请联系管理员添加"
        )
        return ConversationHandler.END
    
    # 存储模板供后续使用以减少请求
    context.user_data['available_templates'] = templates

    # 显示国家选择
    keyboard = []
    row = []
    for country_code in country_codes:
        label = COUNTRY_NAMES.get(country_code, country_code)
        row.append(InlineKeyboardButton(label, callback_data=f"country_{country_code}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("⬅️ 返回", callback_data="back_to_biz")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        f"📍 **选择国家** ({biz_label})\n\n请选择目标国家：",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return SELECT_COUNTRY


async def select_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理国家选择"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data == "back_to_biz":
        # 返回业务类型选择
        keyboard = [
            [
                InlineKeyboardButton("📱 短信 SMS", callback_data="biz_sms"),
                InlineKeyboardButton("📞 语音 Voice", callback_data="biz_voice"),
            ],
            [
                InlineKeyboardButton("📊 数据 Data", callback_data="biz_data"),
            ],
            [InlineKeyboardButton("❌ 取消", callback_data="cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "🎯 **创建开户邀请**\n\n请选择业务类型：",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return SELECT_BIZ_TYPE
    
    country_code = data.replace("country_", "").strip().upper()
    context.user_data['country_code'] = country_code
    
    templates = context.user_data.get('available_templates', [])
    filtered_templates = [t for t in templates if t.get("country_code", "").upper() == country_code]
    
    if not filtered_templates:
        await query.edit_message_text(f"❌ 该国家暂无可用模板")
        return ConversationHandler.END
    
    # 显示模板选择
    keyboard = []
    for tpl in filtered_templates:
        price_str = f"${float(tpl.get('default_price')):.4f}" if tpl.get('default_price') else "待定"
        label = f"{tpl.get('template_name')} ({price_str})"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"tpl_{tpl.get('id')}")])
    keyboard.append([InlineKeyboardButton("⬅️ 返回", callback_data="back_to_country")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        f"📋 **选择模板** ({country_code})\n\n请选择开户模板：",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return SELECT_TEMPLATE


async def select_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理模板选择"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data == "back_to_country":
        # 复用 select_biz_type 的逻辑显示国家列表
        biz_type = context.user_data['business_type']
        biz_label = {"sms": "短信", "voice": "语音", "data": "数据"}.get(biz_type, biz_type)
        templates = context.user_data.get('available_templates', [])
        raw_codes = [t.get("country_code") for t in templates if t.get("country_code")]
        country_codes = dedupe_country_codes_from_templates(raw_codes)
        
        keyboard = []
        row = []
        for country_code in country_codes:
            label = COUNTRY_NAMES.get(country_code, country_code)
            row.append(InlineKeyboardButton(label, callback_data=f"country_{country_code}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("⬅️ 返回", callback_data="back_to_biz")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"📍 **选择国家** ({biz_label})\n\n请选择目标国家：",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return SELECT_COUNTRY
    
    template_id = int(data.replace("tpl_", ""))
    templates = context.user_data.get('available_templates', [])
    tpl = next((t for t in templates if t.get("id") == template_id), None)
    
    if not tpl:
        await query.edit_message_text("❌ 模板不存在")
        return ConversationHandler.END
    
    context.user_data['template_id'] = template_id
    context.user_data['template_name'] = tpl.get('template_name')
    context.user_data['template_code'] = tpl.get('template_code')
    context.user_data['default_price'] = float(tpl.get('default_price')) if tpl.get('default_price') else 0.05
    context.user_data['supplier_group_id'] = tpl.get('supplier_group_id')
    
    # 询问是否使用默认价格
    default_price = context.user_data['default_price']
    keyboard = [
        [InlineKeyboardButton(f"✅ 使用默认价格 ${default_price:.4f}", callback_data="use_default")],
        [InlineKeyboardButton("💰 自定义价格", callback_data="custom_price")],
        [InlineKeyboardButton("⬅️ 返回", callback_data="back_to_template")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"💵 **设置价格**\n\n"
        f"模板: {tpl.get('template_name')}\n"
        f"默认价格: ${default_price:.4f}\n\n"
        f"请选择价格方案：",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return INPUT_PRICE


async def input_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理价格输入"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data == "back_to_template":
        # 返回模板选择
        country_code = context.user_data['country_code']
        templates = context.user_data.get('available_templates', [])
        filtered_templates = [t for t in templates if t.get("country_code", "").upper() == country_code]
        
        keyboard = []
        for tpl in filtered_templates:
            price_str = f"${float(tpl.get('default_price')):.4f}" if tpl.get('default_price') else "待定"
            label = f"{tpl.get('template_name')} ({price_str})"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"tpl_{tpl.get('id')}")])
        keyboard.append([InlineKeyboardButton("⬅️ 返回", callback_data="back_to_country")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"📋 **选择模板** ({country_code})\n\n请选择开户模板：",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return SELECT_TEMPLATE
    
    if data == "use_default":
        context.user_data['final_price'] = context.user_data['default_price']
        return await confirm_invite(update, context)
    
    if data == "custom_price":
        await query.edit_message_text(
            "💰 请输入自定义价格（数字，例如 0.05）：\n\n发送 /cancel 取消操作"
        )
        return CONFIRM


async def receive_custom_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """接收自定义价格输入"""
    text = update.message.text.strip()
    
    try:
        price = float(text)
        if price < 0:
            await update.message.reply_text("❌ 价格不能为负数，请重新输入：")
            return CONFIRM
        context.user_data['final_price'] = price
    except ValueError:
        await update.message.reply_text("❌ 请输入有效的数字，例如 0.05：")
        return CONFIRM
    
    # 显示确认信息
    biz_type = context.user_data['business_type']
    country_code = context.user_data['country_code']
    template_name = context.user_data['template_name']
    final_price = context.user_data['final_price']
    
    keyboard = [
        [InlineKeyboardButton("✅ 确认生成", callback_data="confirm_generate")],
        [InlineKeyboardButton("❌ 取消", callback_data="cancel_all")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    biz_label = {"sms": "短信", "voice": "语音", "data": "数据"}.get(biz_type, biz_type)
    await update.message.reply_text(
        f"📦 **确认邀请码信息**\n\n"
        f"业务类型: {biz_label}\n"
        f"国家: {country_code}\n"
        f"模板: {template_name}\n"
        f"单价: ${final_price:.4f}\n"
        f"有效期: 72小时\n\n"
        f"确认生成？",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return CONFIRM


async def confirm_invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """确认并生成授权码"""
    query = update.callback_query
    await query.answer()

    biz_type = context.user_data['business_type']
    country_code = context.user_data['country_code']
    template_name = context.user_data['template_name']
    final_price = context.user_data.get('final_price', context.user_data['default_price'])

    keyboard = [
        [InlineKeyboardButton("✅ 确认生成", callback_data="confirm_generate")],
        [InlineKeyboardButton("❌ 取消", callback_data="cancel_all")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    biz_label = {"sms": "短信", "voice": "语音", "data": "数据"}.get(biz_type, biz_type)
    await query.edit_message_text(
        f"📦 *确认授权码信息*\n\n"
        f"业务类型: {biz_label}\n"
        f"国家: {country_code}\n"
        f"模板: {template_name}\n"
        f"单价: ${final_price:.4f}\n"
        f"有效期: 72小时\n\n"
        f"确认生成？",
        reply_markup=reply_markup,
        parse_mode='Markdown',
    )
    return CONFIRM


async def generate_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """生成邀请码"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data == "cancel_all":
        await query.edit_message_text("❌ 已取消")
        return ConversationHandler.END
    
    # 生成邀请码
    sales_id = context.user_data['sales_id']
    biz_type = context.user_data['business_type']
    country_code = context.user_data['country_code']
    template_id = context.user_data['template_id']
    template_code = context.user_data['template_code']
    template_name = context.user_data['template_name']
    final_price = context.user_data.get('final_price', context.user_data['default_price'])
    supplier_group_id = context.user_data.get('supplier_group_id')
    
    config = {
        "country": country_code,
        "price": final_price,
        "business_type": biz_type,
        "template_id": template_id,
        "template_code": template_code,
        "template_name": template_name,
        "supplier_group_id": supplier_group_id
    }
    
    api = APIClient()
    res = await api.create_invitation(sales_id, config)
    
    if not res.get("success"):
        await query.edit_message_text(f"❌ 生成失败: {res.get('msg')}")
        return ConversationHandler.END
        
    code = res.get("code")
    import os
    bot_username = os.getenv('TELEGRAM_BOT_USERNAME', 'kaolachbot')
    invite_link = f"https://t.me/{bot_username}?start={code}"

    biz_label = {"sms": "短信", "voice": "语音", "data": "数据"}.get(biz_type, biz_type)
    await query.edit_message_text(
        f"✅ <b>授权码已生成</b>\n\n"
        f"📦 业务: {biz_label} - {country_code}\n"
        f"📋 模板: {context.user_data['template_name']}\n"
        f"💵 单价: ${final_price:.4f}\n"
        f"⏰ 有效期: 72小时\n\n"
        f"📋 授权码: <code>{code}</code>\n"
        f"🔗 开户链接:\n{invite_link}\n\n"
        f"━━━━━━━━━━━━\n"
        f"📤 将上方链接转发给客户\n"
        f"客户点击链接即可自动开户",
        parse_mode='HTML',
    )
    return ConversationHandler.END


async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """取消对话"""
    await update.message.reply_text("❌ 已取消邀请码生成")
    return ConversationHandler.END


from telegram.ext import MessageHandler, filters

# 创建对话处理器
invite_conversation = ConversationHandler(
    entry_points=[CommandHandler("invite", invite_start)],
    states={
        SELECT_BIZ_TYPE: [CallbackQueryHandler(select_biz_type)],
        SELECT_COUNTRY: [CallbackQueryHandler(select_country)],
        SELECT_TEMPLATE: [CallbackQueryHandler(select_template)],
        INPUT_PRICE: [CallbackQueryHandler(input_price)],
        CONFIRM: [
            CallbackQueryHandler(generate_code, pattern="^(confirm_generate|cancel_all)$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_custom_price),
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel_conversation)],
    per_message=False,
    per_user=True,
)


# 导出处理器
sales_handlers = [
    CommandHandler("bind_sales", bind_sales),
    invite_conversation,
]
