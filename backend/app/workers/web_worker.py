"""
注水自动化 Worker：使用 Playwright 无头浏览器模拟点击和注册
"""
import asyncio
import os
import random
import re
import threading
import time
from typing import Optional, Dict
from datetime import datetime

from celery.exceptions import SoftTimeLimitExceeded
from celery.signals import worker_process_shutdown, worker_process_init
from app.workers.celery_app import celery_app
from app.utils.logger import get_logger
from app.workers.register_handlers import tk688, sp111, mxluck  # 注水注册专用 handler(TK688 孟加拉 / SP111 巴西 / MXLUCK 墨西哥)


# ---------- Playwright browser pool（进程级单例）----------
# 业务模式：每个 web_automation worker 子进程跑多个注水任务，每任务一个 BrowserContext。
# 旧实现每任务 launch 一次 Chromium（~150-200 MB），新实现共享一个 Browser 实例：
#   1. _get_browser() 懒加载，首个任务进来时 launch
#   2. 任务完成 context.close() 释放 page；Browser 保留供下个任务复用
#   3. 代理通过 new_context(proxy=...) 按任务设置（不是 browser 级）
#   4. worker_process_shutdown 时 close 干净
#
# 异常恢复：如果 browser 进程崩了（detached），下次 _get_browser() 重新 launch
_PW = None
_BROWSER = None
_BROWSER_LOCK = threading.Lock()


def _get_browser():
    """获取（或懒加载）进程内 Chromium 单例。代理通过 context 级别设置。"""
    global _PW, _BROWSER
    with _BROWSER_LOCK:
        # 健康检查：如果 browser 已 detached，需要重新 launch
        if _BROWSER is not None:
            try:
                # is_connected 能反映 browser 进程是否还活着
                if not _BROWSER.is_connected():
                    _BROWSER = None
            except Exception:
                _BROWSER = None

        if _BROWSER is None:
            # patchright:驱动层打补丁的 Playwright,抹掉 CDP Runtime.enable / navigator.webdriver
            # 等自动化泄漏,过 1win 的 Cloudflare jsd + CDA 指纹墙(点击+注册均走它)。API 与
            # playwright 完全兼容,设备模拟(UA/视口/is_mobile/touch)照常。
            from patchright.sync_api import sync_playwright
            if _PW is None:
                _PW = sync_playwright().start()
            _BROWSER = _PW.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            )
            logger.info(f"web_worker: patchright Chromium launched, pid={getattr(_BROWSER, 'pid', '?')}")
        return _BROWSER


def _close_browser():
    """worker_process_shutdown 时调用，清理浏览器进程"""
    global _PW, _BROWSER
    with _BROWSER_LOCK:
        if _BROWSER is not None:
            try:
                _BROWSER.close()
            except Exception:
                pass
            _BROWSER = None
        if _PW is not None:
            try:
                _PW.stop()
            except Exception:
                pass
            _PW = None

logger = get_logger(__name__)


def _apply_stealth(page):
    """反指纹由 patchright 驱动层内置补丁负责,此处不再叠加 playwright_stealth。

    patchright 官方明确警告:其它 stealth 插件(如 playwright_stealth)注入的 init 脚本会
    覆盖/破坏 patchright 的补丁、反而引入可被指纹识别的新特征。故保留空实现,
    仅作为各调用点的占位(避免改动调用方)。
    """
    return


# 注水省流量:点击注水只需加载落地页 DOM/JS 触发短链计数与打点,不需要图片/字体/媒体。
# 实测博彩落地页 ~61% 流量是装饰性图片(游戏缩图 webp),屏蔽后点击 5.5MB→1.9MB(省 65%),
# 且点击计数在 page.goto(短链) 的 301 跳转即服务端记录(早于任何图片),屏蔽不影响计数。
# 注意:仅用于点击注水;注册注水保持完整加载(屏蔽会掉注册成功率,且注册量占比小、失败更浪费)。
_WATER_BLOCK_MEDIA = os.getenv("WATER_BLOCK_MEDIA", "1").strip().lower() not in ("0", "false", "no", "off")
_WATER_BLOCK_TYPES = {"image", "media", "font"}


def _install_media_blocker(page):
    """在 page 上拦截图片/字体/媒体请求(省住宅代理流量)。best-effort,失败不影响主流程。
    受 env WATER_BLOCK_MEDIA 控制(默认开);若某落地页点击计数依赖 img 像素信标,设 0 关闭。"""
    if not _WATER_BLOCK_MEDIA:
        return
    def _handler(route):
        try:
            if route.request.resource_type in _WATER_BLOCK_TYPES:
                route.abort()
                return
        except Exception:
            pass
        try:
            route.continue_()
        except Exception:
            pass
    try:
        page.route("**/*", _handler)
    except Exception:
        pass


def _wait_through_cf(page, max_wait_ms: int = 25000):
    """检测并等待 Cloudflare Managed Challenge 自动通过（住宅 IP + stealth 通常 5-15s）"""
    deadline = time.time() + max_wait_ms / 1000
    while time.time() < deadline:
        try:
            title = (page.title() or "").lower()
        except Exception:
            break
        if "just a moment" in title or "checking your browser" in title:
            page.wait_for_timeout(1500)
            try:
                page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass
        else:
            break


_RUN_ASYNC_DEFAULT_TIMEOUT = float(os.getenv("WORKER_RUN_ASYNC_TIMEOUT_SEC", "60"))


def _run_async(coro, *, timeout: Optional[float] = None):
    """在 Celery worker 中安全执行异步协程（仅用于数据库操作）。
    超时保护：避免任一异步操作永久阻塞 ForkPoolWorker。
    """
    eff_timeout = timeout if timeout is not None else _RUN_ASYNC_DEFAULT_TIMEOUT
    loop = asyncio.new_event_loop()
    try:
        if eff_timeout and eff_timeout > 0:
            return loop.run_until_complete(asyncio.wait_for(coro, timeout=eff_timeout))
        return loop.run_until_complete(coro)
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


def _make_session():
    """创建独立数据库会话"""
    from app.config import settings
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    connect_timeout = int(os.getenv("WORKER_DB_CONNECT_TIMEOUT_SEC", "10"))
    read_timeout = int(os.getenv("WORKER_DB_READ_TIMEOUT_SEC", "30"))
    eng = create_async_engine(
        settings.SQLALCHEMY_DATABASE_URL,
        echo=False, pool_size=2, max_overflow=2, pool_pre_ping=True,
        connect_args={
            "connect_timeout": connect_timeout,
            "read_timeout": read_timeout,
        },
    )
    factory = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    return eng, factory


# ========== 随机 User-Agent 池 ==========
_MOBILE_UAS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.82 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.6312.99 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
]
_DESKTOP_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]


def _pick_user_agent(ua_type: str = "mobile") -> str:
    if ua_type == "desktop":
        return random.choice(_DESKTOP_UAS)
    elif ua_type == "random":
        return random.choice(_MOBILE_UAS + _DESKTOP_UAS)
    return random.choice(_MOBILE_UAS)


def _describe_device(ua: str, is_mobile: bool, viewport: dict = None) -> str:
    """从 UA + viewport 生成友好设备摘要，写入注水记录供前端展示。
    例：'移动端 · iPhone · iOS 17 · 390×844' / '桌面端 · Windows · Chrome'
    """
    ua = ua or ""
    parts = ["移动端" if is_mobile else "桌面端"]
    # 机型/系统
    if "iPhone" in ua:
        m = re.search(r"iPhone OS (\d+)", ua)
        parts.append("iPhone" + (f" · iOS {m.group(1)}" if m else ""))
    elif "iPad" in ua:
        parts.append("iPad")
    elif "Android" in ua:
        m = re.search(r"Android (\d+)", ua)
        dev = re.search(r";\s*([^;)]+?)\s*\)", ua)
        model = dev.group(1).strip() if dev else "Android"
        parts.append(model + (f" · Android {m.group(1)}" if m else ""))
    elif "Windows" in ua:
        parts.append("Windows")
    elif "Macintosh" in ua or "Mac OS X" in ua:
        parts.append("Mac")
    # 浏览器内核
    if "Chrome" in ua and "Edg" not in ua:
        parts.append("Chrome")
    elif "Version/" in ua and "Safari" in ua:
        parts.append("Safari")
    # 分辨率
    if viewport and viewport.get("width"):
        parts.append(f"{viewport['width']}×{viewport['height']}")
    return " · ".join(parts)


_COUNTRY_LOCALE_MAP = {
    "TH": ("th-TH", "Asia/Bangkok"),
    "BR": ("pt-BR", "America/Sao_Paulo"),
    "IN": ("hi-IN", "Asia/Kolkata"),
    "ID": ("id-ID", "Asia/Jakarta"),
    "PH": ("en-PH", "Asia/Manila"),
    "VN": ("vi-VN", "Asia/Ho_Chi_Minh"),
    "MY": ("ms-MY", "Asia/Kuala_Lumpur"),
    "US": ("en-US", "America/New_York"),
    "GB": ("en-GB", "Europe/London"),
    "DE": ("de-DE", "Europe/Berlin"),
}


def _get_locale_timezone(country_code: str) -> tuple:
    cc = (country_code or "").upper()
    return _COUNTRY_LOCALE_MAP.get(cc, ("en-US", "Asia/Bangkok"))


# ========== 数据库操作（异步） ==========

async def _create_click_log(factory, sms_log_id, account_id, channel_id, task_config_id,
                             url, proxy_id, country_code, batch_id=None):
    """创建点击日志并返回 (log_id, proxy_config)"""
    from app.modules.water.models import WaterInjectionLog
    from app.modules.sms.sms_log import SMSLog
    from app.utils.proxy_manager import get_proxy_for_country
    from sqlalchemy import select

    async with factory() as db:
        # 若未传 batch_id，从 sms_logs 查补
        if not batch_id and sms_log_id:
            row = (await db.execute(select(SMSLog.batch_id).where(SMSLog.id == sms_log_id))).scalar()
            if row:
                batch_id = row

        click_log = WaterInjectionLog(
            sms_log_id=sms_log_id, account_id=account_id, batch_id=batch_id,
            channel_id=channel_id, task_config_id=task_config_id, url=url,
            action='click', status='processing', proxy_id=proxy_id,
            proxy_country=country_code, created_at=datetime.now(),
        )
        db.add(click_log)
        await db.flush()
        log_id = click_log.id

        proxy_config = await get_proxy_for_country(db, country_code, proxy_id)
        await db.commit()
    return log_id, proxy_config


