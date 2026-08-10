"""
RCS 相关接口

1) 回执 Webhook 接收：POST /api/v1/rcs/dlr/{channel_code}
   叮咚 BoltTel 平台主动推送状态变更，HMAC 验签 + deliveryId 幂等去重，
   落回 sms_logs 走与其他通道一致的 DLR 处理链路（批次进度 / 客户 webhook / 注水）。

2) 管理端：余额查询、批次报告查询（对账兜底），仅管理员可见。
"""
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_admin
from app.core.dlr_handler import process_dlr_reports
from app.database import get_db
from app.modules.common.admin_user import AdminUser
from app.modules.sms.channel import Channel
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()
admin_router = APIRouter()

# deliveryId 去重键 TTL：上游默认最多重试约 6 次、间隔递增，3 天足够覆盖
_DEDUP_TTL_SEC = 3 * 24 * 3600

# 上游终态 → 本系统 DLR 语义。
# DELIVERED/READED 都计费且都表示已达终端；同一条消息可能先后收到两者，
# process_dlr_reports 只更新 sent/pending/queued，第二次自然被跳过。
_STATUS_MAP = {
    "DELIVERED": "DELIVRD",
    "READED": "DELIVRD",
    "UNDELIVERABLE": "UNDELIV",
    "REJECTED": "REJECTD",
    "EXPIRED": "EXPIRED",
    "SEND_FAILED": "UNDELIV",
}
# 非终态 / 非投递语义，不改 sms_logs
_STATUS_IGNORED = {"PENDING", "REPLY"}


async def _dedup_seen(delivery_id: str) -> bool:
    """按 deliveryId 幂等去重。返回 True 表示这条推送此前已处理过。

    跨进程键，必须直连 Redis（不能用带进程内 L1 的 cache manager）。
    Redis 不可用时 fail-open：宁可重复处理（下游本身幂等）也不能丢回执。
    """
    if not delivery_id:
        return False
    try:
        from app.utils.cache import get_redis_client

        redis = await get_redis_client()
        ok = await redis.set(f"rcs_dlr:{delivery_id}", b"1", ex=_DEDUP_TTL_SEC, nx=True)
        return not bool(ok)
    except Exception as e:
        logger.warning(f"RCS 回执去重检查失败(放行): deliveryId={delivery_id}, {e}")
        return False


def _to_report(item: dict) -> Optional[dict]:
    """把一条 RCS 推送体转成 dlr_handler 认识的 report 结构。"""
    status = str(item.get("status") or "").strip().upper()
    if not status or status in _STATUS_IGNORED:
        return None
    stat = _STATUS_MAP.get(status)
    if not stat:
        logger.warning(f"RCS 回执状态未识别: {status}, item={str(item)[:200]}")
        return None

    # messageId 与发送返回的 messageIds 一致，已写入 sms_logs.upstream_message_id；
    # clientRef 是我们的 message_id，dlr_handler 会在 upstream 匹配失败时自动兜底。
    message_id = item.get("messageId") or item.get("clientRef")
    if not message_id:
        return None

    return {
        "message_id": str(message_id),
        "mobile": item.get("phone"),
        "status_code": stat,
        # DELIVRD 时不能塞 errorCode：dlr_handler 的失败关键词会先命中 error 字段
        "error_code": (item.get("errorCode") or item.get("errorMsg") or "") if stat != "DELIVRD" else "",
        "delivery_time": item.get("eventTime"),
    }


