"""
注水自动化 Worker：使用 Playwright 无头浏览器模拟点击和注册
"""
import asyncio
import random
import time
from typing import Optional, Dict
from datetime import datetime

from celery.exceptions import SoftTimeLimitExceeded
from app.workers.celery_app import celery_app
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _apply_stealth(page):
    """应用 playwright-stealth 反指纹检测补丁（支持 v1 stealth_sync / v2 Stealth().use_sync）"""
    try:
        from playwright_stealth import Stealth
        Stealth().use_sync(page)
        return
    except Exception:
        pass
    try:
        from playwright_stealth import stealth_sync
        stealth_sync(page)
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


def _run_async(coro):
    """在 Celery worker 中安全执行异步协程（仅用于数据库操作）"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


def _make_session():
    """创建独立数据库会话"""
    from app.config import settings
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    eng = create_async_engine(
        settings.SQLALCHEMY_DATABASE_URL,
        echo=False, pool_size=2, max_overflow=2, pool_pre_ping=True,
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
            result = await db.execute(
                select(WaterRegisterScript).where(
                    WaterRegisterScript.domain == domain,
                    WaterRegisterScript.enabled == True,
                )
            )
            script = result.scalar_one_or_none()

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
                              screenshot_path: str = None):
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

    async with factory() as db:
        await db.execute(
            sa_update(WaterInjectionLog).where(WaterInjectionLog.id == log_id).values(**values)
        )
        await db.commit()


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


# ========== Celery 任务 ==========

@celery_app.task(name="web_click_task", bind=True, max_retries=1,
                 autoretry_for=(OSError, ConnectionError), retry_backoff=15,
                 soft_time_limit=90, time_limit=120)
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
        return {"success": False, "error": "soft_time_limit"}


@celery_app.task(name="web_register_task", bind=True, max_retries=1,
                 autoretry_for=(OSError, ConnectionError), retry_backoff=15,
                 soft_time_limit=100, time_limit=130)
def web_register_task(self, sms_log_id: int, url: str, channel_id: int,
                      task_config_id: int = None, account_id: int = None,
                      country_code: str = "",
                      proxy_id: int = None, ua_type: str = "mobile",
                      click_log_id: int = None, batch_id: int = None):
    """注水注册任务：使用 Playwright 同步 API 模拟注册"""
    if account_id and self.request.id:
        from app.utils.water_task_tracking import untrack_water_task
        untrack_water_task(account_id, self.request.id)
    logger.info(f"注水注册开始: sms_log={sms_log_id}, account={account_id}, batch={batch_id}, url={url[:80]}")
    try:
        return _do_register_sync(
            sms_log_id, url, channel_id, task_config_id, account_id, country_code,
            proxy_id, ua_type, click_log_id, batch_id=batch_id
        )
    except SoftTimeLimitExceeded:
        logger.warning(f"注水注册软超时: sms_log={sms_log_id}")
        return {"success": False, "error": "soft_time_limit"}


# ========== 同步实现（Playwright sync API） ==========

def _db_sync(coro):
    """独立的事件循环执行数据库异步操作"""
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _do_click_sync(sms_log_id, url, channel_id, task_config_id, account_id, country_code,
                   proxy_id, ua_type, register_enabled, register_rate_min, register_rate_max,
                   batch_id=None):
    """使用 Playwright 同步 API 执行点击模拟"""
    eng, factory = _make_session()
    start_time = time.time()
    log_id = None
    pw_success = False
    trigger_register = False
    detected_ip = None

    try:
        # 阶段1：数据库操作（Playwright 之前）
        log_id, proxy_config = _db_sync(
            _create_click_log(factory, sms_log_id, account_id, channel_id,
                              task_config_id, url, proxy_id, country_code,
                              batch_id=batch_id)
        )
        _db_sync(eng.dispose())

        # 阶段2：Playwright 浏览器操作（纯同步，不做任何 asyncio 操作）
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            launch_args = {"headless": True, "args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if proxy_config:
                launch_args["proxy"] = proxy_config

            browser = p.chromium.launch(**launch_args)
            try:
                ua = _pick_user_agent(ua_type)
                viewport = {"width": 375, "height": 812} if "mobile" in ua_type or "Mobile" in ua else {"width": 1440, "height": 900}
                locale, tz = _get_locale_timezone(country_code)

                context = browser.new_context(
                    user_agent=ua, viewport=viewport, locale=locale, timezone_id=tz,
                )
                page = context.new_page()
                _apply_stealth(page)

                # 先探测出口 IP（轻量 API，不影响主流程）
                try:
                    ip_page = context.new_page()
                    _apply_stealth(ip_page)
                    ip_page.goto("https://api.ipify.org?format=text", timeout=8000)
                    detected_ip = (ip_page.content() or "").strip()
                    # 提取纯 IP（去除 HTML 标签）
                    import re
                    m = re.search(r'(\d{1,3}(?:\.\d{1,3}){3})', detected_ip)
                    detected_ip = m.group(1) if m else None
                    ip_page.close()
                except Exception:
                    detected_ip = None

                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                _wait_through_cf(page)  # 等待 Cloudflare 挑战自动通过
                page.wait_for_timeout(random.randint(2000, 5000))

                for _ in range(random.randint(2, 5)):
                    page.evaluate(f"window.scrollBy(0, {random.randint(100, 500)})")
                    page.wait_for_timeout(random.randint(800, 2000))

                for _ in range(random.randint(1, 3)):
                    x = random.randint(50, viewport["width"] - 50)
                    y = random.randint(50, viewport["height"] - 50)
                    page.mouse.move(x, y)
                    page.wait_for_timeout(random.randint(300, 800))

                page.wait_for_timeout(random.randint(3000, 8000))
                pw_success = True

                if register_enabled:
                    rate = random.uniform(register_rate_min, register_rate_max)
                    if random.random() * 100 < rate:
                        trigger_register = True

                context.close()
            finally:
                browser.close()

        # 阶段3：数据库更新（Playwright 结束后）
        duration = int((time.time() - start_time) * 1000)
        eng2, factory2 = _make_session()
        _db_sync(_update_log_status(factory2, log_id, 'success', duration, proxy_ip=detected_ip))
        _db_sync(eng2.dispose())
        logger.info(f"注水点击成功: log={log_id}, duration={duration}ms, ip={detected_ip}")

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
                queue="web_automation",
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
                                            proxy_ip=detected_ip))
                _db_sync(eng3.dispose())
            except Exception:
                pass
        return {"success": False, "error": str(e)}


def _do_register_sync(sms_log_id, url, channel_id, task_config_id, account_id, country_code,
                      proxy_id, ua_type, click_log_id, batch_id=None):
    """使用 Playwright 同步 API 执行注册模拟"""
    eng, factory = _make_session()
    start_time = time.time()
    log_id = None
    reg_success = False
    detected_ip = None

    try:
        # 阶段1：数据库
        log_id, proxy_config, script_data = _db_sync(
            _create_register_log(factory, sms_log_id, account_id, channel_id,
                                 task_config_id, url, proxy_id, country_code,
                                 batch_id=batch_id)
        )
        _db_sync(eng.dispose())

        # 阶段2：Playwright 浏览器
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            launch_args = {"headless": True, "args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if proxy_config:
                launch_args["proxy"] = proxy_config

            browser = p.chromium.launch(**launch_args)
            try:
                ua = _pick_user_agent(ua_type)
                viewport = {"width": 375, "height": 812} if "mobile" in ua_type or "Mobile" in ua else {"width": 1440, "height": 900}
                locale, tz = _get_locale_timezone(country_code)

                context = browser.new_context(
                    user_agent=ua, viewport=viewport, locale=locale, timezone_id=tz,
                )
                page = context.new_page()
                _apply_stealth(page)

                # 探测出口 IP
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
                _wait_through_cf(page)  # 等待 Cloudflare 挑战自动通过
                page.wait_for_timeout(random.randint(2000, 4000))

                if script_data and script_data.get("steps"):
                    reg_success = _execute_script_steps(page, script_data["steps"])
                else:
                    reg_success = _heuristic_register(page)

                context.close()
            finally:
                browser.close()

        # 阶段3：数据库更新（Playwright 之后）
        duration = int((time.time() - start_time) * 1000)
        status = "success" if reg_success else "failed"
        error_msg = None if reg_success else "注册流程未完成"

        eng2, factory2 = _make_session()
        _db_sync(_update_log_status(factory2, log_id, status, duration, error_msg, proxy_ip=detected_ip))
        if script_data and script_data.get("id"):
            _db_sync(_increment_script_counter(factory2, script_data["id"], reg_success))
        _db_sync(eng2.dispose())
        logger.info(f"注水注册{'成功' if reg_success else '失败'}: log={log_id}, duration={duration}ms, ip={detected_ip}")

        return {"success": reg_success, "log_id": log_id}

    except Exception as e:
        duration = int((time.time() - start_time) * 1000)
        logger.error(f"注水注册失败: sms_log={sms_log_id}, {e}")
        if log_id:
            try:
                eng3, factory3 = _make_session()
                _db_sync(_update_log_status(factory3, log_id, 'failed', duration, str(e)[:500]))
                _db_sync(eng3.dispose())
            except Exception:
                pass
        return {"success": False, "error": str(e)}


def _execute_script_steps(page, steps: list) -> bool:
    """按脚本步骤执行注册表单填写"""
    from faker import Faker
    fake = Faker()

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
        logger.warning(f"脚本执行失败: {e}")
        return False


def _heuristic_register(page) -> bool:
    """启发式注册：自动检测表单并填写"""
    from faker import Faker
    fake = Faker()

    try:
        email_selectors = [
            'input[type="email"]', 'input[name*="email"]', 'input[id*="email"]',
            'input[placeholder*="email" i]', 'input[placeholder*="Email"]',
        ]
        for sel in email_selectors:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.fill(fake.email())
                page.wait_for_timeout(random.randint(300, 600))
                break

        password_selectors = [
            'input[type="password"]', 'input[name*="password"]', 'input[id*="password"]',
        ]
        for sel in password_selectors:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.fill(fake.password(length=12))
                page.wait_for_timeout(random.randint(300, 600))
                break

        name_selectors = [
            'input[name*="name"]', 'input[id*="name"]',
            'input[placeholder*="name" i]', 'input[placeholder*="Name"]',
        ]
        for sel in name_selectors:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.fill(fake.name())
                page.wait_for_timeout(random.randint(200, 500))
                break

        phone_selectors = [
            'input[type="tel"]', 'input[name*="phone"]', 'input[name*="mobile"]',
        ]
        for sel in phone_selectors:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.fill(fake.phone_number())
                page.wait_for_timeout(random.randint(200, 500))
                break

        submit_selectors = [
            'button[type="submit"]', 'input[type="submit"]',
            'button:has-text("Sign Up")', 'button:has-text("Register")',
            'button:has-text("注册")', 'button:has-text("Create")',
        ]
        for sel in submit_selectors:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                page.wait_for_timeout(random.randint(3000, 6000))
                return True

        return False
    except Exception as e:
        logger.warning(f"启发式注册异常: {e}")
        return False
