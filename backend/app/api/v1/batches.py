"""
批量发送 API
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import Optional
from datetime import datetime
import csv
import os
import io

from app.database import get_db
from app.modules.sms.sms_batch import SmsBatch, BatchStatus
from app.modules.sms.sms_template import SmsTemplate
from app.schemas.batch import (
    SmsBatchCreate, SmsBatchResponse, SmsBatchListResponse,
    SmsBatchStats, BatchUploadResponse
)
from app.core.auth import get_current_account
from app.modules.common.account import Account
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)

# 上传目录配置
UPLOAD_DIR = "/var/smsc/backend/uploads/batches"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/batches/upload", response_model=BatchUploadResponse, summary="上传CSV批量发送")
async def upload_batch_file(
    file: UploadFile = File(...),
    batch_name: str = Form(...),
    template_id: Optional[int] = Form(None),
    sender_id: Optional[str] = Form(None),
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """
    上传CSV文件进行批量发送
    
    CSV格式要求：
    - 第一列：手机号（必填）
    - 其他列：变量值（如果使用模板）
    
    示例：
    ```
    phone,name,code
    +8613800138000,张三,123456
    +8613800138001,李四,654321
    ```
    """
    try:
        # 验证文件类型
        import os as _os
        clean_name = _os.path.basename(file.filename or "upload.csv")
        if not clean_name.lower().endswith('.csv'):
            raise HTTPException(status_code=400, detail="仅支持CSV文件")
        
        # 读取文件内容
        content = await file.read()
        file_size = len(content)
        
        # 验证文件大小（限制10MB）
        if file_size > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="文件大小不能超过10MB")
        
        # 解析CSV
        csv_content = content.decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(csv_content))
        
        # 验证表头
        if 'phone' not in csv_reader.fieldnames:
            raise HTTPException(status_code=400, detail="CSV必须包含'phone'列")
        
        # 统计行数
        rows = list(csv_reader)
        total_count = len(rows)
        
        if total_count == 0:
            raise HTTPException(status_code=400, detail="CSV文件为空")
        
        if total_count > 10000:
            raise HTTPException(status_code=400, detail="单次批量最多支持10000条")
        
        # 如果使用模板，验证模板存在
        if template_id:
            template_query = select(SmsTemplate).where(
                SmsTemplate.id == template_id,
                SmsTemplate.account_id == current_account.id
            )
            template_result = await db.execute(template_query)
            template = template_result.scalar_one_or_none()
            if not template:
                raise HTTPException(status_code=404, detail="模板不存在")
        
        # 保存文件
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_filename = f"{current_account.id}_{timestamp}_{clean_name}"
        file_path = os.path.join(UPLOAD_DIR, safe_filename)
        
        with open(file_path, 'wb') as f:
            f.write(content)
        
        # 创建批次记录
        batch = SmsBatch(
            account_id=current_account.id,
            batch_name=batch_name,
            template_id=template_id,
            file_path=file_path,
            file_size=file_size,
            total_count=total_count,
            sender_id=sender_id,
            status=BatchStatus.PENDING
        )
        
        db.add(batch)
        await db.commit()
        await db.refresh(batch)
        
        logger.info(f"Batch uploaded: id={batch.id}, account={current_account.id}, count={total_count}")
        
        # TODO: 触发异步处理任务（Celery）
        # from app.workers.batch_worker import process_batch
        # process_batch.delay(batch.id)
        
        return BatchUploadResponse(
            batch_id=batch.id,
            file_name=file.filename,
            file_size=file_size,
            total_count=total_count,
            message="上传成功，正在处理中"
        )
        
    except Exception as e:
        logger.error(f"Failed to upload batch: {str(e)}")
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


@router.get("/batches", response_model=SmsBatchListResponse, summary="查询批次列表")
async def list_batches(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[BatchStatus] = Query(None),
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """查询批量发送任务列表"""
    try:
        conditions = [
            SmsBatch.account_id == current_account.id,
            SmsBatch.is_deleted == False
        ]
        
        if status:
            conditions.append(SmsBatch.status == status)
        
        # 总数
        count_query = select(func.count()).select_from(SmsBatch).where(and_(*conditions))
        total = (await db.execute(count_query)).scalar()
        
        # 数据
        offset = (page - 1) * page_size
        query = select(SmsBatch).where(and_(*conditions)).order_by(
            SmsBatch.created_at.desc()
        ).limit(page_size).offset(offset)
        
        result = await db.execute(query)
        batches = result.scalars().all()
        
        items = [SmsBatchResponse.model_validate(b, from_attributes=True) for b in batches]
        
        return SmsBatchListResponse(
            total=total,
            items=items,
            page=page,
            page_size=page_size
        )
        
    except Exception as e:
        logger.error(f"Failed to list batches: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/batches/stats", response_model=SmsBatchStats, summary="批次统计")
async def get_batch_stats(
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取批量发送统计"""
    try:
        # 总批次数
        total_query = select(func.count()).select_from(SmsBatch).where(
            SmsBatch.account_id == current_account.id,
            SmsBatch.is_deleted == False
        )
        total = (await db.execute(total_query)).scalar()
        
        # 按状态统计
        pending = (await db.execute(
            select(func.count()).select_from(SmsBatch).where(
                SmsBatch.account_id == current_account.id,
                SmsBatch.status == BatchStatus.PENDING,
                SmsBatch.is_deleted == False
            )
        )).scalar()
        
        processing = (await db.execute(
            select(func.count()).select_from(SmsBatch).where(
                SmsBatch.account_id == current_account.id,
                SmsBatch.status == BatchStatus.PROCESSING,
                SmsBatch.is_deleted == False
            )
        )).scalar()
        
        completed = (await db.execute(
            select(func.count()).select_from(SmsBatch).where(
                SmsBatch.account_id == current_account.id,
                SmsBatch.status == BatchStatus.COMPLETED,
                SmsBatch.is_deleted == False
            )
        )).scalar()
        
        failed = (await db.execute(
            select(func.count()).select_from(SmsBatch).where(
                SmsBatch.account_id == current_account.id,
                SmsBatch.status == BatchStatus.FAILED,
                SmsBatch.is_deleted == False
            )
        )).scalar()
        
        # 消息统计
        total_messages = (await db.execute(
            select(func.sum(SmsBatch.total_count)).where(
                SmsBatch.account_id == current_account.id,
                SmsBatch.is_deleted == False
            )
        )).scalar() or 0
        
        success_messages = (await db.execute(
            select(func.sum(SmsBatch.success_count)).where(
                SmsBatch.account_id == current_account.id,
                SmsBatch.is_deleted == False
            )
        )).scalar() or 0
        
        failed_messages = (await db.execute(
            select(func.sum(SmsBatch.failed_count)).where(
                SmsBatch.account_id == current_account.id,
                SmsBatch.is_deleted == False
            )
        )).scalar() or 0
        
        return SmsBatchStats(
            total_batches=total,
            pending_batches=pending,
            processing_batches=processing,
            completed_batches=completed,
            failed_batches=failed,
            total_messages=total_messages,
            success_messages=success_messages,
            failed_messages=failed_messages
        )
        
    except Exception as e:
        logger.error(f"Failed to get stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/batches/{batch_id}", response_model=SmsBatchResponse, summary="查询批次详情")
