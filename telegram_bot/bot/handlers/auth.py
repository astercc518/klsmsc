"""
认证与账户管理 Handler
"""
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from bot.utils import get_session, logger
from app.core.invitation import InvitationService
from app.modules.common.telegram_binding import TelegramBinding
from app.modules.common.account import Account
from app.modules.common.admin_user import AdminUser
from sqlalchemy import select, update
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
            # 1. 检查是否带邀请码
            if args and len(args) > 0:
                code = args[0]
                try:
                    service = InvitationService(db)
                    account, api_key, extra_info = await service.activate_code(code, tg_id)
                    
                    # 切换到新账户
                    context.user_data['account_id'] = account.id
                    
                    # 构建基础消息
                    business_type = extra_info.get('business_type', 'sms')
                    biz_label = {'sms': '短信', 'voice': '语音', 'data': '数据'}.get(business_type, business_type)
                    
                    msg = (
                        f"🎉 **开户成功！**\n\n"
                        f"📦 业务类型: {biz_label}\n"
                        f"🆔 账户ID: `{account.id}`\n"
                        f"👤 用户名: {account.account_name}\n"
                        f"🔑 API Key: `{api_key}`\n"
                        f"_(请妥善保存API Key)_\n\n"
                    )
                    
                    # 添加语音账户信息
                    if business_type == 'voice' and extra_info.get('voice'):
                        voice_info = extra_info['voice']
                        if voice_info.get('success'):
                            msg += (
                                f"📞 **语音账户信息**\n"
                                f"OKCC账号: `{voice_info.get('okcc_account')}`\n"
                                f"OKCC密码: `{voice_info.get('okcc_password')}`\n"
                                f"_(请使用以上信息登录OKCC系统)_\n\n"
                            )
                        else:
                            msg += f"⚠️ 语音账户创建: {voice_info.get('message')}\n\n"
                    
                    # 添加数据账户信息
                    if business_type == 'data' and extra_info.get('data'):
                        data_info = extra_info['data']
                        if data_info.get('success'):
                            msg += (
                                f"📊 **数据账户信息**\n"
                                f"{data_info.get('message')}\n\n"
                            )
                        else:
                            msg += f"⚠️ 数据账户创建: {data_info.get('message')}\n\n"
                    
                    msg += "发送 /help 查看可用指令。"
                    
                    await update.message.reply_text(msg, parse_mode='Markdown')
                    return
                    
                except ValueError as e:
                    await update.message.reply_text(f"❌ 激活失败: {str(e)}")
                    return
                except Exception as e:
                    logger.error(f"Activation error: {e}", exc_info=True)
                    await update.message.reply_text("❌ 系统错误，请稍后重试。")
                    return

            # 2. 检查是否是员工/管理员
            admin_query = select(AdminUser).where(AdminUser.tg_id == tg_id)
            admin_result = await db.execute(admin_query)
            admin = admin_result.scalar_one_or_none()
            
            if admin:
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
                else:
                    menu = get_main_menu_sales()
                
                await update.message.reply_text(
                    f"👋 欢迎回来，{display_name}\n\n"
                    f"🔐 身份: {role_label}\n"
                    f"👤 账号: {admin.username}\n\n"
                    f"请选择操作：",
                    reply_markup=menu
                )
                return
            
            # 3. 检查客户绑定状态
            query = select(TelegramBinding).where(TelegramBinding.tg_id == tg_id)
            result = await db.execute(query)
            bindings = result.scalars().all()
            
            if not bindings:
                logger.info(f"User {tg_id} has no bindings, sending welcome message")
                try:
                    await update.message.reply_text(
                        "👋 欢迎使用 TG 业务助手\n\n"
                        "支持短信、语音、数据三大业务\n\n"
                        "请选择您的身份：",
                        reply_markup=get_main_menu_guest()
                    )
                    logger.info(f"Welcome message sent to {tg_id}")
                except Exception as e:
                    logger.error(f"Failed to send welcome message: {e}")
                return

            # 4. 确定当前活跃账户（已绑定客户）
            active_binding = next((b for b in bindings if b.is_active), bindings[0])
            context.user_data['account_id'] = active_binding.account_id
            context.user_data['user_type'] = 'customer'
            
            # 获取账户详情
            acc_result = await db.execute(select(Account).where(Account.id == active_binding.account_id))
            account = acc_result.scalar_one_or_none()
            
            balance_str = f"${account.balance:.2f}" if account else "N/A"
            account_name = account.account_name if account else "未知"
            
            await update.message.reply_text(
                f"👋 欢迎回来，{username}\n\n"
                f"📦 账户: {account_name}\n"
                f"💰 余额: {balance_str}\n\n"
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
                    update(TelegramBinding)
                    .where(TelegramBinding.tg_id == tg_id)
                    .values(is_active=False)
                )
                await db.execute(
                    update(TelegramBinding)
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

auth_handlers = [
    CommandHandler("start", start),
    CommandHandler("switch", switch_account)
]
