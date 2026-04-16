"""
认证与账户管理 Handler
"""
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from bot.utils import logger, send_and_log
from bot.services.api_client import APIClient
from bot.handlers.menu import (
    get_main_menu_customer, get_main_menu_sales, 
    get_main_menu_tech, get_main_menu_guest
)

api = APIClient()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /start [code]
    """
    user = update.effective_user
    args = context.args
    tg_id = user.id
    username = user.username or user.first_name

    logger.info(f"User {username} ({tg_id}) started bot with args: {args}")

    try:
        # 1. 检查是否带邀请码（授权码开户）
        if args and len(args) > 0:
            code = args[0]
            resp = await api.activate_invitation(
                code,
                tg_id,
                tg_username=user.username,
                tg_first_name=user.first_name
            )

            if resp.get("success"):
                account = resp["account"]
                api_key = resp["api_key"]
                extra_info = resp["extra_info"]

                context.user_data['account_id'] = account["id"]
                context.user_data['user_type'] = 'customer'

                business_type = extra_info.get('business_type', 'sms')
                biz_label = {'sms': '短信', 'voice': '语音', 'data': '数据'}.get(business_type, business_type)
                tpl_name = extra_info.get('template_name', '')
                login_account = extra_info.get('login_account', account["account_name"])
                login_password = extra_info.get('login_password', '')

                msg = f"🎉 <b>开户成功！</b>\n\n"
                if tpl_name:
                    msg += f"📋 模板: {tpl_name}\n"
                msg += (
                    f"📦 业务类型: {biz_label}\n\n"
                    f"━━━ 📱 平台登录信息 ━━━\n"
                    f"🌐 平台地址: https://www.kaolach.com\n"
                    f"👤 登录账户: <code>{login_account}</code>\n"
                    f"🔒 登录密码: <code>{login_password}</code>\n\n"
                    f"━━━ 🔧 API 接口信息 ━━━\n"
                    f"🆔 账户ID: <code>{account['id']}</code>\n"
                    f"🔑 API Key: <code>{login_account}</code>\n"
                    f"🔐 API Secret: <code>{api_key}</code>\n\n"
                )

                if business_type == 'voice' and extra_info.get('voice'):
                    voice_info = extra_info['voice']
                    if voice_info.get('success'):
                        msg += (
                            f"📞 <b>语音账户信息</b>\n"
                            f"OKCC账号: <code>{voice_info.get('okcc_account')}</code>\n"
                            f"OKCC密码: <code>{voice_info.get('okcc_password')}</code>\n\n"
                        )
                    else:
                        msg += f"⚠️ 语音账户创建: {voice_info.get('message')}\n\n"

                if business_type == 'data' and extra_info.get('data'):
                    data_info = extra_info['data']
                    if data_info.get('success'):
                        msg += f"📊 <b>数据账户信息</b>\n{data_info.get('message')}\n\n"
                    else:
                        msg += f"⚠️ 数据账户创建: {data_info.get('message')}\n\n"

                msg += "⚠️ <i>请妥善保存以上信息，密码和密钥不会再次显示</i>\n\n请选择操作："

                await send_and_log(
                    context,
                    tg_id,
                    msg,
                    parse_mode='HTML',
                    reply_markup=get_main_menu_customer(),
                )
                return
            else:
                msg = resp.get("msg", "授权码无效或已过期")
                await update.message.reply_text(
                    f"❌ {msg}\n\n请联系销售获取新的授权码。",
                    reply_markup=get_main_menu_guest(),
                )
                return

        # 2. 验证用户身份 (Admin/Customer/Guest)
        user_info = await api.verify_user(tg_id, username)
        
        if user_info.get("is_admin"):
            admin = user_info["admin"]
            context.user_data['user_type'] = 'admin'
            context.user_data['user_id'] = admin["id"]
            context.user_data['user_role'] = admin["role"]
            
            role_map = {
                'super_admin': '超级管理员',
                'admin': '管理员',
                'sales': '销售',
                'finance': '财务',
                'tech': '技术'
            }
            role_label = role_map.get(admin["role"], admin["role"])
            display_name = admin.get("real_name") or admin.get("username") or '用户'
            
            # 根据角色选择菜单
            if admin["role"] in ['super_admin', 'admin', 'tech']:
                menu = get_main_menu_tech()
                msg = (
                    f"👋 欢迎回来，{display_name}\n\n"
                    f"🔐 身份: {role_label}\n"
                    f"👤 账号: {admin.get('username')}\n\n"
                    f"请选择操作："
                )
            else:
                menu = get_main_menu_sales()
                # 实时计算本月业绩和佣金
                stats_resp = await api.get_sales_stats(admin["id"])
                if stats_resp.get("success"):
                    monthly_profit = stats_resp["monthly_profit"]
                    monthly_comm = stats_resp["monthly_commission"]
                else:
                    monthly_profit = 0.0
                    monthly_comm = 0.0

                msg = (
                    f"👋 姓名: {display_name}\n"
                    f"🔐 角色: {role_label}\n"
                    f"📊 本月预计业绩: ${monthly_profit:.2f}\n"
                    f"💰 本月预计佣金: ${monthly_comm:.2f}\n\n"
                    f"请选择操作：\n\n"
                    f"📢 全行业短信群发，AI语音，渗透数据！\n"
                    f"所有信息以官网 https://www.kaolach.com/ 展示为准！"
                )
            await send_and_log(context, tg_id, msg, reply_markup=menu)
            return
        
        # 3. 客户
        if user_info.get("account"):
            account = user_info["account"]
            context.user_data['account_id'] = account["id"]
            context.user_data['user_type'] = 'customer'
            
            balance_str = f"${account['balance']:.2f}"
            account_name = account['account_name']
            
            await send_and_log(
                context,
                tg_id,
                f"👋 欢迎回来，{username}\n\n"
                f"📦 账户: {account_name}\n"
                f"💰 余额: {balance_str}\n\n"
                f"📢 全行业短信群发，AI语音，渗透数据！\n"
                f"所有信息以官网 https://www.kaolach.com/ 展示为准！\n\n"
                f"请选择操作：",
                reply_markup=get_main_menu_customer()
            )
            return

        # 4. 访客
        logger.info(f"User {tg_id} has no active account, sending guest menu")
        context.user_data.pop("account_id", None)
        context.user_data.pop("user_type", None)
        await update.message.reply_text(
            "👋 欢迎使用 TG 业务助手\n\n"
            "支持短信、语音、数据三大业务\n\n"
            "请选择操作：",
            reply_markup=get_main_menu_guest()
        )

    except Exception as e:
        logger.error(f"Start command error: {e}", exc_info=True)
        try:
            await update.message.reply_text(f"❌ 系统错误，请稍后重试")
        except:
            pass

async def switch_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /switch - 切换账户
    """
    tg_id = update.effective_user.id
    
    resp = await api.get_user_bindings(tg_id)
    if not resp.get("success"):
        await update.message.reply_text("❌ 无法获取账户列表。")
        return
        
    bindings = resp.get("bindings", [])
    if len(bindings) < 2:
        await update.message.reply_text("您当前只有一个账户，无需切换。")
        return
        
    if context.args:
        try:
            target_id = int(context.args[0])
            target_binding = next((b for b in bindings if b["account_id"] == target_id), None)
            
            if target_binding:
                switch_resp = await api.switch_account(tg_id, target_id)
                if switch_resp.get("success"):
                    context.user_data['account_id'] = target_id
                    await update.message.reply_text(f"✅ 已切换到账户 `{target_id}`", parse_mode='Markdown')
                else:
                    await update.message.reply_text(f"❌ 切换失败: {switch_resp.get('msg')}")
            else:
                await update.message.reply_text("❌ 未找到该账户，请检查 ID。")
        except ValueError:
            await update.message.reply_text("❌ 请输入有效的数字 ID。")
    else:
        msg = "📋 **您的账户列表**:\n\n"
        for b in bindings:
            active_mark = "✅ " if b["is_active"] else ""
            msg += f"{active_mark}ID: `{b['account_id']}` ({b['account_name']}) - 发送 `/switch {b['account_id']}` 切换\n"
        
        await update.message.reply_text(msg, parse_mode='Markdown')

