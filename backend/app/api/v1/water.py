"""
注水管理 API：代理管理、注水任务、注水记录、注册脚本
"""
import json
import os
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func, delete as sa_delete, and_, case, or_, and_, case, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.admin import get_current_admin as get_current_admin_user
from app.database import get_db
from app.modules.common.admin_user import AdminUser
from app.modules.sms.channel import Channel
from app.modules.sms.sms_batch import SmsBatch
from app.modules.sms.sms_batch import SmsBatch
from app.modules.water.models import (
    WaterInjectionLog,
    WaterProxy,
    WaterRegisterScript,
    WaterTaskConfig,
)
from app.utils.logger import get_logger
from app.utils.proxy_manager import test_proxy_connectivity

logger = get_logger(__name__)

router = APIRouter(tags=["注水管理"])


# ========== Pydantic 模型 ==========


class ProxyCreate(BaseModel):
    name: str = Field(..., max_length=100)
    proxy_type: str = Field(default="http")
    endpoint: str = Field(..., max_length=500)
    country_code: str = Field(default="*", max_length=5)
    country_auto: bool = False
    max_concurrency: int = Field(default=10, ge=1, le=100)
    remark: Optional[str] = None


class ProxyUpdate(BaseModel):
    name: Optional[str] = None
    proxy_type: Optional[str] = None
    endpoint: Optional[str] = None
    country_code: Optional[str] = None
    country_auto: Optional[bool] = None
    max_concurrency: Optional[int] = None
    status: Optional[str] = None
    remark: Optional[str] = None


class TaskConfigCreate(BaseModel):
    account_id: int
    enabled: bool = False
    click_rate_min: float = Field(default=3.0, ge=0, le=100)
    click_rate_max: float = Field(default=8.0, ge=0, le=100)
    click_delay_min: int = Field(default=60, ge=1)
    click_delay_max: int = Field(default=14400, ge=1)
    click_delay_curve: float = Field(default=4.0, ge=1.0, le=10.0)
    register_enabled: bool = False
    register_rate_min: float = Field(default=1.0, ge=0, le=100)
    register_rate_max: float = Field(default=3.0, ge=0, le=100)
    proxy_id: Optional[int] = None
    user_agent_type: str = Field(default="mobile")


class TaskConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    click_rate_min: Optional[float] = None
    click_rate_max: Optional[float] = None
    click_delay_min: Optional[int] = None
    click_delay_max: Optional[int] = None
    click_delay_curve: Optional[float] = None
    register_enabled: Optional[bool] = None
    register_rate_min: Optional[float] = None
    register_rate_max: Optional[float] = None
    proxy_id: Optional[int] = None
    user_agent_type: Optional[str] = None


# 清空注水队列时须输入的确认口令（与前端一致）
WATER_QUEUE_PURGE_CONFIRM_PHRASE = "清空注水队列"


class PurgeWaterQueueRequest(BaseModel):
    """清空 web_automation 队列请求体"""

    confirm_phrase: str = Field(..., min_length=1, max_length=64, description="须与系统口令完全一致")


class RevokeAccountWaterPendingRequest(BaseModel):
    """按账户撤销已追踪的排队注水任务"""

    confirm_phrase: str = Field(..., min_length=1, max_length=80)


def _water_account_revoke_confirm_phrase(account_id: int) -> str:
    return f"确认取消账户{account_id}"


class ScriptCreate(BaseModel):
    name: str = Field(..., max_length=100)
    domain: str = Field(..., max_length=255)
    steps: dict
    enabled: bool = True
    remark: Optional[str] = None


class ScriptUpdate(BaseModel):
    name: Optional[str] = None
    domain: Optional[str] = None
    steps: Optional[dict] = None
    enabled: Optional[bool] = None
    remark: Optional[str] = None


# ========== 代理管理 ==========


def _mask_endpoint(ep: str) -> str:
    """脱敏代理地址"""
    try:
        p = urlparse(ep)
        if p.username:
            return f"{p.scheme}://***@{p.hostname}:{p.port}"
        return ep
    except Exception:
        return "***"