async def _create_register_log(factory, sms_log_id, account_id, channel_id, task_config_id,
                                url, proxy_id, country_code, batch_id=None):
    """创建注册日志并返回 (log_id, proxy_config, script)"""
    from app.modules.water.models import WaterInjectionLog, WaterRegisterScript
    from app.modules.sms.sms_log import SMSLog
    from app.utils.proxy_manager import get_proxy_for_country
    from sqlalchemy import select
    from urllib.parse import urlparse

    async with factory() as db:
        if not batch_id and sms_log_id:
            row = (await db.execute(select(SMSLog.batch_id).where(SMSLog.id == sms_log_id))).scalar()
            if row:
                batch_id = row

        reg_log = WaterInjectionLog(
            sms_log_id=sms_log_id, account_id=account_id, batch_id=batch_id,
            channel_id=channel_id, task_config_id=task_config_id, url=url,
            action='register', status='processing', proxy_id=proxy_id,
            proxy_country=country_code, created_at=datetime.now(),
        )
        db.add(reg_log)
        await db.flush()
        log_id = reg_log.id

        domain = urlparse(url).hostname or ""
        script = None
        if domain:
            # 按主域后缀匹配(应对随机子域轮换),命中多条取最具体(domain 最长)的一条
            from app.workers.jl_api_register import domain_candidates
            cands = domain_candidates(domain)
            result = await db.execute(
                select(WaterRegisterScript).where(
                    WaterRegisterScript.domain.in_(cands or [domain]),
                    WaterRegisterScript.enabled == True,
                )
            )
            scripts = result.scalars().all()
            script = max(scripts, key=lambda s: len(s.domain)) if scripts else None

        proxy_config = await get_proxy_for_country(db, country_code, proxy_id)
        await db.commit()

    script_data = None
    if script:
        import json
        try:
            steps = json.loads(script.steps) if isinstance(script.steps, str) else script.steps
        except (json.JSONDecodeError, TypeError):
            steps = []
        script_data = {"id": script.id, "name": script.name, "domain": script.domain, "steps": steps}

    return log_id, proxy_config, script_data


async def _update_log_status(factory, log_id: int, status: str, duration_ms: int = 0,
                              error_message: str = None, proxy_ip: str = None,
                              screenshot_path: str = None,
                              device_info: str = None, user_agent: str = None):
    """更新注水日志状态"""
    from sqlalchemy import update as sa_update
    from app.modules.water.models import WaterInjectionLog

    values = {"status": status, "duration_ms": duration_ms}
    if error_message:
        values["error_message"] = error_message
    if proxy_ip:
        values["proxy_ip"] = proxy_ip
    if screenshot_path:
        values["screenshot_path"] = screenshot_path
    if device_info:
        values["device_info"] = device_info
    if user_agent:
        values["user_agent"] = user_agent

    async with factory() as db:
        await db.execute(
            sa_update(WaterInjectionLog).where(WaterInjectionLog.id == log_id).values(**values)
        )
        await db.commit()


async def _attribute_short_link_click(factory, sms_log_id: int,
                                      client_ip: str = None, user_agent: str = None):
    """注水点击成功后，把这次真实 headless 访问归因到该消息的短链 token。

    背景：点击计数原本只靠短链域(如外部 66c.eu)重定向回流 record_link_click_task，
    但外域回流极不可靠(实测仅 ~15% 命中)，致 click_count 远低于成功点击数。
    这里在点击任务确实成功后，直接按 sms_log 的短链 token 记一条点击明细 + 累加
    click_count，与重定向同一套表结构。

    幂等：每个 sms_log 的 token 最多记一条注水点击——已存在点击明细(外域回流或重试
    已记)则跳过，避免重复计数。无短链(非营销宏消息)则静默跳过。
    """
    from sqlalchemy import select as _sel, update as _upd
    from app.modules.sms.short_link_log import ShortLinkLog
    from app.modules.sms.short_link_click import ShortLinkClick

    async with factory() as db:
        row = (await db.execute(
            _sel(ShortLinkLog.id, ShortLinkLog.token)
            .where(ShortLinkLog.sms_log_id == sms_log_id)
        )).first()
        if not row:
            return False
        sl_id, token = row
        exists = (await db.execute(
            _sel(ShortLinkClick.id)
            .where(ShortLinkClick.short_link_log_id == sl_id).limit(1)
        )).scalar_one_or_none()
        if exists:
            return False
        now = datetime.now()
        await db.execute(
            _upd(ShortLinkLog).where(ShortLinkLog.id == sl_id)
            .values(click_count=ShortLinkLog.click_count + 1, last_click_at=now)
        )
        db.add(ShortLinkClick(
            token=token, short_link_log_id=sl_id, clicked_at=now,
            client_ip=(client_ip or None) and str(client_ip)[:64],
            user_agent=(user_agent or "")[:512] or None,
            is_bot=False, bot_reason=None,
        ))
        await db.commit()
        return True


def _finalize_register_log(engine, factory, log_id, script_data, success, *args, **kwargs):
    """写注册终态 + 回写脚本计数 + dispose,全部在同一个事件循环内完成。

    必须同 loop:_db_sync 每次新建 loop 跑完即关,async engine 的连接池绑定首次使用的那个 loop,
    换 loop 复用同一 engine 会抛 'Event loop is closed' —— 计数器原先分两次 _db_sync 调用,
    因此每次注册收尾都异常(账号其实已建、日志已写 success,但任务返回 False 且计数永远不增)。
    *args/**kwargs 原样透传给 _update_log_status(status/duration/error_message/...)。
    """
    async def _run():
        await _update_log_status(factory, log_id, *args, **kwargs)
        if script_data and script_data.get("id"):
            await _increment_script_counter(factory, script_data["id"], success)
        await engine.dispose()

    _db_sync(_run())


async def _increment_script_counter(factory, script_id: int, success: bool):
    """更新脚本成功/失败计数"""
    from sqlalchemy import update as sa_update
    from app.modules.water.models import WaterRegisterScript
    field = WaterRegisterScript.success_count if success else WaterRegisterScript.fail_count
    async with factory() as db:
        await db.execute(
            sa_update(WaterRegisterScript)
            .where(WaterRegisterScript.id == script_id)
            .values({field.key: field + 1, "last_run_at": datetime.now()})
        )
        await db.commit()


# ========== Celery 生命周期 hook：浏览器池清理 ==========

@worker_process_shutdown.connect
def _cleanup_browser_on_shutdown(**kwargs):
    """worker 子进程回收前关闭浏览器，避免 Chromium 进程泄露"""
    try:
        _close_browser()
    except Exception as e:
        logger.warning(f"web_worker: shutdown 关闭浏览器异常: {e}")


# ========== Celery 任务 ==========

def _mark_processing_log_failed(sms_log_id: int, action: str, reason: str):
    """超时分支兜底：把对应 WaterInjectionLog 从 processing→failed，
    避免 Playwright 卡在 C 层时 Python 异常被吞掉、行永远停留 processing。"""
    try:
        from sqlalchemy import update as sa_update
        from app.modules.water.models import WaterInjectionLog
        eng, factory = _make_session()

        async def _do():
            async with factory() as db:
                await db.execute(
                    sa_update(WaterInjectionLog)
                    .where(
                        WaterInjectionLog.sms_log_id == sms_log_id,
                        WaterInjectionLog.action == action,
                        WaterInjectionLog.status == 'processing',
                    )
                    .values(status='failed', error_message=reason[:500])
                )
                await db.commit()
        _db_sync(_do())
        _db_sync(eng.dispose())
    except Exception as e:
        logger.warning(f"标记 WaterInjectionLog 失败状态异常: sms_log={sms_log_id} action={action} {e}")


@celery_app.task(name="web_click_task", bind=True, max_retries=1,
                 autoretry_for=(OSError, ConnectionError), retry_backoff=15,
                 soft_time_limit=180, time_limit=240)
def web_click_task(self, sms_log_id: int, url: str, channel_id: int,
                   task_config_id: int = None, account_id: int = None,
                   country_code: str = "",
                   proxy_id: int = None, ua_type: str = "mobile",
                   register_enabled: bool = False, register_rate_min: float = 1,
                   register_rate_max: float = 3, batch_id: int = None):
    """注水点击任务：使用 Playwright 同步 API 模拟浏览行为"""
    if account_id and self.request.id:
        from app.utils.water_task_tracking import untrack_water_task
        untrack_water_task(account_id, self.request.id)
    logger.info(f"注水点击开始: sms_log={sms_log_id}, account={account_id}, batch={batch_id}, url={url[:80]}")
    try:
        return _do_click_sync(
            sms_log_id, url, channel_id, task_config_id, account_id, country_code,
            proxy_id, ua_type, register_enabled, register_rate_min, register_rate_max,
            batch_id=batch_id
        )
    except SoftTimeLimitExceeded:
        logger.warning(f"注水点击软超时: sms_log={sms_log_id}")
        _mark_processing_log_failed(sms_log_id, 'click', 'soft_time_limit')
        return {"success": False, "error": "soft_time_limit"}


