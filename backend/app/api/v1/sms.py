"""
短信发送API路由
"""
import asyncio
import json
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, BackgroundTasks, Header, HTTPException, Body
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, HTTPBasicCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.modules.common.account import Account
from app.modules.sms.sms_log import SMSLog
from app.core.auth import AuthService, api_key_header, optional_basic
from app.utils.validator import Validator
from app.utils.sms_template import render_sms_variables, sms_template_has_variables
from app.core.router import RoutingEngine
from app.core.pricing import PricingEngine
from app.schemas.sms import (
    SMSSendRequest,
    SMSSendResponse,
    SMSStatusResponse,
    BatchSMSRequest,
    BatchSMSResponse,
    SMSApprovalSubmitRequest,
    SMSApprovalExecuteRequest,
    PublicSMSRate,
    PublicSMSRateResponse,
)
from fastapi.responses import JSONResponse
from app.utils.logger import get_logger
from app.utils.errors import (
    ValidationError, AuthenticationError,
    InsufficientBalanceError, PricingNotFoundError, ChannelNotAvailableError
)
from decimal import Decimal
from sqlalchemy import select, update, func, or_, union_all
from app.modules.common.balance_log import BalanceLog
from app.modules.common.ticket import Ticket
from app.modules.common.account_template import AccountTemplate

logger = get_logger(__name__)


async def _refund_line_charge(
    db: AsyncSession,
    account_id: int,
    amount: float,
    description: str,
) -> None:
    """单条短信已扣费但后续失败（如入队失败）时退回余额"""
    if amount is None or float(amount) <= 0:
        return
    amt = Decimal(str(amount))
    await db.execute(
        update(Account).where(Account.id == account_id).values(balance=Account.balance + amt)
    )
    res = await db.execute(select(Account.balance).where(Account.id == account_id))
    bal = res.scalar()
    db.add(
        BalanceLog(
            account_id=account_id,
            change_type="refund",
            amount=float(amt),
            balance_after=float(bal) if bal is not None else 0.0,
            description=description[:500],
        )
    )
    await db.flush()
    try:
        from app.utils.cache import get_cache_manager

        cm = await get_cache_manager()
        await cm.set(f"account:{account_id}:balance", float(bal) if bal is not None else 0.0, ttl=60)
    except Exception:
        pass
router = APIRouter()

# Optional bearer token for admin access
optional_bearer = HTTPBearer(auto_error=False)


async def get_current_account_or_admin(
    api_key: Optional[str] = Depends(api_key_header),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_bearer),
    basic_creds: Optional[HTTPBasicCredentials] = Depends(optional_basic),
    db: AsyncSession = Depends(get_db)
) -> Account:
    """
    获取当前认证账户 - 支持多种认证方式

    优先级：API Key > HTTP Basic Auth (用户名+密码) > JWT Token (管理员)
    """
    # 1. 优先使用 API Key
    if api_key:
        try:
            return await AuthService.verify_api_key(api_key, db)
        except AuthenticationError:
            pass

    # 2. HTTP Basic Auth（account_name/email + password）
    if basic_creds and basic_creds.username:
        try:
            return await AuthService.verify_basic_credentials(basic_creds, db)
        except AuthenticationError:
            pass

    # 3. 尝试使用 JWT Token（管理员模式）
    if credentials and credentials.credentials:
        try:
            payload = AuthService.verify_token(credentials.credentials)
            admin_id = payload.get("sub")
            if admin_id:
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
    
    # 4. 都失败了
    raise AuthenticationError("Missing API Key, credentials or token")


