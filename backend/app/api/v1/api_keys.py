"""
API密钥管理 API
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import Optional
from datetime import datetime, timedelta
import secrets
import hashlib

from app.database import get_db
from app.modules.common.api_key import ApiKey, ApiKeyStatus, ApiKeyPermission
from app.schemas.api_key import (
    ApiKeyCreate, ApiKeyUpdate, ApiKeyResponse, 
    ApiKeyCreateResponse, ApiKeyListResponse, ApiKeyStats
)
from app.core.auth import get_current_account
from app.modules.common.account import Account
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


def generate_api_key() -> str:
    """生成API Key"""
    return f"ak_{secrets.token_urlsafe(32)}"


def generate_api_secret() -> str:
    """生成API Secret"""
    return f"sk_{secrets.token_urlsafe(48)}"


def hash_secret(secret: str) -> str:
    """加密Secret"""
    return hashlib.sha256(secret.encode()).hexdigest()


@router.post("/api-keys", response_model=ApiKeyCreateResponse, summary="创建API密钥")
async def create_api_key(
    data: ApiKeyCreate,
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """
    创建API密钥
    
    - **key_name**: 密钥名称
    - **permission**: 权限级别（read_only/read_write/full）
    - **ip_whitelist**: IP白名单
    - **rate_limit**: 每分钟请求限制
    - **expires_days**: 有效期（天）
    """
    try:
        # 生成密钥
        api_key = generate_api_key()
        api_secret = generate_api_secret()
        secret_hash = hash_secret(api_secret)
        
        # 计算过期时间
        expires_at = None
        if data.expires_days:
            expires_at = datetime.now() + timedelta(days=data.expires_days)
        
        # 创建记录
        db_key = ApiKey(
            account_id=current_account.id,
            key_name=data.key_name,
            api_key=api_key,
            api_secret=secret_hash,
            permission=data.permission,
            ip_whitelist=data.ip_whitelist,
            rate_limit=data.rate_limit or 1000,
            expires_at=expires_at,
            description=data.description,
            status=ApiKeyStatus.ACTIVE
        )
        
        db.add(db_key)
        await db.commit()
        await db.refresh(db_key)
        
        logger.info(f"API Key created: id={db_key.id}, account_id={current_account.id}")
        
        # 返回响应（包含未加密的secret，仅此一次）
        response = ApiKeyCreateResponse.from_orm(db_key)
        response.api_secret = api_secret  # 明文返回（仅此一次）
        
        return response
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to create API key: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建失败: {str(e)}")


@router.get("/api-keys", response_model=ApiKeyListResponse, summary="查询密钥列表")
async def list_api_keys(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[ApiKeyStatus] = Query(None),
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """查询当前账户的API密钥列表"""
    try:
        conditions = [
            ApiKey.account_id == current_account.id,
            ApiKey.is_deleted == False
        ]
        
        if status:
            conditions.append(ApiKey.status == status)
        
        # 查询总数
        count_query = select(func.count()).select_from(ApiKey).where(and_(*conditions))
        total_result = await db.execute(count_query)
        total = total_result.scalar()
        
        # 查询数据
        offset = (page - 1) * page_size
        query = select(ApiKey).where(and_(*conditions)).order_by(
            ApiKey.created_at.desc()
        ).limit(page_size).offset(offset)
        
        result = await db.execute(query)
        keys = result.scalars().all()
        
        items = [ApiKeyResponse.from_orm(k) for k in keys]
        
        return ApiKeyListResponse(
            total=total,
            items=items,
            page=page,
            page_size=page_size
        )
        
    except Exception as e:
        logger.error(f"Failed to list API keys: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api-keys/stats", response_model=ApiKeyStats, summary="密钥统计")
async def get_api_key_stats(
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取API密钥统计信息"""
    try:
        # 总数
        total_query = select(func.count()).select_from(ApiKey).where(
            ApiKey.account_id == current_account.id,
            ApiKey.is_deleted == False
        )
        total = (await db.execute(total_query)).scalar()
        
        # 按状态统计
        active_query = select(func.count()).select_from(ApiKey).where(
            ApiKey.account_id == current_account.id,
            ApiKey.status == ApiKeyStatus.ACTIVE,
            ApiKey.is_deleted == False
        )
        active = (await db.execute(active_query)).scalar()
        
        disabled_query = select(func.count()).select_from(ApiKey).where(
            ApiKey.account_id == current_account.id,
            ApiKey.status == ApiKeyStatus.DISABLED,
            ApiKey.is_deleted == False
        )
        disabled = (await db.execute(disabled_query)).scalar()
        
        # 总使用次数
        usage_query = select(func.sum(ApiKey.usage_count)).where(
            ApiKey.account_id == current_account.id,
            ApiKey.is_deleted == False
        )
        total_usage = (await db.execute(usage_query)).scalar() or 0
        
        return ApiKeyStats(
            total_keys=total,
            active_keys=active,
            disabled_keys=disabled,
            expired_keys=0,  # 可以加过期检查逻辑
            total_usage=total_usage
        )
        
    except Exception as e:
        logger.error(f"Failed to get stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/api-keys/{key_id}", response_model=ApiKeyResponse, summary="更新密钥")
