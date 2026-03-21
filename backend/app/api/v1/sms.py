"""
短信发送API路由
"""
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, BackgroundTasks, Header, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.modules.common.account import Account
from app.modules.sms.sms_log import SMSLog
from app.core.auth import AuthService, api_key_header
from app.utils.validator import Validator
from app.core.router import RoutingEngine
from app.core.pricing import PricingEngine
from app.schemas.sms import (
    SMSSendRequest,
    SMSSendResponse,
    SMSStatusResponse,
    BatchSMSRequest,
    BatchSMSResponse,
    SMSApprovalSubmitRequest,
)
from fastapi.responses import JSONResponse
from app.utils.logger import get_logger
from app.utils.errors import (
    ValidationError, AuthenticationError,
    InsufficientBalanceError, PricingNotFoundError, ChannelNotAvailableError
)
from sqlalchemy import select

logger = get_logger(__name__)
router = APIRouter()

# Optional bearer token for admin access
optional_bearer = HTTPBearer(auto_error=False)


async def get_current_account_or_admin(
    api_key: Optional[str] = Depends(api_key_header),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_bearer),
    db: AsyncSession = Depends(get_db)
) -> Account:
    """
    获取当前认证账户 - 支持 API Key 或管理员 JWT Token
    
    优先使用 API Key，如果没有则尝试使用 JWT Token（管理员模式）
    管理员模式下会使用系统默认账户或第一个可用账户
    """
    # 1. 优先使用 API Key
    if api_key:
        try:
            return await AuthService.verify_api_key(api_key, db)
        except AuthenticationError:
            pass  # 继续尝试 JWT Token
    
    # 2. 尝试使用 JWT Token（管理员模式）
    if credentials and credentials.credentials:
        try:
            payload = AuthService.verify_token(credentials.credentials)
            admin_id = payload.get("sub")
            if admin_id:
                # 管理员认证成功，获取一个可用账户来发送短信
                # 优先查找系统账户或第一个激活的账户
                result = await db.execute(
                    select(Account).where(
                        Account.status == 'active',
                        Account.is_deleted == False
                    ).order_by(Account.id).limit(1)
                )
                account = result.scalar_one_or_none()
                
                if account:
                    logger.info(
                        f"管理员 {admin_id} 使用系统默认账户 {account.id} ({account.account_name}) 发送短信；"
                        "若需按客户绑定通道发送，请使用「模拟登录」"
                    )
                    return account
                else:
                    raise AuthenticationError("No available account for admin SMS sending")
        except Exception as e:
            logger.warning(f"JWT Token 验证失败: {str(e)}")
    
    # 3. 都失败了
    raise AuthenticationError("Missing API Key or invalid token")


