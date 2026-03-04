"""
短信模板管理 API
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import Optional
from datetime import datetime
import json

from app.database import get_db
from app.modules.sms.sms_template import SmsTemplate, TemplateStatus, TemplateCategory
from app.schemas.template import (
    TemplateCreate, TemplateUpdate, TemplateApprove,
    TemplateResponse, TemplateListResponse
)
from app.core.auth import get_current_account, get_current_admin
from app.modules.common.account import Account
from app.modules.common.admin_user import AdminUser
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.post("/templates", response_model=TemplateResponse, summary="创建短信模板")
async def create_template(
    template: TemplateCreate,
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """
    创建短信模板
    
    - **name**: 模板名称
    - **category**: 模板分类 (verification/notification/marketing)
    - **content**: 模板内容（支持变量如 {name}, {code}）
    - **variables**: 变量列表
    """
    try:
        # 创建模板
        db_template = SmsTemplate(
            account_id=current_account.id,
            name=template.name,
            category=template.category,
            content=template.content,
            variables=json.dumps(template.variables) if template.variables else None,
            status=TemplateStatus.PENDING  # 待审核
        )
        
        db.add(db_template)
        await db.commit()
        await db.refresh(db_template)
        
        logger.info(f"Template created: id={db_template.id}, account_id={current_account.id}")
        
        # 转换响应
        response = TemplateResponse.from_orm(db_template)
        if db_template.variables:
            response.variables = json.loads(db_template.variables)
        
        return response
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to create template: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建模板失败: {str(e)}")


@router.get("/templates", response_model=TemplateListResponse, summary="查询模板列表")
async def list_templates(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    category: Optional[TemplateCategory] = Query(None, description="模板分类"),
    status: Optional[TemplateStatus] = Query(None, description="审核状态"),
    keyword: Optional[str] = Query(None, description="关键词搜索"),
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """查询当前账户的模板列表"""
    try:
        # 构建查询条件
        conditions = [
            SmsTemplate.account_id == current_account.id,
            SmsTemplate.is_deleted == False
        ]
        
        if category:
            conditions.append(SmsTemplate.category == category)
        if status:
            conditions.append(SmsTemplate.status == status)
        if keyword:
            conditions.append(SmsTemplate.name.like(f"%{keyword}%"))
        
        # 查询总数
        count_query = select(func.count()).select_from(SmsTemplate).where(and_(*conditions))
        total_result = await db.execute(count_query)
        total = total_result.scalar()
        
        # 查询数据
        offset = (page - 1) * page_size
        query = select(SmsTemplate).where(and_(*conditions)).order_by(
            SmsTemplate.created_at.desc()
        ).limit(page_size).offset(offset)
        
        result = await db.execute(query)
        templates = result.scalars().all()
        
        # 转换响应
        items = []
        for t in templates:
            item = TemplateResponse.from_orm(t)
            if t.variables:
                item.variables = json.loads(t.variables)
            items.append(item)
        
        return TemplateListResponse(
            total=total,
            items=items,
            page=page,
            page_size=page_size
        )
        
    except Exception as e:
        logger.error(f"Failed to list templates: {str(e)}")
        raise HTTPException(status_code=500, detail=f"查询模板列表失败: {str(e)}")


@router.get("/templates/{template_id}", response_model=TemplateResponse, summary="查询模板详情")
async def get_template(
    template_id: int,
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """查询模板详情"""
    query = select(SmsTemplate).where(
        SmsTemplate.id == template_id,
        SmsTemplate.account_id == current_account.id,
        SmsTemplate.is_deleted == False
    )
    result = await db.execute(query)
    template = result.scalar_one_or_none()
    
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    
    response = TemplateResponse.from_orm(template)
    if template.variables:
        response.variables = json.loads(template.variables)
    
    return response


@router.put("/templates/{template_id}", response_model=TemplateResponse, summary="更新模板")
async def update_template(
    template_id: int,
    template_update: TemplateUpdate,
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """更新模板（仅待审核或已拒绝的模板可以修改）"""
    query = select(SmsTemplate).where(
        SmsTemplate.id == template_id,
        SmsTemplate.account_id == current_account.id,
        SmsTemplate.is_deleted == False
    )
    result = await db.execute(query)
    template = result.scalar_one_or_none()
    
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    
    # 只有待审核或已拒绝的模板可以修改
    if template.status not in [TemplateStatus.PENDING, TemplateStatus.REJECTED]:
        raise HTTPException(status_code=400, detail="已通过审核的模板不能修改")
    
    try:
        # 更新字段
        if template_update.name is not None:
            template.name = template_update.name
        if template_update.category is not None:
            template.category = template_update.category
        if template_update.content is not None:
            template.content = template_update.content
        if template_update.variables is not None:
            template.variables = json.dumps(template_update.variables)
        
        # 重置为待审核状态
        template.status = TemplateStatus.PENDING
        template.reject_reason = None
        
        await db.commit()
        await db.refresh(template)
        
        response = TemplateResponse.from_orm(template)
        if template.variables:
            response.variables = json.loads(template.variables)
        
        return response
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to update template: {str(e)}")
        raise HTTPException(status_code=500, detail=f"更新模板失败: {str(e)}")


@router.delete("/templates/{template_id}", summary="删除模板")
async def delete_template(
    template_id: int,
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """删除模板（软删除）"""
    query = select(SmsTemplate).where(
        SmsTemplate.id == template_id,
        SmsTemplate.account_id == current_account.id,
        SmsTemplate.is_deleted == False
    )
    result = await db.execute(query)
    template = result.scalar_one_or_none()
    
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    
    try:
        template.is_deleted = True
        await db.commit()
        
        return {"success": True, "message": "删除成功"}
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to delete template: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除模板失败: {str(e)}")


# ==================== 管理员接口 ====================

@router.get("/admin/templates", response_model=TemplateListResponse, summary="[管理员] 查询所有模板")
async def admin_list_templates(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    account_id: Optional[int] = Query(None, description="账户ID"),
    category: Optional[TemplateCategory] = Query(None),
    status: Optional[TemplateStatus] = Query(None),
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """管理员查询所有模板"""
    try:
        conditions = [SmsTemplate.is_deleted == False]
        
        if account_id:
            conditions.append(SmsTemplate.account_id == account_id)
        if category:
            conditions.append(SmsTemplate.category == category)
        if status:
            conditions.append(SmsTemplate.status == status)
        
        # 查询总数
        count_query = select(func.count()).select_from(SmsTemplate).where(and_(*conditions))
        total_result = await db.execute(count_query)
        total = total_result.scalar()
        
        # 查询数据
        offset = (page - 1) * page_size
        query = select(SmsTemplate).where(and_(*conditions)).order_by(
            SmsTemplate.created_at.desc()
        ).limit(page_size).offset(offset)
        
        result = await db.execute(query)
        templates = result.scalars().all()
        
        items = []
        for t in templates:
            item = TemplateResponse.from_orm(t)
            if t.variables:
                item.variables = json.loads(t.variables)
            items.append(item)
        
        return TemplateListResponse(
            total=total,
            items=items,
            page=page,
            page_size=page_size
        )
        
    except Exception as e:
        logger.error(f"Failed to list templates: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/templates/{template_id}/approve", response_model=TemplateResponse, summary="[管理员] 审核模板")
async def approve_template(
    template_id: int,
    approve_data: TemplateApprove,
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """管理员审核模板"""
    query = select(SmsTemplate).where(
        SmsTemplate.id == template_id,
        SmsTemplate.is_deleted == False
    )
    result = await db.execute(query)
    template = result.scalar_one_or_none()
    
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    
    try:
        template.status = approve_data.status
        template.reject_reason = approve_data.reject_reason
        template.approved_by = current_admin.id
        template.approved_at = datetime.now()
        
        await db.commit()
        await db.refresh(template)
        
        logger.info(f"Template {template_id} approved: status={approve_data.status}, admin={current_admin.id}")
        
        response = TemplateResponse.from_orm(template)
        if template.variables:
            response.variables = json.loads(template.variables)
        
        return response
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to approve template: {str(e)}")
        raise HTTPException(status_code=500, detail=f"审核失败: {str(e)}")