@router.get("/proxies")
async def list_proxies(
    country_code: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin_user),
):
    """代理列表"""
    query = select(WaterProxy)
    count_query = select(func.count()).select_from(WaterProxy)

    if country_code:
        query = query.where(WaterProxy.country_code == country_code)
        count_query = count_query.where(WaterProxy.country_code == country_code)
    if status:
        query = query.where(WaterProxy.status == status)
        count_query = count_query.where(WaterProxy.status == status)

    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(WaterProxy.id.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    proxies = result.scalars().all()

    return {
        "total": total,
        "items": [
            {
                "id": p.id,
                "name": p.name,
                "proxy_type": p.proxy_type,
                "endpoint_masked": _mask_endpoint(p.endpoint),
                "endpoint": p.endpoint,
                "country_code": p.country_code,
                "country_auto": p.country_auto,
                "max_concurrency": p.max_concurrency,
                "status": p.status,
                "last_test_at": p.last_test_at.isoformat() if p.last_test_at else None,
                "last_test_result": p.last_test_result,
                "remark": p.remark,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in proxies
        ],
    }


@router.post("/proxies")
async def create_proxy(
    req: ProxyCreate,
    db: AsyncSession = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin_user),
):
    """创建代理"""
    proxy = WaterProxy(
        name=req.name,
        proxy_type=req.proxy_type,
        endpoint=req.endpoint,
        country_code=req.country_code,
        country_auto=req.country_auto,
        max_concurrency=req.max_concurrency,
        remark=req.remark,
    )
    db.add(proxy)
    await db.flush()
    return {"id": proxy.id, "message": "创建成功"}


@router.put("/proxies/{proxy_id}")
async def update_proxy(
    proxy_id: int,
    req: ProxyUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin_user),
):
    """更新代理"""
    result = await db.execute(select(WaterProxy).where(WaterProxy.id == proxy_id))
    proxy = result.scalar_one_or_none()
    if not proxy:
        raise HTTPException(status_code=404, detail="代理不存在")

    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(proxy, field, value)

    return {"message": "更新成功"}


@router.delete("/proxies/{proxy_id}")
async def delete_proxy(
    proxy_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin_user),
):
    """删除代理"""
    await db.execute(sa_delete(WaterProxy).where(WaterProxy.id == proxy_id))
    return {"message": "删除成功"}


@router.post("/proxies/{proxy_id}/test")
async def test_proxy(
    proxy_id: int,
    test_country: Optional[str] = Query(default=None, description="测试用国家代码，如 th、br"),
    db: AsyncSession = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin_user),
):
    """测试代理连通性，支持指定测试国家（验证国家路由功能）"""
    result = await db.execute(select(WaterProxy).where(WaterProxy.id == proxy_id))
    proxy = result.scalar_one_or_none()
    if not proxy:
        raise HTTPException(status_code=404, detail="代理不存在")

    country = test_country or proxy.country_code
    test_result = await test_proxy_connectivity(proxy.endpoint, country, proxy.country_auto)

    proxy.last_test_at = datetime.now()
    tc = test_result.get('test_country', '')
    proxy.last_test_result = (
        f"{'成功' if test_result['success'] else '失败'} | "
        f"IP: {test_result.get('ip', 'N/A')} | "
        f"{test_result.get('latency_ms', 0)}ms"
        f"{f' | 国家: {tc.upper()}' if tc else ''}"
    )
    if not test_result["success"]:
        proxy.last_test_result += f" | {test_result.get('error', '')[:100]}"

    return test_result


# ========== 注水任务 ==========


@router.get("/accounts")
async def list_accounts_for_water(
    db: AsyncSession = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin_user),
):
    """获取所有客户账户（供注水任务选择）"""
    from app.modules.common.account import Account
    result = await db.execute(
        select(Account.id, Account.account_name, Account.status)
        .where(Account.status == "active")
        .order_by(Account.id.desc())
    )
    accounts = result.all()
    return [{"id": a.id, "account_name": a.account_name} for a in accounts]


