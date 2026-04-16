from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Header, Body
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from datetime import datetime
import json
import uuid
import secrets
import string
import re
from app.config import settings as app_settings

from app.database import get_db
from app.modules.common.telegram_message import TelegramMessage
from app.modules.common.telegram_binding import TelegramBinding
from app.modules.common.telegram_binding import TelegramBinding
from app.modules.common.admin_user import AdminUser
from app.modules.common.account import Account
from app.modules.common.system_config import SystemConfig
from app.modules.common.account_template import AccountTemplate
from app.modules.common.ticket import Ticket, TicketReply
from app.modules.common.recharge_order import RechargeOrder
from app.modules.common.sms_content_approval import SmsContentApproval
from app.services.notification_service import notification_service
from app.utils.logger import get_logger
import uuid

logger = get_logger(__name__)
router = APIRouter()

async def verify_internal_secret(x_internal_token: str = Header(..., alias="X-Internal-Token")):
    """验证内部调用秘钥"""
    if not app_settings.TELEGRAM_STAFF_API_SECRET:
        # 如果未配置秘钥，则拒绝所有外部调用（仅允许本地通过主测试？不，通常直接报错）
        raise HTTPException(status_code=500, detail="Internal secret not configured")
    if x_internal_token != app_settings.TELEGRAM_STAFF_API_SECRET:
        raise HTTPException(status_code=403, detail="Invalid internal token")
    return x_internal_token

class BotMessageLogRequest(BaseModel):
    tg_user_id: int
    direction: str
    content: str
    tg_username: Optional[str] = None
    tg_chat_id: Optional[int] = None
    message_type: str = "text"
    message_id: Optional[int] = None
    reply_to_message_id: Optional[int] = None
    extra_data: Optional[Dict[str, Any]] = None

class BotTicketCreate(BaseModel):
    tg_id: int
    ticket_type: str = "other"
    priority: str = "normal"
    category: Optional[str] = None
    title: str
    description: Optional[str] = None
    extra_data: Optional[Dict[str, Any]] = None

class BotTicketReply(BaseModel):
    tg_id: int
    content: str
    is_internal: bool = False

class BotAccountCreate(BaseModel):
    biz_type: str
    country_code: str
    sales_id: int
    default_price: float = 0.0
    account_name: Optional[str] = None

@router.get("/customer/info", dependencies=[Depends(verify_internal_secret)])
async def get_customer_info_internal(
    tg_id: int,
    db: AsyncSession = Depends(get_db)
):
    """根据 TG ID 获取客户账户信息"""
    try:
        query = select(Account).join(
            TelegramBinding, Account.id == TelegramBinding.account_id
        ).where(
            TelegramBinding.tg_id == tg_id,
            TelegramBinding.is_closed == False,
            Account.is_deleted == False
        )
        result = await db.execute(query)
        account = result.scalar_one_or_none()
        
        if not account:
            return {"success": False, "msg": "未找到绑定的有效账户"}
            
        return {
            "success": True,
            "account": {
                "id": account.id,
                "account_name": account.account_name,
                "api_key": account.api_key,
                "balance": float(account.balance or 0),
                "status": account.status,
            }
        }
    except Exception as e:
        logger.exception("获取客户信息失败: %s", e)
        return {"success": False, "msg": str(e)}


@router.get("/user/role", dependencies=[Depends(verify_internal_secret)])
async def get_user_role_internal(
    tg_id: int,
    db: AsyncSession = Depends(get_db)
):
    """根据 TG ID 获取用户角色"""
    try:
        # 1. 检查是否是管理员/内部员工
        admin_query = select(AdminUser).where(
            AdminUser.tg_id == tg_id,
            AdminUser.status == 'active'
        )
        admin_res = await db.execute(admin_query)
        admin = admin_res.scalar_one_or_none()
        if admin:
            return {"success": True, "role": admin.role}
            
        # 2. 检查是否是客户
        customer_query = select(Account).join(
            TelegramBinding, Account.id == TelegramBinding.account_id
        ).where(
            TelegramBinding.tg_id == tg_id,
            TelegramBinding.is_closed == False,
            Account.is_deleted == False
        )
        customer_res = await db.execute(customer_query)
        if customer_res.scalar_one_or_none():
            return {"success": True, "role": "customer"}
            
        return {"success": True, "role": "guest"}
    except Exception as e:
        logger.exception("获取用户角色失败: %s", e)
        return {"success": False, "msg": str(e)}


