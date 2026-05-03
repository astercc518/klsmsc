"""
批量发送 Celery Worker
"""
import os
import csv
import io
import time
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.workers.celery_app import celery_app
from app.config import settings
from app.modules.sms.sms_batch import SmsBatch, BatchStatus
from app.modules.sms.sms_log import SMSLog
from app.modules.sms.sms_template import SmsTemplate
from app.modules.common.account import Account
from app.core.pricing import PricingEngine
from app.core.router import RoutingEngine
from app.utils.queue import QueueManager
from app.utils.validator import Validator
from app.utils.logger import get_logger
from app.utils.errors import InsufficientBalanceError, PricingNotFoundError
from app.utils.cache import get_cache_manager

logger = get_logger(__name__)

_worker_engine = None
_worker_session_factory = None


_DB_CONNECT_ARGS = {
    "connect_timeout": int(os.getenv("WORKER_DB_CONNECT_TIMEOUT_SEC", "10")),
    "read_timeout": int(os.getenv("WORKER_DB_READ_TIMEOUT_SEC", "30")),
}
_RUN_ASYNC_DEFAULT_TIMEOUT = float(os.getenv("WORKER_RUN_ASYNC_TIMEOUT_SEC", "60"))


def _get_worker_session():
    """复用进程级单例引擎，避免每次任务新建连接池"""
    global _worker_engine, _worker_session_factory
    if _worker_engine is None:
        from sqlalchemy.pool import NullPool
        _worker_engine = create_async_engine(
            settings.SQLALCHEMY_DATABASE_URL,
            echo=False,
            poolclass=NullPool,
            pool_pre_ping=True,
            pool_recycle=600,
            connect_args=_DB_CONNECT_ARGS,
        )
        _worker_session_factory = async_sessionmaker(
            _worker_engine, class_=AsyncSession, expire_on_commit=False
        )
    return _worker_session_factory()

def _make_fresh_session():
    """每个任务创建独立的引擎和会话，避免事件循环冲突"""
    eng = create_async_engine(
        settings.SQLALCHEMY_DATABASE_URL,
        echo=False,
        pool_size=2,
        max_overflow=0,
        pool_pre_ping=True,
        pool_recycle=600,
        connect_args=_DB_CONNECT_ARGS,
    )
    factory = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    return eng, factory


def _run_async(coro, *, timeout: Optional[float] = None):
    """在 Celery 同步 worker 中安全地执行异步协程。
    超时保护：批量任务里某次 DB 卡死会拖死整个 worker 进程，硬上限避免长期占槽。
    """
    eff_timeout = timeout if timeout is not None else _RUN_ASYNC_DEFAULT_TIMEOUT
    loop = asyncio.new_event_loop()
    try:
        if eff_timeout and eff_timeout > 0:
            return loop.run_until_complete(asyncio.wait_for(coro, timeout=eff_timeout))
        return loop.run_until_complete(coro)
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        loop.close()

@celery_app.task(name='process_batch', bind=True)
def process_batch(self, batch_id: int):
    """
    异步处理批量发送任务
    """
    logger.info(f"开始处理批量发送任务: batch_id={batch_id}")
    # 大批次（10w+）CSV 解析 + 入队需要数分钟，给单独的长超时（1 小时）
    return _run_async(
        _do_process_batch(batch_id),
        timeout=float(os.getenv("WORKER_BATCH_TASK_TIMEOUT_SEC", "3600")),
    )


@celery_app.task(name='process_batch_resume', bind=True)
def process_batch_resume(self, batch_id: int):
    """
    补发未发送：跳过已在 sms_logs 的号码，处理 CSV 中剩余的行。
    用于「批次卡 processing / 中途异常 / 部分号码未入队」等场景。
    """
    logger.info(f"开始补发未发送行: batch_id={batch_id}")
    return _run_async(
        _do_process_batch(batch_id, resume=True),
        timeout=float(os.getenv("WORKER_BATCH_TASK_TIMEOUT_SEC", "3600")),
    )