def _resolve_short_link(url: str):
    """跟随跳转把点击追踪短链(如 66c.eu/<token>)解析成真实落地 URL,并返回落地页 HTML。

    注册分流/脚本匹配/affiliate 提取全靠落地域(rztk6mpvx.com),但虚拟通道批次的消息宏
    只替换成短链 66c.eu/<token>(见 project_virtual_chunk_shortlink_clicks),裸短链 host=66c.eu
    匹配不到任何 merchant → 注册被错误地拖进浏览器路径并 260s 超时。这里一次 HTTP 跟随跳转
    取真实落地域(实测 66c.eu/<token> → www.rztk6mpvx.com/?affiliateCode=...),失败则原样返回。

    返回 (final_url, html):html 供 _looks_like_onewin 做内容识别(1win 马甲域会轮换,
    域名白名单常漏,落地页 meta(author/application-name=1win)远比域名稳定)。
    """
    import httpx
    from urllib.parse import urlparse
    raw = (url or "").split("|", 1)[0].strip()
    try:
        r = httpx.get(raw, follow_redirects=True, verify=False, timeout=12.0,
                      headers={"User-Agent": (
                          "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                          "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Safari/604.1")})
        final = str(r.url)
        html = ""
        try:
            html = r.text or ""
        except Exception:
            html = ""
        if urlparse(final).hostname:
            return final, html
        return url, html
    except Exception as e:
        logger.warning(f"短链解析失败,沿用原 url: {raw[:80]} ({type(e).__name__}: {e})")
    return url, ""


# 1win 落地页内容指纹(比轮换的马甲域稳定):品牌 meta + 注册微前端模块 + 专属 CDN。
# 命中任一即判为 1win 系,走 _do_register_1win 专用表单路径,无需把新马甲域加进白名单。
_ONEWIN_CONTENT_MARKERS = (
    'name="author" content="1win"',
    'name="application-name" content="1win"',
    'apple-mobile-web-app-title" content="1win"',
    '"paywidget":',          # importmap 里 1win 的注册支付微前端模块
    'bundlecdn.com',
    'bundlecda.com',
)


def _looks_like_onewin(html: str) -> bool:
    """按落地页内容特征判断是否 1win 系(域名白名单漏掉的新马甲域兜底)。"""
    if not html:
        return False
    h = re.sub(r"\s+", " ", html).lower()
    return any(m.lower() in h for m in _ONEWIN_CONTENT_MARKERS)


# ========== 1win 系博彩注册（浏览器表单） ==========
# 1win 落地页(如 1wzbzs.life)是 Cloudflare 防护的 Vue SPA,与 wps 平台(rztk6mpvx/in1.fun)
# 完全不同:无逆向出的直连 API,且注册体强依赖浏览器实时算的 fingerprint。故走浏览器表单。
# 关键约束:
#   1) 必须经"目标国"住宅代理出口,否则站点弹"区域受限"弹窗,根本不渲染注册表单。
#   2) 表单 = 国码电话(撞库:填该消息真实收信号) + 密码(≥8) + 协议勾选;填手机号不触发 OTP,提交即建号。
#   3) 域名会轮换 → 用 WATER_ONEWIN_DOMAINS 环境变量(逗号分隔,后缀匹配)维护当前落地主域。
_ONEWIN_DOMAINS = [
    d.strip().lower().strip(".")
    for d in os.getenv("WATER_ONEWIN_DOMAINS", "1wzbzs.life").split(",")
    if d.strip()
]

# 国家 ISO2 → 国际区号(用于把 E.164 收信号去掉区号,填进表单"国码+本地号"控件的本地号位)
_DIAL_CODES = {
    "TH": "66", "BD": "880", "IN": "91", "ID": "62", "PH": "63", "VN": "84",
    "MY": "60", "PK": "92", "MM": "95", "KH": "855", "LA": "856", "NP": "977",
    "LK": "94", "BR": "55", "NG": "234", "EG": "20", "TR": "90",
}


def _onewin_host(host: str) -> bool:
    """host 是否属于 1win 系落地域(精确或子域后缀匹配)。匹配不到返回 False。"""
    host = (host or "").lower().strip(".")
    if not host:
        return False
    for dom in _ONEWIN_DOMAINS:
        if host == dom or host.endswith("." + dom):
            return True
    return False


def _to_national_number(phone: str, country_code: str) -> str:
    """E.164 收信号 → 表单本地号(去国际区号与前导 0)。
    例:TH +66822851805 → 822851805;BD 8801712345678 → 1712345678。"""
    d = re.sub(r"\D", "", phone or "")
    cc = _DIAL_CODES.get((country_code or "").upper())
    if cc and d.startswith(cc):
        d = d[len(cc):]
    return d.lstrip("0")


def _gen_1win_password() -> str:
    """1win 密码:8-14 位,含大小写+数字(拟人,复用 jl 词库生成器,不足 8 位补数字)。"""
    import string as _string
    from app.workers.jl_api_register import _gen_password
    p = _gen_password()
    while len(p) < 8:
        p += random.choice(_string.digits)
    return p[:14]


def _gen_1win_email() -> str:
    """生成拟人随机邮箱(1win 注册表单 email 必填,无需收件验证)。"""
    import string as _string
    user = "".join(random.choice(_string.ascii_lowercase) for _ in range(random.randint(6, 10)))
    user += str(random.randint(2, 9999))
    dom = random.choice(["gmail.com", "outlook.com", "hotmail.com", "yahoo.com", "icloud.com"])
    return f"{user}@{dom}"


# 提交前注入:预挂钩 window.initGeetest4(SDK 在点提交后才加载,用 defineProperty 拦截其赋值),
# 捕获 captcha 实例、captchaId 与站点注册成功回调,存到 window.__gt4。
_GEETEST_HOOK_JS = """() => {
  if (window.__gt4hooked) return;
  window.__gt4hooked = true;
  window.__gt4 = {};
  let _real = undefined;
  function _wrapped(config, cb) {
    try { window.__gt4.captchaId = config && (config.captchaId || config.captcha_id); } catch(e){}
    return _real(config, function(captcha) {
      window.__gt4.captcha = captcha;
      try {
        const _orig = captcha.onSuccess.bind(captcha);
        captcha.onSuccess = function(fn){ window.__gt4.successCb = fn; return _orig(fn); };
      } catch(e){ window.__gt4.err2 = String(e); }
      return cb(captcha);
    });
  }
  try {
    Object.defineProperty(window, 'initGeetest4', {
      configurable: true,
      get() { return _real ? _wrapped : _real; },
      set(v) { _real = v; }
    });
  } catch(e) { window.__gt4.err = String(e); }
}"""

# 解出凭证后注入:覆盖 getValidate 返回 CapSolver 凭证,并触发站点成功回调 → 站点自动提交注册。
_GEETEST_INJECT_JS = """(validate) => {
  const g = window.__gt4 || {};
  if (!g.captcha) return 'no-captcha';
  try { g.captcha.getValidate = function(){ return validate; }; }
  catch(e){ return 'override-failed:' + e; }
  if (typeof g.successCb === 'function') {
    try { g.successCb(validate); return 'fired-cb'; } catch(e){ return 'cb-error:' + e; }
  }
  return 'no-cb';
}"""


def _solve_and_inject_geetest(page, website_url):
    """等 GeeTest 弹出→取 captchaId→CapSolver 解→注入凭证触发注册。返回 (ok, reason)。"""
    captcha_id = None
    deadline = time.time() + 25
    while time.time() < deadline:
        try:
            captcha_id = page.evaluate("()=> (window.__gt4 && window.__gt4.captchaId) || null")
        except Exception:
            captcha_id = None
        if captcha_id:
            break
        page.wait_for_timeout(800)
    if not captcha_id:
        return False, "未捕获 GeeTest captchaId(可能未触发验证码)"
    from app.workers.geetest_solver import solve_geetest_v4
    val = solve_geetest_v4(captcha_id, website_url)
    if not val:
        return False, "CapSolver 未解出 GeeTest"
    # GeeTest getValidate() 期望 snake_case;CapSolver 返回即是该结构
    validate = {k: val.get(k) for k in
                ("lot_number", "captcha_output", "pass_token", "gen_time") if val.get(k) is not None}
    validate["captcha_id"] = val.get("captcha_id") or captcha_id
    if val.get("risk_type"):
        validate["risk_type"] = val["risk_type"]
    try:
        res = page.evaluate(_GEETEST_INJECT_JS, validate)
    except Exception as e:
        return False, f"GeeTest 注入异常: {e}"
    logger.info(f"1win GeeTest 注入结果: {res}")
    return (res == "fired-cb"), f"geetest:{res}"


def _safe_query_selector(page, selector, retries=4, wait_ms=1200):
    """query_selector,容忍 SPA 客户端导航致"执行上下文被销毁"(重试),返回元素或 None。

    1win 落地页 goto 后常再做一次客户端跳转(?p=xxx→区域化路径),此刻 query_selector
    会抛 "Execution context was destroyed, most likely because of a navigation"。
    """
    for _ in range(retries):
        try:
            return page.query_selector(selector)
        except Exception as e:
            if "Execution context" in str(e) or "navigation" in str(e):
                try:
                    page.wait_for_timeout(wait_ms)
                except Exception:
                    pass
                continue
            return None
    try:
        return page.query_selector(selector)
    except Exception:
        return None


def _do_register_1win(sms_log_id, url, channel_id, task_config_id, account_id,
                      country_code, proxy_id, batch_id=None):
    """1win 系博彩注册:经目标国代理驱动浏览器表单建号(撞库电话,无 OTP)。"""
    import time as _time
    from urllib.parse import urlparse
    eng, factory = _make_session()
    start = _time.time()
    log_id = None
    detected_ip = None
    ua = None
    device_desc = None
    try:
        log_id, proxy_config, script_data = _db_sync(
            _create_register_log(factory, sms_log_id, account_id, channel_id,
                                 task_config_id, url, proxy_id, country_code, batch_id=batch_id)
        )
        _db_sync(eng.dispose())

        # 1) 无代理则直接放弃:无目标国出口必被地域拦截,表单不渲染。
        if not proxy_config:
            _db_sync(_update_log_status(_make_session()[1], log_id, 'failed',
                                        int((_time.time() - start) * 1000),
                                        '1win 注册需目标国住宅代理,未取到可用代理',
                                        device_info='1win'))
            logger.warning(f"1win 注册放弃: sms_log={sms_log_id} 无代理(country={country_code})")
            return {"success": False, "error": "no_proxy"}

        # 2) 撞库:取真实收信号 → 表单本地号
        phone = None
        try:
            _e3, _f3 = _make_session()
            phone = _db_sync(_fetch_sms_phone(_f3, sms_log_id))
            _db_sync(_e3.dispose())
        except Exception:
            phone = None
        national = _to_national_number(phone, country_code)
        if not national:
            _db_sync(_update_log_status(_make_session()[1], log_id, 'failed',
                                        int((_time.time() - start) * 1000),
                                        f'无有效收信号可撞库: {phone}', device_info='1win'))
            return {"success": False, "error": "no_phone"}
        password = _gen_1win_password()
        email = ""

        # 3) 浏览器表单
        browser = _get_browser()
        ua = _pick_user_agent("mobile")
        viewport = {"width": 390, "height": 844}
        device_desc = _describe_device(ua, True, viewport)
        locale, tz = _get_locale_timezone(country_code)
        ctx_kwargs = {
            "user_agent": ua, "viewport": viewport, "locale": locale, "timezone_id": tz,
            "screen": dict(viewport), "device_scale_factor": 3, "is_mobile": True, "has_touch": True,
            "proxy": proxy_config,
        }
        context = browser.new_context(**ctx_kwargs)
        captured = {}

        def _on_resp(resp):
            try:
                u = resp.url
                # 真实注册端点是 MS-AUTH 系(如 /api/MS-AUTH/register/v2),旧的 /auth/register 兜底保留。
                # captcha-isEnabled 是验证码探测,非注册结果,排除。
                is_reg = ("captcha-isenabled" not in u.lower()) and (
                    "/auth/register" in u
                    or ("ms-auth" in u.lower() and "regist" in u.lower())
                )
                if is_reg:
                    captured["status"] = resp.status
                    captured["url"] = u
                    try:
                        captured["body"] = (resp.text() or "")[:600]
                    except Exception:
                        captured["body"] = ""
            except Exception:
                pass

        success = False
        try:
            page = context.new_page()
            _apply_stealth(page)
            page.on("response", _on_resp)

            # 出口 IP 探测(best-effort)
            try:
                ip_page = context.new_page()
                _apply_stealth(ip_page)
                ip_page.goto("https://api.ipify.org?format=text", timeout=8000)
                m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", ip_page.content() or "")
                detected_ip = m.group(1) if m else None
                ip_page.close()
            except Exception:
                detected_ip = None

            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            _wait_through_cf(page)
            page.wait_for_timeout(random.randint(3500, 5500))
            # SPA 落地后常再做一次客户端跳转,先等网络静默让导航落定,避免随后探测撞上下文销毁
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass

            # 注册表单常随落地自动弹;若没有电话输入框,主动点"注册"打开弹窗(多语言兜底)
            if not _safe_query_selector(page, "input[type=tel]"):
                for label in ("ลงทะเบียน", "Register", "Daftar", "Registrasi",
                              "Sign up", "Đăng ký", "Регистрация", "注册"):
                    try:
                        page.get_by_text(label, exact=True).first.click(timeout=3500)
                        break
                    except Exception:
                        continue
                page.wait_for_timeout(3000)

            tel = _safe_query_selector(page, "input[type=tel]")
            if not tel:
                # 多半是被地域拦截(代理出口非目标国)→ 取弹窗文案辅助排查
                blk = ""
                try:
                    blk = page.evaluate(
                        "()=>{const m=document.querySelector('[data-testid=modal-layout]');"
                        "return m?(m.innerText||'').slice(0,120):''}") or ""
                except Exception:
                    pass
                raise RuntimeError(f"未找到电话输入框(疑似地域拦截/代理非目标国): {blk[:100]}")

            tel.click()
            tel.type(national, delay=random.randint(50, 110))
            # 邮箱必填:不填则提交按钮校验不过、不触发注册请求(无需收件验证)
            email = email or _gen_1win_email()
            ef = _safe_query_selector(page, "input[type=email]")
            if ef:
                try:
                    ef.click()
                    ef.type(email, delay=random.randint(40, 90))
                except Exception:
                    try:
                        ef.fill(email)
                    except Exception:
                        pass
            pwf = _safe_query_selector(page, "input[type=password]")
            if pwf:
                pwf.fill(password)
            # 勾选所有协议复选框(自定义组件:真 input 可能隐藏,force 点击)
            for cb in page.query_selector_all("input[type=checkbox]"):
                try:
                    if not cb.is_checked():
                        cb.click(force=True)
                except Exception:
                    pass
            page.wait_for_timeout(random.randint(700, 1300))

            # 提交前预挂钩 GeeTest(SDK 在点提交后才加载)
            try:
                page.evaluate(_GEETEST_HOOK_JS)
            except Exception as _he:
                logger.warning(f"1win GeeTest 挂钩失败: {_he}")

            # 提交:弹窗内 submit 按钮优先
            btn = (page.query_selector("[data-testid=modal-layout] button[type=submit]")
                   or page.query_selector("button[type=submit]"))
            if btn:
                try:
                    btn.click(force=True)
                except Exception:
                    pass
            else:
                for label in ("ลงทะเบียน", "Register", "Daftar", "Đăng ký", "Регистрация"):
                    try:
                        page.get_by_role("button", name=label).last.click(timeout=3000, force=True)
                        break
                    except Exception:
                        continue

            # 注册门有 GeeTest v4:解码并注入凭证触发注册(无验证码时快速返回,不阻塞)
            try:
                gt_ok, gt_reason = _solve_and_inject_geetest(page, url)
                if gt_reason and "未捕获" not in gt_reason:
                    logger.info(f"1win GeeTest: {gt_reason} sms_log={sms_log_id}")
            except Exception as _ge:
                logger.warning(f"1win GeeTest 处理异常: {_ge}")

            # 等注册响应回来(最多 ~16s)
            for _ in range(20):
                page.wait_for_timeout(800)
                if captured.get("status"):
                    break
            page.wait_for_timeout(1500)

            if captured.get("status") and 200 <= captured["status"] < 300:
                success = True
            elif not captured.get("status"):
                # 没截到响应(可能 SPA 内部 fetch 早于监听或被合并)→ 退回页面信号判定
                success = _check_register_success(page, url)
        finally:
            try:
                context.close()
            except Exception:
                pass

        duration = int((_time.time() - start) * 1000)
        eng2, factory2 = _make_session()
        if success:
            login = "+" + re.sub(r"\D", "", phone or "")
            creds = (f"账号(手机) {login} ┊ 邮箱 {email} ┊ 密码 {password} ┊ 1win @ "
                     f"{urlparse(url).hostname} ┊ exit {detected_ip}")
            _finalize_register_log(eng2, factory2, log_id, script_data, True,
                                   'success', duration, proxy_ip=detected_ip,
                                   device_info=creds[:255], user_agent=ua)
            logger.info(f"1win 注册成功: sms_log={sms_log_id}, login={login}, pwd={password}, "
                        f"status={captured.get('status')}, {duration}ms")
        else:
            err = (f"1win 注册未成功 status={captured.get('status')} "
                   f"{(captured.get('body') or '')[:160]}")
            _finalize_register_log(eng2, factory2, log_id, script_data, False,
                                   'failed', duration, err[:500], proxy_ip=detected_ip,
                                   device_info=device_desc, user_agent=ua)
            logger.warning(f"1win 注册失败: sms_log={sms_log_id}, {err}")
        return {"success": success, "log_id": log_id}
    except SoftTimeLimitExceeded:
        logger.warning(f"1win 注册软超时: sms_log={sms_log_id}")
        _mark_processing_log_failed(sms_log_id, 'register', '1win_soft_time_limit')
        return {"success": False, "error": "soft_time_limit"}
    except Exception as e:
        logger.error(f"1win 注册异常: sms_log={sms_log_id}, {e}", exc_info=True)
        _mark_processing_log_failed(sms_log_id, 'register', f'1win_error: {str(e)[:200]}')
        return {"success": False, "error": str(e)[:200]}


@celery_app.task(name="web_register_task", bind=True, max_retries=1,
                 autoretry_for=(OSError, ConnectionError), retry_backoff=15,
                 soft_time_limit=200, time_limit=260)
def web_register_task(self, sms_log_id: int, url: str, channel_id: int,
                      task_config_id: int = None, account_id: int = None,
                      country_code: str = "",
                      proxy_id: int = None, ua_type: str = "mobile",
                      click_log_id: int = None, batch_id: int = None,
                      register_handler: str = ""):
    """注水注册任务：使用 Playwright 同步 API 模拟注册"""
    if account_id and self.request.id:
        from app.utils.water_task_tracking import untrack_water_task
        untrack_water_task(account_id, self.request.id)
    try:
        # 手动指定注册脚本/handler:优先入参,否则按 task_config_id 查注水配置(注水配置里按账户选)。
        # 从配置读避免层层透传 register_handler(不动高流量点击链路)。非空则直接路由,跳过自动识别。
        rh = (register_handler or "").strip().lower()
        if not rh and task_config_id:
            try:
                _rhe, _rhf = _make_session()
                rh = (_db_sync(_fetch_register_handler(_rhf, task_config_id)) or "").strip().lower()
                _db_sync(_rhe.dispose())
            except Exception:
                rh = ""
        logger.info(f"注水注册开始: sms_log={sms_log_id}, account={account_id}, batch={batch_id}, "
                    f"handler={rh or 'auto'}, url={url[:80]}")
        if rh == "api":
            return _do_register_via_api(sms_log_id, url, channel_id, task_config_id,
                                        account_id, country_code, proxy_id, batch_id=batch_id)
        if rh == "onewin":
            return _do_register_1win(sms_log_id, url, channel_id, task_config_id,
                                     account_id, country_code, proxy_id, batch_id=batch_id)
        if rh in ("tk688", "sp111", "mxluck", "generic"):
            return _do_register_sync(sms_log_id, url, channel_id, task_config_id, account_id,
                                     country_code, proxy_id, ua_type, click_log_id,
                                     batch_id=batch_id, force_handler=rh)
        # 直连注册 API 域名(如 in1.fun→jilievobdt 博彩SPA):页面反自动化把浏览器拖到200s超时,
        # 改走逆向出的加密注册接口,直接建号,快且稳。
        from urllib.parse import urlparse
        from app.workers.jl_api_register import merchant_for_host, looks_like_white_label
        host = urlparse(url).hostname or ""
        landing_html = ""
        # 裸短链(66c.eu/<token>、cutt.ly/<id>)匹配不到任何已知落地域 → 先跟随跳转解析真实落地域,
        # 让 merchant/1win/脚本/affiliate 都能命中,避免被错误拖进通用浏览器路径而超时。
        # 顺带取落地页 HTML 供内容识别 1win 马甲域(域名会轮换,白名单常漏)。
        if not merchant_for_host(host) and not _onewin_host(host):
            resolved, landing_html = _resolve_short_link(url)
            if resolved and resolved != url:
                logger.info(f"短链解析: {url[:60]} -> {resolved[:80]}")
                url = resolved
                host = urlparse(url).hostname or ""
        # 域名未登记时用落地页内容指纹兜底:该白标每个推广活动都换一个新的中间营销域
        # (7aa88/7aa69/7aa65/7aa13.vip ...),白名单穷举不过来,漏一个就掉进浏览器引擎白跑200s。
        if not merchant_for_host(host) and looks_like_white_label(landing_html):
            logger.info(f"内容识别为白标注册站(域名 {host} 不在白名单)→ 走直连注册 API")
            return _do_register_via_api(
                sms_log_id, url, channel_id, task_config_id, account_id,
                country_code, proxy_id, batch_id=batch_id
            )
        if merchant_for_host(host):
            return _do_register_via_api(
                sms_log_id, url, channel_id, task_config_id, account_id,
                country_code, proxy_id, batch_id=batch_id
            )
        # 1win 系博彩(必须经目标国住宅代理;表单=国码电话(撞库)+密码+协议,无 OTP,提交即建号)
        # 域名白名单 或 落地页内容特征命中即走专用路径——后者兜住未及时入白名单的新马甲域。
        if _onewin_host(host) or _looks_like_onewin(landing_html):
            if not _onewin_host(host):
                logger.info(f"内容识别为 1win 落地页(域名 {host} 不在白名单)→ 走专用注册路径")
            return _do_register_1win(
                sms_log_id, url, channel_id, task_config_id, account_id,
                country_code, proxy_id, batch_id=batch_id
            )
        return _do_register_sync(
            sms_log_id, url, channel_id, task_config_id, account_id, country_code,
            proxy_id, ua_type, click_log_id, batch_id=batch_id
        )
    except SoftTimeLimitExceeded:
        logger.warning(f"注水注册软超时: sms_log={sms_log_id}")
        _mark_processing_log_failed(sms_log_id, 'register', 'soft_time_limit')
        return {"success": False, "error": "soft_time_limit"}


@celery_app.task(name="test_register_handler_task", bind=True,
                 soft_time_limit=180, time_limit=210)
def test_register_handler_task(self, handler_key: str = "", domain: str = "",
                               country: str = "", script_id: int = None):
    """后台「测试运行」:用指定 handler/DB脚本在其域名真跑一次注册,返回成败+落地页。

    浏览器 handler(tk688/sp111/generic/DB脚本)直接驱动页面并返回结果(不写注水统计日志);
    onewin/api 依赖真实收信号撞库,测试仅提示改用真实批次验证。geo 站需在 country 填国家。
    """
    import json as _json
    url = domain if str(domain).startswith("http") else f"https://{(domain or '').strip()}"
    logger.info(f"测试运行注册: handler={handler_key or 'auto'}, script_id={script_id}, url={url[:80]}, country={country}")
    try:
        from app.workers.register_handlers import tk688, sp111, mxluck
        hk = (handler_key or "").strip().lower()
        if hk in ("onewin", "api"):
            return {"success": None, "reason": f"{hk} 类型依赖真实收信号撞库,无法离线测试;请用真实批次验证"}

        eng, factory = _make_session()

        async def _g():
            from app.utils.proxy_manager import get_proxy_for_country
            async with factory() as db:
                return await get_proxy_for_country(db, country or "", None)
        proxy = _db_sync(_g())
        _db_sync(eng.dispose())
        if proxy and "{country}" in _json.dumps(proxy):
            proxy = None  # 空国家占位符残留 → 直连(geo 站会失败,提示填国家)

        browser = _get_browser()
        ck = {"user_agent": _pick_user_agent("mobile"), "viewport": {"width": 390, "height": 844},
              "is_mobile": True, "has_touch": True, "device_scale_factor": 3, "locale": "en-US"}
        if proxy:
            ck["proxy"] = proxy
        ctx = browser.new_context(**ck)
        page = ctx.new_page()
        try:
            _apply_stealth(page)
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            _wait_through_cf(page)
            page.wait_for_timeout(4000)
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            landing = page.url
            if hk == "tk688":
                ok, reason = tk688.register(page, country, phone="")
            elif hk == "sp111":
                ok, reason = sp111.register(page, country, phone="")
            elif hk == "mxluck":
                ok, reason = mxluck.register(page, country, phone="")
            elif script_id:
                e2, f2 = _make_session()

                async def _s():
                    from sqlalchemy import select as _sel
                    from app.modules.water.models import WaterRegisterScript
                    async with f2() as db:
                        return (await db.execute(
                            _sel(WaterRegisterScript.steps).where(WaterRegisterScript.id == script_id)
                        )).scalar()
                raw = _db_sync(_s())
                _db_sync(e2.dispose())
                steps = _json.loads(raw) if isinstance(raw, str) else raw
                ok = _execute_script_steps(page, steps)
                reason = "ok" if ok else "脚本未跑通(检查选择器/成功判断)"
            else:
                ok, reason = _auto_register(page, url, country)
            return {"success": bool(ok), "reason": reason, "landing": landing}
        finally:
            try:
                ctx.close()
            except Exception:
                pass
    except SoftTimeLimitExceeded:
        return {"success": False, "reason": "测试超时(站点慢/反爬严重/geo站未填国家)"}
    except Exception as e:
        logger.error(f"测试运行异常: {e}", exc_info=True)
        return {"success": False, "reason": str(e)[:200]}


@celery_app.task(name="generate_register_script_task", bind=True,
                 soft_time_limit=180, time_limit=210)
def generate_register_script_task(self, url: str, country: str = ""):
    """后台"只填名称+目标站自动生成注册脚本":跑站点探针 → 产出配置脚本/脚手架/无法自动化判定。

    在带浏览器的 worker(web_automation 队列)执行,结果经 Celery result backend 回传给 API 轮询。
    """
    logger.info(f"自动生成注册脚本: url={url[:80]}, country={country}")
    try:
        from app.workers.register_handlers import site_profiler
        return site_profiler.generate(url, country_code=country or "", save=False)
    except SoftTimeLimitExceeded:
        return {"kind": "failed", "note": "探测超时(目标站太慢/反爬严重),请重试或改用手工配置"}
    except Exception as e:
        logger.error(f"自动生成注册脚本异常: {e}", exc_info=True)
        return {"kind": "failed", "note": f"生成异常: {str(e)[:200]}"}


async def _fetch_register_handler(factory, task_config_id):
    """取该注水配置手动指定的注册脚本/handler(''=自动识别)。"""
    from sqlalchemy import select as _select
    from app.modules.water.models import WaterTaskConfig
    async with factory() as db:
        return (await db.execute(
            _select(WaterTaskConfig.register_handler).where(WaterTaskConfig.id == task_config_id)
        )).scalar()


async def _fetch_sms_phone(factory, sms_log_id):
    """取该 sms_log 的收信号码(用于撞库派生用户名)。"""
    from sqlalchemy import select as _select
    from app.modules.sms.sms_log import SMSLog
    async with factory() as db:
        return (await db.execute(_select(SMSLog.phone_number).where(SMSLog.id == sms_log_id))).scalar()


def _do_register_via_api(sms_log_id, url, channel_id, task_config_id, account_id,
                         country_code, proxy_id, batch_id=None):
    """直连加密注册接口建号(无浏览器)。复用注册日志/代理获取,写终态。"""
    import time as _time
    from app.workers.jl_api_register import register_via_api, phone_to_username
    eng, factory = _make_session()
    start = _time.time()
    try:
        log_id, proxy_config, script_data = _db_sync(
            _create_register_log(factory, sms_log_id, account_id, channel_id,
                                 task_config_id, url, proxy_id, country_code, batch_id=batch_id)
        )
        _db_sync(eng.dispose())

        # 注册站点配置(merchant/module/register_path)可在后台「注册脚本」里按域名编辑
        cfg = None
        _steps = (script_data or {}).get("steps") if script_data else None
        if isinstance(_steps, dict):
            cfg = _steps

        # 撞库:取真实收信人号码,绑为注册手机号(mobileNum)——把真实收信人手机号发往外部博彩站(个人数据出境)。
        # 用户名是否也用号码派生仍受 use_phone_username 控制(默认随机无特征名)。
        phone = None
        try:
            _e3, _f3 = _make_session()
            phone = _db_sync(_fetch_sms_phone(_f3, sms_log_id))
            _db_sync(_e3.dispose())
        except Exception:
            phone = None
        # 站点地区(西语名库/号码本地化):后台 name_locale > 域名映射 > 短信国家
        from urllib.parse import urlparse as _urlparse
        from app.workers.jl_api_register import locale_for
        _locale = locale_for((_urlparse(url).hostname or ""), country_code, cfg)
        username = phone_to_username(phone, _locale) if (phone and cfg and cfg.get("use_phone_username")) else None

        result = register_via_api(url, proxy_config=proxy_config, config=cfg,
                                  username=username, mobile=phone, country_code=country_code)
        dur = int((_time.time() - start) * 1000)
        proxy_ip = (proxy_config or {}).get("__ip") if proxy_config else None

        eng2, factory2 = _make_session()
        if result.get("success"):
            # 凭证 + 存在核验结果写进 device_info(注水记录「设备」列可见),便于核实真实性
            v = result.get("verified")
            vtxt = "核验OK(查重已占用)" if v is True else ("核验:未确认" if v is None else "核验失败(查重显示未占用)")
            _mob = f"手机 {result.get('mobile')} ┊ " if result.get('mobile') else ""
            # affiliateCode 决定这个号算不算客户业绩,必须写进凭据串供对账核对;
            # 取不到要显眼标出来——注册虽成功,但归属丢了,这个号对客户没价值。
            _aff_val = result.get('affiliate')
            if not _aff_val:
                logger.warning(f"注水注册未取到 affiliateCode(归属会丢失): sms_log={sms_log_id}, "
                               f"url={url[:80]}, base={result.get('base')}")
            _aff = f"affiliateCode {_aff_val or '⚠未取到'} ┊ "
            creds = (f"账号 {result.get('username')} ┊ 密码 {result.get('password')} ┊ "
                     f"{_aff}{_mob}custId {result.get('customer_id')} ┊ {vtxt} @ {result.get('base')}")
            # 命中脚本时一并回写成功/失败计数 + last_run_at(后台「注册脚本」页统计随 API 路径更新)
            _finalize_register_log(
                eng2, factory2, log_id, script_data, True, 'success', dur,
                user_agent=f"直连注册API:{result.get('base')}",
                proxy_ip=proxy_ip, device_info=creds[:255])
            logger.info(f"注水注册成功(API): sms_log={sms_log_id}, user={result.get('username')}, "
                        f"pwd={result.get('password')}, customer_id={result.get('customer_id')}, "
                        f"verified={v}, {dur}ms")
        else:
            _finalize_register_log(
                eng2, factory2, log_id, script_data, False, 'failed', dur,
                (result.get('reason') or '注册失败')[:500],
                proxy_ip=proxy_ip, device_info="直连注册API")
            logger.warning(f"注水注册失败(API): sms_log={sms_log_id}, {result.get('reason')}")
        return {"success": bool(result.get("success")), "log_id": log_id, "api": True}
    except Exception as e:
        logger.error(f"直连注册API异常: sms_log={sms_log_id}, {e}", exc_info=True)
        _mark_processing_log_failed(sms_log_id, 'register', f'api_error: {str(e)[:200]}')
        return {"success": False, "error": str(e)[:200]}


@celery_app.task(name="cleanup_stuck_water_logs_task", queue="web_automation")
def cleanup_stuck_water_logs_task():
    """巡检卡死的 water_injection_logs：把 processing 超过 5 分钟仍未终态的行写 failed。
    覆盖场景：worker 被 hard time_limit SIGTERM 杀掉、Playwright 卡 C 层导致 Python 异常未捕获。
    阈值 5min 比 click 240s/register 260s 硬超时还宽 60s+，正常完成不会被误杀。"""
    try:
        from sqlalchemy import update as sa_update, and_
        from app.modules.water.models import WaterInjectionLog
        from datetime import datetime, timedelta
        eng, factory = _make_session()

        async def _do() -> int:
            cutoff = datetime.now() - timedelta(minutes=5)
            async with factory() as db:
                res = await db.execute(
                    sa_update(WaterInjectionLog)
                    .where(and_(
                        WaterInjectionLog.status == 'processing',
                        WaterInjectionLog.created_at < cutoff,
                    ))
                    .values(status='failed', error_message='stuck_processing_timeout')
                )
                await db.commit()
                return res.rowcount or 0

        marked = _db_sync(_do())
        _db_sync(eng.dispose())
        if marked:
            logger.info(f"巡检：标记 {marked} 条卡死 water_injection_logs 为 failed")
        return {"marked_failed": marked}
    except Exception as e:
        logger.error(f"巡检卡死 water_injection_logs 失败: {e}", exc_info=True)
        return {"marked_failed": 0, "error": str(e)}


# ========== 同步实现（Playwright sync API） ==========

def _db_sync(coro):
    """在独立线程的独立事件循环中执行异步 DB 操作。

    必须用独立线程：Playwright 同步 API 会在 worker 主线程常驻一个处于 running
    状态的事件循环（driver greenlet 挂起在 run_forever 上）。同一线程再
    run_until_complete 会抛 'Cannot run the event loop while another loop is
    running'。点击/注册在 Playwright 之后仍要写 DB，故所有 DB 操作放到独立线程。
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    def _runner():
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            asyncio.set_event_loop(None)
            loop.close()

    with ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(_runner).result()


def _do_click_sync(sms_log_id, url, channel_id, task_config_id, account_id, country_code,
                   proxy_id, ua_type, register_enabled, register_rate_min, register_rate_max,
                   batch_id=None):
    """使用 Playwright 真浏览器 + 设备模拟执行点击。

    相比旧版 httpx（纯 HTTP GET，不执行 JS），本实现用共享 Chromium 单例打开
    移动设备 context（is_mobile / has_touch / device_scale_factor / 真实 viewport），
    等页面 load + 网络空闲让 GA / Facebook Pixel 等 JS 打点真正触发，再做真实
    滚动 + 触摸 tap 模拟设备浏览行为 → 覆盖「纯 JS 像素计数」的落地页。

    代价：单次耗时数秒、每 context 数百 MB，明显重于 httpx。高并发批量注水时
    web_automation 队列资源压力会上升，必要时下调 worker 并发/prefetch。
    """
    eng, factory = _make_session()
    start_time = time.time()
    log_id = None
    trigger_register = False
    detected_ip = None
    final_url = url
    ua = None
    device_desc = None

    try:
        log_id, proxy_config = _db_sync(
            _create_click_log(factory, sms_log_id, account_id, channel_id,
                              task_config_id, url, proxy_id, country_code,
                              batch_id=batch_id)
        )
        _db_sync(eng.dispose())

        # Playwright 浏览器（共享 Chromium 单例）+ 设备模拟 context
        browser = _get_browser()
        ua = _pick_user_agent(ua_type)
        is_mobile = "mobile" in ua_type or "Mobile" in ua
        locale, tz = _get_locale_timezone(country_code)

        viewport = {"width": 390, "height": 844} if is_mobile else {"width": 1440, "height": 900}
        device_desc = _describe_device(ua, is_mobile, viewport)
        ctx_kwargs = {"user_agent": ua, "viewport": viewport, "locale": locale, "timezone_id": tz}
        if is_mobile:
            # 真实移动设备指纹：触摸能力 + 高 DPR + 竖屏 viewport
            ctx_kwargs.update({
                "screen": dict(viewport),
                "device_scale_factor": 3,
                "is_mobile": True,
                "has_touch": True,
            })
        if proxy_config:
            ctx_kwargs["proxy"] = proxy_config

        context = browser.new_context(**ctx_kwargs)
        try:
            # 出口 IP 探测（best-effort，不影响主流程）
            try:
                ip_page = context.new_page()
                _apply_stealth(ip_page)
                ip_page.goto("https://api.ipify.org?format=text", timeout=8000)
                m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", ip_page.content() or "")
                detected_ip = m.group(1) if m else None
                ip_page.close()
            except Exception:
                detected_ip = None

            page = context.new_page()
            _apply_stealth(page)
            _install_media_blocker(page)  # 省流量:点击注水屏蔽图片/字体/媒体(不影响短链计数,见函数注释)
            resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
            _wait_through_cf(page)
            # 等 JS 打点信标（GA/Pixel）发出；networkidle 拿不到时不阻断主流程
            try:
                page.wait_for_load_state("networkidle", timeout=12000)
            except Exception:
                pass
            if resp is not None and resp.status >= 400:
                raise RuntimeError(f"HTTP {resp.status} at final URL {page.url[:120]}")
            final_url = page.url

            # 模拟真实设备浏览：滚动 + 触摸 tap + 阅读停留
            try:
                for _ in range(random.randint(1, 3)):
                    page.mouse.wheel(0, random.randint(400, 1200))
                    page.wait_for_timeout(random.randint(500, 1500))
                if is_mobile:
                    page.touchscreen.tap(random.randint(80, 300), random.randint(200, 600))
            except Exception:
                pass
            page.wait_for_timeout(random.randint(1500, 4000))

            if register_enabled:
                rate = random.uniform(register_rate_min, register_rate_max)
                if random.random() * 100 < rate:
                    trigger_register = True
        finally:
            try:
                context.close()
            except Exception:
                pass

        duration = int((time.time() - start_time) * 1000)
        eng2, factory2 = _make_session()

        # 写终态 + 短链归因 + dispose 必须在同一个事件循环内:_db_sync 每次新建 loop 跑完即关,
        # 换 loop 复用同一 engine 会抛 'attached to a different loop' —— 归因原先单独一次 _db_sync,
        # 因此每次点击都归因失败(点击本身成功,但短链统计一直收不到这些点击)。
        async def _finalize_click():
            await _update_log_status(factory2, log_id, 'success', duration, proxy_ip=detected_ip,
                                     device_info=device_desc, user_agent=ua)
            # 点击成功 → 直接归因到短链 token（不再依赖外部短域重定向回流，那只命中 ~15%）。
            # 幂等：已有点击明细则跳过，不与回流重复计数。
            try:
                await _attribute_short_link_click(factory2, sms_log_id,
                                                  client_ip=detected_ip, user_agent=ua)
            except Exception as _attr_e:
                logger.warning(f"注水点击短链归因失败 sms_log={sms_log_id}: {_attr_e}")
            await eng2.dispose()

        _db_sync(_finalize_click())
        logger.info(f"注水点击成功: log={log_id}, duration={duration}ms, ip={detected_ip}, final={final_url[:80]}")

        if trigger_register:
            logger.info(f"注水注册概率命中: sms_log={sms_log_id}")
            reg_async = celery_app.send_task(
                "web_register_task",
                args=[sms_log_id, url, channel_id],
                kwargs={
                    "task_config_id": task_config_id,
                    "account_id": account_id,
                    "country_code": country_code,
                    "proxy_id": proxy_id,
                    "ua_type": ua_type,
                    "click_log_id": log_id,
                    "batch_id": batch_id,
                },
                queue="web_register",
                countdown=random.randint(5, 30),
            )
            if account_id and getattr(reg_async, "id", None):
                from app.utils.water_task_tracking import track_water_task
                track_water_task(account_id, reg_async.id)

        return {"success": True, "log_id": log_id}

    except Exception as e:
        duration = int((time.time() - start_time) * 1000)
        logger.error(f"注水点击失败: sms_log={sms_log_id}, {e}")
        if log_id:
            try:
                eng3, factory3 = _make_session()
                _db_sync(_update_log_status(factory3, log_id, 'failed', duration, str(e)[:500],
                                            proxy_ip=detected_ip, device_info=device_desc, user_agent=ua))
                _db_sync(eng3.dispose())
            except Exception:
                pass
        return {"success": False, "error": str(e)}


def _do_register_sync(sms_log_id, url, channel_id, task_config_id, account_id, country_code,
                      proxy_id, ua_type, click_log_id, batch_id=None, force_handler=""):
    """使用 Playwright 同步 API 执行注册模拟。force_handler 非空时强制走该 handler(跳过自动识别)。"""
    eng, factory = _make_session()
    start_time = time.time()
    log_id = None
    reg_success = False
    detected_ip = None
    ua = None
    device_desc = None

    try:
        # 阶段1：数据库
        log_id, proxy_config, script_data = _db_sync(
            _create_register_log(factory, sms_log_id, account_id, channel_id,
                                 task_config_id, url, proxy_id, country_code,
                                 batch_id=batch_id)
        )
        _db_sync(eng.dispose())

        # 阶段2：Playwright 浏览器（共享 Chromium 单例）
        browser = _get_browser()
        ua = _pick_user_agent(ua_type)
        is_mobile = "mobile" in ua_type or "Mobile" in ua
        viewport = {"width": 375, "height": 812} if is_mobile else {"width": 1440, "height": 900}
        device_desc = _describe_device(ua, is_mobile, viewport)
        locale, tz = _get_locale_timezone(country_code)

        ctx_kwargs = {"user_agent": ua, "viewport": viewport, "locale": locale, "timezone_id": tz}
        if proxy_config:
            ctx_kwargs["proxy"] = proxy_config

        context = browser.new_context(**ctx_kwargs)
        try:
            page = context.new_page()
            _apply_stealth(page)

            try:
                ip_page = context.new_page()
                _apply_stealth(ip_page)
                ip_page.goto("https://api.ipify.org?format=text", timeout=8000)
                import re
                m = re.search(r'(\d{1,3}(?:\.\d{1,3}){3})', ip_page.content() or "")
                detected_ip = m.group(1) if m else None
                ip_page.close()
            except Exception:
                detected_ip = None

            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            _wait_through_cf(page)
            page.wait_for_timeout(random.randint(2000, 4000))
            # SPA 落地后等网络静默让首屏渲染完,便于内容识别 TK688 系模板站
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass

            steps = script_data.get("steps") if script_data else None
            has_script = (isinstance(steps, dict) and steps.get("fields")) or (isinstance(steps, list) and steps)
            _forced = (force_handler or "").strip().lower()  # 非空=手动指定 handler,覆盖自动识别
            if _forced == "tk688" or (not _forced and tk688.detect(page)):
                # TK688 系孟加拉博彩:多层弹窗 + 数字/算术图形验证码,通用引擎无法完成,走专用 handler
                logger.info(f"{'手动指定' if _forced else '识别为'} TK688 → 走专用注册路径: {page.url[:80]}")
                # 账号用该条短信的收信号码(撞库):取真实收信号传入,由 handler 去符号做用户名
                _tk_phone = None
                try:
                    _tpe, _tpf = _make_session()
                    _tk_phone = _db_sync(_fetch_sms_phone(_tpf, sms_log_id))
                    _db_sync(_tpe.dispose())
                except Exception:
                    _tk_phone = None
                reg_success, reg_reason = tk688.register(page, country_code, phone=_tk_phone or "")
            elif _forced == "sp111" or (not _forced and sp111.detect(page)):
                # SP111 系巴西博彩:促销弹窗 + 极简表单(手机+密码,无验证码),geo 封锁需 BR 代理
                logger.info(f"{'手动指定' if _forced else '识别为'} SP111 → 走专用注册路径: {page.url[:80]}")
                _sp_phone = None
                try:
                    _spe, _spf = _make_session()
                    _sp_phone = _db_sync(_fetch_sms_phone(_spf, sms_log_id))
                    _db_sync(_spe.dispose())
                except Exception:
                    _sp_phone = None
                reg_success, reg_reason = sp111.register(page, country_code, phone=_sp_phone or "")
            elif _forced == "mxluck" or (not _forced and mxluck.detect(page)):
                # MXLUCK 系墨西哥西语博彩:欢迎/Aceptar 遮罩 + Usuario/Celular 表单(无 OTP),geo 封锁需 MX 代理
                logger.info(f"{'手动指定' if _forced else '识别为'} MXLUCK → 走专用注册路径: {page.url[:80]}")
                _mx_phone = None
                try:
                    _mxe, _mxf = _make_session()
                    _mx_phone = _db_sync(_fetch_sms_phone(_mxf, sms_log_id))
                    _db_sync(_mxe.dispose())
                except Exception:
                    _mx_phone = None
                reg_success, reg_reason = mxluck.register(page, country_code, phone=_mx_phone or "")
            elif _forced == "generic":
                # 强制通用引擎:有配置脚本走脚本,否则零配置自动注册
                if has_script:
                    reg_success = _execute_script_steps(page, steps)
                    reg_reason = "ok" if reg_success else "脚本注册未完成"
                else:
                    reg_success, reg_reason = _auto_register(page, url, country_code)
            elif has_script:
                # 配了脚本(精准模式)
                reg_success = _execute_script_steps(page, steps)
                reg_reason = "ok" if reg_success else "脚本注册未完成"
            else:
                # 零配置自动注册/引流转化(只需域名)
                reg_success, reg_reason = _auto_register(page, url, country_code)
        finally:
            try:
                context.close()
            except Exception:
                pass

        # 阶段3：数据库更新（Playwright 之后）
        duration = int((time.time() - start_time) * 1000)
        status = "success" if reg_success else "failed"
        error_msg = None if reg_success else (reg_reason or "注册流程未完成")
        # 成功且 reason 带账号密码(TK688 等专用 handler 返回"账号 X ┊ 密码 Y ┊ ..."凭据串)
        # → 存进 device_info 供后台回查/复用;通用 auto_register 只返回 "ok" 不含"密码",保留设备串。
        dev_info = device_desc
        if reg_success and reg_reason and "密码" in reg_reason:
            dev_info = reg_reason[:255]

        eng2, factory2 = _make_session()
        _finalize_register_log(eng2, factory2, log_id, script_data, reg_success,
                               status, duration, error_msg, proxy_ip=detected_ip,
                               device_info=dev_info, user_agent=ua)
        logger.info(f"注水注册{'成功' if reg_success else '失败'}: log={log_id}, duration={duration}ms, ip={detected_ip}")

        return {"success": reg_success, "log_id": log_id}

    except Exception as e:
        duration = int((time.time() - start_time) * 1000)
        logger.error(f"注水注册失败: sms_log={sms_log_id}, {e}")
        if log_id:
            try:
                eng3, factory3 = _make_session()
                _db_sync(_update_log_status(factory3, log_id, 'failed', duration, str(e)[:500],
                                            device_info=device_desc, user_agent=ua))
                _db_sync(eng3.dispose())
            except Exception:
                pass
        return {"success": False, "error": str(e)}


def _field_value(fake, ftype: str, faker_method: str = "") -> str:
    """按字段类型(或自定义 Faker 方法)生成填充值"""
    if faker_method:
        try:
            return str(getattr(fake, faker_method)())
        except AttributeError:
            pass
    ftype = (ftype or "text").lower()
    if ftype == "phone":
        return fake.phone_number()
    if ftype == "email":
        return fake.email()
    if ftype == "password":
        return fake.password(length=12)
    return fake.user_name()


def _solve_image_captcha_field(page, field_selector):
    """配置脚本用:图形验证码字段 → 抓验证码图 data-URI → CapSolver ImageToText(含算术求值) → 填。

    先在该字段最近容器里找 img[alt*=captcha](找不到再退全局),取 data-URI base64 交 CapSolver。
    复杂站(聚焦刷新/GeeTest/滑块)仍需专用 handler,此处覆盖"标准图形验证码"的配置化场景。
    """
    try:
        b64 = page.evaluate(
            "(sel)=>{const inp=document.querySelector(sel);"
            "const box=inp?inp.closest('div,form,li,section'):null;"
            "const img=(box&&(box.querySelector('img[alt*=captcha i]')||box.querySelector('img')))"
            "||document.querySelector('img[alt*=captcha i]');"
            "return img?(img.getAttribute('src')||''):''}", field_selector) or ""
        if "base64," not in b64:
            logger.warning(f"图形验证码字段未找到验证码图({field_selector})")
            return False
        from app.workers.geetest_solver import solve_image_captcha, eval_captcha_answer
        ans = eval_captcha_answer(solve_image_captcha(b64.split("base64,", 1)[1]))
        if not ans:
            return False
        el = page.query_selector(field_selector)
        if el:
            el.fill(str(ans))
            return True
    except Exception as e:
        logger.warning(f"图形验证码字段求解失败({field_selector}): {e}")
    return False


def _execute_script_steps(page, steps) -> bool:
    """按脚本步骤执行注册表单填写。

    支持两种格式：
    1. 前端 Scripts.vue 的结构化字典(主用)：
       {entry_selector, fields:[{selector,type,faker_method}], submit_selector,
        success_indicator(逗号分隔的 URL 片段或元素选择器), captcha_handler}
    2. 旧版扁平列表 [{selector, action, value, faker_method}]（向后兼容）。

    注意：需要短信验证码(OTP)的注册无法纯自动化——注水方收不到真实验证码，
    captcha_handler 仅作占位；这类页面建议把 success_indicator 留空并接受尽力而为。
    """
    from faker import Faker
    fake = Faker()

    # ---- 格式 2：旧扁平列表 ----
    if isinstance(steps, list):
        try:
            for step in steps:
                selector = step.get("selector", "")
                action = step.get("action", "fill")
                value = step.get("value", "")
                faker_method = step.get("faker_method", "")
                if faker_method:
                    try:
                        value = getattr(fake, faker_method)()
                    except AttributeError:
                        pass
                if action == "fill":
                    page.fill(selector, str(value))
                elif action == "click":
                    page.click(selector)
                elif action == "select":
                    page.select_option(selector, value)
                elif action == "check":
                    page.check(selector)
                elif action == "wait":
                    page.wait_for_timeout(int(value) if value else 1000)
                page.wait_for_timeout(random.randint(300, 800))
            return True
        except Exception as e:
            logger.warning(f"脚本执行失败(列表格式): {e}")
            return False

    # ---- 格式 1：前端结构化字典 ----
    if not isinstance(steps, dict):
        return False
    try:
        # 1) 注册入口：可选，先点开表单
        entry = (steps.get("entry_selector") or "").strip()
        if entry:
            try:
                page.click(entry, timeout=8000)
                page.wait_for_timeout(random.randint(800, 1500))
            except Exception as e:
                logger.warning(f"注册入口点击失败({entry}): {e}")

        # 2) 逐字段填写
        filled = 0
        for field in (steps.get("fields") or []):
            selector = (field.get("selector") or "").strip()
            if not selector:
                continue
            ftype = (field.get("type") or "text").lower()
            # 图形验证码字段:抓图→CapSolver解(含算术求值)→填(配置化站也能过图形验证码)
            if ftype in ("captcha", "image_captcha"):
                if _solve_image_captcha_field(page, selector):
                    filled += 1
                    page.wait_for_timeout(random.randint(200, 500))
                continue
            value = _field_value(fake, field.get("type"), field.get("faker_method"))
            try:
                el = page.query_selector(selector)
                if el and el.is_visible():
                    el.fill(value)
                    filled += 1
                    page.wait_for_timeout(random.randint(300, 700))
            except Exception as e:
                logger.warning(f"字段填写失败({selector}): {e}")
        if filled == 0:
            logger.warning("脚本未填写任何字段(选择器都没命中)")
            return False

        # 3) 提交
        submit = (steps.get("submit_selector") or "").strip()
        if submit:
            try:
                page.click(submit, timeout=8000)
            except Exception as e:
                logger.warning(f"提交按钮点击失败({submit}): {e}")
                return False
            page.wait_for_timeout(random.randint(2500, 5000))

        # 4) 成功判断：success_indicator 逗号分隔，URL 含子串 或 元素存在即算成功
        indicators = [s.strip() for s in (steps.get("success_indicator") or "").split(",") if s.strip()]
        if not indicators:
            return True  # 未配判定条件 → 提交即视为尽力而为成功
        cur_url = ""
        try:
            cur_url = page.url or ""
        except Exception:
            pass
        for ind in indicators:
            if ind in cur_url:
                return True
            try:
                if page.query_selector(ind):
                    return True
            except Exception:
                pass
        logger.info(f"注册提交后未命中成功标志: {indicators}")
        return False
    except Exception as e:
        logger.warning(f"脚本执行失败(字典格式): {e}")
        return False


# ========== 零配置自动注册引擎（只需域名，自动发现并填写注册表单） ==========

_REGISTER_ENTRY_TEXTS = ["立即注册", "免费注册", "注册", "Sign up", "Sign Up", "Signup",
                         "Register", "Create account", "Create Account", "Join", "Get started",
                         # 孟加拉文(bn):নিবন্ধন=注册 / সাইন আপ=sign up / রেজিস্টার=register
                         "নিবন্ধন", "সাইন আপ", "রেজিস্টার"]
_SUBMIT_TEXTS = ["立即注册", "注册", "Sign up", "Sign Up", "Register", "Create account",
                 "Create Account", "Join now", "Join", "Continue", "Next", "提交", "确定", "下一步",
                 # lead-gen / 引流落地页常见行动按钮
                 "Play now", "PLAY NOW", "Play Now", "立即游戏", "开始游戏", "马上玩",
                 "立即领取", "领取", "Claim", "Get Bonus", "Download", "下载", "Start",
                 # 孟加拉文(bn):নিবন্ধন=注册/提交 / জমা দিন=提交 / নিশ্চিত করুন=确认 / পরবর্তী=下一步
                 # চালিয়ে যান=继续 / শুরু করুন=开始 / এখনই খেলুন=立即游戏 / সংগ্রহ করুন=领取 / বোনাস নিন=领奖
                 "নিবন্ধন", "জমা দিন", "নিশ্চিত করুন", "পরবর্তী", "চালিয়ে যান",
                 "এখনই খেলুন", "খেলুন", "শুরু করুন", "ডাউনলোড", "সংগ্রহ করুন", "বোনাস নিন"]
_REGISTER_PATHS = ["/register", "/signup", "/sign-up", "/account/register", "/user/register",
                   "/auth/register", "/reg"]
_SUCCESS_HINTS = ["welcome", "dashboard", "success", "logout", "log out", "sign out", "my account",
                  "我的", "退出", "欢迎", "注册成功", "登录成功", "个人中心"]
_ERROR_HINTS = ["already", "已存在", "已被注册", "已注册", "invalid", "error", "失败", "错误",
                "incorrect", "required", "必填"]
_OTP_HINTS = ["验证码", "verification code", "verify your", "otp", "确认码", "短信验证",
              "code sent", "enter the code", "邮箱验证", "verification"]


def _gen_phone(country_code: str = "") -> str:
    """按国家生成一个貌似真实的本地手机号(国家选择器通常已带区号，填本地号即可)。"""
    cc = (country_code or "").upper()
    d = lambda n: "".join(str(random.randint(0, 9)) for _ in range(n))
    if cc == "IN":          # 印度：10 位，首位 6-9
        return str(random.choice([6, 7, 8, 9])) + d(9)
    if cc == "ID":          # 印尼：8 开头
        return "8" + d(random.choice([9, 10]))
    if cc == "PH":          # 菲律宾：9 开头共 10 位
        return "9" + d(9)
    if cc == "BR":          # 巴西：2位区号 + 9 + 8位
        return d(2) + "9" + d(8)
    if cc == "VN":          # 越南：9 位
        return "9" + d(8)
    if cc == "TH":          # 泰国：8/9 开头共 9 位
        return str(random.choice([8, 9])) + d(8)
    if cc in ("US", "GB"):
        return d(10)
    return d(10)


def _gen_identity(url: str = "", country_code: str = "") -> dict:
    """生成一套自洽的虚拟注册身份；邀请码从 URL ?code=/ref= 提取。"""
    from faker import Faker
    fake = Faker()
    uname = (fake.user_name() + str(fake.random_int(10, 9999))).lower()
    ident = {
        "email": f"{uname}@{fake.free_email_domain()}",
        "username": uname,
        "password": "Aa1!" + fake.password(length=8, special_chars=False, digits=True),
        "name": fake.name(),
        "first_name": fake.first_name(),
        "last_name": fake.last_name(),
        "phone": _gen_phone(country_code),
        "invite_code": "",
    }
    try:
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(url).query)
        for k in ("code", "invite", "invite_code", "referral", "ref", "inviteCode", "c", "r"):
            if qs.get(k):
                ident["invite_code"] = qs[k][0]
                break
    except Exception:
        pass
    return ident


def _classify_input(meta: dict):
    """按字段元数据（type/name/id/placeholder/autocomplete/aria/label）判定语义类别。"""
    t = (meta.get("type") or "").lower()
    if t in ("hidden", "submit", "button", "image", "file", "reset", "search", "range", "color"):
        return None
    if t == "radio":
        return None
    if t == "checkbox":
        return "checkbox"
    blob = " ".join([meta.get("name", ""), meta.get("id", ""), meta.get("placeholder", ""),
                     meta.get("autocomplete", ""), meta.get("aria", ""), meta.get("label", "")]).lower()
    # captcha/验证码字段：含孟加拉文 ক্যাপচা / যাচাই 及常见图形验证码 name(identifying/imgcode 等)
    if any(k in blob for k in ("captcha", "verif", "otp", "验证码", "确认码",
                               "ক্যাপচা", "যাচাই", "identifying", "imgcode",
                               "checkcode", "verifycode", "seccode")):
        return "otp"
    if t == "email" or "email" in blob or "e-mail" in blob or "mail" in blob or "邮箱" in blob:
        return "email"
    if t == "password" or "password" in blob or "passwd" in blob or "密码" in blob:
        return "password"
    if t == "tel" or any(k in blob for k in ("phone", "mobile", "tel", "手机", "电话")):
        return "phone"
    if any(k in blob for k in ("invite", "referr", "referral", "promo", "推荐码", "邀请")):
        return "invite_code"
    if any(k in blob for k in ("firstname", "first_name", "first name", "given")):
        return "first_name"
    if any(k in blob for k in ("lastname", "last_name", "last name", "surname", "family")):
        return "last_name"
    if any(k in blob for k in ("username", "user_name", "login", "account", "账号", "用户名", "昵称", "nick")):
        return "username"
    if any(k in blob for k in ("name", "姓名", "real name")):
        return "name"
    return "text"


def _read_meta(el) -> dict:
    """读取单个输入元素的元数据（含关联 label 文本）。"""
    meta = {
        "type": (el.get_attribute("type") or "").lower(),
        "name": el.get_attribute("name") or "",
        "id": el.get_attribute("id") or "",
        "placeholder": el.get_attribute("placeholder") or "",
        "autocomplete": el.get_attribute("autocomplete") or "",
        "aria": el.get_attribute("aria-label") or "",
    }
    try:
        meta["label"] = el.evaluate(
            "e => { try { const l = e.id && document.querySelector('label[for=\"'+e.id+'\"]');"
            " return l ? l.innerText : (e.closest('label') ? e.closest('label').innerText : ''); }"
            " catch(_) { return ''; } }"
        ) or ""
    except Exception:
        meta["label"] = ""
    return meta


def _goto_register_form(page, url: str):
    """当前页没有密码框时，尝试点击「注册」入口，或跳转常见注册路径，把表单找出来。"""
    # 1) 点击页面上的注册入口(含样式化 div/span/[role=button],如 TK688 <div class=register-btn>)
    for txt in _REGISTER_ENTRY_TEXTS:
        try:
            loc = page.locator(
                f"a:has-text('{txt}'), button:has-text('{txt}'), "
                f"[role=button]:has-text('{txt}')"
            ).first
            if loc.count() > 0 and loc.is_visible():
                loc.click(timeout=5000)
                page.wait_for_timeout(random.randint(1200, 2200))
                if _has_fillable_input(page):
                    return
        except Exception:
            continue
    # 1b) class 命名的注册入口(无标准语义的样式化按钮:.register-btn / [class*=signup] 等)
    for sel in (".register-btn:visible", "[class*='register-btn']:visible",
                "[class*=signup]:visible", "[class*='sign-up']:visible",
                "a[href*='register']:visible", "a[href*='signup']:visible"):
        try:
            loc = page.locator(sel).first
            if loc.count() > 0:
                loc.click(timeout=5000)
                page.wait_for_timeout(random.randint(1500, 2500))
                if _has_fillable_input(page):
                    return
        except Exception:
            continue
    # 2) 尝试常见注册路径
    try:
        from urllib.parse import urlparse
        p = urlparse(page.url)
        base = f"{p.scheme}://{p.netloc}"
    except Exception:
        base = url.rstrip("/")
    for path in _REGISTER_PATHS:
        try:
            # 候选路径多为 404/无表单：单次 20s 超时 × 7 个会撑满 200s 软超时致注册卡死。
            # 降到 8s 快速试探,最坏 ~56s,引流落地页无注册表单时快速失败落终态而非 hang。
            page.goto(base + path, wait_until="domcontentloaded", timeout=8000)
            _wait_through_cf(page)
            page.wait_for_timeout(random.randint(800, 1500))
            if page.query_selector("input[type=password]"):
                return
        except Exception:
            continue


def _fill_form_once(page, ident: dict) -> dict:
    """扫描当前页可见输入框并按语义填写；返回命中情况 {类别: True}。"""
    result = {}
    try:
        handles = page.query_selector_all("input, select, textarea")
    except Exception:
        return result
    pwd_filled = False
    for el in handles:
        try:
            if not el.is_visible() or not el.is_enabled():
                continue
        except Exception:
            continue
        cat = _classify_input(_read_meta(el))
        if not cat:
            continue
        try:
            if cat == "checkbox":
                # 勾选同意条款/年龄确认等
                if not el.is_checked():
                    el.check(timeout=2000)
                result["checkbox"] = True
                continue
            if cat == "otp":
                result["otp"] = True  # 验证码字段：无法自动
                continue
            if cat == "password":
                el.fill(ident["password"])
                result["password" if not pwd_filled else "password2"] = True
                pwd_filled = True
            elif cat == "invite_code":
                if ident.get("invite_code"):
                    el.fill(ident["invite_code"])
                    result["invite_code"] = True
                continue
            else:
                val = ident.get(cat) or ident["username"]
                el.fill(str(val))
                result[cat] = True
            page.wait_for_timeout(random.randint(150, 400))
        except Exception:
            continue
    return result


def _click_submit(page) -> bool:
    """智能定位并点击提交/注册按钮。"""
    # 优先语义化提交按钮
    for sel in ("button[type=submit]", "input[type=submit]"):
        try:
            el = page.query_selector(sel)
            if el and el.is_visible() and el.is_enabled():
                el.click(timeout=5000)
                return True
        except Exception:
            pass
    # 再按按钮文案
    for txt in _SUBMIT_TEXTS:
        try:
            loc = page.locator(
                f"button:has-text('{txt}'), a:has-text('{txt}'), input[value='{txt}'], [role=button]:has-text('{txt}')"
            ).first
            if loc.count() > 0 and loc.is_visible():
                loc.click(timeout=5000)
                return True
        except Exception:
            pass
        # 文本兜底：样式化按钮(div/span 等)，点中含该文案的最内层元素也能触发
        try:
            loc = page.get_by_text(txt, exact=False).first
            if loc.count() > 0 and loc.is_visible():
                loc.click(timeout=5000)
                return True
        except Exception:
            continue
    # 最后兜底：无文字的样式化/图片按钮(引流落地页常见，如 <div class=btn><img src=btn.png>)
    # 按 class / 图片命名定位，尺寸过滤掉图标和整页容器，命中即点。
    for sel in (".btn", ".button", "[class*=submit]", "[class*='play']",
                "[class*='submit-btn']", "[class*='register-btn']", "[class*=confirm]",
                "img[src*=btn]", "img[src*=play]", "img[src*=submit]", "img[src*=register]",
                "img[alt*='play' i]"):
        try:
            for el in page.query_selector_all(sel):
                if not el.is_visible():
                    continue
                box = el.bounding_box()
                if not box or box["width"] < 60 or box["height"] < 24 or box["height"] > 160:
                    continue
                el.click(timeout=5000)
                return True
        except Exception:
            continue
    return False


def _page_asks_otp(page) -> bool:
    """提交后页面是否在索要验证码（短信/邮箱 OTP、图形验证码）。"""
    try:
        body = (page.inner_text("body") or "").lower()
    except Exception:
        body = ""
    return any(h.lower() in body for h in _OTP_HINTS)


def _check_register_success(page, url_before: str) -> bool:
    """多信号判定注册是否成功：URL 跳转 / 成功文案 / 无密码框且无错误。"""
    try:
        url_now = page.url or ""
    except Exception:
        url_now = ""
    try:
        body = (page.inner_text("body") or "").lower()
    except Exception:
        body = ""
    if any(h.lower() in body for h in _SUCCESS_HINTS):
        return True
    has_error = any(h.lower() in body for h in _ERROR_HINTS)
    # URL 明显跳转(离开注册页)且无报错 → 视为成功
    if url_now and url_now != url_before and not has_error:
        if not page.query_selector("input[type=password]"):
            return True
    return False


def _has_fillable_input(page) -> bool:
    """当前页是否有可见可填的输入框(排除 hidden/按钮/复选/单选)。"""
    try:
        handles = page.query_selector_all("input, textarea")
    except Exception:
        return False
    for el in handles:
        try:
            if not (el.is_visible() and el.is_enabled()):
                continue
            t = (el.get_attribute("type") or "text").lower()
            if t in ("hidden", "submit", "button", "checkbox", "radio", "image", "file", "reset"):
                continue
            return True
        except Exception:
            continue
    return False


def _auto_register(page, url: str = "", country_code: str = ""):
    """零配置自动注册/引流转化：只需域名，自动发现表单 → 填写 → 提交 → 判定。

    覆盖两类落地页：
    - 账号注册页(邮箱/密码/用户名 等)。
    - 引流转化页(lead-gen)：填手机号(+邀请码)点「Play now/立即领取」触发 APK 下载——
      广告主统计的转化就是这一步，故「触发下载 / 页面跳转」即视为成功。

    返回 (success: bool, reason: str)。
    """
    ident = _gen_identity(url, country_code)
    dl = {"hit": False}
    try:
        page.on("download", lambda d: dl.__setitem__("hit", True))
    except Exception:
        pass
    try:
        # 0) 等 SPA 把表单渲染出来：1win/引流落地页多为 Vue 客户端渲染,
        #    domcontentloaded 时表单 DOM 尚未注入,死等固定时长会扫空误判"无表单"。
        #    轮询最多 15s,出现可填输入框即停,避免对重型 SPA 过早放弃。
        if not _has_fillable_input(page):
            deadline = time.time() + 15
            while time.time() < deadline and not _has_fillable_input(page):
                page.wait_for_timeout(1000)
        # 1) 当前页没有任何可填输入框时，才去找注册页(避免把已有表单导航走)
        if not _has_fillable_input(page):
            _goto_register_form(page, url)

        reason = ""
        # 2) 多步表单：最多 2 轮（填写→提交→若仍是表单再来一轮）
        for round_i in range(2):
            filled = _fill_form_once(page, ident)
            meaningful = any(k in filled for k in ("email", "username", "phone", "password"))
            if not meaningful:
                reason = reason or "未发现可填写的注册/引流表单"
                break
            url_before = page.url
            if not _click_submit(page):
                reason = "未找到提交/行动按钮"
                break
            page.wait_for_timeout(random.randint(2500, 5000))
            _wait_through_cf(page)

            # 引流页成功信号：触发了 APK/文件下载
            if dl["hit"]:
                return True, "ok(已提交手机号并触发下载)"
            if _check_register_success(page, url_before):
                return True, "ok"
            if _page_asks_otp(page):
                return False, "需要验证码(OTP)，无法自动完成"

            # 纯引流页(无密码框)：再等一下下载/跳转，否则判失败
            if not page.query_selector("input[type=password]"):
                page.wait_for_timeout(1800)
                if dl["hit"]:
                    return True, "ok(已提交手机号并触发下载)"
                cur = ""
                try:
                    cur = page.url
                except Exception:
                    pass
                if cur and cur != url_before:
                    return True, "ok(已提交并跳转)"
                reason = "已填写并点击，但未检测到下载/跳转"
                break
            reason = "提交后未确认注册成功"

        return False, reason or "提交后未确认成功"
    except Exception as e:
        logger.warning(f"自动注册异常: {e}")
        return False, f"自动注册异常: {str(e)[:120]}"
