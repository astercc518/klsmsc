"""
TG助手管理API
"""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from app.database import get_db
from app.core.auth import AuthService
from app.modules.common.admin_user import AdminUser
from app.modules.common.invitation_code import InvitationCode
from app.modules.common.recharge_order import RechargeOrder
from app.modules.sms.sms_batch import SmsBatch
from app.modules.sms.sms_template import SmsTemplate
from app.modules.common.account import Account
from app.modules.common.telegram_binding import TelegramBinding
from app.core.invitation import InvitationService
from app.core.audit import AuditService
from app.utils.logger import get_logger
from app.workers.batch_worker import process_batch
from pydantic import BaseModel
from datetime import datetime
import httpx
import os

logger = get_logger(__name__)
router = APIRouter()

# --- Schemas ---

class InviteCreateRequest(BaseModel):
    country: str = "CN"
    price: float
    business_type: str = "sms"
    valid_hours: int = 24

class InviteResponse(BaseModel):
    code: str
    sales_id: int
    pricing_config: Optional[Dict]
    status: str
    created_at: datetime

class AuditRequest(BaseModel):
    action: str  # approve / reject
    reason: Optional[str] = None

# --- Endpoints ---

# 1. 邀请码管理
@router.get("/invites", response_model=Dict[str, Any])
async def list_invites(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    sales_id: Optional[int] = None,
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """获取邀请码列表"""
    # 构建查询条件
    where_conditions = []
    
    # 销售只能看自己的
    if admin.role == 'sales':
        where_conditions.append(InvitationCode.sales_id == admin.id)
    elif sales_id and admin.role in ['super_admin', 'admin']:
        where_conditions.append(InvitationCode.sales_id == sales_id)
        
    if status:
        where_conditions.append(InvitationCode.status == status)
        
    # 获取总数
    count_query = select(func.count(InvitationCode.code))
    if where_conditions:
        for condition in where_conditions:
            count_query = count_query.where(condition)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # 分页查询
    query = select(InvitationCode)
    if where_conditions:
        for condition in where_conditions:
            query = query.where(condition)
    query = query.order_by(desc(InvitationCode.created_at))
    query = query.offset((page - 1) * limit).limit(limit)
    
    result = await db.execute(query)
    invites = result.scalars().all()
    
    # 关联查询销售信息
    sales_ids = {i.sales_id for i in invites}
    sales_map = {}
    if sales_ids:
        sales_query = select(AdminUser).where(AdminUser.id.in_(sales_ids))
        sales_result = await db.execute(sales_query)
        sales_map = {
            s.id: s.real_name or s.username or f"User_{s.id}"
            for s in sales_result.scalars().all()
        }
    
    return {
        "items": [
            {
                "code": i.code,
                "sales_id": i.sales_id,
                "sales_name": sales_map.get(i.sales_id, "未知"),
                "config": i.pricing_config or {},
                "status": i.status,
                "used_by_account_id": i.used_by_account_id,
                "created_at": i.created_at.isoformat() if i.created_at else None,
                "expires_at": i.expires_at.isoformat() if i.expires_at else None,
                "used_at": i.used_at.isoformat() if i.used_at else None
            }
            for i in invites
        ],
        "total": total,
        "page": page,
        "limit": limit
    }

@router.post("/invites")
async def create_invite(
    request: InviteCreateRequest,
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """创建邀请码"""
    if admin.role not in ['sales', 'super_admin', 'admin']:
        raise HTTPException(status_code=403, detail="无权操作")
        
    service = InvitationService(db)
    config = {
        "country": request.country,
        "price": request.price,
        "business_type": request.business_type
    }
    
    code = await service.create_code(admin.id, config, request.valid_hours)
    
    # 生成邀请链接
    bot_username = os.getenv("TELEGRAM_BOT_USERNAME", "your_bot")
    invite_link = f"https://t.me/{bot_username}?start={code}"
    
    return {
        "success": True,
        "code": code,
        "invite_link": invite_link
    }

@router.get("/invites/{code}")
async def get_invite_detail(
    code: str,
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """获取邀请码详情"""
    result = await db.execute(
        select(InvitationCode).where(InvitationCode.code == code)
    )
    invite = result.scalar_one_or_none()
    
    if not invite:
        raise HTTPException(status_code=404, detail="邀请码不存在")
    
    # 权限检查：销售只能查看自己的
    if admin.role == 'sales' and invite.sales_id != admin.id:
        raise HTTPException(status_code=403, detail="无权查看")
    
    # 获取销售信息
    sales_result = await db.execute(
        select(AdminUser).where(AdminUser.id == invite.sales_id)
    )
    sales = sales_result.scalar_one_or_none()
    
    # 获取使用账户信息
    account_info = None
    if invite.used_by_account_id:
        acc_result = await db.execute(
            select(Account).where(Account.id == invite.used_by_account_id)
        )
        account = acc_result.scalar_one_or_none()
        if account:
            account_info = {
                "id": account.id,
                "name": account.account_name
            }
    
    return {
        "code": invite.code,
        "sales_id": invite.sales_id,
        "sales_name": sales.real_name or sales.username if sales else "未知",
        "config": invite.pricing_config or {},
        "status": invite.status,
        "used_by_account_id": invite.used_by_account_id,
        "used_by_account": account_info,
        "created_at": invite.created_at.isoformat() if invite.created_at else None,
        "expires_at": invite.expires_at.isoformat() if invite.expires_at else None,
        "used_at": invite.used_at.isoformat() if invite.used_at else None
    }

@router.get("/invites/stats/summary")
async def get_invite_stats(
    sales_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """获取邀请码统计"""
    where_conditions = []
    
    # 销售只能看自己的
    if admin.role == 'sales':
        where_conditions.append(InvitationCode.sales_id == admin.id)
    elif sales_id and admin.role in ['super_admin', 'admin']:
        where_conditions.append(InvitationCode.sales_id == sales_id)
    
    # 时间范围筛选
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            where_conditions.append(InvitationCode.created_at >= start_dt)
        except:
            pass
    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            where_conditions.append(InvitationCode.created_at <= end_dt)
        except:
            pass
    
    # 统计总数
    count_query = select(func.count(InvitationCode.code))
    if where_conditions:
        for condition in where_conditions:
            count_query = count_query.where(condition)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # 按状态统计
    status_query = select(
        InvitationCode.status,
        func.count(InvitationCode.code).label("count")
    )
    if where_conditions:
        for condition in where_conditions:
            status_query = status_query.where(condition)
    status_query = status_query.group_by(InvitationCode.status)
    status_result = await db.execute(status_query)
    status_stats = {row.status: row.count for row in status_result.all()}
    
    return {
        "total": total,
        "unused": status_stats.get("unused", 0),
        "used": status_stats.get("used", 0),
        "expired": status_stats.get("expired", 0),
        "usage_rate": round(status_stats.get("used", 0) / total * 100, 2) if total > 0 else 0
    }

# 2. 充值审核
@router.get("/recharges")
async def list_recharges(
    status: str = Query('pending', description="工单状态"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """获取充值工单列表"""
    if admin.role not in ['finance', 'super_admin', 'admin']:
        raise HTTPException(status_code=403, detail="需要财务权限")
        
    # 获取总数
    count_query = select(func.count(RechargeOrder.id)).where(RechargeOrder.status == status)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # 分页查询
    query = select(RechargeOrder).where(RechargeOrder.status == status)
    query = query.order_by(desc(RechargeOrder.created_at))
    query = query.offset((page - 1) * limit).limit(limit)
    result = await db.execute(query)
    orders = result.scalars().all()
    
    # 关联查询账户信息
    account_ids = {o.account_id for o in orders}
    account_map = {}
    if account_ids:
        acc_query = select(Account).where(Account.id.in_(account_ids))
        acc_result = await db.execute(acc_query)
        account_map = {acc.id: acc for acc in acc_result.scalars().all()}
    
    return {
        "items": [
        {
            "id": o.id,
            "order_no": o.order_no,
            "account_id": o.account_id,
                "account_name": account_map.get(o.account_id, Account()).account_name if account_map.get(o.account_id) else None,
            "amount": float(o.amount),
                "currency": o.currency,
            "proof": o.payment_proof,
                "status": o.status,
                "created_at": o.created_at.isoformat() if o.created_at else None,
                "finance_audit_by": o.finance_audit_by,
                "finance_audit_at": o.finance_audit_at.isoformat() if o.finance_audit_at else None,
                "reject_reason": o.reject_reason
        }
        for o in orders
        ],
        "total": total,
        "page": page,
        "limit": limit
    }

@router.get("/recharges/{oid}")
async def get_recharge_detail(
    oid: int,
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """获取充值工单详情"""
    if admin.role not in ['finance', 'super_admin', 'admin']:
        raise HTTPException(status_code=403, detail="需要财务权限")
    
    result = await db.execute(select(RechargeOrder).where(RechargeOrder.id == oid))
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    
    # 获取账户信息
    acc_result = await db.execute(select(Account).where(Account.id == order.account_id))
    account = acc_result.scalar_one_or_none()
    
    return {
        "id": order.id,
        "order_no": order.order_no,
        "account_id": order.account_id,
        "account": {
            "id": account.id if account else None,
            "name": account.account_name if account else None,
            "balance": float(account.balance) if account else 0,
            "currency": account.currency if account else "USD"
        } if account else None,
        "amount": float(order.amount),
        "currency": order.currency,
        "payment_proof": order.payment_proof,
        "status": order.status,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "finance_audit_by": order.finance_audit_by,
        "finance_audit_at": order.finance_audit_at.isoformat() if order.finance_audit_at else None,
        "tech_audit_by": order.tech_audit_by,
        "tech_audit_at": order.tech_audit_at.isoformat() if order.tech_audit_at else None,
        "reject_reason": order.reject_reason
    }

async def notify_telegram_user(account_id: int, message: str, db: AsyncSession):
    """通知Telegram用户"""
    try:
        # 查找账户的Telegram绑定
        binding_query = select(TelegramBinding).where(
            TelegramBinding.account_id == account_id,
            TelegramBinding.is_active == True
        )
        binding_result = await db.execute(binding_query)
        binding = binding_result.scalar_one_or_none()
        
        if not binding:
            logger.warning(f"账户 {account_id} 没有Telegram绑定")
            return False
        
        # 从系统配置或环境变量获取Bot Token
        from app.services.config_service import ConfigService
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not bot_token:
            bot_token = await ConfigService.get("telegram_bot_token", db)
        
        if not bot_token:
            logger.warning("TELEGRAM_BOT_TOKEN 未配置，跳过通知")
            return False
        
        telegram_api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": binding.tg_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(telegram_api_url, json=payload)
            if response.status_code == 200:
                logger.info(f"Telegram通知发送成功: account_id={account_id}, tg_id={binding.tg_id}")
                return True
            else:
                logger.error(f"Telegram通知发送失败: {response.status_code} {response.text}")
                return False
                
    except Exception as e:
        logger.error(f"发送Telegram通知异常: {str(e)}", exc_info=e)
        return False

@router.post("/recharges/{oid}/audit")
async def audit_recharge(
    oid: int,
    request: AuditRequest,
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """审核充值工单"""
    if admin.role not in ['finance', 'super_admin', 'admin']:
        raise HTTPException(status_code=403, detail="需要财务权限")
    
    if request.action == 'reject' and not request.reason:
        raise HTTPException(status_code=400, detail="拒绝时必须提供原因")
        
    result = await db.execute(select(RechargeOrder).where(RechargeOrder.id == oid))
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
        
    if order.status != 'pending':
        raise HTTPException(status_code=400, detail="工单状态不正确，无法审核")
        
    if request.action == 'approve':
        # 增加余额
        from app.modules.common.balance_log import BalanceLog
        
        acc_res = await db.execute(select(Account).where(Account.id == order.account_id))
        account = acc_res.scalar_one_or_none()
        
        if not account:
            raise HTTPException(status_code=404, detail="账户不存在")
        
        # 更新余额
        account.balance += order.amount
        order.status = 'completed'
        order.finance_audit_by = admin.id
        order.finance_audit_at = datetime.now()
        
        # 记录余额日志
        balance_before = float(account.balance) - float(order.amount)
        log = BalanceLog(
            account_id=account.id,
            change_type='deposit',
            amount=order.amount,
            balance_after=float(account.balance),
            description=f"Recharge Order {order.order_no} (Before: {balance_before}, After: {account.balance})",
            related_order_id=order.id
        )
        db.add(log)
        
        await db.commit()
        
        # 通知用户
        notify_message = (
            f"✅ **充值成功！**\n\n"
            f"💰 金额: {order.amount} {order.currency}\n"
            f"📋 工单号: {order.order_no}\n"
            f"💵 当前余额: {account.balance} {account.currency}\n\n"
            f"感谢您的使用！"
        )
        await notify_telegram_user(order.account_id, notify_message, db)
    
    elif request.action == 'reject':
        order.status = 'rejected'
        order.reject_reason = request.reason
        order.finance_audit_by = admin.id
        order.finance_audit_at = datetime.now()
        
        await db.commit()
        
        # 通知用户
        notify_message = (
            f"❌ **充值申请被拒绝**\n\n"
            f"📋 工单号: {order.order_no}\n"
            f"💰 申请金额: {order.amount} {order.currency}\n"
            f"📝 拒绝原因: {request.reason or '未提供原因'}\n\n"
            f"如有疑问，请联系客服。"
        )
        await notify_telegram_user(order.account_id, notify_message, db)
    else:
        raise HTTPException(status_code=400, detail="无效的操作")
        
    return {"success": True, "message": "审核成功"}

# 3. 群发审核
@router.get("/batches")
async def list_batches(
    status: str = Query('pending_audit', description="批次状态"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """获取群发批次列表"""
    # 获取总数
    count_query = select(func.count(SMSBatch.id)).where(SMSBatch.status == status)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # 分页查询
    query = select(SMSBatch).where(SMSBatch.status == status)
    query = query.order_by(desc(SMSBatch.created_at))
    query = query.offset((page - 1) * limit).limit(limit)
    result = await db.execute(query)
    batches = result.scalars().all()
    
    # 关联查询账户信息
    account_ids = {b.account_id for b in batches}
    account_map = {}
    if account_ids:
        acc_query = select(Account).where(Account.id.in_(account_ids))
        acc_result = await db.execute(acc_query)
        account_map = {acc.id: acc for acc in acc_result.scalars().all()}
    
    return {
        "items": [
        {
            "id": b.id,
            "account_id": b.account_id,
                "account_name": account_map.get(b.account_id, Account()).account_name if account_map.get(b.account_id) else None,
            "content": b.content,
                "content_preview": (b.content[:50] + "...") if b.content and len(b.content) > 50 else b.content,
            "total_count": b.total_count,
                "valid_count": b.valid_count,
            "total_cost": float(b.total_cost),
                "status": b.status,
                "created_at": b.created_at.isoformat() if b.created_at else None,
                "audit_by": b.audit_by,
                "audit_at": b.audit_at.isoformat() if b.audit_at else None
        }
        for b in batches
        ],
        "total": total,
        "page": page,
        "limit": limit
    }

@router.get("/batches/{bid}")
async def get_batch_detail(
    bid: str,
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """获取群发批次详情"""
    result = await db.execute(select(SMSBatch).where(SMSBatch.id == bid))
    batch = result.scalar_one_or_none()
    
    if not batch:
        raise HTTPException(status_code=404, detail="批次不存在")
    
    # 获取账户信息
    acc_result = await db.execute(select(Account).where(Account.id == batch.account_id))
    account = acc_result.scalar_one_or_none()
    
    return {
        "id": batch.id,
        "account_id": batch.account_id,
        "account_name": account.account_name if account else None,
        "file_path": batch.file_path,
        "content": batch.content,
        "total_count": batch.total_count,
        "valid_count": batch.valid_count,
        "total_cost": float(batch.total_cost),
        "status": batch.status,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
        "audit_by": batch.audit_by,
        "audit_at": batch.audit_at.isoformat() if batch.audit_at else None
    }

@router.post("/batches/{bid}/audit")
async def audit_batch(
    bid: str,
    request: AuditRequest,
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """审核群发批次"""
    if request.action == 'reject' and not request.reason:
        raise HTTPException(status_code=400, detail="拒绝时必须提供原因")
    
    service = AuditService(db)
    
    # 检查批次状态
    batch_result = await db.execute(select(SMSBatch).where(SMSBatch.id == bid))
    batch = batch_result.scalar_one_or_none()
    
    if not batch:
        raise HTTPException(status_code=404, detail="批次不存在")
    
    if batch.status != 'pending_audit':
        raise HTTPException(status_code=400, detail="批次状态不正确，无法审核")
    
    if request.action == 'approve':
        batch = await service.approve_batch(bid, admin.id)
        
        # 触发发送流程
        process_batch.delay(str(bid))
        
        # 通知用户
        notify_message = (
            f"✅ **群发审核通过**\n\n"
            f"📦 批次ID: {bid}\n"
            f"📝 内容: {batch.content[:50]}...\n"
            f"📊 总数: {batch.total_count}条\n"
            f"💰 费用: {batch.total_cost}\n\n"
            f"已开始发送，请稍后查看结果。"
        )
        await notify_telegram_user(batch.account_id, notify_message, db)
        
    elif request.action == 'reject':
        batch = await service.reject_batch(bid, admin.id, request.reason)
        
        # 通知用户
        notify_message = (
            f"❌ **群发审核被拒绝**\n\n"
            f"📦 批次ID: {bid}\n"
            f"📝 内容: {batch.content[:50]}...\n"
            f"📋 拒绝原因: {request.reason or '未提供原因'}\n\n"
            f"请修改后重新提交。"
        )
        await notify_telegram_user(batch.account_id, notify_message, db)
    else:
        raise HTTPException(status_code=400, detail="无效的操作")
        
    return {"success": True, "message": "审核成功"}

# 4. 白名单管理
class TemplateCreateRequest(BaseModel):
    account_id: int
    content_text: str

class TemplateUpdateRequest(BaseModel):
    status: str  # approved / rejected

@router.get("/templates")
async def list_templates(
    account_id: Optional[int] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """获取白名单列表"""
    where_conditions = []
    
    if account_id:
        where_conditions.append(SMSTemplate.account_id == account_id)
    
    if search:
        where_conditions.append(SMSTemplate.content_text.like(f"%{search}%"))
    
    # 获取总数
    count_query = select(func.count(SMSTemplate.id))
    if where_conditions:
        for condition in where_conditions:
            count_query = count_query.where(condition)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # 分页查询
    query = select(SMSTemplate)
    if where_conditions:
        for condition in where_conditions:
            query = query.where(condition)
    query = query.order_by(desc(SMSTemplate.created_at))
    query = query.offset((page - 1) * limit).limit(limit)
    result = await db.execute(query)
    tpls = result.scalars().all()
    
    # 关联查询账户信息
    account_ids = {t.account_id for t in tpls}
    account_map = {}
    if account_ids:
        acc_query = select(Account).where(Account.id.in_(account_ids))
        acc_result = await db.execute(acc_query)
        account_map = {acc.id: acc for acc in acc_result.scalars().all()}
    
    return {
        "items": [
        {
            "id": t.id,
                "account_id": t.account_id,
                "account_name": account_map.get(t.account_id, Account()).account_name if account_map.get(t.account_id) else None,
            "hash": t.content_hash,
            "text": t.content_text,
            "status": t.status,
                "created_at": t.created_at.isoformat() if t.created_at else None
        }
        for t in tpls
        ],
        "total": total,
        "page": page,
        "limit": limit
    }

@router.post("/templates")
async def create_template(
    request: TemplateCreateRequest,
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """创建白名单"""
    # 验证账户是否存在
    acc_result = await db.execute(select(Account).where(Account.id == request.account_id))
    account = acc_result.scalar_one_or_none()
    
    if not account:
        raise HTTPException(status_code=404, detail="账户不存在")
    
    # 计算内容哈希
    import hashlib
    content_hash = hashlib.sha256(request.content_text.strip().encode('utf-8')).hexdigest()
    
    # 检查是否已存在
    existing_query = select(SMSTemplate).where(
        SMSTemplate.account_id == request.account_id,
        SMSTemplate.content_hash == content_hash
    )
    existing_result = await db.execute(existing_query)
    existing = existing_result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(status_code=400, detail="该文案已存在于白名单")
    
    # 创建白名单
    template = SMSTemplate(
        account_id=request.account_id,
        content_hash=content_hash,
        content_text=request.content_text.strip(),
        status='approved'
    )
    db.add(template)
    await db.commit()
    
    return {
        "success": True,
        "id": template.id,
        "content_hash": content_hash
    }

@router.put("/templates/{tid}")
async def update_template(
    tid: int,
    request: TemplateUpdateRequest,
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """更新白名单状态"""
    if request.status not in ['approved', 'rejected']:
        raise HTTPException(status_code=400, detail="无效的状态")
    
    result = await db.execute(select(SMSTemplate).where(SMSTemplate.id == tid))
    template = result.scalar_one_or_none()
    
    if not template:
        raise HTTPException(status_code=404, detail="白名单不存在")
    
    template.status = request.status
    await db.commit()
    
    return {"success": True}

@router.delete("/templates/{tid}")
async def delete_template(
    tid: int,
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """删除白名单"""
    result = await db.execute(select(SMSTemplate).where(SMSTemplate.id == tid))
    template = result.scalar_one_or_none()
    
    if not template:
        raise HTTPException(status_code=404, detail="白名单不存在")
    
    await db.delete(template)
    await db.commit()
    
    return {"success": True}


# 5. Bot配置管理
class BotConfigUpdate(BaseModel):
    bot_token: Optional[str] = None
    bot_username: Optional[str] = None
    bot_status: Optional[str] = None
    admin_group_id: Optional[str] = None
    notification_group_id: Optional[str] = None
    enable_register: Optional[bool] = None
    enable_recharge: Optional[bool] = None
    enable_batch_review: Optional[bool] = None
    enable_balance_query: Optional[bool] = None
    enable_send_sms: Optional[bool] = None
    enable_sms_content_review: Optional[bool] = None
    enable_ticket: Optional[bool] = None
    welcome_message: Optional[str] = None
    help_message: Optional[str] = None
    maintenance_message: Optional[str] = None
    max_recipients: Optional[int] = None
    daily_send_limit: Optional[int] = None
    min_recharge_amount: Optional[float] = None
    send_cooldown_seconds: Optional[int] = None
    webhook_url: Optional[str] = None
    webhook_secret: Optional[str] = None

@router.get("/config")
async def get_bot_config(
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """获取Bot配置"""
    from app.services.config_service import ConfigService
    
    configs = await ConfigService.get_by_category("telegram", db)
    
    bot_token = configs.get('telegram_bot_token') or os.getenv('TELEGRAM_BOT_TOKEN', '')
    bot_username = configs.get('telegram_bot_username') or os.getenv('TELEGRAM_BOT_USERNAME', '')
    
    # 检查Bot实际运行状态 - 调用Telegram API getMe
    bot_status = 'stopped'
    telegram_bot_username = ''
    
    if bot_token:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"https://api.telegram.org/bot{bot_token}/getMe")
                if response.status_code == 200:
                    data = response.json()
                    if data.get('ok'):
                        bot_status = 'active'
                        telegram_bot_username = data.get('result', {}).get('username', '')
                        # 如果数据库没有保存用户名，使用Telegram返回的
                        if not bot_username:
                            bot_username = telegram_bot_username
                else:
                    bot_status = 'error'
        except Exception as e:
            logger.warning(f"检查Bot状态失败: {e}")
            bot_status = 'unknown'
    
    return {
        "success": True,
        "config": {
            "bot_token": bot_token,
            "bot_username": bot_username,
            "bot_status": bot_status,
            "admin_group_id": configs.get('telegram_admin_group_id') or os.getenv('TELEGRAM_ADMIN_GROUP_ID', ''),
            "notification_group_id": configs.get('telegram_notification_group_id', ''),
            "enable_register": configs.get('telegram_enable_register', 'true') == 'true',
            "enable_recharge": configs.get('telegram_enable_recharge', 'true') == 'true',
            "enable_batch_review": configs.get('telegram_enable_batch_review', 'true') == 'true',
            "enable_balance_query": configs.get('telegram_enable_balance_query', 'true') == 'true',
            "enable_send_sms": configs.get('telegram_enable_send_sms', 'true') == 'true',
            "enable_sms_content_review": configs.get('telegram_enable_sms_content_review', 'true') == 'true',
            "enable_ticket": configs.get('telegram_enable_ticket', 'true') == 'true',
            "welcome_message": configs.get('telegram_welcome_message', ''),
            "help_message": configs.get('telegram_help_message', ''),
            "maintenance_message": configs.get('telegram_maintenance_message', ''),
            "max_recipients": int(configs.get('telegram_max_recipients', '1000')),
            "daily_send_limit": int(configs.get('telegram_daily_send_limit', '10000')),
            "min_recharge_amount": float(configs.get('telegram_min_recharge_amount', '10')),
            "send_cooldown_seconds": int(configs.get('telegram_send_cooldown_seconds', '60')),
            "webhook_url": configs.get('telegram_webhook_url', ''),
            "webhook_secret": configs.get('telegram_webhook_secret', '')[:5] + "..." if configs.get('telegram_webhook_secret') else ''
        }
    }

@router.post("/config")
async def update_bot_config(
    data: BotConfigUpdate,
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """更新Bot配置"""
    if admin.role not in ['super_admin', 'admin']:
        raise HTTPException(status_code=403, detail="需要管理员权限")

    from app.services.config_service import ConfigService

    config_map = {
        'bot_token': 'telegram_bot_token',
        'bot_username': 'telegram_bot_username',
        'bot_status': 'telegram_bot_status',
        'admin_group_id': 'telegram_admin_group_id',
        'notification_group_id': 'telegram_notification_group_id',
        'enable_register': 'telegram_enable_register',
        'enable_recharge': 'telegram_enable_recharge',
        'enable_batch_review': 'telegram_enable_batch_review',
        'enable_balance_query': 'telegram_enable_balance_query',
        'enable_send_sms': 'telegram_enable_send_sms',
        'enable_sms_content_review': 'telegram_enable_sms_content_review',
        'enable_ticket': 'telegram_enable_ticket',
        'welcome_message': 'telegram_welcome_message',
        'help_message': 'telegram_help_message',
        'maintenance_message': 'telegram_maintenance_message',
        'max_recipients': 'telegram_max_recipients',
        'daily_send_limit': 'telegram_daily_send_limit',
        'min_recharge_amount': 'telegram_min_recharge_amount',
        'send_cooldown_seconds': 'telegram_send_cooldown_seconds',
        'webhook_url': 'telegram_webhook_url',
        'webhook_secret': 'telegram_webhook_secret',
    }

    update_data = data.dict(exclude_unset=True)
    updates: dict[str, str] = {}

    for field, db_key in config_map.items():
        if field in update_data and update_data[field] is not None:
            value = update_data[field]
            updates[db_key] = 'true' if value is True else ('false' if value is False else str(value))

    if updates:
        await ConfigService.batch_update(
            updates, db,
            admin_id=admin.id,
            admin_name=admin.username,
        )

        # 同步关键配置到 .env 文件，使 Docker 重启后仍可读取
        env_sync_map = {
            'telegram_bot_token': 'TELEGRAM_BOT_TOKEN',
            'telegram_admin_group_id': 'TELEGRAM_ADMIN_GROUP_ID',
        }
        env_updates = {}
        for db_key, env_key in env_sync_map.items():
            if db_key in updates:
                env_updates[env_key] = updates[db_key]
        if env_updates:
            _sync_env_file(env_updates)

    return {"success": True, "message": "配置已更新"}


def _sync_env_file(updates: dict[str, str]):
    """同步更新挂载的 .env 文件"""
    env_path = "/app/.env.host"
    if not os.path.exists(env_path):
        logger.warning(f".env 文件未挂载: {env_path}")
        return

    try:
        with open(env_path, "r") as f:
            lines = f.readlines()

        updated_keys = set()
        new_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.split("=", 1)[0]
                if key in updates:
                    new_lines.append(f"{key}={updates[key]}\n")
                    updated_keys.add(key)
                    continue
            new_lines.append(line)

        # 追加新增的 key
        for key, val in updates.items():
            if key not in updated_keys:
                new_lines.append(f"{key}={val}\n")

        with open(env_path, "w") as f:
            f.writelines(new_lines)

        logger.info(f".env 已同步: {list(updates.keys())}")
    except Exception as e:
        logger.error(f"同步 .env 失败: {e}")

@router.post("/restart")
async def restart_bot(
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """重启Bot服务"""
    if admin.role not in ['super_admin', 'admin']:
        raise HTTPException(status_code=403, detail="需要管理员权限")

    import threading

    def _restart_sync():
        proxy_url = os.getenv("DOCKER_PROXY_URL", "http://docker-proxy:2375")
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(f"{proxy_url}/containers/smsc-bot/restart", params={"t": 10})
                resp.raise_for_status()
            logger.info(f"Bot 容器重启成功 (by {admin.username})")
        except Exception as e:
            logger.error(f"Bot 容器重启失败: {e}")

    threading.Thread(target=_restart_sync, daemon=True).start()

    return {"success": True, "message": "重启命令已发送，Bot 将在数秒内重启"}


# 6. 消息记录
@router.get("/messages")
async def get_bot_messages(
    keyword: Optional[str] = None,
    direction: Optional[str] = None,
    message_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """获取Bot消息记录"""
    from app.modules.common.telegram_message import TelegramMessage
    
    where_conditions = []
    
    if keyword:
        where_conditions.append(TelegramMessage.content.ilike(f"%{keyword}%"))
    
    if direction:
        where_conditions.append(TelegramMessage.direction == direction)
    
    if message_type:
        where_conditions.append(TelegramMessage.message_type == message_type)
    
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            where_conditions.append(TelegramMessage.created_at >= start_dt)
        except:
            pass
    
    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            where_conditions.append(TelegramMessage.created_at <= end_dt)
        except:
            pass
    
    # 获取总数
    count_query = select(func.count(TelegramMessage.id))
    for condition in where_conditions:
        count_query = count_query.where(condition)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # 分页查询
    query = select(TelegramMessage)
    for condition in where_conditions:
        query = query.where(condition)
    query = query.order_by(desc(TelegramMessage.created_at))
    query = query.offset((page - 1) * limit).limit(limit)
    
    result = await db.execute(query)
    messages = result.scalars().all()
    
    # 统计
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # 今日收到
    received_query = select(func.count(TelegramMessage.id)).where(
        TelegramMessage.direction == 'incoming',
        TelegramMessage.created_at >= today_start
    )
    received_result = await db.execute(received_query)
    received_today = received_result.scalar() or 0
    
    # 今日发出
    sent_query = select(func.count(TelegramMessage.id)).where(
        TelegramMessage.direction == 'outgoing',
        TelegramMessage.created_at >= today_start
    )
    sent_result = await db.execute(sent_query)
    sent_today = sent_result.scalar() or 0
    
    # 活跃用户
    active_query = select(func.count(func.distinct(TelegramMessage.tg_user_id))).where(
        TelegramMessage.created_at >= today_start
    )
    active_result = await db.execute(active_query)
    active_users = active_result.scalar() or 0
    
    return {
        "success": True,
        "messages": [
            {
                "id": m.id,
                "tg_user_id": m.tg_user_id,
                "tg_username": m.tg_username,
                "direction": m.direction,
                "message_type": m.message_type,
                "content": m.content,
                "account_id": m.account_id,
                "account_name": m.account_name,
                "created_at": m.created_at.isoformat() if m.created_at else None
            }
            for m in messages
        ],
        "total": total,
        "page": page,
        "limit": limit,
        "stats": {
            "received_today": received_today,
            "sent_today": sent_today,
            "active_users": active_users,
            "total_messages": total
        }
    }
