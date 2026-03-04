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
    BatchSMSResponse
)
from app.utils.logger import get_logger
from app.utils.errors import ValidationError, AuthenticationError
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
                    logger.info(f"管理员 {admin_id} 使用账户 {account.id} 发送短信")
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
        
        # 3. 路由选择通道
        routing_engine = RoutingEngine(db)
        channel = await routing_engine.select_channel(
            country_code=country_code,
            preferred_channel=request.channel_id,
            strategy='priority'
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
        await db.commit()
        
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
    except Exception as e:
        logger.error(f"发送短信失败: {str(e)}", exc_info=e)
        await db.rollback()
        return SMSSendResponse(
            success=False,
            error={"code": "INTERNAL_ERROR", "message": str(e)}
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
    """批量发送短信"""
    results = []
    succeeded = 0
    failed = 0
    
    for phone_number in request.phone_numbers:
        try:
            # 调用单条发送API
            single_request = SMSSendRequest(
                phone_number=phone_number,
                message=request.message,
                sender_id=request.sender_id, # 兼容旧参数
                callback_url=request.callback_url
            )
            
            response = await send_sms(single_request, account, db)
            
            if response.success:
                succeeded += 1
            else:
                failed += 1
            
            results.append({
                "phone_number": phone_number,
                "success": response.success,
                "message_id": response.message_id,
                "error": response.error
            })
            
        except Exception as e:
            failed += 1
            results.append({
                "phone_number": phone_number,
                "success": False,
                "error": {"code": "ERROR", "message": str(e)}
            })
    
    return BatchSMSResponse(
        success=True,
        total=len(request.phone_numbers),
        succeeded=succeeded,
        failed=failed,
        messages=results
    )


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
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    account_id: Optional[int] = None,
    auth_context: dict = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db)
):
    """
    获取短信发送记录
    
    - **page**: 页码（默认1）
    - **page_size**: 每页数量（默认20）
    - **status**: 状态过滤（可选）
    - **start_date**: 开始日期（可选，格式 YYYY-MM-DD）
    - **end_date**: 结束日期（可选，格式 YYYY-MM-DD）
    - **account_id**: 账户ID过滤（仅管理员可用）
    
    管理员可以查看所有记录，客户账户只能查看自己的记录
    """
    from sqlalchemy import func, and_
    from datetime import datetime
    
    # 构建查询条件
    conditions = []
    
    # 根据用户类型过滤
    if auth_context["is_admin"]:
        # 管理员可以查看所有记录，可选按账户ID过滤
        if account_id:
            conditions.append(SMSLog.account_id == account_id)
        logger.info(f"管理员查询发送记录, account_id filter: {account_id}")
    else:
        # 客户账户只能查看自己的记录
        conditions.append(SMSLog.account_id == auth_context["account_id"])
    
    if status:
        conditions.append(SMSLog.status == status)
    
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            conditions.append(SMSLog.submit_time >= start_dt)
        except ValueError:
            pass
    
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            # 包含结束日期的整天
            end_dt = end_dt.replace(hour=23, minute=59, second=59)
            conditions.append(SMSLog.submit_time <= end_dt)
        except ValueError:
            pass
    
    # 查询总数
    if conditions:
        count_query = select(func.count(SMSLog.id)).where(and_(*conditions))
    else:
        count_query = select(func.count(SMSLog.id))
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0
    
    # 查询记录
    offset = (page - 1) * page_size
    if conditions:
        query = select(SMSLog).where(
            and_(*conditions)
        ).order_by(SMSLog.id.desc()).offset(offset).limit(page_size)
    else:
        query = select(SMSLog).order_by(SMSLog.id.desc()).offset(offset).limit(page_size)
    
    result = await db.execute(query)
    records = result.scalars().all()
    
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
                "account_id": r.account_id,
                "phone_number": r.phone_number,
                "country_code": r.country_code,
                "message": r.message[:50] + "..." if r.message and len(r.message) > 50 else r.message,
                "message_count": r.message_count,
                "status": r.status,
                "cost": float(r.selling_price) if r.selling_price else 0,
                "currency": r.currency,
                "submit_time": r.submit_time.isoformat() if r.submit_time else None,
                "sent_time": r.sent_time.isoformat() if r.sent_time else None,
                "delivery_time": r.delivery_time.isoformat() if r.delivery_time else None,
                "error_message": r.error_message
            }
            for r in records
        ]
    }


# ============ 上游 DLR 回调接口 (推送模式) ============

from fastapi import Request, Body
from app.core.dlr_handler import (
    parse_json_dlr, parse_xml_dlr, parse_form_dlr, 
    detect_and_parse_dlr, process_dlr_reports
)


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
    
    支持多种字段名称，自动适配不同上游通道
    """
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
            # 自动检测格式
            reports = detect_and_parse_dlr(body_text, content_type)
        
        if not reports:
            logger.warning(f"DLR 回调无法解析或无有效报告: {body_text[:200]}")
            return {"status": 0, "message": "no valid reports"}
        
        # 处理报告
        success, fail = await process_dlr_reports(reports, db, source="push")
        
        logger.info(f"DLR 回调处理完成: 成功={success}, 失败={fail}")
        return {"status": 0, "message": "success", "processed": success + fail}
        
    except Exception as e:
        logger.error(f"处理 DLR 回调失败: {str(e)}", exc_info=True)
        return {"status": 1, "message": str(e)}


@router.get("/dlr/callback")
async def dlr_callback_get(
    request: Request,
    db: AsyncSession = Depends(get_db),
    # 常见字段名
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
    try:
        # 合并所有可能的字段
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
        
        # 处理报告
        success, fail = await process_dlr_reports([report], db, source="push-get")
        
        return {"status": 0, "message": "success", "processed": success + fail}
        
    except Exception as e:
        logger.error(f"处理 DLR GET 回调失败: {str(e)}")
        return {"status": 1, "message": str(e)}


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
