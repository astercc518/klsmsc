"""
数据业务定时任务 Worker
"""
from datetime import datetime, timedelta, date
from decimal import Decimal
from typing import Optional
from sqlalchemy import select, func, or_
from app.workers.celery_app import celery_app
import app.models  # noqa: F401 确保所有 ORM 关系模型被加载
from app.modules.data.models import DataNumber, DataProduct, DataOrder, DataImportBatch, DataPricingTemplate, DATA_SOURCES, DATA_PURPOSES, SOURCE_LABELS, PURPOSE_LABELS
from app.utils.logger import get_logger
from app.api.v1.data.helpers import calculate_stock, compute_freshness
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

    eng = create_async_engine(
        settings.DATABASE_URL, echo=False,
        pool_size=2, max_overflow=3,
        pool_pre_ping=True, pool_recycle=600,
    )
    factory = async_sessionmaker(eng, class_=AsyncSession,
                                 expire_on_commit=False, autocommit=False, autoflush=False)
    return eng, factory


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
        for product in products:
            try:
                new_stock = await calculate_stock(db, product.filter_criteria, public_only=True)
                if product.stock_count != new_stock:
                    product.stock_count = new_stock
                    updated += 1
            except Exception as e:
                logger.error(f"刷新商品 {product.id} 库存失败: {e}")

        await db.commit()
        logger.info(f"库存刷新完成: 共 {len(products)} 个商品, 更新 {updated} 个")
    await eng.dispose()
    return {"total": len(products), "updated": updated}


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
                        default_region: Optional[str] = None):
    """异步导入号码 Celery 任务（大文件最多允许 4 小时）"""
    return _run_async(_do_import(
        batch_id, file_path, ext, source, purpose,
        data_date_str, pricing_template_id, tags_json, default_region,
    ))


async def _do_import(batch_id: str, file_path: str, ext: str,
                     source: str, purpose: str, data_date_str: str,
                     pricing_template_id: Optional[int],
                     tags_json: Optional[list],
                     default_region: Optional[str] = None):
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
                batch_buf.append((e164, row_country or cc, t_str, row_carrier or carrier_name))

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

            product_code = None
            stock_for_product = valid_count
            effective_country = None  # 用于商品创建的国家（模板指定或上传时选择）
            if valid_count == 0 and matched_tpl_id and duplicate_count > 0:
                # 全部为重复时，基于池中现有数量创建商品（避免有号码无商品）
                from app.api.v1.data.helpers import calculate_stock
                tpl = await db.execute(
                    select(DataPricingTemplate).where(DataPricingTemplate.id == matched_tpl_id)
                )
                tpl_obj = tpl.scalar_one_or_none()
                if tpl_obj:
                    if tpl_obj.country_code and tpl_obj.country_code != '*':
                        effective_country = _to_iso(tpl_obj.country_code)
                    elif default_region:
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
    if freshness:
        filter_criteria["freshness"] = freshness

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

    # product_code 限 50 字符，用批次末尾短码
    if batch_id and "-" in batch_id:
        batch_suffix = batch_id.split("-")[-1][:8]  # 如 A00BF9
    elif batch_id:
        batch_suffix = batch_id[-8:] if len(batch_id) > 8 else batch_id
    else:
        batch_suffix = datetime.now().strftime("%H%M%S")
    if iso_code:
        code = f"AUTO-{iso_code}-{source}-{purpose}-{freshness}-{batch_suffix}"
    else:
        code = f"AUTO-{source}-{purpose}-{freshness}-{batch_suffix}"

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
