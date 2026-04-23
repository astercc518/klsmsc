"""
数据业务定时任务 Worker
"""
import os
from datetime import datetime, timedelta, date
from decimal import Decimal
from typing import Optional
from sqlalchemy import select, func, or_, update as sa_update, insert
from sqlalchemy.exc import OperationalError
from app.workers.celery_app import celery_app
import app.models  # noqa: F401 确保所有 ORM 关系模型被加载
from app.modules.data.models import (
    DataNumber,
    DataProduct,
    DataOrder,
    DataOrderNumber,
    DataImportBatch,
    DataPricingTemplate,
    PrivateLibraryUploadTask,
    DATA_SOURCES,
    DATA_PURPOSES,
    SOURCE_LABELS,
    PURPOSE_LABELS,
)
from app.utils.logger import get_logger
from app.api.v1.data.helpers import calculate_stock, compute_freshness
from app.modules.data.stock_summary_sync import update_stock_summary_from_batch
import asyncio
import csv
import io
import re
import json
import time
import phonenumbers
import redis

logger = get_logger(__name__)

HEADER_KEYWORDS = re.compile(
    r'(?i)^(phone|mobile|number|tel|手机|号码|电话|编号|序号|#|id|index)',
)
NON_DIGIT_RE = re.compile(r'[^\d+]')


def _clean_phone(raw: str) -> Optional[str]:
    """清洗原始字符串，返回可供 phonenumbers 解析的字符串（保留原始格式）"""
    s = raw.strip().strip('\ufeff').strip('\u200b').strip('"').strip("'")
    if not s:
        return None
    if HEADER_KEYWORDS.match(s):
        return None
    s = NON_DIGIT_RE.sub('', s)
    if not s:
        return None
    digits = s.lstrip('+')
    if len(digits) < 7 or len(digits) > 20:
        return None
    return s


def _parse_phone(cleaned: str, region: Optional[str] = None):
    """解析号码，返回 (e164, country_code) 或 None"""
    attempts = []
    if cleaned.startswith('+'):
        attempts.append(cleaned)
    elif cleaned.startswith('00'):
        attempts.append('+' + cleaned[2:])
    else:
        if region:
            attempts.append(cleaned)
        attempts.append('+' + cleaned)

    for attempt in attempts:
        try:
            pn = phonenumbers.parse(attempt, region)
            if phonenumbers.is_valid_number(pn):
                e164 = phonenumbers.format_number(pn, phonenumbers.PhoneNumberFormat.E164)
                cc = phonenumbers.region_code_for_number(pn)
                try:
                    from phonenumbers import carrier as _carrier_mod
                    carrier_name = _carrier_mod.name_for_number(pn, "en") or None
                except Exception:
                    carrier_name = None
                return e164, cc, carrier_name
        except Exception:
            continue
    return None


def _get_redis():
    """获取同步 Redis 客户端（用于进度更新）"""
    from app.config import settings
    return redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=0, decode_responses=True)


def _update_progress(redis_client, batch_id: str, data: dict):
    """更新 Redis 中的导入进度"""
    key = f"import_progress:{batch_id}"
    redis_client.setex(key, 3600, json.dumps(data, ensure_ascii=False))


