"""
私库号码上传核心逻辑（同步接口与 Celery 任务共用）。
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from collections import Counter

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.data.models import PrivateLibraryNumber
from app.modules.data.private_library_summary_sync import (
    ORIGIN_MANUAL,
    norm_dim,
    pls_apply_deltas_bulk,
    pls_prune_non_positive,
)
from app.modules.data.private_upload_parse import (
    batch_lookup_carriers,
    decode_my_numbers_upload_bytes,
    extract_phone_numbers_from_upload_text,
    phone_db_lookup_keys,
)
from app.utils.data_customer_cache import invalidate_my_numbers_summary_cache

ProgressCb = Optional[Callable[..., Awaitable[None]]]


async def run_private_library_upload(
    db: AsyncSession,
    account_id: int,
    content: bytes,
    fname: str,
    country_code: str,
    source: Optional[str],
    purpose: Optional[str],
    remarks: Optional[str],
    detect_carrier: bool,
    progress: ProgressCb = None,
) -> Dict[str, Any]:
    """
    执行私库上传写入 private_library_numbers。
    progress: async (stage=..., progress_percent=..., total_unique=..., inserted=..., updated=...) 可选。
    """
    async def _p(**kw: Any) -> None:
        if progress:
            await progress(**kw)

    fname = fname or ""
    if not fname.lower().endswith((".csv", ".txt")):
        raise ValueError("仅支持 CSV 或 TXT 文件")

    await _p(stage="decoding", progress_percent=2)
    text_content = decode_my_numbers_upload_bytes(content)
    region_iso = (country_code or "").strip().upper() or None

    parse_threshold = 200_000
    await _p(stage="parsing", progress_percent=8)
    if len(content) > parse_threshold:
        numbers_to_add = await asyncio.to_thread(
            extract_phone_numbers_from_upload_text, fname, text_content, region_iso
        )
    else:
        numbers_to_add = extract_phone_numbers_from_upload_text(fname, text_content, region_iso)

    if not numbers_to_add:
        raise ValueError(
            "未检测到有效手机号码。请确认国家/地区与文件编码；TXT/CSV 中号码可被识别。"
        )

    unique_numbers = sorted(list(set(numbers_to_add)))
    total_u = len(unique_numbers)
    await _p(stage="deduped", progress_percent=15, total_unique=total_u)

    # 勾选识别时对全部新增号码做运营商查询；未勾选时仅对少量号码自动识别（兼容旧行为）
    want_carrier_lookup = detect_carrier or total_u <= 5_000

    existing_pln: Dict[str, int] = {}
    chunk_n = 800
    nchunks = max(1, (total_u + chunk_n - 1) // chunk_n)
    for ci, i in enumerate(range(0, total_u, chunk_n)):
        chunk = unique_numbers[i : i + chunk_n]
        variants: List[str] = []
        for n in chunk:
            variants.extend(phone_db_lookup_keys(n))
        q = select(PrivateLibraryNumber.id, PrivateLibraryNumber.phone_number).where(
            PrivateLibraryNumber.account_id == account_id,
            PrivateLibraryNumber.phone_number.in_(variants),
        )
        res = await db.execute(q)
        for row in res.all():
            canon = (row.phone_number or "").lstrip("+")
            if canon not in existing_pln:
                existing_pln[canon] = row.id
        pct = 15 + int(25 * (ci + 1) / nchunks)
        await _p(stage="loading_existing", progress_percent=min(pct, 40), total_unique=total_u)

    insert_dicts: List[dict] = []
    update_ids: List[int] = []

    batch_id = f"UP-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    now = datetime.now()

    new_for_carrier: List[str] = [
        n for n in unique_numbers if n.lstrip("+") not in existing_pln
    ]
    carrier_map: Dict[str, Optional[str]] = {}
    if want_carrier_lookup and new_for_carrier:
        # 分块在线程池中识别，避免单次任务过大；进度 44%–49% 后进入写入 50%+
        ncar = len(new_for_carrier)
        chunk_sz = 3000
        n_car_chunks = max(1, (ncar + chunk_sz - 1) // chunk_sz)
        for ci, i in enumerate(range(0, ncar, chunk_sz)):
            sub = new_for_carrier[i : i + chunk_sz]
            pct = 45 if n_car_chunks <= 1 else 44 + int(5 * (ci + 1) / n_car_chunks)
            await _p(stage="carrier_lookup", progress_percent=pct, total_unique=total_u)
            part = await asyncio.to_thread(batch_lookup_carriers, sub)
            carrier_map.update(part)

    for num in unique_numbers:
        canon = num.lstrip("+")
        pln_id = existing_pln.get(canon)
        if pln_id is None:
            detected_carrier = carrier_map.get(num) if want_carrier_lookup else None
            insert_dicts.append(
                {
                    "phone_number": num,
                    "country_code": country_code,
                    "source": source,
                    "purpose": purpose,
                    "remarks": remarks,
                    "account_id": account_id,
                    "status": "active",
                    "batch_id": batch_id,
                    "carrier": detected_carrier,
                    "tags": ["private_upload"],
                    "is_deleted": False,
                    "created_at": now,
                    "updated_at": now,
                }
            )
        else:
            update_ids.append(pln_id)

    await _p(stage="inserting", progress_percent=50, total_unique=total_u)
    ins_chunks = max(1, (len(insert_dicts) + 4999) // 5000)
    if insert_dicts:
        chunk_size = 5000
        for j, i in enumerate(range(0, len(insert_dicts), chunk_size)):
            await db.execute(insert(PrivateLibraryNumber), insert_dicts[i : i + chunk_size])
            pct = 50 + int(35 * (j + 1) / ins_chunks)
            await _p(
                stage="inserting",
                progress_percent=min(pct, 85),
                total_unique=total_u,
                inserted=min(i + chunk_size, len(insert_dicts)),
            )

    # 快照旧维度值（必须在 UPDATE 之前读取，否则 batch_id 已被改为新值，旧桶永不减少）
    _old_snapshots: List[Tuple[str, str, str, str, str, int]] = []
    if update_ids:
        await db.flush()
        ch_sz = 2000
        for j in range(0, len(update_ids), ch_sz):
            chunk = update_ids[j : j + ch_sz]
            res = await db.execute(
                select(
                    PrivateLibraryNumber.country_code,
                    PrivateLibraryNumber.source,
                    PrivateLibraryNumber.purpose,
                    PrivateLibraryNumber.batch_id,
                    PrivateLibraryNumber.carrier,
                    PrivateLibraryNumber.use_count,
                ).where(PrivateLibraryNumber.id.in_(chunk))
            )
            for r in res.all():
                _old_snapshots.append((
                    norm_dim(r[0]), norm_dim(r[1]), norm_dim(r[2]),
                    norm_dim(r[3]), norm_dim(r[4]), int(r[5] or 0),
                ))

    await _p(stage="updating", progress_percent=88, total_unique=total_u)
    if update_ids:
        chunk_size = 5000
        for i in range(0, len(update_ids), chunk_size):
            chunk_ids = update_ids[i : i + chunk_size]
            stmt = (
                update(PrivateLibraryNumber)
                .where(PrivateLibraryNumber.id.in_(chunk_ids))
                .values(
                    status="active",
                    batch_id=batch_id,
                    use_count=0,
                    last_used_at=None,
                    is_deleted=False,
                    updated_at=now,
                )
            )
            if remarks is not None:
                stmt = stmt.values(remarks=remarks)
            await db.execute(stmt)

    # 写时维护私库汇总表（与明细同一事务）
    deltas: List[tuple] = []
    cc_n = norm_dim(country_code)
    src_n = norm_dim(source or "")
    pur_n = norm_dim(purpose or "")
    bid_n = norm_dim(batch_id)
    for car_k, n in Counter(norm_dim(d.get("carrier")) for d in insert_dicts).items():
        deltas.append(
            (ORIGIN_MANUAL, cc_n, src_n, pur_n, bid_n, car_k, n, 0, remarks, now, now)
        )
    for oc, osrc, opur, ob, ocar, ouc in _old_snapshots:
        deltas.append((ORIGIN_MANUAL, oc, osrc, opur, ob, ocar, -1, -1 if ouc > 0 else 0, None, None, None))
        deltas.append(
            (ORIGIN_MANUAL, oc, osrc, opur, bid_n, ocar, 1, 0, remarks, now, now)
        )
    if deltas:
        await pls_apply_deltas_bulk(db, account_id, deltas)
        await pls_prune_non_positive(db, account_id)

    await db.commit()
    await invalidate_my_numbers_summary_cache(account_id)

    n_ins = len(insert_dicts)
    n_upd = len(update_ids)
    await _p(
        stage="completed",
        progress_percent=100,
        total_unique=total_u,
        inserted=n_ins,
        updated=n_upd,
        batch_id=batch_id,
    )

    return {
        "success": True,
        "message": f"成功上传 {n_ins} 条新数据，更新 {n_upd} 条已有私库记录",
        "total": total_u,
        "added": n_ins + n_upd,
        "inserted": n_ins,
        "updated": n_upd,
        "batch_id": batch_id,
        "skipped_other_account": 0,
        "duplicates": 0,
    }