async def get_auth_context(
    api_key: Optional[str] = Depends(api_key_header),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_bearer),
    basic_creds: Optional[HTTPBasicCredentials] = Depends(optional_basic),
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

    # 3. HTTP Basic Auth（account_name/email + password）
    if basic_creds and basic_creds.username:
        try:
            account = await AuthService.verify_basic_credentials(basic_creds, db)
            context["account"] = account
            context["account_id"] = account.id
            return context
        except AuthenticationError:
            pass

    # 4. 都失败了
    raise AuthenticationError("Missing API Key, credentials or token")


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

        from app.utils.account_country_restrict import assert_sms_destination_allowed, AccountCountryNotAllowedError
        try:
            assert_sms_destination_allowed(account, country_code)
        except AccountCountryNotAllowedError as e:
            return SMSSendResponse(
                success=False,
                error={"code": "COUNTRY_NOT_ALLOWED", "message": e.message},
            )

        # 2. 内置变量替换（{随机码} 等）后再校验长度与计费
        final_message = (
            render_sms_variables(
                request.message,
                index=1,
                phone_e164=phone_info["e164_format"],
                country_code=country_code,
            )
            if sms_template_has_variables(request.message)
            else request.message
        )

        is_valid_content, error_msg, content_info = Validator.validate_content(final_message)
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
            message=final_message
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
            message=final_message,
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

        # Worker 使用独立 DB 连接，须先提交本事务，否则可能读不到未提交的 SMSLog（Message not found → 永久 queued）
        await db.commit()

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
            logger.error(f"加入队列失败，已退款并标记失败: {message_id}")
            await _refund_line_charge(
                db,
                account.id,
                charge_result["total_cost"],
                f"SMS入队失败退款 {message_id}",
            )
            await db.execute(
                update(SMSLog)
                .where(SMSLog.message_id == message_id)
                .values(
                    status="failed",
                    error_message="加入发送队列失败，请检查 RabbitMQ 与 Celery worker-sms 是否运行",
                )
            )
            await db.flush()
            return SMSSendResponse(
                success=False,
                message_id=message_id,
                error={
                    "code": "QUEUE_FAILED",
                    "message": "加入发送队列失败，请检查消息队列与短信 Worker（worker-sms）",
                },
            )

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

    先创建发送任务（sms_batches），再预校验号码并批量创建记录、扣费，然后统一入队异步发送；
    与发送任务页（批量列表）打通，便于查看进度。
    """
    from app.utils.queue import QueueManager
    from app.modules.sms.sms_batch import SmsBatch, BatchStatus

    results = []
    succeeded = 0
    failed = 0

    # 1. 如果提供了私有库过滤条件，从中展开号码（私库表 + 公海购入绑定到本账户的 data_numbers）
    if request.private_library_filters:
        from app.modules.data.models import DataNumber, PrivateLibraryNumber
        from app.api.v1.data.customer import (
            _sql_dim_ci_trim_eq,
            _sql_dim_source_match,
            _sql_dim_purpose_match,
        )

        f = dict(request.private_library_filters)
        from app.utils.account_country_restrict import account_country_iso
        from app.utils.country_code import normalize_country_code

        acc_iso = account_country_iso(account)
        if acc_iso:
            pf_cc = f.get("country_code")
            if pf_cc:
                if normalize_country_code(str(pf_cc)) != acc_iso:
                    return BatchSMSResponse(
                        success=False,
                        total=0,
                        succeeded=0,
                        failed=0,
                        messages=[],
                        batch_id=None,
                        error={
                            "code": "COUNTRY_NOT_ALLOWED",
                            "message": f"当前账户仅允许使用 {acc_iso} 国家/地区的号码，私库筛选国家与账户不一致",
                        },
                    )
            else:
                f["country_code"] = acc_iso
        try:
            _lim = int(f.get("limit", 50000))
        except (TypeError, ValueError):
            _lim = 50000
        if _lim <= 0:
            return BatchSMSResponse(
                success=False,
                total=0,
                succeeded=0,
                failed=0,
                messages=[],
                batch_id=None,
                error={
                    "code": "INVALID_LIMIT",
                    "message": "发送条数须大于 0；若勾选「仅未使用」后可用为 0，请取消筛选或更换分组。",
                },
            )

        def _carrier_clause(col, car_raw: str):
            """运营商筛选条件（PLN / DN 共用）"""
            car = str(car_raw).strip()
            if not car:
                return None
            _trimmed = func.lower(func.trim(func.coalesce(col, "")))
            if car.lower() not in ("unknown", "未知"):
                _cl = car.lower()
                return or_(_trimmed.like(_cl + "%"), _trimmed.like("%" + _cl + "%"))
            return or_(
                func.trim(func.coalesce(col, "")) == "",
                _trimmed.in_(("unknown", "未知")),
            )

        def _apply_dims(q, model, *, include_batch: bool = True):
            """国家/批次/来源/用途/运营商/仅未使用 公共过滤"""
            if f.get("country_code"):
                q = q.where(_sql_dim_ci_trim_eq(model.country_code, f["country_code"]))
            if include_batch and f.get("batch_id") is not None:
                bid = str(f["batch_id"]).strip()
                if bid:
                    q = q.where(_sql_dim_ci_trim_eq(model.batch_id, bid))
            if f.get("source"):
                q = q.where(_sql_dim_source_match(model.source, f["source"]))
            if f.get("purpose"):
                q = q.where(_sql_dim_purpose_match(model.purpose, f["purpose"]))
            if f.get("carrier"):
                cc = _carrier_clause(model.carrier, f["carrier"])
                if cc is not None:
                    q = q.where(cc)
            if f.get("unused_only"):
                # use_count 在历史数据里可能为 NULL（早期上传未初始化默认值），
                # NULL 与 0 在 SQL 比较里不相等 → 必须同时兼容两种写法
                q = q.where(or_(model.use_count == 0, model.use_count.is_(None)))
            return q

        def _build_union(include_batch: bool = True):
            q_pln = _apply_dims(
                select(PrivateLibraryNumber.phone_number).where(
                    PrivateLibraryNumber.account_id == account.id,
                    PrivateLibraryNumber.is_deleted == False,  # noqa: E712
                ),
                PrivateLibraryNumber,
                include_batch=include_batch,
            )
            q_dn = _apply_dims(
                select(DataNumber.phone_number).where(
                    DataNumber.account_id == account.id,
                ),
                DataNumber,
                include_batch=include_batch,
            )
            return union_all(q_pln, q_dn).subquery()

        limit = _lim
        u = _build_union(include_batch=True)
        res = await db.execute(select(u.c.phone_number).distinct().limit(limit))
        db_nums = [r[0] for r in res.all()]

        # 兜底：batch_id 过滤后为空（汇总表与明细不一致时），去掉 batch_id 再查一次
        if not db_nums and f.get("batch_id"):
            logger.warning(
                "私库取号: batch_id=%s 无结果, 回退去掉 batch_id 重试 account=%s",
                f.get("batch_id"), account.id,
            )
            u2 = _build_union(include_batch=False)
            res2 = await db.execute(select(u2.c.phone_number).distinct().limit(limit))
            db_nums = [r[0] for r in res2.all()]
        if db_nums:
            now = datetime.now()
            BATCH_SZ = 2000

            for ci in range(0, len(db_nums), BATCH_SZ):
                chunk = db_nums[ci:ci + BATCH_SZ]
                await db.execute(
                    update(PrivateLibraryNumber)
                    .where(
                        PrivateLibraryNumber.account_id == account.id,
                        PrivateLibraryNumber.phone_number.in_(chunk),
                        PrivateLibraryNumber.is_deleted == False,  # noqa: E712
                    )
                    .values(
                        use_count=PrivateLibraryNumber.use_count + 1,
                        last_used_at=now,
                    )
                )
                await db.execute(
                    update(DataNumber)
                    .where(
                        DataNumber.account_id == account.id,
                        DataNumber.phone_number.in_(chunk),
                    )
                    .values(
                        use_count=DataNumber.use_count + 1,
                        last_used_at=now,
                    )
                )
            await db.flush()

            from app.utils.data_customer_cache import invalidate_my_numbers_summary_cache
            await invalidate_my_numbers_summary_cache(account.id)

            from app.workers.celery_app import celery_app as _celery_pls
            _celery_pls.send_task(
                "private_library_sync_used",
                args=[account.id, db_nums],
                queue="data_tasks",
            )

            if not request.phone_numbers:
                request.phone_numbers = []
            request.phone_numbers.extend(db_nums)

    if not request.phone_numbers or len(request.phone_numbers) == 0:
        _empty_err = None
        if request.private_library_filters:
            _empty_err = {
                "code": "NO_NUMBERS",
                "message": (
                    "未找到符合条件的私有库号码。请检查：运营商筛选、「仅未使用」、批次是否与当前卡片一致；"
                    "或刷新「我的号码」后重试。"
                ),
            }
        return BatchSMSResponse(
            success=False,
            total=0,
            succeeded=0,
            failed=0,
            messages=[],
            batch_id=None,
            error=_empty_err,
        )

    rot_messages = [m for m in (request.messages or []) if m and str(m).strip()]
    use_rotate = len(rot_messages) > 0
    total_numbers = len(request.phone_numbers)

    # === 余额预检 ===
    # 防止「余额远小于估算总额 → worker 跑完只发出极少部分 → 批次卡 processing 不结束」（参考 batch 352 事故）。
    # 估算口径：抽样首个国家 + 通道，按当前账户单价 × 段数 × 总数。多国混发场景为近似值；价格不可知时跳过预检。
    _est_country: Optional[str] = None
    if request.private_library_filters and request.private_library_filters.get("country_code"):
        _est_country = str(request.private_library_filters["country_code"]).strip().upper() or None
    if not _est_country:
        for _p in request.phone_numbers[:50]:
            _ok, _, _info = Validator.validate_phone_number(str(_p).strip())
            if _ok:
                _est_country = (_info.get("country_code") or "").strip() or None
                if _est_country:
                    break

    _est_price: Optional[float] = None
    _est_currency = "USD"
    if _est_country:
        _pricing_chk = PricingEngine(db)
        _ch_for_est = request.channel_id
        if not _ch_for_est:
            try:
                _ch_obj = await RoutingEngine(db).select_channel(
                    country_code=_est_country, strategy='priority', account_id=account.id,
                )
                if _ch_obj:
                    _ch_for_est = _ch_obj.id
            except Exception:
                _ch_for_est = None
        if _ch_for_est:
            try:
                _pi = await _pricing_chk.get_price(_ch_for_est, _est_country, None, account.id)
                if _pi and _pi.get("price"):
                    _est_price = float(_pi["price"])
                    _est_currency = _pi.get("currency", "USD")
            except Exception:
                pass

    if _est_price and _est_price > 0:
        _msg_for_estimate = max(rot_messages, key=len) if rot_messages else request.message
        _parts = max(1, PricingEngine(db)._count_sms_parts(_msg_for_estimate))
        _est_total = total_numbers * _parts * _est_price
        _bal_row = await db.execute(select(Account.balance).where(Account.id == account.id))
        _bal = float(_bal_row.scalar() or 0)
        if _bal < _est_total:
            return BatchSMSResponse(
                success=False, total=total_numbers, succeeded=0, failed=0,
                messages=[], batch_id=None,
                error={
                    "code": "INSUFFICIENT_BALANCE",
                    "message": (
                        f"余额不足：当前 {_bal:.4f} {_est_currency}，"
                        f"预估需要 {_est_total:.4f} {_est_currency}（{total_numbers} 条 × "
                        f"{_parts} 段 × {_est_price:.4f}）。请充值后重试。"
                    ),
                    "balance": round(_bal, 4),
                    "estimated_cost": round(_est_total, 4),
                    "currency": _est_currency,
                    "total_count": total_numbers,
                    "parts_per_sms": _parts,
                    "price_per_part": round(_est_price, 6),
                },
            )

    batch_label = (request.batch_name or "").strip() or f"发送页-{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    sms_batch = SmsBatch(
        account_id=account.id,
        batch_name=batch_label[:200],
        total_count=total_numbers,
        success_count=0,
        failed_count=0,
        status=BatchStatus.PROCESSING,
        sender_id=request.sender_id,
    )
    db.add(sms_batch)
    await db.flush()
    batch_pk = sms_batch.id

    ASYNC_THRESHOLD = 10
    # 与 batch_worker 写库分片对齐，减少 Celery 任务数、缩短 HTTP 内同步调度时间
    CHUNK_SIZE = 5000

    if total_numbers > ASYNC_THRESHOLD:
        # ========== 大批量：异步分片处理 ==========
        from app.workers.batch_worker import process_batch_chunk

        phones = request.phone_numbers
        rot = rot_messages if use_rotate else []

        def _enqueue_all_batch_chunks() -> int:
            """在线程中执行大量 .delay()，避免阻塞事件循环。"""
            n = 0
            for offset in range(0, total_numbers, CHUNK_SIZE):
                chunk = phones[offset : offset + CHUNK_SIZE]
                process_batch_chunk.delay(
                    batch_pk,
                    account.id,
                    chunk,
                    request.message,
                    rot,
                    offset,
                    request.channel_id,
                    request.sender_id,
                )
                n += 1
            return n

        chunk_count = await asyncio.to_thread(_enqueue_all_batch_chunks)

        sms_batch.send_config = {"chunks": chunk_count, "chunk_size": CHUNK_SIZE, "async": True}
        await db.commit()

        logger.info(f"批量发送已进入后台加速处理: batch_id={batch_pk}, total={total_numbers}, chunks={chunk_count}")
        return BatchSMSResponse(
            success=True,
            total=total_numbers,
            succeeded=0,
            failed=0,
            messages=[],
            batch_id=batch_pk,
            async_processing=True,
        )

    # ========== 极小批量（≤10）：保持同步处理（也进行窗口化优化） ==========
    from app.utils.account_country_restrict import assert_sms_destination_allowed, AccountCountryNotAllowedError
    
    # 预创建所需的 log 记录（暂时不入队）
    valid_logs_mids = []
    
    for batch_index, phone_number in enumerate(request.phone_numbers, start=1):
        try:
            is_valid, err_msg, phone_info = Validator.validate_phone_number(phone_number)
            if not is_valid:
                failed += 1
                results.append({"phone_number": phone_number, "success": False,
                                "message_id": None, "error": {"code": "INVALID_PHONE", "message": err_msg}})
                continue

            country_code = phone_info['country_code']

            try:
                assert_sms_destination_allowed(account, country_code)
            except AccountCountryNotAllowedError as e:
                failed += 1
                results.append({
                    "phone_number": phone_number, "success": False,
                    "message_id": None, "error": {"code": "COUNTRY_NOT_ALLOWED", "message": e.message},
                })
                continue

            raw_body = rot_messages[(batch_index - 1) % len(rot_messages)] if use_rotate else request.message
            has_tpl_vars = sms_template_has_variables(raw_body)
            final_message = (
                render_sms_variables(
                    raw_body,
                    index=batch_index,
                    phone_e164=phone_info["e164_format"],
                    country_code=country_code,
                )
                if has_tpl_vars
                else raw_body
            )
            is_valid_content, content_err, _ = Validator.validate_content(final_message)
            if not is_valid_content:
                failed += 1
                results.append({"phone_number": phone_number, "success": False,
                                "message_id": None, "error": {"code": "INVALID_CONTENT", "message": content_err}})
                continue

            routing_engine = RoutingEngine(db)
            channel = await routing_engine.select_channel(
                country_code=country_code,
                preferred_channel=request.channel_id,
                strategy='priority',
                account_id=account.id
            )
            if not channel:
                failed += 1
                results.append({"phone_number": phone_number, "success": False,
                                "message_id": None, "error": {"code": "NO_CHANNEL", "message": "No available channel"}})
                continue

            pricing_engine = PricingEngine(db)
            charge_result = await pricing_engine.calculate_and_charge(
                account_id=account.id, channel_id=channel.id,
                country_code=country_code, message=final_message,
            )
            if not charge_result['success']:
                failed += 1
                results.append({"phone_number": phone_number, "success": False,
                                "message_id": None, "error": {"code": "BILLING_ERROR", "message": charge_result.get('error', 'Billing failed')}})
                continue

            message_id = f"msg_{uuid.uuid4().hex}"
            sms_log = SMSLog(
                message_id=message_id, account_id=account.id, channel_id=channel.id,
                phone_number=phone_info['e164_format'], country_code=country_code,
                message=final_message, message_count=charge_result['message_count'],
                status='queued', cost_price=charge_result.get('total_base_cost', 0),
                selling_price=charge_result.get('total_cost', 0), currency=charge_result.get('currency', 'USD'),
                submit_time=datetime.now(),
                batch_id=batch_pk,
            )
            db.add(sms_log)
            valid_logs_mids.append((message_id, phone_number, channel))

        except (InsufficientBalanceError, PricingNotFoundError, ChannelNotAvailableError) as e:
            failed += 1
            results.append({"phone_number": phone_number, "success": False,
                            "message_id": None, "error": {"code": e.error_code, "message": e.message}})
        except Exception as e:
            logger.error(f"批量发送单条失败: {phone_number}, {str(e)}")
            failed += 1
            results.append({"phone_number": phone_number, "success": False,
                            "message_id": None, "error": {"code": "ERROR", "message": "Send failed"}})

    # 统一提交记录，然后批量入队
    if valid_logs_mids:
        await db.commit()
        # 极小批量：按协议分 SMPP（直投 sms_send_smpp）与其它（sms_send）
        smpp_ids = []
        other_ids = []
        for mid, phone, chan in valid_logs_mids:
            if 'SMPP' in str(chan.protocol).upper():
                smpp_ids.append((mid, phone))
            else:
                other_ids.append((mid, phone))
        
        # 处理 SMPP 批量
        if smpp_ids:
            mids_only = [m[0] for m in smpp_ids]
            from app.utils.smpp_payload import smpp_payload_public_dict

            _log_rows = (
                await db.execute(select(SMSLog).where(SMSLog.message_id.in_(mids_only)))
            ).scalars().all()
            _bs_snap = ""
            if batch_pk:
                _bstat = await db.execute(select(SmsBatch.status).where(SmsBatch.id == batch_pk))
                _br = _bstat.scalar_one_or_none()
                _bs_snap = getattr(_br, "value", str(_br or ""))
            _by_mid = {r.message_id: r for r in _log_rows}
            smpp_payloads = [
                smpp_payload_public_dict(_by_mid[mid], _bs_snap)
                for mid in mids_only
                if mid in _by_mid
            ]
            if smpp_payloads and QueueManager.queue_sms_batch_smpp(smpp_payloads):
                for mid, phone in smpp_ids:
                    succeeded += 1
                    results.append({"phone_number": phone, "success": True, "message_id": mid, "error": None})
            else:
                for mid, phone in smpp_ids:
                    row = _by_mid.get(mid)
                    if row and QueueManager.queue_smpp_gateway(smpp_payload_public_dict(row, _bs_snap)):
                        succeeded += 1
                        results.append({"phone_number": phone, "success": True, "message_id": mid, "error": None})
                    else:
                        failed += 1
                        results.append({"phone_number": phone, "success": False, "message_id": mid, "error": "入队失败"})

        # 处理其他（HTTP等）
        for mid, phone in other_ids:
            if QueueManager.queue_sms(mid):
                succeeded += 1
                results.append({"phone_number": phone, "success": True, "message_id": mid, "error": None})
            else:
                failed += 1
                results.append({"phone_number": phone, "success": False, "message_id": mid, "error": "入队失败"})


    cnt_row = await db.execute(
        select(func.count()).select_from(SMSLog).where(SMSLog.batch_id == batch_pk)
    )
    sms_batch.total_count = int(cnt_row.scalar() or 0)
    if succeeded == 0:
        sms_batch.status = BatchStatus.FAILED
        sms_batch.progress = 0
        sms_batch.error_message = "没有成功入队的短信（号码、内容、余额或通道等原因）"
    else:
        # 入队成功 ≠ 发送完成（SMPP 多跳后才有 sent）；由 sms_logs 驱动批次终态
        from app.modules.sms.batch_utils import update_batch_progress

        await update_batch_progress(db, batch_pk)
        await db.refresh(sms_batch)
        if sms_batch.status not in (BatchStatus.COMPLETED, BatchStatus.FAILED, BatchStatus.CANCELLED):
            sms_batch.status = BatchStatus.PROCESSING
            sms_batch.completed_at = None

    await db.commit()

    return BatchSMSResponse(
        success=True,
        total=total_numbers,
        succeeded=succeeded,
        failed=failed,
        messages=results,
        batch_id=batch_pk,
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

    is_valid_content, content_err, _ = Validator.validate_content(request.message)
    if not is_valid_content:
        raise HTTPException(status_code=400, detail=content_err)

    phone_e164 = None
    if request.phone_number:
        is_valid_phone, error_msg, phone_info = Validator.validate_phone_number(request.phone_number)
        if not is_valid_phone:
            raise HTTPException(status_code=400, detail=error_msg)
        phone_e164 = phone_info["e164_format"]

    import secrets
    approval_no = f"SA{datetime.now().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(2).upper()}"
    approval = SmsContentApproval(
        approval_no=approval_no,
        account_id=account.id,
        tg_user_id="web",
        phone_number=phone_e164,
        content=request.message,
        status="pending",
    )
    db.add(approval)
    await db.flush()

    ticket_no = f"TK{datetime.now().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(2).upper()}"
    sms_ticket = Ticket(
        ticket_no=ticket_no,
        account_id=account.id,
        tg_user_id="web",
        ticket_type="test",
        priority="normal",
        title=f"短信审核-{approval_no}",
        description=f"内容: {(request.message or '')[:500]}",
        status="open",
        created_by_type="account",
        created_by_id=account.id,
        test_phone=phone_e164,
        test_content=request.message,
        review_status="pending",
        forwarded_to_group=admin_group_id if admin_group_id else None,
        extra_data={"sms_approval_id": approval.id},
    )
    db.add(sms_ticket)
    await db.commit()
    await db.refresh(approval)
    await db.refresh(sms_ticket)
    ticket_row_id = sms_ticket.id

    ok = await _forward_approval_to_telegram(
        approval.id, account.id, approval.content, db
    )
    if not ok:
        raise HTTPException(status_code=500, detail="转发至供应商群失败，请稍后重试")

    a2 = await db.get(SmsContentApproval, approval.id)
    t2 = await db.get(Ticket, ticket_row_id)
    if a2 and t2:
        t2.forwarded_to_group = a2.forwarded_to_group
        t2.forwarded_message_id = a2.forwarded_message_id
        if a2.forwarded_to_group:
            t2.review_status = "forwarded"
        await db.commit()

    return {
        "success": True,
        "approval_no": approval_no,
        "approval_id": approval.id,
        "ticket_no": ticket_no,
        "message": "已提交审核，工单已同步生成，审核通过后可前往发送页发送",
    }


@router.delete("/approval/{approval_id}")
async def delete_sms_approval(
    approval_id: int,
    account: Account = Depends(get_current_account_or_admin),
    db: AsyncSession = Depends(get_db),
):
    """删除短信审核记录（未发送才可删）；关联测试工单将标记为已取消"""
    from app.modules.common.sms_content_approval import SmsContentApproval

    result = await db.execute(
        select(SmsContentApproval).where(SmsContentApproval.id == approval_id)
    )
    approval = result.scalar_one_or_none()
    if not approval:
        raise HTTPException(status_code=404, detail="审核记录不存在")
    if approval.account_id != account.id:
        raise HTTPException(status_code=403, detail="无权删除此审核记录")
    if approval.message_id:
        raise HTTPException(status_code=400, detail="已发送的审核记录不可删除")

    tres = await db.execute(
        select(Ticket)
        .where(
            Ticket.account_id == account.id,
            Ticket.ticket_type == "test",
        )
        .order_by(Ticket.created_at.desc())
    )
    for tick in tres.scalars().all():
        ex = tick.extra_data or {}
        if ex.get("sms_approval_id") == approval.id:
            if tick.status in ("open", "assigned", "in_progress", "pending_user"):
                tick.status = "cancelled"
                tick.closed_at = datetime.now()
                tick.close_reason = "用户删除短信审核"
            break

    await db.delete(approval)
    await db.commit()
    return {"success": True, "message": "已删除"}


@router.get("/approvals")
async def list_sms_approvals(
    status: Optional[str] = None,
    search: Optional[str] = None,
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
    if search and (s := search.strip()):
        pat = f"%{s}%"
        conditions.append(
            or_(
                SmsContentApproval.phone_number.ilike(pat),
                SmsContentApproval.content.ilike(pat),
                SmsContentApproval.approval_no.ilike(pat),
            )
        )

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


@router.get("/approvals/{approval_id}")
async def get_sms_approval_detail(
    approval_id: int,
    account: Account = Depends(get_current_account_or_admin),
    db: AsyncSession = Depends(get_db),
):
    """单条审核详情（含完整短信内容，供发送页预填）"""
    from app.modules.common.sms_content_approval import SmsContentApproval

    result = await db.execute(
        select(SmsContentApproval).where(SmsContentApproval.id == approval_id)
    )
    a = result.scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="审核记录不存在")
    if a.account_id != account.id:
        raise HTTPException(status_code=403, detail="无权查看此审核记录")
    return {
        "success": True,
        "id": a.id,
        "approval_no": a.approval_no,
        "phone_number": a.phone_number,
        "content": a.content or "",
        "status": a.status,
        "reviewed_at": a.reviewed_at.isoformat() if a.reviewed_at else None,
        "message_id": a.message_id,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@router.post("/approval/{approval_id}/execute")
async def execute_approved_sms(
    approval_id: int,
    exec_body: SMSApprovalExecuteRequest = Body(default_factory=SMSApprovalExecuteRequest),
    account: Account = Depends(get_current_account_or_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    执行审核通过的短信发送（客户点击「立即发送」）
    仅限审核状态为 approved 且未发送的记录。
    若审核记录无号码（如 Telegram 仅文案审核），须在请求体中传 phone_number。
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

    # 号码：记录已有则用记录；否则使用本次请求补传的号码（规范化后写回库）
    stored = (approval.phone_number or "").strip()
    incoming = (exec_body.phone_number or "").strip()
    if stored:
        phone_raw = stored
    else:
        phone_raw = incoming
        if not phone_raw:
            raise HTTPException(
                status_code=400,
                detail="该审核未保存接收号码，请在请求中填写目标号码（E.164，如 +8613800138000）后再发送",
            )
    is_valid_phone, err_msg, phone_info = Validator.validate_phone_number(phone_raw)
    if not is_valid_phone:
        raise HTTPException(status_code=400, detail=err_msg or "号码格式无效")
    from app.utils.account_country_restrict import assert_sms_destination_allowed, AccountCountryNotAllowedError
    try:
        assert_sms_destination_allowed(account, phone_info["country_code"])
    except AccountCountryNotAllowedError as e:
        raise HTTPException(status_code=400, detail=e.message)
    if not stored and phone_info.get("e164_format"):
        approval.phone_number = phone_info["e164_format"]
        await db.flush()

    routing_engine = RoutingEngine(db)
    channel = await routing_engine.select_channel(
        country_code=phone_info["country_code"],
        account_id=account.id
    )
    if not channel:
        raise HTTPException(status_code=400, detail="无可用通道")

    final_message = (
        render_sms_variables(
            approval.content,
            index=1,
            phone_e164=phone_info["e164_format"],
            country_code=phone_info["country_code"],
        )
        if sms_template_has_variables(approval.content)
        else approval.content
    )
    is_valid_content, content_err, _ = Validator.validate_content(final_message)
    if not is_valid_content:
        raise HTTPException(status_code=400, detail=content_err or "内容校验失败")

    pricing_engine = PricingEngine(db)
    charge_result = await pricing_engine.calculate_and_charge(
        account_id=account.id,
        channel_id=channel.id,
        country_code=phone_info["country_code"],
        message=final_message
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
        message=final_message,
        message_count=charge_result["message_count"],
        status="queued",
        cost_price=charge_result["total_base_cost"],
        selling_price=charge_result["total_cost"],
        currency=charge_result["currency"],
        submit_time=datetime.now(),
    )
    db.add(sms_log)
    await db.flush()
    await db.commit()

    from app.utils.queue import QueueManager

    if not QueueManager.queue_sms(message_id):
        await _refund_line_charge(
            db,
            account.id,
            charge_result["total_cost"],
            f"审核短信入队失败退款 {message_id}",
        )
        await db.execute(
            update(SMSLog)
            .where(SMSLog.message_id == message_id)
            .values(status="failed", error_message="加入发送队列失败")
        )
        approval.send_error = "加入发送队列失败，请检查 RabbitMQ 与 worker-sms"
        await db.commit()
        raise HTTPException(status_code=503, detail="加入发送队列失败，请稍后重试或联系管理员")

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
    batch_id: Optional[int] = None,
    auth_context: dict = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db)
):
    """获取短信发送记录（带通道信息、客户名称、归属员工）"""
    from sqlalchemy import func, and_
    from sqlalchemy.orm import aliased
    from datetime import datetime
    from app.modules.sms.channel import Channel
    from app.modules.sms.sms_batch import SmsBatch
    from app.modules.common.account import Account
    from app.modules.common.admin_user import AdminUser

    SalesUser = aliased(AdminUser)

    conditions = []

    if auth_context["is_admin"]:
        if account_id:
            conditions.append(SMSLog.account_id == account_id)
    else:
        conditions.append(SMSLog.account_id == auth_context["account_id"])

    # 按批次筛选：非管理员须校验批次归属，避免遍历他人 batch_id
    if batch_id is not None:
        if auth_context["is_admin"]:
            conditions.append(SMSLog.batch_id == batch_id)
        else:
            own_batch = await db.scalar(
                select(SmsBatch.id).where(
                    SmsBatch.id == batch_id,
                    SmsBatch.account_id == auth_context["account_id"],
                    SmsBatch.is_deleted == False,
                )
            )
            if own_batch is None:
                conditions.append(SMSLog.id < 0)
            else:
                conditions.append(SMSLog.batch_id == batch_id)

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
        select(
            SMSLog,
            Channel.channel_code,
            Channel.channel_name,
            Account.account_name,
            SalesUser.real_name.label("sales_name"),
        )
        .outerjoin(Channel, SMSLog.channel_id == Channel.id)
        .outerjoin(Account, SMSLog.account_id == Account.id)
        .outerjoin(SalesUser, Account.sales_id == SalesUser.id)
        .where(where_clause)
        .order_by(SMSLog.id.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(query)
    rows = result.all()

    is_adm = auth_context["is_admin"]
    out_records = []
    for r, ch_code, ch_name, acct_name, sales_name in rows:
        rec = {
            "id": r.id,
            "message_id": r.message_id,
            "upstream_message_id": r.upstream_message_id,
            "account_id": r.account_id,
            "account_name": acct_name,
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
            "sales_name": sales_name,
        }
        rec["channel_id"] = r.channel_id
        rec["channel_code"] = ch_code
        rec["channel_name"] = ch_name
        out_records.append(rec)

    return {
        "success": True,
        "total": total,
        "page": page,
        "page_size": page_size,
        "is_admin": is_adm,
        "records": out_records,
    }


# ============ 上游 DLR 回调接口 (推送模式) ============

from fastapi import Request, Body
from app.core.dlr_handler import (
    parse_json_dlr, parse_xml_dlr, parse_form_dlr, 
    detect_and_parse_dlr, process_dlr_reports
)
from app.modules.sms.batch_utils import update_batch_progress
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


async def _handle_dlr_callback_post(
    request: Request,
    db: AsyncSession,
    channel_id: Optional[int] = None,
    source: str = "push",
):
    """
    解析 POST 体并处理 DLR；channel_id 非空时仅更新该通道下的短信（与拉取任务一致）。
    """
    content_type = request.headers.get('content-type', '')
    body = await request.body()
    body_text = body.decode('utf-8', errors='ignore')

    logger.info(f"收到 DLR 回调 (POST): content_type={content_type}, body={body_text[:500]}")

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

    success, fail, affected_batch_ids = await process_dlr_reports(
        reports, db, source=source, channel_id=channel_id
    )

    # 异步同步批次统计数据
    for b_id in affected_batch_ids:
        await update_batch_progress(db, b_id)

    logger.info(f"DLR 回调处理完成: 成功={success}, 失败={fail}, 影响批次={len(affected_batch_ids)}")
    return {"status": 0, "message": "success", "processed": success + fail}


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
        return await _handle_dlr_callback_post(request, db, channel_id=None, source="push")
    except Exception as e:
        logger.error(f"处理 DLR 回调失败: {str(e)}", exc_info=True)
        return {"status": 1, "message": "internal error"}


@router.get("/dlr/callback")
async def dlr_callback_get(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    接收上游 DLR 回调 (GET 方式)

    先将全部 query 转为小写键后用 parse_form_dlr 解析，兼容 mid/msgid/task_id 等任意组合；
    避免仅依赖少量硬编码参数名导致上游已回调但系统收不到消息 ID 的异常。
    """
    if not _verify_dlr_caller(request):
        logger.warning(f"DLR GET 回调认证失败: IP={request.client.host if request.client else 'unknown'}")
        return JSONResponse(
            status_code=403,
            content={"status": 1, "message": "Forbidden"}
        )

    try:
        query_string = str(request.query_params)
        logger.info(f"收到 DLR 回调 (GET): {query_string}")

        # 合并 query（小写键，后者覆盖同名）供表单解析器统一处理
        qp: dict = {}
        for k, v in request.query_params.multi_items():
            if k:
                qp[str(k).lower()] = v

        reports = parse_form_dlr(qp)

        if not reports:
            logger.warning(f"DLR GET 无法解析报告（缺少已知消息 ID 字段）: {query_string[:500]}")
            return {"status": 0, "message": "missing message_id"}

        success, fail = await process_dlr_reports(
            reports, db, source="push-get", channel_id=None
        )

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
    from app.modules.sms.channel import Channel

    logger.info(f"收到通道 {channel_code} 的 DLR 回调")
    if not _verify_dlr_caller(request):
        logger.warning(
            f"DLR 回调认证失败: channel={channel_code}, "
            f"IP={request.client.host if request.client else 'unknown'}"
        )
        return JSONResponse(
            status_code=403,
            content={"status": 1, "message": "Forbidden"}
        )

    ch_res = await db.execute(
        select(Channel).where(
            Channel.channel_code == channel_code,
            Channel.is_deleted == False,
        )
    )
    channel = ch_res.scalar_one_or_none()
    if not channel:
        return JSONResponse(
            status_code=404,
            content={"status": 1, "message": f"unknown channel: {channel_code}"},
        )

    try:
        return await _handle_dlr_callback_post(
            request,
            db,
            channel_id=channel.id,
            source=f"push-{channel_code}",
        )
    except Exception as e:
        logger.error(f"处理 DLR 回调失败: {str(e)}", exc_info=True)
        return {"status": 1, "message": "internal error"}


