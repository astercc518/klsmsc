"""
客户自动重新分配任务

规则：
- 活跃度为0超过10天的客户可以重新分配员工
- 分配规则：按照员工本月佣金从高到低
- 分配后由TG助手发送通知
"""
import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.modules.common.account import Account
from app.modules.common.admin_user import AdminUser

logger = logging.getLogger(__name__)


async def calculate_actual_activity(account: Account) -> int:
    """计算实际活跃度（考虑每日递减5）"""
    base_score = account.activity_score if account.activity_score is not None else 100
    last_update = account.activity_updated_at or account.created_at
    if last_update:
        days_passed = (datetime.utcnow() - last_update).days
        score = base_score - (days_passed * 5)
        return max(0, score)
    return base_score


async def get_sales_by_commission() -> list:
    """获取销售人员列表，按本月佣金从高到低排序"""
    async with async_session_factory() as db:
        # 查询角色为sales的员工，按月佣金降序
        result = await db.execute(
            select(AdminUser)
            .where(
                AdminUser.role == 'sales',
                AdminUser.status == 'active'
            )
            .order_by(AdminUser.monthly_commission.desc())
        )
        return result.scalars().all()


async def get_inactive_customers() -> list:
    """获取需要重新分配的客户（活跃度为0超过10天）"""
    async with async_session_factory() as db:
        ten_days_ago = datetime.utcnow() - timedelta(days=10)
        
        # 查询活跃度为0开始时间超过10天的客户
        result = await db.execute(
            select(Account)
            .where(
                Account.is_deleted == False,
                Account.status == 'active',
                Account.activity_zero_since != None,
                Account.activity_zero_since <= ten_days_ago
            )
        )
        return result.scalars().all()


async def send_tg_notification(sales: AdminUser, customer: Account, old_sales: AdminUser = None):
    """发送TG分配通知"""
    try:
        # 尝试导入TG Bot模块
        from telegram_bot.bot import send_admin_notification
        
        message = f"""🔄 **客户重新分配通知**

📋 客户信息：
• 客户名称：{customer.account_name}
• 业务类型：{customer.business_type or 'sms'}
• 当前余额：{customer.balance} {customer.currency}

👤 分配给：{sales.real_name or sales.username}
"""
        if old_sales:
            message += f"👤 原销售：{old_sales.real_name or old_sales.username}\n"
        
        message += f"""
📊 分配原因：客户活跃度为0超过10天

⏰ 分配时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        # 发送给新销售
        if sales.tg_id:
            await send_admin_notification(sales.tg_id, message)
        
        # 发送给管理群
        await send_admin_notification(None, message)  # None 表示发送到管理群
        
        logger.info(f"TG通知已发送: 客户 {customer.account_name} 分配给 {sales.username}")
    except Exception as e:
        logger.error(f"发送TG通知失败: {e}")


async def reassign_inactive_customers():
    """重新分配不活跃客户"""
    logger.info("开始检查需要重新分配的客户...")
    
    # 获取按佣金排序的销售列表
    sales_list = await get_sales_by_commission()
    if not sales_list:
        logger.warning("没有可用的销售人员")
        return
    
    # 获取需要重新分配的客户
    inactive_customers = await get_inactive_customers()
    if not inactive_customers:
        logger.info("没有需要重新分配的客户")
        return
    
    logger.info(f"发现 {len(inactive_customers)} 个需要重新分配的客户")
    
    async with async_session_factory() as db:
        reassigned_count = 0
        sales_index = 0
        
        for customer in inactive_customers:
            # 轮询分配给销售（按佣金高到低）
            new_sales = sales_list[sales_index % len(sales_list)]
            
            # 跳过分配给同一个销售的情况
            if customer.sales_id == new_sales.id:
                sales_index += 1
                new_sales = sales_list[sales_index % len(sales_list)]
            
            # 记录原销售
            old_sales = None
            if customer.sales_id:
                result = await db.execute(
                    select(AdminUser).where(AdminUser.id == customer.sales_id)
                )
                old_sales = result.scalar_one_or_none()
            
            # 更新客户的销售归属
            result = await db.execute(
                select(Account).where(Account.id == customer.id)
            )
            acc = result.scalar_one_or_none()
            if acc:
                acc.sales_id = new_sales.id
                acc.activity_zero_since = None  # 重置活跃度为0的开始时间
                await db.commit()
                
                # 发送TG通知
                await send_tg_notification(new_sales, customer, old_sales)
                
                reassigned_count += 1
                logger.info(f"客户 {customer.account_name} 已分配给 {new_sales.username}")
            
            sales_index += 1
        
        logger.info(f"客户重新分配完成，共分配 {reassigned_count} 个客户")


async def update_activity_zero_tracking():
    """更新活跃度为0的跟踪时间"""
    async with async_session_factory() as db:
        result = await db.execute(
            select(Account).where(
                Account.is_deleted == False,
                Account.status == 'active'
            )
        )
        accounts = result.scalars().all()
        
        updated = 0
        for acc in accounts:
            actual_score = await calculate_actual_activity(acc)
            
            # 如果活跃度为0且没有记录开始时间
            if actual_score == 0 and acc.activity_zero_since is None:
                acc.activity_zero_since = datetime.utcnow()
                updated += 1
            # 如果活跃度不为0但有记录开始时间，清除
            elif actual_score > 0 and acc.activity_zero_since is not None:
                acc.activity_zero_since = None
                updated += 1
        
        if updated > 0:
            await db.commit()
            logger.info(f"更新了 {updated} 个客户的活跃度跟踪状态")


async def run_reassign_task():
    """运行重新分配任务（入口函数）"""
    try:
        # 先更新活跃度为0的跟踪
        await update_activity_zero_tracking()
        # 然后执行重新分配
        await reassign_inactive_customers()
    except Exception as e:
        logger.error(f"客户重新分配任务执行失败: {e}")


if __name__ == "__main__":
    # 直接运行测试
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_reassign_task())
