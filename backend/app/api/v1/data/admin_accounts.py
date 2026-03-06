"""管理员 - 数据账户管理 API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from sqlalchemy.orm import selectinload
from typing import Optional
from datetime import datetime
from decimal import Decimal

from app.database import get_db
from app.modules.data.data_account import DataAccount, DataExtractionLog
from app.modules.common.account import Account
from app.core.auth import get_current_admin
from app.schemas.data import DataAccountCreate, DataAccountUpdate, DataAccountRecharge
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


def _serialize_account(a: DataAccount) -> dict:
    """序列化数据账户 — 余额统一使用主账户余额"""
    acct = a.account
    balance = float(acct.balance) if acct and acct.balance else 0
    return {
        "id": a.id,
        "account_id": a.account_id,
        "account_name": acct.account_name if acct else None,
        "account_email": acct.email if acct else None,
        "balance": balance,
        "platform_account": a.platform_account,
        "country_code": a.country_code,
        "total_extracted": a.total_extracted or 0,
        "total_spent": float(a.total_spent) if a.total_spent else 0,
        "status": a.status or "active",
        "remarks": (a.extra_data or {}).get("remarks", ""),
        "last_sync_at": a.last_sync_at.isoformat() if a.last_sync_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }


# ============ 列表 + 统计 ============

@router.get("/accounts")
async def list_data_accounts(
    country_code: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """获取数据账户列表"""
    query = select(DataAccount).options(selectinload(DataAccount.account))

    if country_code:
        query = query.where(DataAccount.country_code == country_code)
    if status:
        query = query.where(DataAccount.status == status)
    if search:
        query = query.join(Account, DataAccount.account_id == Account.id).where(
            Account.account_name.ilike(f"%{search}%")
            | Account.email.ilike(f"%{search}%")
            | DataAccount.platform_account.ilike(f"%{search}%")
        )

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    result = await db.execute(
        query.order_by(DataAccount.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    accounts = result.scalars().all()

    return {
        "success": True,
        "items": [_serialize_account(a) for a in accounts],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/accounts/stats")
async def data_account_stats(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """数据账户统计"""
    total = (await db.execute(select(func.count()).select_from(DataAccount))).scalar() or 0
    active = (await db.execute(
        select(func.count()).select_from(DataAccount).where(DataAccount.status == "active")
    )).scalar() or 0
    total_balance = (await db.execute(
        select(func.coalesce(func.sum(Account.balance), 0))
        .where(Account.id.in_(select(DataAccount.account_id)))
    )).scalar() or 0
    total_spent = (await db.execute(
        select(func.coalesce(func.sum(DataAccount.total_spent), 0))
    )).scalar() or 0
    total_extracted = (await db.execute(
        select(func.coalesce(func.sum(DataAccount.total_extracted), 0))
    )).scalar() or 0

    return {
        "success": True,
        "total": total,
        "active": active,
        "total_balance": float(total_balance),
        "total_spent": float(total_spent),
        "total_extracted": int(total_extracted),
    }


@router.get("/accounts/available-accounts")
async def list_available_accounts(
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """获取未创建数据账户的本地账户列表（用于新建时选择）"""
    existing_ids_q = select(DataAccount.account_id)
    existing_result = await db.execute(existing_ids_q)
    existing_ids = {row[0] for row in existing_result.fetchall()}

    query = select(Account).where(
        Account.is_deleted == False,
        Account.status == "active",
    )
    if search:
        query = query.where(
            Account.account_name.ilike(f"%{search}%")
            | Account.email.ilike(f"%{search}%")
        )

    result = await db.execute(query.order_by(Account.id).limit(50))
    accounts = result.scalars().all()

    return {
        "success": True,
        "items": [
            {
                "id": a.id,
                "account_name": a.account_name,
                "email": a.email,
                "balance": float(a.balance) if a.balance else 0,
                "has_data_account": a.id in existing_ids,
            }
            for a in accounts
        ],
    }


# ============ CRUD ============

@router.post("/accounts")
async def create_data_account(
    data: DataAccountCreate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """创建数据账户"""
    acct_result = await db.execute(select(Account).where(Account.id == data.account_id))
    acct = acct_result.scalar_one_or_none()
    if not acct:
        raise HTTPException(status_code=404, detail="关联账户不存在")

    existing = await db.execute(
        select(DataAccount).where(DataAccount.account_id == data.account_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="该账户已存在数据账户，请勿重复创建")

    extra = {}
    if data.remarks:
        extra["remarks"] = data.remarks

    da = DataAccount(
        account_id=data.account_id,
        country_code=data.country_code or "",
        balance=Decimal("0"),
        total_extracted=0,
        total_spent=Decimal("0"),
        status="active",
        extra_data=extra or None,
    )
    db.add(da)

    # 自动在主账户 services 中加入 data
    svc = acct.services or "sms"
    svc_list = [s.strip() for s in svc.split(",") if s.strip()]
    if "data" not in svc_list:
        svc_list.append("data")
        acct.services = ",".join(svc_list)

    await db.commit()
    await db.refresh(da, attribute_names=["id", "created_at"])

    return {"success": True, "id": da.id, "message": "数据账户创建成功"}


@router.put("/accounts/{account_id}")
async def update_data_account(
    account_id: int,
    data: DataAccountUpdate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """更新数据账户"""
    result = await db.execute(select(DataAccount).where(DataAccount.id == account_id))
    da = result.scalar_one_or_none()
    if not da:
        raise HTTPException(status_code=404, detail="数据账户不存在")

    if data.country_code is not None:
        da.country_code = data.country_code
    if data.status is not None:
        da.status = data.status
    if data.remarks is not None:
        extra = da.extra_data or {}
        extra["remarks"] = data.remarks
        da.extra_data = extra

    await db.commit()
    return {"success": True, "message": "更新成功"}


@router.delete("/accounts/{account_id}")
async def delete_data_account(
    account_id: int,
    force: bool = False,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """删除数据账户。force=false 关闭，force=true 永久删除"""
    result = await db.execute(select(DataAccount).where(DataAccount.id == account_id))
    da = result.scalar_one_or_none()
    if not da:
        raise HTTPException(status_code=404, detail="数据账户不存在")

    if force:
        await db.delete(da)
        await db.commit()
        return {"success": True, "message": "数据账户已永久删除"}

    da.status = "closed"
    await db.commit()
    return {"success": True, "message": "数据账户已关闭"}


# ============ 充值 ============

@router.post("/accounts/{account_id}/recharge")
async def recharge_data_account(
    account_id: int,
    data: DataAccountRecharge,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """账户充值（充到主账户余额，短信和数据共用）"""
    result = await db.execute(
        select(DataAccount).options(selectinload(DataAccount.account))
        .where(DataAccount.id == account_id)
    )
    da = result.scalar_one_or_none()
    if not da:
        raise HTTPException(status_code=404, detail="数据账户不存在")
    if da.status == "closed":
        raise HTTPException(status_code=400, detail="已关闭的账户无法充值")
    if not da.account:
        raise HTTPException(status_code=400, detail="未关联主账户")

    amount = Decimal(str(data.amount))
    acct = da.account
    old_balance = acct.balance or Decimal("0")
    acct.balance = old_balance + amount

    log = DataExtractionLog(
        data_account_id=da.id,
        extraction_id=f"RECHARGE-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        count=0,
        unit_price=Decimal("0"),
        total_cost=-amount,
        filters={"type": "recharge", "remarks": data.remarks, "admin_id": admin.id},
        status="success",
        completed_at=datetime.now(),
    )
    db.add(log)
    await db.commit()

    return {
        "success": True,
        "message": f"充值成功 ${data.amount:.2f}",
        "old_balance": float(old_balance),
        "new_balance": float(acct.balance),
    }


# ============ 同步 ============

@router.post("/accounts/{account_id}/sync")
async def sync_data_account(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """刷新账户信息"""
    result = await db.execute(
        select(DataAccount).options(selectinload(DataAccount.account))
        .where(DataAccount.id == account_id)
    )
    da = result.scalar_one_or_none()
    if not da:
        raise HTTPException(status_code=404, detail="账户不存在")

    da.last_sync_at = datetime.now()
    da.sync_error = None
    await db.commit()

    balance = float(da.account.balance) if da.account and da.account.balance else 0
    return {
        "success": True,
        "message": "刷新成功",
        "balance": balance,
    }


# ============ 提取/充值记录 ============

@router.get("/accounts/{account_id}/logs")
async def list_account_logs(
    account_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """获取数据账户操作记录（提取+充值）"""
    query = select(DataExtractionLog).where(DataExtractionLog.data_account_id == account_id)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    result = await db.execute(
        query.order_by(DataExtractionLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    logs = result.scalars().all()

    return {
        "success": True,
        "items": [
            {
                "id": log.id,
                "extraction_id": log.extraction_id,
                "count": log.count,
                "unit_price": float(log.unit_price) if log.unit_price else 0,
                "total_cost": float(log.total_cost) if log.total_cost else 0,
                "filters": log.filters,
                "is_recharge": bool(log.filters and log.filters.get("type") == "recharge"),
                "remarks": (log.filters or {}).get("remarks", ""),
                "status": log.status,
                "error_message": log.error_message,
                "created_at": log.created_at.isoformat() if log.created_at else None,
                "completed_at": log.completed_at.isoformat() if log.completed_at else None,
            }
            for log in logs
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