@router.get("/public/rates", response_model=PublicSMSRateResponse)
async def get_public_rates(db: AsyncSession = Depends(get_db)):
    """获取公开短信费率（基于开户模板最高价 + 50% 利润）"""
    try:
        query = (
            select(
                AccountTemplate.country_code,
                AccountTemplate.country_name,
                func.max(AccountTemplate.default_price).label("max_price")
            )
            .where(AccountTemplate.business_type == "sms")
            .where(AccountTemplate.status == "active")
            .group_by(AccountTemplate.country_code, AccountTemplate.country_name)
            .order_by(AccountTemplate.country_name.asc())
        )
        
        result = await db.execute(query)
        rows = result.all()
        
        rates = []
        for row in rows:
            price = float(Decimal(str(row.max_price or 0)) * Decimal("1.5"))
            rates.append(PublicSMSRate(
                code=row.country_code,
                name=row.country_name,
                price=round(price, 4)
            ))
            
        return PublicSMSRateResponse(success=True, data=rates)
    except Exception as e:
        logger.error(f"获取公开费率失败: {str(e)}", exc_info=True)
        return PublicSMSRateResponse(success=False, data=[])


@router.get("/channels/{channel_id}/banned-words")
async def get_channel_banned_words_for_user(
    channel_id: int,
    account: Account = Depends(get_current_account_or_admin),
    db: AsyncSession = Depends(get_db)
):
    """获取通道违禁词（客户和管理员均可访问）"""
    from app.modules.sms.channel import Channel
    from app.modules.sms.routing_rule import RoutingRule

    result = await db.execute(select(Channel).where(Channel.id == channel_id))
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    rules_result = await db.execute(
        select(RoutingRule).where(
            RoutingRule.channel_id == channel_id,
            RoutingRule.is_active == True
        )
    )
    rules = rules_result.scalars().all()

    country_words = {}
    for r in rules:
        if r.banned_words:
            country_words[r.country_code] = r.banned_words

    return {
        "success": True,
        "channel_banned_words": channel.banned_words or "",
        "country_banned_words": country_words,
    }


