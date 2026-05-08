"""
短链重定向路由

GET /s/{token}  — 无鉴权，公开访问
- Redis 热路径：缓存命中时 < 1ms 返回 302，不查 DB
- 点击计数通过 Celery 任务（webhook_tasks 队列）异步累加，主链路无锁等待
- IP/UA 异步记录，用于运营分析
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.utils.client_ip import get_client_ip
from app.utils.logger import get_logger
from app.utils.short_link import get_original_url_by_token, record_link_click

logger = get_logger(__name__)

router = APIRouter()


@router.get("/s/{token}", include_in_schema=False)
async def redirect_short_link(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """公开短链重定向接口，无需鉴权。"""
    # 简单校验：token 只允许 Base62 字符，防止路径注入
    if not token or not token.isalnum() or len(token) > 16:
        return JSONResponse(status_code=400, content={"error": "invalid token"})

    original_url = await get_original_url_by_token(token, db)
    if not original_url:
        return JSONResponse(status_code=404, content={"error": "not found"})

    # 异步点击计数（fire-and-forget，主路径不等待）
    try:
        client_ip = get_client_ip(request)
        user_agent = request.headers.get("User-Agent", "")[:512]
        record_link_click(token, client_ip, user_agent)
    except Exception as e:
        # 点击统计失败不影响重定向
        logger.warning(f"record_link_click dispatch failed: {e}")

    return RedirectResponse(url=original_url, status_code=302)