async def _do_process_batch(batch_id: int, resume: bool = False):
    db = _get_worker_session()
    try:
        # 1. 获取批次记录
        result = await db.execute(select(SmsBatch).where(SmsBatch.id == batch_id))
        batch = result.scalar_one_or_none()
        if not batch:
            logger.error(f"批次记录不存在: {batch_id}")
            return

        if not resume:
            if batch.status != BatchStatus.PENDING:
                logger.warning(f"批次状态不是 PENDING: {batch_id}, status={batch.status}")
                return
        else:
            # 补发模式：要求批次属于 CSV 上传来源；状态可以是 processing/completed/failed
            if not batch.file_path:
                logger.error(f"补发跳过: 批次无 file_path（非 CSV 来源）, batch_id={batch_id}")
                return
            if batch.status == BatchStatus.CANCELLED:
                logger.warning(f"补发跳过: 批次已取消, batch_id={batch_id}")
                return

        # 2. 更新状态为处理中
        batch.status = BatchStatus.PROCESSING
        if not resume:
            batch.started_at = datetime.now()
        else:
            batch.completed_at = None
            batch.error_message = None
        await db.commit()

        # 补发模式：预先加载已处理过的号码集合，遍历 CSV 时直接跳过
        already_processed_phones: set = set()
        if resume:
            existing_res = await db.execute(
                select(SMSLog.phone_number).where(SMSLog.batch_id == batch_id)
            )
            already_processed_phones = {row[0] for row in existing_res.all()}
            logger.info(
                f"补发预加载: batch={batch_id}, 已处理 {len(already_processed_phones)} 条，"
                f"将跳过这些号码继续处理 CSV 剩余行"
            )

        # 3. 准备工具
        pricing_engine = PricingEngine(db)
        routing_engine = RoutingEngine(db)
        validator = Validator()
        
        # 获取模板（如果使用）
        template = None
        if batch.template_id:
            result = await db.execute(select(SmsTemplate).where(SmsTemplate.id == batch.template_id))
            template = result.scalar_one_or_none()
            if not template:
                logger.error(f"模板不存在: batch_id={batch_id}, template_id={batch.template_id}")
                batch.status = BatchStatus.FAILED
                batch.error_message = f"模板 ID {batch.template_id} 不存在"
                await db.commit()
                return

        # 4. 读取 CSV 文件
        if not batch.file_path or not os.path.exists(batch.file_path):
            logger.error(f"文件不存在: {batch.file_path}")
            batch.status = BatchStatus.FAILED
            batch.error_message = "文件不存在"
            await db.commit()
            return

        # 检测编码
        detected_enc = "utf-8"
        try:
            with open(batch.file_path, 'rb') as f:
                sample = f.read(4096)
                for enc in ("utf-8-sig", "utf-8", "gbk", "latin-1"):
                    try:
                        sample.decode(enc)
                        detected_enc = enc
                        break
                    except UnicodeDecodeError:
                        continue
        except Exception:
            pass

        # 流式读取 CSV（不一次性 load 全部，防止百万行 OOM）
        total_rows = 0
        success_count = 0
        failed_count = 0
        commit_batch = []
        COMMIT_EVERY = 500

        # 进程内缓存：同一批次中相同国家/通道组合无需重复查库/Redis
        _route_cache: dict = {}   # country_code -> Channel
        _channel: Optional[object] = None  # 最近一次使用的通道（用于剩余处理）
        _chunk_deducted: float = 0.0  # 当前 chunk 已扣款总额（用于汇总 BalanceLog）

        try:
            with open(batch.file_path, 'r', encoding=detected_enc, errors='replace') as f:
                reader = csv.DictReader(f)

                for i, row in enumerate(reader):
                    total_rows = i + 1

                    if i % 2000 == 0 and i > 0:
                        batch.progress = min(99, int(success_count * 100 / max(total_rows, 1)))
                        batch.success_count = success_count
                        batch.failed_count = failed_count
                        await db.commit()

                    phone = row.get('phone', '').strip()
                    if not phone:
                        failed_count += 1
                        continue

                    content = ""
                    if template:
                        content = template.content
                        for key, val in row.items():
                            if key != 'phone':
                                content = content.replace(f"{{{key}}}", str(val))
                    else:
                        content = row.get('content', '').strip()

                    if not content:
                        failed_count += 1
                        continue

                    e164, country_code = validator.validate_phone(phone)
                    if not e164:
                        failed_count += 1
                        continue

                    # 补发模式：跳过已处理的号码
                    if already_processed_phones and e164 in already_processed_phones:
                        continue

                    try:
                        # 进程内路由缓存：同一国家只查一次（路由引擎自身有 Redis 缓存，
                        # 这里再加一层 dict 缓存，省去 Redis 网络往返）
                        if country_code not in _route_cache:
                            _route_cache[country_code] = await routing_engine.select_channel(
                                country_code, account_id=batch.account_id
                            )
                        channel = _route_cache[country_code]
                        _channel = channel
                        if not channel:
                            failed_count += 1
                            continue

                        # skip_balance_log=True：跳过每条短信的 SELECT/INSERT/flush/Redis，
                        # 由下方 commit 点统一写一条汇总 BalanceLog（500 条 → 1 条）
                        charge_result = await pricing_engine.calculate_and_charge(
                            account_id=batch.account_id,
                            channel_id=channel.id,
                            country_code=country_code,
                            message=content,
                            channel=channel,
                            skip_balance_log=True,
                        )

                        message_id = f"MSG_{int(time.time()*1000)}_{i}_{batch.id}"
                        sms_log = SMSLog(
                            message_id=message_id,
                            account_id=batch.account_id,
                            batch_id=batch.id,
                            phone_number=e164,
                            country_code=country_code,
                            message=content,
                            message_count=charge_result.get("message_count", 1),
                            channel_id=channel.id,
                            cost_price=charge_result.get("total_base_cost", 0),
                            selling_price=charge_result.get("total_cost", 0),
                            currency=charge_result.get("currency", "USD"),
                            status="queued",
                            submit_time=datetime.now()
                        )
                        db.add(sms_log)
                        _chunk_cost = charge_result.get("total_cost", 0)
                        _chunk_deducted += _chunk_cost
                        commit_batch.append((message_id, _chunk_cost))

                        if len(commit_batch) >= COMMIT_EVERY:
                            await _flush_commit_chunk(
                                db, batch, channel, commit_batch,
                                _chunk_deducted,
                            )
                            s, f = await _queue_commit_batch(
                                db, batch.account_id, channel, commit_batch, batch,
                            )
                            success_count += s
                            failed_count += f
                            commit_batch.clear()
                            _chunk_deducted = 0.0

                    except (InsufficientBalanceError, PricingNotFoundError, Exception) as e:
                        logger.warning(f"处理行 {i} 失败: {e}")
                        failed_count += 1
                        continue

        except Exception as e:
            logger.error(f"解析 CSV 失败: {e}")
            batch.status = BatchStatus.FAILED
            batch.error_message = f"解析 CSV 失败: {str(e)}"
            await db.commit()
            return

        # 处理剩余
        if commit_batch and _channel:
            await _flush_commit_chunk(db, batch, _channel, commit_batch, _chunk_deducted)
            s, f = await _queue_commit_batch(db, batch.account_id, _channel, commit_batch, batch)
            success_count += s
            failed_count += f
            commit_batch.clear()

        if total_rows == 0:
            batch.status = BatchStatus.FAILED
            batch.error_message = "CSV 文件为空"
            await db.commit()
            return

        batch.total_count = total_rows
        from app.modules.sms.batch_utils import update_batch_progress

        await update_batch_progress(db, batch_id)
        await db.refresh(batch)
        # success_count 此处为入队成功条数，勿写入批次表；终态仅由 sms_logs 与 update_batch_progress 决定
        if batch.status not in (BatchStatus.COMPLETED, BatchStatus.FAILED, BatchStatus.CANCELLED):
            batch.status = BatchStatus.PROCESSING
            batch.completed_at = None
        await db.commit()

        logger.info(
            f"批次 CSV 入队完成: batch_id={batch_id}, total={total_rows}, "
            f"入队成功(本地计数)={success_count}, 入队失败(本地计数)={failed_count}"
        )

    except Exception as e:
        logger.exception(f"处理批次异常: {e}")
        try:
            batch.status = BatchStatus.FAILED
            batch.error_message = str(e)[:500]
            await db.commit()
        except Exception as rollback_err:
            logger.error(f"批次失败状态写入异常: {rollback_err}")
    finally:
        await db.close()