# ============ 客户端发送统计（精细化回执） ============

from fastapi import Query as QueryParam
from datetime import timedelta


@router.get("/send-statistics")
async def get_customer_send_statistics(
    start_date: Optional[str] = QueryParam(None),
    end_date: Optional[str] = QueryParam(None),
    account: Account = Depends(get_current_account_or_admin),
    db: AsyncSession = Depends(get_db),
):
    """客户端发送统计：按日期精细化回执状态统计，不按国家/通道分组"""
    from sqlalchemy import case, and_

    if not end_date:
        end_date = datetime.now().date().isoformat()
    if not start_date:
        start_date = (datetime.now() - timedelta(days=30)).date().isoformat()
    try:
        start_dt = datetime.fromisoformat(start_date)
        end_dt = datetime.fromisoformat(end_date) + timedelta(days=1)
    except ValueError:
        return {"success": False, "detail": "日期格式错误"}

    base = (
        select(
            func.date(SMSLog.submit_time).label("date"),
            func.count(SMSLog.id).label("submit_total"),
            func.sum(case((SMSLog.status == "delivered", 1), else_=0)).label("delivered"),
            func.sum(case((SMSLog.status == "failed", 1), else_=0)).label("failed"),
            func.sum(case((SMSLog.status == "pending", 1), else_=0)).label("pending"),
            func.sum(case((SMSLog.status == "queued", 1), else_=0)).label("queued"),
            func.sum(case((SMSLog.status == "sent", 1), else_=0)).label("sent"),
            func.sum(case((SMSLog.status == "expired", 1), else_=0)).label("expired"),
            func.sum(SMSLog.selling_price).label("total_spending"),
        )
        .where(and_(
            SMSLog.account_id == account.id,
            SMSLog.submit_time >= start_dt,
            SMSLog.submit_time < end_dt,
        ))
        .group_by(func.date(SMSLog.submit_time))
        .order_by(func.date(SMSLog.submit_time).desc())
    )

    result = await db.execute(base)
    rows = result.all()

    sum_submit = sum_delivered = sum_failed = 0
    sum_pending = sum_queued = sum_sent = sum_expired = 0
    sum_spending = 0.0
    items = []

    for r in rows:
        total = r.submit_total or 0
        delivered = r.delivered or 0
        failed = r.failed or 0
        pending = r.pending or 0
        queued = r.queued or 0
        sent = r.sent or 0
        expired = r.expired or 0
        spending = round(float(r.total_spending or 0), 5)
        delivery_rate = round((delivered / total * 100) if total > 0 else 0, 2)

        sum_submit += total
        sum_delivered += delivered
        sum_failed += failed
        sum_pending += pending
        sum_queued += queued
        sum_sent += sent
        sum_expired += expired
        sum_spending += spending

        items.append({
            "date": r.date.isoformat() if r.date else None,
            "submit_total": total,
            "delivered": delivered,
            "failed": failed,
            "pending": pending,
            "queued": queued,
            "sent": sent,
            "expired": expired,
            "delivery_rate": delivery_rate,
            "total_spending": spending,
        })

    summary = {
        "submit_total": sum_submit,
        "delivered": sum_delivered,
        "failed": sum_failed,
        "pending": sum_pending,
        "queued": sum_queued,
        "sent": sum_sent,
        "expired": sum_expired,
        "delivery_rate": round((sum_delivered / sum_submit * 100) if sum_submit > 0 else 0, 2),
        "total_spending": round(sum_spending, 5),
    }

    return {
        "success": True,
        "total": len(items),
        "items": items,
        "summary": summary,
        "filters": {"start_date": start_date, "end_date": end_date},
    }


