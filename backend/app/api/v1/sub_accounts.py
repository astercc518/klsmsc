"""
子账户管理 API（P2-2）
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import Optional

from app.database import get_db
from app.models.sub_account import SubAccount, SubAccountRole, SubAccountStatus
from app.schemas.sub_account import (
    SubAccountCreate, SubAccountUpdate, SubAccountResponse,
    SubAccountListResponse, SubAccountStats
)
from app.core.auth import get_current_account, AuthService
from app.modules.common.account import Account
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.post("/sub-accounts", response_model=SubAccountResponse, summary="创建子账户")
async def create_sub_account(
    data: SubAccountCreate,
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """
    创建子账户
    
    - **username**: 用户名（唯一）
    - **password**: 密码
    - **role**: 角色（viewer/operator/manager）
    """
    try:
        # 检查用户名是否存在
        existing = await db.execute(
            select(SubAccount).where(SubAccount.username == data.username)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="用户名已存在")
        
        # 创建子账户
        sub_account = SubAccount(
            parent_account_id=current_account.id,
            username=data.username,
            email=data.email,
            password_hash=AuthService.hash_password(data.password),
            role=data.role,
            permissions=data.permissions,
            rate_limit=data.rate_limit,
            daily_limit=data.daily_limit,
            ip_whitelist=data.ip_whitelist,
            description=data.description,
            status=SubAccountStatus.ACTIVE
        )
        
        db.add(sub_account)
        await db.commit()
        await db.refresh(sub_account)
        
        logger.info(f"Sub account created: id={sub_account.id}, parent={current_account.id}")
        
        return SubAccountResponse.from_orm(sub_account)
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to create sub account: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建失败: {str(e)}")


@router.get("/sub-accounts", response_model=SubAccountListResponse, summary="查询子账户列表")
async def list_sub_accounts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    role: Optional[SubAccountRole] = Query(None),
    status: Optional[SubAccountStatus] = Query(None),
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """查询子账户列表"""
    try:
        conditions = [
            SubAccount.parent_account_id == current_account.id,
            SubAccount.is_deleted == False
        ]
        
        if role:
            conditions.append(SubAccount.role == role)
        if status:
            conditions.append(SubAccount.status == status)
        
        # 总数
        count_query = select(func.count()).select_from(SubAccount).where(and_(*conditions))
        total = (await db.execute(count_query)).scalar()
        
        # 数据
        offset = (page - 1) * page_size
        query = select(SubAccount).where(and_(*conditions)).order_by(
            SubAccount.created_at.desc()
        ).limit(page_size).offset(offset)
        
        result = await db.execute(query)
        sub_accounts = result.scalars().all()
        
        items = [SubAccountResponse.from_orm(sa) for sa in sub_accounts]
        
        return SubAccountListResponse(
            total=total,
            items=items,
            page=page,
            page_size=page_size
        )
        
    except Exception as e:
        logger.error(f"Failed to list sub accounts: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sub-accounts/stats", response_model=SubAccountStats, summary="子账户统计")
async def get_sub_account_stats(
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取子账户统计"""
    try:
        base_condition = and_(
            SubAccount.parent_account_id == current_account.id,
            SubAccount.is_deleted == False
        )
        
        total = (await db.execute(
            select(func.count()).select_from(SubAccount).where(base_condition)
        )).scalar()
        
        active = (await db.execute(
            select(func.count()).select_from(SubAccount).where(
                base_condition, SubAccount.status == SubAccountStatus.ACTIVE
            )
        )).scalar()
        
        suspended = (await db.execute(
            select(func.count()).select_from(SubAccount).where(
                base_condition, SubAccount.status == SubAccountStatus.SUSPENDED
            )
        )).scalar()
        
        total_sent = (await db.execute(
            select(func.sum(SubAccount.total_sent)).where(base_condition)
        )).scalar() or 0
        
        return SubAccountStats(
            total_sub_accounts=total,
            active_sub_accounts=active,
            suspended_sub_accounts=suspended,
            total_sent_by_subs=total_sent
        )
        
    except Exception as e:
        logger.error(f"Failed to get stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/sub-accounts/{sub_id}", response_model=SubAccountResponse, summary="更新子账户")
async def update_sub_account(
    sub_id: int,
    data: SubAccountUpdate,
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """更新子账户信息"""
    query = select(SubAccount).where(
        SubAccount.id == sub_id,
        SubAccount.parent_account_id == current_account.id,
        SubAccount.is_deleted == False
    )
    result = await db.execute(query)
    sub_account = result.scalar_one_or_none()
    
    if not sub_account:
        raise HTTPException(status_code=404, detail="子账户不存在")
    
    try:
        if data.email is not None:
            sub_account.email = data.email
        if data.role is not None:
            sub_account.role = data.role
        if data.permissions is not None:
            sub_account.permissions = data.permissions
        if data.status is not None:
            sub_account.status = data.status
        if data.rate_limit is not None:
            sub_account.rate_limit = data.rate_limit
        if data.daily_limit is not None:
            sub_account.daily_limit = data.daily_limit
        if data.ip_whitelist is not None:
            sub_account.ip_whitelist = data.ip_whitelist
        if data.description is not None:
            sub_account.description = data.description
        
        await db.commit()
        await db.refresh(sub_account)
        
        return SubAccountResponse.from_orm(sub_account)
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to update sub account: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sub-accounts/{sub_id}", summary="删除子账户")
async def delete_sub_account(
    sub_id: int,
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """删除子账户"""
    query = select(SubAccount).where(
        SubAccount.id == sub_id,
        SubAccount.parent_account_id == current_account.id,
        SubAccount.is_deleted == False
    )
    result = await db.execute(query)
    sub_account = result.scalar_one_or_none()
    
    if not sub_account:
        raise HTTPException(status_code=404, detail="子账户不存在")
    
    try:
        sub_account.is_deleted = True
        sub_account.status = SubAccountStatus.DISABLED
        await db.commit()
        
        logger.info(f"Sub account deleted: id={sub_id}")
        
        return {"success": True, "message": "删除成功"}
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to delete sub account: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sub-accounts/{sub_id}/reset-password", summary="重置密码")
async def reset_sub_account_password(
    sub_id: int,
    new_password: str = Query(..., min_length=8, description="新密码"),
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """重置子账户密码"""
    query = select(SubAccount).where(
        SubAccount.id == sub_id,
        SubAccount.parent_account_id == current_account.id,
        SubAccount.is_deleted == False
    )
    result = await db.execute(query)
    sub_account = result.scalar_one_or_none()
    
    if not sub_account:
        raise HTTPException(status_code=404, detail="子账户不存在")
    
    try:
        sub_account.password_hash = AuthService.hash_password(new_password)
        await db.commit()
        
        logger.info(f"Sub account password reset: id={sub_id}")
        
        return {"success": True, "message": "密码已重置"}
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to reset password: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
