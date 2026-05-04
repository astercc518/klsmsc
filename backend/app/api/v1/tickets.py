"""工单系统API"""
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, update, delete
from sqlalchemy.orm import selectinload
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

from app.database import get_db
from app.modules.common.ticket import Ticket, TicketReply, TicketTemplate
from app.modules.common.account import Account
from app.modules.common.admin_user import AdminUser
from app.modules.common.telegram_binding import TelegramBinding
from app.services.notification_service import notification_service
from app.api.v1.admin import get_current_admin
from app.api.v1.account import get_current_account
from app.core.audit_dep import audited

router = APIRouter(tags=["工单系统"])

# 工单附件存储目录（项目根目录 data/tickets，可通过 TICKET_UPLOAD_DIR 覆盖）
_BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
TICKET_DIR = Path(os.environ.get("TICKET_UPLOAD_DIR", str(_BASE_DIR.parent / "data" / "tickets")))
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


def _ensure_ticket_dir(ticket_id: int) -> Path:
    """确保工单附件目录存在"""
    d = TICKET_DIR / str(ticket_id)
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"无法创建附件目录: {str(e)}")
    return d


# ============ Pydantic 模型 ============

class TicketCreate(BaseModel):
    ticket_type: str = Field(default="other", description="工单类型")
    priority: str = Field(default="normal", description="优先级")
    category: Optional[str] = None
    title: str = Field(..., max_length=200, description="工单标题")
    description: Optional[str] = None
    attachments: Optional[List[str]] = None
    extra_data: Optional[dict] = None


class TicketUpdate(BaseModel):
    priority: Optional[str] = None
    category: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class TicketReplyCreate(BaseModel):
    content: str = Field(..., description="回复内容")
    attachments: Optional[List[str]] = None
    is_internal: bool = Field(default=False, description="是否内部备注")


class TicketAssign(BaseModel):
    admin_id: int = Field(..., description="分配给的管理员ID")


class TicketResolve(BaseModel):
    resolution: str = Field(..., description="解决方案")


def generate_ticket_no() -> str:
    """生成工单号"""
    now = datetime.now()
    return f"TK{now.strftime('%Y%m%d%H%M%S')}{str(uuid.uuid4().hex)[:6].upper()}"


# ============ 客户端工单接口 ============

customer_router = APIRouter(prefix="/tickets", tags=["客户工单"])


@customer_router.get("")
async def get_my_tickets(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    ticket_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account)
):
    """获取我的工单列表"""
    query = select(Ticket).where(Ticket.account_id == account.id)
    
    if status:
        query = query.where(Ticket.status == status)
    if ticket_type:
        query = query.where(Ticket.ticket_type == ticket_type)
    
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)
    
    query = query.order_by(Ticket.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    tickets = result.scalars().all()
    
    return {
        "success": True,
        "total": total,
        "page": page,
        "page_size": page_size,
        "tickets": [
            {
                "id": t.id,
                "ticket_no": t.ticket_no,
                "ticket_type": t.ticket_type,
                "priority": t.priority,
                "title": t.title,
                "status": t.status,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
                "resolved_at": t.resolved_at.isoformat() if t.resolved_at else None
            }
            for t in tickets
        ]
    }


@customer_router.post("")
async def create_ticket(
    data: TicketCreate,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account)
):
    """创建工单"""
    ticket = Ticket(
        ticket_no=generate_ticket_no(),
        account_id=account.id,
        ticket_type=data.ticket_type,
        priority=data.priority,
        category=data.category,
        title=data.title,
        description=data.description,
        attachments=data.attachments,
        extra_data=data.extra_data,
        status='open',
        created_by_type='account',
        created_by_id=account.id
    )
    
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)
    
    # 发送通知给管理员
    message = (
        f"🆕 *新工单通知*\n\n"
        f"工单号: `{ticket.ticket_no}`\n"
        f"账户: {account.account_name} ({account.email})\n"
        f"标题: {ticket.title}\n"
        f"类型: {ticket.ticket_type}\n"
        f"描述: {ticket.description[:100] + '...' if len(ticket.description or '') > 100 else ticket.description}"
    )
    await notification_service.notify_admin_group(message)
    
    return {
        "success": True,
        "message": "工单创建成功",
        "ticket_id": ticket.id,
        "ticket_no": ticket.ticket_no
    }