async def get_batch(
    batch_id: int,
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """查询批次详情"""
    query = select(SmsBatch).where(
        SmsBatch.id == batch_id,
        SmsBatch.account_id == current_account.id,
        SmsBatch.is_deleted == False
    )
    result = await db.execute(query)
    batch = result.scalar_one_or_none()
    
    if not batch:
        raise HTTPException(status_code=404, detail="批次不存在")

    try:
        return SmsBatchResponse.model_validate(batch, from_attributes=True)
    except Exception as e:
        logger.exception(f"批次详情序列化失败 batch_id={batch_id}: {e}")
        raise HTTPException(status_code=500, detail="批次数据格式异常，请联系管理员查看日志")


@router.delete("/batches/{batch_id}", summary="取消批次")
async def cancel_batch(
    batch_id: int,
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """取消批量发送任务"""
    query = select(SmsBatch).where(
        SmsBatch.id == batch_id,
        SmsBatch.account_id == current_account.id,
        SmsBatch.is_deleted == False
    )
    result = await db.execute(query)
    batch = result.scalar_one_or_none()
    
    if not batch:
        raise HTTPException(status_code=404, detail="批次不存在")
    
    if batch.status in [BatchStatus.COMPLETED, BatchStatus.FAILED]:
        raise HTTPException(status_code=400, detail="该批次已完成，无法取消")
    
    try:
        batch.status = BatchStatus.CANCELLED
        await db.commit()
        
        logger.info(f"Batch cancelled: id={batch_id}")
        
        return {"success": True, "message": "批次已取消"}
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to cancel batch: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
