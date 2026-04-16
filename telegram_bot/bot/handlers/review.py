"""
审核处理 Handler - 供应商群审核测试工单
"""
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from loguru import logger

from bot.utils import get_group_ids
from bot.services.api_client import APIClient


async def approve_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /approve <工单号> [备注]
    供应商通过测试申请
    """
    if not context.args:
        await update.message.reply_text("用法: /approve <工单号> [备注]")
        return
    
    ticket_no = context.args[0]
    note = ' '.join(context.args[1:]) if len(context.args) > 1 else None
    
    user_name = update.effective_user.full_name or update.effective_user.username
    chat_id = update.effective_chat.id
    
    try:
        api = APIClient()
        # 调用后端接口执行审批
        result = await api.review_ticket_internal(
            ticket_no=ticket_no,
            action='approve',
            user_name=user_name,
            note=note,
            chat_id=chat_id
        )
        
        if not result.get("success"):
            await update.message.reply_text(f"❌ 审批失败: {result.get('message', '未知错误')}")
            return

        ticket_data = result.get("ticket", {})
        
        # 回复确认
        await update.message.reply_text(
            f"✅ *测试申请已通过*\n\n"
            f"工单号: `{ticket_no}`\n"
            f"审批人: {user_name}\n"
            f"备注: {note or '无'}",
            parse_mode='Markdown'
        )
        
        # 通知客户
        tg_user_id = ticket_data.get("tg_user_id")
        if tg_user_id:
            try:
                await context.bot.send_message(
                    chat_id=int(tg_user_id),
                    text=(
                        f"✅ *您的测试申请已通过*\n\n"
                        f"工单号: `{ticket_no}`\n"
                        f"审批备注: {note or '已通过，请等待测试结果'}\n\n"
                        f"技术人员将尽快为您安排测试。"
                    ),
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"通知客户失败: {e}")
        
        # 通知技术群
        gids = await get_group_ids()
        staff_gid = gids.get('tech_group_id') or gids.get('admin_group_id')
        if staff_gid:
            try:
                await context.bot.send_message(
                    chat_id=staff_gid,
                    text=(
                        f"🟢 *测试工单已通过供应商审核*\n\n"
                        f"工单号: `{ticket_no}`\n"
                        f"测试号码: `{ticket_data.get('test_phone')}`\n"
                        f"文案: {ticket_data.get('test_content', '')[:100] or '无'}\n\n"
                        f"请技术人员安排测试发送。"
                    ),
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"通知技术群失败: {e}")
                    
    except Exception as e:
        logger.error(f"审批测试工单失败: {e}")
        await update.message.reply_text("❌ 操作失败，请稍后重试")


async def reject_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /reject <工单号> [拒绝原因]
    供应商拒绝测试申请
    """
    if not context.args:
        await update.message.reply_text("用法: /reject <工单号> [拒绝原因]")
        return
    
    ticket_no = context.args[0]
    reason = ' '.join(context.args[1:]) if len(context.args) > 1 else "供应商拒绝"
    
    user_name = update.effective_user.full_name or update.effective_user.username
    chat_id = update.effective_chat.id
    
    try:
        api = APIClient()
        result = await api.review_ticket_internal(
            ticket_no=ticket_no,
            action='reject',
            user_name=user_name,
            note=reason,
            chat_id=chat_id
        )
        
        if not result.get("success"):
            await update.message.reply_text(f"❌ 操作失败: {result.get('message', '未知错误')}")
            return

        ticket_data = result.get("ticket", {})
        
        # 回复确认
        await update.message.reply_text(
            f"❌ *测试申请已拒绝*\n\n"
            f"工单号: `{ticket_no}`\n"
            f"审批人: {user_name}\n"
            f"原因: {reason}",
            parse_mode='Markdown'
        )
        
        # 通知客户
        tg_user_id = ticket_data.get("tg_user_id")
        if tg_user_id:
            try:
                await context.bot.send_message(
                    chat_id=int(tg_user_id),
                    text=(
                        f"❌ *您的测试申请被拒绝*\n\n"
                        f"工单号: `{ticket_no}`\n"
                        f"拒绝原因: {reason}\n\n"
                        f"如有疑问请联系您的销售代表。"
                    ),
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"通知客户失败: {e}")
        
        # 通知技术群
        gids = await get_group_ids()
        staff_gid = gids.get('tech_group_id') or gids.get('admin_group_id')
        if staff_gid:
            try:
                await context.bot.send_message(
                    chat_id=staff_gid,
                    text=(
                        f"🔴 *测试工单被供应商拒绝*\n\n"
                        f"工单号: `{ticket_no}`\n"
                        f"拒绝原因: {reason}\n\n"
                        f"工单已自动关闭。"
                    ),
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"通知员工群失败: {e}")
                    
    except Exception as e:
        logger.error(f"拒绝测试工单失败: {e}")
        await update.message.reply_text("❌ 操作失败，请稍后重试")


async def test_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /test_result <工单号> <成功|失败> [备注]
    技术人员反馈测试结果
    """
    if len(context.args) < 2:
        await update.message.reply_text("用法: /test_result <工单号> <成功|失败> [备注]")
        return
    
    ticket_no = context.args[0]
    result_status = context.args[1].lower()
    note = ' '.join(context.args[2:]) if len(context.args) > 2 else None
    
    if result_status not in ['成功', '失败', 'success', 'fail']:
        await update.message.reply_text("❌ 状态必须是 '成功' 或 '失败'")
        return
    
    is_success = result_status in ['成功', 'success']
    user_name = update.effective_user.full_name or update.effective_user.username
    
    try:
        api = APIClient()
        result = await api.submit_test_result_internal(
            ticket_no=ticket_no,
            success=is_success,
            user_name=user_name,
            note=note
        )
        
        if not result.get("success"):
            await update.message.reply_text(f"❌ 记录失败: {result.get('message', '未知错误')}")
            return
            
        # 回复确认
        emoji = "✅" if is_success else "❌"
        await update.message.reply_text(
            f"{emoji} *测试结果已记录*\n\n"
            f"工单号: `{ticket_no}`\n"
            f"结果: {'成功' if is_success else '失败'}\n"
            f"备注: {note or '无'}",
            parse_mode='Markdown'
        )
        
        # 通知客户
        tg_user_id = result.get("tg_user_id")
        if tg_user_id:
            try:
                if is_success:
                    msg = (
                        f"✅ *测试成功*\n\n"
                        f"工单号: `{ticket_no}`\n"
                        f"测试号码: `{result.get('test_phone')}`\n\n"
                        f"通道测试已完成，您可以开始正式发送。\n"
                        f"如需群发，请使用 /mass 命令。"
                    )
                else:
                    msg = (
                        f"❌ *测试失败*\n\n"
                        f"工单号: `{ticket_no}`\n"
                        f"失败原因: {note or '未知'}\n\n"
                        f"请联系您的销售代表获取更多信息。"
                    )
                
                await context.bot.send_message(
                    chat_id=int(tg_user_id),
                    text=msg,
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"通知客户失败: {e}")
                    
    except Exception as e:
        logger.error(f"记录测试结果失败: {e}")
        await update.message.reply_text("❌ 操作失败，请稍后重试")


# 导出处理器
review_handlers = [
    CommandHandler("approve", approve_test),
    CommandHandler("reject", reject_test),
    CommandHandler("test_result", test_result),
]
