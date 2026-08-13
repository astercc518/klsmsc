"""
节点 RCS 群发的号码文件服务

节点上游要求 `numberUrl` 指向一个每行一个号码的 TXT，由上游主动来 HTTP 拉取。
这等于把客户号码库放到公网上，是本次接入最大的风险点，因此：

  - token 用 `secrets.token_urlsafe(32)`（≈256 bit），路径不可枚举
  - 有效期默认 48h（上游可能排队/审核后才拉，不能太短），过期即 410
  - 任务进入终态后主动清空内容（purge），不留在库里
  - 每次下载都记录时间/IP/次数，事后可审计到底被谁拉过几次

不落盘而存 DB：api 容器没有持久化卷，重启就丢；而文件必须活到上游来拉为止。
"""
import secrets
from datetime import datetime, timedelta
from typing import Iterable, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.sms.rcs_task import RCSNumberFile
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 上游可能在任务排队/人工审核结束后才来拉号码，给足冗余
DEFAULT_TTL_HOURS = 48
# token 熵：32 字节 → base64url 43 字符，不可枚举
_TOKEN_BYTES = 32


def build_txt(phones: Iterable[str]) -> tuple[str, int]:
    """把号码序列拼成上游要的 TXT：每行一个号码，去空去重且保序。

    节点没说要不要带 `+`。这里保留调用方给的形态（批次里存的是 E.164），
    若上游报 705「文件错误」再按其要求调整。
    """
    seen = set()
    lines = []
    for p in phones:
        s = str(p or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        lines.append(s)
    return "\n".join(lines), len(lines)


async def create_number_file(
    db: AsyncSession,
    phones: Iterable[str],
    channel_id: Optional[int] = None,
    batch_id: Optional[int] = None,
    ttl_hours: int = DEFAULT_TTL_HOURS,
) -> RCSNumberFile:
    """落一份号码文件，返回带 token 的行（调用方据此拼 URL）。"""
    content, count = build_txt(phones)
    if not count:
        raise ValueError("号码列表为空，无法生成 RCS 号码文件")

    row = RCSNumberFile(
        token=secrets.token_urlsafe(_TOKEN_BYTES),
        channel_id=channel_id,
        batch_id=batch_id,
        phone_count=count,
        content=content,
        expires_at=datetime.now() + timedelta(hours=ttl_hours),
    )
    db.add(row)
    await db.flush()
    logger.info(
        f"RCS 号码文件已生成: id={row.id} batch={batch_id} channel={channel_id} "
        f"条数={count} 有效期={ttl_hours}h"
    )
    return row


def public_url(token: str, base_url: Optional[str] = None) -> str:
    """拼出给上游的下载地址。"""
    from app.config import settings

    base = (base_url or getattr(settings, "PUBLIC_WEB_BASE_URL", "") or "").rstrip("/")
    return f"{base}/api/v1/rcs/numbers/{token}.txt"


async def purge_file(db: AsyncSession, file_id: int, reason: str = "task_final") -> None:
    """清空号码正文（任务终态或过期后调用）。保留行本身以便审计下载记录。"""
    if not file_id:
        return
    await db.execute(
        update(RCSNumberFile)
        .where(RCSNumberFile.id == file_id, RCSNumberFile.purged_at.is_(None))
        .values(content=None, purged_at=datetime.now())
    )
    logger.info(f"RCS 号码文件已清空: id={file_id} 原因={reason}")


async def purge_expired(db: AsyncSession, limit: int = 500) -> int:
    """清空已过期但仍留有正文的文件。由 beat 兜底调用。"""
    rows = (
        await db.execute(
            select(RCSNumberFile.id)
            .where(
                RCSNumberFile.expires_at < datetime.now(),
                RCSNumberFile.purged_at.is_(None),
                RCSNumberFile.content.isnot(None),
            )
            .limit(limit)
        )
    ).scalars().all()
    for fid in rows:
        await purge_file(db, fid, reason="expired")
    return len(rows)
