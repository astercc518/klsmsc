"""
注水触发器 - 供所有 DLR 处理入口（虚拟通道/HTTP拉取/SMPP/推送）统一调用

延迟分布模型：
  使用 Beta(1, curve) 分布替代均匀分布，模拟真实用户「先快后慢」的点击行为。
  curve=1.0 → 均匀分布（退化为旧逻辑）
  curve=4.0 → ~60% 点击集中在前 25% 时间窗口（推荐）
  curve=8.0 → ~80% 点击集中在前 15% 时间窗口
"""
import random
import logging
from typing import Optional, List, Tuple

logger = logging.getLogger(__name__)


def _calc_delay(delay_min: int, delay_max: int, curve: float) -> int:
    """
    根据 Beta(1, curve) 分布计算延迟秒数。
    curve 越大，分布越偏向 delay_min 一侧（大量点击发生在早期）。
    """
    if curve <= 1.0:
        return random.randint(delay_min, delay_max)
    raw = random.betavariate(1.0, curve)
    return int(delay_min + (delay_max - delay_min) * raw)


async def _resolve_water_url(db, url: str) -> str:
    """
    短链替换：若 url 命中 water_url_resolutions 表，返回人工解析后的真实落地页 URL。
    用于绕过 shorturl.at 等带 Cloudflare Interactive Challenge 的短链服务（headless 浏览器无法通过）。
    未命中则原样返回。命中计数由 worker 异步更新，不阻塞 DLR 主路径。
    """
    try:
        from sqlalchemy import text as _sa_text
        resolved = (await db.execute(
            _sa_text(
                "SELECT resolved_url FROM water_url_resolutions "
                "WHERE short_url = :u AND enabled = 1"
            ),
            {"u": url},
        )).scalar_one_or_none()
        if resolved:
            logger.info(f"短链替换: {url} -> {resolved}")
            return resolved
    except Exception as e:
        logger.warning(f"短链替换查询失败（按原 URL 投递）: {e}")
    return url


async def trigger_water_for_delivered(
    db,
    delivered_items: List[Tuple],
    channel_id: int = None,
    batch_id: int = None,
):
    """
    批量注水触发：对 delivered 消息按账户维度检查注水配置并调度点击任务。

    delivered_items: [(sms_log_id, message_text, country_code, account_id), ...]
    """
    try:
        from sqlalchemy import select
        from app.modules.water.models import WaterTaskConfig
        from app.utils.url_extractor import extract_urls
        from app.workers.celery_app import celery_app

        account_ids = set(item[3] for item in delivered_items if item[3])
        if not account_ids:
            return 0

        result = await db.execute(
            select(WaterTaskConfig).where(
                WaterTaskConfig.account_id.in_(list(account_ids)),
                WaterTaskConfig.enabled == True,
            )
        )
        configs = {cfg.account_id: cfg for cfg in result.scalars().all()}
        if not configs:
            return 0

        dispatched = 0
        for sms_log_id, message_text, sms_country_code, account_id in delivered_items:
            if not account_id or account_id not in configs:
                continue
            task_config = configs[account_id]

            if not message_text:
                continue
            urls = extract_urls(message_text)
            if not urls:
                continue

            click_rate = random.uniform(
                float(task_config.click_rate_min),
                float(task_config.click_rate_max),
            )
            if random.random() * 100 >= click_rate:
                continue

            url = urls[0]
            url = await _resolve_water_url(db, url)
            curve = float(getattr(task_config, 'click_delay_curve', 1.0) or 1.0)
            delay = _calc_delay(task_config.click_delay_min, task_config.click_delay_max, curve)

            async_result = celery_app.send_task(
                "web_click_task",
                args=[sms_log_id, url, channel_id or 0],
                kwargs={
                    "task_config_id": task_config.id,
                    "account_id": account_id,
                    "country_code": sms_country_code or "",
                    "proxy_id": task_config.proxy_id,
                    "ua_type": task_config.user_agent_type or "mobile",
                    "register_enabled": task_config.register_enabled,
                    "register_rate_min": float(task_config.register_rate_min),
                    "register_rate_max": float(task_config.register_rate_max),
                    "batch_id": batch_id,
                },
                queue="web_automation",
                countdown=delay,
            )
            tid = getattr(async_result, "id", None)
            if tid:
                from app.utils.water_task_tracking import track_water_task
                track_water_task(account_id, tid)
            dispatched += 1

        if dispatched:
            logger.info(
                f"注水调度: channel={channel_id}, batch={batch_id}, "
                f"accounts={list(configs.keys())}, dispatched={dispatched}/{len(delivered_items)}"
            )
        return dispatched

    except ImportError:
        return 0
    except Exception as e:
        logger.warning(f"注水触发异常（不影响DLR）: {e}")
        return 0


async def trigger_water_single(
    db,
    sms_log_id: int,
    message_text: str,
    country_code: str,
    account_id: int,
    channel_id: int = None,
):
    """
    单条注水触发：当一条短信被标记为 delivered 时调用。
    适用于实时 DLR（推送/SMPP）处理。
    """
    if not account_id or not message_text:
        return 0
    return await trigger_water_for_delivered(
        db,
        [(sms_log_id, message_text, country_code, account_id)],
        channel_id=channel_id,
    )
