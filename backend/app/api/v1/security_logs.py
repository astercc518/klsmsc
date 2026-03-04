"""
安全日志 API（P2-4）
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
from typing import Optional
from datetime import datetime, timedelta

from app.database import get_db
from app.modules.common.security_log import SecurityLog, LoginAttempt, SecurityEventType, SecurityLevel
from app.schemas.security_log import (
    SecurityLogResponse, SecurityLogListResponse,
    LoginAttemptResponse, SecurityStats
)
from app.core.auth import get_current_account
from app.modules.common.account import Account
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.get("/security-logs", response_model=SecurityLogListResponse, summary="查询安全日志")
async def list_security_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    event_type: Optional[SecurityEventType] = Query(None),
    level: Optional[SecurityLevel] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """
    查询安全日志列表
    
    - **event_type**: 事件类型筛选
    - **level**: 安全级别筛选
    - **start_date**: 开始日期
    - **end_date**: 结束日期
    """
    try:
        conditions = [SecurityLog.account_id == current_account.id]
        
        if event_type:
            conditions.append(SecurityLog.event_type == event_type)
        if level:
            conditions.append(SecurityLog.level == level)
        if start_date:
            conditions.append(SecurityLog.created_at >= start_date)
        if end_date:
            conditions.append(SecurityLog.created_at <= end_date)
        
        # 总数
        count_query = select(func.count()).select_from(SecurityLog).where(and_(*conditions))
        total = (await db.execute(count_query)).scalar()
        
        # 数据
        offset = (page - 1) * page_size
        query = select(SecurityLog).where(and_(*conditions)).order_by(
            desc(SecurityLog.created_at)
        ).limit(page_size).offset(offset)
        
        result = await db.execute(query)
        logs = result.scalars().all()
        
        items = [SecurityLogResponse.from_orm(log) for log in logs]
        
        return SecurityLogListResponse(
            total=total,
            items=items,
            page=page,
            page_size=page_size
        )
        
    except Exception as e:
        logger.error(f"Failed to list security logs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/security-logs/stats", response_model=SecurityStats, summary="安全统计")
async def get_security_stats(
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取安全统计信息"""
    try:
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # 总事件数
        total = (await db.execute(
            select(func.count()).select_from(SecurityLog).where(
                SecurityLog.account_id == current_account.id
            )
        )).scalar()
        
        # 今日登录尝试
        login_attempts_today = (await db.execute(
            select(func.count()).select_from(LoginAttempt).where(
                LoginAttempt.username == current_account.account_name,
                LoginAttempt.created_at >= today
            )
        )).scalar()
        
        # 今日失败登录
        failed_logins = (await db.execute(
            select(func.count()).select_from(LoginAttempt).where(
                LoginAttempt.username == current_account.account_name,
                LoginAttempt.success == False,
                LoginAttempt.created_at >= today
            )
        )).scalar()
        
        # 可疑活动
        suspicious = (await db.execute(
            select(func.count()).select_from(SecurityLog).where(
                SecurityLog.account_id == current_account.id,
                SecurityLog.event_type == SecurityEventType.SUSPICIOUS_ACTIVITY
            )
        )).scalar()
        
        # 限流触发
        rate_limit = (await db.execute(
            select(func.count()).select_from(SecurityLog).where(
                SecurityLog.account_id == current_account.id,
                SecurityLog.event_type == SecurityEventType.RATE_LIMIT_EXCEEDED
            )
        )).scalar()
        
        return SecurityStats(
            total_events=total,
            login_attempts_today=login_attempts_today,
            failed_logins_today=failed_logins,
            suspicious_activities=suspicious,
            rate_limit_exceeded=rate_limit
        )
        
    except Exception as e:
        logger.error(f"Failed to get security stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/login-attempts", response_model=list[LoginAttemptResponse], summary="查询登录记录")
async def list_login_attempts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    success: Optional[bool] = Query(None),
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """查询登录尝试记录"""
    try:
        conditions = [LoginAttempt.username == current_account.account_name]
        
        if success is not None:
            conditions.append(LoginAttempt.success == success)
        
        offset = (page - 1) * page_size
        query = select(LoginAttempt).where(and_(*conditions)).order_by(
            desc(LoginAttempt.created_at)
        ).limit(page_size).offset(offset)
        
        result = await db.execute(query)
        attempts = result.scalars().all()
        
        return [LoginAttemptResponse.from_orm(attempt) for attempt in attempts]
        
    except Exception as e:
        logger.error(f"Failed to list login attempts: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
