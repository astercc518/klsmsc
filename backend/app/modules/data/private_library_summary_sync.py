"""
私库卡片汇总表 private_library_summaries 写时维护工具。
与明细表 private_library_numbers（manual）、data_numbers 购入绑定（purchased）保持一致。
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.data.models import PrivateLibrarySummary

# 与 models / 迁移中 library_origin 取值一致
ORIGIN_MANUAL = "manual"
ORIGIN_PURCHASED = "purchased"


def norm_dim(v: Optional[str]) -> str:
    """汇总表维度归一化（空串表示缺省，与迁移 SQL 一致）"""
    if v is None:
        return ""
    s = str(v).strip()
    return s


def carrier_label(v: Optional[str]) -> str:
    """与前端卡片「Unknown」一致"""
    return norm_dim(v) if norm_dim(v) else "Unknown"


async def pls_apply_bucket_delta(
    db: AsyncSession,
    *,
    account_id: int,
    library_origin: str,
    country_code: str,
    source: str,
    purpose: str,
    batch_id: str,
    carrier: str,
    delta_total: int,
    delta_used: int,
    remarks: Optional[str] = None,
    touch_first: Optional[datetime] = None,
    touch_last: Optional[datetime] = None,
) -> None:
    """
    对单个桶做增量（可正可负）。统一先查后改，避免 INSERT 负增量产生空桶脏行。
    """
    cc = norm_dim(country_code)
    src = norm_dim(source)
    pur = norm_dim(purpose)
    bid = norm_dim(batch_id)
    car = norm_dim(carrier)
    org = library_origin if library_origin in (ORIGIN_MANUAL, ORIGIN_PURCHASED) else ORIGIN_MANUAL

    rmk = (remarks or None) if remarks else None
    fa = touch_first
    la = touch_last

    q = select(PrivateLibrarySummary).where(
        PrivateLibrarySummary.account_id == account_id,
        PrivateLibrarySummary.country_code == cc,
        PrivateLibrarySummary.source == src,
        PrivateLibrarySummary.purpose == pur,
        PrivateLibrarySummary.batch_id == bid,
        PrivateLibrarySummary.carrier == car,
        PrivateLibrarySummary.library_origin == org,
    )
    row = (await db.execute(q)).scalar_one_or_none()
    if row is None:
        nt = max(0, delta_total)
        nu = max(0, delta_used)
        nu = min(nu, nt)
        if nt <= 0:
            return
        db.add(
            PrivateLibrarySummary(
                account_id=account_id,
                country_code=cc,
                source=src,
                purpose=pur,
                batch_id=bid,
                carrier=car,
                library_origin=org,
                total_count=nt,
                used_count=nu,
                remarks=rmk,
                first_at=fa,
                last_at=la,
            )
        )
        return

    nt = max(0, (row.total_count or 0) + delta_total)
    nu = max(0, (row.used_count or 0) + delta_used)
    nu = min(nu, nt)
    row.total_count = nt
    row.used_count = nu
    # 正增量恢复被软删的汇总行（客户重新上传数据时自动复活卡片）
    if delta_total > 0 and getattr(row, "is_deleted", False):
        row.is_deleted = False
    if rmk and (not row.remarks or len(rmk) > len(row.remarks or "")):
        row.remarks = rmk
    if fa is not None:
        if row.first_at is None or fa < row.first_at:
            row.first_at = fa
    if la is not None:
        if row.last_at is None or la > row.last_at:
            row.last_at = la


async def pls_prune_non_positive(db: AsyncSession, account_id: int) -> None:
    """删除 total_count<=0 的汇总行（硬删，用于管理端物理删除场景）"""
    await db.execute(
        delete(PrivateLibrarySummary).where(
            PrivateLibrarySummary.account_id == account_id,
            PrivateLibrarySummary.total_count <= 0,
        )
    )


async def pls_soft_prune_non_positive(db: AsyncSession, account_id: int) -> None:
    """标记 total_count<=0 的汇总行为 is_deleted=True（客户侧软删场景，管理端仍可查阅）"""
    await db.execute(
        update(PrivateLibrarySummary)
        .where(
            PrivateLibrarySummary.account_id == account_id,
            PrivateLibrarySummary.total_count <= 0,
        )
        .values(is_deleted=True)
    )


async def pls_apply_deltas_bulk(
    db: AsyncSession,
    account_id: int,
    deltas: List[Tuple[str, str, str, str, str, str, int, int, Optional[str], Optional[datetime], Optional[datetime]]],
) -> None:
    """
    批量应用桶增量。元组:
    (origin, country, source, purpose, batch_id, carrier, delta_total, delta_used, remarks?, first?, last?)
    """
    merged: Dict[Tuple, list] = defaultdict(list)
    for t in deltas:
        if len(t) != 11:
            continue
        org, c, s, p, b, car, dt, du, rmk, fa, la = t
        key = (org or ORIGIN_MANUAL, norm_dim(c), norm_dim(s), norm_dim(p), norm_dim(b), norm_dim(car))
        merged[key].append((int(dt or 0), int(du or 0), rmk, fa, la))

    for (org, c, s, p, b, car), parts in merged.items():
        sdt = sum(x[0] for x in parts)
        sdu = sum(x[1] for x in parts)
        # 取最长备注、最早 first、最晚 last
        rmk = None
        fa = None
        la = None
        for _, _, r, f, l in parts:
            if r and (rmk is None or len(r) > len(rmk or "")):
                rmk = r
            if f is not None:
                fa = f if fa is None else min(fa, f)
            if l is not None:
                la = l if la is None else max(la, l)
        await pls_apply_bucket_delta(
            db,
            account_id=account_id,
            library_origin=org,
            country_code=c,
            source=s,
            purpose=p,
            batch_id=b,
            carrier=car,
            delta_total=sdt,
            delta_used=sdu,
            remarks=rmk,
            touch_first=fa,
            touch_last=la,
        )


def build_summary_payload_from_rows(
    rows: List[PrivateLibrarySummary],
    *,
    max_batches: int,
    total_all_accounts_hint: Optional[int] = None,
) -> dict:
    """
    将 PrivateLibrarySummary 行转为与旧版 _compute_summary 一致的 JSON（含按卡片合并 carrier）。
    """
    if not rows:
        meta = {
            "max_batches": max_batches,
            "truncated": False,
            "batch_card_limit": max_batches if max_batches > 0 else None,
        }
        return {
            "success": True,
            "items": [],
            "total": int(total_all_accounts_hint or 0),
            "meta": meta,
        }

    total = sum((r.total_count or 0) for r in rows)

    working = list(rows)
    truncated_hint = False
    if max_batches > 0:
        batch_last: Dict[str, datetime] = {}
        for r in working:
            bid = norm_dim(r.batch_id)
            la = r.last_at or r.first_at
            if la is None:
                continue
            if bid not in batch_last or la > batch_last[bid]:
                batch_last[bid] = la
        sorted_bids = sorted(
            batch_last.keys(),
            key=lambda b: batch_last.get(b) or datetime.min,
            reverse=True,
        )
        if len(sorted_bids) > max_batches:
            truncated_hint = True
        keep: Set[str] = set(sorted_bids[:max_batches])
        working = [r for r in working if norm_dim(r.batch_id) in keep]

    # 卡片键：国家+来源+用途+批次（与旧版一致）；合并 manual/purchased 为 mixed
    groups: Dict[Tuple[str, str, str, str], dict] = {}
    for r in working:
        key = (norm_dim(r.country_code), norm_dim(r.source), norm_dim(r.purpose), norm_dim(r.batch_id))
        if key not in groups:
            groups[key] = {
                "country_code": key[0],
                "source": key[1],
                "purpose": key[2],
                "batch_id": key[3],
                "batch_name": None,
                "export_password_hash": None,
                "remarks": None,
                "_origins": set(),
                "_count": 0,
                "_used": 0,
                "_carrier_map": defaultdict(int),
                "_carrier_unused_map": defaultdict(int),
                "_first_at": None,
                "_last_at": None,
                "_is_deleted": True,
            }
        g = groups[key]
        g["_origins"].add(r.library_origin)
        # 只要任一汇总行未软删，卡片即视为存活
        if not getattr(r, "is_deleted", False):
            g["_is_deleted"] = False
        _tu = max(0, int(r.total_count or 0))
        _uu = min(_tu, max(0, int(r.used_count or 0)))
        g["_count"] += _tu
        g["_used"] += _uu
        cname = carrier_label(r.carrier)
        g["_carrier_map"][cname] += _tu
        g["_carrier_unused_map"][cname] += _tu - _uu
        if r.remarks and (not g["remarks"] or len(r.remarks) > len(g["remarks"] or "")):
            g["remarks"] = r.remarks
        if getattr(r, "batch_name", None) and not g["batch_name"]:
            g["batch_name"] = r.batch_name
        if getattr(r, "export_password_hash", None) and not g["export_password_hash"]:
            g["export_password_hash"] = r.export_password_hash
        if r.first_at:
            if g["_first_at"] is None or r.first_at < g["_first_at"]:
                g["_first_at"] = r.first_at
        if r.last_at:
            if g["_last_at"] is None or r.last_at > g["_last_at"]:
                g["_last_at"] = r.last_at

    items = []
    for g in groups.values():
        origins = g["_origins"]
        if ORIGIN_MANUAL in origins and ORIGIN_PURCHASED in origins:
            lo = "mixed"
        elif ORIGIN_MANUAL in origins:
            lo = "manual"
        else:
            lo = "purchased"
        _umap = g["_carrier_unused_map"]
        carriers = [
            {
                "name": n,
                "count": c,
                "unused_count": min(c, max(0, int(_umap.get(n, 0)))),
            }
            for n, c in sorted(g["_carrier_map"].items(), key=lambda x: -x[1])
        ]
        unused = max(0, g["_count"] - g["_used"])
        items.append(
            {
                "country_code": g["country_code"],
                "source": g["source"],
                "source_label": g["source"],
                "purpose": g["purpose"],
                "purpose_label": g["purpose"],
                "batch_id": g["batch_id"],
                "batch_name": g["batch_name"],
                "remarks": g["remarks"],
                "is_encrypted": bool(g["export_password_hash"]),
                "count": g["_count"],
                "used_count": g["_used"],
                "unused_count": unused,
                "carriers": carriers,
                "first_at": g["_first_at"].isoformat() if g["_first_at"] else None,
                "last_at": g["_last_at"].isoformat() if g["_last_at"] else None,
                "library_origin": lo,
                "is_deleted": g.get("_is_deleted", False),
            }
        )

    items.sort(key=lambda x: x["last_at"] or "", reverse=True)

    # 填充 source_label / purpose_label 由接口层用 SOURCE_LABELS 覆盖
    return {
        "success": True,
        "items": items,
        "total": int(total_all_accounts_hint if total_all_accounts_hint is not None else total),
        "meta": {
            "max_batches": max_batches,
            "truncated": bool(truncated_hint) if max_batches > 0 else False,
            "batch_card_limit": max_batches if max_batches > 0 else None,
        },
    }
