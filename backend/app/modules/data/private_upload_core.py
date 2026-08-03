"""
私库号码上传核心逻辑（同步接口与 Celery 任务共用）。
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional

from collections import Counter

from sqlalchemy import insert
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
    filter_numbers_by_real_country,
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

    # 按账户国家剔除"区号相同但真实国家不同"的号码（如 US 账户上传 +1 里的 PR/CA 等共用区号号码）
    dropped_by_country: Dict[str, int] = {}
    if region_iso:
        numbers_to_add, dropped_by_country = filter_numbers_by_real_country(numbers_to_add, region_iso)
        if dropped_by_country:
            await _p(stage="country_filtered", progress_percent=12)
        if not numbers_to_add:
            raise ValueError(
                f"上传的号码经识别均不属于账户国家 {region_iso}（已剔除：{dropped_by_country}）。"
                f"请确认上传的是 {region_iso} 号码。"
            )

    unique_numbers = sorted(list(set(numbers_to_add)))
    total_u = len(unique_numbers)
    await _p(stage="deduped", progress_percent=15, total_unique=total_u)

    # 勾选识别时对全部新增号码做运营商查询；未勾选时仅对少量号码自动识别（兼容旧行为）
    want_carrier_lookup = detect_carrier or total_u <= 5_000

    batch_id = f"UP-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    now = datetime.now()

    # 分包独立：不跨包查重、不改挂。本包内去重后全部作为新行写入，与账户里
    # 其它数据包重号是允许的（唯一键含 batch_id），各包的总数/已使用互不影响。
    # 旧实现会把重号的老行 batch_id 改成新包并清零 use_count，导致老包凭空缩水、
    # 已发过的号变回"未使用"，卡片数字与客户上传的文件条数对不上。
    await _p(stage="loading_existing", progress_percent=40, total_unique=total_u)

    carrier_map: Dict[str, Optional[str]] = {}
    if want_carrier_lookup and unique_numbers:
        # 分块在线程池中识别，避免单次任务过大；进度 44%–49% 后进入写入 50%+
        ncar = len(unique_numbers)
        chunk_sz = 3000
        n_car_chunks = max(1, (ncar + chunk_sz - 1) // chunk_sz)
        for ci, i in enumerate(range(0, ncar, chunk_sz)):
            sub = unique_numbers[i : i + chunk_sz]
            pct = 45 if n_car_chunks <= 1 else 44 + int(5 * (ci + 1) / n_car_chunks)
            await _p(stage="carrier_lookup", progress_percent=pct, total_unique=total_u)
            part = await asyncio.to_thread(batch_lookup_carriers, sub)
            carrier_map.update(part)

    insert_dicts: List[dict] = [
        {
            "phone_number": num,
            "country_code": country_code,
            "source": source,
            "purpose": purpose,
            "remarks": remarks,
            "account_id": account_id,
            "status": "active",
            "batch_id": batch_id,
            "carrier": carrier_map.get(num) if want_carrier_lookup else None,
            "tags": ["private_upload"],
            "is_deleted": False,
            "created_at": now,
            "updated_at": now,
        }
        for num in unique_numbers
    ]

    await _p(stage="inserting", progress_percent=50, total_unique=total_u)
    ins_chunks = max(1, (len(insert_dicts) + 4999) // 5000)
    actually_inserted = 0
    if insert_dicts:
        chunk_size = 5000
        for j, i in enumerate(range(0, len(insert_dicts), chunk_size)):
            chunk_data = insert_dicts[i : i + chunk_size]
            stmt = insert(PrivateLibraryNumber).prefix_with("IGNORE")
            result = await db.execute(stmt, chunk_data)
            actually_inserted += getattr(result, 'rowcount', len(chunk_data))
            pct = 50 + int(35 * (j + 1) / ins_chunks)
            await _p(
                stage="inserting",
                progress_percent=min(pct, 85),
                total_unique=total_u,
                inserted=min(i + chunk_size, len(insert_dicts)),
            )

    await _p(stage="updating", progress_percent=88, total_unique=total_u)

    # 写时维护私库汇总表（与明细同一事务）。分包独立后本次上传只新增本包的桶，
    # 不再需要"从旧包桶里减一"的补偿逻辑。
    deltas: List[tuple] = []
    cc_n = norm_dim(country_code)
    src_n = norm_dim(source or "")
    pur_n = norm_dim(purpose or "")
    bid_n = norm_dim(batch_id)
    for car_k, n in Counter(norm_dim(d.get("carrier")) for d in insert_dicts).items():
        deltas.append(
            (ORIGIN_MANUAL, cc_n, src_n, pur_n, bid_n, car_k, n, 0, remarks, now, now)
        )
    if deltas:
        await pls_apply_deltas_bulk(db, account_id, deltas)
        await pls_prune_non_positive(db, account_id)

    await db.commit()
    await invalidate_my_numbers_summary_cache(account_id)

    n_ins = actually_inserted
    n_upd = 0  # 分包独立后不再改挂已有记录，保留字段兼容前端/日志
    n_dup = len(insert_dicts) - actually_inserted
    await _p(
        stage="completed",
        progress_percent=100,
        total_unique=total_u,
        inserted=n_ins,
        updated=n_upd,
        batch_id=batch_id,
    )

    n_dropped = sum(dropped_by_country.values()) if dropped_by_country else 0
    _drop_msg = ""
    if n_dropped:
        _detail = "、".join(f"{k}:{v}" for k, v in sorted(dropped_by_country.items(), key=lambda x: -x[1]))
        _drop_msg = f"，剔除 {n_dropped} 条非 {region_iso} 国家号码（{_detail}）"
    return {
        "success": True,
        "message": f"成功上传 {n_ins} 条数据" + (f"，跳过 {n_dup} 条重复" if n_dup else "") + _drop_msg,
        "total": total_u,
        "added": n_ins + n_upd,
        "inserted": n_ins,
        "updated": n_upd,
        "dropped_non_country": n_dropped,
        "dropped_by_country": dropped_by_country,
        "batch_id": batch_id,
        "skipped_other_account": 0,
        "duplicates": n_dup,
    }