async def get_auth_context(
    api_key: Optional[str] = Depends(api_key_header),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_bearer),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    获取认证上下文 - 区分管理员和客户账户
    
    返回:
        {
            "is_admin": bool,
            "admin_id": Optional[int],
            "account": Optional[Account],
            "account_id": Optional[int]
        }
    """
    context = {
        "is_admin": False,
        "admin_id": None,
        "account": None,
        "account_id": None
    }
    
    # 1. 先检查 JWT Token（管理员模式）
    if credentials and credentials.credentials:
        try:
            payload = AuthService.verify_token(credentials.credentials)
            admin_id = payload.get("sub")
            if admin_id:
                context["is_admin"] = True
                context["admin_id"] = int(admin_id)
                logger.info(f"管理员 {admin_id} 访问短信记录")
                return context
        except Exception as e:
            logger.debug(f"JWT Token 验证失败: {str(e)}")
    
    # 2. 检查 API Key（客户账户模式）
    if api_key:
        try:
            account = await AuthService.verify_api_key(api_key, db)
            context["account"] = account
            context["account_id"] = account.id
            return context
        except AuthenticationError:
            pass
    
    # 3. 都失败了
    raise AuthenticationError("Missing API Key or invalid token")


# 保留旧函数名以兼容
async def get_current_account(
    api_key: str = Depends(api_key_header),
    db: AsyncSession = Depends(get_db)
) -> Account:
    """获取当前认证账户（仅 API Key）"""
    return await AuthService.verify_api_key(api_key, db)


@router.post("/send", response_model=SMSSendResponse)
async def send_sms(
    request: SMSSendRequest,
    account: Account = Depends(get_current_account_or_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    发送单条短信
    
    - **phone_number**: 目标电话号码（E.164格式）
    - **message**: 短信内容
    - **sender_id**: (废弃字段，自动使用通道默认SID)
    - **channel_id**: 指定通道ID（可选）
    - **callback_url**: 状态回调URL（可选）
    """
    try:
        logger.info(f"收到短信发送请求: 账户={account.id}, 号码={request.phone_number}")
        
        # 1. 验证号码
        is_valid_phone, error_msg, phone_info = Validator.validate_phone_number(request.phone_number)
        if not is_valid_phone:
            return SMSSendResponse(
                success=False,
                error={"code": "INVALID_PHONE", "message": error_msg}
            )
        
        country_code = phone_info['country_code']
        logger.debug(f"号码解析: 国家={country_code}")
        
        # 2. 验证内容
        is_valid_content, error_msg, content_info = Validator.validate_content(request.message)
        if not is_valid_content:
            return SMSSendResponse(
                success=False,
                error={"code": "INVALID_CONTENT", "message": error_msg}
            )
        
        # 3. 路由选择通道（账户已绑定通道时，仅在绑定通道中路由）
        routing_engine = RoutingEngine(db)
        channel = await routing_engine.select_channel(
            country_code=country_code,
            preferred_channel=request.channel_id,
            strategy='priority',
            account_id=account.id
        )
        
        if not channel:
            return SMSSendResponse(
                success=False,
                error={"code": "NO_CHANNEL", "message": "No available channel"}
            )
        
        logger.info(f"选择通道: {channel.channel_code}")
        
        # 4. 获取发送方ID (从通道获取默认SID)
        sender_id = channel.default_sender_id
        
        # 5. 计费 (Cost + Sell)
        pricing_engine = PricingEngine(db)
        charge_result = await pricing_engine.calculate_and_charge(
            account_id=account.id,
            channel_id=channel.id,
            country_code=country_code,
            message=request.message
        )
        
        if not charge_result['success']:
            return SMSSendResponse(
                success=False,
                error={"code": "BILLING_ERROR", "message": charge_result.get('error', 'Billing failed')}
            )
        
        # 6. 生成消息ID
        message_id = f"msg_{uuid.uuid4().hex}"
        
        # 7. 创建短信记录 (包含成本与利润)
        sms_log = SMSLog(
            message_id=message_id,
            account_id=account.id,
            channel_id=channel.id,
            phone_number=phone_info['e164_format'],
            country_code=country_code,
            message=request.message,
            message_count=charge_result['message_count'],
            status='queued',
            # 结算数据
            cost_price=charge_result['total_base_cost'],
            selling_price=charge_result['total_cost'],
            # profit 由数据库生成列自动计算，或手动传入
            # profit=charge_result['total_cost'] - charge_result['total_base_cost'], 
            currency=charge_result['currency'],
            submit_time=datetime.now(),
            sent_time=None,
            delivery_time=None,
            error_message=None
        )
        
        db.add(sms_log)
        await db.flush()
        
        logger.info(f"短信记录已创建: {message_id}, Profit={sms_log.selling_price - sms_log.cost_price}")
        
        # 8. 发送到消息队列（后台任务）
        from app.utils.queue import QueueManager
        
        # 如果是HTTP通道且提供了HTTP凭据，传递给Worker
        http_credentials = None
        if request.http_username or request.http_password:
            http_credentials = {
                "username": request.http_username,
                "password": request.http_password
            }
        
        queue_success = QueueManager.queue_sms(message_id, http_credentials)
        
        if not queue_success:
            logger.warning(f"加入队列失败，但记录已创建: {message_id}")
        
        return SMSSendResponse(
            success=True,
            message_id=message_id,
            status='queued',
            cost=charge_result['total_cost'],
            currency=charge_result['currency'],
            message_count=charge_result['message_count']
        )
        
    except ValidationError as e:
        logger.error(f"参数验证错误: {str(e)}")
        return SMSSendResponse(
            success=False,
            error={"code": e.error_code, "message": e.message}
        )
    except (InsufficientBalanceError, PricingNotFoundError, ChannelNotAvailableError) as e:
        return SMSSendResponse(
            success=False,
            error={"code": e.error_code, "message": e.message}
        )
    except Exception as e:
        logger.error(f"发送短信失败: {str(e)}", exc_info=e)
        return SMSSendResponse(
            success=False,
            error={"code": "INTERNAL_ERROR", "message": "An internal error occurred. Please try again later."}
        )


