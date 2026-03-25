"""
认证与账户管理 Handler
"""
import redis
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from bot.utils import get_session, get_valid_customer_binding_and_account, logger
from bot.config import settings
from app.core.invitation import InvitationService
from app.modules.common.telegram_binding import TelegramBinding
from app.modules.common.telegram_user import TelegramUser
from app.modules.common.account import Account
from app.modules.common.admin_user import AdminUser
from sqlalchemy import select, update as sa_update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from bot.handlers.menu import (
    get_main_menu_customer, get_main_menu_sales, 
    get_main_menu_tech, get_main_menu_guest
)

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
        async with get_session() as db:
            # 1. 检查是否带邀请码（授权码开户）
            if args and len(args) > 0:
                code = args[0]
                try:
                    service = InvitationService(db)
                    account, api_key, extra_info = await service.activate_code(
                        code,
                        tg_id,
                        tg_username=user.username,
                        tg_first_name=user.first_name,
                    )

                    context.user_data['account_id'] = account.id
                    context.user_data['user_type'] = 'customer'

                    business_type = extra_info.get('business_type', 'sms')
                    biz_label = {'sms': '短信', 'voice': '语音', 'data': '数据'}.get(business_type, business_type)
                    tpl_name = extra_info.get('template_name', '')
                    login_account = extra_info.get('login_account', account.account_name)
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
                        f"🆔 账户ID: <code>{account.id}</code>\n"
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

                    await update.message.reply_text(
                        msg,
                        parse_mode='HTML',
                        reply_markup=get_main_menu_customer(),
                    )
                    return

                except ValueError as e:
                    await update.message.reply_text(
                        f"❌ 授权码无效或已过期\n\n请联系销售获取新的授权码。",
                        reply_markup=get_main_menu_guest(),
                    )
                    return
                except Exception as e:
                    logger.error(f"Activation error: {e}", exc_info=True)
                    await update.message.reply_text("❌ 系统错误，请稍后重试。")
                    return

            # 2. 检查是否是员工/管理员
            admin_query = select(AdminUser).where(
                AdminUser.tg_id == tg_id,
                AdminUser.status == 'active'
            )
            admin_result = await db.execute(admin_query)
            admin = admin_result.scalar_one_or_none()
            
            if admin:
                # 补全 tg_username（历史绑定可能未保存，每次 /start 时同步）
                if not admin.tg_username and update.effective_user:
                    admin.tg_username = (
                        update.effective_user.username
                        or update.effective_user.first_name
                        or str(tg_id)
                    )
                    await db.commit()
                # 员工/管理员登录
                context.user_data['user_type'] = 'admin'
                context.user_data['user_id'] = admin.id
                context.user_data['user_role'] = admin.role
                
                role_map = {
                    'super_admin': '超级管理员',
                    'admin': '管理员',
                    'sales': '销售',
                    'finance': '财务',
                    'tech': '技术'
                }
                role_label = role_map.get(admin.role, admin.role)
                display_name = admin.real_name or admin.username or '用户'
                
                # 根据角色选择菜单
                if admin.role in ['super_admin', 'admin', 'tech']:
                    menu = get_main_menu_tech()
                    msg = (
                        f"👋 欢迎回来，{display_name}\n\n"
                        f"🔐 身份: {role_label}\n"
                        f"👤 账号: {admin.username}\n\n"
                        f"请选择操作："
                    )
                else:
                    menu = get_main_menu_sales()
                    monthly = float(admin.monthly_commission or 0)
                    msg = (
                        f"👋 姓名: {display_name}\n"
                        f"🔐 角色: {role_label}\n"
                        f"💰 本月佣金: ${monthly:.2f}\n\n"
                        f"请选择操作：\n\n"
                        f"📢 全行业短信群发，AI语音，渗透数据！\n"
                        f"所有信息以官网 https://www.kaolach.com/ 展示为准！"
                    )
                await update.message.reply_text(msg, reply_markup=menu)
                return
            
            # 3. 检查客户绑定状态（须未删除且非 closed，与菜单回调一致）
            active_binding, account = await get_valid_customer_binding_and_account(db, tg_id)

            if not account:
                logger.info(f"User {tg_id} has no active account, sending guest menu")
                context.user_data.pop("account_id", None)
                context.user_data.pop("user_type", None)
                await update.message.reply_text(
                    "👋 欢迎使用 TG 业务助手\n\n"
                    "支持短信、语音、数据三大业务\n\n"
                    "请选择操作：",
                    reply_markup=get_main_menu_guest()
                )
                return

            # 4. 有效账户
            context.user_data['account_id'] = active_binding.account_id
            context.user_data['user_type'] = 'customer'
            
            balance_str = f"${account.balance:.2f}" if account else "N/A"
            account_name = account.account_name if account else "未知"
            
            await update.message.reply_text(
                f"👋 欢迎回来，{username}\n\n"
                f"📦 账户: {account_name}\n"
                f"💰 余额: {balance_str}\n\n"
                f"📢 全行业短信群发，AI语音，渗透数据！\n"
                f"所有信息以官网 https://www.kaolach.com/ 展示为准！\n\n"
                f"请选择操作：",
                reply_markup=get_main_menu_customer()
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
    
    async with get_session() as db:
        query = select(TelegramBinding).where(TelegramBinding.tg_id == tg_id)
        result = await db.execute(query)
        bindings = result.scalars().all()
        
        if len(bindings) < 2:
            await update.message.reply_text("您当前只有一个账户，无需切换。")
            return
            
        # 这里应该展示一个 InlineKeyboard 让用户选择
        # 为了简化，如果是 /switch [account_id] 则直接切换
        # 如果只是 /switch，列出所有账户
        
        if context.args:
            target_id = int(context.args[0])
            target_binding = next((b for b in bindings if b.account_id == target_id), None)
            
            if target_binding:
                # 更新 DB 活跃状态
                await db.execute(
                    sa_update(TelegramBinding)
                    .where(TelegramBinding.tg_id == tg_id)
                    .values(is_active=False)
                )
                await db.execute(
                    sa_update(TelegramBinding)
                    .where(TelegramBinding.tg_id == tg_id, TelegramBinding.account_id == target_id)
                    .values(is_active=True)
                )
                await db.commit()
                
                context.user_data['account_id'] = target_id
                await update.message.reply_text(f"✅ 已切换到账户 `{target_id}`", parse_mode='Markdown')
            else:
                await update.message.reply_text("❌ 未找到该账户，请检查 ID。")
        else:
            msg = "📋 **您的账户列表**:\n\n"
            for b in bindings:
                active_mark = "✅ " if b.is_active else ""
                msg += f"{active_mark}ID: `{b.account_id}` - 发送 `/switch {b.account_id}` 切换\n"
            
            await update.message.reply_text(msg, parse_mode='Markdown')

async def bind_account_by_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/bindaccount <code> — 客户通过网页生成的验证码绑定 Telegram"""
    user = update.effective_user
    tg_id = user.id
    username = user.username or user.first_name

    if not context.args or len(context.args) < 1:
        await update.message.reply_text("用法: /bindaccount <6位验证码>\n请先在网页端【账户设置】生成绑定码。")
        return

    code = context.args[0].strip()
    if not code.isdigit() or len(code) != 6:
        await update.message.reply_text("❌ 验证码格式错误，应为6位数字。")
        return

    try:
        redis_host = getattr(settings, "REDIS_HOST", "redis")
        redis_port = int(getattr(settings, "REDIS_PORT", 6379))
        redis_password = getattr(settings, "REDIS_PASSWORD", None)
        r = redis.Redis(host=redis_host, port=redis_port, password=redis_password or None, decode_responses=True)
        redis_key = f"acct_tg_bind:{code}"
        account_id_str = r.get(redis_key)

        if not account_id_str:
            await update.message.reply_text("❌ 验证码无效或已过期，请重新生成。")
            return

        account_id = int(account_id_str)
        r.delete(redis_key)

        async with get_session() as db:
            acc_result = await db.execute(select(Account).where(Account.id == account_id))
            account = acc_result.scalar_one_or_none()
            if not account:
                await update.message.reply_text("❌ 账户不存在。")
                return

            account.tg_id = tg_id
            account.tg_username = username

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

            stmt = mysql_insert(TelegramUser).values(
                tg_id=tg_id, username=username, account_id=account_id
            )
            stmt = stmt.on_duplicate_key_update(username=username, account_id=account_id)
            await db.execute(stmt)
            await db.commit()

        context.user_data['account_id'] = account_id
        context.user_data['user_type'] = 'customer'

        await update.message.reply_text(
            f"✅ 绑定成功！\n\n"
            f"📦 账户: {account.account_name}\n"
            f"🆔 ID: {account_id}\n\n"
            f"发送 /start 返回主菜单。"
        )
    except Exception as e:
        logger.error(f"bindaccount error: {e}", exc_info=True)
        await update.message.reply_text("❌ 绑定失败，请稍后重试。")


auth_handlers = [
    CommandHandler("start", start),
    CommandHandler("switch", switch_account),
    CommandHandler("bindaccount", bind_account_by_code),
]