def _run_async(coro):
    """在 Celery 同步 worker 中安全地执行异步协程，始终使用全新事件循环"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


def _make_session():
    """为 Worker 任务创建独立的数据库引擎和会话（避免跨事件循环复用连接池）"""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from app.config import settings

    from sqlalchemy.pool import NullPool
    eng = create_async_engine(
        settings.SQLALCHEMY_DATABASE_URL, echo=False,
        poolclass=NullPool,
        pool_pre_ping=True, pool_recycle=600,
    )
    factory = async_sessionmaker(eng, class_=AsyncSession,
                                 expire_on_commit=False, autocommit=False, autoflush=False)
    return eng, factory


def _is_mysql_deadlock(exc: BaseException) -> bool:
    """判断是否为 InnoDB 死锁(1213)，可重试。"""
    orig = getattr(exc, "orig", None)
    if orig is not None:
        args = getattr(orig, "args", ()) or ()
        if args and args[0] == 1213:
            return True
    if exc.args and exc.args[0] == 1213:
        return True
    s = str(exc)
    return "1213" in s or "Deadlock" in s or "deadlock" in s


async def _finalize_buy_send_failure_state(order_id: int, batch_id: int, reason: str):
    """
    使用独立会话写入订单/批次终态，避免原事务报错后会话无法提交。
    订单使用 cancelled（与 data_orders.status 枚举一致）；批次标为 failed。
    """
    from app.modules.sms.sms_batch import SmsBatch, BatchStatus

    safe = (reason or "unknown")[:800]
    hint = f"购数并发送失败（未产生或未完全产生发送记录）：{safe}"
    eng, Session = _make_session()
    try:
        async with Session() as db:
            await db.execute(
                sa_update(DataOrder)
                .where(DataOrder.id == order_id)
                .values(
                    status="cancelled",
                    cancel_reason=hint[:2000],
                    updated_at=datetime.now(),
                )
            )
            await db.execute(
                sa_update(SmsBatch)
                .where(SmsBatch.id == batch_id)
                .values(
                    status=BatchStatus.FAILED,
                    error_message=hint[:2000],
                    progress=0,
                    processing_count=0,
                    success_count=0,
                    failed_count=0,
                    completed_at=datetime.now(),
                    updated_at=datetime.now(),
                )
            )
            await db.commit()
    except Exception as e:
        logger.error(
            f"[buy-send-async] 独立会话写失败状态仍异常 order={order_id} batch={batch_id}: {e}",
            exc_info=True,
        )
        try:
            await db.rollback()
        except Exception:
            pass
    finally:
        await eng.dispose()

async def _do_buy_send_async_once(db, order_id, batch_id, account_id, number_ids, message, messages, sender_id):
    """
    购数并发送单次事务：按 5000 条分片从关联表或 legacy 列表取号，Core 批量 insert sms_logs，
    避免 ORM 膨胀；提交后按 id 分页组负载入队，控制峰值内存。
    number_ids 为 None 时仅从 data_order_numbers 键集分页反查（瘦消息）。
    """
    from collections import Counter, defaultdict
    from sqlalchemy import text as sa_text

    from app.core.router import RoutingEngine
    from app.core.pricing import PricingEngine
    from app.modules.sms.sms_log import SMSLog
    from app.modules.sms.sms_batch import SmsBatch, BatchStatus
    from app.modules.sms.channel import Channel
    from app.modules.common.account import AccountChannel
    from app.utils.queue import QueueManager
    from app.utils.phone_utils import country_to_dial_code
    from app.utils.sms_template import render_sms_variables, sms_template_has_variables
    from app.utils.smpp_payload import smpp_payload_public_dict_from_row
    from app.api.v1.data.customer import (
        ORIGIN_PURCHASED,
        norm_dim,
        pls_apply_deltas_bulk,
        pls_prune_non_positive,
    )
    import uuid as _uuid

    CHUNK = 5000
    IN_READ = 3000

    from app.modules.sms.batch_utils import publish_batch_pipeline_progress

    msg_list = messages if messages and len(messages) > 1 else [message]
    msg_count = len(msg_list)
    msg_has_vars = [sms_template_has_variables(m) for m in msg_list]

    stream_from_order = number_ids is None
    legacy_ptr = 0
    last_don_id = 0

    dn_t = DataOrderNumber.__table__
    num_t = DataNumber.__table__
    log_t = SMSLog.__table__

    routing_engine = RoutingEngine(db)
    pricing_engine = PricingEngine(db)

    ac_result = await db.execute(
        select(AccountChannel.channel_id).where(AccountChannel.account_id == account_id)
    )
    bound_ids = [r[0] for r in ac_result.all()]

    country_channel_cache = {}
    country_price_cache = {}

    async def _get_channel_for_country(cc_country):
        if cc_country in country_channel_cache:
            return country_channel_cache[cc_country]
        dial_code = country_to_dial_code(cc_country)
        channel = None
        for cc in [dial_code, cc_country]:
            try:
                ch = await routing_engine.select_channel(
                    country_code=cc, strategy="priority", account_id=account_id
                )
                if ch:
                    if ch.protocol in ("VIRTUAL", "HTTP", "SMPP"):
                        channel = ch
                        break
            except Exception:
                continue
        if not channel and bound_ids:
            ch_result = await db.execute(
                select(Channel).where(
                    Channel.id.in_(bound_ids),
                    Channel.status == "active",
                    Channel.is_deleted == False,
                ).order_by(Channel.priority.desc()).limit(1)
            )
            channel = ch_result.scalar_one_or_none()
        country_channel_cache[cc_country] = channel
        return channel

    async def _get_price_for(channel, cc_country):
        cache_key = (channel.id, cc_country)
        if cache_key in country_price_cache:
            return country_price_cache[cache_key]
        dial_code = country_to_dial_code(cc_country)
        price_info = await pricing_engine.get_price(channel.id, dial_code, account_id=account_id)
        if not price_info:
            price_info = await pricing_engine.get_price(channel.id, cc_country, account_id=account_id)
        base_cost = await pricing_engine.resolve_base_cost_per_sms(channel.id, cc_country, channel)
        sell_per = float(price_info["price"]) if price_info else 0.0
        cost_per = float(base_cost)
        curr = price_info["currency"] if price_info else "USD"
        country_price_cache[cache_key] = (sell_per, cost_per, curr)
        return sell_per, cost_per, curr

    global_idx = 0
    channels_used = set()
    channel_ids_used = set()
    n_inserted_total = 0

    # 预期总条数（进度分母）：订单 quantity → legacy 列表长 → 关联表 COUNT
    oq = await db.scalar(select(DataOrder.quantity).where(DataOrder.id == order_id))
    total_expected = int(oq or 0)
    if total_expected <= 0 and not stream_from_order and number_ids:
        total_expected = len(number_ids)
    if total_expected <= 0 and stream_from_order:
        total_expected = int(
            await db.scalar(
                select(func.count()).select_from(dn_t).where(dn_t.c.order_id == order_id)
            )
            or 0
        )

    chunk_no = 0
    while True:
        if stream_from_order:
            don_res = await db.execute(
                select(dn_t.c.id, dn_t.c.number_id)
                .where(dn_t.c.order_id == order_id, dn_t.c.id > last_don_id)
                .order_by(dn_t.c.id)
                .limit(CHUNK)
            )
            don_rows = don_res.all()
            if not don_rows:
                break
            last_don_id = don_rows[-1][0]
            chunk_ids = [r[1] for r in don_rows]
        else:
            if legacy_ptr >= len(number_ids):
                break
            chunk_ids = number_ids[legacy_ptr : legacy_ptr + CHUNK]
            legacy_ptr += len(chunk_ids)
            if not chunk_ids:
                break

        chunk_no += 1
        id_to_row = {}
        for _off in range(0, len(chunk_ids), IN_READ):
            sub = chunk_ids[_off : _off + IN_READ]
            nr = await db.execute(select(num_t).where(num_t.c.id.in_(sub)))
            for rowmap in nr.mappings().all():
                id_to_row[rowmap["id"]] = rowmap
        ordered_nums = [id_to_row[i] for i in chunk_ids if i in id_to_row]

        if not ordered_nums:
            logger.warning(
                f"[buy-send-async] order={order_id} chunk#{chunk_no} 无有效 data_numbers 行，跳过"
            )
            continue

        by_country = defaultdict(list)
        for row in ordered_nums:
            cc = row.get("country_code") or "PH"
            by_country[cc].append(row)

        insert_rows = []
        inserted_number_id_for_use_count = []
        now_ts = datetime.now()

        for cc_country, cc_rows in by_country.items():
            channel = await _get_channel_for_country(cc_country)
            if not channel:
                logger.warning(
                    f"[buy-send-async] 国家 {cc_country} 无可用通道，跳过本 chunk 内 {len(cc_rows)} 条"
                )
                continue
            channels_used.add(channel.channel_code)
            channel_ids_used.add(int(channel.id))
            sell_per, cost_per, curr = await _get_price_for(channel, cc_country)

            for row in cc_rows:
                global_idx += 1
                template = msg_list[(global_idx - 1) % msg_count]
                msg = (
                    render_sms_variables(
                        template,
                        index=global_idx,
                        phone_e164=row.get("phone_number") or "",
                        country_code=row.get("country_code") or "",
                    )
                    if msg_has_vars[(global_idx - 1) % msg_count]
                    else template
                )
                parts = pricing_engine._count_sms_parts(msg)
                sell = sell_per * parts
                cost = cost_per * parts
                mid = f"msg_{_uuid.uuid4().hex}"
                insert_rows.append(
                    {
                        "message_id": mid,
                        "account_id": account_id,
                        "channel_id": int(channel.id),
                        "batch_id": batch_id,
                        "phone_number": row["phone_number"],
                        "country_code": row.get("country_code"),
                        "message": msg,
                        "message_count": int(parts),
                        "status": "pending",
                        "cost_price": Decimal(str(cost)),
                        "selling_price": Decimal(str(sell)),
                        "currency": curr,
                        "submit_time": now_ts,
                    }
                )
                inserted_number_id_for_use_count.append(row["id"])

        now_pls = datetime.now()
        pls_chunk = [
            (
                ORIGIN_PURCHASED,
                norm_dim(row.get("country_code")),
                norm_dim(row.get("source")),
                norm_dim(row.get("purpose")),
                norm_dim(row.get("batch_id")),
                norm_dim(row.get("carrier")),
                1,
                1,
                row.get("remarks"),
                row.get("created_at"),
                now_pls,
            )
            for row in ordered_nums
        ]
        try:
            if pls_chunk:
                await pls_apply_deltas_bulk(db, account_id, pls_chunk)
        except Exception as e:
            logger.warning(
                f"[buy-send-async] PLS 分片 chunk#{chunk_no} 失败（非致命）: {e}"
            )

        if insert_rows:
            await db.execute(insert(log_t), insert_rows)
            await db.flush()

            counter = Counter(inserted_number_id_for_use_count)
            if counter:
                items = list(counter.items())
                for i in range(0, len(items), 400):
                    part = dict(items[i : i + 400])
                    when_sql = " ".join(f"WHEN {int(k)} THEN {int(v)}" for k, v in part.items())
                    ids_sql = ",".join(str(int(k)) for k in part.keys())
                    await db.execute(
                        sa_text(
                            "UPDATE data_numbers SET use_count = IFNULL(use_count, 0) + "
                            f"CASE id {when_sql} ELSE 0 END WHERE id IN ({ids_sql})"
                        )
                    )

            n_inserted_total += len(insert_rows)
            logger.info(
                f"[buy-send-async] order={order_id} Core 写入 chunk#{chunk_no} "
                f"{len(insert_rows)} 条 sms_logs（累计 {n_inserted_total}）"
            )
            # 独立会话刷进度，避免主事务未提交时前端长时间 0%
            if total_expected > 0:
                await publish_batch_pipeline_progress(
                    batch_id,
                    total=total_expected,
                    inserted=n_inserted_total,
                    queued=0,
                )

        insert_rows.clear()
        inserted_number_id_for_use_count.clear()

    try:
        await pls_prune_non_positive(db, account_id)
    except Exception as e:
        logger.warning(f"[buy-send-async] PLS prune 失败（非致命）: {e}")

    batch_result = await db.execute(select(SmsBatch).where(SmsBatch.id == batch_id))
    sms_batch = batch_result.scalar_one_or_none()
    if sms_batch:
        sms_batch.total_count = n_inserted_total
        sms_batch.status = BatchStatus.PROCESSING

    await db.commit()
    logger.info(
        f"[buy-send-async] order={order_id}, Core 分片完成，共创建 {n_inserted_total} 条 SMS 记录"
    )

    bs_val = ""
    if batch_id:
        _bs_row = await db.execute(select(SmsBatch.status).where(SmsBatch.id == batch_id))
        _bs_raw = _bs_row.scalar_one_or_none()
        bs_val = getattr(_bs_raw, "value", str(_bs_raw or ""))

    prot_map = {}
    for _cid in channel_ids_used:
        _pr = await db.execute(select(Channel.protocol).where(Channel.id == _cid))
        prot_map[_cid] = _pr.scalar_one_or_none()

    # MQ 投递批大小：与 SMPP 网关会话窗口（SMPP_WINDOW_SIZE）解耦，减少 Rabbit 往返次数
    MQ_BATCH_SIZE = 2000
    queued = 0
    last_log_id = 0
    while True:
        qrows = await db.execute(
            select(
                log_t.c.id,
                log_t.c.message_id,
                log_t.c.phone_number,
                log_t.c.message,
                log_t.c.channel_id,
                log_t.c.status,
            )
            .where(log_t.c.batch_id == batch_id, log_t.c.id > last_log_id)
            .order_by(log_t.c.id)
            .limit(CHUNK)
        )
        maps = qrows.mappings().all()
        if not maps:
            break
        last_log_id = maps[-1]["id"]

        smpp_payloads = []
        other_mids = []
        for rm in maps:
            _prot_raw = prot_map.get(rm["channel_id"])
            _pv = getattr(_prot_raw, "value", _prot_raw)
            _pv = getattr(_pv, "value", _pv)
            st = getattr(rm["status"], "value", rm["status"]) or ""
            if "SMPP" in str(_pv or "").upper():
                smpp_payloads.append(
                    smpp_payload_public_dict_from_row(
                        int(rm["id"]),
                        rm["message_id"],
                        rm["phone_number"] or "",
                        rm["message"] or "",
                        int(rm["channel_id"] or 0),
                        str(st),
                        bs_val,
                    )
                )
            else:
                other_mids.append(rm["message_id"])

        # 每 chunk 调用一次 queue_sms_batch_smpp：内部为「整包单次 publish」，不再按条 apply_async
        for _i in range(0, len(smpp_payloads), MQ_BATCH_SIZE):
            chunk = smpp_payloads[_i : _i + MQ_BATCH_SIZE]
            if QueueManager.queue_sms_batch_smpp(chunk):
                queued += len(chunk)
            else:
                for _p in chunk:
                    if QueueManager.queue_smpp_gateway(_p):
                        queued += 1
        for mid in other_mids:
            if QueueManager.queue_sms(mid):
                queued += 1

        smpp_payloads.clear()
        other_mids.clear()

        if total_expected > 0:
            await publish_batch_pipeline_progress(
                batch_id,
                total=total_expected,
                inserted=n_inserted_total,
                queued=queued,
            )

    n_msgs = n_inserted_total
    logger.info(f"[buy-send-async] order={order_id}, 入队 {queued}/{n_msgs}")

    order_result = await db.execute(select(DataOrder).where(DataOrder.id == order_id))
    order = order_result.scalar_one_or_none()
    if order and n_msgs > 0:
        order.executed_count = n_msgs
        order.executed_at = datetime.now()
        if queued == 0:
            order.status = "cancelled"
            prev = (order.cancel_reason or "").strip()
            hint = "购数并发送：全部短信入队失败，请检查 RabbitMQ 与 worker-sms"
            order.cancel_reason = f"{prev} | {hint}" if prev else hint
        elif queued < n_msgs:
            order.status = "processing"
            prev = (order.cancel_reason or "").strip()
            hint = f"购数并发送：部分入队失败 {queued}/{n_msgs}，请检查 Broker 或对未入队记录重投"
            order.cancel_reason = f"{prev} | {hint}" if prev else hint
        else:
            order.status = "completed"
            order.cancel_reason = None

    if n_inserted_total > 0 and len(channel_ids_used) == 1:
        _only_cid = next(iter(channel_ids_used))
        _prot_row = await db.execute(select(Channel.protocol).where(Channel.id == _only_cid))
        _prot = _prot_row.scalar_one_or_none()
        _prot_raw = getattr(_prot, "value", _prot)
        _prot_raw = getattr(_prot_raw, "value", _prot_raw)
        if str(_prot_raw or "").upper() == "VIRTUAL":
            from app.workers.sms_worker import virtual_dlr_batch_generate_task as _vbatch_task

            _mid_res = await db.execute(
                select(log_t.c.message_id).where(
                    log_t.c.batch_id == batch_id,
                    log_t.c.channel_id == _only_cid,
                )
            )
            all_mids = [r[0] for r in _mid_res.all()]
            _chunk_size = 500
            _nchunks = (len(all_mids) + _chunk_size - 1) // _chunk_size
            for _bi, _start in enumerate(range(0, len(all_mids), _chunk_size)):
                _chunk = all_mids[_start : _start + _chunk_size]
                _vbatch_task.apply_async(
                    args=[_chunk, _only_cid, batch_id],
                    countdown=min(600, 3 + _bi * 2),
                    queue="sms_send",
                )
            logger.info(
                f"[buy-send-async] 虚拟通道已补调度 virtual_dlr_batch_generate: "
                f"batch={batch_id}, channel_id={_only_cid}, chunks={_nchunks}"
            )

    from app.modules.sms.batch_utils import update_batch_progress

    await update_batch_progress(db, batch_id)
    # update_batch_progress 在「全 pending」时 progress 按已终态条数算会为 0；入队刚结束需保持「提交阶段」进度观感
    if n_inserted_total > 0:
        await publish_batch_pipeline_progress(
            batch_id,
            total=n_inserted_total,
            inserted=n_inserted_total,
            queued=queued,
        )
    batch_result2 = await db.execute(select(SmsBatch).where(SmsBatch.id == batch_id))
    sms_batch2 = batch_result2.scalar_one_or_none()
    if sms_batch2:
        if n_msgs == 0:
            sms_batch2.status = BatchStatus.FAILED
            sms_batch2.error_message = "无有效短信记录"
            sms_batch2.progress = 0
        elif queued == 0:
            sms_batch2.status = BatchStatus.FAILED
            sms_batch2.error_message = (
                "全部短信入队失败：请检查 RabbitMQ、worker-sms 及 Broker 连通性"
            )
            sms_batch2.progress = 0
        elif queued < n_msgs:
            sms_batch2.status = BatchStatus.PROCESSING
            sms_batch2.error_message = (
                f"部分入队失败：{queued}/{n_msgs}，请检查 Broker 或使用运维脚本对 pending 记录重投"
            )
            sms_batch2.progress = min(99, int(100 * queued / n_msgs)) if n_msgs else 0
        else:
            sms_batch2.status = BatchStatus.PROCESSING
            sms_batch2.completed_at = None
            sms_batch2.error_message = None
        logger.info(
            f"[buy-send-async] batch={batch_id} 状态={sms_batch2.status}; "
            f"入队 {queued}/{n_msgs}; success_count={sms_batch2.success_count}, "
            f"failed_count={sms_batch2.failed_count}"
        )
    await db.commit()

    return {"order_id": order_id, "total": n_inserted_total, "queued": queued}


async def _do_buy_send_async(order_id, batch_id, account_id, number_ids,
                              message, messages, sender_id):
    """购数并发送：含 InnoDB 死锁重试与失败落库。"""
    # None：仅走 data_order_numbers；列表：legacy Celery 大包（若关联表有数据则强制忽略）
    legacy = None if number_ids is None else list(number_ids)

    eng_probe, Session_probe = _make_session()
    try:
        async with Session_probe() as db_probe:
            assoc_n = await db_probe.scalar(
                select(func.count())
                .select_from(DataOrderNumber)
                .where(DataOrderNumber.order_id == order_id)
            ) or 0
    finally:
        await eng_probe.dispose()

    if assoc_n > 0:
        legacy = None
    elif not legacy:
        logger.error(
            f"[buy-send-async] order={order_id} 无号码：data_order_numbers 为空且未传入 number_ids"
        )
        await _finalize_buy_send_failure_state(
            order_id,
            batch_id,
            "购数并发送：订单无关联号码（data_order_numbers 为空），请检查 API 是否写入关联表",
        )
        return {"order_id": order_id, "total": 0, "queued": 0}

    _deadlock_attempts = 5
    for _attempt in range(_deadlock_attempts):
        eng, Session = _make_session()
        try:
            async with Session() as db:
                try:
                    return await _do_buy_send_async_once(
                        db, order_id, batch_id, account_id, legacy, message, messages, sender_id,
                    )
                except OperationalError as e:
                    if _is_mysql_deadlock(e) and _attempt < _deadlock_attempts - 1:
                        await db.rollback()
                        logger.warning(
                            f"[buy-send-async] order={order_id} MySQL死锁(1213)，"
                            f"第 {_attempt + 1}/{_deadlock_attempts} 次失败后重试: {e}"
                        )
                        await asyncio.sleep(0.06 * (2 ** _attempt))
                        continue
                    logger.error(f"[buy-send-async] order={order_id} 异常: {e}", exc_info=True)
                    await _finalize_buy_send_failure_state(
                        order_id,
                        batch_id,
                        f"MySQL死锁或数据库错误(重试已用尽): {e!s}"[:500],
                    )
                    raise
                except Exception as e:
                    logger.error(f"[buy-send-async] order={order_id} 异常: {e}", exc_info=True)
                    await _finalize_buy_send_failure_state(order_id, batch_id, str(e)[:500])
                    raise
        finally:
            await eng.dispose()


@celery_app.task(name='data_refresh_all_product_stock')
def data_refresh_all_product_stock():
    """每小时刷新所有活跃商品库存"""
    return _run_async(_refresh_all_stock())


async def _refresh_all_stock():
    eng, Session = _make_session()
    async with Session() as db:
        result = await db.execute(
            select(DataProduct).where(
                DataProduct.is_deleted == False,
                DataProduct.status == 'active',
            )
        )
        products = result.scalars().all()

        updated = 0
        auto_deactivated = 0
        for product in products:
            try:
                new_stock = await calculate_stock(db, product.filter_criteria, public_only=True)
                if product.stock_count != new_stock:
                    product.stock_count = new_stock
                    updated += 1

                # 自动下架：时效类商品库存持续为 0
                if new_stock == 0 and product.filter_criteria and product.filter_criteria.get('freshness'):
                    fc_no_fresh = {k: v for k, v in product.filter_criteria.items() if k != 'freshness'}
                    total_no_fresh = await calculate_stock(db, fc_no_fresh, public_only=True)
                    if total_no_fresh > 0:
                        # 数据存在但已过期 → 自动下架并记录原因
                        product.status = 'inactive'
                        product.stock_count = 0
                        logger.warning(
                            f"商品 {product.id}({product.product_name}) 时效过期自动下架: "
                            f"freshness={product.filter_criteria.get('freshness')}, "
                            f"过期数据={total_no_fresh}条"
                        )
                        auto_deactivated += 1
            except Exception as e:
                logger.error(f"刷新商品 {product.id} 库存失败: {e}")

        await db.commit()
        logger.info(f"库存刷新完成: 共 {len(products)} 个商品, 更新 {updated} 个, 过期下架 {auto_deactivated} 个")
    await eng.dispose()
    return {"total": len(products), "updated": updated, "auto_deactivated": auto_deactivated}


# ============ 大批量 buy-and-send 异步处理 ============

@celery_app.task(name='data_buy_send_async', bind=True, soft_time_limit=600, time_limit=660)
def data_buy_send_async(
    self,
    order_id: int,
    batch_id: int,
    account_id: int,
    message: str,
    messages: list = None,
    sender_id: str = None,
    number_ids: list = None,
):
    """异步处理大批量数据购买+发送：路由、定价、创建 SMS 记录、入队。

    number_ids 可选；缺省时由 data_order_numbers 按 order_id 反查（与 buy_and_send 瘦消息体对齐）。
    """
    return _run_async(
        _do_buy_send_async(
            order_id,
            batch_id,
            account_id,
            number_ids,
            message,
            messages,
            sender_id,
        )
    )


@celery_app.task(name='data_backfill_carriers', bind=True, soft_time_limit=7200, time_limit=7500)
def data_backfill_carriers(self, batch_size: int = 5000, limit: int = 0):
    """回填存量号码的运营商信息"""
    return _run_async(_backfill_carriers(batch_size, limit))


async def _backfill_carriers(batch_size: int = 5000, limit: int = 0):
    from phonenumbers import carrier as _carrier_mod
    from sqlalchemy import text as sa_text

    eng, Session = _make_session()
    async with Session() as db:
        count_result = await db.execute(
            sa_text("SELECT COUNT(*) FROM data_numbers WHERE (carrier IS NULL OR carrier = '') AND status = 'active'")
        )
        total_todo = count_result.scalar() or 0
        if limit > 0:
            total_todo = min(total_todo, limit)
        logger.info(f"[回填运营商] 待处理: {total_todo} 条")

        processed = 0
        updated = 0
        last_id = 0
        while True:
            result = await db.execute(
                sa_text(
                    "SELECT id, phone_number FROM data_numbers "
                    "WHERE id > :last_id AND (carrier IS NULL OR carrier = '') AND status = 'active' "
                    "ORDER BY id ASC LIMIT :batch"
                ).bindparams(last_id=last_id, batch=batch_size)
            )
            rows = result.fetchall()
            if not rows:
                break

            last_id = rows[-1][0]
            resolved = []
            unresolved_ids = []
            for row in rows:
                try:
                    pn = phonenumbers.parse(row[1])
                    carrier_name = _carrier_mod.name_for_number(pn, "en") or None
                    if carrier_name:
                        resolved.append((row[0], carrier_name.replace("'", "''")))
                    else:
                        unresolved_ids.append(str(row[0]))
                except Exception:
                    unresolved_ids.append(str(row[0]))

            # P0-FIX: 参数化更新，防止 SQL 注入
            if resolved:
                for uid, cn in resolved:
                    await db.execute(
                        sa_text("UPDATE data_numbers SET carrier = :carrier WHERE id = :uid"),
                        {"carrier": cn, "uid": uid}
                    )
                updated += len(resolved)

            if unresolved_ids:
                u_ids = [int(x) for x in unresolved_ids]
                for uid in u_ids:
                    await db.execute(
                        sa_text("UPDATE data_numbers SET carrier = 'Unknown' WHERE id = :uid"),
                        {"uid": uid}
                    )

            await db.commit()
            processed += len(rows)
            if limit > 0 and processed >= limit:
                break
            if processed % 50000 == 0:
                logger.info(f"[回填运营商] 进度: {processed}/{total_todo}, 已更新: {updated}")

        logger.info(f"[回填运营商] 完成: 处理 {processed}, 更新 {updated}")
    await eng.dispose()
    return {"processed": processed, "updated": updated}


@celery_app.task(name='data_recycle_expired_numbers')
def data_recycle_expired_numbers():
    """每天凌晨回收过期私库号码回公海（默认 90 天未使用）"""
    return _run_async(_recycle_expired(days=90))


async def _recycle_expired(days: int = 90):
    cutoff = datetime.now() - timedelta(days=days)
    eng, Session = _make_session()
    async with Session() as db:
        result = await db.execute(
            select(DataNumber).where(
                DataNumber.account_id.isnot(None),
                or_(
                    DataNumber.last_used_at.is_(None),
                    DataNumber.last_used_at < cutoff,
                ),
            )
        )
        numbers = result.scalars().all()

        recycled = 0
        for num in numbers:
            num.account_id = None
            recycled += 1

        await db.commit()
        logger.info(f"号码回收完成: 释放 {recycled} 个号码回公海 (超过 {days} 天未使用)")
    await eng.dispose()
    return {"recycled": recycled, "cutoff_days": days}


@celery_app.task(name='data_expire_pending_orders')
def data_expire_pending_orders():
    """每 30 分钟清理过期的 pending 订单"""
    return _run_async(_expire_orders())


async def _expire_orders():
    now = datetime.now()
    eng, Session = _make_session()
    async with Session() as db:
        result = await db.execute(
            select(DataOrder).where(
                DataOrder.status == 'pending',
                DataOrder.expires_at.isnot(None),
                DataOrder.expires_at < now,
            )
        )
        orders = result.scalars().all()

        expired = 0
        for order in orders:
            order.status = 'expired'
            order.cancel_reason = '订单超时未支付，系统自动过期'
            expired += 1

        await db.commit()
        logger.info(f"过期订单清理完成: {expired} 个订单已标记为过期")
    await eng.dispose()
    return {"expired": expired}


# ============ 号码导入异步任务 ============

@celery_app.task(
    name='data_import_numbers', bind=True, max_retries=0,
    soft_time_limit=4 * 3600, time_limit=4 * 3600 + 300,
)
def data_import_numbers(self, batch_id: str, file_path: str, ext: str,
                        source: str, purpose: str, data_date_str: str,
                        pricing_template_id: Optional[int],
                        tags_json: Optional[list],
                        default_region: Optional[str] = None,
                        force_country: bool = False):
    """异步导入号码 Celery 任务（大文件最多允许 4 小时）"""
    return _run_async(_do_import(
        batch_id, file_path, ext, source, purpose,
        data_date_str, pricing_template_id, tags_json, default_region, force_country,
    ))


async def _do_import(batch_id: str, file_path: str, ext: str,
                     source: str, purpose: str, data_date_str: str,
                     pricing_template_id: Optional[int],
                     tags_json: Optional[list],
                     default_region: Optional[str] = None,
                     force_country: bool = False):
    """流式导入：边解析边入库，恒定内存占用，丰富进度上报"""
    import os
    from sqlalchemy import text as sa_text

    rc = _get_redis()
    t_start = time.monotonic()

    parsed_date = date.fromisoformat(data_date_str) if data_date_str else date.today()
    freshness = compute_freshness(parsed_date)

    eng, Session = _make_session()
    async with Session() as db:
        batch_result = await db.execute(
            select(DataImportBatch).where(DataImportBatch.batch_id == batch_id)
        )
        import_batch = batch_result.scalar_one_or_none()
        if not import_batch:
            logger.error(f"[{batch_id}] 找不到导入批次记录")
            return

        import_batch.status = "processing"
        await db.commit()

        matched_tpl_id = pricing_template_id
        if not matched_tpl_id:
            tpl_result = await db.execute(
                select(DataPricingTemplate.id).where(
                    DataPricingTemplate.source == source,
                    DataPricingTemplate.purpose == purpose,
                    DataPricingTemplate.freshness == freshness,
                    DataPricingTemplate.status == 'active',
                ).limit(1)
            )
            matched_tpl_id = tpl_result.scalar_one_or_none()

        try:
            file_size = os.path.getsize(file_path)

            # 用文件头部采样检测编码
            with open(file_path, 'rb') as f:
                sample = f.read(min(file_size, 128 * 1024))
            detected_enc = None
            for enc in ("utf-8-sig", "utf-8", "gbk", "latin-1"):
                try:
                    sample.decode(enc)
                    detected_enc = enc
                    break
                except (UnicodeDecodeError, LookupError):
                    continue
            if not detected_enc:
                raise ValueError("无法识别文件编码")
            del sample

            INSERT_SQL = sa_text(
                "INSERT IGNORE INTO data_numbers "
                "(phone_number, country_code, tags, carrier, status, "
                "source, purpose, data_date, batch_id, pricing_template_id) "
                "VALUES (:phone, :country, :tags, :carrier, :status, "
                ":source, :purpose, :data_date, :batch_id, :tpl_id)"
            )
            DB_BATCH = 10000
            PROGRESS_INTERVAL = 2.0

            region = default_region.upper() if default_region else None
            forced_cc = (default_region or "").upper() or None
            if forced_cc == "*":
                forced_cc = None
            seen: set = set()
            batch_buf: list = []

            total_count = 0
            cleaned_count = 0
            invalid_count = 0
            file_dedup_count = 0
            valid_count = 0
            duplicate_count = 0
            last_progress_time = t_start

            tags_str = json.dumps(tags_json, ensure_ascii=False) if tags_json else None

            def _make_progress(status: str, phase: str, pct: int = 0):
                elapsed = round(time.monotonic() - t_start, 1)
                speed = int(total_count / max(elapsed, 0.1))
                return {
                    "status": status, "phase": phase,
                    "total_count": total_count,
                    "valid_count": valid_count,
                    "duplicate_count": duplicate_count,
                    "cleaned_count": cleaned_count,
                    "invalid_count": invalid_count,
                    "file_dedup_count": file_dedup_count,
                    "progress_pct": min(pct, 99),
                    "elapsed_seconds": elapsed,
                    "speed": speed,
                    "file_size_mb": round(file_size / 1024 / 1024, 2),
                }

            async def _flush_buf():
                """将缓冲区写入数据库"""
                nonlocal valid_count, duplicate_count
                if not batch_buf:
                    return
                params = [
                    {
                        "phone": r[0], "country": r[1],
                        "tags": r[2], "carrier": r[3],
                        "status": "active", "source": source, "purpose": purpose,
                        "data_date": parsed_date, "batch_id": batch_id,
                        "tpl_id": matched_tpl_id,
                    }
                    for r in batch_buf
                ]
                result = await db.execute(INSERT_SQL, params)
                inserted = result.rowcount
                valid_count += inserted
                duplicate_count += len(batch_buf) - inserted
                await db.commit()
                batch_buf.clear()

            def _should_report():
                nonlocal last_progress_time
                now = time.monotonic()
                if now - last_progress_time >= PROGRESS_INTERVAL:
                    last_progress_time = now
                    return True
                return False

            _update_progress(rc, batch_id, _make_progress("processing", "读取文件中..."))

            def _process_line_txt(raw: str):
                nonlocal total_count, cleaned_count, invalid_count, file_dedup_count
                raw = raw.strip('\r').strip()
                if not raw:
                    return
                total_count += 1
                cleaned = _clean_phone(raw)
                if cleaned is None:
                    cleaned_count += 1
                    return
                result = _parse_phone(cleaned, region)
                if result is None:
                    invalid_count += 1
                    return
                e164, cc, carrier_name = result
                if force_country and forced_cc:
                    cc = forced_cc
                if e164 in seen:
                    file_dedup_count += 1
                    return
                seen.add(e164)
                batch_buf.append((e164, cc, tags_str, carrier_name))

            def _process_row_csv(row):
                nonlocal total_count, cleaned_count, invalid_count, file_dedup_count
                if not row or not row[0].strip():
                    cleaned_count += 1
                    total_count += 1
                    return
                total_count += 1
                cleaned = _clean_phone(row[0].strip())
                if cleaned is None:
                    cleaned_count += 1
                    return
                result = _parse_phone(cleaned, region)
                if result is None:
                    invalid_count += 1
                    return
                e164, cc, carrier_name = result
                if force_country and forced_cc:
                    cc = forced_cc
                if e164 in seen:
                    file_dedup_count += 1
                    return
                seen.add(e164)
                row_tags = tags_json[:] if tags_json else []
                row_country = row[1].strip() if len(row) > 1 and row[1].strip() else None
                if len(row) > 2 and row[2].strip():
                    row_tags.extend([t.strip() for t in row[2].split("|")])
                row_carrier = row[3].strip() if len(row) > 3 and row[3].strip() else None
                t_str = json.dumps(row_tags, ensure_ascii=False) if row_tags else None
                final_cc = row_country or cc
                if force_country and forced_cc:
                    final_cc = forced_cc
                batch_buf.append((e164, final_cc, t_str, row_carrier or carrier_name))

            # 流式读取文件并边解析边入库（用 readline 替代 for 迭代以支持 tell()）
            bytes_read = 0
            with open(file_path, 'rb') as fb:
                if ext == 'csv':
                    import io as _io
                    text_wrapper = _io.TextIOWrapper(fb, encoding=detected_enc, errors='replace')
                    for row in csv.reader(text_wrapper):
                        _process_row_csv(row)
                        if len(batch_buf) >= DB_BATCH:
                            bytes_read = fb.tell()
                            pct = int(bytes_read / max(file_size, 1) * 95)
                            await _flush_buf()
                            if _should_report():
                                _update_progress(rc, batch_id, _make_progress("processing", f"已处理 {total_count:,} 行, 写入 {valid_count:,} 条", pct))
                else:
                    while True:
                        raw_line = fb.readline()
                        if not raw_line:
                            break
                        _process_line_txt(raw_line.decode(detected_enc, errors='replace'))
                        if len(batch_buf) >= DB_BATCH:
                            bytes_read = fb.tell()
                            pct = int(bytes_read / max(file_size, 1) * 95)
                            await _flush_buf()
                            if _should_report():
                                _update_progress(rc, batch_id, _make_progress("processing", f"已处理 {total_count:,} 行, 写入 {valid_count:,} 条", pct))

            # 刷入剩余数据
            await _flush_buf()
            del seen

            logger.info(f"[{batch_id}] 导入完成: 总行={total_count}, 有效={valid_count}, 重复={duplicate_count}")

            elapsed = round(time.monotonic() - t_start, 2)
            batch_result2 = await db.execute(
                select(DataImportBatch).where(DataImportBatch.batch_id == batch_id)
            )
            import_batch = batch_result2.scalar_one()
            import_batch.total_count = total_count
            import_batch.valid_count = valid_count
            import_batch.duplicate_count = duplicate_count
            import_batch.invalid_count = invalid_count
            import_batch.cleaned_count = cleaned_count
            import_batch.file_dedup_count = file_dedup_count
            import_batch.status = "completed"
            import_batch.completed_at = datetime.now()
            await db.commit()

            # 增量更新全局库存汇总
            if valid_count > 0:
                try:
                    await update_stock_summary_from_batch(db, batch_id, delta=1)
                    await db.commit()
                except Exception as e:
                    logger.warning(f"[{batch_id}] 导入后汇总同步失败: {e}")

            product_code = None
            stock_for_product = valid_count
            # 有效导入时：优先用上传时选择的国家，否则从模板获取
            effective_country = (import_batch.country_code or "").upper() or None
            if effective_country and effective_country == "*":
                effective_country = None
            if not effective_country and matched_tpl_id:
                tpl_for_country = await db.execute(
                    select(DataPricingTemplate).where(DataPricingTemplate.id == matched_tpl_id)
                )
                tpl_obj = tpl_for_country.scalar_one_or_none()
                if tpl_obj and tpl_obj.country_code and tpl_obj.country_code != "*":
                    effective_country = _to_iso(tpl_obj.country_code)
            if valid_count == 0 and matched_tpl_id and duplicate_count > 0:
                # 全部为重复时，基于池中现有数量创建商品（避免有号码无商品）
                from app.api.v1.data.helpers import calculate_stock
                tpl = await db.execute(
                    select(DataPricingTemplate).where(DataPricingTemplate.id == matched_tpl_id)
                )
                tpl_obj = tpl.scalar_one_or_none()
                if tpl_obj:
                    if not effective_country and tpl_obj.country_code and tpl_obj.country_code != '*':
                        effective_country = _to_iso(tpl_obj.country_code)
                    elif not effective_country and default_region:
                        effective_country = default_region.upper() if isinstance(default_region, str) else None
                    if effective_country:
                        fc = {"source": source, "purpose": purpose, "freshness": freshness, "country": effective_country}
                        stock_for_product = await calculate_stock(db, fc, public_only=True)
            # 有模板+国家时，即使库存为 0 也创建商品（售罄状态），避免「有导入无商品」
            should_create = stock_for_product > 0 or (
                valid_count == 0 and duplicate_count > 0 and matched_tpl_id and effective_country
            )
            if should_create:
                try:
                    product_code = await _auto_create_product(
                        db, source, purpose, freshness,
                        country_code=effective_country, matched_tpl_id=matched_tpl_id,
                        batch_id=batch_id, valid_count=stock_for_product,
                        file_name=os.path.basename(file_path),
                    )
                except Exception as e:
                    logger.warning(f"[{batch_id}] 自动创建商品失败: {e}")

            speed = int(total_count / max(elapsed, 0.1))
            final = {
                "status": "completed", "phase": "导入完成",
                "total_count": total_count, "valid_count": valid_count,
                "duplicate_count": duplicate_count, "invalid_count": invalid_count,
                "cleaned_count": cleaned_count, "file_dedup_count": file_dedup_count,
                "elapsed_seconds": elapsed, "speed": speed,
                "file_size_mb": round(file_size / 1024 / 1024, 2),
                "pricing_template_id": matched_tpl_id,
                "product_code": product_code,
                "progress_pct": 100,
            }
            _update_progress(rc, batch_id, final)
            logger.info(f"[{batch_id}] 有效={valid_count}, 商品={product_code}, 速度={speed}/s, 耗时={elapsed}s")

        except Exception as e:
            try:
                batch_err = await db.execute(
                    select(DataImportBatch).where(DataImportBatch.batch_id == batch_id)
                )
                ib = batch_err.scalar_one_or_none()
                if ib:
                    ib.status = "failed"
                    ib.error_message = str(e)[:500]
                    await db.commit()
            except Exception:
                pass
            _update_progress(rc, batch_id, {
                "status": "failed", "phase": f"导入失败: {str(e)[:200]}",
                "error": str(e)[:200],
                "elapsed_seconds": round(time.monotonic() - t_start, 1),
            })
            logger.error(f"[{batch_id}] 导入失败: {e}", exc_info=True)
        finally:
            try:
                os.remove(file_path)
            except OSError:
                pass
            rc.close()
    await eng.dispose()


def _to_iso(code: str) -> str:
    """将国家码统一转为 ISO（兼容拨号码和已有 ISO 码）"""
    if not code or code == '*':
        return code
    if code.isalpha() and len(code) == 2:
        return code.upper()
    try:
        regions = phonenumbers.region_codes_for_country_code(int(code))
        if regions:
            return regions[0]
    except (ValueError, TypeError):
        pass
    return code


async def _auto_create_product(
    db, source: str, purpose: str, freshness: str,
    country_code: Optional[str] = None,
    matched_tpl_id: Optional[int] = None,
    batch_id: Optional[str] = None,
    valid_count: int = 0,
    file_name: Optional[str] = None,
) -> Optional[str]:
    """每次导入创建独立数据商品，返回 product_code"""

    filter_criteria = {"source": source, "purpose": purpose, "batch_id": batch_id}

    src_label = SOURCE_LABELS.get(source, source)
    pur_label = PURPOSE_LABELS.get(purpose, purpose)
    from app.modules.data.models import FRESHNESS_LABELS
    fr_label = FRESHNESS_LABELS.get(freshness, freshness)

    iso_code = ""
    price = "0.001"
    if matched_tpl_id:
        tpl = await db.execute(
            select(DataPricingTemplate).where(DataPricingTemplate.id == matched_tpl_id)
        )
        tpl_obj = tpl.scalar_one_or_none()
        if tpl_obj:
            price = str(tpl_obj.price_per_number)
            if tpl_obj.country_code and tpl_obj.country_code != '*':
                iso_code = _to_iso(tpl_obj.country_code)
            elif country_code:
                iso_code = _to_iso(country_code)
            if iso_code:
                filter_criteria["country"] = iso_code

    # product_code 限 50 字符，用批次末尾短码，超出则截断
    if batch_id and "-" in batch_id:
        batch_suffix = batch_id.split("-")[-1][:8]  # 如 A00BF9
    elif batch_id:
        batch_suffix = batch_id[-8:] if len(batch_id) > 8 else batch_id
    else:
        batch_suffix = datetime.now().strftime("%H%M%S")
    # source/purpose 可能来自用户输入，限制长度避免超 50 字符
    _src = (source or "")[:16]
    _pur = (purpose or "")[:16]
    _fr = (freshness or "")[:8]
    if iso_code:
        code = f"AUTO-{iso_code}-{_src}-{_pur}-{_fr}-{batch_suffix}"[:50]
    else:
        code = f"AUTO-{_src}-{_pur}-{_fr}-{batch_suffix}"[:50]

    REGIONS_MAP = {
        'CN': '中国', 'VN': '越南', 'PH': '菲律宾', 'BR': '巴西',
        'CO': '哥伦比亚', 'MX': '墨西哥', 'ID': '印尼', 'TH': '泰国',
        'IN': '印度', 'MY': '马来西亚', 'SG': '新加坡', 'JP': '日本',
        'KR': '韩国', 'US': '美国', 'GB': '英国', 'DE': '德国',
        'FR': '法国', 'IT': '意大利', 'AU': '澳大利亚', 'CA': '加拿大', 'RU': '俄罗斯',
        'SA': '沙特', 'AE': '阿联酋', 'TR': '土耳其', 'NG': '尼日利亚',
        'EG': '埃及', 'ZA': '南非', 'PE': '秘鲁', 'CL': '智利',
        'AR': '阿根廷', 'PK': '巴基斯坦', 'BD': '孟加拉',
        'MM': '缅甸', 'KH': '柬埔寨', 'LA': '老挝', 'NP': '尼泊尔',
        'TW': '台湾', 'HK': '香港', 'MO': '澳门',
    }
    country_name = REGIONS_MAP.get(iso_code, iso_code) if iso_code else "全球"
    product_name = f"{country_name}-{src_label}-{pur_label}-{fr_label}"

    original_name = ""
    if file_name:
        name_part = file_name.rsplit(".", 1)[0] if "." in file_name else file_name
        original_name = name_part[:50]

    desc_parts = [f"来源: {src_label}", f"用途: {pur_label}", f"时效: {fr_label}"]
    if original_name:
        desc_parts.append(f"文件: {original_name}")
    if batch_id:
        desc_parts.append(f"批次: {batch_id}")
    desc = ", ".join(desc_parts)

    product = DataProduct(
        product_code=code,
        product_name=product_name,
        description=desc,
        filter_criteria=filter_criteria,
        price_per_number=price,
        stock_count=valid_count,
        min_purchase=10,
        max_purchase=max(valid_count, 100000),
        product_type='data_only',
        status='active' if valid_count > 0 else 'sold_out',
    )
    db.add(product)
    await db.commit()
    logger.info(f"创建商品 {code}: {product_name}, 库存={valid_count}, 文件={file_name}")

    return code


@celery_app.task(name="private_library_upload", bind=True, soft_time_limit=3600, time_limit=3660)
def private_library_upload(self, task_id: str):
    """客户私库异步上传（大文件），进度写入 private_library_upload_tasks"""
    return _run_async(_do_private_library_upload_task(task_id))


async def _do_private_library_upload_task(task_id: str):
    from app.modules.data.private_upload_core import run_private_library_upload

    eng, Session = _make_session()
    try:
        async with Session() as db:
            row = (
                await db.execute(
                    select(PrivateLibraryUploadTask).where(PrivateLibraryUploadTask.task_id == task_id)
                )
            ).scalar_one_or_none()
            if not row:
                logger.error("私库上传任务不存在: %s", task_id)
                return {"ok": False, "error": "not_found"}

            row.status = "processing"
            row.stage = "starting"
            row.progress_percent = 1
            await db.commit()

            fpath = row.file_path
            try:
                with open(fpath, "rb") as f:
                    content = f.read()
            except OSError as e:
                await db.execute(
                    sa_update(PrivateLibraryUploadTask)
                    .where(PrivateLibraryUploadTask.id == row.id)
                    .values(
                        status="failed",
                        error_message=f"读取上传文件失败: {e}",
                        completed_at=datetime.now(),
                    )
                )
                await db.commit()
                return {"ok": False, "error": str(e)}

            tid = row.id

            async def progress(**kw):
                vals = {}
                if "stage" in kw:
                    vals["stage"] = kw["stage"]
                if "progress_percent" in kw:
                    vals["progress_percent"] = kw["progress_percent"]
                if "total_unique" in kw:
                    vals["total_unique"] = kw["total_unique"]
                if "inserted" in kw:
                    vals["inserted"] = kw["inserted"]
                if "updated" in kw:
                    vals["updated"] = kw["updated"]
                if "batch_id" in kw:
                    vals["result_batch_id"] = kw["batch_id"]
                if vals:
                    await db.execute(
                        sa_update(PrivateLibraryUploadTask)
                        .where(PrivateLibraryUploadTask.id == tid)
                        .values(**vals)
                    )
                    await db.commit()

            try:
                result = await run_private_library_upload(
                    db,
                    row.account_id,
                    content,
                    row.original_filename or "upload.txt",
                    row.country_code,
                    row.source,
                    row.purpose,
                    row.remarks,
                    bool(row.detect_carrier),
                    progress=progress,
                )
            except ValueError as e:
                logger.warning("私库上传任务校验失败: %s %s", task_id, e)
                await db.rollback()
                await db.execute(
                    sa_update(PrivateLibraryUploadTask)
                    .where(PrivateLibraryUploadTask.id == tid)
                    .values(
                        status="failed",
                        error_message=str(e)[:4000],
                        completed_at=datetime.now(),
                    )
                )
                await db.commit()
                return {"ok": False, "error": str(e)}
            except Exception as e:
                logger.exception("私库上传任务失败: %s", task_id)
                await db.rollback()
                await db.execute(
                    sa_update(PrivateLibraryUploadTask)
                    .where(PrivateLibraryUploadTask.id == tid)
                    .values(
                        status="failed",
                        error_message=str(e)[:4000],
                        completed_at=datetime.now(),
                    )
                )
                await db.commit()
                return {"ok": False, "error": str(e)}

            result_batch_id = result.get("batch_id")
            await db.execute(
                sa_update(PrivateLibraryUploadTask)
                .where(PrivateLibraryUploadTask.id == tid)
                .values(
                    status="completed",
                    inserted=result.get("inserted", 0),
                    updated=result.get("updated", 0),
                    total_unique=result.get("total", 0),
                    progress_percent=100,
                    stage="completed",
                    result_batch_id=result_batch_id,
                    completed_at=datetime.now(),
                )
            )
            await db.commit()

            # 将 batch_name（原始文件名）和 export_password_hash 写入对应的汇总行
            if result_batch_id:
                from app.modules.data.models import PrivateLibrarySummary
                try:
                    await db.execute(
                        sa_update(PrivateLibrarySummary)
                        .where(
                            PrivateLibrarySummary.account_id == row.account_id,
                            PrivateLibrarySummary.batch_id == result_batch_id,
                        )
                        .values(
                            batch_name=(row.original_filename or "")[:255] or None,
                            export_password_hash=row.export_password_hash,
                        )
                    )
                    await db.commit()
                except Exception as ex:
                    logger.warning("私库上传写入 batch_name/export_password_hash 失败: %s", ex)

            # 与 run_private_library_upload 内失效互补：避免 Worker 连不上 Redis 时用户长期看到旧汇总
            try:
                from app.utils.data_customer_cache import invalidate_my_numbers_summary_cache

                await invalidate_my_numbers_summary_cache(row.account_id)
            except Exception as ex:
                logger.warning(
                    "私库上传任务完成后汇总缓存失效失败 account=%s: %s",
                    row.account_id,
                    ex,
                )

            try:
                os.remove(fpath)
            except OSError:
                pass

            logger.info(
                "私库上传任务完成: %s account=%s inserted=%s updated=%s",
                task_id,
                row.account_id,
                result.get("inserted"),
                result.get("updated"),
            )
            return {"ok": True, "result": result}
    finally:
        await eng.dispose()


@celery_app.task(name="private_library_sync_used", bind=True, soft_time_limit=300, time_limit=360)
def private_library_sync_used(self, account_id: int, phone_numbers: list):
    """异步更新私库汇总表的 used_count（发送时触发）"""
    return _run_async(_do_sync_used(account_id, phone_numbers))


async def _do_sync_used(account_id: int, phone_numbers: list):
    from app.modules.data.private_library_summary_sync import (
        ORIGIN_MANUAL, ORIGIN_PURCHASED, norm_dim, pls_apply_deltas_bulk,
    )
    from app.modules.data.models import PrivateLibraryNumber

    eng, Session = _make_session()
    try:
        async with Session() as db:
            BATCH_SZ = 2000
            pls_deltas = []
            now = datetime.now()

            for ci in range(0, len(phone_numbers), BATCH_SZ):
                chunk = phone_numbers[ci:ci + BATCH_SZ]
                res_pln = await db.execute(
                    select(PrivateLibraryNumber).where(
                        PrivateLibraryNumber.account_id == account_id,
                        PrivateLibraryNumber.phone_number.in_(chunk),
                        PrivateLibraryNumber.use_count == 1,
                        PrivateLibraryNumber.is_deleted == False,  # noqa: E712
                    )
                )
                for row in res_pln.scalars():
                    pls_deltas.append((
                        ORIGIN_MANUAL,
                        norm_dim(row.country_code), norm_dim(row.source),
                        norm_dim(row.purpose), norm_dim(row.batch_id),
                        norm_dim(row.carrier), 0, 1,
                        row.remarks, row.created_at, now,
                    ))

                res_dn = await db.execute(
                    select(DataNumber).where(
                        DataNumber.account_id == account_id,
                        DataNumber.phone_number.in_(chunk),
                        DataNumber.use_count == 1,
                    )
                )
                for row in res_dn.scalars():
                    pls_deltas.append((
                        ORIGIN_PURCHASED,
                        norm_dim(row.country_code), norm_dim(row.source),
                        norm_dim(row.purpose), norm_dim(row.batch_id),
                        norm_dim(row.carrier), 0, 1,
                        row.remarks, row.created_at, now,
                    ))

            if pls_deltas:
                await pls_apply_deltas_bulk(db, account_id, pls_deltas)
                await db.commit()
                logger.info(f"私库汇总同步完成: account={account_id}, deltas={len(pls_deltas)}")
    finally:
        await eng.dispose()