async def update_api_key(
    key_id: int,
    data: ApiKeyUpdate,
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """更新API密钥配置"""
    query = select(ApiKey).where(
        ApiKey.id == key_id,
        ApiKey.account_id == current_account.id,
        ApiKey.is_deleted == False
    )
    result = await db.execute(query)
    api_key = result.scalar_one_or_none()
    
    if not api_key:
        raise HTTPException(status_code=404, detail="密钥不存在")
    
    try:
        if data.key_name is not None:
            api_key.key_name = data.key_name
        if data.permission is not None:
            api_key.permission = data.permission
        if data.ip_whitelist is not None:
            api_key.ip_whitelist = data.ip_whitelist
        if data.rate_limit is not None:
            api_key.rate_limit = data.rate_limit
        if data.status is not None:
            api_key.status = data.status
        if data.description is not None:
            api_key.description = data.description
        
        await db.commit()
        await db.refresh(api_key)
        
        return ApiKeyResponse.from_orm(api_key)
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to update API key: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api-keys/{key_id}/regenerate", response_model=ApiKeyCreateResponse, summary="重新生成密钥")
async def regenerate_api_key(
    key_id: int,
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """重新生成API Key和Secret"""
    query = select(ApiKey).where(
        ApiKey.id == key_id,
        ApiKey.account_id == current_account.id,
        ApiKey.is_deleted == False
    )
    result = await db.execute(query)
    api_key = result.scalar_one_or_none()
    
    if not api_key:
        raise HTTPException(status_code=404, detail="密钥不存在")
    
    try:
        # 生成新密钥
        new_key = generate_api_key()
        new_secret = generate_api_secret()
        secret_hash = hash_secret(new_secret)
        
        api_key.api_key = new_key
        api_key.api_secret = secret_hash
        api_key.usage_count = 0  # 重置使用次数
        
        await db.commit()
        await db.refresh(api_key)
        
        logger.info(f"API Key regenerated: id={key_id}")
        
        response = ApiKeyCreateResponse.from_orm(api_key)
        response.api_secret = new_secret  # 明文返回（仅此一次）
        
        return response
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to regenerate API key: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api-keys/{key_id}", summary="删除密钥")
async def delete_api_key(
    key_id: int,
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """删除API密钥（软删除）"""
    query = select(ApiKey).where(
        ApiKey.id == key_id,
        ApiKey.account_id == current_account.id,
        ApiKey.is_deleted == False
    )
    result = await db.execute(query)
    api_key = result.scalar_one_or_none()
    
    if not api_key:
        raise HTTPException(status_code=404, detail="密钥不存在")
    
    try:
        api_key.is_deleted = True
        api_key.status = ApiKeyStatus.DISABLED
        await db.commit()
        
        logger.info(f"API Key deleted: id={key_id}")
        
        return {"success": True, "message": "删除成功"}
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to delete API key: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
