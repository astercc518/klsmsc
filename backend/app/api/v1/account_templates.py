"""
开户模板管理API
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, cast, String
from pydantic import BaseModel, Field
from typing import Optional, List
from decimal import Decimal

from app.database import get_db
from app.modules.common.admin_user import AdminUser
from app.modules.common.account_template import AccountTemplate
from app.api.v1.admin import get_current_admin

router = APIRouter(prefix="/admin/account-templates", tags=["AccountTemplates"])


# ========== Schemas ==========
class TemplateCreateRequest(BaseModel):
    template_code: Optional[str] = None  # 可选，为空时自动生成
    template_name: str = Field(..., max_length=100)
    business_type: str = Field(..., pattern="^(sms|voice|data)$")
    country_code: str = Field(..., max_length=10)
    country_name: Optional[str] = None
    supplier_group_id: Optional[int] = None
    supplier_group_name: Optional[str] = None
    channel_ids: Optional[List[int]] = None
    external_product_id: Optional[str] = None
    default_price: Optional[Decimal] = 0.0
    pricing_rules: Optional[dict] = None
    description: Optional[str] = None
    status: str = "active"


import secrets
import string

def generate_template_code(business_type: str, country_code: str) -> str:
    """自动生成模板编码"""
    prefix = business_type.upper()
    country = country_code.upper()
    suffix = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
    return f"{prefix}_{country}_{suffix}"


class TemplateUpdateRequest(BaseModel):
    template_name: Optional[str] = None
    country_code: Optional[str] = None
    country_name: Optional[str] = None
    supplier_group_id: Optional[int] = None
    supplier_group_name: Optional[str] = None
    channel_ids: Optional[List[int]] = None
    external_product_id: Optional[str] = None
    default_price: Optional[Decimal] = None
    pricing_rules: Optional[dict] = None
    description: Optional[str] = None
    status: Optional[str] = None


# ========== API Endpoints ==========
@router.get("", response_model=dict)
async def list_templates(
    business_type: Optional[str] = None,
    country_code: Optional[str] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """获取开户模板列表"""
    query = select(AccountTemplate)
    
    if business_type:
        query = query.where(AccountTemplate.business_type == business_type)
    if country_code:
        query = query.where(AccountTemplate.country_code == country_code)
    if status:
        query = query.where(AccountTemplate.status == status)
    if keyword and (k := keyword.strip()):
        kw = f"%{k}%"
        # MySQL 下 ilike 编译为 lower(col) LIKE lower(:kw)；CAST JSON 便于搜计费模式/线路等
        pr_text = func.lower(cast(AccountTemplate.pricing_rules, String(4000)))
        query = query.where(or_(
            AccountTemplate.template_name.ilike(kw),
            AccountTemplate.template_code.ilike(kw),
            AccountTemplate.country_name.ilike(kw),
            AccountTemplate.description.ilike(kw),
            AccountTemplate.external_product_id.ilike(kw),
            pr_text.like(func.lower(kw)),
        ))
    
    # 总数
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # 分页
    query = query.order_by(AccountTemplate.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    templates = result.scalars().all()
    
    return {
        "success": True,
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": t.id,
                "template_code": t.template_code,
                "template_name": t.template_name,
                "business_type": t.business_type,
                "country_code": t.country_code,
                "country_name": t.country_name,
                "supplier_group_id": t.supplier_group_id,
                "supplier_group_name": t.supplier_group_name,
                "channel_ids": t.channel_ids,
                "external_product_id": t.external_product_id,
                "default_price": float(t.default_price) if t.default_price else 0,
                "pricing_rules": t.pricing_rules,
                "description": t.description,
                "status": t.status,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None
            }
            for t in templates
        ]
    }


@router.post("", response_model=dict)
async def create_template(
    request: TemplateCreateRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """创建开户模板"""
    # 自动生成模板编码（如果未提供）
    template_code = request.template_code
    if not template_code:
        # 尝试生成唯一编码
        for _ in range(10):
            template_code = generate_template_code(request.business_type, request.country_code)
            existing = await db.execute(
                select(AccountTemplate).where(AccountTemplate.template_code == template_code)
            )
            if not existing.scalar_one_or_none():
                break
        else:
            raise HTTPException(status_code=500, detail="无法生成唯一模板编码")
    else:
        # 检查编码唯一性
        existing = await db.execute(
            select(AccountTemplate).where(AccountTemplate.template_code == template_code)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="模板编码已存在")
    
    template = AccountTemplate(
        template_code=template_code,
        template_name=request.template_name,
        business_type=request.business_type,
        country_code=request.country_code,
        country_name=request.country_name,
        supplier_group_id=request.supplier_group_id,
        supplier_group_name=request.supplier_group_name,
        channel_ids=request.channel_ids,
        external_product_id=request.external_product_id,
        default_price=request.default_price,
        pricing_rules=request.pricing_rules,
        description=request.description,
        status=request.status,
        created_by=admin.id
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    
    return {
        "success": True,
        "message": "模板创建成功",
        "template": {
            "id": template.id,
            "template_code": template.template_code,
            "template_name": template.template_name
        }
    }


@router.get("/{template_id}", response_model=dict)
async def get_template(
    template_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """获取模板详情"""
    result = await db.execute(
        select(AccountTemplate).where(AccountTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    
    return {
        "success": True,
        "template": {
            "id": template.id,
            "template_code": template.template_code,
            "template_name": template.template_name,
            "business_type": template.business_type,
            "country_code": template.country_code,
            "country_name": template.country_name,
            "supplier_group_id": template.supplier_group_id,
            "supplier_group_name": template.supplier_group_name,
            "channel_ids": template.channel_ids,
            "external_product_id": template.external_product_id,
            "default_price": float(template.default_price) if template.default_price else 0,
            "pricing_rules": template.pricing_rules,
            "description": template.description,
            "status": template.status,
            "created_by": template.created_by,
            "created_at": template.created_at.isoformat() if template.created_at else None,
            "updated_at": template.updated_at.isoformat() if template.updated_at else None
        }
    }


@router.put("/{template_id}", response_model=dict)
async def update_template(
    template_id: int,
    request: TemplateUpdateRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """更新开户模板"""
    result = await db.execute(
        select(AccountTemplate).where(AccountTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    
    # 更新字段
    if request.template_name is not None:
        template.template_name = request.template_name
    if request.country_code is not None:
        template.country_code = request.country_code
    if request.country_name is not None:
        template.country_name = request.country_name
    if request.supplier_group_id is not None:
        template.supplier_group_id = request.supplier_group_id
    if request.supplier_group_name is not None:
        template.supplier_group_name = request.supplier_group_name
    if request.channel_ids is not None:
        template.channel_ids = request.channel_ids
    if request.external_product_id is not None:
        template.external_product_id = request.external_product_id
    if request.default_price is not None:
        template.default_price = request.default_price
    if request.pricing_rules is not None:
        template.pricing_rules = request.pricing_rules
    if request.description is not None:
        template.description = request.description
    if request.status is not None:
        template.status = request.status
    
    await db.commit()
    
    return {
        "success": True,
        "message": "模板更新成功"
    }


@router.delete("/{template_id}", response_model=dict)
async def delete_template(
    template_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """删除开户模板（真正删除）"""
    result = await db.execute(
        select(AccountTemplate).where(AccountTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    
    await db.delete(template)
    await db.commit()
    
    return {
        "success": True,
        "message": "模板已删除"
    }


@router.get("/by-type/{business_type}", response_model=dict)
async def list_templates_by_type(
    business_type: str,
    country_code: Optional[str] = None,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """按业务类型获取模板列表（用于TG Bot选择）"""
    query = select(AccountTemplate).where(
        AccountTemplate.business_type == business_type,
        AccountTemplate.status == "active"
    )
    
    if country_code:
        query = query.where(AccountTemplate.country_code == country_code)
    
    query = query.order_by(AccountTemplate.country_code, AccountTemplate.template_name)
    result = await db.execute(query)
    templates = result.scalars().all()
    
    return {
        "success": True,
        "templates": [
            {
                "id": t.id,
                "template_code": t.template_code,
                "template_name": t.template_name,
                "country_code": t.country_code,
                "country_name": t.country_name,
                "default_price": float(t.default_price) if t.default_price else 0
            }
            for t in templates
        ]
    }