@router.get("/tasks")
async def list_tasks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin_user),
):
    """注水任务列表"""
    total = (await db.execute(select(func.count()).select_from(WaterTaskConfig))).scalar() or 0

    query = (
        select(WaterTaskConfig)
        .order_by(WaterTaskConfig.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    tasks = result.scalars().all()

    from app.modules.common.account import Account

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    items = []
    for t in tasks:
        # 客户账户 + 归属员工（admin_users，Account.sales_id）
        acct = (
            await db.execute(
                select(
                    Account.account_name,
                    Account.country_code,
                    AdminUser.real_name,
                    AdminUser.username,
                )
                .outerjoin(AdminUser, Account.sales_id == AdminUser.id)
                .where(Account.id == t.account_id)
            )
        ).first()
        # 已有注水记录的去重发送批次数（batch_id 非空）
        water_batch_distinct = (
            await db.execute(
                select(func.count(func.distinct(WaterInjectionLog.batch_id))).where(
                    WaterInjectionLog.task_config_id == t.id,
                    WaterInjectionLog.batch_id.isnot(None),
                )
            )
        ).scalar() or 0
        # 今日统计
        click_cnt = (
            await db.execute(
                select(func.count()).select_from(WaterInjectionLog).where(
                    WaterInjectionLog.task_config_id == t.id,
                    WaterInjectionLog.action == "click",
                    WaterInjectionLog.created_at >= today,
                )
            )
        ).scalar() or 0
        reg_cnt = (
            await db.execute(
                select(func.count()).select_from(WaterInjectionLog).where(
                    WaterInjectionLog.task_config_id == t.id,
                    WaterInjectionLog.action == "register",
                    WaterInjectionLog.created_at >= today,
                )
            )
        ).scalar() or 0
        # 代理名
        proxy_name = None
        if t.proxy_id:
            pr = (await db.execute(select(WaterProxy.name).where(WaterProxy.id == t.proxy_id))).scalar()
            proxy_name = pr

        # 员工展示名：优先真实姓名，否则登录名
        account_staff_name = ""
        if acct:
            rn = (acct.real_name or "").strip()
            un = (acct.username or "").strip()
            account_staff_name = rn or un

        items.append(
            {
                "id": t.id,
                "account_id": t.account_id,
                "account_name": acct.account_name if acct else "未知",
                "account_country_code": (acct.country_code or "").strip().upper() if acct else "",
                "account_staff_name": account_staff_name,
                "water_distinct_batches": int(water_batch_distinct),
                "enabled": t.enabled,
                "click_rate_min": float(t.click_rate_min),
                "click_rate_max": float(t.click_rate_max),
                "click_delay_min": t.click_delay_min,
                "click_delay_max": t.click_delay_max,
                "click_delay_curve": float(t.click_delay_curve) if t.click_delay_curve else 4.0,
                "register_enabled": t.register_enabled,
                "register_rate_min": float(t.register_rate_min),
                "register_rate_max": float(t.register_rate_max),
                "proxy_id": t.proxy_id,
                "proxy_name": proxy_name,
                "user_agent_type": t.user_agent_type,
                "today_clicks": click_cnt,
                "today_registers": reg_cnt,
            }
        )

    return {"total": total, "items": items}


@router.get("/tasks/{task_config_id}/batch-progress")
async def water_task_batch_progress(
    task_config_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin_user),
):
    """
    按发送批次（sms_batches）展示该注水配置对应客户账户的注水执行进度。
    统计来自 water_injection_logs（按 batch_id + account_id，与 task_config 所属账户一致）。
    """
    cfg = (
        await db.execute(select(WaterTaskConfig).where(WaterTaskConfig.id == task_config_id))
    ).scalar_one_or_none()
    if not cfg:
        raise HTTPException(status_code=404, detail="注水任务配置不存在")

    account_id = cfg.account_id
    base = select(func.count()).select_from(SmsBatch).where(
        SmsBatch.account_id == account_id,
        SmsBatch.is_deleted == False,
    )
    total_batches = (await db.execute(base)).scalar() or 0

    off = (page - 1) * page_size
    batch_rows = (
        await db.execute(
            select(SmsBatch)
            .where(SmsBatch.account_id == account_id, SmsBatch.is_deleted == False)
            .order_by(SmsBatch.id.desc())
            .offset(off)
            .limit(page_size)
        )
    ).scalars().all()

    if not batch_rows:
        return {
            "task_config_id": task_config_id,
            "account_id": account_id,
            "total": total_batches,
            "page": page,
            "page_size": page_size,
            "items": [],
        }

    batch_ids = [b.id for b in batch_rows]
    # 仅统计属于该注水配置或历史未写 task_config_id 的同账户记录
    log_filter = and_(
        WaterInjectionLog.account_id == account_id,
        WaterInjectionLog.batch_id.in_(batch_ids),
        or_(
            WaterInjectionLog.task_config_id == task_config_id,
            WaterInjectionLog.task_config_id.is_(None),
        ),
    )

    agg_stmt = (
        select(
            WaterInjectionLog.batch_id,
            func.sum(case((WaterInjectionLog.action == "click", 1), else_=0)).label("click_total"),
            func.sum(
                case(
                    (
                        and_(WaterInjectionLog.action == "click", WaterInjectionLog.status == "success"),
                        1,
                    ),
                    else_=0,
                )
            ).label("click_success"),
            func.sum(
                case(
                    (
                        and_(WaterInjectionLog.action == "click", WaterInjectionLog.status == "failed"),
                        1,
                    ),
                    else_=0,
                )
            ).label("click_failed"),
            func.sum(
                case(
                    (
                        and_(
                            WaterInjectionLog.action == "click",
                            WaterInjectionLog.status.in_(("processing", "pending")),
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("click_in_progress"),
            func.sum(case((WaterInjectionLog.action == "register", 1), else_=0)).label("register_total"),
            func.sum(
                case(
                    (
                        and_(WaterInjectionLog.action == "register", WaterInjectionLog.status == "success"),
                        1,
                    ),
                    else_=0,
                )
            ).label("register_success"),
            func.sum(
                case(
                    (
                        and_(WaterInjectionLog.action == "register", WaterInjectionLog.status == "failed"),
                        1,
                    ),
                    else_=0,
                )
            ).label("register_failed"),
            func.sum(
                case(
                    (
                        and_(
                            WaterInjectionLog.action == "register",
                            WaterInjectionLog.status.in_(("processing", "pending")),
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("register_in_progress"),
        )
        .where(log_filter)
        .group_by(WaterInjectionLog.batch_id)
    )
    agg_result = await db.execute(agg_stmt)
    agg_map = {row.batch_id: row for row in agg_result.all()}

    items = []
    for b in batch_rows:
        row = agg_map.get(b.id)
        ct = int(row.click_total or 0) if row else 0
        cs = int(row.click_success or 0) if row else 0
        cf = int(row.click_failed or 0) if row else 0
        cp = int(row.click_in_progress or 0) if row else 0
        rt = int(row.register_total or 0) if row else 0
        rs = int(row.register_success or 0) if row else 0
        rf = int(row.register_failed or 0) if row else 0
        rp = int(row.register_in_progress or 0) if row else 0
        finished = cs + cf
        click_done_rate = round(finished / ct * 100, 1) if ct > 0 else None
        ref_success = b.success_count or 0
        # 相对发送成功条数的点击覆盖（仅作参考：实际触发受点击率随机影响）
        cover_rate = round(ct / ref_success * 100, 1) if ref_success > 0 and ct > 0 else None

        items.append(
            {
                "batch_id": b.id,
                "batch_name": b.batch_name,
                "batch_status": b.status.value if hasattr(b.status, "value") else str(b.status),
                "send_total": b.total_count or 0,
                "send_success": ref_success,
                "water_click_total": ct,
                "water_click_success": cs,
                "water_click_failed": cf,
                "water_click_in_progress": cp,
                "water_click_finished_rate": click_done_rate,
                "water_vs_send_success_rate": cover_rate,
                "water_register_total": rt,
                "water_register_success": rs,
                "water_register_failed": rf,
                "water_register_in_progress": rp,
                "batch_created_at": b.created_at.isoformat() if b.created_at else None,
                "batch_completed_at": b.completed_at.isoformat() if b.completed_at else None,
            }
        )

    return {
        "task_config_id": task_config_id,
        "account_id": account_id,
        "total": total_batches,
        "page": page,
        "page_size": page_size,
        "items": items,
    }


@router.get("/tasks/stats")
async def task_stats(
    db: AsyncSession = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin_user),
):
    """今日注水全局统计"""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    click_total = (
        await db.execute(
            select(func.count()).select_from(WaterInjectionLog).where(
                WaterInjectionLog.action == "click",
                WaterInjectionLog.created_at >= today,
            )
        )
    ).scalar() or 0
    click_success = (
        await db.execute(
            select(func.count()).select_from(WaterInjectionLog).where(
                WaterInjectionLog.action == "click",
                WaterInjectionLog.status == "success",
                WaterInjectionLog.created_at >= today,
            )
        )
    ).scalar() or 0
    reg_total = (
        await db.execute(
            select(func.count()).select_from(WaterInjectionLog).where(
                WaterInjectionLog.action == "register",
                WaterInjectionLog.created_at >= today,
            )
        )
    ).scalar() or 0
    reg_success = (
        await db.execute(
            select(func.count()).select_from(WaterInjectionLog).where(
                WaterInjectionLog.action == "register",
                WaterInjectionLog.status == "success",
                WaterInjectionLog.created_at >= today,
            )
        )
    ).scalar() or 0

    return {
        "today_clicks": click_total,
        "today_clicks_success": click_success,
        "click_success_rate": round(click_success / click_total * 100, 1) if click_total else 0,
        "today_registers": reg_total,
        "today_registers_success": reg_success,
        "register_success_rate": round(reg_success / reg_total * 100, 1) if reg_total else 0,
    }


@router.get("/queue/web-automation")
async def water_queue_stats(
    _admin: AdminUser = Depends(get_current_admin_user),
):
    """查询注水专用队列 web_automation 中待执行任务数量（未投递给 worker 的消息）"""
    from app.utils.water_queue import get_web_automation_queue_stats

    messages, consumers, exists = get_web_automation_queue_stats()
    return {
        "queue": "web_automation",
        "pending_messages": messages,
        "consumers": consumers,
        "queue_exists": exists,
    }


@router.post("/queue/web-automation/purge")
async def water_queue_purge(
    req: PurgeWaterQueueRequest,
    _admin: AdminUser = Depends(get_current_admin_user),
):
    """
    丢弃 web_automation 队列中尚未被 worker 取走的消息（如大量积压的点击任务）。
    已在 worker 内执行的任务无法取消；数据库中「处理中」的注水记录不会自动变更。
    """
    if req.confirm_phrase.strip() != WATER_QUEUE_PURGE_CONFIRM_PHRASE:
        raise HTTPException(
            status_code=400,
            detail=f"确认口令不正确，请在请求体中输入：{WATER_QUEUE_PURGE_CONFIRM_PHRASE}",
        )
    from app.utils.water_queue import purge_web_automation_queue

    purged = purge_web_automation_queue()
    logger.warning(f"管理员清空注水队列 web_automation，丢弃消息数={purged}")
    return {"purged": purged, "message": f"已丢弃队列中 {purged} 条待执行任务"}


@router.get("/tasks/account/{account_id}/pending-tracked")
async def water_account_pending_tracked(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin_user),
):
    """
    该账户在 Redis 中记录的待撤销注水任务数（派发后尚未被 worker 开始执行）。
    仅统计本功能上线后新派发的任务；无法区分共享队列中其他账户的消息。
    """
    row = (
        await db.execute(select(WaterTaskConfig.id).where(WaterTaskConfig.account_id == account_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="该账户无注水任务配置")
    from app.utils.water_task_tracking import count_tracked_pending

    return {
        "account_id": account_id,
        "tracked_pending": count_tracked_pending(account_id),
    }


@router.post("/tasks/account/{account_id}/revoke-pending")
async def water_account_revoke_pending(
    account_id: int,
    req: RevokeAccountWaterPendingRequest,
    db: AsyncSession = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin_user),
):
    """
    对已追踪的 task_id 批量 Celery revoke，仅影响该账户、且尚未开始执行的任务。
    不会清空整个 web_automation 队列，其他客户账户的任务保留。
    """
    expected = _water_account_revoke_confirm_phrase(account_id)
    if req.confirm_phrase.strip() != expected:
        raise HTTPException(
            status_code=400,
            detail=f"确认口令不正确，请输入：{expected}",
        )
    row = (
        await db.execute(select(WaterTaskConfig.id).where(WaterTaskConfig.account_id == account_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="该账户无注水任务配置")
    from app.utils.water_task_tracking import revoke_tracked_tasks_for_account

    n = revoke_tracked_tasks_for_account(account_id)
    logger.warning(f"管理员按账户撤销注水排队: account_id={account_id}, revoked={n}")
    return {
        "revoked": n,
        "message": f"已撤销该账户 {n} 个待执行注水任务（未开始执行且已追踪的部分）",
    }


@router.post("/tasks")
async def create_task(
    req: TaskConfigCreate,
    db: AsyncSession = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin_user),
):
    """创建注水任务配置（绑定客户账户）"""
    existing = (
        await db.execute(select(WaterTaskConfig).where(WaterTaskConfig.account_id == req.account_id))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="该账户已有注水配置，请编辑而非新建")

    task = WaterTaskConfig(**req.model_dump())
    db.add(task)
    await db.flush()
    return {"id": task.id, "message": "创建成功"}


@router.put("/tasks/{task_id}")
async def update_task(
    task_id: int,
    req: TaskConfigUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin_user),
):
    """更新注水任务配置"""
    result = await db.execute(select(WaterTaskConfig).where(WaterTaskConfig.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务配置不存在")

    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(task, field, value)

    return {"message": "更新成功"}


@router.put("/tasks/{task_id}/toggle")
async def toggle_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin_user),
):
    """切换启用/停用"""
    result = await db.execute(select(WaterTaskConfig).where(WaterTaskConfig.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务配置不存在")

    task.enabled = not task.enabled
    return {"enabled": task.enabled, "message": f"已{'启用' if task.enabled else '停用'}"}


@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin_user),
):
    """删除注水任务配置"""
    await db.execute(sa_delete(WaterTaskConfig).where(WaterTaskConfig.id == task_id))
    return {"message": "删除成功"}


# ========== 注水记录 ==========


@router.get("/logs")
async def list_logs(
    action: Optional[str] = None,
    status: Optional[str] = None,
    account_id: Optional[int] = None,
    channel_id: Optional[int] = None,
    batch_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin_user),
):
    """注水记录列表"""
    query = select(WaterInjectionLog)
    count_query = select(func.count()).select_from(WaterInjectionLog)

    if action:
        query = query.where(WaterInjectionLog.action == action)
        count_query = count_query.where(WaterInjectionLog.action == action)
    if status:
        query = query.where(WaterInjectionLog.status == status)
        count_query = count_query.where(WaterInjectionLog.status == status)
    if account_id:
        query = query.where(WaterInjectionLog.account_id == account_id)
        count_query = count_query.where(WaterInjectionLog.account_id == account_id)
    if channel_id:
        query = query.where(WaterInjectionLog.channel_id == channel_id)
        count_query = count_query.where(WaterInjectionLog.channel_id == channel_id)
    if batch_id:
        query = query.where(WaterInjectionLog.batch_id == batch_id)
        count_query = count_query.where(WaterInjectionLog.batch_id == batch_id)
    if start_date:
        query = query.where(WaterInjectionLog.created_at >= start_date)
        count_query = count_query.where(WaterInjectionLog.created_at >= start_date)
    if end_date:
        query = query.where(WaterInjectionLog.created_at <= end_date + " 23:59:59")
        count_query = count_query.where(WaterInjectionLog.created_at <= end_date + " 23:59:59")

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(WaterInjectionLog.id.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    logs = result.scalars().all()

    return {
        "total": total,
        "items": [
            {
                "id": l.id,
                "sms_log_id": l.sms_log_id,
                "account_id": l.account_id,
                "batch_id": l.batch_id,
                "channel_id": l.channel_id,
                "task_config_id": l.task_config_id,
                "url": l.url,
                "action": l.action,
                "status": l.status,
                "proxy_id": l.proxy_id,
                "proxy_ip": l.proxy_ip,
                "proxy_country": l.proxy_country,
                "duration_ms": l.duration_ms,
                "error_message": l.error_message,
                "has_screenshot": bool(l.screenshot_path),
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in logs
        ],
    }


@router.get("/logs/{log_id}/screenshot")
async def get_screenshot(
    log_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin_user),
):
    """获取截图"""
    result = await db.execute(select(WaterInjectionLog).where(WaterInjectionLog.id == log_id))
    log = result.scalar_one_or_none()
    if not log or not log.screenshot_path:
        raise HTTPException(status_code=404, detail="截图不存在")
    if not os.path.exists(log.screenshot_path):
        raise HTTPException(status_code=404, detail="截图文件已删除")

    return FileResponse(log.screenshot_path, media_type="image/png")


# ========== 注册脚本 ==========


@router.get("/scripts")
async def list_scripts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin_user),
):
    """注册脚本列表"""
    total = (await db.execute(select(func.count()).select_from(WaterRegisterScript))).scalar() or 0
    query = (
        select(WaterRegisterScript)
        .order_by(WaterRegisterScript.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    scripts = result.scalars().all()

    return {
        "total": total,
        "items": [
            {
                "id": s.id,
                "name": s.name,
                "domain": s.domain,
                "steps": json.loads(s.steps) if isinstance(s.steps, str) else s.steps,
                "enabled": s.enabled,
                "success_count": s.success_count,
                "fail_count": s.fail_count,
                "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
                "remark": s.remark,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in scripts
        ],
    }


@router.post("/scripts")
async def create_script(
    req: ScriptCreate,
    db: AsyncSession = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin_user),
):
    """创建注册脚本"""
    existing = (
        await db.execute(select(WaterRegisterScript).where(WaterRegisterScript.domain == req.domain))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail=f"域名 {req.domain} 已有脚本配置")

    script = WaterRegisterScript(
        name=req.name,
        domain=req.domain,
        steps=json.dumps(req.steps, ensure_ascii=False),
        enabled=req.enabled,
        remark=req.remark,
    )
    db.add(script)
    await db.flush()
    return {"id": script.id, "message": "创建成功"}


@router.put("/scripts/{script_id}")
async def update_script(
    script_id: int,
    req: ScriptUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin_user),
):
    """更新注册脚本"""
    result = await db.execute(select(WaterRegisterScript).where(WaterRegisterScript.id == script_id))
    script = result.scalar_one_or_none()
    if not script:
        raise HTTPException(status_code=404, detail="脚本不存在")

    data = req.model_dump(exclude_unset=True)
    if "steps" in data and isinstance(data["steps"], dict):
        data["steps"] = json.dumps(data["steps"], ensure_ascii=False)
    for field, value in data.items():
        setattr(script, field, value)

    return {"message": "更新成功"}


@router.delete("/scripts/{script_id}")
async def delete_script(
    script_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin_user),
):
    """删除注册脚本"""
    await db.execute(sa_delete(WaterRegisterScript).where(WaterRegisterScript.id == script_id))
    return {"message": "删除成功"}


@router.post("/scripts/{script_id}/test")
async def test_script(
    script_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin_user),
):
    """测试运行注册脚本"""
    result = await db.execute(select(WaterRegisterScript).where(WaterRegisterScript.id == script_id))
    script = result.scalar_one_or_none()
    if not script:
        raise HTTPException(status_code=404, detail="脚本不存在")

    # 使用 Celery 异步执行测试
    from app.workers.celery_app import celery_app

    task = celery_app.send_task(
        "web_register_task",
        args=[0, f"https://{script.domain}", 0],
        kwargs={"task_config_id": 0, "ua_type": "mobile"},
        queue="web_automation",
    )

    return {"task_id": task.id, "message": f"测试任务已提交，脚本: {script.name}"}
