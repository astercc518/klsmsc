"""
系统配置管理API
"""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.core.auth import AuthService
from app.modules.common.admin_user import AdminUser
from app.modules.common.system_config import SystemConfig
from app.utils.logger import get_logger
from pydantic import BaseModel
from datetime import datetime

logger = get_logger(__name__)
router = APIRouter()

# --- Schemas ---

class ConfigCreateRequest(BaseModel):
    config_key: str
    config_value: str
    config_type: str = "string"
    description: Optional[str] = None
    is_public: bool = False

class ConfigUpdateRequest(BaseModel):
    config_value: str
    description: Optional[str] = None
    is_public: Optional[bool] = None

# --- Endpoints ---

@router.get("/configs")
async def list_configs(
    is_public: Optional[bool] = None,
    search: Optional[str] = None,
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """获取系统配置列表"""
    if admin.role not in ['super_admin', 'admin']:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    
    query = select(SystemConfig)
    
    if is_public is not None:
        query = query.where(SystemConfig.is_public == is_public)
    
    if search:
        query = query.where(
            SystemConfig.config_key.like(f"%{search}%") |
            SystemConfig.description.like(f"%{search}%")
        )
    
    query = query.order_by(SystemConfig.config_key)
    result = await db.execute(query)
    configs = result.scalars().all()
    
    return [
        {
            "id": c.id,
            "config_key": c.config_key,
            "config_value": c.config_value,
            "config_type": c.config_type,
            "description": c.description,
            "is_public": c.is_public,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            "updated_by": c.updated_by
        }
        for c in configs
    ]

@router.get("/configs/{key}")
async def get_config(
    key: str,
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """获取单个配置"""
    result = await db.execute(
        select(SystemConfig).where(SystemConfig.config_key == key)
    )
    config = result.scalar_one_or_none()
    
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")
    
    # 非管理员只能查看公开配置
    if not config.is_public and admin.role not in ['super_admin', 'admin']:
        raise HTTPException(status_code=403, detail="无权查看")
    
    return {
        "id": config.id,
        "config_key": config.config_key,
        "config_value": config.config_value,
        "config_type": config.config_type,
        "description": config.description,
        "is_public": config.is_public,
        "updated_at": config.updated_at.isoformat() if config.updated_at else None,
        "updated_by": config.updated_by
    }

@router.post("/configs")
async def create_config(
    request: ConfigCreateRequest,
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """创建系统配置"""
    if admin.role not in ['super_admin', 'admin']:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    
    # 检查是否已存在
    existing = await db.execute(
        select(SystemConfig).where(SystemConfig.config_key == request.config_key)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="配置键已存在")
    
    config = SystemConfig(
        config_key=request.config_key,
        config_value=request.config_value,
        config_type=request.config_type,
        description=request.description,
        is_public=request.is_public,
        updated_by=admin.id
    )
    db.add(config)
    await db.commit()
    
    return {"success": True, "id": config.id}

@router.put("/configs/{key}")
async def update_config(
    key: str,
    request: ConfigUpdateRequest,
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """更新系统配置"""
    if admin.role not in ['super_admin', 'admin']:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    
    result = await db.execute(
        select(SystemConfig).where(SystemConfig.config_key == key)
    )
    config = result.scalar_one_or_none()
    
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")
    
    config.config_value = request.config_value
    if request.description is not None:
        config.description = request.description
    if request.is_public is not None:
        config.is_public = request.is_public
    config.updated_by = admin.id
    
    await db.commit()
    
    return {"success": True}

@router.delete("/configs/{key}")
async def delete_config(
    key: str,
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """删除系统配置"""
    if admin.role not in ['super_admin', 'admin']:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    
    result = await db.execute(
        select(SystemConfig).where(SystemConfig.config_key == key)
    )
    config = result.scalar_one_or_none()
    
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")
    
    await db.delete(config)
    await db.commit()
    
    return {"success": True}
