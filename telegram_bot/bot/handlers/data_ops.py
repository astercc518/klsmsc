"""
数据操作 Handler - 通过TG Bot查询和提取数据
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler
from loguru import logger

from bot.utils import get_user_binding_internal
from bot.services.api_client import APIClient


async def get_user_account(tg_id: int):
    """获取用户绑定的有效账户信息"""
    return await get_user_binding_internal(tg_id)


async def data_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /data_query [country_code] - 查询可用数据
    """
    user_id = update.effective_user.id
    account = await get_user_account(user_id)
    
    if not account:
        await update.message.reply_text("❌ 您还未绑定账户")
        return
    
    country_code = context.args[0].upper() if context.args else None
    
    try:
        api = APIClient()
        result = await api.get_public_data_stats_internal(country_code)
        
        if not result.get("success"):
            await update.message.reply_text(f"❌ 查询失败: {result.get('message', '未知错误')}")
            return
            
        stats = result.get("stats", [])
        
        if not stats:
            await update.message.reply_text(
                "📭 暂无可用数据\n\n"
                "请联系管理员补充数据源。"
            )
            return
        
        text = "📊 *公海可用数据*\n\n"
        total = 0
        for item in stats:
            country = item.get('country_code')
            count = item.get('count', 0)
            text += f"• {country}: {count:,}条\n"
            total += count
        
        text += f"\n共计: {total:,}条\n\n"
        text += "使用 `/data_extract <国家> <数量>` 提取数据"
        
        await update.message.reply_text(text, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"查询数据失败: {e}")
        await update.message.reply_text("❌ 查询失败，请稍后重试")


async def data_extract(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /data_extract <country_code> <count> - 提取数据到私有库
    """
    user_id = update.effective_user.id
    account = await get_user_account(user_id)
    
    if not account:
        await update.message.reply_text("❌ 您还未绑定账户")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "📥 *数据提取*\n\n"
            "用法: `/data_extract <国家代码> <数量>`\n\n"
            "示例: `/data_extract CN 1000`",
            parse_mode='Markdown'
        )
        return
    
    country_code = context.args[0].upper()
    try:
        count = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ 数量必须是数字")
        return
    
    if count <= 0 or count > 10000:
        await update.message.reply_text("❌ 数量必须在 1-10000 之间")
        return
    
    try:
        api = APIClient()
        result = await api.extract_data_internal(user_id, country_code, count)
        
        if result.get("success"):
            await update.message.reply_text(
                f"✅ *数据提取成功*\n\n"
                f"国家: {country_code}\n"
                f"数量: {result.get('count', count)}条\n\n"
                f"数据已添加到您的私有库。\n"
                f"使用 /data_balance 查看余额。",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(f"❌ 提取失败: {result.get('message', '可用数据不足或系统异常')}")
            
    except Exception as e:
        logger.error(f"提取数据失败: {e}")
        await update.message.reply_text("❌ 提取失败，请稍后重试")


async def data_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /data_balance - 查询数据余额（私有库）
    """
    user_id = update.effective_user.id
    account = await get_user_account(user_id)
    
    if not account:
        await update.message.reply_text("❌ 您还未绑定账户")
        return
    
    try:
        api = APIClient()
        # 注意：这里可能需要更多的 backend 统计逻辑。目前 get_data_pool_stats_internal 返回按国家分组的 available 数量
        result = await api.get_data_pool_stats_internal(account.get('account_id'))
        
        if not result.get("success"):
             await update.message.reply_text("❌ 查询余额失败")
             return

        countries = result.get("countries", [])
        
        if not countries:
            await update.message.reply_text(
                "📭 您的私有库暂无数据\n\n"
                "使用 `/data_query` 查看公海数据\n"
                "使用 `/data_extract` 提取数据",
                parse_mode='Markdown'
            )
            return
        
        text = "📦 *我的数据库*\n\n"
        total_available = 0
        
        for item in countries:
            country = item.get('country_code')
            count = item.get('count', 0)
            total_available += count
            
            text += f"🌍 {country}\n"
            text += f"   可用: {count:,}条\n\n"
        
        text += f"------------------------\n"
        text += f"总可用: {total_available:,}条\n"
        
        await update.message.reply_text(text, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"查询数据余额失败: {e}")
        await update.message.reply_text("❌ 查询失败，请稍后重试")


async def data_platform_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /dp_query [country] [carrier] - 查询外部数据平台可用数据
    """
    user_id = update.effective_user.id
    account = await get_user_account(user_id)
    
    if not account:
        await update.message.reply_text("❌ 您还未绑定账户")
        return
    
    # 获取用户的数据平台设置通常也需要通过 API
    # 鉴于数据平台逻辑复杂，这里简化，建议将该逻辑移至 backend internal_bot.py
    # 但由于时间关系，我们保持结构，增加对应的 internal 调用
    # TODO: 后续应完全移至后端
    await update.message.reply_text("⏳ 该功能正在迁移至 API，请稍后重试")


async def data_platform_extract(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /dp_extract <count> - 从数据平台提取数据
    """
    user_id = update.effective_user.id
    account = await get_user_account(user_id)
    
    if not account:
        await update.message.reply_text("❌ 您还未绑定账户")
        return
    
    await update.message.reply_text("⏳ 该功能正在迁移至 API，请稍后重试")


# 导出处理器
data_handlers = [
    CommandHandler("data_query", data_query),
    CommandHandler("data_extract", data_extract),
    CommandHandler("data_balance", data_balance),
    CommandHandler("dp_query", data_platform_query),
    CommandHandler("dp_extract", data_platform_extract),
]