@customer_router.get("/{ticket_id}")
async def get_ticket_detail(
    ticket_id: int,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account)
):
    """获取工单详情"""
    result = await db.execute(
        select(Ticket)
        .options(selectinload(Ticket.replies))
        .where(Ticket.id == ticket_id, Ticket.account_id == account.id)
    )
    ticket = result.scalar_one_or_none()
    
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")
    
    # 过滤内部备注
    replies = [r for r in ticket.replies if not r.is_internal]
    
    return {
        "success": True,
        "ticket": {
            "id": ticket.id,
            "ticket_no": ticket.ticket_no,
            "ticket_type": ticket.ticket_type,
            "priority": ticket.priority,
            "category": ticket.category,
            "title": ticket.title,
            "description": ticket.description,
            "attachments": ticket.attachments,
            "status": ticket.status,
            "resolution": ticket.resolution,
            "satisfaction_rating": ticket.satisfaction_rating,
            "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
            "updated_at": ticket.updated_at.isoformat() if ticket.updated_at else None,
            "resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else None,
            "replies": [
                {
                    "id": r.id,
                    "reply_by_type": r.reply_by_type,
                    "reply_by_name": r.reply_by_name or ("客服" if r.reply_by_type == 'admin' else "我"),
                    "content": r.content,
                    "attachments": r.attachments,
                    "is_solution": r.is_solution,
                    "created_at": r.created_at.isoformat() if r.created_at else None
                }
                for r in replies
            ]
        }
    }


@customer_router.post("/{ticket_id}/reply")
async def reply_ticket(
    ticket_id: int,
    data: TicketReplyCreate,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account)
):
    """回复工单"""
    result = await db.execute(
        select(Ticket).where(Ticket.id == ticket_id, Ticket.account_id == account.id)
    )
    ticket = result.scalar_one_or_none()
    
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")
    
    if ticket.status in ['closed', 'cancelled']:
        raise HTTPException(status_code=400, detail="工单已关闭，无法回复")
    
    reply = TicketReply(
        ticket_id=ticket_id,
        reply_by_type='account',
        reply_by_id=account.id,
        reply_by_name=account.account_name,
        content=data.content,
        attachments=data.attachments,
        source='web'
    )
    
    db.add(reply)
    
    # 如果工单状态是等待用户回复，则改为处理中
    if ticket.status == 'pending_user':
        ticket.status = 'in_progress'
    
    await db.commit()
    
    # 发送通知给管理员
    message = (
        f"💬 *工单用户回复*\n\n"
        f"工单号: `{ticket.ticket_no}`\n"
        f"回复人: {account.account_name}\n"
        f"内容: {data.content[:200] + '...' if len(data.content) > 200 else data.content}"
    )
    await notification_service.notify_admin_group(message)
    
    return {"success": True, "message": "回复成功"}


@customer_router.post("/{ticket_id}/rate")
async def rate_ticket(
    ticket_id: int,
    rating: int = Query(..., ge=1, le=5),
    comment: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account)
):
    """评价工单"""
    result = await db.execute(
        select(Ticket).where(
            Ticket.id == ticket_id,
            Ticket.account_id == account.id,
            Ticket.status.in_(['resolved', 'closed'])
        )
    )
    ticket = result.scalar_one_or_none()
    
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在或未解决")
    
    ticket.satisfaction_rating = rating
    ticket.satisfaction_comment = comment
    
    await db.commit()
    
    return {"success": True, "message": "评价成功"}


# ============ 管理员工单接口 ============

admin_router = APIRouter(prefix="/admin/tickets", tags=["管理员工单"])


@admin_router.get("")
async def get_all_tickets(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    ticket_type: Optional[str] = None,
    priority: Optional[str] = None,
    assigned_to: Optional[int] = None,
    keyword: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """获取所有工单列表(管理员)"""
    query = select(Ticket).options(selectinload(Ticket.account))
    
    if status:
        query = query.where(Ticket.status == status)
    if ticket_type:
        query = query.where(Ticket.ticket_type == ticket_type)
    if priority:
        query = query.where(Ticket.priority == priority)
    if assigned_to:
        query = query.where(Ticket.assigned_to == assigned_to)
    if keyword:
        query = query.where(
            or_(
                Ticket.ticket_no.ilike(f"%{keyword}%"),
                Ticket.title.ilike(f"%{keyword}%")
            )
        )
    
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)
    
    # 优先级排序：urgent > high > normal > low
    query = query.order_by(
        func.field(Ticket.priority, 'urgent', 'high', 'normal', 'low'),
        Ticket.created_at.desc()
    )
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    tickets = result.scalars().all()
    
    return {
        "success": True,
        "total": total,
        "page": page,
        "page_size": page_size,
        "tickets": [
            {
                "id": t.id,
                "ticket_no": t.ticket_no,
                "ticket_type": t.ticket_type,
                "priority": t.priority,
                "category": t.category,
                "title": t.title,
                "status": t.status,
                "account_id": t.account_id,
                "account_name": t.account.account_name if t.account else None,
                "assigned_to": t.assigned_to,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None
            }
            for t in tickets
        ]
    }


