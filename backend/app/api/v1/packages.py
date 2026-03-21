"""
套餐管理 API（P2-3）
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import Optional, List
from datetime import datetime, timedelta

from app.database import get_db
from app.modules.common.package import Package, AccountPackage, PackageStatus
from app.schemas.package import (
    PackageResponse, PackageListResponse,
    AccountPackageResponse, PurchasePackageRequest
)
from app.core.auth import get_current_account
from app.modules.common.account import Account
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.get("/packages", response_model=PackageListResponse, summary="查询套餐列表")
async def list_packages(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[PackageStatus] = Query(None),
    is_featured: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """
    查询可用套餐列表（公开接口，无需认证）
    """
    try:
        conditions = [Package.is_deleted == False]
        
        if status:
            conditions.append(Package.status == status)
        else:
            conditions.append(Package.status == PackageStatus.ACTIVE)
            
        if is_featured is not None:
            conditions.append(Package.is_featured == is_featured)
        
        # 总数
        count_query = select(func.count()).select_from(Package).where(and_(*conditions))
        total = (await db.execute(count_query)).scalar()
        
        # 数据
        offset = (page - 1) * page_size
        query = select(Package).where(and_(*conditions)).order_by(
            Package.sort_order, Package.id
        ).limit(page_size).offset(offset)
        
        result = await db.execute(query)
        packages = result.scalars().all()
        
        items = [PackageResponse.from_orm(p) for p in packages]
        
        return PackageListResponse(
            total=total,
            items=items,
            page=page,
            page_size=page_size
        )
        
    except Exception as e:
        logger.error(f"Failed to list packages: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/packages/{package_id}", response_model=PackageResponse, summary="查询套餐详情")
async def get_package(
    package_id: int,
    db: AsyncSession = Depends(get_db)
):
    """查询套餐详情"""
    query = select(Package).where(
        Package.id == package_id,
        Package.is_deleted == False
    )
    result = await db.execute(query)
    package = result.scalar_one_or_none()
    
    if not package:
        raise HTTPException(status_code=404, detail="套餐不存在")
    
    return PackageResponse.from_orm(package)


@router.post("/packages/{package_id}/purchase", response_model=AccountPackageResponse, summary="购买套餐")
async def purchase_package(
    package_id: int,
    request: PurchasePackageRequest,
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """
    购买套餐
    
    - **package_id**: 套餐ID
    - **payment_method**: 支付方式
    """
    try:
        # 查询套餐
        package_query = select(Package).where(
            Package.id == package_id,
            Package.status == PackageStatus.ACTIVE,
            Package.is_deleted == False
        )
        package_result = await db.execute(package_query)
        package = package_result.scalar_one_or_none()
        
        if not package:
            raise HTTPException(status_code=404, detail="套餐不存在或已下架")
        
        # 检查余额是否足够
        if current_account.balance < package.price:
            raise HTTPException(status_code=400, detail="余额不足")
        
        # 扣款
        current_account.balance -= package.price
        
        # 创建账户套餐记录
        start_date = datetime.now()
        end_date = start_date + timedelta(days=package.validity_days or 30)
        
        account_package = AccountPackage(
            account_id=current_account.id,
            package_id=package.id,
            sms_remaining=package.sms_quota,
            start_date=start_date,
            end_date=end_date,
            is_active=True,
            purchase_price=package.price
        )
        
        db.add(account_package)
        await db.commit()
        await db.refresh(account_package)
        
        logger.info(f"Package purchased: package_id={package_id}, account={current_account.id}")
        
        # 构造响应
        response = AccountPackageResponse.from_orm(account_package)
        response.package_name = package.package_name
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to purchase package: {str(e)}")
        raise HTTPException(status_code=500, detail=f"购买失败: {str(e)}")


@router.get("/my-packages", response_model=List[AccountPackageResponse], summary="查询我的套餐")
async def get_my_packages(
    is_active: Optional[bool] = Query(None),
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """查询当前账户的套餐"""
    try:
        conditions = [AccountPackage.account_id == current_account.id]
        
        if is_active is not None:
            conditions.append(AccountPackage.is_active == is_active)
        
        query = select(AccountPackage, Package).join(
            Package, AccountPackage.package_id == Package.id
        ).where(and_(*conditions)).order_by(
            AccountPackage.created_at.desc()
        )
        
        result = await db.execute(query)
        rows = result.all()
        
        items = []
        for account_pkg, package in rows:
            response = AccountPackageResponse.from_orm(account_pkg)
            response.package_name = package.package_name
            items.append(response)
        
        return items
        
    except Exception as e:
        logger.error(f"Failed to get my packages: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
