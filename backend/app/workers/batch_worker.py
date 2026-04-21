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
    )
    factory = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    return eng, factory


def _run_async(coro):
    """在 Celery 同步 worker 中安全地执行异步协程"""
    loop = asyncio.new_event_loop()
    try:
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
    return _run_async(_do_process_batch(batch_id))

async def _do_process_batch(batch_id: int):
    db = _get_worker_session()
    try:
        # 1. 获取批次记录
        result = await db.execute(select(SmsBatch).where(SmsBatch.id == batch_id))
        batch = result.scalar_one_or_none()
        if not batch:
            logger.error(f"批次记录不存在: {batch_id}")
            return
        
        if batch.status != BatchStatus.PENDING:
            logger.warning(f"批次状态不是 PENDING: {batch_id}, status={batch.status}")
            return

        # 2. 更新状态为处理中
        batch.status = BatchStatus.PROCESSING
        batch.started_at = datetime.now()
        await db.commit()

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
                                db, batch.account_id, channel, commit_batch,
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
            s, f = await _queue_commit_batch(db, batch.account_id, _channel, commit_batch)
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
    """入队失败退款"""
    if amount <= 0:
        return
    try:
        from app.modules.common.balance_log import BalanceLog
        await db.execute(
            update(Account).where(Account.id == account_id)
            .values(balance=Account.balance + amount)
        )
        bal = await db.execute(select(Account.balance).where(Account.id == account_id))
        db.add(BalanceLog(
            account_id=account_id, change_type='refund', amount=amount,
            balance_after=float(bal.scalar()),
            description=f"Batch queue fail refund: {message_id}"
        ))
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


async def _queue_commit_batch(db, account_id: int, channel, commit_batch: list) -> tuple[int, int]:
    """
    将 commit_batch 中的消息批量入队，返回 (success_count, failed_count)。
    """
    success = 0
    failed = 0
    _proto = str(channel.protocol).upper() if channel else "HTTP"

    if 'SMPP' in _proto:
        smpp_mids = [mid for mid, _ in commit_batch]
        from app.config import settings as _cfg
        _win = int(getattr(_cfg, 'SMPP_WINDOW_SIZE', 10) or 10)
        for _i in range(0, len(smpp_mids), _win):
            _chunk = smpp_mids[_i:_i + _win]
            if QueueManager.queue_sms_batch_smpp(_chunk):
                success += len(_chunk)
            else:
                for _m in _chunk:
                    if QueueManager.queue_smpp_gateway(_m):
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
    """处理一个分片（最多 500 条号码）：校验 → 计费 → 写库 → 入队"""
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
    from app.utils.sms_template import render_sms_variables, sms_template_has_variables
    from app.modules.sms.channel import Channel

    eng, factory = _make_fresh_session()
    succeeded = 0
    failed = 0
    use_rotate = len(rot_messages) > 0

    try:
        async with factory() as db:
            from app.utils.account_country_restrict import assert_sms_destination_allowed, AccountCountryNotAllowedError

            # 批次状态检查：已取消或已失败的批次直接跳过
            _batch_chk = await db.execute(
                select(SmsBatch.status).where(SmsBatch.id == batch_id)
            )
            _batch_status = _batch_chk.scalar_one_or_none()
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
                        dr = await db.execute(
                            sa_update(Account)
                            .where(Account.id == account_id, Account.balance >= total_sell)
                            .values(balance=Account.balance - total_sell)
                        )
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

                    # 4. 批量创建 SMSLog
                    if deduct_ok:
                        now = datetime.now()
                        for phone_info, cc, final_msg, msg_count, batch_index in valid_items:
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
                            db.add(sms_log)
                            virtual_message_ids.append(mid)
                            succeeded += 1
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
                        dr = await db.execute(
                            sa_update(Account)
                            .where(Account.id == account_id, Account.balance >= total_sell)
                            .values(balance=Account.balance - total_sell)
                        )
                        if dr.rowcount == 0:
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
                            cache_manager = await get_cache_manager()
                            await cache_manager.set(f"account:{account_id}:balance", float(bal_after), ttl=60)

                    _t2 = time.time()
                    logger.info(f"批量扣费完成: batch={batch_id}, total_sell={total_sell}, "
                                f"deduct_ok={deduct_ok}, 耗时={_t2 - _t1:.2f}s")

                    if deduct_ok:
                        # 阶段3: 批量创建 SMSLog + 单次 commit
                        now = datetime.now()
                        all_mids = []
                        smpp_mids = []
                        http_mids = []
                        _batch_channel = None

                        for phone_info, cc, final_msg, msg_count, batch_index, ch in valid_items:
                            sell_pp, currency, cost_pp = price_cache[(ch.id, cc)]
                            mid = f"msg_{uuid.uuid4().hex}"
                            _batch_channel = ch

                            if ch.protocol == 'VIRTUAL':
                                is_virtual_channel = True
                                virtual_channel_id = ch.id
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
                            db.add(sms_log)
                            all_mids.append(mid)

                            # 按协议分类
                            _proto = str(ch.protocol).upper()
                            if 'SMPP' in _proto:
                                smpp_mids.append(mid)
                            elif ch.protocol != 'VIRTUAL':
                                http_mids.append(mid)

                        await db.flush()
                        await db.commit()

                        _t3 = time.time()
                        logger.info(f"批量写库完成: batch={batch_id}, count={len(all_mids)}, 耗时={_t3 - _t2:.2f}s")

                        # 阶段4: 批量入队
                        if is_virtual_channel:
                            succeeded += len(virtual_message_ids)
                        if smpp_mids:
                            if QueueManager.queue_sms_batch_smpp(smpp_mids):
                                succeeded += len(smpp_mids)
                            else:
                                # 回退单条
                                for _m in smpp_mids:
                                    if QueueManager.queue_smpp_gateway(_m):
                                        succeeded += 1
                                    else:
                                        failed += 1
                        if http_mids:
                            for _m in http_mids:
                                if QueueManager.queue_sms(_m):
                                    succeeded += 1
                                else:
                                    failed += 1

                        _t4 = time.time()
                        logger.info(f"批量入队完成: batch={batch_id}, smpp={len(smpp_mids)}, "
                                    f"http={len(http_mids)}, virtual={len(virtual_message_ids)}, "
                                    f"耗时={_t4 - _t3:.2f}s, 总耗时={_t4 - _t0:.2f}s")
                    else:
                        # 余额不足时逐条回退：尽可能扣到余额耗尽
                        for phone_info, cc, final_msg, msg_count, batch_index, ch in valid_items:
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
                                        if QueueManager.queue_sms_batch_smpp(_mids):
                                            succeeded += len(_mids)
                                        else:
                                            for _m in _mids:
                                                if QueueManager.queue_smpp_gateway(_m):
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
                                failed += 1
                                break  # 余额耗尽，终止
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
                                if QueueManager.queue_sms_batch_smpp(_mids):
                                    succeeded += len(_mids)
                                else:
                                    for _m in _mids:
                                        if QueueManager.queue_smpp_gateway(_m):
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
                        # 剩余未处理的标记为失败
                        remaining_failed = len(valid_items) - succeeded - failed
                        if remaining_failed > 0:
                            failed += remaining_failed

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
        raise
    finally:
        await eng.dispose()