@admin_router.get("/dashboard")
async def get_tickets_dashboard(
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """工单仪表板统计"""
    # 各状态数量
    status_query = select(
        Ticket.status,
        func.count(Ticket.id).label('count')
    ).group_by(Ticket.status)
    
    result = await db.execute(status_query)
    status_stats = {row.status: row.count for row in result}
    
    # 各类型数量
    type_query = select(
        Ticket.ticket_type,
        func.count(Ticket.id).label('count')
    ).group_by(Ticket.ticket_type)
    
    result = await db.execute(type_query)
    type_stats = {row.ticket_type: row.count for row in result}
    
    # 今日新增
    from datetime import date
    today_query = select(func.count(Ticket.id)).where(
        func.date(Ticket.created_at) == date.today()
    )
    today_count = await db.scalar(today_query)
    
    # 待处理（open + assigned）
    pending_count = status_stats.get('open', 0) + status_stats.get('assigned', 0)
    
    return {
        "success": True,
        "dashboard": {
            "status_stats": status_stats,
            "type_stats": type_stats,
            "today_count": today_count or 0,
            "pending_count": pending_count,
            "total_count": sum(status_stats.values())
        }
    }


@admin_router.get("/{ticket_id}/attachments/{filename}")
async def download_ticket_attachment(
    ticket_id: int,
    filename: str,
    admin: AdminUser = Depends(get_current_admin)
):
    """下载工单附件（解决方案中的图片等）"""
    # 安全检查：文件名仅允许字母数字、下划线、横线、点
    if not all(c.isalnum() or c in "._-" for c in filename):
        raise HTTPException(status_code=400, detail="非法文件名")
    file_path = TICKET_DIR / str(ticket_id) / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="附件不存在")
    return FileResponse(path=str(file_path), filename=filename)