@router.get("/daily-stats")
async def get_customer_daily_stats(
    days: int = QueryParam(7, ge=1, le=90),
    start_date: Optional[str] = QueryParam(None),
    end_date: Optional[str] = QueryParam(None),
    account: Account = Depends(get_current_account_or_admin),
    db: AsyncSession = Depends(get_db),
):
    """客户端每日趋势统计（精细化回执）"""
    from sqlalchemy import case, and_

    if start_date and end_date:
        try:
            start_dt = datetime.fromisoformat(start_date).date()
            end_dt = datetime.fromisoformat(end_date).date() + timedelta(days=1)
        except ValueError:
            return {"success": False, "detail": "日期格式错误"}
    else:
        end_dt = datetime.now().date() + timedelta(days=1)
        start_dt = end_dt - timedelta(days=max(1, min(90, days)))

    base = (
        select(
            func.date(SMSLog.submit_time).label("date"),
            func.count(SMSLog.id).label("total_sent"),
            func.sum(case((SMSLog.status == "delivered", 1), else_=0)).label("delivered"),
            func.sum(case((SMSLog.status == "failed", 1), else_=0)).label("failed"),
            func.sum(case((SMSLog.status == "pending", 1), else_=0)).label("pending"),
            func.sum(case((SMSLog.status == "queued", 1), else_=0)).label("queued"),
            func.sum(case((SMSLog.status == "sent", 1), else_=0)).label("sent"),
            func.sum(case((SMSLog.status == "expired", 1), else_=0)).label("expired"),
            func.sum(SMSLog.selling_price).label("total_spending"),
        )
        .where(and_(
            SMSLog.account_id == account.id,
            SMSLog.submit_time >= start_dt,
            SMSLog.submit_time < end_dt,
        ))
    )

    base = base.group_by(func.date(SMSLog.submit_time)).order_by(func.date(SMSLog.submit_time).asc())
    result = await db.execute(base)

    statistics = []
    for row in result:
        ts = row.total_sent or 0
        d = row.delivered or 0
        f = row.failed or 0
        p = row.pending or 0
        q = row.queued or 0
        s = row.sent or 0
        e = row.expired or 0
        spending = float(row.total_spending or 0)
        statistics.append({
            "date": row.date.isoformat() if row.date else None,
            "total_sent": ts,
            "delivered": d,
            "failed": f,
            "pending": p,
            "queued": q,
            "sent": s,
            "expired": e,
            "delivery_rate": round(d / ts * 100, 2) if ts > 0 else 0,
            "total_spending": round(spending, 5),
        })

    return {"success": True, "days": (end_dt - start_dt).days, "statistics": statistics}


