"""
品牌皮肤 API

- public_router: GET /brand/active —— 免鉴权,Login/Landing 登录前即需读品牌(名称/主色/Logo/favicon)
- admin_router : /admin/brands CRUD + 激活 —— 列表需登录管理员;增改删/激活需 super_admin
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.auth import AuthService
from app.modules.common.admin_user import AdminUser
from app.modules.common.brand_theme import BrandTheme

public_router = APIRouter()
admin_router = APIRouter()


def _serialize(b: BrandTheme) -> dict:
    return {
        "id": b.id,
        "name": b.name,
        "primary_color": b.primary_color,
        "logo": b.logo,
        "favicon": b.favicon,
        "is_active": bool(b.is_active),
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "updated_at": b.updated_at.isoformat() if b.updated_at else None,
    }


def _require_super(admin: AdminUser) -> None:
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="需要超级管理员权限")


# ---------- 公开:当前激活品牌 ----------
@public_router.get("/brand/active")
async def get_active_brand(db: AsyncSession = Depends(get_db)):
    row = (await db.execute(
        select(BrandTheme).where(BrandTheme.is_active == True, BrandTheme.is_deleted == False)  # noqa: E712
    )).scalars().first()
    return {"success": True, "brand": _serialize(row) if row else None}


# ---------- 管理:列表 ----------
@admin_router.get("/admin/brands")
async def list_brands(
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(BrandTheme).where(BrandTheme.is_deleted == False).order_by(BrandTheme.id.desc())  # noqa: E712
    )).scalars().all()
    return {"success": True, "items": [_serialize(b) for b in rows]}


class BrandIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    primary_color: str = Field("#2a9d8f", max_length=16)
    logo: Optional[str] = None       # data URL(base64);None=不改(更新时)
    favicon: Optional[str] = None


# ---------- 管理:新增 ----------
@admin_router.post("/admin/brands")
async def create_brand(
    payload: BrandIn,
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    _require_super(admin)
    b = BrandTheme(
        name=payload.name.strip(),
        primary_color=payload.primary_color.strip() or "#2a9d8f",
        logo=payload.logo,
        favicon=payload.favicon,
        is_active=False,
    )
    db.add(b)
    await db.commit()
    await db.refresh(b)
    return {"success": True, "id": b.id}


# ---------- 管理:编辑 ----------
@admin_router.put("/admin/brands/{bid}")
async def update_brand(
    bid: int,
    payload: BrandIn,
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    _require_super(admin)
    b = (await db.execute(
        select(BrandTheme).where(BrandTheme.id == bid, BrandTheme.is_deleted == False)  # noqa: E712
    )).scalars().first()
    if not b:
        raise HTTPException(status_code=404, detail="品牌不存在")
    b.name = payload.name.strip()
    b.primary_color = payload.primary_color.strip() or "#2a9d8f"
    # logo/favicon 传 None 表示不改;传空串表示清空
    if payload.logo is not None:
        b.logo = payload.logo or None
    if payload.favicon is not None:
        b.favicon = payload.favicon or None
    await db.commit()
    return {"success": True}


# ---------- 管理:设为激活 ----------
@admin_router.post("/admin/brands/{bid}/activate")
async def activate_brand(
    bid: int,
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    _require_super(admin)
    b = (await db.execute(
        select(BrandTheme).where(BrandTheme.id == bid, BrandTheme.is_deleted == False)  # noqa: E712
    )).scalars().first()
    if not b:
        raise HTTPException(status_code=404, detail="品牌不存在")
    # 全实例唯一激活:先清空所有,再激活目标
    await db.execute(update(BrandTheme).values(is_active=False))
    b.is_active = True
    await db.commit()
    return {"success": True}


# ---------- 管理:删除(软删) ----------
@admin_router.delete("/admin/brands/{bid}")
async def delete_brand(
    bid: int,
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    _require_super(admin)
    b = (await db.execute(
        select(BrandTheme).where(BrandTheme.id == bid, BrandTheme.is_deleted == False)  # noqa: E712
    )).scalars().first()
    if not b:
        raise HTTPException(status_code=404, detail="品牌不存在")
    if b.is_active:
        raise HTTPException(status_code=400, detail="不能删除当前激活的品牌,请先激活其它品牌")
    b.is_deleted = True
    await db.commit()
    return {"success": True}