async def _refund_single(db, account_id: int, amount: float, message_id: str):
    """
    批次入队失败退款。走 services/sms_refund.execute_auto_refund 统一路径，
    会写完整 refunded_at/by/amount 使 Refund Audit 可见。
    保留 account_id/amount 参数兼容旧调用，但实际由 execute_auto_refund 按 sms_log 重新解析。
    """
    if amount <= 0:
        return
    try:
        from app.services.sms_refund import execute_auto_refund
        from app.modules.sms.sms_log import SMSLog as _SMSLog

        row = (await db.execute(
            select(_SMSLog).where(_SMSLog.message_id == message_id).limit(1)
        )).scalar_one_or_none()
        if not row:
            logger.warning(f"_refund_single: sms_log 未找到 message_id={message_id}")
            return
        # 嵌入批次事务，不自己 commit；批次链路统一在 _flush_commit_chunk 里 commit
        await execute_auto_refund(
            db, row.id,
            source="batch_queue_fail",
            note=f"batch queue fail",
            auto_commit=False,
        )
    except Exception as e:
        logger.error(f"退款失败: {message_id}, {e}")


async def _flush_commit_chunk(db, batch, channel, commit_batch: list, chunk_deducted: float):
    """
    flush + commit 当前 chunk，并写入一条汇总 BalanceLog + 更新 Redis 余额缓存。
    取代原来每条短信单独 SELECT/INSERT/flush/Redis，500 条短信只做 1 次。
    """
    from app.modules.common.balance_log import BalanceLog
    from app.utils.cache import get_cache_manager

    await db.flush()
    await db.commit()

    if chunk_deducted > 0:
        try:
            bal_row = await db.execute(select(Account.balance).where(Account.id == batch.account_id))
            balance_after = bal_row.scalar()
            db.add(BalanceLog(
                account_id=batch.account_id,
                change_type='charge',
                amount=-chunk_deducted,
                balance_after=float(balance_after) if balance_after is not None else 0.0,
                description=f"Batch {batch.id} charge: {len(commit_batch)} SMS",
            ))
            await db.commit()

            cache_manager = await get_cache_manager()
            await cache_manager.set(
                f"account:{batch.account_id}:balance",
                float(balance_after) if balance_after is not None else 0.0,
                ttl=60,
            )
        except Exception as e:
            logger.warning(f"批次 BalanceLog 写入失败(非致命): batch={batch.id}, {e}")

    _proto = str(channel.protocol).upper() if channel else "HTTP"
    logger.info(f"批次 {batch.id} commit chunk: 协议={_proto}, 数量={len(commit_batch)}, 扣款={chunk_deducted:.4f}")


async def _queue_commit_batch(
    db, account_id: int, channel, commit_batch: list, batch: Optional[SmsBatch] = None
) -> tuple[int, int]:
    """
    将 commit_batch 中的消息批量入队，返回 (success_count, failed_count)。
    """
    success = 0
    failed = 0
    _proto = str(channel.protocol).upper() if channel else "HTTP"

    if 'SMPP' in _proto:
        smpp_mids = [mid for mid, _ in commit_batch]
        bstat = ""
        if batch is not None:
            bstat = getattr(batch.status, "value", str(batch.status))
        from app.utils.smpp_payload import smpp_payload_public_dict

        rows = (await db.execute(select(SMSLog).where(SMSLog.message_id.in_(smpp_mids)))).scalars().all()
        mid_to_row = {r.message_id: r for r in rows}
        smpp_payloads = []
        for mid in smpp_mids:
            row = mid_to_row.get(mid)
            if row:
                smpp_payloads.append(smpp_payload_public_dict(row, bstat))
        from app.config import settings as _cfg
        _win = int(getattr(_cfg, 'SMPP_WINDOW_SIZE', 10) or 10)
        for _i in range(0, len(smpp_payloads), _win):
            _chunk = smpp_payloads[_i : _i + _win]
            if QueueManager.queue_sms_batch_smpp(_chunk):
                success += len(_chunk)
            else:
                for _p in _chunk:
                    if QueueManager.queue_smpp_gateway(_p):
                        success += 1
                    else:
                        failed += 1
    else:
        mids = [mid for mid, _ in commit_batch]
        costs = {mid: cost for mid, cost in commit_batch}
        ok_ids, fail_ids = QueueManager.queue_sms_bulk(mids)
        success += len(ok_ids)
        for mid in fail_ids:
            await _refund_single(db, account_id, costs.get(mid, 0), mid)
            failed += 1

    return success, failed


# ============ 大批量分片处理 ============

@celery_app.task(name='process_batch_chunk', bind=True, max_retries=1,
                 soft_time_limit=15 * 60, time_limit=20 * 60,
                 acks_late=True, reject_on_worker_lost=True)
def process_batch_chunk(
    self,
    batch_id: int,
    account_id: int,
    phone_numbers: list,
    message: str,
    rot_messages: list,
    start_offset: int,
    channel_id: int = None,
    sender_id: str = None,
):
    """处理一个分片（规模由 API 的 CHUNK_SIZE 决定，通常 ≤5000）：校验 → 计费 → 写库 → 入队"""
    logger.info(f"分片处理开始: batch={batch_id}, offset={start_offset}, count={len(phone_numbers)}")
    return _run_async(_do_process_chunk(
        batch_id, account_id, phone_numbers, message,
        rot_messages, start_offset, channel_id, sender_id,
    ))