@router.get("/status/{message_id}", response_model=SMSStatusResponse)
async def get_sms_status(
    message_id: str,
    account: Account = Depends(get_current_account_or_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    查询短信状态
    """
    # 查询短信记录
    result = await db.execute(
        select(SMSLog).where(
            SMSLog.message_id == message_id,
            SMSLog.account_id == account.id
        )
    )
    sms_log = result.scalar_one_or_none()
    
    if not sms_log:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Message not found")
    
    return SMSStatusResponse(
        message_id=sms_log.message_id,
        status=sms_log.status,
        phone_number=sms_log.phone_number,
        submit_time=sms_log.submit_time.isoformat(),
        sent_time=sms_log.sent_time.isoformat() if sms_log.sent_time else None,
        delivery_time=sms_log.delivery_time.isoformat() if sms_log.delivery_time else None,
        error_message=sms_log.error_message,
        cost=float(sms_log.selling_price) if sms_log.selling_price else None,
        currency=sms_log.currency
    )


@router.post("/batch", response_model=BatchSMSResponse)
async def send_batch_sms(
    request: BatchSMSRequest,
    account: Account = Depends(get_current_account_or_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    批量发送短信（异步入队模式）

    先预校验号码并批量创建记录、扣费，然后统一入队异步发送，
    避免逐条同步阻塞。
    """
    from app.utils.queue import QueueManager

    results = []
    succeeded = 0
    failed = 0

    for phone_number in request.phone_numbers:
        try:
            # 1. 校验号码
            is_valid, err_msg, phone_info = Validator.validate_phone_number(phone_number)
            if not is_valid:
                failed += 1
                results.append({"phone_number": phone_number, "success": False,
                                "message_id": None, "error": {"code": "INVALID_PHONE", "message": err_msg}})
                continue

            country_code = phone_info['country_code']

            # 2. 路由选择（账户已绑定通道时，仅在绑定通道中路由）
            routing_engine = RoutingEngine(db)
            channel = await routing_engine.select_channel(
                country_code=country_code,
                strategy='priority',
                account_id=account.id
            )
            if not channel:
                failed += 1
                results.append({"phone_number": phone_number, "success": False,
                                "message_id": None, "error": {"code": "NO_CHANNEL", "message": "No available channel"}})
                continue

            # 3. 计费扣款
            pricing_engine = PricingEngine(db)
            charge_result = await pricing_engine.calculate_and_charge(
                account_id=account.id, channel_id=channel.id,
                country_code=country_code, message=request.message,
            )
            if not charge_result['success']:
                failed += 1
                results.append({"phone_number": phone_number, "success": False,
                                "message_id": None, "error": {"code": "BILLING_ERROR", "message": charge_result.get('error', 'Billing failed')}})
                continue

            # 4. 创建短信记录
            message_id = f"msg_{uuid.uuid4().hex}"
            sms_log = SMSLog(
                message_id=message_id, account_id=account.id, channel_id=channel.id,
                phone_number=phone_info['e164_format'], country_code=country_code,
                message=request.message, message_count=charge_result['message_count'],
                status='queued', cost_price=charge_result['total_base_cost'],
                selling_price=charge_result['total_cost'], currency=charge_result['currency'],
                submit_time=datetime.now(),
            )
            db.add(sms_log)
            await db.flush()

            # 5. 入队异步发送
            QueueManager.queue_sms(message_id)

            succeeded += 1
            results.append({"phone_number": phone_number, "success": True,
                            "message_id": message_id, "error": None})

        except (InsufficientBalanceError, PricingNotFoundError, ChannelNotAvailableError) as e:
            failed += 1
            results.append({"phone_number": phone_number, "success": False,
                            "message_id": None, "error": {"code": e.error_code, "message": e.message}})
        except Exception as e:
            logger.error(f"批量发送单条失败: {phone_number}, {str(e)}")
            failed += 1
            results.append({"phone_number": phone_number, "success": False,
                            "message_id": None, "error": {"code": "ERROR", "message": "Send failed"}})

    return BatchSMSResponse(
        success=True,
        total=len(request.phone_numbers),
        succeeded=succeeded,
        failed=failed,
        messages=results
    )


# ============ 短信审核（Web 端与 Bot 同步） ============

async def _get_test_countries_for_account(db, account_id: int) -> str:
    """从账户绑定通道获取测试国家列表（审核消息不显示用户信息）"""
    from sqlalchemy import text
    from app.modules.common.account import AccountChannel

    try:
        ac_result = await db.execute(
            select(AccountChannel.channel_id).where(AccountChannel.account_id == account_id).order_by(AccountChannel.priority.desc())
        )
        channel_ids = [r[0] for r in ac_result.all()]
        if not channel_ids:
            return "-"
        placeholders = ",".join([str(int(cid)) for cid in channel_ids])
        sql = text(f"""
            SELECT DISTINCT cc.country_code, cc.country_name
            FROM channel_countries cc
            WHERE cc.channel_id IN ({placeholders}) AND cc.status = 'active'
            LIMIT 10
        """)
        raw = await db.execute(sql)
        rows = raw.all()
        if not rows:
            return "-"
        names = []
        seen = set()
        for r in rows:
            name = (r[1] or "").strip() or (r[0] or "")
            if name and name not in seen:
                seen.add(name)
                names.append(name)
        return "、".join(names) if names else "-"
    except Exception as e:
        logger.warning("获取账户测试国家失败: %s", e)
        return "-"


async def _forward_approval_to_telegram(approval_id: int, account_id: int, content: str, db) -> bool:
    """将审核消息转发到供应商群（仅显示测试国家+测试内容，不显示用户信息）"""
    import os
    import httpx
    from app.modules.common.sms_content_approval import SmsContentApproval
    from app.services.config_service import ConfigService

    configs = await ConfigService.get_by_category("telegram", db)
    bot_token = configs.get("telegram_bot_token") or os.getenv("TELEGRAM_BOT_TOKEN")
    admin_group_id = (configs.get("telegram_admin_group_id") or os.getenv("TELEGRAM_ADMIN_GROUP_ID") or "").strip()

    if not bot_token or not admin_group_id:
        logger.warning("未配置 telegram_bot_token 或 telegram_admin_group_id，无法转发审核")
        return False

    test_countries = await _get_test_countries_for_account(db, account_id)
    msg_text = (
        f"📋 *短信内容待审核*\n\n"
        f"🌍 测试国家: {test_countries}\n"
        f"📝 测试内容:\n{content[:500]}{'...' if len(content) > 500 else ''}"
    )
    payload = {
        "chat_id": int(admin_group_id),
        "text": msg_text,
        "parse_mode": "Markdown",
        "reply_markup": {
            "inline_keyboard": [[
                {"text": "✅ 通过", "callback_data": f"approve_sms_{approval_id}"},
                {"text": "❌ 拒绝", "callback_data": f"reject_sms_{approval_id}"},
            ]]
        }
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json=payload
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok") and data.get("result", {}).get("message_id"):
                    # 更新转发信息
                    result = await db.execute(select(SmsContentApproval).where(SmsContentApproval.id == approval_id))
                    a = result.scalar_one_or_none()
                    if a:
                        a.forwarded_to_group = admin_group_id
                        a.forwarded_message_id = data["result"]["message_id"]
                        await db.commit()
                    return True
            logger.error(f"Telegram 转发失败: {resp.status_code} {resp.text}")
    except Exception as e:
        logger.exception("转发审核到 Telegram 失败: %s", e)
    return False


@router.post("/approval")
async def submit_sms_approval(
    request: SMSApprovalSubmitRequest,
    account: Account = Depends(get_current_account_or_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    提交短信审核（Web 端）
    创建审核记录并转发到供应商群，审核通过后客户需在 Web 或 Bot 中点击「立即发送」
    """
    from app.modules.common.sms_content_approval import SmsContentApproval
    from app.services.config_service import ConfigService

    configs = await ConfigService.get_by_category("telegram", db)
    enable_review = (configs.get("telegram_enable_sms_content_review") or "true").lower() == "true"
    admin_group_id = (configs.get("telegram_admin_group_id") or "").strip()

    if not enable_review or not admin_group_id:
        raise HTTPException(
            status_code=400,
            detail="短信审核功能未启用或未配置供应商群，请直接使用发送接口"
        )

    # 验证号码和内容
    is_valid_phone, error_msg, phone_info = Validator.validate_phone_number(request.phone_number)
    if not is_valid_phone:
        raise HTTPException(status_code=400, detail=error_msg)
    is_valid_content, content_err, _ = Validator.validate_content(request.message)
    if not is_valid_content:
        raise HTTPException(status_code=400, detail=content_err)

    import secrets
    approval_no = f"SA{datetime.now().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(2).upper()}"
    approval = SmsContentApproval(
        approval_no=approval_no,
        account_id=account.id,
        tg_user_id="web",  # Web 端来源
        phone_number=phone_info["e164_format"],
        content=request.message,
        status="pending",
    )
    db.add(approval)
    await db.commit()
    await db.refresh(approval)

    ok = await _forward_approval_to_telegram(
        approval.id, account.id, approval.content, db
    )
    if not ok:
        raise HTTPException(status_code=500, detail="转发至供应商群失败，请稍后重试")

    return {
        "success": True,
        "approval_no": approval_no,
        "approval_id": approval.id,
        "message": "已提交审核，审核通过后会通知您，请点击「立即发送」进行发送"
    }


@router.get("/approvals")
async def list_sms_approvals(
    status: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    account_id: Optional[int] = None,
    auth_context: dict = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db)
):
    """获取当前账户的短信审核列表（管理员可传 account_id 查询指定账户）"""
    from app.modules.common.sms_content_approval import SmsContentApproval

    aid = auth_context.get("account_id") or account_id
    if not aid:
        raise HTTPException(status_code=401, detail="需要账户认证或指定 account_id")

    conditions = [SmsContentApproval.account_id == aid]
    if status:
        conditions.append(SmsContentApproval.status == status)

    result = await db.execute(
        select(SmsContentApproval)
        .where(*conditions)
        .order_by(SmsContentApproval.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = result.scalars().all()

    from sqlalchemy import func
    total_result = await db.execute(
        select(func.count(SmsContentApproval.id)).where(*conditions)
    )
    total = total_result.scalar() or 0

    return {
        "success": True,
        "total": total,
        "items": [
            {
                "id": a.id,
                "approval_no": a.approval_no,
                "phone_number": a.phone_number,
                "content": (a.content or "")[:100] + ("..." if len(a.content or "") > 100 else ""),
                "status": a.status,
                "reviewed_at": a.reviewed_at.isoformat() if a.reviewed_at else None,
                "reviewed_by_name": a.reviewed_by_name,
                "message_id": a.message_id,
                "send_error": a.send_error,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in items
        ]
    }


@router.post("/approval/{approval_id}/execute")
async def execute_approved_sms(
    approval_id: int,
    account: Account = Depends(get_current_account_or_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    执行审核通过的短信发送（客户点击「立即发送」）
    仅限审核状态为 approved 且未发送的记录
    """
    from app.modules.common.sms_content_approval import SmsContentApproval

    result = await db.execute(
        select(SmsContentApproval, Account)
        .join(Account, SmsContentApproval.account_id == Account.id)
        .where(SmsContentApproval.id == approval_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="审核记录不存在")

    approval, acc = row
    if approval.account_id != account.id:
        raise HTTPException(status_code=403, detail="无权操作此审核记录")

    if approval.status != "approved":
        raise HTTPException(status_code=400, detail="该短信未通过审核或已拒绝")

    if approval.message_id:
        raise HTTPException(status_code=400, detail="该短信已发送")

    # 调用发送逻辑（复用 send_sms 核心逻辑）
    from app.utils.validator import Validator
    is_valid_phone, _, phone_info = Validator.validate_phone_number(approval.phone_number)
    if not is_valid_phone:
        raise HTTPException(status_code=400, detail="号码格式无效")

    routing_engine = RoutingEngine(db)
    channel = await routing_engine.select_channel(
        country_code=phone_info["country_code"],
        account_id=account.id
    )
    if not channel:
        raise HTTPException(status_code=400, detail="无可用通道")

    pricing_engine = PricingEngine(db)
    charge_result = await pricing_engine.calculate_and_charge(
        account_id=account.id,
        channel_id=channel.id,
        country_code=phone_info["country_code"],
        message=approval.content
    )
    if not charge_result["success"]:
        raise HTTPException(status_code=400, detail=charge_result.get("error", "计费失败"))

    message_id = f"msg_{uuid.uuid4().hex}"
    sms_log = SMSLog(
        message_id=message_id,
        account_id=account.id,
        channel_id=channel.id,
        phone_number=phone_info["e164_format"],
        country_code=phone_info["country_code"],
        message=approval.content,
        message_count=charge_result["message_count"],
        status="queued",
        cost_price=charge_result["total_base_cost"],
        selling_price=charge_result["total_cost"],
        currency=charge_result["currency"],
        submit_time=datetime.now(),
    )
    db.add(sms_log)
    await db.flush()

    from app.utils.queue import QueueManager
    qm = QueueManager()
    qm.queue_sms(message_id)

    approval.message_id = message_id
    approval.send_error = None
    await db.commit()

    return {
        "success": True,
        "message_id": message_id,
        "cost": charge_result["total_cost"],
        "currency": charge_result.get("currency", "USD"),
        "message": "发送成功，可在发送记录中查看"
    }


@router.get("/stats")
async def get_sms_stats(
    auth_context: dict = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db)
):
    """
    获取短信发送统计
    
    返回今日发送数量、成功数量、成功率和消费金额
    """
    from sqlalchemy import func, and_
    from datetime import datetime, timedelta
    
    # 今天的开始时间
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # 构建查询条件
    conditions = [SMSLog.submit_time >= today_start]
    
    # 根据用户类型过滤
    if not auth_context["is_admin"]:
        conditions.append(SMSLog.account_id == auth_context["account_id"])
    
    # 查询今日总发送数
    count_query = select(func.count(SMSLog.id)).where(and_(*conditions))
    count_result = await db.execute(count_query)
    today_sent = count_result.scalar() or 0
    
    # 查询今日成功数
    success_conditions = conditions + [SMSLog.status == 'delivered']
    success_query = select(func.count(SMSLog.id)).where(and_(*success_conditions))
    success_result = await db.execute(success_query)
    today_success = success_result.scalar() or 0
    
    # 计算成功率
    success_rate = round((today_success / today_sent * 100) if today_sent > 0 else 0, 1)
    
    # 查询今日消费
    cost_query = select(func.coalesce(func.sum(SMSLog.selling_price), 0)).where(and_(*conditions))
    cost_result = await db.execute(cost_query)
    today_cost = float(cost_result.scalar() or 0)
    
    return {
        "success": True,
        "today_sent": today_sent,
        "today_success": today_success,
        "success_rate": success_rate,
        "today_cost": f"{today_cost:.2f}"
    }


@router.get("/records")
async def get_sms_records(
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    phone_number: Optional[str] = None,
    message_id: Optional[str] = None,
    channel_id: Optional[int] = None,
    country_code: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    account_id: Optional[int] = None,
    auth_context: dict = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db)
):
    """获取短信发送记录（带通道信息）"""
    from sqlalchemy import func, and_
    from sqlalchemy.orm import aliased
    from datetime import datetime
    from app.modules.sms.channel import Channel

    conditions = []

    if auth_context["is_admin"]:
        if account_id:
            conditions.append(SMSLog.account_id == account_id)
    else:
        conditions.append(SMSLog.account_id == auth_context["account_id"])

    if status:
        conditions.append(SMSLog.status == status)
    if phone_number:
        conditions.append(SMSLog.phone_number.like(f"%{phone_number}%"))
    if message_id:
        conditions.append(SMSLog.message_id.like(f"%{message_id}%"))
    if channel_id:
        conditions.append(SMSLog.channel_id == channel_id)
    if country_code:
        conditions.append(SMSLog.country_code == country_code)

    if start_date:
        try:
            conditions.append(SMSLog.submit_time >= datetime.strptime(start_date, "%Y-%m-%d"))
        except ValueError:
            pass
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            conditions.append(SMSLog.submit_time <= end_dt)
        except ValueError:
            pass

    where_clause = and_(*conditions) if conditions else True

    count_result = await db.execute(select(func.count(SMSLog.id)).where(where_clause))
    total = count_result.scalar() or 0

    offset = (page - 1) * page_size
    query = (
        select(SMSLog, Channel.channel_code, Channel.channel_name)
        .outerjoin(Channel, SMSLog.channel_id == Channel.id)
        .where(where_clause)
        .order_by(SMSLog.id.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(query)
    rows = result.all()

    return {
        "success": True,
        "total": total,
        "page": page,
        "page_size": page_size,
        "is_admin": auth_context["is_admin"],
        "records": [
            {
                "id": r.id,
                "message_id": r.message_id,
                "upstream_message_id": r.upstream_message_id,
                "account_id": r.account_id,
                "channel_id": r.channel_id,
                "channel_code": ch_code,
                "channel_name": ch_name,
                "batch_id": r.batch_id,
                "phone_number": r.phone_number,
                "country_code": r.country_code,
                "message": r.message,
                "message_count": r.message_count,
                "status": r.status,
                "cost_price": float(r.cost_price) if r.cost_price else 0,
                "selling_price": float(r.selling_price) if r.selling_price else 0,
                "profit": float(r.profit) if r.profit else 0,
                "currency": r.currency,
                "submit_time": r.submit_time.isoformat() if r.submit_time else None,
                "sent_time": r.sent_time.isoformat() if r.sent_time else None,
                "delivery_time": r.delivery_time.isoformat() if r.delivery_time else None,
                "error_message": r.error_message,
            }
            for r, ch_code, ch_name in rows
        ],
    }


@router.get("/records/export")
async def export_sms_records(
    status: Optional[str] = None,
    phone_number: Optional[str] = None,
    channel_id: Optional[int] = None,
    country_code: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    account_id: Optional[int] = None,
    auth_context: dict = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db)
):
    """导出发送记录为 CSV"""
    from sqlalchemy import and_
    from datetime import datetime
    from app.modules.sms.channel import Channel
    from fastapi.responses import StreamingResponse
    import csv
    import io

    conditions = []
    if auth_context["is_admin"]:
        if account_id:
            conditions.append(SMSLog.account_id == account_id)
    else:
        conditions.append(SMSLog.account_id == auth_context["account_id"])

    if status:
        conditions.append(SMSLog.status == status)
    if phone_number:
        conditions.append(SMSLog.phone_number.like(f"%{phone_number}%"))
    if channel_id:
        conditions.append(SMSLog.channel_id == channel_id)
    if country_code:
        conditions.append(SMSLog.country_code == country_code)
    if start_date:
        try:
            conditions.append(SMSLog.submit_time >= datetime.strptime(start_date, "%Y-%m-%d"))
        except ValueError:
            pass
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            conditions.append(SMSLog.submit_time <= end_dt)
        except ValueError:
            pass

    where_clause = and_(*conditions) if conditions else True

    query = (
        select(SMSLog, Channel.channel_code, Channel.channel_name)
        .outerjoin(Channel, SMSLog.channel_id == Channel.id)
        .where(where_clause)
        .order_by(SMSLog.id.desc())
        .limit(10000)
    )
    result = await db.execute(query)
    rows = result.all()

    output = io.StringIO()
    output.write('\ufeff')  # BOM for Excel
    writer = csv.writer(output)
    writer.writerow([
        "ID", "消息ID", "上游消息ID", "账户ID", "通道", "手机号",
        "国家", "内容", "条数", "状态", "成本价", "售价", "利润",
        "币种", "提交时间", "发送时间", "送达时间", "错误信息"
    ])

    for r, ch_code, ch_name in rows:
        writer.writerow([
            r.id, r.message_id, r.upstream_message_id or "", r.account_id,
            ch_code or "", r.phone_number, r.country_code or "",
            (r.message or "")[:200], r.message_count,
            r.status,
            float(r.cost_price) if r.cost_price else 0,
            float(r.selling_price) if r.selling_price else 0,
            float(r.profit) if r.profit else 0,
            r.currency or "USD",
            r.submit_time.strftime("%Y-%m-%d %H:%M:%S") if r.submit_time else "",
            r.sent_time.strftime("%Y-%m-%d %H:%M:%S") if r.sent_time else "",
            r.delivery_time.strftime("%Y-%m-%d %H:%M:%S") if r.delivery_time else "",
            r.error_message or "",
        ])

    output.seek(0)
    filename = f"sms_records_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ============ 上游 DLR 回调接口 (推送模式) ============

from fastapi import Request, Body
from app.core.dlr_handler import (
    parse_json_dlr, parse_xml_dlr, parse_form_dlr, 
    detect_and_parse_dlr, process_dlr_reports
)
from app.config import settings
import ipaddress as _ipaddress


def _verify_dlr_caller(request: Request) -> bool:
    """
    校验 DLR 回调请求来源：Token 或 IP 白名单。
    - DLR_CALLBACK_OPEN=true 时：允许所有回调（上游不支持认证时使用）
    - 否则需配置 Token 或 IP 白名单，至少满足其一
    """
    if getattr(settings, 'DLR_CALLBACK_OPEN', False):
        return True

    token_ok: Optional[bool] = None
    ip_ok: Optional[bool] = None
    client_ip = (
        request.headers.get("X-Real-IP")
        or (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )

    # Token 校验
    if settings.DLR_CALLBACK_TOKEN:
        req_token = (
            request.headers.get("X-DLR-Token")
            or request.query_params.get("dlr_token")
        )
        token_ok = (req_token == settings.DLR_CALLBACK_TOKEN)

    # IP 白名单校验
    allowed_ips = settings.dlr_callback_ip_list
    if allowed_ips:
        try:
            client_addr = _ipaddress.ip_address(client_ip)
            ip_ok = any(
                (client_addr in _ipaddress.ip_network(entry, strict=False))
                if "/" in entry
                else (client_addr == _ipaddress.ip_address(entry))
                for entry in allowed_ips
            )
        except ValueError:
            ip_ok = False

    # 两项都未配置 → 拒绝
    if token_ok is None and ip_ok is None:
        logger.warning(f"DLR回调认证失败: 未配置Token和IP白名单，拒绝请求 IP={client_ip}。可设置 DLR_CALLBACK_OPEN=true 或配置 Token/IP 白名单")
        return False
    # 任一通过即可
    if token_ok is True or ip_ok is True:
        return True
    return False


@router.post("/dlr/callback")
async def dlr_callback_post(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    接收上游 DLR (Delivery Report) 推送回调 - POST 方式
    
    支持多种格式：
    - JSON: {"mid":"xxx", "status":"delivered", ...}
    - XML: <report><mid>xxx</mid><status>delivered</status></report>
    - Form: mid=xxx&status=delivered
    
    认证方式（至少配置一项）：
    - Header: X-DLR-Token  或  Query: ?dlr_token=xxx
    - IP 白名单（环境变量 DLR_CALLBACK_IP_WHITELIST）
    """
    if not _verify_dlr_caller(request):
        logger.warning(f"DLR 回调认证失败: IP={request.client.host if request.client else 'unknown'}")
        return JSONResponse(
            status_code=403,
            content={"status": 1, "message": "Forbidden"}
        )

    try:
        content_type = request.headers.get('content-type', '')
        body = await request.body()
        body_text = body.decode('utf-8', errors='ignore')
        
        logger.info(f"收到 DLR 回调 (POST): content_type={content_type}, body={body_text[:500]}")
        
        # 解析 DLR 报告
        reports = []
        
        if 'json' in content_type:
            try:
                import json
                data = json.loads(body_text)
                reports = parse_json_dlr(data)
            except Exception as e:
                logger.warning(f"JSON 解析失败: {e}")
        
        elif 'xml' in content_type:
            reports = parse_xml_dlr(body_text)
        
        elif 'form' in content_type or 'urlencoded' in content_type:
            form_data = await request.form()
            reports = parse_form_dlr(dict(form_data))
        
        else:
            reports = detect_and_parse_dlr(body_text, content_type)
        
        if not reports:
            logger.warning(f"DLR 回调无法解析或无有效报告: {body_text[:200]}")
            return {"status": 0, "message": "no valid reports"}
        
        success, fail = await process_dlr_reports(reports, db, source="push")
        
        logger.info(f"DLR 回调处理完成: 成功={success}, 失败={fail}")
        return {"status": 0, "message": "success", "processed": success + fail}
        
    except Exception as e:
        logger.error(f"处理 DLR 回调失败: {str(e)}", exc_info=True)
        return {"status": 1, "message": "internal error"}


@router.get("/dlr/callback")
async def dlr_callback_get(
    request: Request,
    db: AsyncSession = Depends(get_db),
    mid: Optional[str] = None,
    msgid: Optional[str] = None,
    message_id: Optional[str] = None,
    taskid: Optional[str] = None,
    mobile: Optional[str] = None,
    phone: Optional[str] = None,
    to: Optional[str] = None,
    result: Optional[str] = None,
    status: Optional[str] = None,
    state: Optional[str] = None,
    errorcode: Optional[str] = None,
    error: Optional[str] = None,
    recvTime: Optional[str] = None,
    deliverytime: Optional[str] = None,
    time: Optional[str] = None,
):
    """
    接收上游 DLR 回调 (GET 方式)
    
    支持多种常见的 URL 参数名称，自动适配不同上游
    """
    if not _verify_dlr_caller(request):
        logger.warning(f"DLR GET 回调认证失败: IP={request.client.host if request.client else 'unknown'}")
        return JSONResponse(
            status_code=403,
            content={"status": 1, "message": "Forbidden"}
        )

    try:
        report = {
            'message_id': mid or msgid or message_id or taskid,
            'mobile': mobile or phone or to,
            'status_code': result or status or state,
            'error_code': errorcode or error,
            'delivery_time': recvTime or deliverytime or time,
        }
        
        query_string = str(request.query_params)
        logger.info(f"收到 DLR 回调 (GET): {query_string}")
        
        if not report['message_id']:
            logger.warning(f"DLR GET 回调缺少消息ID: {query_string}")
            return {"status": 0, "message": "missing message_id"}
        
        success, fail = await process_dlr_reports([report], db, source="push-get")
        
        return {"status": 0, "message": "success", "processed": success + fail}
        
    except Exception as e:
        logger.error(f"处理 DLR GET 回调失败: {str(e)}")
        return {"status": 1, "message": "internal error"}


@router.post("/dlr/callback/{channel_code}")
async def dlr_callback_by_channel(
    channel_code: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    按通道接收 DLR 回调
    
    URL 中包含通道编码，便于区分不同上游的回调
    例如: /api/v1/sms/dlr/callback/KAOLA_MO
    """
    logger.info(f"收到通道 {channel_code} 的 DLR 回调")
    return await dlr_callback_post(request, db)
