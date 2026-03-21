"""
定时发送任务 API（P2-1）
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import Optional
from datetime import datetime

from app.database import get_db
from app.models.scheduled_task import ScheduledTask, TaskStatus, TaskFrequency
from app.schemas.scheduled_task import (
    ScheduledTaskCreate, ScheduledTaskUpdate, ScheduledTaskResponse,
    ScheduledTaskListResponse, ScheduledTaskStats
)
from app.core.auth import get_current_account
from app.modules.common.account import Account
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.post("/scheduled-tasks", response_model=ScheduledTaskResponse, summary="创建定时任务")
async def create_scheduled_task(
    data: ScheduledTaskCreate,
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """
    创建定时发送任务
    
    - **task_name**: 任务名称
    - **phone_numbers**: 手机号列表
    - **scheduled_time**: 计划执行时间
    - **frequency**: 执行频率（once/daily/weekly/monthly）
    """
    try:
        # 计算下次执行时间
        next_run_time = data.scheduled_time if data.frequency != TaskFrequency.ONCE else None
        
        task = ScheduledTask(
            account_id=current_account.id,
            task_name=data.task_name,
            template_id=data.template_id,
            phone_numbers=data.phone_numbers,
            content=data.content,
            sender_id=data.sender_id,
            frequency=data.frequency,
            scheduled_time=data.scheduled_time,
            next_run_time=next_run_time,
            repeat_config=data.repeat_config,
            status=TaskStatus.PENDING
        )
        
        db.add(task)
        await db.commit()
        await db.refresh(task)
        
        logger.info(f"Scheduled task created: id={task.id}, account={current_account.id}")
        
        return ScheduledTaskResponse.from_orm(task)
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to create scheduled task: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建失败: {str(e)}")


@router.get("/scheduled-tasks", response_model=ScheduledTaskListResponse, summary="查询任务列表")
async def list_scheduled_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[TaskStatus] = Query(None),
    frequency: Optional[TaskFrequency] = Query(None),
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """查询定时任务列表"""
    try:
        conditions = [
            ScheduledTask.account_id == current_account.id,
            ScheduledTask.is_deleted == False
        ]
        
        if status:
            conditions.append(ScheduledTask.status == status)
        if frequency:
            conditions.append(ScheduledTask.frequency == frequency)
        
        # 总数
        count_query = select(func.count()).select_from(ScheduledTask).where(and_(*conditions))
        total = (await db.execute(count_query)).scalar()
        
        # 数据
        offset = (page - 1) * page_size
        query = select(ScheduledTask).where(and_(*conditions)).order_by(
            ScheduledTask.scheduled_time.desc()
        ).limit(page_size).offset(offset)
        
        result = await db.execute(query)
        tasks = result.scalars().all()
        
        items = [ScheduledTaskResponse.from_orm(t) for t in tasks]
        
        return ScheduledTaskListResponse(
            total=total,
            items=items,
            page=page,
            page_size=page_size
        )
        
    except Exception as e:
        logger.error(f"Failed to list tasks: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scheduled-tasks/stats", response_model=ScheduledTaskStats, summary="任务统计")
async def get_task_stats(
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取任务统计信息"""
    try:
        base_condition = and_(
            ScheduledTask.account_id == current_account.id,
            ScheduledTask.is_deleted == False
        )
        
        total = (await db.execute(
            select(func.count()).select_from(ScheduledTask).where(base_condition)
        )).scalar()
        
        pending = (await db.execute(
            select(func.count()).select_from(ScheduledTask).where(
                base_condition, ScheduledTask.status == TaskStatus.PENDING
            )
        )).scalar()
        
        running = (await db.execute(
            select(func.count()).select_from(ScheduledTask).where(
                base_condition, ScheduledTask.status == TaskStatus.RUNNING
            )
        )).scalar()
        
        completed = (await db.execute(
            select(func.count()).select_from(ScheduledTask).where(
                base_condition, ScheduledTask.status == TaskStatus.COMPLETED
            )
        )).scalar()
        
        failed = (await db.execute(
            select(func.count()).select_from(ScheduledTask).where(
                base_condition, ScheduledTask.status == TaskStatus.FAILED
            )
        )).scalar()
        
        return ScheduledTaskStats(
            total_tasks=total,
            pending_tasks=pending,
            running_tasks=running,
            completed_tasks=completed,
            failed_tasks=failed
        )
        
    except Exception as e:
        logger.error(f"Failed to get stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scheduled-tasks/{task_id}", response_model=ScheduledTaskResponse, summary="查询任务详情")
async def get_scheduled_task(
    task_id: int,
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """查询任务详情"""
    query = select(ScheduledTask).where(
        ScheduledTask.id == task_id,
        ScheduledTask.account_id == current_account.id,
        ScheduledTask.is_deleted == False
    )
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return ScheduledTaskResponse.from_orm(task)


@router.put("/scheduled-tasks/{task_id}", response_model=ScheduledTaskResponse, summary="更新任务")
async def update_scheduled_task(
    task_id: int,
    data: ScheduledTaskUpdate,
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """更新定时任务"""
    query = select(ScheduledTask).where(
        ScheduledTask.id == task_id,
        ScheduledTask.account_id == current_account.id,
        ScheduledTask.is_deleted == False
    )
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    if task.status == TaskStatus.RUNNING:
        raise HTTPException(status_code=400, detail="任务运行中，无法修改")
    
    try:
        if data.task_name is not None:
            task.task_name = data.task_name
        if data.scheduled_time is not None:
            task.scheduled_time = data.scheduled_time
            task.next_run_time = data.scheduled_time
        if data.frequency is not None:
            task.frequency = data.frequency
        if data.status is not None:
            task.status = data.status
        if data.repeat_config is not None:
            task.repeat_config = data.repeat_config
        
        await db.commit()
        await db.refresh(task)
        
        return ScheduledTaskResponse.from_orm(task)
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to update task: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/scheduled-tasks/{task_id}", summary="删除任务")
async def delete_scheduled_task(
    task_id: int,
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """删除定时任务"""
    query = select(ScheduledTask).where(
        ScheduledTask.id == task_id,
        ScheduledTask.account_id == current_account.id,
        ScheduledTask.is_deleted == False
    )
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    if task.status == TaskStatus.RUNNING:
        raise HTTPException(status_code=400, detail="任务运行中，无法删除")
    
    try:
        task.is_deleted = True
        task.status = TaskStatus.CANCELLED
        await db.commit()
        
        logger.info(f"Task deleted: id={task_id}")
        
        return {"success": True, "message": "删除成功"}
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to delete task: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scheduled-tasks/{task_id}/execute", summary="立即执行任务")
async def execute_scheduled_task(
    task_id: int,
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """立即执行定时任务"""
    query = select(ScheduledTask).where(
        ScheduledTask.id == task_id,
        ScheduledTask.account_id == current_account.id,
        ScheduledTask.is_deleted == False
    )
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    if task.status == TaskStatus.RUNNING:
        raise HTTPException(status_code=400, detail="任务已在运行中")
    
    try:
        # TODO: 触发实际的短信发送逻辑
        # from app.workers.scheduled_worker import execute_scheduled_task
        # execute_scheduled_task.delay(task_id)
        
        task.status = TaskStatus.RUNNING
        task.last_run_time = datetime.now()
        await db.commit()
        
        logger.info(f"Task execution triggered: id={task_id}")
        
        return {"success": True, "message": "任务已开始执行"}
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to execute task: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
