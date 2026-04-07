"""
审核处理 Handler - 供应商群审核测试工单
"""
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from loguru import logger
from datetime import datetime
import os

from app.database import AsyncSessionLocal
from app.modules.common.ticket import Ticket
from app.modules.common.account import Account
from app.modules.common.telegram_binding import TelegramBinding
from sqlalchemy import select

from bot.utils import get_group_ids


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
    
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name or update.effective_user.username
    chat_id = update.effective_chat.id
    
    try:
        async with AsyncSessionLocal() as session:
            # 查找工单
            result = await session.execute(
                select(Ticket).where(Ticket.ticket_no == ticket_no)
            )
            ticket = result.scalar_one_or_none()
            
            if not ticket:
                await update.message.reply_text(f"❌ 工单 {ticket_no} 不存在")
                return
            
            if ticket.ticket_type != 'test':
                await update.message.reply_text("❌ 此工单不是测试工单")
                return
            
            if ticket.review_status not in ['pending', 'forwarded']:
                await update.message.reply_text(f"❌ 工单已处理，当前状态: {ticket.review_status}")
                return
            
            # 验证是否来自正确的供应商群
            if ticket.forwarded_to_group and str(chat_id) != ticket.forwarded_to_group:
                await update.message.reply_text("❌ 请在对应的供应商群中操作")
                return
            
            # 更新工单状态
            ticket.review_status = 'approved'
            ticket.reviewed_at = datetime.now()
            ticket.review_note = f"审批人: {user_name}\n" + (note or "通过")
            ticket.status = 'in_progress'  # 转为处理中状态
            
            await session.commit()
            
            # 回复确认
            await update.message.reply_text(
                f"✅ *测试申请已通过*\n\n"
                f"工单号: `{ticket_no}`\n"
                f"审批人: {user_name}\n"
                f"备注: {note or '无'}",
                parse_mode='Markdown'
            )
            
            # 通知客户
            if ticket.tg_user_id:
                try:
                    await context.bot.send_message(
                        chat_id=int(ticket.tg_user_id),
                        text=(
                            f"✅ *您的测试申请已通过*\n\n"
                            f"工单号: `{ticket.ticket_no}`\n"
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
                            f"工单号: `{ticket.ticket_no}`\n"
                            f"测试号码: `{ticket.test_phone}`\n"
                            f"文案: {ticket.test_content[:100] if ticket.test_content else '无'}\n\n"
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
    
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name or update.effective_user.username
    chat_id = update.effective_chat.id
    
    try:
        async with AsyncSessionLocal() as session:
            # 查找工单
            result = await session.execute(
                select(Ticket).where(Ticket.ticket_no == ticket_no)
            )
            ticket = result.scalar_one_or_none()
            
            if not ticket:
                await update.message.reply_text(f"❌ 工单 {ticket_no} 不存在")
                return
            
            if ticket.ticket_type != 'test':
                await update.message.reply_text("❌ 此工单不是测试工单")
                return
            
            if ticket.review_status not in ['pending', 'forwarded']:
                await update.message.reply_text(f"❌ 工单已处理，当前状态: {ticket.review_status}")
                return
            
            # 验证是否来自正确的供应商群
            if ticket.forwarded_to_group and str(chat_id) != ticket.forwarded_to_group:
                await update.message.reply_text("❌ 请在对应的供应商群中操作")
                return
            
            # 更新工单状态
            ticket.review_status = 'rejected'
            ticket.reviewed_at = datetime.now()
            ticket.review_note = f"审批人: {user_name}\n拒绝原因: {reason}"
            ticket.status = 'closed'
            ticket.close_reason = f"供应商拒绝: {reason}"
            ticket.closed_at = datetime.now()
            
            await session.commit()
            
            # 回复确认
            await update.message.reply_text(
                f"❌ *测试申请已拒绝*\n\n"
                f"工单号: `{ticket_no}`\n"
                f"审批人: {user_name}\n"
                f"原因: {reason}",
                parse_mode='Markdown'
            )
            
            # 通知客户
            if ticket.tg_user_id:
                try:
                    await context.bot.send_message(
                        chat_id=int(ticket.tg_user_id),
                        text=(
                            f"❌ *您的测试申请被拒绝*\n\n"
                            f"工单号: `{ticket.ticket_no}`\n"
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
                            f"工单号: `{ticket.ticket_no}`\n"
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
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Ticket).where(Ticket.ticket_no == ticket_no)
            )
            ticket = result.scalar_one_or_none()
            
            if not ticket:
                await update.message.reply_text(f"❌ 工单 {ticket_no} 不存在")
                return
            
            if ticket.ticket_type != 'test':
                await update.message.reply_text("❌ 此工单不是测试工单")
                return
            
            # 更新工单
            ticket.status = 'resolved'
            ticket.resolved_at = datetime.now()
            ticket.resolution = f"测试{'成功' if is_success else '失败'}\n操作人: {user_name}\n" + (note or "")
            
            # 保存测试结果到extra_data
            extra = ticket.extra_data or {}
            extra['test_result'] = {
                'success': is_success,
                'note': note,
                'operator': user_name,
                'time': datetime.now().isoformat()
            }
            ticket.extra_data = extra
            
            await session.commit()
            
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
            if ticket.tg_user_id:
                try:
                    if is_success:
                        msg = (
                            f"✅ *测试成功*\n\n"
                            f"工单号: `{ticket.ticket_no}`\n"
                            f"测试号码: `{ticket.test_phone}`\n\n"
                            f"通道测试已完成，您可以开始正式发送。\n"
                            f"如需群发，请使用 /mass 命令。"
                        )
                    else:
                        msg = (
                            f"❌ *测试失败*\n\n"
                            f"工单号: `{ticket.ticket_no}`\n"
                            f"失败原因: {note or '未知'}\n\n"
                            f"请联系您的销售代表获取更多信息。"
                        )
                    
                    await context.bot.send_message(
                        chat_id=int(ticket.tg_user_id),
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