async def _do_process_chunk(
    batch_id: int,
    account_id: int,
    phone_numbers: list,
    message: str,
    rot_messages: list,
    start_offset: int,
    channel_id: int = None,
    sender_id: str = None,
):
    import uuid
    from decimal import Decimal
    from app.utils.sms_template import render_sms_variables, sms_template_has_variables
    from app.modules.sms.channel import Channel

    eng, factory = _make_fresh_session()
    succeeded = 0
    failed = 0
    use_rotate = len(rot_messages) > 0
    _charged_amount = Decimal('0')  # 扣费已提交但未完成分片写库时的回滚金额

    try:
        async with factory() as db:
            from app.utils.account_country_restrict import assert_sms_destination_allowed, AccountCountryNotAllowedError

            # 批次状态检查：已取消或已失败的批次直接跳过
            _batch_chk = await db.execute(
                select(SmsBatch.status).where(SmsBatch.id == batch_id)
            )
            _batch_status = _batch_chk.scalar_one_or_none()
            _batch_status_str = getattr(_batch_status, "value", str(_batch_status or ""))
            if _batch_status in ('cancelled', 'failed'):
                logger.info(f"分片跳过: batch={batch_id} 已{_batch_status}，offset={start_offset}")
                return {"succeeded": 0, "failed": 0, "skipped": True}

            # 幂等性检查：worker 重启后重试时跳过已处理的号码
            existing_res = await db.execute(
                select(SMSLog.phone_number).where(
                    SMSLog.batch_id == batch_id,
                    SMSLog.phone_number.in_(phone_numbers),
                )
            )
            already_done = set(r[0] for r in existing_res.all())

            # 黑名单预查询：一次性捞出本分片内所有黑名单号码，逐号码循环时 O(1) 判断
            blacklisted_phones: set = set()
            try:
                from app.modules.data.models import DataNumber
                bl_rows = await db.execute(
                    select(DataNumber.phone_number)
                    .where(DataNumber.phone_number.in_(phone_numbers),
                           DataNumber.status == 'blacklisted')
                )
                blacklisted_phones = {r[0] for r in bl_rows.all()}
                if blacklisted_phones:
                    logger.info(f"批量黑名单预检: batch={batch_id}, 命中 {len(blacklisted_phones)} 个号码")
            except Exception as _bl_err:
                logger.warning(f"批量黑名单预查询异常(忽略): {_bl_err}")
            if already_done:
                logger.info(
                    f"分片幂等检查: batch={batch_id}, offset={start_offset}, "
                    f"已存在 {len(already_done)}/{len(phone_numbers)} 条，跳过重复"
                )

            acc_row = await db.execute(select(Account).where(Account.id == account_id))
            batch_account = acc_row.scalar_one_or_none()

            routing_engine = RoutingEngine(db)
            pricing_engine = PricingEngine(db)
            commit_batch = []
            is_virtual_channel = False
            virtual_channel_id = None
            virtual_message_ids = []

            # 预检测：如果指定了通道且是虚拟通道，走批量快速路径
            _pre_channel = None
            if channel_id:
                from app.modules.sms.channel import Channel as _PreCh
                _pre_r = await db.execute(select(_PreCh).where(_PreCh.id == channel_id))
                _pre_channel = _pre_r.scalar_one_or_none()

            if _pre_channel and _pre_channel.protocol == 'VIRTUAL':
                # ====== 虚拟通道批量快速路径 ======
                is_virtual_channel = True
                virtual_channel_id = _pre_channel.id
                from decimal import Decimal
                from app.modules.common.balance_log import BalanceLog

                # 1. 验证所有号码并渲染消息
                valid_items = []
                for i, phone_number in enumerate(phone_numbers):
                    if phone_number in already_done:
                        succeeded += 1
                        continue
                    batch_index = start_offset + i + 1
                    phone_number = str(phone_number).strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
                    is_valid, err_msg, phone_info = Validator.validate_phone_number(phone_number)
                    if not is_valid:
                        logger.warning(f"分片预检失败 (格式错误): batch={batch_id}, phone={phone_number}, error={err_msg}")
                        failed += 1
                        continue
                    if phone_number in blacklisted_phones or phone_info.get('e164_format') in blacklisted_phones:
                        logger.info(f"分片预检失败 (黑名单): batch={batch_id}, phone={phone_number}")
                        failed += 1
                        continue
                    cc = phone_info['country_code']
                    if batch_account:
                        try:
                            assert_sms_destination_allowed(batch_account, cc)
                        except AccountCountryNotAllowedError as e:
                            logger.warning(f"分片预检失败 (国家限制): batch={batch_id}, phone={phone_number}, country={cc}, error={e.message}")
                            failed += 1
                            continue
                    raw_body = rot_messages[(batch_index - 1) % len(rot_messages)] if use_rotate else message
                    has_tpl_vars = sms_template_has_variables(raw_body)
                    final_msg = (
                        render_sms_variables(raw_body, index=batch_index,
                                             phone_e164=phone_info["e164_format"], country_code=cc)
                        if has_tpl_vars else raw_body
                    )
                    msg_count = pricing_engine._count_sms_parts(final_msg)
                    valid_items.append((phone_info, cc, final_msg, msg_count, batch_index))

                if valid_items:
                    # 2. 一次性查价（按 country_code 缓存）
                    price_cache: Dict[str, Any] = {}
                    total_sell = Decimal('0')
                    total_cost = Decimal('0')
                    for _, cc, _, msg_count, _ in valid_items:
                        if cc not in price_cache:
                            pi = await pricing_engine.get_price(_pre_channel.id, cc, None, account_id)
                            base_cost = await pricing_engine.resolve_base_cost_per_sms(
                                _pre_channel.id, cc, _pre_channel)
                            price_cache[cc] = (
                                Decimal(str(pi['price'])) if pi else Decimal('0'),
                                pi.get('currency', 'USD') if pi else 'USD',
                                base_cost,
                            )
                        sell_pp, currency, cost_pp = price_cache[cc]
                        total_sell += sell_pp * msg_count
                        total_cost += cost_pp * msg_count

                    # 3. 一次性扣款
                    deduct_ok = True
                    if total_sell > 0:
                        from sqlalchemy import update as sa_update
                        _is_postpaid = (getattr(batch_account, 'payment_type', None) == 'postpaid')
                        _deduct_stmt = sa_update(Account).values(balance=Account.balance - total_sell)
                        if _is_postpaid:
                            _deduct_stmt = _deduct_stmt.where(Account.id == account_id)
                        else:
                            _deduct_stmt = _deduct_stmt.where(Account.id == account_id, Account.balance >= total_sell)
                        dr = await db.execute(_deduct_stmt)
                        if dr.rowcount == 0:
                            deduct_ok = False
                            failed += len(valid_items)
                            logger.warning(f"虚拟通道批量扣款失败: batch={batch_id}, 余额不足, total_sell={total_sell}")
                        else:
                            bal_r = await db.execute(select(Account.balance).where(Account.id == account_id))
                            bal_after = bal_r.scalar() or 0
                            db.add(BalanceLog(
                                account_id=account_id, change_type='charge',
                                amount=-total_sell, balance_after=bal_after,
                                description=f"Virtual batch: {len(valid_items)} msgs, batch#{batch_id}"
                            ))
                            cache_manager = await get_cache_manager()
                            await cache_manager.set(f"account:{account_id}:balance", float(bal_after), ttl=60)

                    # 4. 分片批量创建 SMSLog（避免单次包体过大 / 长事务）
                    if deduct_ok:
                        now = datetime.now()
                        _db_log_chunk = 5000
                        for _c0 in range(0, len(valid_items), _db_log_chunk):
                            _sub = valid_items[_c0 : _c0 + _db_log_chunk]
                            _rows: List[SMSLog] = []
                            for phone_info, cc, final_msg, msg_count, batch_index in _sub:
                                sell_pp, currency, cost_pp = price_cache[cc]
                                mid = f"msg_{uuid.uuid4().hex}"
                                sms_log = SMSLog(
                                    message_id=mid, account_id=account_id, channel_id=_pre_channel.id,
                                    phone_number=phone_info['e164_format'], country_code=cc,
                                    message=final_msg, message_count=msg_count,
                                    status='pending', cost_price=float(cost_pp * msg_count),
                                    selling_price=float(sell_pp * msg_count), currency=currency,
                                    submit_time=now, batch_id=batch_id,
                                )
                                sms_log.upstream_message_id = f"VIRT-{uuid.uuid4().hex[:12]}"
                                _rows.append(sms_log)
                                virtual_message_ids.append(mid)
                                succeeded += 1
                            if _rows:
                                db.add_all(_rows)
                                await db.flush()
                                await db.commit()

            else:
                # ====== 普通通道批量快速路径（优化版） ======
                # 阶段1: 批量验证号码 + 渲染消息 + 缓存路由/查价
                from decimal import Decimal
                from app.modules.common.balance_log import BalanceLog

                _t0 = time.time()
                route_cache = {}   # country_code -> channel
                price_cache = {}   # (channel_id, country_code) -> (sell_pp, currency, cost_pp)
                valid_items = []   # [(phone_info, cc, final_msg, msg_count, batch_index, channel), ...]

                for i, phone_number in enumerate(phone_numbers):
                    if phone_number in already_done:
                        succeeded += 1
                        continue
                    batch_index = start_offset + i + 1
                    try:
                        phone_number = str(phone_number).strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
                        is_valid, err_msg, phone_info = Validator.validate_phone_number(phone_number)
                        if not is_valid:
                            logger.warning(f"分片预检失败 (格式错误): batch={batch_id}, phone={phone_number}, error={err_msg}")
                            failed += 1
                            continue

                        if phone_number in blacklisted_phones or phone_info.get('e164_format') in blacklisted_phones:
                            logger.info(f"分片预检失败 (黑名单): batch={batch_id}, phone={phone_number}")
                            failed += 1
                            continue

                        country_code = phone_info['country_code']
                        if batch_account:
                            try:
                                assert_sms_destination_allowed(batch_account, country_code)
                            except AccountCountryNotAllowedError as e:
                                logger.warning(f"分片预检失败 (国家限制): batch={batch_id}, phone={phone_number}, country={country_code}, error={e.message}")
                                failed += 1
                                continue

                        # 渲染消息
                        raw_body = rot_messages[(batch_index - 1) % len(rot_messages)] if use_rotate else message
                        has_tpl_vars = sms_template_has_variables(raw_body)
                        final_message = (
                            render_sms_variables(
                                raw_body, index=batch_index,
                                phone_e164=phone_info["e164_format"],
                                country_code=country_code,
                            )
                            if has_tpl_vars else raw_body
                        )
                        msg_count = pricing_engine._count_sms_parts(final_message)

                        # 路由（缓存）
                        if country_code not in route_cache:
                            ch = await routing_engine.select_channel(
                                country_code=country_code,
                                preferred_channel=channel_id,
                                strategy='priority',
                                account_id=account_id
                            )
                            route_cache[country_code] = ch
                        channel = route_cache[country_code]
                        if not channel:
                            logger.warning(f"分片预检失败 (无可用通道): batch={batch_id}, phone={phone_number}, country={country_code}")
                            failed += 1
                            continue

                        # 查价（缓存）
                        _pk = (channel.id, country_code)
                        if _pk not in price_cache:
                            pi = await pricing_engine.get_price(channel.id, country_code, None, account_id)
                            base_cost = await pricing_engine.resolve_base_cost_per_sms(
                                channel.id, country_code, channel)
                            price_cache[_pk] = (
                                Decimal(str(pi['price'])) if pi else Decimal('0'),
                                pi.get('currency', 'USD') if pi else 'USD',
                                base_cost,
                            )

                        valid_items.append((phone_info, country_code, final_message, msg_count, batch_index, channel))
                    except Exception as e:
                        logger.warning(f"分片预检失败: batch={batch_id}, phone={phone_number}, {e}")
                        failed += 1
                        continue

                _t1 = time.time()
                logger.info(f"批量预检完成: batch={batch_id}, offset={start_offset}, "
                            f"valid={len(valid_items)}, failed={failed}, 耗时={_t1 - _t0:.2f}s")

                if valid_items:
                    # 阶段2: 一次性批量扣费
                    total_sell = Decimal('0')
                    total_cost = Decimal('0')
                    for _, cc, _, msg_count, _, ch in valid_items:
                        sell_pp, currency, cost_pp = price_cache[(ch.id, cc)]
                        total_sell += sell_pp * msg_count
                        total_cost += cost_pp * msg_count

                    deduct_ok = True
                    if total_sell > 0:
                        from sqlalchemy import update as sa_update
                        from sqlalchemy.exc import OperationalError as _OpErr
                        _is_postpaid = (getattr(batch_account, 'payment_type', None) == 'postpaid')
                        dr = None
                        _attempts = 5
                        for _atmpt in range(_attempts):
                            try:
                                _deduct_stmt = sa_update(Account).values(balance=Account.balance - total_sell)
                                if _is_postpaid:
                                    _deduct_stmt = _deduct_stmt.where(Account.id == account_id)
                                else:
                                    _deduct_stmt = _deduct_stmt.where(Account.id == account_id, Account.balance >= total_sell)
                                dr = await db.execute(_deduct_stmt)
                                break
                            except _OpErr as _err:
                                _orig = getattr(_err, 'orig', None)
                                _code = (_orig.args[0] if _orig and getattr(_orig, 'args', None) else None)
                                if _code in (1205, 1213) and _atmpt < _attempts - 1:
                                    logger.warning(
                                        f"分片扣费行锁冲突({_code}) retry={_atmpt+1}: "
                                        f"batch={batch_id}, offset={start_offset}"
                                    )
                                    try:
                                        await db.rollback()
                                    except Exception:
                                        pass
                                    await asyncio.sleep(0.5 + _atmpt * 0.5)
                                    continue
                                raise
                        if dr is None or dr.rowcount == 0:
                            # 余额不足：逐条回退处理（按余额能扣多少扣多少）
                            deduct_ok = False
                            logger.warning(
                                f"批量扣费失败(余额不足): batch={batch_id}, "
                                f"total_sell={total_sell}, 回退逐条扣费"
                            )
                        else:
                            bal_r = await db.execute(select(Account.balance).where(Account.id == account_id))
                            bal_after = bal_r.scalar() or 0
                            db.add(BalanceLog(
                                account_id=account_id, change_type='charge',
                                amount=-total_sell, balance_after=bal_after,
                                description=f"Batch charge: {len(valid_items)} msgs, batch#{batch_id}"
                            ))
                            # 关键：立即 commit 释放 accounts 行锁，避免后续 INSERT 5000 sms_logs
                            # 长时间持锁（40+ 秒），阻塞其他 chunk 的扣费 UPDATE 触发 1205 lock_wait_timeout。
                            await db.commit()
                            _charged_amount = total_sell  # 供异常时退款使用
                            cache_manager = await get_cache_manager()
                            await cache_manager.set(f"account:{account_id}:balance", float(bal_after), ttl=60)

                    _t2 = time.time()
                    logger.info(f"批量扣费完成: batch={batch_id}, total_sell={total_sell}, "
                                f"deduct_ok={deduct_ok}, 耗时={_t2 - _t1:.2f}s")

                    if deduct_ok:
                        # 阶段3/4：分片写库 + 分片入队（每片最多 5000 条，降低 max_allowed_packet / 长事务风险）
                        now = datetime.now()
                        _db_log_chunk = 5000
                        _t3 = time.time()
                        from app.utils.smpp_payload import smpp_payload_public_dict

                        for _c0 in range(0, len(valid_items), _db_log_chunk):
                            sub_items = valid_items[_c0 : _c0 + _db_log_chunk]
                            chunk_logs: List[SMSLog] = []
                            smpp_logs_batch = []
                            http_mids = []
                            _batch_channel = None

                            for phone_info, cc, final_msg, msg_count, batch_index, ch in sub_items:
                                sell_pp, currency, cost_pp = price_cache[(ch.id, cc)]
                                mid = f"msg_{uuid.uuid4().hex}"
                                _batch_channel = ch

                                if ch.protocol == 'VIRTUAL':
                                    is_virtual_channel = True
                                    virtual_channel_id = ch.id
                                    init_status = 'pending'
                                elif 'SMPP' in str(ch.protocol).upper():
                                    # SMPP：写库用 pending，Go 网关取到消息后再改 queued 并写 submit_time。
                                    init_status = 'pending'
                                else:
                                    init_status = 'queued'

                                sms_log = SMSLog(
                                    message_id=mid, account_id=account_id, channel_id=ch.id,
                                    phone_number=phone_info['e164_format'], country_code=cc,
                                    message=final_msg, message_count=msg_count,
                                    status=init_status, cost_price=float(cost_pp * msg_count),
                                    selling_price=float(sell_pp * msg_count), currency=currency,
                                    submit_time=now, batch_id=batch_id,
                                )
                                if ch.protocol == 'VIRTUAL':
                                    sms_log.upstream_message_id = f"VIRT-{uuid.uuid4().hex[:12]}"
                                    virtual_message_ids.append(mid)
                                chunk_logs.append(sms_log)

                                _proto = str(ch.protocol).upper()
                                if 'SMPP' in _proto:
                                    smpp_logs_batch.append(sms_log)
                                elif ch.protocol != 'VIRTUAL':
                                    http_mids.append(mid)

                            if chunk_logs:
                                db.add_all(chunk_logs)
                                await db.flush()

                            smpp_payloads = [
                                smpp_payload_public_dict(sl, _batch_status_str)
                                for sl in smpp_logs_batch
                            ]
                            await db.commit()

                            if smpp_payloads:
                                if QueueManager.queue_sms_batch_smpp(smpp_payloads):
                                    succeeded += len(smpp_payloads)
                                else:
                                    for _p in smpp_payloads:
                                        if QueueManager.queue_smpp_gateway(_p):
                                            succeeded += 1
                                        else:
                                            failed += 1
                            if http_mids:
                                _ok_http, _bad_http = QueueManager.queue_sms_bulk(http_mids)
                                succeeded += len(_ok_http)
                                failed += len(_bad_http)

                        if is_virtual_channel:
                            succeeded += len(virtual_message_ids)

                        _t4 = time.time()
                        logger.info(
                            f"批量写库+入队完成(分片): batch={batch_id}, valid={len(valid_items)}, "
                            f"virtual={len(virtual_message_ids)}, 耗时={_t4 - _t3:.2f}s, 总耗时={_t4 - _t0:.2f}s"
                        )
                    else:
                        # 余额不足时逐条回退：尽可能扣到余额耗尽
                        balance_exhausted_at: Optional[int] = None
                        for _idx, (phone_info, cc, final_msg, msg_count, batch_index, ch) in enumerate(valid_items):
                            try:
                                charge_result = await pricing_engine.calculate_and_charge(
                                    account_id=account_id, channel_id=ch.id,
                                    country_code=cc, message=final_msg,
                                )
                                if not charge_result.get('success'):
                                    failed += 1
                                    continue

                                mid = f"msg_{uuid.uuid4().hex}"
                                if ch.protocol == 'VIRTUAL':
                                    is_virtual_channel = True
                                    virtual_channel_id = ch.id
                                init_status = 'pending' if ch.protocol == 'VIRTUAL' else 'queued'
                                sms_log = SMSLog(
                                    message_id=mid, account_id=account_id, channel_id=ch.id,
                                    phone_number=phone_info['e164_format'], country_code=cc,
                                    message=final_msg, message_count=charge_result['message_count'],
                                    status=init_status, cost_price=charge_result.get('total_base_cost', 0),
                                    selling_price=charge_result.get('total_cost', 0),
                                    currency=charge_result.get('currency', 'USD'),
                                    submit_time=datetime.now(), batch_id=batch_id,
                                )
                                if ch.protocol == 'VIRTUAL':
                                    sms_log.upstream_message_id = f"VIRT-{uuid.uuid4().hex[:12]}"
                                    virtual_message_ids.append(mid)
                                db.add(sms_log)
                                commit_batch.append((mid, charge_result.get('total_cost', 0)))

                                if len(commit_batch) >= 50:
                                    await db.flush()
                                    await db.commit()
                                    _proto = str(ch.protocol).upper()
                                    if is_virtual_channel:
                                        succeeded += len(commit_batch)
                                    elif 'SMPP' in _proto:
                                        _mids = [m for m, _ in commit_batch]
                                        from app.utils.smpp_payload import smpp_payload_public_dict

                                        _rows = (
                                            await db.execute(select(SMSLog).where(SMSLog.message_id.in_(_mids)))
                                        ).scalars().all()
                                        _by = {r.message_id: r for r in _rows}
                                        _pl = [
                                            smpp_payload_public_dict(_by[m], _batch_status_str)
                                            for m in _mids
                                            if m in _by
                                        ]
                                        if QueueManager.queue_sms_batch_smpp(_pl):
                                            succeeded += len(_pl)
                                        else:
                                            for _p in _pl:
                                                if QueueManager.queue_smpp_gateway(_p):
                                                    succeeded += 1
                                                else:
                                                    failed += 1
                                    else:
                                        for m, _ in commit_batch:
                                            if QueueManager.queue_sms(m):
                                                succeeded += 1
                                            else:
                                                failed += 1
                                    commit_batch.clear()
                            except (InsufficientBalanceError, PricingNotFoundError):
                                # 余额耗尽：记录中断位置，剩余未处理项稍后批量补 failed sms_logs
                                balance_exhausted_at = _idx
                                break
                            except Exception as e:
                                logger.warning(f"逐条回退失败: batch={batch_id}, {e}")
                                failed += 1
                                continue

                        # 提交剩余
                        if commit_batch:
                            await db.flush()
                            await db.commit()
                            _proto = str(ch.protocol).upper() if ch else ''
                            if is_virtual_channel:
                                succeeded += len(commit_batch)
                            elif 'SMPP' in _proto:
                                _mids = [m for m, _ in commit_batch]
                                from app.utils.smpp_payload import smpp_payload_public_dict

                                _rows = (
                                    await db.execute(select(SMSLog).where(SMSLog.message_id.in_(_mids)))
                                ).scalars().all()
                                _by = {r.message_id: r for r in _rows}
                                _pl = [
                                    smpp_payload_public_dict(_by[m], _batch_status_str)
                                    for m in _mids
                                    if m in _by
                                ]
                                if QueueManager.queue_sms_batch_smpp(_pl):
                                    succeeded += len(_pl)
                                else:
                                    for _p in _pl:
                                        if QueueManager.queue_smpp_gateway(_p):
                                            succeeded += 1
                                        else:
                                            failed += 1
                            else:
                                for m, c in commit_batch:
                                    if QueueManager.queue_sms(m):
                                        succeeded += 1
                                    else:
                                        failed += 1
                            commit_batch.clear()
                        # 余额耗尽后未处理项：批量写入 sms_logs(status='failed')，让 batch 进度能正确收口
                        # 历史 bug：仅累加 `failed += remaining`，sms_logs 不写入 → batch_utils.update_batch_progress
                        # 用 sms_logs 实际行数算 done，永远 done < total，批次卡 processing 不结束（参考 batch 352 事故）
                        if balance_exhausted_at is not None:
                            unprocessed = valid_items[balance_exhausted_at:]
                            if unprocessed:
                                now_fail = datetime.now()
                                fail_logs: List[SMSLog] = []
                                for phone_info, cc, final_msg, msg_count, _bi, ch in unprocessed:
                                    fail_logs.append(SMSLog(
                                        message_id=f"msg_{uuid.uuid4().hex}",
                                        account_id=account_id, channel_id=ch.id,
                                        phone_number=phone_info['e164_format'], country_code=cc,
                                        message=final_msg, message_count=msg_count,
                                        status='failed', cost_price=0, selling_price=0,
                                        currency='USD',
                                        submit_time=now_fail, batch_id=batch_id,
                                        error_message='Insufficient balance',
                                    ))
                                # 大批量分片写库，避免单事务过大
                                _fail_chunk = 5000
                                for _f0 in range(0, len(fail_logs), _fail_chunk):
                                    db.add_all(fail_logs[_f0:_f0 + _fail_chunk])
                                    await db.flush()
                                    await db.commit()
                                failed += len(fail_logs)
                                logger.warning(
                                    f"批次余额耗尽: batch={batch_id}, offset={start_offset}, "
                                    f"未处理 {len(fail_logs)} 条已批量写入 sms_logs(failed)"
                                )

            # 分片写库/入队完成后：按 sms_logs 真实状态汇总批次。
            # 禁止把「入队成功条数」累加到 success_count，否则会出现「批次 completed 且 success=总量但全是 queued」的假象（如批次 246/247）。
            from app.modules.sms.batch_utils import update_batch_progress

            _total_logs = (
                await db.execute(
                    select(func.count()).select_from(SMSLog).where(SMSLog.batch_id == batch_id)
                )
            ).scalar() or 0
            logger.info(
                f"分片收尾: batch={batch_id}, offset={start_offset}, "
                f"本片入队统计 succeeded={succeeded}, failed={failed}, 累计 sms_logs={_total_logs}"
            )
            await update_batch_progress(db, batch_id)

        if is_virtual_channel and virtual_message_ids and virtual_channel_id:
            from app.workers.celery_app import celery_app as _celery
            from app.modules.sms.channel import Channel as _Ch
            import random

            ch_tps = 50
            dlr_base_delay = 3
            try:
                eng2, fac2 = _make_fresh_session()
                async with fac2() as _db2:
                    _r = await _db2.execute(select(_Ch).where(_Ch.id == virtual_channel_id))
                    _ch = _r.scalar_one_or_none()
                    if _ch:
                        ch_tps = max(1, _ch.max_tps or 50)
                        cfg = _ch.get_virtual_config() if hasattr(_ch, 'get_virtual_config') else {}
                        dlr_base_delay = max(1, cfg.get("dlr_delay_min", 3))
                await eng2.dispose()
            except Exception:
                pass

            # 阶段1：模拟上游提交延迟 (pending → sent)，按 TPS 速率排队
            submit_delay = start_offset / max(ch_tps, 1)
            submit_jitter = random.uniform(0, min(3, 200 / max(ch_tps, 1)))
            _celery.send_task(
                "virtual_submit_simulate",
                args=[virtual_message_ids, virtual_channel_id, batch_id],
                countdown=submit_delay + submit_jitter,
                queue="sms_send",
            )

            # 阶段2：模拟回执延迟 (sent → delivered/failed)，在提交完成后再等待
            dlr_delay = submit_delay + submit_jitter + dlr_base_delay + random.uniform(1, 5)
            _celery.send_task(
                "virtual_dlr_batch_generate",
                args=[virtual_message_ids, virtual_channel_id, batch_id],
                countdown=dlr_delay,
                queue="sms_send",
            )
            logger.info(
                f"虚拟通道两阶段任务已创建: batch={batch_id}, offset={start_offset}, "
                f"count={len(virtual_message_ids)}, submit_delay={submit_delay + submit_jitter:.1f}s, "
                f"dlr_delay={dlr_delay:.1f}s (tps={ch_tps})"
            )

        logger.info(f"分片处理完成: batch={batch_id}, offset={start_offset}, succeeded={succeeded}, failed={failed}")
        return {"succeeded": succeeded, "failed": failed}

    except Exception as e:
        logger.exception(f"分片处理异常: batch={batch_id}, offset={start_offset}, {e}")
        # 扣费已 commit 但分片写库/入队未完成：独立新会话退款，避免用户为未入库记录付费
        if _charged_amount and _charged_amount > 0 and succeeded == 0:
            try:
                _eng2, _fac2 = _make_fresh_session()
                try:
                    async with _fac2() as _db2:
                        from sqlalchemy import update as _sa_upd
                        await _db2.execute(
                            _sa_upd(Account)
                            .where(Account.id == account_id)
                            .values(balance=Account.balance + _charged_amount)
                        )
                        _bal_r = await _db2.execute(select(Account.balance).where(Account.id == account_id))
                        _bal_after = _bal_r.scalar() or 0
                        _db2.add(BalanceLog(
                            account_id=account_id, change_type='refund',
                            amount=_charged_amount, balance_after=_bal_after,
                            description=f"Batch chunk failed refund: batch#{batch_id} offset={start_offset}",
                        ))
                        await _db2.commit()
                    logger.warning(
                        f"分片失败退款完成: batch={batch_id}, offset={start_offset}, refund={_charged_amount}"
                    )
                finally:
                    await _eng2.dispose()
            except Exception as _re:
                logger.error(
                    f"分片失败退款失败(需人工介入): batch={batch_id}, offset={start_offset}, "
                    f"charged={_charged_amount}, err={_re}"
                )
        raise
    finally:
        await eng.dispose()