async def bind_account_by_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/bindaccount <code> — 客户通过网页生成的验证码绑定 Telegram"""
    user = update.effective_user
    tg_id = user.id
    username = (user.username or user.first_name or str(tg_id))

    if not context.args or len(context.args) < 1:
        await update.message.reply_text("用法: /bindaccount <6位验证码>\n请先在网页端【账户设置】生成绑定码。")
        return

    code = context.args[0].strip()
    if not code.isdigit() or len(code) != 6:
        await update.message.reply_text("❌ 验证码格式错误，应为6位数字。")
        return

    try:
        resp = await api.bind_account_by_code(code, tg_id, username)
        if resp.get("success"):
            account_id = resp["account_id"]
            context.user_data['account_id'] = account_id
            context.user_data['user_type'] = 'customer'

            await update.message.reply_text(
                f"✅ 绑定成功！\n\n"
                f"📦 账户: {resp['account_name']}\n"
                f"🆔 ID: {account_id}\n\n"
                f"发送 /start 返回主菜单。"
            )
        else:
            await update.message.reply_text(f"❌ 绑定失败: {resp.get('msg')}")
    except Exception as e:
        logger.error(f"bindaccount error: {e}", exc_info=True)
        await update.message.reply_text("❌ 绑定失败，请稍后重试。")

auth_handlers = [
    CommandHandler("start", start),
    CommandHandler("switch", switch_account),
    CommandHandler("bindaccount", bind_account_by_code),
]


auth_handlers = [
    CommandHandler("start", start),
    CommandHandler("switch", switch_account),
    CommandHandler("bindaccount", bind_account_by_code),
]