@router.post("/messages", dependencies=[Depends(verify_internal_secret)])
async def log_bot_message(
    request: BotMessageLogRequest,
    db: AsyncSession = Depends(get_db)
):
    """供内部 Bot 服务调用的消息留痕接口"""
    try:
        account_id = None
        account_name = None
        
        binding_query = select(TelegramBinding, Account).join(
            Account, TelegramBinding.account_id == Account.id
        ).where(
            TelegramBinding.tg_id == request.tg_user_id
        )
        result = await db.execute(binding_query)
        row = result.first()
        if row:
            binding, account = row
            account_id = account.id
            account_name = account.account_name

        msg = TelegramMessage(
            tg_user_id=str(request.tg_user_id),
            tg_username=request.tg_username,
            tg_chat_id=str(request.tg_chat_id) if request.tg_chat_id else None,
            direction=request.direction,
            message_type=request.message_type,
            content=request.content,
            account_id=account_id,
            account_name=account_name,
            message_id=str(request.message_id) if request.message_id else None,
            reply_to_message_id=str(request.reply_to_message_id) if request.reply_to_message_id else None,
            extra_data=json.dumps(request.extra_data) if request.extra_data else None,
            created_at=datetime.now()
        )
        db.add(msg)
        await db.commit()
        return {"success": True}
    except Exception as e:
        logger.error(f"处理内部Bot日记请求失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.get("/settings", dependencies=[Depends(verify_internal_secret)])
async def get_bot_settings(db: AsyncSession = Depends(get_db)):
    """获取 Bot 相关系统配置"""
    try:
        keys = [
            'telegram_bot_token',
            'telegram_admin_group_id',
            'telegram_tech_group_id',
            'telegram_billing_group_id'
        ]
        result = await db.execute(
            select(SystemConfig).where(SystemConfig.config_key.in_(keys))
        )
        configs = {c.config_key: c.config_value for c in result.scalars().all()}
        return {
            "token": configs.get('telegram_bot_token'),
            "admin_group_id": configs.get('telegram_admin_group_id'),
            "tech_group_id": configs.get('telegram_tech_group_id'),
            "billing_group_id": configs.get('telegram_billing_group_id')
        }
    except Exception as e:
        logger.error(f"获取Bot设置失败: {e}")
        raise HTTPException(status_code=500)

@router.get("/verify-user/{tg_id}", dependencies=[Depends(verify_internal_secret)])
async def verify_bot_user(tg_id: int, db: AsyncSession = Depends(get_db)):
    """校验 TG 用户身份并返回其关联的账户信息"""
    try:
        # 1. 检查是否是管理员/销售
        admin = (await db.execute(
            select(AdminUser).where(AdminUser.tg_id == tg_id, AdminUser.status == 'active')
        )).scalar_one_or_none()
        
        if admin:
            res_data = {
                "role": admin.role,
                "user_id": admin.id,
                "real_name": admin.real_name or admin.username,
                "username": admin.username,
                "is_admin": True,
                "status": admin.status
            }
            # 如果是销售/财务，计算本月业绩
            if admin.role in ['sales', 'finance', 'super_admin']:
                from datetime import date
                from sqlalchemy import text
                rate = float(admin.commission_rate or 0) / 100.0
                first_day = date.today().replace(day=1).strftime('%Y-%m-%d 00:00:00')
                
                sql = text("""
                    SELECT SUM(l.profit * l.message_count) 
                    FROM sms_logs l
                    JOIN accounts acc ON l.account_id = acc.id
                    JOIN channels ch ON l.channel_id = ch.id
                    WHERE acc.sales_id = :sales_id 
                      AND l.submit_time >= :start_time
                      AND l.status = 'delivered'
                      AND ch.protocol != 'VIRTUAL'
                """)
                try:
                    res_comm = await db.execute(sql, {"sales_id": admin.id, "start_time": first_day})
                    total_profit = float(res_comm.scalar() or 0)
                    res_data["monthly_profit"] = total_profit
                    res_data["monthly_commission"] = total_profit * rate
                except Exception as e:
                    logger.error(f"Backend failed to calc commission for admin_id={admin.id}: {e}")
            return res_data

        # 2. 检查是否是客户绑定
        binding_query = select(TelegramBinding, Account).join(
            Account, TelegramBinding.account_id == Account.id
        ).where(
            TelegramBinding.tg_id == tg_id,
            Account.status != "closed",
            Account.is_deleted == False
        )
        result = await db.execute(binding_query)
        row = result.first()
        if row:
            binding, account = row
            return {
                "role": "customer",
                "account_id": account.id,
                "account_name": account.account_name,
                "balance": float(account.balance),
                "currency": account.currency,
                "status": account.status,
                "tg_id": account.tg_id,
                "tg_username": account.tg_username,
                "created_at": account.created_at.isoformat() if account.created_at else None,
                "valid": True,
                "is_admin": False
            }

        return {"role": "guest", "valid": False, "is_admin": False}
    except Exception as e:
        logger.error(f"校验Bot用户失败: {e}")
        raise HTTPException(status_code=500)

@router.get("/templates", dependencies=[Depends(verify_internal_secret)])
async def get_bot_templates(
    biz_type: str,
    country_code: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """获取可用模板列表"""
    try:
        query = select(AccountTemplate).where(
            AccountTemplate.business_type == biz_type,
            AccountTemplate.status == "active"
        )
        if country_code:
            if country_code == '*':
                query = query.where(AccountTemplate.country_code == '*')
            else:
                query = query.where(AccountTemplate.country_code.ilike(country_code))
        
        result = await db.execute(query.order_by(AccountTemplate.template_name))
        templates = result.scalars().all()
        
        return [
            {
                "id": t.id,
                "name": t.template_name,
                "code": t.template_code,
                "price": float(t.default_price) if t.default_price else 0,
                "country_code": t.country_code,
                "pricing_rules": t.pricing_rules
            } for t in templates
        ]
    except Exception as e:
        logger.error(f"获取模板列表失败: {e}")
        raise HTTPException(status_code=500)

@router.post("/tickets", dependencies=[Depends(verify_internal_secret)])
async def create_bot_ticket(
    request: BotTicketCreate,
    db: AsyncSession = Depends(get_db)
):
    """供 Bot 调用的工单创建接口"""
    try:
        # 获取关联账户
        binding = (await db.execute(
            select(TelegramBinding).where(TelegramBinding.tg_id == request.tg_id)
        )).scalar_one_or_none()
        
        account_id = binding.account_id if binding else None
        
        ticket_no = f"TK{datetime.now().strftime('%Y%m%d%H%M%S')}{str(uuid.uuid4().hex)[:6].upper()}"
        
        ticket = Ticket(
            ticket_no=ticket_no,
            account_id=account_id,
            tg_user_id=str(request.tg_id),
            ticket_type=request.ticket_type,
            priority=request.priority,
            category=request.category,
            title=request.title,
            description=request.description,
            status='open',
            created_by_type='admin' if account_id is None else 'account',
            created_by_id=request.tg_id if account_id is None else account_id,
            extra_data=request.extra_data
        )
        db.add(ticket)
        await db.commit()
        await db.refresh(ticket)
        
        return {
            "success": True, 
            "ticket_id": ticket.id, 
            "ticket_no": ticket.ticket_no
        }
    except Exception as e:
        logger.error(f"Bot创建工单失败: {e}")
        raise HTTPException(status_code=500)

@router.get("/tickets", dependencies=[Depends(verify_internal_secret)])
async def get_bot_tickets(
    status: Optional[str] = None,
    tg_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """获取工单列表"""
    try:
        query = select(Ticket)
        if status:
            query = query.where(Ticket.status == status)
        if tg_id:
            query = query.where(Ticket.tg_user_id == str(tg_id))
            
        result = await db.execute(query.order_by(Ticket.created_at.desc()).limit(50))
        tickets = result.scalars().all()
        
        return [
            {
                "id": t.id,
                "ticket_no": t.ticket_no,
                "title": t.title,
                "status": t.status,
                "created_at": t.created_at
            } for t in tickets
        ]
    except Exception as e:
        logger.error(f"获取工单列表失败: {e}")
        raise HTTPException(status_code=500)

@router.get("/tickets/{ticket_id}", dependencies=[Depends(verify_internal_secret)])
async def get_bot_ticket_detail(ticket_id: int, db: AsyncSession = Depends(get_db)):
    """获取工单详情"""
    try:
        from sqlalchemy.orm import selectinload
        result = await db.execute(
            select(Ticket).options(selectinload(Ticket.replies)).where(Ticket.id == ticket_id)
        )
        ticket = result.scalar_one_or_none()
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        
        return {
            "id": ticket.id,
            "ticket_no": ticket.ticket_no,
            "status": ticket.status,
            "title": ticket.title,
            "description": ticket.description,
            "replies": [
                {
                    "content": r.content,
                    "reply_by_name": r.reply_by_name,
                    "created_at": r.created_at
                } for r in ticket.replies if not r.is_internal
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取工单详情失败: {e}")
        raise HTTPException(status_code=500)

@router.post("/tickets/{ticket_id}/reply", dependencies=[Depends(verify_internal_secret)])
async def reply_bot_ticket(
    ticket_id: int,
    request: BotTicketReply,
    db: AsyncSession = Depends(get_db)
):
    """工单回复"""
    try:
        ticket = await db.get(Ticket, ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
            
        admin = (await db.execute(
            select(AdminUser).where(AdminUser.tg_id == request.tg_id)
        )).scalar_one_or_none()
        
        reply_by_type = 'admin' if admin else 'account'
        reply_by_name = admin.username if admin else "Customer"
        
        reply = TicketReply(
            ticket_id=ticket_id,
            reply_by_type=reply_by_type,
            reply_by_id=request.tg_id,
            reply_by_name=reply_by_name,
            content=request.content,
            is_internal=request.is_internal,
            source='telegram'
        )
        db.add(reply)
        
        if not request.is_internal and ticket.status == 'pending_user':
            ticket.status = 'in_progress'
            
        await db.commit()
        return {"success": True}
    except Exception as e:
        logger.error(f"回复工单失败: {e}")
        raise HTTPException(status_code=500)

@router.patch("/tickets/{ticket_id}/take")
async def take_bot_ticket(
    ticket_id: int,
    request: Dict[str, Any], # { "tg_id": ... }
    db: AsyncSession = Depends(get_db),
    dependencies=[Depends(verify_internal_secret)]
):
    """接单：指派给特定管理员"""
    try:
        from app.modules.common.admin_user import AdminUser
        from app.modules.common.ticket import Ticket
        
        tg_id = request.get("tg_id")
        # 查找接单管理员
        res = await db.execute(select(AdminUser).where(AdminUser.tg_id == tg_id, AdminUser.status == 'active'))
        admin = res.scalar_one_or_none()
        if not admin:
            raise HTTPException(status_code=403, detail="Not authorized")
            
        ticket = await db.get(Ticket, ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="Not found")
            
        if ticket.status not in ('open', 'assigned'):
            return {"success": False, "message": f"工单状态已变更: {ticket.status}", "status": ticket.status}
            
        ticket.status = 'in_progress'
        ticket.assigned_to = admin.id
        ticket.assigned_at = datetime.now()
        
        await db.commit()
        return {
            "success": True, 
            "ticket_no": ticket.ticket_no, 
            "admin_name": admin.real_name or admin.username
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"接单失败: {e}")
        raise HTTPException(status_code=500)

def _parse_bot_supplier_creds(text: str) -> dict:
    creds = {}
    url_match = re.search(r'https?://[^\s]+', text)
    if url_match:
        creds['system_url'] = url_match.group(0).rstrip('/')

    kv_patterns = {
        'client_name': r'客户名[：:]\s*(.+)',
        'username': r'用户名[：:]\s*(.+)',
        'password': r'密码[：:]\s*(.+)',
        'agent_range': r'坐席号[：:]\s*(.+)',
        'agent_password': r'口令[：:]\s*(.+)',
        'domain': r'域名[：:]\s*(.+)',
        'dial_rule': r'送号规则[：:]\s*(.+)',
    }
    for key, pattern in kv_patterns.items():
        match = re.search(pattern, text)
        if match:
            val = match.group(1).strip()
            if val:
                creds[key] = val

    sections = {}
    current_section = None
    for line in text.split('\n'):
        line_s = line.strip().strip('-')
        if not line_s: continue
        if '企业客户登录' in line_s:
            current_section = 'enterprise_login'
            sections[current_section] = {}
        elif '坐席注册' in line_s:
            current_section = 'agent_register'
            sections[current_section] = {}
        elif '坐席登录' in line_s:
            current_section = 'agent_login'
            sections[current_section] = {}
        elif current_section and ('：' in line_s or ':' in line_s):
            sep = '：' if '：' in line_s else ':'
            parts = line_s.split(sep, 1)
            if len(parts) == 2:
                k, v = parts[0].strip(), parts[1].strip()
                if k and v: sections[current_section][k] = v
    if sections: creds['sections'] = sections
    return creds

@router.post("/tickets/finalize")
async def finalize_bot_ticket(
    request: Dict[str, Any], # { "ticket_id": ..., "ticket_no": ..., "reply_text": ..., "tg_id": ... }
    db: AsyncSession = Depends(get_db),
    dependencies=[Depends(verify_internal_secret)]
):
    """完结工单：解析回复凭据，同步更新账户"""
    try:
        from app.modules.common.ticket import Ticket, TicketReply
        from app.modules.common.admin_user import AdminUser
        from app.modules.common.account import Account
        
        reply_text = request.get("reply_text", "")
        tg_id = request.get("tg_id")
        ticket_id = request.get("ticket_id")
        ticket_no = request.get("ticket_no")
        
        if ticket_id:
            ticket = await db.get(Ticket, ticket_id)
        elif ticket_no:
            res = await db.execute(select(Ticket).where(Ticket.ticket_no == ticket_no))
            ticket = res.scalar_one_or_none()
        else:
            raise HTTPException(status_code=400, detail="ticket_id or ticket_no required")

        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        
        if ticket.status in ('resolved', 'closed', 'cancelled'):
            return {"success": False, "message": "Ticket already finalized"}
            
        # 查找接单/完结管理员
        res = await db.execute(select(AdminUser).where(AdminUser.tg_id == tg_id, AdminUser.status == 'active'))
        admin = res.scalar_one_or_none()
        admin_id = admin.id if admin else None
        admin_name = admin.real_name or admin.username if admin else f"TG:{tg_id}"
        
        # 解析凭据
        creds = _parse_bot_supplier_creds(reply_text)
        creds['raw_reply'] = reply_text.strip()
        
        # 1. 记录回复
        reply_record = TicketReply(
            ticket_id=ticket.id,
            reply_by_type='admin',
            reply_by_id=admin_id,
            reply_by_name=admin_name,
            content=reply_text,
            is_internal=False,
            is_solution=True,
            source='telegram',
        )
        db.add(reply_record)
        
        # 2. 更新工单状态
        ticket.status = 'resolved'
        ticket.resolved_at = datetime.now()
        ticket.resolved_by = admin_id
        ticket.resolution = reply_text
        
        # 3. 账户处理
        extra = ticket.extra_data or {}
        biz_type = extra.get('opening_type', '')
        account_id = extra.get('account_id')
        cc = extra.get('country_code', '')
        
        display_name = ""
        if biz_type == 'voice':
            # 语音：可能需要新建账户（如果之前 deferred）
            okcc_name = creds.get('client_name')
            if not okcc_name:
                ent = creds.get('sections', {}).get('enterprise_login', {})
                okcc_name = ent.get('客户名') or ent.get('客户名')
            
            acct_name = okcc_name or f"VOICE_{cc}_{secrets.token_hex(3).upper()}"
            
            if account_id:
                account = await db.get(Account, account_id)
                if account:
                    account.account_name = acct_name
                    account.supplier_credentials = creds
                    account.supplier_url = creds.get('system_url', '')
            else:
                # 新建
                selected_lines = extra.get('selected_lines', [])
                sell_price = selected_lines[0].get('sell_price', 0) if selected_lines else 0
                
                account = Account(
                    account_name=acct_name,
                    sales_id=extra.get('sales_id'),
                    status='active',
                    balance=0,
                    rate_limit=1000,
                    business_type='voice',
                    services='voice',
                    country_code=cc,
                    unit_price=sell_price,
                    supplier_url=creds.get('system_url', ''),
                    supplier_credentials=creds,
                )
                db.add(account)
                await db.flush()
                extra['account_id'] = account.id
                extra['account_name'] = acct_name
                ticket.extra_data = extra
            display_name = acct_name
        else:
            # 数据/其他：更新凭据
            if account_id:
                account = await db.get(Account, account_id)
                if account:
                    account.supplier_credentials = creds
                    account.supplier_url = creds.get('system_url', '')
                    display_name = account.account_name
            else:
                display_name = extra.get('account_name', '')

        await db.commit()
        return {
            "success": True,
            "ticket_no": ticket.ticket_no,
            "display_name": display_name,
            "creds": creds,
            "sales_tg_id": extra.get('sales_tg_id'),
            "biz_type": biz_type,
            "country_name": extra.get('country_name'),
            "template_name": extra.get('template_name'),
            "selected_lines": extra.get('selected_lines')
        }
        
    except Exception as e:
        logger.error(f"完结工单失败: {e}")
        raise HTTPException(status_code=500)

@router.post("/admins/bind", dependencies=[Depends(verify_internal_secret)])
async def bind_admin_internal(data: dict, db: AsyncSession = Depends(get_db)):
    """绑定管理员/员工"""
    try:
        from app.modules.common.admin_user import AdminUser
        username = data.get("username")
        password = data.get("password")
        tg_id = data.get("tg_id")

        result = await db.execute(select(AdminUser).where(AdminUser.username == username, AdminUser.status == 'active'))
        admin = result.scalar_one_or_none()

        if not admin:
            return {"success": False, "msg": "用户不存在或已禁用"}
        
        # 简单校验密码 (实际项目中应使用 hash 校验)
        # 这里为了演示和兼容现有逻辑，假设如果是明文/已存在的逻辑
        # 严格说应该 import pwd_context
        from app.core.security import verify_password
        if not verify_password(password, admin.password_hash):
             return {"success": False, "msg": "密码错误"}
        
        admin.tg_id = tg_id
        await db.commit()
        return {"success": True, "admin": {"id": admin.id, "username": admin.username, "role": admin.role}}
    except Exception as e:
        logger.error(f"绑定管理员失败: {e}", exc_info=True)
        return {"success": False, "msg": str(e)}

@router.get("/admins/{tg_id}")
async def get_bot_admin(
    tg_id: int,
    db: AsyncSession = Depends(get_db),
    dependencies=[Depends(verify_internal_secret)]
):
    """获取管理员信息"""
    try:
        from app.modules.common.admin_user import AdminUser
        res = await db.execute(select(AdminUser).where(AdminUser.tg_id == tg_id, AdminUser.status == 'active'))
        admin = res.scalar_one_or_none()
        if not admin:
            return {"success": False, "message": "Admin not found"}
        return {
            "success": True,
            "admin": {
                "id": admin.id,
                "username": admin.username,
                "real_name": admin.real_name,
                "tg_id": admin.tg_id
            }
        }
    except Exception as e:
        logger.error(f"获取管理员失败: {e}")
        raise HTTPException(status_code=500)

@router.post("/bulk/validate", dependencies=[Depends(verify_internal_secret)])
async def bulk_validate_internal(
    request: Dict[str, Any],
    db: AsyncSession = Depends(get_db)
):
    """批量短信预审与估价"""
    try:
        from app.utils.validator import Validator
        from app.core.pricing import PricingEngine
        
        account_id = request.get("account_id")
        content = request.get("content")
        phones = request.get("phones", [])
        
        # 1. 验证文案
        is_valid, err, info = Validator.validate_content(content)
        if not is_valid:
            return {"success": False, "msg": f"文案违规: {err}"}
            
        parts = info['parts']
        
        # 2. 估算价格 (取参考单价)
        pricing_engine = PricingEngine(db)
        # 简化：取该账户 CN 单价作为参考，或循环估算（如果号码不多）
        # 这里为了演示，取 CN 步进
        price_info = await pricing_engine.get_price(1, 'CN', account_id=account_id)
        unit_price = price_info['price'] if price_info else 0.05
        
        total_cost = len(phones) * parts * unit_price
        
        return {
            "success": True,
            "parts": parts,
            "encoding": info['encoding'],
            "length": info['length'],
            "unit_price": unit_price,
            "total_cost": total_cost,
            "valid_count": len(phones)
        }
    except Exception as e:
        logger.exception("批量预审失败: %s", e)
        return {"success": False, "msg": str(e)}

@router.post("/mass-tasks", dependencies=[Depends(verify_internal_secret)])
async def create_mass_task_internal(
    request: Dict[str, Any],
    db: AsyncSession = Depends(get_db)
):
    """创建群发任务 (SmsBatch)"""
    try:
        from app.modules.sms.sms_batch import SmsBatch
        from app.modules.common.account import Account
        from decimal import Decimal
        
        account_id = request.get("account_id")
        total_cost = request.get("total_cost", 0)
        
        # 扣费逻辑在后端更安全
        account = await db.get(Account, account_id)
        if not account or float(account.balance) < float(total_cost):
            return {"success": False, "message": "余额不足"}
            
        account.balance = Decimal(str(float(account.balance) - float(total_cost)))
        
        batch = SmsBatch(
            batch_id=f"MASS{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:6].upper()}",
            account_id=account_id,
            message=request.get("content"),
            sender_id=request.get("sender_id"),
            total_count=request.get("total_count", 0),
            phone_numbers=request.get("phone_numbers", []),
            status='pending',
            created_at=datetime.now(),
            extra_data=request.get("extra_data", {})
        )
        db.add(batch)
        await db.commit()
        await db.refresh(batch)
        return {"success": True, "batch_id": batch.batch_id, "id": batch.id}
    except Exception as e:
        logger.error(f"创建批量任务失败: {e}")
        return {"success": False, "msg": str(e)}

@router.get("/data-pool/stats")
async def get_data_pool_stats(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    dependencies=[Depends(verify_internal_secret)]
):
    """获取数据池国家统计"""
    try:
        from app.modules.data.models import DataNumber
        from sqlalchemy import func
        result = await db.execute(
            select(DataNumber.country_code, func.count(DataNumber.id).label('count'))
            .where(
                DataNumber.owner_account_id == account_id,
                DataNumber.status == 'available'
            )
            .group_by(DataNumber.country_code)
        )
        rows = result.all()
        return {
            "success": True,
            "countries": [{"country_code": r[0], "count": r[1]} for r in rows]
        }
    except Exception as e:
        logger.error(f"获取数据池统计失败: {e}")
        raise HTTPException(status_code=500)

@router.get("/data-pool/count")
async def get_data_pool_count(
    account_id: int,
    country_code: str,
    db: AsyncSession = Depends(get_db),
    dependencies=[Depends(verify_internal_secret)]
):
    """获取指定国家可用数量"""
    try:
        from app.modules.data.models import DataNumber
        from sqlalchemy import func
        count = await db.scalar(
            select(func.count(DataNumber.id)).where(
                DataNumber.owner_account_id == account_id,
                DataNumber.country_code == country_code,
                DataNumber.status == 'available'
            )
        )
        return {"success": True, "count": count or 0}
    except Exception as e:
        logger.error(f"获取国家计数失败: {e}")
        raise HTTPException(status_code=500)

@router.get("/task-categories")
async def get_task_categories(
    db: AsyncSession = Depends(get_db),
    dependencies=[Depends(verify_internal_secret)]
):
    """获取任务分类 (AccountTemplate)"""
    try:
        from app.modules.common.account_template import AccountTemplate
        result = await db.execute(select(AccountTemplate).where(AccountTemplate.status == 'active'))
        templates = result.scalars().all()
        return {
            "success": True, 
            "categories": [{"id": t.id, "name": t.name, "biz_type": t.biz_type} for t in templates]
        }
    except Exception as e:
        logger.error(f"获取分类失败: {e}")
        raise HTTPException(status_code=500)

@router.get("/sending-stats")
async def get_sending_stats(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    dependencies=[Depends(verify_internal_secret)]
):
    """获取发送统计 (今日发送量等)"""
    try:
        from app.modules.sms.sms_log import SMSLog
        from sqlalchemy import func
        from datetime import date, datetime, time
        
        today_start = datetime.combine(date.today(), time.min)
        
        # 今日已发送
        today_count = await db.scalar(
            select(func.count(SMSLog.id)).where(
                SMSLog.account_id == account_id,
                SMSLog.submit_time >= today_start
            )
        )
        # 累计已发送
        total_count = await db.scalar(
            select(func.count(SMSLog.id)).where(SMSLog.account_id == account_id)
        )
        
        return {
            "success": True,
            "today_sent": today_count or 0,
            "total_sent": total_count or 0
        }
    except Exception as e:
        logger.error(f"获取统计失败: {e}")
        raise HTTPException(status_code=500)

@router.post("/auth/verify")
async def create_bot_ticket(
    request: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    dependencies=[Depends(verify_internal_secret)]
):
    """创建工单"""
    try:
        from app.modules.common.ticket import Ticket
        
        ticket = Ticket(
            ticket_no=request.get("ticket_no"),
            account_id=request.get("account_id"),
            tg_user_id=str(request.get("tg_user_id")),
            ticket_type=request.get("ticket_type"),
            priority=request.get("priority", "normal"),
            title=request.get("title"),
            description=request.get("description"),
            status='open',
            created_by_type=request.get("created_by_type"),
            created_by_id=request.get("created_by_id")
        )
        db.add(ticket)
        await db.commit()
        await db.refresh(ticket)
        return {"success": True, "ticket_id": ticket.id, "ticket_no": ticket.ticket_no}
    except Exception as e:
        logger.error(f"创建工单失败: {e}")
        raise HTTPException(status_code=500)

@router.get("/tickets")
async def get_bot_tickets(
    account_id: int = None,
    admin_id: int = None,
    ticket_type: str = None,
    review_status: str = None,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    dependencies=[Depends(verify_internal_secret)]
):
    """获取工单列表"""
    try:
        from app.modules.common.ticket import Ticket
        query = select(Ticket).order_by(Ticket.created_at.desc())
        
        if account_id:
            query = query.where(Ticket.account_id == account_id)
        if admin_id:
            query = query.where((Ticket.assigned_to == admin_id) | (Ticket.created_by_id == admin_id))
            
        res = await db.execute(query)
        tickets = res.scalars().all()
        return {
            "success": True, 
            "tickets": [
                {
                   "id": t.id,
                   "ticket_no": t.ticket_no,
                   "title": t.title,
                   "status": t.status,
                   "created_at": t.created_at.isoformat() if t.created_at else None
                } for t in tickets
            ]
        }
    except Exception as e:
        logger.error(f"查询工单列表失败: {e}")
        raise HTTPException(status_code=500)

@router.get("/tickets/{ticket_no}")
async def get_bot_ticket_detail(
    ticket_no: str,
    account_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    dependencies=[Depends(verify_internal_secret)]
):
    """获取工单详情"""
    try:
        from app.modules.common.ticket import Ticket, TicketReply
        query = select(Ticket).where(Ticket.ticket_no == ticket_no)
        if account_id:
            query = query.where(Ticket.account_id == account_id)
            
        res = await db.execute(query)
        ticket = res.scalar_one_or_none()
        if not ticket:
            return {"success": False, "message": "Ticket not found"}
            
        replies_res = await db.execute(
            select(TicketReply).where(TicketReply.ticket_id == ticket.id, TicketReply.is_internal == False)
                               .order_by(TicketReply.created_at.asc())
        )
        replies = replies_res.scalars().all()
        
        return {
            "success": True,
            "ticket": {
                "id": ticket.id,
                "ticket_no": ticket.ticket_no,
                "ticket_type": ticket.ticket_type,
                "title": ticket.title,
                "status": ticket.status,
                "description": ticket.description,
                "resolution": ticket.resolution,
                "assigned_to": ticket.assigned_to
            },
            "replies": [
                {
                    "reply_by_type": r.reply_by_type,
                    "content": r.content,
                    "created_at": r.created_at.isoformat() if r.created_at else None
                } for r in replies
            ]
        }
    except Exception as e:
        logger.error(f"获取详情失败: {e}")
        raise HTTPException(status_code=500)

@router.post("/tickets/{ticket_id}/action")
async def ticket_action_internal(
    ticket_id: int,
    request: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    dependencies=[Depends(verify_internal_secret)]
):
    """实施接单或解决动作"""
    try:
        from app.modules.common.ticket import Ticket
        action = request.get("action")
        admin_id = request.get("admin_id")
        
        ticket = await db.get(Ticket, ticket_id)
        if not ticket:
            return {"success": False, "message": "Ticket not found"}
            
        if action == "take":
            ticket.status = 'assigned'
            ticket.assigned_to = admin_id
            ticket.assigned_at = datetime.now()
        elif action == "resolve":
            ticket.status = 'resolved'
            ticket.resolved_at = datetime.now()
            ticket.resolved_by = admin_id
            ticket.resolution = request.get("resolution", "Resolved via Bot")
            
        await db.commit()
        return {"success": True, "ticket_no": ticket.ticket_no}
    except Exception as e:
        logger.error(f"操作工单失败: {e}")
        raise HTTPException(status_code=500)

@router.get("/sms-log")
async def get_bot_sms_history(
    account_id: int,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    dependencies=[Depends(verify_internal_secret)]
):
    """获取短信历史"""
    try:
        from app.modules.sms.sms_log import SMSLog
        res = await db.execute(
            select(SMSLog).where(SMSLog.account_id == account_id)
                          .order_by(SMSLog.submit_time.desc())
                          .limit(limit)
        )
        logs = res.scalars().all()
        return {
            "success": True,
            "logs": [
                {
                    "status": log.status,
                    "submit_time": log.submit_time.isoformat() if log.submit_time else None,
                    "phone_number": log.phone_number,
                    "message": log.message
                } for log in logs
            ]
        }
    except Exception as e:
        logger.error(f"获取历史失败: {e}")
        raise HTTPException(status_code=500)

@router.post("/accounts", dependencies=[Depends(verify_internal_secret)])
async def create_bot_account(
    request: BotAccountCreate,
    db: AsyncSession = Depends(get_db)
):
    """处理 Bot 开户请求"""
    try:
        from app.core.auth import AuthService
        from app.modules.common.account import Account
        
        # 简化逻辑：生成随机密码和 API Key
        import secrets
        import string
        plain_pwd = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
        hashed_pwd = AuthService.hash_password(plain_pwd)
        api_key = f"ak_{str(uuid.uuid4().hex)}"
        
        account_name = request.account_name or f"BotClient_{str(uuid.uuid4().hex)[:6]}"
        
        account = Account(
            account_name=account_name,
            password_hash=hashed_pwd,
            api_key=api_key,
            role='customer',
            status='active',
            balance=0,
            currency='USD',
            sales_id=request.sales_id,
            business_type=request.biz_type,
            services=request.biz_type,
            country_code=request.country_code,
            unit_price=getattr(request, 'default_price', 0),
            created_at=datetime.now()
        )
        db.add(account)
        await db.flush() # 获取 ID
        
        if request.biz_type == 'data':
            try:
                from app.modules.data.data_account import DataAccount
                da = DataAccount(
                    account_id=account.id,
                    country_code=request.country_code,
                    balance=0,
                    status='active'
                )
                db.add(da)
            except Exception as de:
                logger.warning(f"Failed to create DataAccount sub-record: {de}")
        await db.commit()
        await db.refresh(account)
        
        return {
            "success": True,
            "account_id": account.id,
            "account_name": account.account_name,
            "plain_password": plain_pwd,
            "api_key": api_key
        }
    except Exception as e:
        logger.error(f"Bot开户失败: {e}")
        raise HTTPException(status_code=500)

@router.get("/accounts/{account_id}/test-countries")
async def get_bot_account_test_countries(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    dependencies=[Depends(verify_internal_secret)]
):
    """获取账户关联通道的测试国家（不泄露敏感信息）"""
    try:
        from app.modules.common.account import AccountChannel
        # from app.modules.sms.channel_relations import ChannelCountry # 假设表名对的
        from sqlalchemy import text
        
        ac_result = await db.execute(
            select(AccountChannel.channel_id)
            .where(AccountChannel.account_id == account_id)
            .order_by(AccountChannel.priority.desc())
        )
        channel_ids = [r[0] for r in ac_result.all()]
        if not channel_ids:
            return {"countries": "-"}

        placeholders = ",".join([str(int(cid)) for cid in channel_ids])
        sql = text(f"""
            SELECT DISTINCT cc.country_code, cc.country_name
            FROM channel_countries cc
            WHERE cc.channel_id IN ({placeholders})
              AND cc.status = 'active'
            ORDER BY cc.channel_id
            LIMIT 10
        """)
        raw = await db.execute(sql)
        rows = raw.all()
        if not rows:
            return {"countries": "-"}
            
        labels = [f"{r[1]}({r[0]})" for r in rows]
        return {"countries": ", ".join(labels)}
    except Exception as e:
        logger.error(f"获取测试国家失败: {e}")
        return {"countries": "Error"}

@router.get("/sms-approvals")
async def get_bot_sms_approvals(db: AsyncSession = Depends(get_db), dependencies=[Depends(verify_internal_secret)]):
    """获取待审核的短信列表"""
    try:
        from sqlalchemy.orm import joinedload
        result = await db.execute(
            select(SmsContentApproval)
            .options(joinedload(SmsContentApproval.account))
            .where(SmsContentApproval.status == 'pending')
            .order_by(SmsContentApproval.created_at.desc())
        )
        approvals = result.scalars().all()
        return [
            {
                "id": a.id,
                "account_name": a.account.account_name if a.account else "Unknown",
                "content": a.content,
                "created_at": a.created_at
            } for a in approvals
        ]
    except Exception as e:
        logger.error(f"获取审核列表失败: {e}")
        raise HTTPException(status_code=500)

@router.get("/sms-approvals/{approval_id}")
async def get_bot_sms_approval_detail(
    approval_id: int,
    db: AsyncSession = Depends(get_db),
    dependencies=[Depends(verify_internal_secret)]
):
    """获取审核详情"""
    try:
        from sqlalchemy.orm import joinedload
        result = await db.execute(
            select(SmsContentApproval)
            .options(joinedload(SmsContentApproval.account))
            .where(SmsContentApproval.id == approval_id)
        )
        a = result.scalar_one_or_none()
        if not a:
            raise HTTPException(status_code=404, detail="Not found")
            
        return {
            "id": a.id,
            "account_id": a.account_id,
            "account_name": a.account.account_name if a.account else "Unknown",
            "api_key": a.account.api_key if a.account else None,
            "content": a.content,
            "status": a.status,
            "phone_number": a.phone_number,
            "tg_user_id": a.tg_user_id,
            "message_id": a.message_id,
            "created_at": a.created_at
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取审核详情失败: {e}")
        raise HTTPException(status_code=500)

@router.post("/sms-approvals/{approval_id}/action")
async def action_bot_sms_approval(
    approval_id: int,
    action: str, # 'approve' or 'reject'
    reason: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    dependencies=[Depends(verify_internal_secret)]
):
    """审核短信内容"""
    try:
        approval = await db.get(SmsContentApproval, approval_id)
        if not approval:
            raise HTTPException(status_code=404, detail="Not found")
        
        approval.status = 'approved' if action == 'approve' else 'rejected'
        approval.remark = reason
        approval.updated_at = datetime.now()
        
        # 同步更新关联的测试工单
        try:
            from app.modules.common.ticket import Ticket
            # 查找关联的 test 类型工单
            ticket_query = select(Ticket).where(
                Ticket.account_id == approval.account_id,
                Ticket.ticket_type == 'test',
                Ticket.status.in_(['open', 'assigned', 'in_progress'])
            ).order_by(Ticket.created_at.desc())
            
            result = await db.execute(ticket_query)
            tickets = result.scalars().all()
            
            for ticket in tickets:
                # 检查 extra_data 里的关联 ID 或者标题包含 approval_no
                ex = ticket.extra_data or {}
                linked = ex.get('sms_approval_id') == approval.id
                if not linked and approval.approval_no and ticket.title and approval.approval_no in ticket.title:
                    linked = True
                
                if linked:
                    now = datetime.now()
                    if action == 'approve':
                        ticket.review_status = 'approved'
                        ticket.reviewed_at = now
                        ticket.review_note = f"Bot审核通过 — {reason or 'Approved'}"
                        ticket.status = 'resolved'
                        ticket.resolved_at = now
                    else:
                        ticket.review_status = 'rejected'
                        ticket.reviewed_at = now
                        ticket.review_note = f"Bot审核拒绝 — {reason or 'Rejected'}"
                        ticket.status = 'closed'
                        ticket.closed_at = now
                    break # 只同步最近的一个匹配工单
        except Exception as te:
            logger.error(f"同步工单失败: {te}")
            
        await db.commit()
        return {"success": True}
    except Exception as e:
        logger.error(f"审核操作失败: {e}")
        raise HTTPException(status_code=500)

@router.get("/data-pool/public-stats", dependencies=[Depends(verify_internal_secret)])
async def get_public_data_stats(
    country_code: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """查询公海数据统计"""
    try:
        from app.modules.data.models import DataNumber
        from sqlalchemy import func
        query = select(
            DataNumber.country_code,
            func.count(DataNumber.id).label('count')
        ).where(
            DataNumber.status == 'available',
            DataNumber.owner_account_id.is_(None)
        )
        if country_code:
            query = query.where(DataNumber.country_code == country_code)
        
        result = await db.execute(query.group_by(DataNumber.country_code))
        rows = result.all()
        return {
            "success": True,
            "stats": [{"country_code": r[0], "count": r[1]} for r in rows]
        }
    except Exception as e:
        logger.error(f"获取公海统计失败: {e}")
        raise HTTPException(status_code=500)

@router.post("/data-pool/extract", dependencies=[Depends(verify_internal_secret)])
async def extract_data_to_private(
    request: Dict[str, Any], # {tg_id, country_code, count}
    db: AsyncSession = Depends(get_db)
):
    """提取公海数据到私有库"""
    try:
        from app.modules.data.models import DataNumber
        from app.modules.common.telegram_binding import TelegramBinding
        from sqlalchemy import func
        
        tg_id = request.get("tg_id")
        country_code = request.get("country_code", "").upper()
        count = int(request.get("count", 0))
        
        binding = (await db.execute(
            select(TelegramBinding).where(TelegramBinding.tg_id == tg_id)
        )).scalar_one_or_none()
        
        if not binding:
             return {"success": False, "message": "User not bound"}
             
        # 查询并锁定
        result = await db.execute(
            select(DataNumber).where(
                DataNumber.country_code == country_code,
                DataNumber.status == 'available',
                DataNumber.owner_account_id.is_(None)
            ).limit(count)
        )
        numbers = result.scalars().all()
        
        if len(numbers) < count:
            return {"success": False, "message": f"Insufficient data: {len(numbers)} available"}
            
        for num in numbers:
            num.owner_account_id = binding.account_id
            num.status = 'owned'
            
        await db.commit()
        return {"success": True, "count": len(numbers)}
    except Exception as e:
        logger.error(f"数据提取失败: {e}")
        raise HTTPException(status_code=500)

@router.post("/tickets/{ticket_no}/review", dependencies=[Depends(verify_internal_secret)])
async def review_ticket_internal(
    ticket_no: str,
    request: Dict[str, Any], # {action: approve|reject, user_name, note, chat_id}
    db: AsyncSession = Depends(get_db)
):
    """审核测试工单（供应商操作）"""
    try:
        from app.modules.common.ticket import Ticket
        action = request.get("action")
        user_name = request.get("user_name")
        note = request.get("note")
        chat_id = str(request.get("chat_id"))
        
        result = await db.execute(select(Ticket).where(Ticket.ticket_no == ticket_no))
        ticket = result.scalar_one_or_none()
        
        if not ticket:
             return {"success": False, "message": "Ticket not found"}
        
        if ticket.ticket_type != 'test':
             return {"success": False, "message": "Not a test ticket"}
             
        # 验证群主
        if ticket.forwarded_to_group and chat_id != ticket.forwarded_to_group:
             return {"success": False, "message": "Invalid group"}
             
        if action == 'approve':
            ticket.review_status = 'approved'
            ticket.reviewed_at = datetime.now()
            ticket.review_note = f"审批人: {user_name}\n" + (note or "通过")
            ticket.status = 'in_progress'
        else:
            ticket.review_status = 'rejected'
            ticket.reviewed_at = datetime.now()
            ticket.review_note = f"审批人: {user_name}\n拒绝原因: {note or '供应商拒绝'}"
            ticket.status = 'closed'
            ticket.close_reason = f"供应商拒绝: {note}"
            ticket.closed_at = datetime.now()
            
        await db.commit()
        return {"success": True, "ticket": {
            "ticket_no": ticket.ticket_no,
            "tg_user_id": ticket.tg_user_id,
            "test_phone": ticket.test_phone,
            "test_content": ticket.test_content
        }}
    except Exception as e:
        logger.error(f"审核工单失败: {e}")
        raise HTTPException(status_code=500)

@router.post("/tickets/{ticket_no}/test-result", dependencies=[Depends(verify_internal_secret)])
async def submit_test_result_internal(
    ticket_no: str,
    request: Dict[str, Any], # {success: bool, user_name, note}
    db: AsyncSession = Depends(get_db)
):
    """提交测试结果"""
    try:
        from app.modules.common.ticket import Ticket
        is_success = request.get("success")
        user_name = request.get("user_name")
        note = request.get("note")
        
        result = await db.execute(select(Ticket).where(Ticket.ticket_no == ticket_no))
        ticket = result.scalar_one_or_none()
        
        if not ticket:
             return {"success": False, "message": "Ticket not found"}
             
        ticket.status = 'resolved'
        ticket.resolved_at = datetime.now()
        ticket.resolution = f"测试{'成功' if is_success else '失败'}\n操作人: {user_name}\n" + (note or "")
        
        extra = ticket.extra_data or {}
        extra['test_result'] = {
            'success': is_success,
            'note': note,
            'operator': user_name,
            'time': datetime.now().isoformat()
        }
        ticket.extra_data = extra
        
        await db.commit()
        return {"success": True, "message": "测试结果已提交", "tg_user_id": ticket.tg_user_id, "test_phone": ticket.test_phone}
    except Exception as e:
        logger.error(f"提交测试结果失败: {e}")
        raise HTTPException(status_code=500)

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    tg_id: int
    tg_username: Optional[str] = None

@router.post("/register")
async def bot_register(req: RegisterRequest, db: AsyncSession = Depends(get_db), token: str = Depends(verify_internal_secret)):
    """处理来自 Bot 的新用户注册"""
    from app.modules.common.account import Account
    from app.modules.common.telegram_binding import TelegramBinding
    from app.modules.common.telegram_user import TelegramUser
    from app.modules.common.balance_log import BalanceLog
    import secrets
    
    # 检查邮箱
    result = await db.execute(select(Account).where(Account.email == req.email))
    if result.scalar_one_or_none():
        return {"success": False, "message": "邮箱已被注册"}
    
    # 检查绑定
    result = await db.execute(select(TelegramBinding).where(TelegramBinding.tg_id == req.tg_id))
    if result.scalar_one_or_none():
        return {"success": False, "message": "该 Telegram 账号已绑定其他账户"}
    
    try:
        from app.core.auth import AuthService
        api_key = f"ak_{secrets.token_hex(30)}"
        api_secret = secrets.token_hex(32)
        
        new_account = Account(
            account_name=req.name,
            email=req.email,
            password_hash=AuthService.hash_password(req.password),
            balance=1.0, # 赠送 1U
            currency="USD",
            status="active",
            api_key=api_key,
            api_secret=api_secret,
            tg_id=req.tg_id,
            tg_username=req.tg_username,
        )
        db.add(new_account)
        await db.flush()
        
        # 余额日志
        db.add(BalanceLog(
            account_id=new_account.id,
            change_type='deposit',
            amount=1.0,
            balance_after=1.0,
            description='新开短信账户赠送',
        ))
        
        # 绑定
        db.add(TelegramBinding(
            tg_id=req.tg_id,
            account_id=new_account.id,
            is_active=True,
        ))
        
        # TelegramUser (upsert)
        from sqlalchemy.dialects.mysql import insert as mysql_insert
        stmt = mysql_insert(TelegramUser).values(
            tg_id=req.tg_id,
            username=req.tg_username,
            account_id=new_account.id,
        ).on_duplicate_key_update(
            username=req.tg_username,
            account_id=new_account.id,
        )
        await db.execute(stmt)
        
        await db.commit()
        return {
            "success": True, 
            "account_id": new_account.id, 
            "api_key": api_key,
            "message": "注册成功"
        }
    except Exception as e:
        await db.rollback()
        logger.exception("Bot注册异常")
        return {"success": False, "message": f"服务器内部错误: {str(e)}"}
@router.get("/templates/{template_id}")
async def get_template_detail(template_id: int, db: AsyncSession = Depends(get_db), token: str = Depends(verify_internal_secret)):
    """获取账户模板详情"""
    from app.modules.common.account_template import AccountTemplate
    result = await db.execute(select(AccountTemplate).where(AccountTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return {
        "id": template.id,
        "template_name": template.template_name,
        "country_code": template.country_code,
        "default_price": float(template.default_price or 0),
        "biz_type": template.biz_type,
        "status": template.status
    }

class SmsApprovalReviewRequest(BaseModel):
    approval_id: int
    approved: bool
    admin_tg_id: Optional[int] = None

@router.post("/sms-approvals/review")
async def review_sms_approval(req: SmsApprovalReviewRequest, db: AsyncSession = Depends(get_db), token: str = Depends(verify_internal_secret)):
    """处理短信内容审核的回调逻辑"""
    from app.modules.common.sms_content_approval import SmsContentApproval
    from app.modules.common.account import Account
    
    result = await db.execute(
        select(SmsContentApproval, Account)
        .join(Account, SmsContentApproval.account_id == Account.id)
        .where(SmsContentApproval.id == req.approval_id)
    )
    row = result.first()
    if not row:
        return {"success": False, "message": "审核记录不存在"}
    
    approval, account = row
    # 这里可以增加复杂的审核通过逻辑，例如扣费、发送等。
    # 暂时简化实现，实际逻辑可能由 Bot 的 handle_sms_approval_callback 继续处理。
    # 或是由这里更新 DB 状态。
    approval.status = 'approved' if req.approved else 'rejected'
    approval.updated_at = datetime.now()
    await db.commit()
    
    return {
        "success": True, 
        "approval_id": approval.id, 
        "approved": req.approved,
        "account_id": account.id,
        "tg_id": account.tg_id
    }

@router.get("/sms-approvals/{approval_id}")
async def get_sms_approval_internal(approval_id: int, db: AsyncSession = Depends(get_db), token: str = Depends(verify_internal_secret)):
    """获取短信审核详情"""
    from app.modules.common.sms_content_approval import SmsContentApproval
    result = await db.execute(select(SmsContentApproval).where(SmsContentApproval.id == approval_id))
    approval = result.scalar_one_or_none()
    if not approval:
        raise HTTPException(status_code=404, detail="Sms approval not found")
    return {
        "id": approval.id,
        "account_id": approval.account_id,
        "content": approval.content,
        "phone_number": approval.phone_number,
        "status": approval.status,
        "tg_user_id": approval.tg_user_id
    }

class RechargeReviewRequest(BaseModel):
    approved: bool
    admin_tg_id: int

@router.post("/recharge-orders/{order_id}/review")
async def review_recharge_order(order_id: int, req: RechargeReviewRequest, db: AsyncSession = Depends(get_db), token: str = Depends(verify_internal_secret)):
    """处理充值审批逻辑"""
    from app.modules.common.recharge_order import RechargeOrder
    from app.modules.common.account import Account
    from app.modules.common.admin_user import AdminUser
    from app.modules.common.balance_log import BalanceLog
    
    # 1. 验证管理员
    result = await db.execute(select(AdminUser).where(AdminUser.tg_id == req.admin_tg_id, AdminUser.status == 'active'))
    admin = result.scalar_one_or_none()
    if not admin or admin.role not in ['super_admin', 'admin', 'finance']:
        return {"success": False, "message": "无审批权限"}
    
    # 2. 获取订单
    result = await db.execute(
        select(RechargeOrder, Account)
        .join(Account, RechargeOrder.account_id == Account.id)
        .where(RechargeOrder.id == order_id)
    )
    row = result.first()
    if not row:
        return {"success": False, "message": "订单不存在"}
    
    order, account = row
    if order.status != 'pending':
        return {"success": False, "message": f"订单状态为 {order.status}，无法审批"}
        
    if req.approved:
        order.status = 'completed'
        order.finance_audit_by = admin.id
        order.finance_audit_at = datetime.now()
        
        old_balance = float(account.balance)
        amount = float(order.amount)
        account.balance = old_balance + amount
        
        # 记录余额变动
        log = BalanceLog(
            account_id=account.id,
            change_amount=amount,
            old_balance=old_balance,
            new_balance=old_balance + amount,
            change_type='recharge',
            related_id=order.id,
            operator_id=admin.id,
            note=f"充值审批通过 (订单: {order.order_no})"
        )
        db.add(log)
    else:
        order.status = 'rejected'
        order.finance_audit_by = admin.id
        order.finance_audit_at = datetime.now()
        
    await db.commit()
    return {
        "success": True, 
        "order_no": order.order_no, 
        "amount": float(order.amount),
        "account_name": account.account_name,
        "new_balance": float(account.balance)
    }

class SmsFinalizeRequest(BaseModel):
    message_id: Optional[str] = None
    error: Optional[str] = None

@router.post("/sms-approvals/{approval_id}/finalize-send")
async def finalize_sms_send(approval_id: int, req: SmsFinalizeRequest, db: AsyncSession = Depends(get_db), token: str = Depends(verify_internal_secret)):
    """更新短信审核记录的发送状态"""
    from app.modules.common.sms_content_approval import SmsContentApproval
    result = await db.execute(select(SmsContentApproval).where(SmsContentApproval.id == approval_id))
    approval = result.scalar_one_or_none()
    if not approval:
        raise HTTPException(status_code=404, detail="Sms approval not found")
        
    if req.message_id:
        approval.message_id = req.message_id
        approval.send_error = None
    else:
        approval.send_error = req.error
        
    await db.commit()
    return {"success": True}

@router.get("/accounts/{account_id}/test-countries")
async def get_account_test_countries(account_id: int, db: AsyncSession = Depends(get_db), token: str = Depends(verify_internal_secret)):
    """获取账户可测试的国家列表"""
    from app.modules.common.account import AccountChannel
    # 简化实现，实际逻辑可参考 menu.py 中的 _get_test_countries_for_account
    ac_result = await db.execute(
        select(AccountChannel.channel_id)
        .where(AccountChannel.account_id == account_id)
        .order_by(AccountChannel.priority.desc())
    )
    channel_ids = [r[0] for r in ac_result.all()]
    if not channel_ids:
        return {"countries": "-"}

    # 为了简单，这里直接返回字符串
    from sqlalchemy import text
    placeholders = ",".join([str(int(cid)) for cid in channel_ids])
    sql = text(f"""
        SELECT DISTINCT cc.country_name
        FROM channel_countries cc
        WHERE cc.channel_id IN ({placeholders})
          AND cc.status = 'active'
        LIMIT 10
    """)
    raw = await db.execute(sql)
    rows = raw.all()
    if not rows:
        return {"countries": "-"}
    return {"countries": ", ".join([r[0] for r in rows])}

@router.get("/system-stats")
async def get_system_stats_internal(db: AsyncSession = Depends(get_db), token: str = Depends(verify_internal_secret)):
    """系统统计汇总接口"""
    from app.modules.common.account import Account
    from app.modules.common.recharge_order import RechargeOrder
    from app.modules.common.ticket import Ticket
    from sqlalchemy import func
    
    today = datetime.now().date()
    today_start = datetime.combine(today, datetime.min.time())
    
    total_accounts = (await db.execute(select(func.count(Account.id)))).scalar() or 0
    today_recharge = (await db.execute(select(func.sum(RechargeOrder.amount)).where(
        RechargeOrder.status == 'completed', RechargeOrder.created_at >= today_start
    ))).scalar() or 0
    pending_tickets = (await db.execute(select(func.count(Ticket.id)).where(
        Ticket.status.in_(['open', 'assigned', 'in_progress'])
    ))).scalar() or 0
    pending_recharge = (await db.execute(select(func.count(RechargeOrder.id)).where(
        RechargeOrder.status == 'pending'
    ))).scalar() or 0
    
    return {
        "total_accounts": total_accounts,
        "today_recharge": float(today_recharge),
        "pending_tickets": pending_tickets,
        "pending_recharge": pending_recharge
    }

@router.get("/sales-stats")
async def get_sales_stats_internal(tg_id: int, db: AsyncSession = Depends(get_db), token: str = Depends(verify_internal_secret)):
    """销售业绩统计汇总接口"""
    from app.modules.common.admin_user import AdminUser
    from app.modules.common.account import Account
    from app.modules.common.recharge_order import RechargeOrder
    from sqlalchemy import func
    
    admin = (await db.execute(select(AdminUser).where(AdminUser.tg_id == tg_id))).scalar_one_or_none()
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found")
        
    today = datetime.now()
    month_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    customer_count = (await db.execute(select(func.count(Account.id)).where(
        Account.admin_id == admin.id, Account.is_deleted == False
    ))).scalar() or 0
    
    month_recharge = (await db.execute(
        select(func.sum(RechargeOrder.amount))
        .join(Account, RechargeOrder.account_id == Account.id)
        .where(
            Account.admin_id == admin.id,
            RechargeOrder.status == 'completed',
            RechargeOrder.created_at >= month_start
        )
    )).scalar() or 0
    
    return {
        "admin_name": admin.real_name or admin.username,
        "customer_count": customer_count,
        "month_recharge": float(month_recharge)
    }

@router.get("/customer/balance/{tg_id}", dependencies=[Depends(verify_internal_secret)])
async def get_customer_balance_internal(tg_id: int, db: AsyncSession = Depends(get_db)):
    """获取客户余额"""
    try:
        from app.modules.common.telegram_binding import TelegramBinding
        from app.modules.common.account import Account
        
        row = (await db.execute(
            select(TelegramBinding, Account)
            .join(Account, TelegramBinding.account_id == Account.id)
            .where(TelegramBinding.tg_id == tg_id, Account.status != "closed", Account.is_deleted == False)
        )).first()
        
        if not row:
            return {"success": False, "msg": "未找到绑定账户"}
        
        _, account = row
        return {
            "success": True,
            "account_name": account.account_name,
            "balance": float(account.balance),
            "currency": account.currency,
            "status": account.status
        }
    except Exception as e:
        logger.error(f"获取余额失败: {e}")
        return {"success": False, "msg": str(e)}

@router.get("/customer/sms-stats/{tg_id}", dependencies=[Depends(verify_internal_secret)])
async def get_customer_sms_stats(tg_id: int, db: AsyncSession = Depends(get_db)):
    """获取客户最近7天发送统计"""
    try:
        from datetime import datetime, timedelta
        from sqlalchemy import func, case
        from app.modules.common.telegram_binding import TelegramBinding
        from app.modules.sms.sms_log import SmsLog
        
        account_id = (await db.execute(
            select(TelegramBinding.account_id).where(TelegramBinding.tg_id == tg_id)
        )).scalar()
        
        if not account_id:
            return {"success": False, "msg": "未绑定账户"}
            
        seven_days_ago = datetime.now() - timedelta(days=7)
        
        # 总发送/成功/失败/费用
        stats = (await db.execute(
            select(
                func.count(SmsLog.id).label("total"),
                func.sum(case((SmsLog.status == 'delivered', 1), else_=0)).label("success"),
                func.sum(case((SmsLog.status == 'failed', 1), else_=0)).label("failed"),
                func.sum(SmsLog.cost).label("cost")
            ).where(
                SmsLog.account_id == account_id,
                SmsLog.created_at >= seven_days_ago
            )
        )).mappings().first()
        
        return {
            "success": True,
            "total": stats["total"] or 0,
            "success_count": int(stats["success"] or 0),
            "failed_count": int(stats["failed"] or 0),
            "total_cost": float(stats["cost"] or 0)
        }
    except Exception as e:
        logger.error(f"获取发送统计失败: {e}")
        return {"success": False, "msg": str(e)}

@router.get("/sales/customers/{admin_id}", dependencies=[Depends(verify_internal_secret)])
async def get_sales_customers(
    admin_id: int, 
    biz_type: Optional[str] = None,
    page: int = 0,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db)
):
    """获取销售名下的客户列表"""
    try:
        from app.modules.common.account import Account
        from sqlalchemy import func
        query = select(Account).where(
            Account.sales_id == admin_id,
            Account.is_deleted == False
        )
        if biz_type and biz_type != 'all':
            query = query.where(Account.business_type == biz_type)
            
        # 统计类型
        counts_res = await db.execute(
            select(Account.business_type, func.count(Account.id))
            .where(Account.sales_id == admin_id, Account.is_deleted == False)
            .group_by(Account.business_type)
        )
        type_counts = dict(counts_res.all())
        
        # 分页
        total_q = select(func.count()).select_from(query.subquery())
        total = (await db.execute(total_q)).scalar() or 0
        
        res = await db.execute(query.order_by(Account.created_at.desc()).offset(page * page_size).limit(page_size))
        accounts = res.scalars().all()
        
        return {
            "success": True,
            "total": total,
            "type_counts": type_counts,
            "customers": [
                {
                    "id": a.id,
                    "account_name": a.account_name,
                    "business_type": a.business_type,
                    "balance": float(a.balance),
                    "status": a.status,
                    "created_at": a.created_at.isoformat() if a.created_at else None
                } for a in accounts
            ]
        }
    except Exception as e:
        logger.error(f"获取客户列表失败: {e}")
        return {"success": False, "msg": str(e)}

@router.post("/customer/sync-okcc/{account_id}", dependencies=[Depends(verify_internal_secret)])
async def sync_okcc_balance_internal(account_id: int, db: AsyncSession = Depends(get_db)):
    """从 OKCC 同步余额并写入账户 (后端逻辑)"""
    import httpx
    from sqlalchemy.orm.attributes import flag_modified
    from app.modules.common.account import Account

    _OKCC_APIS = {
        "lcchcc": "https://www.lcchcc.com/smsc_api.php",
        "klchcc": "https://www.klchcc.com/smsc_api.php",
    }
    _OKCC_API_KEY = "smsc_okcc_sync_8f3a2d1e"

    try:
        acct = await db.get(Account, account_id)
        if not acct or acct.business_type not in ("voice", "data"):
            return {"success": False, "msg": "账户类型不支持同步"}
        
        if not (acct.supplier_url or acct.supplier_credentials):
            return {"success": False, "msg": "资料缺失，无法同步"}

        acct_name = acct.account_name
        creds = dict(acct.supplier_credentials or {})
        okcc_server = creds.get("okcc_server", "")
        servers = [okcc_server] if okcc_server in _OKCC_APIS else list(_OKCC_APIS.keys())

        balance_yuan = None
        found_server = None
        for srv in servers:
            try:
                async with httpx.AsyncClient(verify=False, timeout=10) as client:
                    resp = await client.get(
                        _OKCC_APIS[srv],
                        params={"key": _OKCC_API_KEY, "action": "customer_detail", "name": acct_name},
                    )
                    data = resp.json()
                    if data.get("ok") and data.get("data"):
                        balance_yuan = float(data["data"].get("balance_yuan", 0))
                        found_server = srv
                        break
            except Exception:
                continue

        if balance_yuan is None:
            return {"success": False, "msg": "未在 OKCC 找到匹配客户"}

        creds["okcc_balance"] = balance_yuan
        creds["okcc_server"] = found_server
        creds["okcc_synced_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        acct.supplier_credentials = creds
        acct.balance = balance_yuan
        flag_modified(acct, "supplier_credentials")
        await db.commit()
        return {"success": True, "balance": balance_yuan}
    except Exception as e:
        logger.exception(f"sync_okcc_balance 失败 account_id={account_id}: {e}")
        return {"success": False, "msg": str(e)}

@router.get("/account-detail/{account_id}", dependencies=[Depends(verify_internal_secret)])
async def get_account_detail_internal(account_id: int, db: AsyncSession = Depends(get_db)):
    """获取账户详细信息 (后端视角)"""
    try:
        from app.modules.common.account import Account
        acct = await db.get(Account, account_id)
        if not acct:
            return {"success": False, "msg": "账户不存在"}
            
        return {
            "success": True,
            "id": acct.id,
            "account_name": acct.account_name,
            "business_type": acct.business_type,
            "balance": float(acct.balance),
            "currency": acct.currency,
            "status": acct.status,
            "supplier_url": acct.supplier_url,
            "supplier_credentials": acct.supplier_credentials,
            "created_at": acct.created_at.isoformat() if acct.created_at else None
        }
    except Exception as e:
        logger.error(f"获取账户详情失败: {e}")
        return {"success": False, "msg": str(e)}

@router.get("/account-pricing/{account_id}", dependencies=[Depends(verify_internal_secret)])
async def get_account_pricing_internal(account_id: int, db: AsyncSession = Depends(get_db)):
    """获取账户资费详情"""
    try:
        from app.modules.sms.channel import AccountChannel, Channel
        result = await db.execute(
            select(AccountChannel, Channel)
            .join(Channel, Channel.id == AccountChannel.channel_id)
            .where(AccountChannel.account_id == account_id)
        )
        pricing = []
        for ac, ch in result.all():
            pricing.append({
                "channel_name": ch.channel_name,
                "channel_code": ch.channel_code,
                "unit_price": float(ac.unit_price),
                "is_default": ac.is_default,
                "priority": ac.priority
            })
        return {"success": True, "pricing": pricing}
    except Exception as e:
        logger.error(f"获取资费详情失败: {e}")
        return {"success": False, "msg": str(e)}

@router.get("/account-bindings/{account_id}", dependencies=[Depends(verify_internal_secret)])
async def get_account_bindings_internal(account_id: int, db: AsyncSession = Depends(get_db)):
    """获取账户绑定的 Telegram 用户"""
    try:
        from app.modules.common.telegram_binding import TelegramBinding
        result = await db.execute(
            select(TelegramBinding).where(TelegramBinding.account_id == account_id, TelegramBinding.status == 'active')
        )
        bindings = []
        for b in result.scalars().all():
            bindings.append({
                "tg_id": b.tg_id,
                "tg_username": b.tg_username,
                "binding_type": b.binding_type
            })
        return {"success": True, "bindings": bindings}
    except Exception as e:
        logger.error(f"获取绑定失败: {e}")
        return {"success": False, "msg": str(e)}

@router.get("/knowledge/articles", dependencies=[Depends(verify_internal_secret)])
async def get_knowledge_articles_internal(category: str = None, db: AsyncSession = Depends(get_db)):
    """获取知识库文章列表"""
    try:
        from app.modules.common.knowledge import KnowledgeArticle
        query = select(KnowledgeArticle).where(KnowledgeArticle.status == "published").order_by(KnowledgeArticle.updated_at.desc())
        if category:
            query = query.where(KnowledgeArticle.category == category)
        
        result = await db.execute(query.limit(20))
        articles = []
        for a in result.scalars().all():
            articles.append({
                "id": a.id,
                "title": a.title,
                "category": a.category,
                "view_count": a.view_count,
                "updated_at": a.updated_at.isoformat() if a.updated_at else None
            })
        return {"success": True, "articles": articles}
    except Exception as e:
        logger.error(f"获取文章列表失败: {e}")
        return {"success": False, "msg": str(e)}

@router.get("/knowledge/articles/{article_id}", dependencies=[Depends(verify_internal_secret)])
async def get_knowledge_article_internal(article_id: int, db: AsyncSession = Depends(get_db)):
    """获取单篇文章详情"""
    try:
        from app.modules.common.knowledge import KnowledgeArticle, KnowledgeAttachment
        from sqlalchemy.orm import selectinload
        result = await db.execute(
            select(KnowledgeArticle)
            .options(selectinload(KnowledgeArticle.attachments))
            .where(KnowledgeArticle.id == article_id, KnowledgeArticle.status == "published")
        )
        a = result.scalar_one_or_none()
        if not a:
            return {"success": False, "msg": "文章不存在"}
        
        # 增加浏览次数
        a.view_count = (a.view_count or 0) + 1
        await db.commit()

        attachments = []
        for att in (a.attachments or []):
            attachments.append({
                "id": att.id,
                "file_name": att.file_name,
                "file_path": att.file_path,
                "file_size": att.file_size
            })
            
        return {
            "success": True, 
            "article": {
                "id": a.id,
                "title": a.title,
                "content": a.content,
                "category": a.category,
                "view_count": a.view_count,
                "attachments": attachments
            }
        }
    except Exception as e:
        logger.error(f"获取文章详情失败: {e}")
        return {"success": False, "msg": str(e)}

@router.get("/knowledge/attachments/{att_id}", dependencies=[Depends(verify_internal_secret)])
async def get_knowledge_attachment_internal(att_id: int, db: AsyncSession = Depends(get_db)):
    """获取知识库附件详情"""
    try:
        from app.modules.common.knowledge import KnowledgeAttachment
        result = await db.execute(select(KnowledgeAttachment).where(KnowledgeAttachment.id == att_id))
        att = result.scalar_one_or_none()
        if not att:
            return {"success": False, "msg": "附件不存在"}
            
        return {
            "success": True,
            "attachment": {
                "id": att.id,
                "file_name": att.file_name,
                "file_path": att.file_path
            }
        }
    except Exception as e:
        logger.error(f"获取附件详情失败: {e}")
        return {"success": False, "msg": str(e)}

@router.get("/pricing/countries/{biz_type}", dependencies=[Depends(verify_internal_secret)])
async def get_pricing_countries_internal(biz_type: str, db: AsyncSession = Depends(get_db)):
    """获取有报价的国家列表"""
    try:
        from sqlalchemy import text
        result = await db.execute(
            text("""
                SELECT DISTINCT country_code FROM supplier_rates
                WHERE status = 'active' AND business_type = :biz
                ORDER BY country_code
            """),
            {"biz": biz_type}
        )
        countries = [r[0] for r in result.fetchall()]
        return {"success": True, "countries": countries}
    except Exception as e:
        logger.error(f"获取报价国家失败: {e}")
        return {"success": False, "msg": str(e)}

@router.get("/pricing/detail/{biz_type}/{country_code}", dependencies=[Depends(verify_internal_secret)])
async def get_pricing_detail_internal(biz_type: str, country_code: str, db: AsyncSession = Depends(get_db)):
    """获取特定国家/业务的报价详情 (简版由bot自行根据 admin 策略计算，或返回原始供应商报价列表)"""
    try:
        from app.modules.sms.supplier import SupplierRate, Supplier
        result = await db.execute(
            select(SupplierRate, Supplier)
            .join(Supplier, Supplier.id == SupplierRate.supplier_id)
            .where(
                SupplierRate.business_type == biz_type,
                SupplierRate.country_code == country_code,
                SupplierRate.status == 'active',
                Supplier.is_deleted == False
            )
        )
        rates = []
        for sr, s in result.all():
            rates.append({
                "supplier_name": s.supplier_name,
                "cost_price": float(sr.cost_price),
                "billing_model": sr.billing_model,
                "note": sr.note
            })
        return {"success": True, "rates": rates}
    except Exception as e:
        logger.error(f"获取报价详情失败: {e}")
        return {"success": False, "msg": str(e)}

@router.get("/account-test-countries/{account_id}", dependencies=[Depends(verify_internal_secret)])
async def get_test_countries_internal(account_id: int, db: AsyncSession = Depends(get_db)):
    """获取账户可测试的国家列表"""
    try:
        from app.modules.common.account_template import AccountTemplate
        from app.modules.common.account import Account
        result = await db.execute(
            select(AccountTemplate.test_countries)
            .select_from(Account)
            .join(AccountTemplate, Account.template_id == AccountTemplate.id)
            .where(Account.id == account_id)
        )
        countries = result.scalar_one_or_none() or "-"
        return {"success": True, "countries": countries}
    except Exception as e:
        logger.error(f"获取测试国家失败: {e}")
        return {"success": False, "msg": str(e)}

@router.get("/account-supplier-group/{account_id}", dependencies=[Depends(verify_internal_secret)])
async def get_supplier_group_internal(account_id: int, db: AsyncSession = Depends(get_db)):
    """获取账户对应的供应商 Telegram 群组 ID"""
    try:
        from app.modules.sms.channel import SupplierChannel
        from app.modules.sms.supplier import Supplier
        from app.modules.common.account import Account
        
        # 简化版逻辑：获取账户关联通道的第一个有效供应商群组
        # 实际逻辑可能更复杂，这里先实现核心解耦需求
        from sqlalchemy import text
        sql = text("""
            SELECT s.telegram_group_id, s.supplier_name
            FROM supplier_channels sc
            JOIN suppliers s ON sc.supplier_id = s.id
            JOIN accounts a ON FIND_IN_SET(sc.channel_id, a.channel_ids)
            WHERE a.id = :acc_id 
              AND sc.status = 'active'
              AND s.is_deleted = 0
              AND s.telegram_group_id IS NOT NULL
              AND TRIM(s.telegram_group_id) != ''
            LIMIT 1
        """)
        raw_result = await db.execute(sql, {"acc_id": account_id})
        row = raw_result.first()
        tg_id = row[0] if row else None
        return {"success": True, "supplier_group_id": tg_id}
    except Exception as e:
        logger.error(f"获取供应商群组失败: {e}")
        return {"success": False, "msg": str(e)}

@router.post("/recharge-order", dependencies=[Depends(verify_internal_secret)])
async def create_recharge_order_internal(data: dict, db: AsyncSession = Depends(get_db)):
    """创建充值工单"""
    try:
        from app.modules.common.recharge_order import RechargeOrder
        from app.modules.common.account import Account
        from datetime import datetime
        import uuid

        account_id = data.get("account_id")
        amount = data.get("amount")
        proof = data.get("proof")
        
        # 验证账户
        acc_result = await db.execute(select(Account).where(Account.id == account_id))
        account = acc_result.scalar_one_or_none()
        if not account or account.is_deleted:
            return {"success": False, "msg": "账户不存在或已删除"}

        order_no = f"RCH_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6].upper()}"
        order = RechargeOrder(
            order_no=order_no,
            account_id=account_id,
            amount=amount,
            currency="USD",
            payment_proof=proof,
            status="pending"
        )
        db.add(order)
        await db.commit()
        return {"success": True, "order_no": order_no}
    except Exception as e:
        logger.error(f"创建充值工单失败: {e}")
        return {"success": False, "msg": str(e)}

@router.get("/recharge-orders/pending", dependencies=[Depends(verify_internal_secret)])
async def get_pending_recharges_internal(db: AsyncSession = Depends(get_db)):
    """获取待审核的充值工单"""
    try:
        from app.modules.common.recharge_order import RechargeOrder
        from app.modules.common.account import Account
        result = await db.execute(
            select(RechargeOrder, Account.username)
            .join(Account, Account.id == RechargeOrder.account_id)
            .where(RechargeOrder.status == "pending")
        )
        orders = []
        for r, username in result.all():
            orders.append({
                "id": r.id,
                "order_no": r.order_no,
                "username": username,
                "amount": float(r.amount),
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "proof": r.payment_proof
            })
        return {"success": True, "orders": orders}
    except Exception as e:
        logger.error(f"获取待审核充值失败: {e}")
        return {"success": False, "msg": str(e)}

@router.post("/recharge-order/{order_id}/audit", dependencies=[Depends(verify_internal_secret)])
async def audit_recharge_order_internal(order_id: int, data: dict, db: AsyncSession = Depends(get_db)):
    """审核充值工单"""
    try:
        from app.modules.common.recharge_order import RechargeOrder
        from app.modules.common.account import Account
        from app.modules.common.balance_log import BalanceLog
        from app.services.notification_service import notification_service
        
        status = data.get("status") # 'approved' or 'rejected'
        remark = data.get("remark", "")
        admin_id = data.get("admin_id")

        result = await db.execute(select(RechargeOrder).where(RechargeOrder.id == order_id))
        order = result.scalar_one_or_none()
        if not order or order.status != "pending":
            return {"success": False, "msg": "工单不存在或已处理"}

        order.status = status
        order.remark = remark
        order.audited_at = datetime.now()
        order.auditor_id = admin_id

        if status == "approved":
            # 增加余额
            acc_result = await db.execute(select(Account).where(Account.id == order.account_id))
            account = acc_result.scalar_one_or_none()
            if account:
                old_balance = float(account.balance)
                account.balance += order.amount
                # 记录流水
                log = BalanceLog(
                    account_id=account.id,
                    type="recharge",
                    amount=order.amount,
                    old_balance=old_balance,
                    new_balance=float(account.balance),
                    operator=f"BotAdmin:{admin_id}",
                    note=f"充值审核通过: {order.order_no}"
                )
                db.add(log)
        
        await db.commit()

        # 发送通知
        try:
            await notification_service.notify_recharge_audit(order.id)
        except Exception as notify_e:
            logger.error(f"发送充值审核通知失败: {notify_e}")

        return {"success": True}
    except Exception as e:
        logger.error(f"审核充值工单失败: {e}")
        return {"success": False, "msg": str(e)}

@router.post("/sales/bind", dependencies=[Depends(verify_internal_secret)])
async def bind_sales_internal(data: dict, db: AsyncSession = Depends(get_db)):
    """绑定销售账号到 Telegram ID"""
    try:
        from app.modules.common.admin_user import AdminUser
        from app.core.auth import AuthService
        
        username = data.get("username")
        password = data.get("password")
        tg_id = data.get("tg_id")

        result = await db.execute(
            select(AdminUser).where(AdminUser.username == username, AdminUser.status == 'active')
        )
        admin = result.scalar_one_or_none()
        
        if not admin:
            return {"success": False, "msg": "用户名不存在或账号已禁用"}
            
        if not AuthService.verify_password(password, admin.password_hash):
            return {"success": False, "msg": "密码错误"}
            
        if admin.role not in ['sales', 'super_admin', 'admin']:
            return {"success": False, "msg": "权限不足（非销售角色）"}
            
        admin.tg_id = tg_id
        await db.commit()
        return {"success": True, "real_name": admin.real_name, "sales_id": admin.id}
    except Exception as e:
        logger.error(f"绑定销售失败: {e}")
        return {"success": False, "msg": str(e)}

@router.get("/sales/templates", dependencies=[Depends(verify_internal_secret)])
async def get_sales_templates_internal(biz_type: Optional[str] = None, country_code: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """获取销售可用的开户模板"""
    try:
        from app.modules.common.account_template import AccountTemplate
        query = select(AccountTemplate).where(AccountTemplate.status == "active")
        if biz_type:
            query = query.where(AccountTemplate.business_type == biz_type)
        if country_code:
            query = query.where(func.upper(AccountTemplate.country_code) == country_code.upper())
        
        result = await db.execute(query)
        templates = []
        for t in result.scalars().all():
            templates.append({
                "id": t.id,
                "template_name": t.template_name,
                "template_code": t.template_code,
                "business_type": t.business_type,
                "country_code": t.country_code,
                "default_price": float(t.default_price) if t.default_price else 0.0,
                "supplier_group_id": t.supplier_group_id
            })
        return {"success": True, "templates": templates}
    except Exception as e:
        logger.error(f"获取销售模板失败: {e}")
        return {"success": False, "msg": str(e)}

@router.post("/sales/invitation", dependencies=[Depends(verify_internal_secret)])
async def create_invitation_internal(data: dict, db: AsyncSession = Depends(get_db)):
    """创建邀请码"""
    try:
        from app.core.invitation import InvitationService
        sales_id = data.get("sales_id")
        config = data.get("config")
        valid_hours = data.get("valid_hours", 72)

        service = InvitationService(db)
        code = await service.create_code(sales_id, config, valid_hours)
        return {"success": True, "code": code}
    except Exception as e:
        logger.error(f"创建邀请码失败: {e}")
        return {"success": False, "msg": str(e)}

@router.post("/invitation/activate", dependencies=[Depends(verify_internal_secret)])
async def activate_invitation_internal(data: dict, db: AsyncSession = Depends(get_db)):
    """激活邀请码"""
    try:
        from app.core.invitation import InvitationService
        code = data.get("code")
        tg_id = data.get("tg_id")
        tg_username = data.get("tg_username")
        tg_first_name = data.get("tg_first_name")

        service = InvitationService(db)
        account, api_key, extra_info = await service.activate_code(
            code, tg_id, tg_username=tg_username, tg_first_name=tg_first_name
        )
        
        return {
            "success": True,
            "account": {
                "id": account.id,
                "account_name": account.account_name,
                "business_type": account.business_type
            },
            "api_key": api_key,
            "extra_info": extra_info
        }
    except ValueError as e:
        return {"success": False, "msg": str(e)}
    except Exception as e:
        logger.error(f"激活邀请码失败: {e}", exc_info=True)
        return {"success": False, "msg": "Internal server error"}

@router.get("/sales/stats/{sales_id}", dependencies=[Depends(verify_internal_secret)])
async def get_sales_stats_internal(sales_id: int, db: AsyncSession = Depends(get_db)):
    """获取销售业绩统计"""
    try:
        from app.modules.common.admin_user import AdminUser
        from app.modules.common.account import Account
        from sqlalchemy import func, select, text
        from datetime import datetime

        admin = await db.get(AdminUser, sales_id)
        if not admin:
            return {"success": False, "msg": "Sales user not found"}
            
        rate = float(admin.commission_rate or 0) / 100.0
        
        # 本月第一天
        today = datetime.now()
        first_day_dt = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        first_day_str = first_day_dt.strftime('%Y-%m-%d 00:00:00')
        
        # 我的客户数
        total_cust_res = await db.execute(
            select(func.count(Account.id)).where(Account.sales_id == sales_id, Account.is_deleted == False)
        )
        total_customers = total_cust_res.scalar() or 0
        
        # 本月新增客户
        new_cust_res = await db.execute(
            select(func.count(Account.id)).where(
                Account.sales_id == sales_id, 
                Account.created_at >= first_day_dt,
                Account.is_deleted == False
            )
        )
        new_customers = new_cust_res.scalar() or 0
        
        # 客户总余额
        balance_res = await db.execute(
            select(func.sum(Account.balance)).where(Account.sales_id == sales_id, Account.is_deleted == False)
        )
        total_balance = float(balance_res.scalar() or 0)

        # 业绩统计
        sql = text("""
            SELECT SUM(l.profit * l.message_count) 
            FROM sms_logs l
            JOIN accounts acc ON l.account_id = acc.id
            JOIN channels ch ON l.channel_id = ch.id
            WHERE acc.sales_id = :sales_id 
              AND l.submit_time >= :start_time
              AND l.status = 'delivered'
              AND ch.protocol != 'VIRTUAL'
        """)
        
        res_comm = await db.execute(sql, {"sales_id": sales_id, "start_time": first_day_str})
        total_profit = float(res_comm.scalar() or 0)
        
        return {
            "success": True,
            "monthly_profit": total_profit,
            "monthly_commission": total_profit * rate,
            "commission_rate": admin.commission_rate,
            "total_customers": total_customers,
            "new_customers": new_customers,
            "total_balance": total_balance
        }
    except Exception as e:
        logger.error(f"获取销售统计失败: {e}")
        return {"success": False, "msg": str(e)}

@router.get("/user/bindings/{tg_id}", dependencies=[Depends(verify_internal_secret)])
async def get_user_bindings_internal(tg_id: int, db: AsyncSession = Depends(get_db)):
    """获取用户绑定的所有账户"""
    try:
        from app.modules.common.telegram_binding import TelegramBinding
        from app.modules.common.account import Account
        
        query = select(TelegramBinding, Account).join(
            Account, TelegramBinding.account_id == Account.id
        ).where(TelegramBinding.tg_id == tg_id)
        
        result = await db.execute(query)
        bindings = []
        for b, acc in result.all():
            bindings.append({
                "account_id": b.account_id,
                "account_name": acc.account_name,
                "is_active": b.is_active,
                "status": acc.status
            })
        return {"success": True, "bindings": bindings}
    except Exception as e:
        logger.error(f"获取绑定失败: {e}")
        return {"success": False, "msg": str(e)}

@router.post("/user/switch-account", dependencies=[Depends(verify_internal_secret)])
async def switch_user_account_internal(data: dict, db: AsyncSession = Depends(get_db)):
    """切换当前活跃账户"""
    try:
        from app.modules.common.telegram_binding import TelegramBinding
        tg_id = data.get("tg_id")
        account_id = data.get("account_id")
        
        # 将该用户的所有绑定设为非活跃
        await db.execute(
            update(TelegramBinding)
            .where(TelegramBinding.tg_id == tg_id)
            .values(is_active=False)
        )
        
        # 将指定绑定设为活跃
        await db.execute(
            update(TelegramBinding)
            .where(TelegramBinding.tg_id == tg_id, TelegramBinding.account_id == account_id)
            .values(is_active=True)
        )
        
        await db.commit()
        return {"success": True}
    except Exception as e:
        logger.error(f"切换账户失败: {e}")
        return {"success": False, "msg": str(e)}

@router.post("/user/bind-by-code", dependencies=[Depends(verify_internal_secret)])
async def bind_account_by_code_internal(data: dict, db: AsyncSession = Depends(get_db)):
    """通过验证码绑定账户"""
    try:
        import redis
        from app.config import settings
        from app.modules.common.telegram_binding import TelegramBinding
        from app.modules.common.telegram_user import TelegramUser
        from app.modules.common.account import Account
        from sqlalchemy.dialects.mysql import insert as mysql_insert

        code = data.get("code")
        tg_id = data.get("tg_id")
        username = data.get("username")

        redis_host = getattr(settings, "REDIS_HOST", "redis")
        redis_port = int(getattr(settings, "REDIS_PORT", 6379))
        redis_password = getattr(settings, "REDIS_PASSWORD", None)
        r = redis.Redis(host=redis_host, port=redis_port, password=redis_password or None, decode_responses=True)
        
        redis_key = f"acct_tg_bind:{code}"
        account_id_str = r.get(redis_key)
        if not account_id_str:
            return {"success": False, "msg": "验证码无效或已过期"}

        account_id = int(account_id_str)
        r.delete(redis_key)

        acc = await db.get(Account, account_id)
        if not acc:
            return {"success": False, "msg": "账户不存在"}

        acc.tg_id = tg_id
        acc.tg_username = username

        # 处理绑定
        res = await db.execute(select(TelegramBinding).where(TelegramBinding.tg_id == tg_id, TelegramBinding.account_id == account_id))
        binding = res.scalar_one_or_none()
        if binding:
            binding.is_active = True
        else:
            db.add(TelegramBinding(tg_id=tg_id, account_id=account_id, is_active=True))

        # 处理 TelegramUser
        stmt = mysql_insert(TelegramUser).values(tg_id=tg_id, username=username, account_id=account_id)
        stmt = stmt.on_duplicate_key_update(username=username, account_id=account_id)
        await db.execute(stmt)
        
        await db.commit()
        return {"success": True, "account_name": acc.account_name, "account_id": acc.id}
    except Exception as e:
        logger.error(f"验证码绑定失败: {e}")
        return {"success": False, "msg": str(e)}

@router.get("/system/config", dependencies=[Depends(verify_internal_secret)])
async def get_system_config_internal(db: AsyncSession = Depends(get_db)):
    """获取系统 Bot 相关配置"""
    try:
        from app.modules.common.system_config import SystemConfig
        result = await db.execute(
            select(SystemConfig.config_key, SystemConfig.config_value).where(
                SystemConfig.config_key.in_([
                    'telegram_admin_group_id',
                    'telegram_enable_sms_content_review',
                    'telegram_bot_username'
                ])
            )
        )
        rows = result.fetchall()
        config_data = {}
        for k, v in rows:
            config_data[k] = v
        return {"success": True, "config": config_data}
    except Exception as e:
        logger.error(f"获取系统配置失败: {e}")
        return {"success": False, "msg": str(e)}

@router.post("/sms/submit-approval", dependencies=[Depends(verify_internal_secret)])
async def submit_sms_approval_internal(data: dict, db: AsyncSession = Depends(get_db)):
    """提交短信内容审核"""
    try:
        from app.modules.common.account import Account
        from app.modules.common.sms_content_approval import SmsContentApproval
        from app.modules.common.ticket import Ticket
        from app.modules.common.system_config import SystemConfig
        from app.core.router import RoutingEngine
        from app.utils.validator import Validator
        import secrets
        from datetime import datetime
        
        tg_id = data.get("tg_id")
        account_id = data.get("account_id")
        content = data.get("content")
        phone = data.get("phone")  # 可选
        sms_submit_mode = data.get("sms_submit_mode", "direct")
        
        acc = await db.get(Account, account_id)
        if not acc:
            return {"success": False, "msg": "账户不存在"}
            
        if float(acc.balance or 0) <= 0:
            return {"success": False, "msg": "余额不足"}

        # 获取系统配置
        config_res = await db.execute(
            select(SystemConfig.config_key, SystemConfig.config_value).where(
                SystemConfig.config_key.in_(['telegram_admin_group_id', 'telegram_enable_sms_content_review'])
            )
        )
        sys_config = {k: v for k, v in config_res.fetchall()}
        admin_group_id = (sys_config.get('telegram_admin_group_id') or '').strip()
        enable_review = (sys_config.get('telegram_enable_sms_content_review') or 'true').lower() == 'true'
        
        # 默认目标群组
        target_group_id = admin_group_id
        
        # 尝试根据国家路由解析供应商群组
        country_code = "*"
        if phone:
            is_valid, _, phone_info = Validator.validate_phone_number(phone)
            if is_valid and phone_info:
                country_code = phone_info.get('country_code', '*')
        
        # 解析供应商群组逻辑 (复制自 menu.py logic)
        try:
            routing = RoutingEngine(db)
            channel = await routing.select_channel(country_code=country_code, account_id=account_id)
            if channel:
                from app.modules.sms.supplier import Supplier, SupplierChannel
                sc_result = await db.execute(
                    select(SupplierChannel, Supplier)
                    .join(Supplier, SupplierChannel.supplier_id == Supplier.id)
                    .where(
                        SupplierChannel.channel_id == channel.id,
                        SupplierChannel.status == 'active',
                        Supplier.is_deleted == False
                    ).limit(1)
                )
                sc_row = sc_result.first()
                if sc_row:
                    _, supplier = sc_row
                    if getattr(supplier, 'telegram_group_id', None):
                        target_group_id = (supplier.telegram_group_id or '').strip()
        except Exception as e:
            logger.debug(f"解析供应商群组失败: {e}")

        # 判断是否需要审核
        force_audit = (sms_submit_mode == 'audit')
        if not (force_audit or (enable_review and target_group_id)):
            return {"success": True, "need_audit": False}

        # 创建审核记录
        approval_no = f"SA{datetime.now().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(2).upper()}"
        approval = SmsContentApproval(
            approval_no=approval_no,
            account_id=account_id,
            tg_user_id=str(tg_id),
            phone_number=phone,
            content=content,
            status='pending',
            forwarded_to_group=target_group_id if target_group_id else None
        )
        db.add(approval)
        await db.flush() # 获取 ID
        
        # 创建工单
        ticket_no = f"TK{datetime.now().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(2).upper()}"
        sms_ticket = Ticket(
            ticket_no=ticket_no,
            account_id=account_id,
            tg_user_id=str(tg_id),
            ticket_type='test',
            priority='normal',
            title=f"短信审核-{approval_no}",
            description=f"号码: {phone or '未提供'}\n内容: {content[:500]}",
            status='open',
            created_by_type='telegram',
            created_by_id=tg_id,
            test_phone=phone,
            test_content=content,
            review_status='pending',
            forwarded_to_group=target_group_id if target_group_id else None,
            extra_data={"sms_approval_id": approval.id},
        )
        db.add(sms_ticket)
        await db.commit()
        
        # 获取测试国家列表用于展示
        test_countries = "-"
        try:
            from app.modules.common.account_template import AccountTemplate
            res = await db.execute(select(AccountTemplate).where(AccountTemplate.account_id == account_id))
            templates = res.scalars().all()
            codes = set()
            for t in templates:
                if t.country_code: codes.add(t.country_code)
            test_countries = ",".join(sorted(list(codes))) if codes else "全球"
        except: pass

        return {
            "success": True,
            "need_audit": True,
            "approval_id": approval.id,
            "ticket_no": ticket_no,
            "target_group_id": target_group_id,
            "test_countries": test_countries,
            "approval_no": approval_no
        }
    except Exception as e:
        logger.error(f"提交审核失败: {e}", exc_info=True)
        return {"success": False, "msg": str(e)}

@router.post("/sms/approval/{approval_id}/send", dependencies=[Depends(verify_internal_secret)])
async def send_sms_after_approval_internal(approval_id: int, data: dict, db: AsyncSession = Depends(get_db)):
    """审核通过后发送短信"""
    try:
        from app.modules.common.sms_content_approval import SmsContentApproval
        from app.modules.common.account import Account
        from app.core.sms_service import SMSService
        from app.utils.validator import Validator
        
        phone = data.get("phone")
        tg_id = data.get("tg_id")

        if not phone:
            return {"success": False, "msg": "手机号不能为空"}

        # 校验号码
        is_valid, err_msg, _ = Validator.validate_phone_number(phone)
        if not is_valid:
            return {"success": False, "msg": f"号码格式错误: {err_msg}"}

        res = await db.execute(
            select(SmsContentApproval, Account)
            .join(Account, SmsContentApproval.account_id == Account.id)
            .where(SmsContentApproval.id == approval_id)
        )
        row = res.first()
        if not row:
            return {"success": False, "msg": "审批记录不存在"}
        
        approval, account = row
        if str(approval.tg_user_id) != str(tg_id):
            return {"success": False, "msg": "无权操作"}
            
        if approval.status != 'approved':
            return {"success": False, "msg": f"审批状态不正确: {approval.status}"}
            
        if approval.message_id:
            return {"success": False, "msg": "短信已经发送过"}

        # 发送短信
        service = SMSService(db)
        send_res = await service.send_sms(
            account_id=account.id,
            phone_number=phone,
            message=approval.content,
            api_key=account.api_key
        )
        
        if send_res.get("success"):
            approval.phone_number = phone
            approval.message_id = send_res.get("message_id", "")
            approval.send_error = None
            await db.commit()
            return {"success": True, "message_id": approval.message_id}
        else:
            approval.send_error = send_res.get("msg", "Unknown error")
            await db.commit()
            return {"success": False, "msg": f"发送失败: {send_res.get('msg')}"}
            
    except Exception as e:
        logger.error(f"发送审批后短信失败: {e}", exc_info=True)
        return {"success": False, "msg": str(e)}

@router.post("/sms/approval/{approval_id}/action", dependencies=[Depends(verify_internal_secret)])
async def update_sms_approval_action_internal(approval_id: int, data: dict, db: AsyncSession = Depends(get_db)):
    """更新审批记录（通过/拒绝）"""
    try:
        from app.modules.common.sms_content_approval import SmsContentApproval
        from app.modules.common.ticket import Ticket
        
        status = data.get("status") # 'approved' or 'rejected'
        reason = data.get("reason", "")
        
        approval = await db.get(SmsContentApproval, approval_id)
        if not approval:
            return {"success": False, "msg": "记录不存在"}
            
        approval.status = status
        approval.review_note = reason
        
        # 同时更新工单状态
        ticket_res = await db.execute(select(Ticket).where(Ticket.extra_data['sms_approval_id'].as_integer() == approval_id))
        ticket = ticket_res.scalar_one_or_none()
        if ticket:
            ticket.status = 'closed'
            ticket.review_status = status
            ticket.resolution = reason
            
        await db.commit()
        return {"success": True}
    except Exception as e:
        logger.error(f"更新审批动作失败: {e}")
        return {"success": False, "msg": str(e)}

@router.get("/knowledge")
async def list_knowledge(category: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """获取知识库文章列表"""
    from app.modules.common.knowledge import KnowledgeArticle
    query = select(KnowledgeArticle).where(KnowledgeArticle.is_published == True)
    if category:
        query = query.where(KnowledgeArticle.category == category)
    result = await db.execute(query.order_by(KnowledgeArticle.order.asc(), KnowledgeArticle.created_at.desc()))
    articles = result.scalars().all()
    return {
        "success": True, 
        "articles": [
            {"id": a.id, "title": a.title, "category": a.category} for a in articles
        ]
    }

@router.get("/knowledge/{article_id}")
async def get_knowledge_detail(article_id: int, db: AsyncSession = Depends(get_db)):
    """获取知识库文章详情"""
    from app.modules.common.knowledge import KnowledgeArticle, KnowledgeAttachment
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(KnowledgeArticle)
        .options(selectinload(KnowledgeArticle.attachments))
        .where(KnowledgeArticle.id == article_id)
    )
    article = result.scalar_one_or_none()
    if not article:
        return {"success": False, "message": "Article not found"}
    
    return {
        "success": True,
        "article": {
            "id": article.id,
            "title": article.title,
            "content": article.content,
            "attachments": [
                {"id": att.id, "filename": att.filename, "file_path": att.file_path} for att in article.attachments
            ]
        }
    }