def _classify_fail_reason(error_message: str) -> str:
    """将原始 error_message 归类为客户可读的失败原因"""
    if not error_message:
        return "unknown"
    msg = error_message.lower()
    if "stat=undeliv" in msg:
        return "undelivered"
    if "stat=reject" in msg:
        return "rejected"
    if "stat=unknown" in msg:
        return "unknown_receipt"
    if "提交被拒" in error_message or "submit_sm_resp" in msg:
        return "submit_rejected"
    if "channel not found" in msg or "no available channel" in msg:
        return "no_channel"
    if "connection failed" in msg or "bind failed" in msg or "bind_transmitter" in msg:
        return "channel_error"
    if "上游" in error_message or "upstream" in msg:
        return "upstream_error"
    if "event loop" in msg or "different loop" in msg or "object has no attribute" in msg or "settings" in msg:
        return "system_error"
    if "expired" in msg or "timeout" in msg:
        return "timeout"
    return "other"


FAIL_REASON_LABELS = {
    "undelivered": "运营商未送达",
    "rejected": "运营商拒绝",
    "unknown_receipt": "未知回执",
    "submit_rejected": "提交被拒",
    "no_channel": "无可用通道",
    "channel_error": "通道连接异常",
    "upstream_error": "上游接口错误",
    "system_error": "系统异常",
    "timeout": "超时/过期",
    "other": "其他",
    "unknown": "原因未知",
}


