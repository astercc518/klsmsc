"""
通知中心 API（P1-3）
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
from typing import Optional
from datetime import datetime, timedelta

from app.database import get_db
from app.modules.common.notification import Notification, NotificationType, NotificationPriority
from app.schemas.notification import (
    NotificationCreate, NotificationResponse,
    NotificationListResponse, NotificationStats
)
from app.core.auth import get_current_account
from app.modules.common.account import Account
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.get("/notifications", response_model=NotificationListResponse, summary="查询通知列表")
async def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    is_read: Optional[bool] = Query(None),
    notification_type: Optional[NotificationType] = Query(None),
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """
    查询通知列表
    
    - **is_read**: 是否已读（不传则返回全部）
    - **notification_type**: 通知类型筛选
    """
    try:
        conditions = [
            Notification.account_id == current_account.id,
            Notification.is_deleted == False
        ]
        
        if is_read is not None:
            conditions.append(Notification.is_read == is_read)
        if notification_type:
            conditions.append(Notification.notification_type == notification_type)
        
        # 总数
        count_query = select(func.count()).select_from(Notification).where(and_(*conditions))
        total = (await db.execute(count_query)).scalar()
        
        # 未读数
        unread_query = select(func.count()).select_from(Notification).where(
            Notification.account_id == current_account.id,
            Notification.is_read == False,
            Notification.is_deleted == False
        )
        unread_count = (await db.execute(unread_query)).scalar()
        
        # 数据
        offset = (page - 1) * page_size
        query = select(Notification).where(and_(*conditions)).order_by(
            desc(Notification.created_at)
        ).limit(page_size).offset(offset)
        
        result = await db.execute(query)
        notifications = result.scalars().all()
        
        items = [NotificationResponse.from_orm(n) for n in notifications]
        
        return NotificationListResponse(
            total=total,
            unread_count=unread_count,
            items=items,
            page=page,
            page_size=page_size
        )
        
    except Exception as e:
        logger.error(f"Failed to list notifications: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/notifications/stats", response_model=NotificationStats, summary="通知统计")
async def get_notification_stats(
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取通知统计"""
    try:
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        base_condition = and_(
            Notification.account_id == current_account.id,
            Notification.is_deleted == False
        )
        
        total = (await db.execute(
            select(func.count()).select_from(Notification).where(base_condition)
        )).scalar()
        
        unread = (await db.execute(
            select(func.count()).select_from(Notification).where(
                base_condition, Notification.is_read == False
            )
        )).scalar()
        
        today_count = (await db.execute(
            select(func.count()).select_from(Notification).where(
                base_condition, Notification.created_at >= today
            )
        )).scalar()
        
        return NotificationStats(
            total_notifications=total,
            unread_notifications=unread,
            today_notifications=today_count
        )
        
    except Exception as e:
        logger.error(f"Failed to get notification stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/notifications/{notification_id}/read", response_model=NotificationResponse, summary="标记为已读")
async def mark_notification_read(
    notification_id: int,
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """标记通知为已读"""
    query = select(Notification).where(
        Notification.id == notification_id,
        Notification.account_id == current_account.id,
        Notification.is_deleted == False
    )
    result = await db.execute(query)
    notification = result.scalar_one_or_none()
    
    if not notification:
        raise HTTPException(status_code=404, detail="通知不存在")
    
    try:
        notification.is_read = True
        notification.read_at = datetime.now()
        await db.commit()
        await db.refresh(notification)
        
        return NotificationResponse.from_orm(notification)
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to mark notification as read: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/notifications/mark-all-read", summary="全部标记为已读")
async def mark_all_read(
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """将所有未读通知标记为已读"""
    try:
        from sqlalchemy import update
        
        stmt = update(Notification).where(
            Notification.account_id == current_account.id,
            Notification.is_read == False,
            Notification.is_deleted == False
        ).values(is_read=True, read_at=datetime.now())
        
        result = await db.execute(stmt)
        await db.commit()
        
        return {"success": True, "marked_count": result.rowcount}
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to mark all as read: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/notifications/{notification_id}", summary="删除通知")
async def delete_notification(
    notification_id: int,
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """删除通知"""
    query = select(Notification).where(
        Notification.id == notification_id,
        Notification.account_id == current_account.id,
        Notification.is_deleted == False
    )
    result = await db.execute(query)
    notification = result.scalar_one_or_none()
    
    if not notification:
        raise HTTPException(status_code=404, detail="通知不存在")
    
    try:
        notification.is_deleted = True
        await db.commit()
        
        return {"success": True, "message": "删除成功"}
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to delete notification: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
