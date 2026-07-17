"""
短链域名健康巡检 (Short-Link Domain Health Inspector)

背景：2026-07-06 主短链域 66c.eu 被域名注册商暂停，DNS 整域失效，系统闷头往死域发了
一整天打不开的短链才靠人工发现。本任务定期对每个 active 短链域做真实端到端探测（走公网
DNS + HTTPS 可达性），连续失败即**自动 disable 并告警**；被自动停用的域探测恢复后**自动
re-enable 并告警**。

停用即从发送侧移除：短链生成走 `short_link.resolve_effective_base`，会把内嵌的已停用域
自动故障转移到当前最优 active 域（见该函数），故本任务改状态后调用
`rebuild_active_domain_map` 立即刷新发送视图。

只处理两类域：① 当前 active 域（探测失败 → 停用）；② 曾被本任务自动停用的域（探测成功 →
恢复）。**人工停用的域不在恢复范围**（如 66c.eu 永久暂停，不做无谓的重启用尝试）。

阈值可用环境变量覆盖：
  SHORTLINK_PROBE_FAIL_THRESHOLD   连续失败几次判定停用（默认 3，配合 3min 周期≈9min 去抖）
  SHORTLINK_PROBE_RECOVER_THRESHOLD 连续成功几次判定恢复（默认 2）
  SHORTLINK_PROBE_TIMEOUT          单次探测超时秒（默认 8）
"""
import os

import httpx
from sqlalchemy import select

from app.workers.celery_app import celery_app
from app.workers.sms_worker import _make_session, _run_async
from app.services.notification_service import notification_service
from app.modules.sms.short_link_domain import ShortLinkDomain
from app.utils.short_link import rebuild_active_domain_map, _get_redis
from app.utils.logger import get_logger

logger = get_logger(__name__)

_FAIL_THRESHOLD = int(os.environ.get("SHORTLINK_PROBE_FAIL_THRESHOLD", "3"))
_RECOVER_THRESHOLD = int(os.environ.get("SHORTLINK_PROBE_RECOVER_THRESHOLD", "2"))
_TIMEOUT = float(os.environ.get("SHORTLINK_PROBE_TIMEOUT", "8"))

# CF「源站不可达」类状态码：edge 活着但回源失败 → 视为该域故障。
# 其余任何 HTTP 响应（含 200/403/404/503 challenge）都证明「域名解析+可达」，不判失败，
# 避免 CF 人机校验等误伤。整域 DNS 消失(如 66c.eu)会抛连接异常，被单独判失败。
_CF_ORIGIN_DOWN = {521, 522, 523, 524, 525, 526, 530}

_AUTODIS_KEY = "slh:autodis"     # set：被本任务自动停用、待探测恢复的 domain id


def _b2s(x):
    return x.decode() if isinstance(x, (bytes, bytearray)) else x


@celery_app.task(name='inspect_shortlink_domains_task')
def inspect_shortlink_domains_task():
    """每 3 分钟巡检短链域健康：失败自动停用+告警，恢复自动启用+告警。"""
    return _run_async(_do_inspect(), timeout=120)


async def _probe_domain(domain: str) -> tuple:
    """(ok, reason)。整域解析失败/连接超时/CF 源站不可达 → ok=False。"""
    url = f"https://{domain}/health"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, verify=False,
                                     follow_redirects=False) as client:
            resp = await client.get(url)
        if resp.status_code in _CF_ORIGIN_DOWN:
            return False, f"源站不可达 HTTP {resp.status_code}"
        return True, f"HTTP {resp.status_code}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


async def _do_inspect():
    eng, Session = _make_session()
    try:
        async with Session() as db:
            rows = (await db.execute(select(ShortLinkDomain))).scalars().all()
            r = await _get_redis()

            # 当前自动停用集合
            autodis_ids = set()
            try:
                raw = await r.smembers(_AUTODIS_KEY)
                autodis_ids = {int(_b2s(x)) for x in raw} if raw else set()
            except Exception as e:
                logger.debug(f"读取 autodis 集合失败: {e}")

            active_count = sum(1 for d in rows if d.status == "active")
            changed = False
            alerts = []
            probed = 0

            for d in rows:
                is_active = d.status == "active"
                is_autodis = d.id in autodis_ids
                if not is_active and not is_autodis:
                    continue  # 人工停用且非自动停用 → 不巡检（如 66c.eu 永久暂停）

                # 管理员已手工把自动停用域重新启用：清出 autodis，按 active 常规处理
                if is_active and is_autodis:
                    try:
                        await r.srem(_AUTODIS_KEY, str(d.id))
                    except Exception:
                        pass
                    is_autodis = False

                probed += 1
                ok, reason = await _probe_domain(d.domain)
                fail_key = f"slh:fail:{d.id}"
                ok_key = f"slh:ok:{d.id}"

                if is_active:
                    if ok:
                        await r.delete(fail_key)
                        continue
                    n = int(await r.incr(fail_key))
                    await r.expire(fail_key, 3600)
                    logger.warning(f"短链域 {d.domain} 探测失败({n}/{_FAIL_THRESHOLD}): {reason}")
                    if n < _FAIL_THRESHOLD:
                        continue
                    if active_count <= 1:
                        # 不停用最后一个 active 域（否则前端无可选域），仅高声告警
                        alerts.append(
                            f"🚨 *短链域全线告警*\n唯一 active 短链域 `{d.domain}` 连续"
                            f"{n} 次探测失败（{reason}），为避免无可用域**未自动停用**。"
                            f"请立即人工排查并尽快补入新的短链域！"
                        )
                        await r.delete(fail_key)
                    else:
                        d.status = "disabled"
                        changed = True
                        active_count -= 1
                        await r.sadd(_AUTODIS_KEY, str(d.id))
                        await r.delete(fail_key)
                        alerts.append(
                            f"⚠️ *短链域自动停用*\n`{d.domain}` 连续 {_FAIL_THRESHOLD} 次探测失败"
                            f"（{reason}），已自动停用；新发送短链将自动故障转移到其他健康域。"
                            f"恢复后会自动重新启用。"
                        )
                else:
                    # 自动停用域：探测恢复
                    if ok:
                        n = int(await r.incr(ok_key))
                        await r.expire(ok_key, 3600)
                        if n >= _RECOVER_THRESHOLD:
                            d.status = "active"
                            changed = True
                            active_count += 1
                            await r.srem(_AUTODIS_KEY, str(d.id))
                            await r.delete(ok_key)
                            alerts.append(
                                f"✅ *短链域已恢复*\n`{d.domain}` 探测恢复健康（{reason}），已自动重新启用。"
                            )
                    else:
                        await r.delete(ok_key)

            if changed:
                await db.commit()
                # 状态变了 → 立刻刷新发送侧故障转移视图
                try:
                    await rebuild_active_domain_map(db)
                except Exception as e:
                    logger.error(f"刷新 active 短链域映射失败: {e}")

            for a in alerts:
                try:
                    await notification_service.notify_admin_group(a)
                except Exception as e:
                    logger.error(f"短链域巡检告警发送失败: {e}")

            return {"probed": probed, "changed": changed, "alerts": len(alerts)}
    finally:
        await eng.dispose()