@router.get("/fail-analysis")
async def get_customer_fail_analysis(
    start_date: Optional[str] = QueryParam(None),
    end_date: Optional[str] = QueryParam(None),
    account: Account = Depends(get_current_account_or_admin),
    db: AsyncSession = Depends(get_db),
):
    """客户端失败回执细分分析"""
    from sqlalchemy import and_

    if not end_date:
        end_date = datetime.now().date().isoformat()
    if not start_date:
        start_date = (datetime.now() - timedelta(days=30)).date().isoformat()
    try:
        start_dt = datetime.fromisoformat(start_date)
        end_dt = datetime.fromisoformat(end_date) + timedelta(days=1)
    except ValueError:
        return {"success": False, "detail": "日期格式错误"}

    result = await db.execute(
        select(SMSLog.error_message, func.count(SMSLog.id).label("cnt"))
        .where(and_(
            SMSLog.account_id == account.id,
            SMSLog.status == "failed",
            SMSLog.submit_time >= start_dt,
            SMSLog.submit_time < end_dt,
        ))
        .group_by(SMSLog.error_message)
    )

    category_map: dict[str, dict] = {}
    total_failed = 0

    for row in result:
        raw_msg = row.error_message or ""
        cnt = row.cnt or 0
        total_failed += cnt
        cat = _classify_fail_reason(raw_msg)

        if cat not in category_map:
            category_map[cat] = {
                "category": cat,
                "label": FAIL_REASON_LABELS.get(cat, cat),
                "count": 0,
                "details": [],
            }
        category_map[cat]["count"] += cnt
        short_msg = raw_msg[:80] + "..." if len(raw_msg) > 80 else raw_msg
        category_map[cat]["details"].append({
            "error_message": short_msg or "(空)",
            "count": cnt,
        })

    items = sorted(category_map.values(), key=lambda x: x["count"], reverse=True)

    for item in items:
        item["percentage"] = round(item["count"] / total_failed * 100, 2) if total_failed > 0 else 0
        item["details"] = sorted(item["details"], key=lambda x: x["count"], reverse=True)[:5]

    return {
        "success": True,
        "total_failed": total_failed,
        "categories": items,
        "filters": {"start_date": start_date, "end_date": end_date},
    }