@admin_router.get("/{ticket_id}")
async def get_ticket_detail_admin(
    ticket_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """获取工单详情(管理员)"""
    result = await db.execute(
        select(Ticket)
        .options(
            selectinload(Ticket.replies),
            selectinload(Ticket.account),
            selectinload(Ticket.assignee)
        )
        .where(Ticket.id == ticket_id)
    )
    ticket = result.scalar_one_or_none()
    
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")
    
    return {
        "success": True,
        "ticket": {
            "id": ticket.id,
            "ticket_no": ticket.ticket_no,
            "ticket_type": ticket.ticket_type,
            "priority": ticket.priority,
            "category": ticket.category,
            "title": ticket.title,
            "description": ticket.description,
            "attachments": ticket.attachments,
            "status": ticket.status,
            "account_id": ticket.account_id,
            "account_name": ticket.account.account_name if ticket.account else None,
            "account_email": ticket.account.email if ticket.account else None,
            "tg_user_id": ticket.tg_user_id,
            "assigned_to": ticket.assigned_to,
            "assignee_name": ticket.assignee.username if ticket.assignee else None,
            "resolution": ticket.resolution,
            "satisfaction_rating": ticket.satisfaction_rating,
            "satisfaction_comment": ticket.satisfaction_comment,
            "extra_data": ticket.extra_data,
            "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
            "updated_at": ticket.updated_at.isoformat() if ticket.updated_at else None,
            "assigned_at": ticket.assigned_at.isoformat() if ticket.assigned_at else None,
            "resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else None,
            "closed_at": ticket.closed_at.isoformat() if ticket.closed_at else None,
            "replies": [
                {
                    "id": r.id,
                    "reply_by_type": r.reply_by_type,
                    "reply_by_name": r.reply_by_name,
                    "content": r.content,
                    "attachments": r.attachments,
                    "is_internal": r.is_internal,
                    "is_solution": r.is_solution,
                    "source": r.source,
                    "created_at": r.created_at.isoformat() if r.created_at else None
                }
                for r in ticket.replies
            ]
        }
    }


@admin_router.post("/{ticket_id}/assign")
async def assign_ticket(
    ticket_id: int,
    data: TicketAssign,
    db: AsyncSession = Depends(get_db),
    auth = Depends(audited("ticket", "assign")),
):
    """分配工单"""
    admin, audit = auth
    ticket = await db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")

    # 验证管理员存在
    assignee = await db.get(AdminUser, data.admin_id)
    if not assignee:
        raise HTTPException(status_code=404, detail="分配目标管理员不存在")

    ticket.assigned_to = data.admin_id
    ticket.assigned_at = datetime.now()
    if ticket.status == 'open':
        ticket.status = 'assigned'

    await db.commit()
    await audit(target_id=ticket_id, target_type="ticket",
                title=f"分配工单 {ticket.ticket_no} → {assignee.username}",
                detail={"ticket_no": ticket.ticket_no, "assigned_to": assignee.username})
    await db.commit()
    return {"success": True, "message": "工单分配成功"}


@admin_router.post("/{ticket_id}/reply")
async def admin_reply_ticket(
    ticket_id: int,
    data: TicketReplyCreate,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """管理员回复工单"""
    ticket = await db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")
    
    reply = TicketReply(
        ticket_id=ticket_id,
        reply_by_type='admin',
        reply_by_id=admin.id,
        reply_by_name=admin.username,
        content=data.content,
        attachments=data.attachments,
        is_internal=data.is_internal,
        source='web'
    )
    
    db.add(reply)
    
    # 如果不是内部备注，更新状态为等待用户回复
    if not data.is_internal and ticket.status in ['open', 'assigned', 'in_progress']:
        ticket.status = 'pending_user'
    
    await db.commit()
    
    # 如果不是内部备注，通知客户
    if not data.is_internal:
        # 获取客户TG ID
        tg_id = ticket.tg_user_id
        if not tg_id:
            # 尝试从绑定表获取
            result = await db.execute(
                select(TelegramBinding.tg_id)
                .where(TelegramBinding.account_id == ticket.account_id, TelegramBinding.is_active == True)
                .limit(1)
            )
            tg_id = result.scalar_one_or_none()
        
        if tg_id:
            message = (
                f"📩 *工单新回复*\n\n"
                f"工单号: `{ticket.ticket_no}`\n"
                f"回复人: 客服 {admin.username}\n"
                f"内容: {data.content[:200] + '...' if len(data.content) > 200 else data.content}"
            )
            await notification_service.notify_user(tg_id, message)
    
    return {"success": True, "message": "回复成功"}


@admin_router.post("/{ticket_id}/resolve")
async def resolve_ticket(
    ticket_id: int,
    resolution: str = Form(..., description="解决方案"),
    files: List[UploadFile] = File(default=[]),
    db: AsyncSession = Depends(get_db),
    auth = Depends(audited("ticket", "resolve")),
):
    """解决工单（支持图片上传）"""
    admin, audit = auth
    ticket = await db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")
    
    ticket.status = 'resolved'
    ticket.resolved_at = datetime.now()
    ticket.resolved_by = admin.id
    ticket.resolution = resolution
    
    # 保存上传的图片
    attachment_paths = []
    if files:
        upload_dir = _ensure_ticket_dir(ticket_id)
        for f in files:
            if not f.filename:
                continue
            ext = Path(f.filename).suffix.lower()
            if ext not in ALLOWED_IMAGE_EXTENSIONS:
                continue
            content_bytes = await f.read()
            if len(content_bytes) > 10 * 1024 * 1024:  # 10MB 限制
                continue
            safe_name = f"{uuid.uuid4().hex[:8]}_{f.filename}"
            file_path = upload_dir / safe_name
            with open(file_path, "wb") as fp:
                fp.write(content_bytes)
            attachment_paths.append(safe_name)
    
    # 添加解决方案回复（含附件）
    reply = TicketReply(
        ticket_id=ticket_id,
        reply_by_type='admin',
        reply_by_id=admin.id,
        reply_by_name=admin.username,
        content=resolution,
        attachments=attachment_paths if attachment_paths else None,
        is_solution=True,
        source='web'
    )
    db.add(reply)
    
    await db.commit()
    
    # 通知客户
    tg_id = ticket.tg_user_id
    if not tg_id:
        result = await db.execute(
            select(TelegramBinding.tg_id)
            .where(TelegramBinding.account_id == ticket.account_id, TelegramBinding.is_active == True)
            .limit(1)
        )
        tg_id = result.scalar_one_or_none()
    
    if tg_id:
        message = (
            f"✅ *工单已解决*\n\n"
            f"工单号: `{ticket.ticket_no}`\n"
            f"解决方案: {resolution}\n\n"
            f"如果您有任何疑问，请继续回复工单。"
        )
        await notification_service.notify_user(tg_id, message)
        # 发送上传的图片
        if attachment_paths:
            upload_dir = TICKET_DIR / str(ticket_id)
            for fn in attachment_paths:
                file_path = upload_dir / fn
                if file_path.exists():
                    await notification_service.send_photo(str(tg_id), file_path)

    await audit(target_id=ticket_id, target_type="ticket",
                title=f"解决工单 {ticket.ticket_no}",
                detail={"ticket_no": ticket.ticket_no,
                        "resolution_len": len(resolution or ""),
                        "attachment_count": len(attachment_paths)})
    await db.commit()
    return {"success": True, "message": "工单已解决"}


@admin_router.post("/{ticket_id}/close")
async def close_ticket(
    ticket_id: int,
    reason: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    auth = Depends(audited("ticket", "close")),
):
    """关闭工单"""
    admin, audit = auth
    ticket = await db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")

    ticket.status = 'closed'
    ticket.closed_at = datetime.now()
    ticket.closed_by = admin.id
    ticket.close_reason = reason

    await db.commit()
    await audit(target_id=ticket_id, target_type="ticket",
                title=f"关闭工单 {ticket.ticket_no}",
                detail={"ticket_no": ticket.ticket_no, "reason": reason})
    await db.commit()
    return {"success": True, "message": "工单已关闭"}


@admin_router.put("/{ticket_id}/status")
async def update_ticket_status_admin(
    ticket_id: int,
    status: str = Query(..., description="目标状态"),
    db: AsyncSession = Depends(get_db),
    auth = Depends(audited("ticket", "update_status")),
):
    """更新工单状态（与前端 PUT /admin/tickets/{id}/status 对齐）"""
    admin, audit = auth
    valid_statuses = {
        "open",
        "assigned",
        "in_progress",
        "pending_user",
        "resolved",
        "closed",
        "cancelled",
    }
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail="无效的状态值")

    ticket = await db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")

    old_status = ticket.status
    ticket.status = status
    now = datetime.now()
    if status == "closed":
        ticket.closed_at = now
        ticket.closed_by = admin.id
    elif status == "resolved" and not ticket.resolved_at:
        ticket.resolved_at = now
        ticket.resolved_by = admin.id

    await db.commit()
    await audit(target_id=ticket_id, target_type="ticket",
                title=f"工单状态变更 {ticket.ticket_no}: {old_status} → {status}",
                detail={"ticket_no": ticket.ticket_no, "from": old_status, "to": status})
    await db.commit()
    return {"success": True, "message": "状态已更新"}


@admin_router.delete("/{ticket_id}")
async def delete_ticket_admin(
    ticket_id: int,
    db: AsyncSession = Depends(get_db),
    auth = Depends(audited("ticket", "delete")),
):
    """管理员删除工单（级联删除回复，并清理附件目录）"""
    admin, audit = auth
    ticket = await db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")
    snap = {"ticket_no": ticket.ticket_no, "subject": getattr(ticket, "subject", None),
            "status": ticket.status, "account_id": ticket.account_id}
    await db.execute(delete(TicketReply).where(TicketReply.ticket_id == ticket_id))
    await db.delete(ticket)
    await db.commit()
    upload_dir = TICKET_DIR / str(ticket_id)
    if upload_dir.exists():
        try:
            shutil.rmtree(upload_dir)
        except OSError:
            pass
    await audit(target_id=ticket_id, target_type="ticket",
                title=f"删除工单 {snap['ticket_no']}",
                detail=snap)
    await db.commit()
    return {"success": True, "message": "工单已删除"}


@admin_router.put("/{ticket_id}")
async def update_ticket_admin(
    ticket_id: int,
    data: TicketUpdate,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """更新工单(管理员)"""
    ticket = await db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")
    
    update_data = data.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(ticket, key, value)
    
    await db.commit()
    
    return {"success": True, "message": "工单更新成功"}


# ============ 快捷回复模板 ============

@admin_router.get("/templates")
async def get_ticket_templates(
    template_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """获取快捷回复模板"""
    query = select(TicketTemplate).where(
        TicketTemplate.is_deleted == False,
        TicketTemplate.status == 'active'
    )
    
    if template_type:
        query = query.where(TicketTemplate.template_type == template_type)
    
    result = await db.execute(query.order_by(TicketTemplate.usage_count.desc()))
    templates = result.scalars().all()
    
    return {
        "success": True,
        "templates": [
            {
                "id": t.id,
                "template_name": t.template_name,
                "template_type": t.template_type,
                "content_template": t.content_template,
                "usage_count": t.usage_count
            }
            for t in templates
        ]
    }


# 合并路由
router.include_router(customer_router)
router.include_router(admin_router)