@router.post("/rcs/dlr/{channel_code}")
async def rcs_dlr_webhook(
    channel_code: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    接收叮咚 BoltTel RCS 回执推送。

    - 验签：X-Rcs-Signature = HEX_LOWER(HMAC_SHA256(secret, 原始 body))，
      secret 配在通道 config_json.rcs.webhook_secret。
    - 幂等：按 X-Rcs-Delivery / body 里的 deliveryId 去重。
    - 单条推送 body 是对象，批量（pushBatchSize>1）是数组；对完整数组原文验签。
    - 上游要求 2xx 即成功，非 2xx 整包重试。
    """
    raw_body = await request.body()

    ch_res = await db.execute(
        select(Channel).where(
            Channel.channel_code == channel_code,
            Channel.is_deleted == False,  # noqa: E712
        )
    )
    channel = ch_res.scalar_one_or_none()
    if not channel:
        logger.warning(f"RCS 回执：未知通道 {channel_code}")
        return JSONResponse(status_code=404, content={"code": 1, "message": "unknown channel"})

    if str(channel.protocol).upper() != "RCS":
        logger.warning(f"RCS 回执：通道 {channel_code} 不是 RCS 协议")
        return JSONResponse(status_code=404, content={"code": 1, "message": "not an RCS channel"})

    from app.workers.adapters.rcs_adapter import get_rcs_adapter

    adapter = get_rcs_adapter(channel)
    if not adapter.webhook_secret:
        # 没配 secret 就无法验签。此时若放行，任何人都能伪造回执把未达改成已达。
        logger.error(
            f"RCS 通道 {channel_code} 未配置 webhook_secret，拒收回执。"
            f"请在通道扩展配置 rcs.webhook_secret 填入平台侧回执 secret"
        )
        return JSONResponse(status_code=403, content={"code": 1, "message": "webhook secret not configured"})

    signature = request.headers.get("X-Rcs-Signature")
    if not adapter.verify_webhook_signature(raw_body, signature):
        logger.warning(
            f"RCS 回执验签失败: channel={channel_code}, sig={signature!r}, len={len(raw_body)}"
        )
        return JSONResponse(status_code=403, content={"code": 1, "message": "bad signature"})

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as e:
        logger.warning(f"RCS 回执 body 非法 JSON: channel={channel_code}, {e}")
        return {"code": 0, "message": "ignored"}

    items: List[dict] = payload if isinstance(payload, list) else [payload]
    logger.info(f"收到 RCS 回执: channel={channel_code}, 条数={len(items)}")

    reports = []
    replies = 0
    duplicated = 0
    for item in items:
        if not isinstance(item, dict):
            continue

        delivery_id = str(item.get("deliveryId") or "").strip()
        if await _dedup_seen(delivery_id):
            duplicated += 1
            continue

        status = str(item.get("status") or "").strip().upper()
        if status == "REPLY":
            # 用户回复：不计费、不改投递状态。当前无入站消息表，先落日志留痕。
            replies += 1
            logger.info(
                f"RCS 用户回复: channel={channel_code}, phone={item.get('phone')}, "
                f"messageId={item.get('messageId')}, reply={str(item.get('reply'))[:200]}"
            )
            continue

        report = _to_report(item)
        if report:
            reports.append(report)

    if not reports:
        return {
            "code": 0,
            "message": "success",
            "processed": 0,
            "duplicated": duplicated,
            "replies": replies,
        }

    success, fail, _affected = await process_dlr_reports(
        reports, db, source=f"rcs-{channel_code}", channel_id=channel.id
    )
    logger.info(
        f"RCS 回执处理完成: channel={channel_code}, 送达={success}, 失败={fail}, "
        f"重复={duplicated}, 回复={replies}"
    )
    return {
        "code": 0,
        "message": "success",
        "processed": success + fail,
        "duplicated": duplicated,
        "replies": replies,
    }


# ── 管理端：余额 / 批次报告（对账兜底） ──────────────────────────────────────


async def _load_rcs_channel(db: AsyncSession, channel_id: int) -> Channel:
    res = await db.execute(select(Channel).where(Channel.id == channel_id))
    channel = res.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    if str(channel.protocol).upper() != "RCS":
        raise HTTPException(status_code=400, detail="不是 RCS 通道")
    return channel


@admin_router.get("/admin/rcs/channels/{channel_id}/balance")
async def rcs_channel_balance(
    channel_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """查询 RCS 上游账户余额（管理员专用，属上游内部信息，不得暴露给客户端）。"""
    channel = await _load_rcs_channel(db, channel_id)
    from app.workers.adapters.rcs_adapter import RCSConfigError, get_rcs_adapter

    try:
        result = await get_rcs_adapter(channel).get_balance()
    except RCSConfigError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"RCS 余额查询失败: channel={channel.channel_code}, {e}")
        raise HTTPException(status_code=502, detail="上游查询失败")
    return {"success": result.get("success", False), **result}


@admin_router.get("/admin/rcs/channels/{channel_id}/report")
async def rcs_batch_report(
    channel_id: int,
    batch_id: str,
    with_messages: bool = False,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """查询上游批次报告（对账兜底；轮询间隔建议 ≥60s，别当回执主通道用）。"""
    channel = await _load_rcs_channel(db, channel_id)
    from app.workers.adapters.rcs_adapter import RCSConfigError, get_rcs_adapter

    try:
        result = await get_rcs_adapter(channel).get_report(batch_id, with_messages)
    except RCSConfigError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"RCS 批次报告查询失败: channel={channel.channel_code}, batch={batch_id}, {e}")
        raise HTTPException(status_code=502, detail="上游查询失败")
    return {"success": result.get("success", False), **result}


@admin_router.get("/admin/rcs/channels/{channel_id}/webhook-url")
async def rcs_webhook_url(
    channel_id: int,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """返回该通道应在叮咚平台配置的回执 callbackUrl，便于管理员直接复制。"""
    channel = await _load_rcs_channel(db, channel_id)
    from app.config import settings

    base = (getattr(settings, "PUBLIC_WEB_BASE_URL", "") or "").rstrip("/")
    if not base:
        base = str(request.base_url).rstrip("/")
    cfg = channel.get_rcs_config()
    return {
        "success": True,
        "callback_url": f"{base}/api/v1/rcs/dlr/{channel.channel_code}",
        "secret_configured": bool(cfg.get("webhook_secret")),
        "events": "DELIVERED,READED,UNDELIVERABLE,REJECTED,EXPIRED,SEND_FAILED,REPLY",
    }
