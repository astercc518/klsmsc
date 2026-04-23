"""
短信发送Worker
"""
import contextlib
import json
import threading
import time
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple
from sqlalchemy import select, and_, or_, update
from sqlalchemy.exc import OperationalError
from celery.exceptions import Retry

from app.workers.celery_app import celery_app
from app.config import settings
from app.modules.sms.sms_log import SMSLog
from app.modules.sms.channel import Channel
from app.database import AsyncSessionLocal
# 进程内单例 httpx 客户端，复用 TCP/TLS 连接
_http_client = None

def _get_http_client():
    global _http_client
    import httpx
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(
                max_connections=50,
                max_keepalive_connections=20,
                keepalive_expiry=120,
            ),
            http2=False,
        )
    return _http_client
from app.utils.logger import get_logger
from app.utils.phone_utils import format_sms_dest_phone
import asyncio

logger = get_logger(__name__)


# 从工具类导入
from app.modules.sms.batch_utils import update_batch_progress, _mimic_smpp_expired_dlr_message
from app.modules.sms.sms_batch import SmsBatch
from app.workers.webhook_worker import send_webhook_task





def _run_async(coro):
    """在 Celery 同步 worker 中安全地执行异步协程，始终使用全新事件循环。
    这是最稳妥的模式，彻底避免 'Event loop is closed' 错误。
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


def _make_session():
    """为 Worker 任务创建独立的数据库引擎和会话（避免跨事件循环复用连接池）"""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from sqlalchemy.pool import NullPool
    
    eng = create_async_engine(
        settings.SQLALCHEMY_DATABASE_URL, 
        echo=False,
        poolclass=NullPool,
        pool_pre_ping=True, 
        pool_recycle=600,
    )
    factory = async_sessionmaker(
        eng, class_=AsyncSession,
        expire_on_commit=False, 
        autocommit=False, 
        autoflush=False
    )
    return eng, factory


async def _load_smpp_payload_by_message_id(message_id: str) -> Optional[Dict[str, Any]]:
    """按 message_id 查库组装 Go 网关所需全量负载（仅用于兼容旧入队路径）。"""
    eng, Session = _make_session()
    try:
        async with Session() as db:
            result = await db.execute(select(SMSLog).where(SMSLog.message_id == message_id))
            sms_log = result.scalar_one_or_none()
            if not sms_log:
                return None
            bs = ""
            if sms_log.batch_id:
                _bs = (
                    await db.execute(select(SmsBatch.status).where(SmsBatch.id == sms_log.batch_id))
                ).scalar_one_or_none()
                bs = getattr(_bs, "value", str(_bs or ""))
            from app.utils.smpp_payload import smpp_payload_public_dict

            return smpp_payload_public_dict(sms_log, bs)
    finally:
        await eng.dispose()


async def _load_smpp_payloads_by_message_ids(message_ids: List[str]) -> List[Dict[str, Any]]:
    """批量按 message_id 组装 SMPP 负载列表（顺序与输入一致，缺失则跳过）。"""
    if not message_ids:
        return []
    eng, Session = _make_session()
    try:
        async with Session() as db:
            result = await db.execute(select(SMSLog).where(SMSLog.message_id.in_(message_ids)))
            logs = list(result.scalars().all())
            by_mid = {r.message_id: r for r in logs}
            from app.utils.smpp_payload import smpp_payload_public_dict

            out: List[Dict[str, Any]] = []
            for mid in message_ids:
                row = by_mid.get(mid)
                if not row:
                    continue
                bs = ""
                if row.batch_id:
                    _bs = (
                        await db.execute(select(SmsBatch.status).where(SmsBatch.id == row.batch_id))
                    ).scalar_one_or_none()
                    bs = getattr(_bs, "value", str(_bs or ""))
                out.append(smpp_payload_public_dict(row, bs))
            return out
    finally:
        await eng.dispose()


@celery_app.task(name='dlr_water_followup_task')
def dlr_water_followup_task(
    sms_log_id: int,
    message_text: str,
    country_code: str,
    account_id: int,
    channel_id: int = 0,
):
    """DLR 送达后的注水逻辑：独立队列，避免阻塞 sms_dlr Worker。"""
    if not account_id or not (message_text or "").strip():
        return {"skipped": True}
    cid = channel_id if channel_id else None

    async def _body():
        eng, Session = _make_session()
        try:
            async with Session() as db:
                from app.utils.water_trigger import trigger_water_single

                await trigger_water_single(
                    db, sms_log_id, message_text, country_code or "", account_id, channel_id=cid
                )
        finally:
            await eng.dispose()

    try:
        _run_async(_body())
        return {"success": True}
    except Exception as e:
        logger.warning(f"dlr_water_followup_task 异常: {e}")
        return {"success": False, "error": str(e)}


@celery_app.task(name='send_sms_task', bind=True, max_retries=3)
def send_sms_task(self, first, http_credentials: dict = None):
    """
    发送短信任务

    Args:
        first: sms_send 队列为 message_id 字符串；sms_send_smpp 为全量负载 dict（仅 Go 消费，Python 直接跳过）
        http_credentials: HTTP通道凭据（可选），包含 username 和 password
    """
    if isinstance(first, dict):
        logger.debug(
            "send_sms_task 收到 sms_send_smpp 专用负载，应由 Go 网关消费；Python worker 跳过"
        )
        return {"success": True, "skipped_gateway_payload": True}

    # 整包批量负载：首参为 list[dict]，与 Go extractSmsPayloads 的「args[0] 为对象数组」对齐，仅网关消费
    if isinstance(first, list):
        logger.debug(
            f"send_sms_task 收到 sms_send_smpp 批量负载 len={len(first)}，应由 Go 网关消费；Python worker 跳过"
        )
        return {"success": True, "skipped_gateway_payload": True, "batch_len": len(first)}

    message_id = first
    logger.info(f"开始处理短信发送任务: {message_id}")
    current_queue = (self.request.delivery_info or {}).get('routing_key', 'sms_send')

    try:
        result = _run_async(_send_sms_async(message_id, http_credentials, _current_queue=current_queue))

        if isinstance(result, dict) and result.get("_reroute_smpp"):
            smpp_pl = result.get("_smpp_payload")
            if not smpp_pl:
                logger.error(f"SMPP 重路由缺少负载: {message_id}")
                _run_async(_mark_failed(message_id, "SMPP重路由缺少全量负载"))
                return {"success": False, "error": "missing smpp payload"}
            logger.info(f"SMPP 通道任务重路由到 sms_send_smpp 队列: {message_id}")
            try:
                send_sms_task.apply_async(
                    args=[smpp_pl, http_credentials],
                    queue='sms_send_smpp',
                )
            except Exception as e:
                logger.error(
                    f"SMPP 重投 sms_send_smpp 失败: {message_id}, {e}",
                    exc_info=e,
                )
                _run_async(_mark_failed(message_id, f"SMPP重投sms_send_smpp失败: {e}"))
                return {"success": False, "error": str(e)}
            return {"success": True, "rerouted": "sms_send_smpp"}

        if isinstance(result, dict) and result.get("_rate_limited"):
            wait_sec = result.get("_wait_sec", 0.5)
            logger.info(f"通道限速，{wait_sec}s 后重试: {message_id}")
            raise self.retry(countdown=wait_sec, max_retries=200)

        if (
            isinstance(result, dict)
            and result.get("error") == "Message not found"
            and self.request.retries < self.max_retries
        ):
            countdown = 2 + int(self.request.retries) * 3
            logger.warning(
                f"短信记录尚未提交可见，{countdown}s 后重试: {message_id} (第{self.request.retries + 1}次)"
            )
            raise self.retry(countdown=countdown)
        return result

    except Retry:
        raise
    except Exception as e:
        logger.error(f"发送短信失败: {message_id}, 错误: {str(e)}", exc_info=e)
        
        if self.request.retries < self.max_retries:
            logger.info(f"将重试发送: {message_id}, 重试次数: {self.request.retries + 1}")
            raise self.retry(exc=e, countdown=60)
        else:
            logger.error(f"达到最大重试次数，标记为失败: {message_id}")
            _run_async(_mark_failed(message_id, str(e)))
            return {"success": False, "error": str(e)}





async def _send_sms_async(message_id: str, http_credentials: dict = None, *, _current_queue: str = 'sms_send') -> dict:
    """
    异步发送短信
    
    Args:
        message_id: 消息ID
        http_credentials: HTTP通道凭据（可选），包含 username 和 password
        _current_queue: 当前任务所在队列，用于 SMPP 通道重路由判断
    """
    eng, Session = _make_session()
    try:
        async with Session() as db:
            # 查询短信记录
            result = await db.execute(
                select(SMSLog).where(SMSLog.message_id == message_id)
            )
            sms_log = result.scalar_one_or_none()
        
            if not sms_log:
                logger.error(f"短信记录不存在: {message_id}")
                return {"success": False, "error": "Message not found"}

            # 批次已取消：不再入队 SMPP / 不再发 HTTP，待发记录直接失败（避免队列残留任务仍打到通道）
            if sms_log.batch_id:
                _bs = (
                    await db.execute(select(SmsBatch.status).where(SmsBatch.id == sms_log.batch_id))
                ).scalar_one_or_none()
                _bsv = getattr(_bs, "value", _bs)
                if _bsv == "cancelled" and sms_log.status in ("pending", "queued"):
                    sms_log.status = "failed"
                    sms_log.error_message = "批次已取消"
                    await db.commit()
                    if sms_log.batch_id:
                        await update_batch_progress(db, sms_log.batch_id)
                    logger.info(f"批次已取消，跳过发送: batch={sms_log.batch_id}, message_id={message_id}")
                    return {"success": True, "message_id": message_id, "status": "failed", "skipped": True}

            # 已为终态则不再走发送逻辑（避免与批量虚拟回执等竞态把 delivered 覆盖回 sent）
            if sms_log.status in ("delivered", "failed", "expired"):
                logger.info(f"短信已终态，跳过发送任务: {message_id}, status={sms_log.status}")
                return {"success": True, "message_id": message_id, "status": sms_log.status, "skipped": True}

            # 黑名单校验：data_numbers.status='blacklisted' 的号码直接拦截
            try:
                from app.modules.data.models import DataNumber
                bl = await db.execute(
                    select(DataNumber.id)
                    .where(DataNumber.phone_number == sms_log.phone_number,
                           DataNumber.status == 'blacklisted')
                    .limit(1)
                )
                if bl.scalar_one_or_none():
                    sms_log.status = 'failed'
                    sms_log.error_message = '号码已列入黑名单'
                    await db.commit()
                    if sms_log.batch_id:
                        await update_batch_progress(db, sms_log.batch_id)
                    logger.info(f"黑名单拦截: phone={sms_log.phone_number}, message_id={message_id}")
                    return {"success": False, "error": "blacklisted", "message_id": message_id}
            except Exception as _bl_err:
                logger.warning(f"黑名单检查异常(忽略): {_bl_err}")

            # 查询通道（若未指定则自动路由）
            channel = None
            if sms_log.channel_id:
                result = await db.execute(
                    select(Channel).where(Channel.id == sms_log.channel_id)
                )
                channel = result.scalar_one_or_none()

            if not channel:
                try:
                    from app.core.router import RoutingEngine
                    router = RoutingEngine(db)
                    country = sms_log.country_code or "PH"
                    channel = await router.select_channel(country)
                    if channel:
                        sms_log.channel_id = channel.id
                except Exception as route_err:
                    logger.warning(f"自动路由失败: {message_id}, {route_err}")

            if not channel:
                logger.error(f"无可用通道: {message_id}, channel_id={sms_log.channel_id}")
                sms_log.status = 'failed'
                sms_log.error_message = "No available channel"
                await db.commit()
                return {"success": False, "error": "No available channel"}
        
            logger.info(f"使用通道: {channel.channel_code} ({channel.protocol})")

            # SMPP：由 Go smpp-gateway 消费 sms_send_smpp；在 sms_send 上执行时重投该队列
            if channel.protocol == 'SMPP' and _current_queue != 'sms_send_smpp':
                # 已进入发送链路，先落库为 queued，避免长期停留在 pending 被误判为「未出队」
                if sms_log.status == "pending":
                    sms_log.status = "queued"
                    await db.commit()
                # 首跳即 return，原先未刷新批次汇总；Go 网关写 sent 也不经本进程，须在此先同步一次
                if sms_log.batch_id:
                    await update_batch_progress(db, sms_log.batch_id)
                bs = ""
                if sms_log.batch_id:
                    _bs = (
                        await db.execute(select(SmsBatch.status).where(SmsBatch.id == sms_log.batch_id))
                    ).scalar_one_or_none()
                    bs = getattr(_bs, "value", str(_bs or ""))
                from app.utils.smpp_payload import smpp_payload_public_dict

                smpp_pl = smpp_payload_public_dict(sms_log, bs)
                await db.close()
                return {"_reroute_smpp": True, "_smpp_payload": smpp_pl}

            if channel.protocol != 'VIRTUAL':
                from app.utils.rate_limiter import acquire_send_slot
                max_tps = channel.max_tps or 100
                allowed, wait_ms = acquire_send_slot(channel.id, max_tps)
                if not allowed:
                    await db.close()
                    return {"_rate_limited": True, "_wait_sec": round(wait_ms / 1000, 2)}

            # 更新状态为发送中
            sms_log.status = 'sent'
            sms_log.sent_time = datetime.now()
            await db.commit()
        
            # 根据通道协议发送
            if channel.protocol == 'VIRTUAL':
                success = await _send_via_virtual(sms_log, channel)
            elif channel.protocol == 'HTTP':
                http_result = await _send_via_http(sms_log, channel, http_credentials)
                if http_result == "_retry":
                    # 临时错误（超时/限速/网关故障）：回退状态避免幽灵 sent，等待 Celery retry
                    sms_log.status = 'queued'
                    await db.commit()
                    await db.close()
                    return {"_rate_limited": True, "_wait_sec": 10}
                success = bool(http_result)
            else:
                # SMPP 不应在 Python 内 Submit；防御性重路由（缺负载时上层会记失败）
                logger.error(f"非预期路径：{channel.protocol} 在 Python Worker 执行，触发重路由")
                return {"_reroute_smpp": True}

            # 发送成功后立刻提交：submit_sm_resp 写入的 upstream_message_id 必须先落库。
            # deliver_sm 常在同一秒内到达，DLR 在独立线程读库；若仍停留在未提交的会话里，会大量出现「SMPP DLR: 未找到」且界面长期「送达等待中」。
            if success:
                await db.commit()
        
            # 更新状态
            if success:
                logger.info(f"短信发送成功: {message_id}")
            
                # 触发Webhook回调（sent状态）
                try:
                    from app.workers.webhook_worker import trigger_webhook
                    await trigger_webhook(
                        message_id,
                        'sent',
                        {
                            'phone_number': sms_log.phone_number,
                            'country_code': sms_log.country_code,
                            'channel_id': sms_log.channel_id
                        },
                        account_id=sms_log.account_id,
                    )
                except Exception as e:
                    logger.warning(f"触发Webhook失败: {str(e)}")
            else:
                sms_log.status = 'failed'
                # 保留详细错误信息，只有未设置时才使用默认值
                if not sms_log.error_message:
                    sms_log.error_message = "Send failed"
                logger.error(f"短信发送失败: {message_id}, 错误: {sms_log.error_message}")
            
                # 触发Webhook回调（failed状态）
                try:
                    from app.workers.webhook_worker import trigger_webhook
                    await trigger_webhook(
                        message_id,
                        'failed',
                        {
                            'phone_number': sms_log.phone_number,
                            'country_code': sms_log.country_code,
                            'error_message': sms_log.error_message
                        },
                        account_id=sms_log.account_id,
                    )
                except Exception as e:
                    logger.warning(f"触发Webhook失败: {str(e)}")
        
            await db.commit()

            # 更新批次进度
            if sms_log.batch_id:
                await update_batch_progress(db, sms_log.batch_id)
        
            return {"success": success, "message_id": message_id, "status": sms_log.status}
    finally:
        await eng.dispose()




async def _send_via_virtual(sms_log: SMSLog, channel: Channel) -> bool:
    """
    虚拟通道：不实际发送短信，立即标记为 sent，
    然后安排延迟 Celery 任务生成模拟回执（delivered/failed）。
    """
    import uuid
    try:
        virtual_msg_id = f"VIRT-{uuid.uuid4().hex[:12]}"
        sms_log.upstream_message_id = virtual_msg_id
        logger.info(f"虚拟通道发送: {sms_log.message_id} via {channel.channel_code}, virt_id={virtual_msg_id}")

        cfg = channel.get_virtual_config()
        delay_min = max(1, cfg.get("dlr_delay_min", 3))
        delay_max = max(delay_min, cfg.get("dlr_delay_max", 30))

        import random
        delay = random.uniform(delay_min, delay_max)

        from app.workers.celery_app import celery_app as _celery
        _celery.send_task(
            "virtual_dlr_generate",
            args=[sms_log.message_id, channel.id],
            countdown=delay,
            queue="sms_send",
        )
        return True
    except Exception as e:
        logger.error(f"虚拟通道处理异常: {sms_log.message_id}, {e}")
        return False


_HTTP_RETRIABLE_STATUS = {429, 502, 503, 504}


async def _send_via_http(sms_log: SMSLog, channel: Channel, http_credentials: dict = None):
    """
    通过HTTP发送短信。

    Returns:
        True      — 成功
        False     — 永久失败（已设置 sms_log.error_message）
        "_retry"  — 可重试的临时失败（限速/超时/网关错误），调用方应触发 Celery retry
    """
    import httpx

    try:
        logger.info(f"通过HTTP发送短信: {sms_log.message_id} via {channel.channel_code}")

        extno = channel.default_sender_id or ""

        if not channel.api_url:
            logger.info(f"HTTP通道未配置api_url，使用模拟模式: {sms_log.message_id}")
            return True

        http_account = None
        http_password = None

        if http_credentials:
            http_account = http_credentials.get("username") or http_credentials.get("account")
            http_password = http_credentials.get("password")

        if not http_account and channel.username:
            http_account = channel.username
            http_password = channel.password

        if not http_account and channel.api_key:
            try:
                import json
                api_config = json.loads(channel.api_key)
                http_account = api_config.get("account")
                http_password = api_config.get("password")
            except json.JSONDecodeError:
                logger.warning(f"通道api_key不是有效的JSON格式: {channel.api_key}")

        mobile = format_sms_dest_phone(
            sms_log.phone_number,
            strip_leading_plus=channel.strip_leading_plus_for_submit(),
        )

        payload = {
            "action": "send",
            "account": http_account or "",
            "password": http_password or "",
            "mobile": mobile,
            "content": sms_log.message,
            "extno": extno,
        }

        scheduled_time = getattr(sms_log, 'scheduled_time', None)
        if scheduled_time:
            payload["atTime"] = scheduled_time.strftime("%Y-%m-%d %H:%M:%S")

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "SMSC-Gateway/1.0",
        }

        logger.info(f"HTTP请求URL: {channel.api_url}")
        logger.info(f"HTTP请求参数: {payload}")

        # 每个 Celery task 拥有独立事件循环；使用独立 client 避免跨 loop 复用已关闭连接
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(channel.api_url, json=payload, headers=headers)

        response_text = response.text
        logger.info(f"HTTP响应: status={response.status_code}, body={response_text[:500]}")

        # 上游限速或网关临时故障 → 可重试
        if response.status_code in _HTTP_RETRIABLE_STATUS:
            logger.warning(f"HTTP可重试错误: {sms_log.message_id}, status={response.status_code}")
            sms_log.error_message = f"上游临时错误 HTTP {response.status_code}，等待重试"
            return "_retry"

        if response.status_code in [200, 201]:
            try:
                resp_data = response.json()
                api_status = resp_data.get('status')
                balance = resp_data.get('balance', 0)
                result_list = resp_data.get('list', [])

                status_errors = {
                    0: "成功", 2: "IP错误", 3: "账号密码错误", 5: "其它错误",
                    6: "接入点错误", 7: "账号状态异常(已停用)", 11: "系统内部错误",
                    34: "请求参数有误", 100: "系统内部错误",
                }
                result_errors = {
                    0: "提交成功", 10: "原发号码错误(extno错误)",
                    15: "余额不足", 100: "系统内部错误",
                }

                if api_status == 0:
                    if result_list:
                        first_result = result_list[0]
                        mid = (first_result.get('mid') or first_result.get('msgid') or
                               first_result.get('taskid') or first_result.get('message_id') or
                               first_result.get('id') or '')
                        result_code = first_result.get('result', first_result.get('status', -1))
                        if isinstance(result_code, str) and result_code.isdigit():
                            result_code = int(result_code)

                        if result_code == 0:
                            logger.info(f"HTTP发送成功: {sms_log.message_id}, upstream_id={mid}, balance={balance}")
                            sms_log.upstream_message_id = mid or None
                            return True
                        else:
                            error_desc = result_errors.get(result_code, f"未知错误({result_code})")
                            logger.error(f"HTTP发送失败(提交错误): {sms_log.message_id}, result={result_code}, 错误: {error_desc}")
                            sms_log.error_message = f"上游错误: {error_desc}"
                            return False
                    else:
                        mid = (resp_data.get('mid') or resp_data.get('msgid') or
                               resp_data.get('taskid') or resp_data.get('message_id') or
                               resp_data.get('id') or '')
                        if mid:
                            sms_log.upstream_message_id = str(mid)
                            logger.info(f"HTTP发送成功(无明细): {sms_log.message_id}, upstream_id={mid}")
                        else:
                            logger.info(f"HTTP发送成功(无明细): {sms_log.message_id}, balance={balance}")
                        return True
                else:
                    error_desc = status_errors.get(api_status, f"未知错误({api_status})")
                    logger.error(f"HTTP发送失败(API错误): {sms_log.message_id}, status={api_status}, 错误: {error_desc}")
                    sms_log.error_message = f"上游API错误: {error_desc}"
                    return False

            except Exception as e:
                if '<returnsms>' in response_text:
                    import re
                    status_match = re.search(r'<returnstatus>(\w+)</returnstatus>', response_text)
                    message_match = re.search(r'<message>([^<]*)</message>', response_text)
                    return_status = status_match.group(1) if status_match else 'Unknown'
                    return_message = message_match.group(1) if message_match else ''
                    if return_status.lower() == 'success':
                        logger.info(f"HTTP发送成功(XML): {sms_log.message_id}")
                        return True
                    else:
                        logger.error(f"HTTP发送失败(XML): {sms_log.message_id}, status={return_status}, message={return_message}")
                        sms_log.error_message = f"上游XML错误: status={return_status}, code={return_message}"
                        return False
                else:
                    logger.error(f"HTTP响应解析失败: {sms_log.message_id}, error={e}, body={response_text[:200]}")
                    sms_log.error_message = f"响应解析失败: {str(e)}"
                    return False
        else:
            err_snippet = response_text[:200] if response_text else ''
            logger.error(f"HTTP发送失败: {sms_log.message_id}, status={response.status_code}, body={err_snippet}")
            sms_log.error_message = f"上游HTTP错误: {response.status_code}"
            return False

    except httpx.TimeoutException as e:
        logger.warning(f"HTTP发送超时(可重试): {sms_log.message_id}, {e}")
        sms_log.error_message = f"请求超时，等待重试"
        return "_retry"
    except httpx.ConnectError as e:
        logger.warning(f"HTTP连接失败(可重试): {sms_log.message_id}, {e}")
        sms_log.error_message = f"连接失败，等待重试"
        return "_retry"
    except Exception as e:
        logger.error(f"HTTP发送异常: {sms_log.message_id}, {str(e)}", exc_info=e)
        sms_log.error_message = f"发送异常: {str(e)[:100]}"
        return False


async def _mark_failed(message_id: str, error_message: str):
    """标记短信为失败状态"""
    eng, Session = _make_session()
    try:
        async with Session() as db:
            result = await db.execute(
                select(SMSLog).where(SMSLog.message_id == message_id)
            )
            sms_log = result.scalar_one_or_none()
            if sms_log:
                sms_log.status = 'failed'
                sms_log.error_message = error_message
                await db.commit()
                logger.info(f"已标记为失败: {message_id}")
    finally:
        await eng.dispose()


@celery_app.task(name='process_dlr_task')
def process_dlr_task(dlr_data: dict):
    """
    处理送达回执(DLR)任务
    
    Args:
        dlr_data: DLR数据
    """
    logger.info(f"处理DLR: {dlr_data}")
    
    try:
        _run_async(_process_dlr_async(dlr_data))
        return {"success": True}
        
    except Exception as e:
        logger.error(f"处理DLR失败: {str(e)}", exc_info=e)
        return {"success": False, "error": str(e)}


async def _process_dlr_async(dlr_data: dict):
    """
    异步处理DLR
    """
    eng, Session = _make_session()
    try:
        async with Session() as db:
            message_id = dlr_data.get('message_id')
            status = dlr_data.get('status')
            
            result = await db.execute(
                select(SMSLog).where(SMSLog.message_id == message_id)
            )
            sms_log = result.scalar_one_or_none()
            
            if not sms_log:
                logger.warning(f"DLR对应的短信记录不存在: {message_id}")
                return
            
            sms_log.status = status
            if status == 'delivered':
                sms_log.delivery_time = datetime.now()
            elif status == 'failed':
                sms_log.error_message = dlr_data.get('error_message', 'Delivery failed')
            
            await db.commit()
            logger.info(f"DLR处理完成: {message_id}, 状态: {status}")

            # 批次进度由 sync_processing_batch_progress_task 等定时汇总，避免每条 HTTP DLR 抢锁 sms_batches。

            # Webhook / 注水：仅入队，秒结本任务，避免阻塞 sms_dlr
            try:
                send_webhook_task.apply_async(
                    args=[
                        sms_log.account_id,
                        message_id,
                        status,
                        {
                            "phone_number": sms_log.phone_number,
                            "country_code": sms_log.country_code,
                            "error_message": dlr_data.get("error_message")
                            if status == "failed"
                            else None,
                        },
                    ],
                    queue="webhook_tasks",
                )
            except Exception as e:
                logger.warning(f"Webhook 入队失败: {e}")

            if status == "delivered" and sms_log.account_id:
                try:
                    celery_app.send_task(
                        "dlr_water_followup_task",
                        args=[
                            sms_log.id,
                            sms_log.message or "",
                            sms_log.country_code or "",
                            sms_log.account_id,
                            sms_log.channel_id or 0,
                        ],
                        queue="data_tasks",
                    )
                except Exception as e:
                    logger.warning(f"注水任务入队失败: {e}")
    finally:
        await eng.dispose()


@celery_app.task(name='process_smpp_dlr_task', max_retries=3)
def process_smpp_dlr_task(channel_id: int, upstream_id: str, new_status: str, stat: str, err: str, dest_addr: str, source_addr: str, receipted_message_id: str):
    """处理 SMPP DLR 发送到异步队列，避免在 PDU 接收线程中消耗过多 FD 资源导致服务崩溃。"""
    logger.info(f"队列接手SMPP DLR: id={upstream_id}")
    try:
        _run_async(_process_smpp_dlr_async(channel_id, upstream_id, new_status, stat, err, dest_addr, source_addr, receipted_message_id))
        return {"success": True}
    except Exception as e:
        logger.error(f"SMPP DLR队列处理失败: {e}", exc_info=e)
        return {"success": False, "error": str(e)}


async def _process_smpp_dlr_async(channel_id: int, upstream_id: str, new_status: str, stat: str, err: str, dest_addr: str, source_addr: str, receipted_message_id: str):
    # 纯函数，不依赖 db，定义在 session 外
    def _expand_id_candidates(raw: str) -> list:
        upstream_id_str = str(raw).strip()
        if not upstream_id_str:
            return []
        cands = [upstream_id_str]
        if any(x in upstream_id_str.upper() for x in "ABCDEF"):
            cands.append(upstream_id_str.upper())
            cands.append(upstream_id_str.lower())
        try:
            if upstream_id_str.startswith("0x") or upstream_id_str.startswith("0X"):
                cands.append(str(int(upstream_id_str, 16)))
            elif upstream_id_str.isdigit():
                cands.append(hex(int(upstream_id_str)))
            elif all(c in "0123456789abcdefABCDEF" for c in upstream_id_str):
                cands.append(str(int(upstream_id_str, 16)))
        except (ValueError, TypeError):
            pass
        return list(dict.fromkeys(cands))

    def _digits(s: str) -> str:
        return "".join(c for c in str(s) if c.isdigit())

    candidate_ids = []
    for piece in (upstream_id, receipted_message_id):
        candidate_ids.extend(_expand_id_candidates(piece))
    candidate_ids = list(dict.fromkeys(candidate_ids))

    eng, Session = _make_session()
    try:
        async with Session() as db:
            sms_log = None
            # 查询时同时包含 'delivered'/'failed'：重复 DLR 或重试时记录可能已是终态。
            # 过滤掉 expired/cancelled 即可，
            # 勿过滤 delivered/failed，否则 webhook 等后续逻辑永远不会被调用。
            _non_terminal = ["sent", "pending", "queued", "delivered", "failed"]
            if candidate_ids:
                stmt = select(SMSLog).where(
                    and_(
                        SMSLog.channel_id == channel_id,
                        SMSLog.upstream_message_id.in_(candidate_ids),
                        SMSLog.status.in_(_non_terminal),
                    )
                ).order_by(SMSLog.submit_time.desc()).limit(1)

                for _attempt in range(5):
                    result = await db.execute(stmt)
                    sms_log = result.scalar_one_or_none()
                    if sms_log:
                        break
                    if _attempt < 4:
                        await asyncio.sleep(0.08)

            if not sms_log:
                for addr in (dest_addr, source_addr):
                    d = _digits(addr)
                    if len(d) < 8:
                        continue
                    stmt2 = select(SMSLog).where(
                        and_(
                            SMSLog.channel_id == channel_id,
                            SMSLog.status.in_(["sent", "pending", "queued"]),
                            or_(
                                SMSLog.phone_number.like(f"%{d}"),
                                SMSLog.phone_number == f"+{d}",
                            ),
                        )
                    ).order_by(SMSLog.sent_time.desc()).limit(1)
                    res2 = await db.execute(stmt2)
                    sms_log = res2.scalar_one_or_none()
                    if sms_log:
                        logger.info(f"SMPP DLR: 按号码兜底匹配成功 upstream_id={upstream_id} -> log={sms_log.message_id}")
                        break

            if not sms_log:
                logger.warning(f"SMPP DLR: 未找到 upstream_id={upstream_id} (候选 {candidate_ids})，dest={dest_addr!r}")
                try:
                    from app.utils.dlr_buffer import buffer_unmatched_dlr
                    await buffer_unmatched_dlr(
                        channel_id, upstream_id, new_status, stat, err,
                        dest_addr, source_addr, receipted_message_id,
                    )
                except Exception as _buf_err:
                    logger.debug(f"DLR 重试缓冲写入异常(忽略): {_buf_err}")
                return False

            already_correct = sms_log.status == new_status
            if not already_correct:
                # Go gateway 尚未更新（或更新失败）：Python 主动写入
                sms_log.status = new_status
                if new_status == "delivered":
                    sms_log.delivery_time = datetime.now()
                    sms_log.error_message = None
                elif new_status == "failed":
                    sms_log.error_message = f"SMPP DLR: stat={stat} err={err}"

                if upstream_id and str(sms_log.upstream_message_id or "") != str(upstream_id).strip():
                    sms_log.upstream_message_id = str(upstream_id).strip()

                await db.commit()
                logger.info(f"SMPP DLR 更新成功: {sms_log.message_id} -> {new_status}")
            else:
                # 重复 DLR：状态已是目标值，跳过写库，仍派发 webhook/注水入队（与首次一致）
                logger.info(f"SMPP DLR 业务处理: {sms_log.message_id} 已是 {new_status}，派发 webhook/注水入队")

            # 批次进度由 sync_processing_batch_progress_task 等定时汇总，避免海量 DLR 并发抢锁 sms_batches。

            try:
                send_webhook_task.apply_async(
                    args=[
                        sms_log.account_id,
                        sms_log.message_id,
                        new_status,
                        {
                            "phone_number": sms_log.phone_number,
                            "country_code": sms_log.country_code,
                            "error_message": sms_log.error_message,
                        },
                    ],
                    queue="webhook_tasks",
                )
            except Exception as e:
                logger.warning(f"Webhook 入队失败: {e}")

            if new_status == "delivered" and sms_log.account_id:
                try:
                    celery_app.send_task(
                        "dlr_water_followup_task",
                        args=[
                            sms_log.id,
                            sms_log.message or "",
                            sms_log.country_code or "",
                            sms_log.account_id,
                            sms_log.channel_id or 0,
                        ],
                        queue="data_tasks",
                    )
                except Exception as e:
                    logger.warning(f"注水任务入队失败: {e}")

            return True

    finally:
        await eng.dispose()


# ============ DLR 重试缓冲 Flush 任务 ============

@celery_app.task(name='flush_dlr_retry_buffer_task')
def flush_dlr_retry_buffer_task():
    """
    每 5 秒重试一次「DLR 先于 SubmitSMResp 到达」导致未匹配的回执。
    这类 DLR 已被写入 Redis dlr_pending_retry Hash，本任务重新尝试匹配并写 DB。
    """
    try:
        _run_async(_flush_dlr_retry_buffer_async())
    except Exception as e:
        logger.error(f"flush_dlr_retry_buffer_task 异常: {e}")


async def _flush_dlr_retry_buffer_async():
    from app.utils.dlr_buffer import (
        pop_retry_buffer, remove_retry_item, increment_retry_count, retry_buffer_size,
    )

    size = await retry_buffer_size()
    if size <= 0:
        return
    logger.info(f"DLR 重试缓冲: 当前积压 {size} 条，开始重试")

    items = await pop_retry_buffer(limit=50)
    for item in items:
        field = item.get("_field", "")
        try:
            matched = await _process_smpp_dlr_async(
                channel_id=item["channel_id"],
                upstream_id=item["upstream_id"],
                new_status=item["new_status"],
                stat=item.get("stat", ""),
                err=item.get("err", ""),
                dest_addr=item.get("dest_addr", ""),
                source_addr=item.get("source_addr", ""),
                receipted_message_id=item.get("receipted_message_id", ""),
            )
            if matched:
                # 成功匹配并写入 DB，从缓冲区删除
                await remove_retry_item(field)
                logger.info(f"DLR 重试成功: field={field}")
            else:
                # 仍未找到 sms_log，增加重试计数（超限后由 increment_retry_count 自动删除）
                await increment_retry_count(field, item)
        except Exception as e:
            logger.warning(f"DLR 重试处理异常: field={field}, {e}")
            await increment_retry_count(field, item)


# ============ 定时拉取 DLR 报告 ============

@celery_app.task(name='fetch_dlr_reports_task')
def fetch_dlr_reports_task():
    """
    定时拉取上游 DLR 报告
    
    从 Kaola SMS 的 report 接口拉取送达报告
    """
    logger.info("开始拉取 DLR 报告...")
    
    try:
        result = _run_async(_fetch_dlr_reports_async())
        return result
        
    except Exception as e:
        logger.error(f"拉取 DLR 报告失败: {str(e)}", exc_info=e)
        return {"success": False, "error": str(e)}


async def _fetch_dlr_reports_async():
    """
    异步拉取 DLR 报告
    ...
    """
    import httpx
    from app.core.dlr_handler import detect_and_parse_dlr, process_dlr_reports
    from app.modules.common.system_config import SystemConfig

    eng, Session = _make_session()
    try:
        async with Session() as db:
            # 读取 DLR report URL 覆盖配置（系统配置 -> dlr_report_url_override，类型 json）
            url_overrides = {}
            try:
                cfg_res = await db.execute(
                    select(SystemConfig).where(SystemConfig.config_key == 'dlr_report_url_override')
                )
                cfg = cfg_res.scalar_one_or_none()
                if cfg and cfg.config_value:
                    raw = cfg.config_value
                    url_overrides = json.loads(raw) if isinstance(raw, str) else (raw or {})
            except (json.JSONDecodeError, TypeError):
                pass

        # HTTP 通道：有 api_url 的参与拉取
        http_result = await db.execute(
            select(Channel).where(
                Channel.protocol == 'HTTP',
                Channel.status == 'active',
                Channel.is_deleted == False
            )
        )
        channels = list(http_result.scalars().all())
        # SMPP 通道：若 dlr_report_url_override 配置了 report URL，也参与拉取（Kaola 等 SMPP 通道可通过 HTTP report 接口获取 DLR）
        smpp_result = await db.execute(
            select(Channel).where(
                Channel.protocol == 'SMPP',
                Channel.status == 'active',
                Channel.is_deleted == False
            )
        )
        smpp_channels = smpp_result.scalars().all()
        for sc in smpp_channels:
            ov = url_overrides.get(sc.channel_code)
            if ov and (isinstance(ov, str) or (isinstance(ov, dict) and ov.get('url'))):
                channels.append(sc)
        pull_channels = [(c.channel_code, getattr(c, 'api_url', None) or '', bool(c.username or c.password or c.api_key)) for c in channels]
        logger.info(f"DLR 拉取通道列表: {pull_channels}")

        total_success = 0
        total_fail = 0

        for channel in channels:
            # 解析 URL 覆盖（支持 "url" 或 直接字符串）
            override_val = url_overrides.get(channel.channel_code)
            url_override = None
            report_method = 'GET'
            if isinstance(override_val, str):
                url_override = override_val
            elif isinstance(override_val, dict) and override_val.get('url'):
                url_override = override_val['url']
                report_method = (override_val.get('method') or 'GET').upper()

            # HTTP 通道需 api_url；SMPP 通道需 dlr_report_url_override 配置了 report URL
            if not channel.api_url and not url_override:
                continue

            http_account = channel.username or ''
            http_password = channel.password or channel.api_key or ''

            if not http_account:
                logger.warning(f"通道 {channel.channel_code} 未配置 username，跳过 DLR 拉取")
                continue

            report_url = _build_dlr_pull_url(channel, url_override)
            if not report_url:
                logger.warning(f"通道 {channel.channel_code} 无有效 report URL，跳过")
                continue
            params = {
                "action": "report",
                "account": http_account,
                "password": http_password
            }

            try:
                logger.info(f"拉取 DLR: {channel.channel_code}, URL: {report_url}, method: {report_method}")

                pull_timeout = float(getattr(settings, "DLR_PULL_HTTP_TIMEOUT_SECONDS", 60.0) or 60.0)
                async with httpx.AsyncClient(timeout=pull_timeout) as client:
                    if report_method == 'POST':
                        response = await client.post(report_url, params=params)
                    else:
                        response = await client.get(report_url, params=params)

                    # GET 返回 405 时尝试 POST（部分上游仅支持 POST）
                    if response.status_code == 405 and report_method == 'GET':
                        logger.info(f"[{channel.channel_code}] GET 返回 405，尝试 POST")
                        response = await client.post(report_url, params=params)

                    if response.status_code == 200:
                        resp_text = response.text
                        content_type = response.headers.get('content-type', '')

                        if _is_empty_dlr_response(resp_text):
                            logger.info(f"[{channel.channel_code}] DLR 响应为空（上游暂无回执）")
                            continue

                        if _is_error_dlr_response(resp_text):
                            logger.warning(f"[{channel.channel_code}] DLR 响应错误: {resp_text[:200]}")
                            continue

                        reports = detect_and_parse_dlr(resp_text, content_type)

                        if reports:
                            logger.info(f"[{channel.channel_code}] 解析到 {len(reports)} 条 DLR 报告")
                            success, fail = await process_dlr_reports(
                                reports,
                                db,
                                source=f"pull-{channel.channel_code}",
                                channel_id=channel.id,
                            )
                            total_success += success
                            total_fail += fail
                        else:
                            logger.debug(f"[{channel.channel_code}] 无有效 DLR 报告，原始: {resp_text[:200]}")
                    else:
                        logger.warning(f"[{channel.channel_code}] 拉取 DLR 失败: HTTP {response.status_code}")

            except Exception as e:
                logger.error(f"拉取通道 {channel.channel_code} DLR 失败: {str(e)}")

        total = total_success + total_fail
        logger.info(f"DLR 拉取完成: 成功={total_success}, 失败={total_fail}, 总计={total}")
        return {"success": True, "updated": total, "delivered": total_success, "failed": total_fail}
    finally:
        await eng.dispose()


def _build_dlr_pull_url(channel: Channel, url_override: Optional[str] = None) -> str:
    """
    构建 DLR 拉取 URL
    
    根据不同的通道类型构建对应的报告查询 URL。
    若传入 url_override（来自系统配置 dlr_report_url_override），则优先使用。
    """
    if url_override:
        return url_override.strip()

    base_url = channel.api_url or ''

    # Kaola 格式: /smsv2 -> /sms，report 使用 action=report 参数
    if 'kaolasms' in base_url.lower():
        base_url = base_url.replace('/smsv2', '/sms').replace('?action=send', '')
        if '?' in base_url:
            base_url = base_url.split('?')[0]
        return base_url

    # 通用格式: 尝试替换或添加 /report 路径
    if base_url.endswith('/send'):
        return base_url.replace('/send', '/report')

    if base_url.endswith('/sms'):
        return base_url + '/report'

    # 默认直接使用
    return base_url


def _is_empty_dlr_response(resp_text: str) -> bool:
    """
    检查 DLR 响应是否为空
    """
    resp_text = resp_text.strip()
    
    # XML 空响应
    if '<returnsms></returnsms>' in resp_text:
        return True
    if '<returnsms/>' in resp_text:
        return True
    if '<reports></reports>' in resp_text:
        return True
    
    # JSON 空响应
    if resp_text in ['{}', '[]', '{"list":[]}', '{"reports":[]}', '{"data":[]}']:
        return True
    
    # 纯空
    if not resp_text:
        return True
    
    return False


def _is_error_dlr_response(resp_text: str) -> bool:
    """
    检查 DLR 响应是否为错误
    """
    resp_text = resp_text.lower()
    
    # 常见错误标识（含 Kaola 等上游的认证失败返回）
    error_patterns = [
        '<errorstatus>',
        '<error>',
        '"error":',
        'invalid_auth',
        'con_invalid_auth',
        'authentication failed',
        'access denied',
        'unauthorized',
    ]
    
    return any(pattern in resp_text for pattern in error_patterns)


# ============ DLR 超时处理 ============

@celery_app.task(name='dlr_timeout_check_task')
def dlr_timeout_check_task():
    """
    定时检查超时的 sent 记录
    超过指定时间仍为 sent 的记录标记为 timeout
    """
    logger.info("开始检查 DLR 超时记录...")
    try:
        result = _run_async(_dlr_timeout_check_async())
        return result
    except Exception as e:
        logger.error(f"DLR 超时检查失败: {str(e)}", exc_info=e)
        return {"success": False, "error": str(e)}


async def _dlr_timeout_check_async():
    """异步检查并标记超时的 sent 记录（按通道 dlr_sent_timeout_hours，否则用全局 DLR_SENT_TIMEOUT_HOURS）"""
    from datetime import timedelta
    from sqlalchemy import and_, update

    eng, Session = _make_session()
    try:
        async with Session() as db:
            default_h = int(getattr(settings, "DLR_SENT_TIMEOUT_HOURS", 72) or 72)
            default_h = max(4, min(default_h, 720))

            ch_result = await db.execute(
                select(Channel.id, Channel.dlr_sent_timeout_hours).where(
                    Channel.is_deleted == False
                )
            )
            channel_rows = ch_result.all()
            # 显式列出的通道（含仅自定义超时的通道）
            channel_ids = {row[0] for row in channel_rows}
            expired_count = 0

            for ch_id, custom_h in channel_rows:
                h = int(custom_h) if custom_h is not None and int(custom_h) > 0 else default_h
                h = max(4, min(h, 720))
                cutoff = datetime.now() - timedelta(hours=h)
                stmt = (
                    update(SMSLog)
                    .where(
                        and_(
                            SMSLog.channel_id == ch_id,
                            SMSLog.status == 'sent',
                            SMSLog.sent_time < cutoff,
                            SMSLog.sent_time.isnot(None),
                        )
                    )
                    .values(
                        status='expired',
                        error_message=f'DLR 超时: 超过{h}小时未收到终态回执',
                    )
                )
                r = await db.execute(stmt)
                expired_count += r.rowcount

            # 无 channel_id、或通道已删除/未在表中的记录，用全局默认小时数
            from sqlalchemy import or_, true as sql_true

            cutoff_default = datetime.now() - timedelta(hours=default_h)
            if channel_ids:
                misc_where = or_(
                    SMSLog.channel_id.is_(None),
                    ~SMSLog.channel_id.in_(list(channel_ids)),
                )
            else:
                misc_where = sql_true()

            stmt_misc = (
                update(SMSLog)
                .where(
                    and_(
                        SMSLog.status == 'sent',
                        SMSLog.sent_time < cutoff_default,
                        SMSLog.sent_time.isnot(None),
                        misc_where,
                    )
                )
                .values(
                    status='expired',
                    error_message=f'DLR 超时: 超过{default_h}小时未收到终态回执',
                )
            )
            r2 = await db.execute(stmt_misc)
            expired_count += r2.rowcount

            # --- SMPP SubmitSMResp 丢失处理 ---
            # queued + sent_time IS NULL = submit_sm 已写入 socket 但 SubmitSMResp 因会话断连而丢失。
            # 上游可能已收到并发送 DLR，但因 upstream_message_id 为 NULL 无法匹配，导致永久卡住。
            # 以 submit_time 为基准，超时后标记为 expired 解锁批次。
            SMPP_SUBMIT_RESP_TIMEOUT_HOURS = 2  # SubmitSMResp 通常秒级返回，2h 足够保守

            smpp_orphan_count = 0
            for ch_id, custom_h in channel_rows:
                smpp_cutoff = datetime.now() - timedelta(hours=SMPP_SUBMIT_RESP_TIMEOUT_HOURS)
                r_orphan = await db.execute(
                    update(SMSLog)
                    .where(
                        and_(
                            SMSLog.channel_id == ch_id,
                            SMSLog.status.in_(['queued', 'pending']),
                            SMSLog.sent_time.is_(None),
                            SMSLog.submit_time < smpp_cutoff,
                            SMSLog.submit_time.isnot(None),
                        )
                    )
                    .values(
                        status='expired',
                        error_message='SMPP SubmitSMResp丢失: 会话断连或消费超时，超时标记',
                    )
                )
                smpp_orphan_count += r_orphan.rowcount

            await db.commit()

            if smpp_orphan_count > 0:
                logger.warning(f"SMPP 孤儿 queued 清理: 标记 {smpp_orphan_count} 条为 expired（SubmitSMResp 丢失）")

            if expired_count > 0:
                logger.info(f"DLR 超时: 标记 {expired_count} 条记录为 expired（默认阈值 {default_h}h）")
            else:
                logger.debug("DLR 超时检查: 无超时记录")

            return {"success": True, "expired": expired_count}
    finally:
        await eng.dispose()


# ============ 虚拟通道回执生成任务 ============

@celery_app.task(name="virtual_dlr_generate", bind=True, max_retries=3,
                 autoretry_for=(Exception,), retry_backoff=2, retry_backoff_max=30)
def virtual_dlr_generate_task(self, message_id: str, channel_id: int):
    """延迟生成虚拟通道的模拟回执（单条，兼容旧逻辑）"""
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_do_virtual_dlr(message_id, channel_id))
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


@celery_app.task(name="virtual_submit_simulate", bind=True, max_retries=2,
                 autoretry_for=(Exception,), retry_backoff=5, retry_backoff_max=60,
                 soft_time_limit=10 * 60, time_limit=12 * 60,
                 acks_late=True, reject_on_worker_lost=True)
def virtual_submit_simulate_task(self, message_ids: list, channel_id: int, batch_id: int = None):
    """模拟虚拟通道上游提交：将 pending 状态批量更新为 sent"""
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_do_virtual_submit(message_ids, channel_id, batch_id))
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


async def _do_virtual_submit(message_ids: list, channel_id: int, batch_id: int = None):
    """批量将 pending 消息更新为 sent，模拟上游提交完成"""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession as _AS
    from sqlalchemy import update as sa_update
    from app.modules.sms.sms_batch import SmsBatch

    eng = create_async_engine(
        settings.SQLALCHEMY_DATABASE_URL, echo=False,
        pool_size=2, max_overflow=1, pool_pre_ping=True, pool_recycle=300,
    )
    factory = async_sessionmaker(eng, class_=_AS, expire_on_commit=False)
    updated = 0
    now = datetime.now()

    try:
        async with factory() as db:
            if batch_id:
                _bs = (await db.execute(select(SmsBatch.status).where(SmsBatch.id == batch_id))).scalar_one_or_none()
                if _bs in ('cancelled', 'failed'):
                    logger.info(f"虚拟提交跳过: batch={batch_id} 已{_bs}")
                    return {"updated": 0, "skipped": True}
            for chunk_start in range(0, len(message_ids), 200):
                chunk_ids = message_ids[chunk_start:chunk_start + 200]
                result = await db.execute(
                    sa_update(SMSLog)
                    .where(
                        SMSLog.message_id.in_(chunk_ids),
                        SMSLog.status == "pending",
                    )
                    .values(status="sent", sent_time=now)
                )
                updated += result.rowcount
                await db.commit()

            if batch_id:
                await update_batch_progress(db, batch_id)

        logger.info(
            f"虚拟通道提交模拟完成: batch={batch_id}, updated={updated}/{len(message_ids)}"
        )
        return {"updated": updated}
    except Exception as e:
        logger.error(f"虚拟通道提交模拟异常: batch={batch_id}, {e}")
        raise
    finally:
        await eng.dispose()


@celery_app.task(name="virtual_dlr_batch_generate", bind=True, max_retries=2,
                 autoretry_for=(Exception,), retry_backoff=5, retry_backoff_max=60,
                 soft_time_limit=15 * 60, time_limit=20 * 60,
                 acks_late=True, reject_on_worker_lost=True)
def virtual_dlr_batch_generate_task(self, message_ids: list, channel_id: int, batch_id: int = None):
    """批量生成虚拟通道回执，一个任务处理一整个分片（最多500条）"""
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_do_virtual_dlr_batch(message_ids, channel_id, batch_id))
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


async def _do_virtual_dlr_batch(message_ids: list, channel_id: int, batch_id: int = None):
    """批量处理虚拟DLR：一个DB连接处理整个分片"""
    import random
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession as _AS
    from app.modules.sms.sms_batch import SmsBatch

    eng = create_async_engine(
        settings.SQLALCHEMY_DATABASE_URL, echo=False,
        pool_size=2, max_overflow=1, pool_pre_ping=True, pool_recycle=300,
    )
    factory = async_sessionmaker(eng, class_=_AS, expire_on_commit=False)
    delivered = 0
    failed_cnt = 0
    expired_cnt = 0

    try:
        async with factory() as db:
            if batch_id:
                _bs = (await db.execute(select(SmsBatch.status).where(SmsBatch.id == batch_id))).scalar_one_or_none()
                if _bs in ('cancelled', 'failed'):
                    logger.info(f"虚拟DLR跳过: batch={batch_id} 已{_bs}")
                    return {"delivered": 0, "failed": 0, "expired": 0, "skipped": True}

            ch_result = await db.execute(
                select(Channel).where(Channel.id == channel_id)
            )
            channel = ch_result.scalar_one_or_none()
            cfg = channel.get_virtual_config() if channel else {}

            delivery_rate_min = cfg.get("delivery_rate_min", 80)
            delivery_rate_max = cfg.get("delivery_rate_max", 90)
            fail_rate_min = cfg.get("fail_rate_min", 5)
            fail_rate_max = cfg.get("fail_rate_max", 15)
            fail_codes = cfg.get("fail_codes", ["UNDELIV"])

            delivery_base = random.uniform(delivery_rate_min, delivery_rate_max)
            fail_base = random.uniform(fail_rate_min, fail_rate_max)
            delivery_rate = max(0.0, min(100.0, delivery_base + random.gauss(0, 1.5)))
            fail_rate = max(0.0, min(100.0 - delivery_rate, fail_base + random.gauss(0, 0.8)))

            now = datetime.now()

            delivered_items = []

            for chunk_start in range(0, len(message_ids), 100):
                chunk_ids = message_ids[chunk_start:chunk_start + 100]
                result = await db.execute(
                    select(SMSLog).where(
                        SMSLog.message_id.in_(chunk_ids),
                        SMSLog.status.in_(["sent", "pending", "queued"]),
                    )
                )
                logs = result.scalars().all()

                for sms_log in logs:
                    if not sms_log.sent_time:
                        sms_log.sent_time = now
                    roll = random.uniform(0, 100)
                    if roll < delivery_rate:
                        sms_log.status = "delivered"
                        sms_log.delivery_time = now
                        sms_log.error_message = None
                        delivered += 1
                        delivered_items.append((sms_log.id, sms_log.message, sms_log.country_code, sms_log.account_id))
                    elif roll < delivery_rate + fail_rate:
                        sms_log.status = "failed"
                        code = random.choice(fail_codes) if fail_codes else "UNDELIV"
                        sms_log.error_message = f"SMPP DLR: stat={code} err={random.randint(1,99):03d}"
                        failed_cnt += 1
                    else:
                        sms_log.status = "expired"
                        sms_log.error_message = _mimic_smpp_expired_dlr_message()
                        expired_cnt += 1

                await db.commit()

                # 批量虚拟回执与单条 API 行为对齐：终态入 Webhook 队列
                for _log in logs:
                    if _log.status not in ("delivered", "failed", "expired"):
                        continue
                    try:
                        from app.workers.webhook_worker import trigger_webhook
                        await trigger_webhook(
                            _log.message_id,
                            _log.status,
                            {
                                "phone_number": _log.phone_number,
                                "country_code": _log.country_code,
                                "error_message": _log.error_message if _log.status != "delivered" else None,
                            },
                            account_id=_log.account_id,
                        )
                    except Exception as _e:
                        logger.warning(f"虚拟DLR批量Webhook失败: {_log.message_id}, {_e}")

            if batch_id:
                await update_batch_progress(db, batch_id)

            # 注水触发：对 delivered 消息按概率调度点击任务
            if delivered_items:
                from app.utils.water_trigger import trigger_water_for_delivered
                await trigger_water_for_delivered(db, delivered_items, channel_id, batch_id)

        logger.info(
            f"虚拟DLR批量完成: batch={batch_id}, "
            f"delivered={delivered}, failed={failed_cnt}, expired={expired_cnt}"
        )
        return {"delivered": delivered, "failed": failed_cnt, "expired": expired_cnt}
    except Exception as e:
        logger.error(f"虚拟DLR批量异常: batch={batch_id}, {e}")
        raise
    finally:
        await eng.dispose()


async def _do_virtual_dlr(message_id: str, channel_id: int):
    """根据虚拟通道配置，随机决定回执状态并更新 SMSLog（单条兼容）"""
    import random
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession as _AS
    eng = create_async_engine(
        settings.SQLALCHEMY_DATABASE_URL, echo=False,
        pool_size=1, max_overflow=0, pool_pre_ping=True, pool_recycle=300,
    )
    factory = async_sessionmaker(eng, class_=_AS, expire_on_commit=False)
    try:
        async with factory() as db:
            result = await db.execute(
                select(SMSLog).where(SMSLog.message_id == message_id)
            )
            sms_log = result.scalar_one_or_none()
            if not sms_log:
                logger.warning(f"虚拟DLR: 未找到记录 {message_id}")
                return {"success": False, "reason": "not_found"}

            if sms_log.status not in ("sent", "pending", "queued"):
                return {"success": True, "status": sms_log.status}

            ch_result = await db.execute(
                select(Channel).where(Channel.id == channel_id)
            )
            channel = ch_result.scalar_one_or_none()
            cfg = channel.get_virtual_config() if channel else {}

            delivery_rate_min = cfg.get("delivery_rate_min", 80)
            delivery_rate_max = cfg.get("delivery_rate_max", 90)
            fail_rate_min = cfg.get("fail_rate_min", 5)
            fail_rate_max = cfg.get("fail_rate_max", 15)
            fail_codes = cfg.get("fail_codes", ["UNDELIV"])

            delivery_base = random.uniform(delivery_rate_min, delivery_rate_max)
            fail_base = random.uniform(fail_rate_min, fail_rate_max)

            delivery_rate = delivery_base + random.gauss(0, 1.5)
            fail_rate = fail_base + random.gauss(0, 0.8)
            delivery_rate = max(0.0, min(100.0, delivery_rate))
            fail_rate = max(0.0, min(100.0 - delivery_rate, fail_rate))

            roll = random.uniform(0, 100)
            if roll < delivery_rate:
                new_status = "delivered"
                sms_log.delivery_time = datetime.now()
                sms_log.error_message = None
            elif roll < delivery_rate + fail_rate:
                new_status = "failed"
                code = random.choice(fail_codes) if fail_codes else "UNDELIV"
                err_no = f"{random.randint(1,99):03d}"
                sms_log.error_message = f"SMPP DLR: stat={code} err={err_no}"
            else:
                new_status = "expired"
                sms_log.error_message = _mimic_smpp_expired_dlr_message()

            sms_log.status = new_status
            await db.commit()

            if sms_log.batch_id:
                await update_batch_progress(db, sms_log.batch_id)

            # 与真实 DLR 一致：终态后触发注水与 Webhook
            if new_status == "delivered" and sms_log.account_id:
                try:
                    from app.utils.water_trigger import trigger_water_single
                    await trigger_water_single(
                        db, sms_log.id, sms_log.message,
                        sms_log.country_code, sms_log.account_id,
                        channel_id=sms_log.channel_id,
                    )
                except Exception as e:
                    logger.warning(f"虚拟DLR注水触发异常: {e}")
            try:
                from app.workers.webhook_worker import trigger_webhook
                await trigger_webhook(
                    message_id,
                    new_status,
                    {
                        "phone_number": sms_log.phone_number,
                        "country_code": sms_log.country_code,
                        "error_message": sms_log.error_message if new_status != "delivered" else None,
                    },
                    account_id=sms_log.account_id,
                )
            except Exception as e:
                logger.warning(f"虚拟DLR触发Webhook失败: {e}")

            return {"success": True, "message_id": message_id, "status": new_status}
    except Exception as e:
        logger.error(f"虚拟DLR异常: {message_id}, {e}")
        raise
    finally:
        await eng.dispose()


@celery_app.task(name="repair_virtual_batch_dlr", bind=True, max_retries=1)
def repair_virtual_batch_dlr_task(self, batch_id: int):
    """按 batch_id 为仍处 sent/pending/queued 的短信补调度虚拟终态（修复卡回执批次）"""
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_do_repair_virtual_batch_dlr(batch_id))
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


async def _do_repair_virtual_batch_dlr(batch_id: int):
    from collections import defaultdict

    eng, Session = _make_session()
    try:
        async with Session() as db:
            rows = (
                await db.execute(
                    select(SMSLog.message_id, SMSLog.channel_id).where(
                        SMSLog.batch_id == batch_id,
                        SMSLog.status.in_(["sent", "pending", "queued"]),
                    )
                )
            ).all()
            if not rows:
                logger.info(f"repair_virtual_batch_dlr: batch={batch_id} 无待处理记录")
                return {"batch_id": batch_id, "chunks_scheduled": 0}

            by_chan = defaultdict(list)
            for mid, cid in rows:
                if cid:
                    by_chan[cid].append(mid)

            chunks_scheduled = 0
            for cid, mids in by_chan.items():
                ch_row = await db.execute(select(Channel.protocol).where(Channel.id == cid))
                prot = ch_row.scalar_one_or_none()
                pv = getattr(prot, "value", prot)
                pv = getattr(pv, "value", pv)
                if str(pv or "").upper() != "VIRTUAL":
                    logger.warning(
                        f"repair_virtual_batch_dlr: batch={batch_id} channel_id={cid} 非 VIRTUAL，跳过"
                    )
                    continue

                chunk_size = 500
                for bi, start in enumerate(range(0, len(mids), chunk_size)):
                    chunk = mids[start : start + chunk_size]
                    virtual_dlr_batch_generate_task.apply_async(
                        args=[chunk, cid, batch_id],
                        countdown=2 + bi * 2,
                        queue="sms_send",
                    )
                    chunks_scheduled += 1

            logger.info(
                f"repair_virtual_batch_dlr: batch={batch_id}, chunks_scheduled={chunks_scheduled}"
            )
            return {"batch_id": batch_id, "chunks_scheduled": chunks_scheduled}
    finally:
        await eng.dispose()


# ---------- Go 网关 SubmitSM 结果异步回写（合并 UPDATE，减轻 MySQL 压力）----------
_SMS_RESULT_BUFFER: List[dict] = []
_SMS_RESULT_LOCK = threading.Lock()
_SMS_RESULT_TIMER: Optional[threading.Timer] = None


def _sms_result_is_deadlock(exc: BaseException) -> bool:
    """判断是否为 InnoDB 死锁(1213)，可整批重试。"""
    orig = getattr(exc, "orig", None)
    if orig is not None:
        args = getattr(orig, "args", ()) or ()
        if args and args[0] == 1213:
            return True
    if getattr(exc, "args", None) and exc.args and exc.args[0] == 1213:
        return True
    s = str(exc)
    return "1213" in s or "Deadlock" in s or "deadlock" in s


def _sms_result_remove_flushed_from_buffer(flushed: List[dict]) -> None:
    """按 log_id 从进程缓冲中剔除已成功落库的结果，避免失败时误删未持久化数据。"""
    flushed_ids = {int(x.get("log_id") or 0) for x in flushed if int(x.get("log_id") or 0) > 0}
    if not flushed_ids:
        return
    with _SMS_RESULT_LOCK:
        _SMS_RESULT_BUFFER[:] = [
            r for r in _SMS_RESULT_BUFFER if int(r.get("log_id") or 0) not in flushed_ids
        ]


async def _apply_sms_result_row_to_db(db, r: dict, now: datetime) -> Optional[int]:
    """单条 sms_logs 更新；返回 batch_id 供后续进度汇总。"""
    log_id = int(r.get("log_id") or 0)
    if log_id <= 0:
        return None
    st = (r.get("status") or "").strip() or "failed"
    up = (r.get("upstream_message_id") or "").strip() or None
    err = (r.get("error") or "")[:4000]
    br = await db.execute(select(SMSLog.batch_id).where(SMSLog.id == log_id))
    bid = br.scalar_one_or_none()
    vals: Dict[str, Any] = {
        "status": st,
        "upstream_message_id": up,
    }
    if st == "failed":
        vals["error_message"] = err
        vals["sent_time"] = now
    elif st == "sent":
        vals["error_message"] = None
        vals["sent_time"] = now
    await db.execute(update(SMSLog).where(SMSLog.id == log_id).values(**vals))
    return int(bid) if bid is not None else None


async def _flush_sms_results_bulk_once(rows: List[dict]) -> None:
    """单会话整批提交；失败抛异常由上层重试或降级。"""
    eng, Session = _make_session()
    try:
        async with Session() as db:
            now = datetime.now()
            batch_ids: Set[int] = set()
            for r in rows:
                bid = await _apply_sms_result_row_to_db(db, r, now)
                if bid is not None:
                    batch_ids.add(bid)
            await db.commit()
            for bid in batch_ids:
                try:
                    await update_batch_progress(db, bid)
                except Exception as e:
                    logger.warning(f"update_batch_progress batch={bid}: {e}")
    finally:
        await eng.dispose()


async def _flush_sms_results_one_by_one(rows: List[dict]) -> bool:
    """整批失败时降级：逐条独立会话提交，隔离脏数据。"""
    now = datetime.now()
    batch_ids: Set[int] = set()
    ok_any = False
    for r in rows:
        log_id = int(r.get("log_id") or 0)
        if log_id <= 0:
            continue
        eng, Session = _make_session()
        try:
            async with Session() as db:
                bid = await _apply_sms_result_row_to_db(db, r, now)
                await db.commit()
                if bid is not None:
                    batch_ids.add(bid)
            ok_any = True
        except Exception as e2:
            logger.error(
                f"sms_result 单条降级回写仍失败 log_id={log_id}: {e2}",
                exc_info=e2,
            )
        finally:
            await eng.dispose()
    for bid in batch_ids:
        try:
            eng2, Session2 = _make_session()
            async with Session2() as db2:
                await update_batch_progress(db2, bid)
            await eng2.dispose()
        except Exception as e:
            logger.warning(f"update_batch_progress batch={bid}: {e}")
    return ok_any


async def _flush_sms_results_async(rows: List[dict]) -> bool:
    """批量回写 Go 网关 Submit 结果；死锁可重试一次，仍失败则逐条降级。"""
    if not rows:
        return True
    try:
        await _flush_sms_results_bulk_once(rows)
        return True
    except OperationalError as e:
        if _sms_result_is_deadlock(e):
            logger.warning(f"sms_result 整批刷盘遇死锁，将重试一次: {e}")
            await asyncio.sleep(0.08)
            try:
                await _flush_sms_results_bulk_once(rows)
                return True
            except Exception as e2:
                logger.error(
                    f"sms_result 整批刷盘重试仍失败，降级逐条: {e2}",
                    exc_info=e2,
                )
                return await _flush_sms_results_one_by_one(rows)
        logger.error(f"sms_result 整批刷盘 OperationalError: {e}", exc_info=e)
        return await _flush_sms_results_one_by_one(rows)
    except Exception as e:
        logger.error(f"sms_result 整批刷盘异常，降级逐条: {e}", exc_info=e)
        return await _flush_sms_results_one_by_one(rows)


def _flush_sms_results_sync(rows: List[dict]) -> bool:
    if not rows:
        return True
    return bool(_run_async(_flush_sms_results_async(rows)))


def _timer_flush_sms_results():
    global _SMS_RESULT_TIMER
    snap: List[dict] = []
    with _SMS_RESULT_LOCK:
        _SMS_RESULT_TIMER = None
        if _SMS_RESULT_BUFFER:
            snap = list(_SMS_RESULT_BUFFER)
    if not snap:
        return
    if _flush_sms_results_sync(snap):
        _sms_result_remove_flushed_from_buffer(snap)
    else:
        logger.error(
            f"sms_result 定时刷盘失败，已保留缓冲内约 {len(snap)} 条待后续重试"
        )


def _enqueue_sms_result_buffer(item: dict):
    global _SMS_RESULT_TIMER
    snap: Optional[List[dict]] = None
    with _SMS_RESULT_LOCK:
        _SMS_RESULT_BUFFER.append(item)
        if len(_SMS_RESULT_BUFFER) >= 200:
            snap = list(_SMS_RESULT_BUFFER[:200])
            if _SMS_RESULT_TIMER is not None:
                try:
                    _SMS_RESULT_TIMER.cancel()
                except Exception:
                    pass
                _SMS_RESULT_TIMER = None
        elif _SMS_RESULT_TIMER is None:
            _SMS_RESULT_TIMER = threading.Timer(1.0, _timer_flush_sms_results)
            _SMS_RESULT_TIMER.daemon = True
            _SMS_RESULT_TIMER.start()
    if snap is not None:
        if _flush_sms_results_sync(snap):
            _sms_result_remove_flushed_from_buffer(snap)
        else:
            logger.error(
                f"sms_result 满200刷盘失败，已保留缓冲内数据（含本批 {len(snap)} 条）待重试"
            )


@celery_app.task(name="process_sms_result_task", acks_late=True)
def process_sms_result_task(item: dict):
    """消费 Go 网关回传的 SubmitSM 结果，200 条或 1 秒合并刷盘。"""
    try:
        _enqueue_sms_result_buffer(item)
    except Exception as e:
        logger.error(f"process_sms_result_task 入缓冲失败: {e}", exc_info=e)
    return {"ok": True}
