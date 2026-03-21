"""
数据操作 Handler - 通过TG Bot查询和提取数据
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler
from loguru import logger
from datetime import datetime

from app.database import AsyncSessionLocal
from app.modules.common.telegram_binding import TelegramBinding
from app.modules.common.account import Account
from app.modules.data.models import DataNumber
from app.modules.data.data_account import DataAccount
from sqlalchemy import select, func


async def get_user_account(tg_id: int):
    """获取用户绑定的账户"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Account).join(TelegramBinding).where(
                TelegramBinding.tg_id == tg_id,
                TelegramBinding.is_active == True
            )
        )
        return result.scalar_one_or_none()


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
        async with AsyncSessionLocal() as session:
            # 查询公海数据
            query = select(
                DataNumber.country_code,
                func.count(DataNumber.id).label('count')
            ).where(
                DataNumber.status == 'available',
                DataNumber.owner_account_id.is_(None)  # 公海数据
            )
            
            if country_code:
                query = query.where(DataNumber.country_code == country_code)
            
            query = query.group_by(DataNumber.country_code)
            result = await session.execute(query)
            stats = result.all()
            
            if not stats:
                await update.message.reply_text(
                    "📭 暂无可用数据\n\n"
                    "请联系管理员补充数据源。"
                )
                return
            
            text = "📊 *公海可用数据*\n\n"
            total = 0
            for country, count in stats:
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
        async with AsyncSessionLocal() as session:
            # 查询可用数量
            available_result = await session.execute(
                select(func.count(DataNumber.id)).where(
                    DataNumber.country_code == country_code,
                    DataNumber.status == 'available',
                    DataNumber.owner_account_id.is_(None)
                )
            )
            available = available_result.scalar() or 0
            
            if available < count:
                await update.message.reply_text(
                    f"❌ 可用数据不足\n\n"
                    f"请求: {count}条\n"
                    f"可用: {available}条"
                )
                return
            
            # 提取数据
            data_result = await session.execute(
                select(DataNumber).where(
                    DataNumber.country_code == country_code,
                    DataNumber.status == 'available',
                    DataNumber.owner_account_id.is_(None)
                ).limit(count)
            )
            numbers = data_result.scalars().all()
            
            # 分配给用户
            for num in numbers:
                num.owner_account_id = account.id
                num.status = 'owned'
            
            await session.commit()
            
            await update.message.reply_text(
                f"✅ *数据提取成功*\n\n"
                f"国家: {country_code}\n"
                f"数量: {len(numbers)}条\n\n"
                f"数据已添加到您的私有库。\n"
                f"使用 /data_balance 查看余额。",
                parse_mode='Markdown'
            )
            
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
        async with AsyncSessionLocal() as session:
            # 查询用户私有数据
            query = select(
                DataNumber.country_code,
                DataNumber.status,
                func.count(DataNumber.id).label('count')
            ).where(
                DataNumber.owner_account_id == account.id
            ).group_by(DataNumber.country_code, DataNumber.status)
            
            result = await session.execute(query)
            stats = result.all()
            
            if not stats:
                await update.message.reply_text(
                    "📭 您的私有库暂无数据\n\n"
                    "使用 `/data_query` 查看公海数据\n"
                    "使用 `/data_extract` 提取数据",
                    parse_mode='Markdown'
                )
                return
            
            # 按国家整理
            by_country = {}
            for country, status, count in stats:
                if country not in by_country:
                    by_country[country] = {'available': 0, 'used': 0, 'owned': 0}
                status_key = status if status in by_country[country] else 'owned'
                by_country[country][status_key] = count
            
            text = "📦 *我的数据库*\n\n"
            total_available = 0
            total_used = 0
            
            for country, counts in by_country.items():
                available = counts.get('available', 0) + counts.get('owned', 0)
                used = counts.get('used', 0)
                total_available += available
                total_used += used
                
                text += f"🌍 {country}\n"
                text += f"   可用: {available:,}条\n"
                text += f"   已用: {used:,}条\n\n"
            
            text += f"------------------------\n"
            text += f"总可用: {total_available:,}条\n"
            text += f"总已用: {total_used:,}条"
            
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
    
    # 获取用户的数据账户
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(DataAccount).where(
                DataAccount.account_id == account.id,
                DataAccount.status == 'active'
            )
        )
        data_account = result.scalar_one_or_none()
    
    if not data_account:
        await update.message.reply_text(
            "❌ 您没有数据平台账户\n\n"
            "请联系销售开通数据业务。"
        )
        return
    
    # 构建查询条件
    filters = {}
    if len(context.args) >= 1:
        filters['country_code'] = context.args[0].upper()
    if len(context.args) >= 2:
        filters['carrier'] = context.args[1]
    
    try:
        from app.services.data_platform_client import get_data_platform_client
        
        client = get_data_platform_client()
        result = await client.query_data(filters)
        
        if result.get('success'):
            data = result.get('data', {})
            await update.message.reply_text(
                f"📊 *数据平台查询结果*\n\n"
                f"可用数量: {data.get('total_available', 0):,}条\n"
                f"单价: ${data.get('unit_price', 0):.4f}\n\n"
                f"使用 `/dp_extract <数量>` 提取数据",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(f"❌ 查询失败: {result.get('message')}")
            
    except Exception as e:
        logger.error(f"查询数据平台失败: {e}")
        await update.message.reply_text("❌ 查询失败，请稍后重试")


async def data_platform_extract(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /dp_extract <count> - 从数据平台提取数据
    """
    user_id = update.effective_user.id
    account = await get_user_account(user_id)
    
    if not account:
        await update.message.reply_text("❌ 您还未绑定账户")
        return
    
    if not context.args:
        await update.message.reply_text(
            "用法: `/dp_extract <数量>`\n\n"
            "示例: `/dp_extract 1000`",
            parse_mode='Markdown'
        )
        return
    
    try:
        count = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ 数量必须是数字")
        return
    
    if count <= 0 or count > 10000:
        await update.message.reply_text("❌ 数量必须在 1-10000 之间")
        return
    
    # 获取数据账户
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(DataAccount).where(
                DataAccount.account_id == account.id,
                DataAccount.status == 'active'
            )
        )
        data_account = result.scalar_one_or_none()
    
    if not data_account:
        await update.message.reply_text("❌ 您没有数据平台账户")
        return
    
    try:
        from app.services.data_platform_client import get_data_platform_client
        
        client = get_data_platform_client()
        result = await client.extract_data(
            data_account.external_id,
            {'country_code': data_account.country_code},
            count
        )
        
        if result.get('success'):
            data = result.get('data', {})
            numbers = data.get('numbers', [])
            
            # 导入到本地数据库
            async with AsyncSessionLocal() as session:
                for num_data in numbers:
                    num = DataNumber(
                        phone_number=num_data.get('phone'),
                        country_code=num_data.get('country_code', data_account.country_code),
                        carrier=num_data.get('carrier'),
                        owner_account_id=account.id,
                        status='owned',
                        source='data_platform'
                    )
                    session.add(num)
                await session.commit()
            
            await update.message.reply_text(
                f"✅ *数据提取成功*\n\n"
                f"提取数量: {data.get('extracted_count', 0)}条\n"
                f"费用: ${data.get('total_cost', 0):.2f}\n\n"
                f"数据已添加到您的私有库。",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(f"❌ 提取失败: {result.get('message')}")
            
    except Exception as e:
        logger.error(f"提取数据平台数据失败: {e}")
        await update.message.reply_text("❌ 提取失败，请稍后重试")


# 导出处理器
data_handlers = [
    CommandHandler("data_query", data_query),
    CommandHandler("data_extract", data_extract),
    CommandHandler("data_balance", data_balance),
    CommandHandler("dp_query", data_platform_query),
    CommandHandler("dp_extract", data_platform_extract),
]
