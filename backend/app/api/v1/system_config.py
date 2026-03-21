"""
系统配置管理API — 含审计日志、导出/导入
"""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.core.auth import AuthService
from app.modules.common.admin_user import AdminUser
from app.modules.common.system_config import SystemConfig
from app.services.config_service import ConfigService
from app.utils.logger import get_logger
from pydantic import BaseModel

logger = get_logger(__name__)
router = APIRouter()

# ==================== 分类定义 ====================

CONFIG_CATEGORIES = [
    {"key": "general", "label": "基础设置", "label_en": "General"},
    {"key": "sms", "label": "短信设置", "label_en": "SMS"},
    {"key": "telegram", "label": "Telegram Bot", "label_en": "Telegram Bot"},
    {"key": "notification", "label": "通知与告警", "label_en": "Notification"},
    {"key": "security", "label": "安全设置", "label_en": "Security"},
]


# ==================== Schemas ====================

class ConfigCreateRequest(BaseModel):
    config_key: str
    config_value: str
    config_type: str = "string"
    category: str = "general"
    description: Optional[str] = None
    is_public: bool = False


class ConfigUpdateRequest(BaseModel):
    config_value: str
    description: Optional[str] = None
    is_public: Optional[bool] = None


class BatchUpdateRequest(BaseModel):
    items: Dict[str, str]


class ImportRequest(BaseModel):
    items: List[Dict[str, Any]]
    overwrite: bool = False


# ==================== 权限 ====================

def _require_admin(admin: AdminUser):
    if admin.role not in ("super_admin", "admin"):
        raise HTTPException(status_code=403, detail="需要管理员权限")


# ==================== 端点 ====================

@router.get("/configs/categories")
async def list_categories(
    admin: AdminUser = Depends(AuthService.get_current_admin),
):
    """获取配置分类列表"""
    return CONFIG_CATEGORIES


@router.get("/configs/grouped")
async def list_configs_grouped(
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """获取全部配置（按分类分组，含修改人信息）"""
    _require_admin(admin)
    groups = await ConfigService.get_all_grouped(db)
    return {
        "categories": CONFIG_CATEGORIES,
        "groups": groups,
    }


@router.get("/configs")
async def list_configs(
    is_public: Optional[bool] = None,
    search: Optional[str] = None,
    category: Optional[str] = None,
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """获取系统配置列表"""
    _require_admin(admin)
    query = select(SystemConfig)
    if category:
        query = query.where(SystemConfig.category == category)
    if is_public is not None:
        query = query.where(SystemConfig.is_public == is_public)
    if search:
        query = query.where(
            SystemConfig.config_key.like(f"%{search}%")
            | SystemConfig.description.like(f"%{search}%")
        )
    query = query.order_by(SystemConfig.category, SystemConfig.config_key)
    result = await db.execute(query)
    return [
        {
            "id": c.id,
            "config_key": c.config_key,
            "config_value": c.config_value,
            "config_type": c.config_type,
            "category": c.category or "general",
            "description": c.description,
            "is_public": c.is_public,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            "updated_by": c.updated_by,
        }
        for c in result.scalars().all()
    ]


@router.get("/configs/{key}")
async def get_config(
    key: str,
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """获取单个配置"""
    result = await db.execute(
        select(SystemConfig).where(SystemConfig.config_key == key)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")
    if not config.is_public and admin.role not in ("super_admin", "admin"):
        raise HTTPException(status_code=403, detail="无权查看")
    return {
        "id": config.id,
        "config_key": config.config_key,
        "config_value": config.config_value,
        "config_type": config.config_type,
        "category": config.category or "general",
        "description": config.description,
        "is_public": config.is_public,
        "updated_at": config.updated_at.isoformat() if config.updated_at else None,
        "updated_by": config.updated_by,
    }


@router.post("/configs")
async def create_config(
    request: ConfigCreateRequest,
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """创建系统配置"""
    _require_admin(admin)

    existing = await db.execute(
        select(SystemConfig).where(SystemConfig.config_key == request.config_key)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="配置键已存在")

    _validate_value(request.config_value, request.config_type)

    cfg = await ConfigService.create(
        request.config_key, request.config_value, db,
        config_type=request.config_type,
        category=request.category,
        description=request.description,
        is_public=request.is_public,
        admin_id=admin.id,
        admin_name=admin.username,
    )
    return {"success": True, "id": cfg.id}


@router.put("/configs/{key}")
async def update_config(
    key: str,
    request: ConfigUpdateRequest,
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """更新单个配置"""
    _require_admin(admin)

    result = await db.execute(
        select(SystemConfig).where(SystemConfig.config_key == key)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")

    _validate_value(request.config_value, config.config_type)

    await ConfigService.set(
        key, request.config_value, db,
        admin_id=admin.id,
        admin_name=admin.username,
        description=request.description,
    )
    if request.is_public is not None:
        config.is_public = request.is_public

    return {"success": True}


@router.put("/configs")
async def batch_update_configs(
    request: BatchUpdateRequest,
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """批量更新配置（含类型校验 + 审计）"""
    _require_admin(admin)
    try:
        count = await ConfigService.batch_update(
            request.items, db,
            admin_id=admin.id,
            admin_name=admin.username,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True, "updated": count}


@router.delete("/configs/{key}")
async def delete_config(
    key: str,
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """删除配置"""
    _require_admin(admin)
    ok = await ConfigService.delete(
        key, db, admin_id=admin.id, admin_name=admin.username,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="配置不存在")
    return {"success": True}


# ==================== 审计日志 ====================

@router.get("/configs-audit")
async def list_audit_logs(
    config_key: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """查询配置变更审计日志"""
    _require_admin(admin)
    offset = (page - 1) * limit
    return await ConfigService.get_audit_logs(
        db, config_key=config_key, limit=limit, offset=offset
    )


# ==================== 导出 / 导入 ====================

@router.get("/configs-export")
async def export_configs(
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """导出所有配置为 JSON"""
    _require_admin(admin)
    data = await ConfigService.export_all(db)
    return JSONResponse(
        content={"configs": data, "total": len(data)},
        headers={"Content-Disposition": "attachment; filename=system_configs.json"},
    )


@router.post("/configs-import")
async def import_configs(
    request: ImportRequest,
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """导入配置"""
    _require_admin(admin)
    result = await ConfigService.import_configs(
        request.items, db,
        admin_id=admin.id,
        admin_name=admin.username,
        overwrite=request.overwrite,
    )
    return {"success": True, **result}


# ==================== 工具 ====================

def _validate_value(value: str, config_type: str):
    """校验值与类型是否匹配"""
    if config_type == "number":
        try:
            float(value)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"值 '{value}' 不是有效数字")
    elif config_type == "boolean":
        if value.lower() not in ("true", "false", "1", "0", "yes", "no"):
            raise HTTPException(status_code=400, detail=f"值 '{value}' 不是有效布尔值")
    elif config_type == "json":
        import json
        try:
            json.loads(value)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"值不是有效 JSON: {e}")
