"""MXLUCK / 9AMX 系墨西哥西语博彩注册 handler。

兼容两代表单：

* 旧版 MXLUCK：`/m/register`，username + mobileNum1 + 双密码，无验证码。
* 新版 9AMX：首页按钮 ``Registrar`` 打开抽屉，手机号 + 邮箱 + 双密码 + 图片验证码。
  验证码来自 ``/api/auth/image_code``，在同一浏览器会话中取图、重绘后交给 CapSolver；
  注册成功信号为 ``POST /api/auth/register`` 返回 ``status: 0``。

两版均需 MX 住宅代理。域名会轮换，除环境变量白名单外还用页面标题/西语表单指纹兜底。
"""
import base64
import hashlib
import json
import os
import re
import random
import secrets
import string
import logging
import time

logger = logging.getLogger(__name__)

NAME = "mxluck"

_DOMAINS = [
    d.strip().lower().strip(".")
    for d in os.getenv(
        "WATER_MXLUCK_DOMAINS", "mxluck.com.mx,mxluck.info,mxluck.com,9amx.com.mx"
    ).split(",")
    if d.strip()
]

# 拦路弹窗/确认层关闭候选(欢迎弹窗 + Aceptar 年龄条款门 + 促销角标 swiper)
_POPUP_CLOSE = (".close-btn", ".bottom-btn--agree", ".entry-close",
                "[class*=entry-close]", "[class*=close-btn]", "[class*=icon-close]")


def _host(host):
    host = (host or "").lower().strip(".")
    return bool(host) and any(host == d or host.endswith("." + d) for d in _DOMAINS)


def detect(page) -> bool:
    """落地后判断是否 MXLUCK/9AMX 系：域名、标题或西语注册入口指纹。"""
    try:
        from urllib.parse import urlparse
        if _host(urlparse(page.url or "").hostname):
            return True
    except Exception:
        pass
    try:
        title = (page.title() or "").lower()
        if "mxluck" in title or "9amx" in title:
            return True
        # 该模板特征:.register-btn 样式化注册入口 + 西语正文
        if page.query_selector(".register-btn, .login-register"):
            body = (page.inner_text("body") or "").lower()
            if "registrarse" in body and ("ingresar" in body or "iniciar sesión" in body):
                return True
    except Exception:
        pass
    return False


def _click_first_visible(page, sel, timeout=2000, force=False):
    try:
        loc = page.locator(sel)
        for i in range(loc.count()):
            el = loc.nth(i)
            try:
                if el.is_visible():
                    el.click(timeout=timeout, force=force)
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def _dismiss_popups(page, rounds=3):
    """连关欢迎弹窗 / Aceptar 确认层 / 促销角标(首屏遮罩拦截点击,必须先清)。"""
    for _ in range(rounds):
        for sel in _POPUP_CLOSE:
            _click_first_visible(page, sel, timeout=1500, force=True)
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        page.wait_for_timeout(500)


def _reg_form_present(page) -> bool:
    """兼容旧 MXLUCK 与新 9AMX 的注册表单判据。"""
    try:
        return bool(page.evaluate(
            "()=>{"
            "const pw=document.querySelectorAll('input[type=password]');"
            "const legacy=document.querySelector('input[name=username],input[name=mobileNum1]');"
            "const modern=document.querySelector('input[type=tel]')&&"
            " document.querySelector('input[type=email]')&&pw.length>=2;"
            "return !!((legacy&&pw.length)||modern);}"))
    except Exception:
        return False


def _modern_form_present(page) -> bool:
    """新版 9AMX 抽屉表单：tel/email/双密码，并通常带 CAPTCHA。"""
    try:
        return bool(page.evaluate(
            "()=>!!(document.querySelector('input[type=tel]')&&"
            "document.querySelector('input[type=email]')&&"
            "document.querySelectorAll('input[type=password]').length>=2)"))
    except Exception:
        return False


def _is_9amx_site(page) -> bool:
    """新版 9AMX 品牌识别；用于优先走不依赖 SPA 渲染的同源 API。"""
    try:
        from urllib.parse import urlparse
        host = (urlparse(page.url or "").hostname or "").lower().strip(".")
        if host == "9amx.com.mx" or host.endswith(".9amx.com.mx"):
            return True
    except Exception:
        pass
    try:
        return "9amx" in (page.title() or "").lower()
    except Exception:
        return False


def _dismiss_bottom_modal(page):
    """关底部弹层(表单加载几秒后冒出的「Habilitar las notificaciones」通知弹窗会盖住提交键)。
    点 Cancelar 拒绝(干净关闭,无 am-modal 连锁;点 Aceptar 会再弹权限确认层)。best-effort。"""
    for _ in range(5):
        try:
            on = page.evaluate("()=>document.querySelectorAll('.bottom-modal.on,.bottom-modal-v1-app.on').length")
        except Exception:
            on = 0
        if not on:
            return
        try:
            page.evaluate("""()=>{const b=[...document.querySelectorAll(
              '.bottom-modal.on .bottom-btn--cancel,.bottom-modal.on .close-btn,.bottom-modal-v1-app.on .close-btn')]
              .find(e=>e.offsetParent); if(b) b.click();}""")
        except Exception:
            pass
        page.wait_for_timeout(500)


def _submit_click(page):
    """提交注册。JS .click() 直接触发 React onClick,无视通知/权限遮罩(遮罩只拦真实指针点击),
    Playwright force 点击兜底。"""
    try:
        did = page.evaluate("""()=>{const b=document.querySelector('button.submit-btn')||
          [...document.querySelectorAll('button,[class*=submit]')].find(e=>/registrarse/i.test(e.innerText||''));
          if(b){b.click();return true;} return false;}""")
        if did:
            return True
    except Exception:
        pass
    return (_click_first_visible(page, "button.submit-btn", timeout=4000, force=True)
            or _click_first_visible(page, ".submit-btn", timeout=3000, force=True)
            or _click_first_visible(page, "button:has-text('Registrarse')", timeout=3000, force=True))


def _click_spanish_register_button(page, submit=False):
    """点动态 CSS 的西语注册按钮。

    新版 9AMX 的 class 每次构建都会变，只能依赖可见文案。打开表单时取第一个精确
    ``Registrar``；提交时倒序取最后一个可见且未禁用的按钮，避开页头同名入口。
    """
    try:
        loc = page.locator("button,[role=button]")
        indexes = range(loc.count() - 1, -1, -1) if submit else range(loc.count())
        for i in indexes:
            el = loc.nth(i)
            try:
                text = re.sub(r"\s+", " ", el.inner_text() or "").strip()
                if not re.match(r"^(registrar|registrarse)(?:\s|$)", text, re.I):
                    continue
                if not el.is_visible() or (submit and el.is_disabled()):
                    continue
                el.click(timeout=5000, force=True)
                return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def _wait_for_form(page, timeout_ms=16000):
    waited = 0
    while waited < timeout_ms:
        if _reg_form_present(page):
            return True
        page.wait_for_timeout(500)
        waited += 500
    return _reg_form_present(page)


def _wait_for_entry_and_open(page, timeout_ms=25000):
    """等待慢 SPA 渲染注册入口，找到后只点击一次，再等待抽屉表单。"""
    waited = 0
    while waited < timeout_ms:
        if _reg_form_present(page):
            return True
        clicked = (_click_first_visible(page, ".nav-btn.register-btn", timeout=1500, force=True)
                   or _click_first_visible(page, ".register-btn", timeout=1500, force=True)
                   or _click_spanish_register_button(page))
        if clicked:
            return _wait_for_form(page, timeout_ms=20000)
        page.wait_for_timeout(500)
        waited += 500
    return _reg_form_present(page)


def _open_register(page, aff=""):
    """打开注册表单：先点当前首页入口（新版），再尝试旧版直连路由。"""
    from urllib.parse import urlparse
    p = urlparse(page.url)
    base = f"{p.scheme}://{p.netloc}"

    # 新版 9AMX：SPA 首屏在慢代理下可能 15 秒后才渲染动态 class 的 Registrar 按钮。
    _dismiss_popups(page, rounds=2)
    if _wait_for_entry_and_open(page):
        return True

    # 旧版 MXLUCK：直连路由表单更干净；新版会 200 后重定向回首页，随后仍可点入口。
    try:
        target = base + "/m/register" + (f"?affiliateCode={aff}" if aff else "")
        page.goto(target, wait_until="domcontentloaded", timeout=25000)
        _dismiss_popups(page, rounds=1)
        if _wait_for_form(page, timeout_ms=8000):
            return True
    except Exception:
        pass

    # 路由被新版站重定向回首页时，重新等待 SPA 入口（第二次网络加载也可能较慢）。
    _dismiss_popups(page, rounds=2)
    if _wait_for_entry_and_open(page):
        return True
    return _reg_form_present(page)


def _fill(page, selector, value):
    try:
        el = page.query_selector(selector)
        if not el:
            return False
        el.click()
        el.fill("")
        el.type(str(value), delay=random.randint(40, 100))
        return True
    except Exception:
        try:
            el.fill(str(value))
            return True
        except Exception:
            return False


def _gen_password():
    """MXLUCK 密码:字母+数字混合(保守无特殊符号),含字母与数字,10 位。"""
    chars = list("".join(random.choice(string.ascii_lowercase) for _ in range(6))
                 + "".join(random.choice(string.digits) for _ in range(4)))
    random.shuffle(chars)
    if not chars[0].isalpha():  # 首位保证字母(部分站要求)
        chars[0] = random.choice(string.ascii_lowercase)
    return "".join(chars)


def _gen_username():
    """随机用户名:字母开头,字母+数字,10-13 位(站点要求 ≥10 字符,不撞车)。"""
    n = random.randint(7, 9)
    body = "".join(random.choice(string.ascii_lowercase) for _ in range(n))
    return body + "".join(random.choice(string.digits) for _ in range(random.randint(3, 4)))


def _gen_9amx_password():
    """新版 9AMX：12 位大小写字母+数字，避开符号导致的前端规则差异。"""
    chars = [random.choice(string.ascii_uppercase), random.choice(string.ascii_lowercase),
             random.choice(string.digits)]
    chars.extend(random.choice(string.ascii_letters + string.digits) for _ in range(9))
    random.shuffle(chars)
    return "".join(chars)


def _gen_email():
    """生成不与手机号绑定、足够低碰撞的邮箱格式（站点不要求邮件 OTP）。"""
    suffix = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(14))
    return f"mx{suffix}@gmail.com"


def _parse_register_response(http_status, body):
    """解析旧版及 9AMX 注册接口响应，返回 (ok, 应用状态)。"""
    payload = None
    try:
        payload = json.loads(body or "")
    except Exception:
        payload = None

    if isinstance(payload, dict):
        if payload.get("success") is True:
            return True, payload.get("code", http_status)
        app_status = payload.get("status")
        # 9AMX /api/auth/register：status=0 且 user 内返回 token/userId。
        if app_status == 0 and isinstance(payload.get("user"), dict):
            user = payload["user"]
            return bool(user.get("token") or user.get("userId")), app_status
        code = payload.get("code")
        if code in (0, 200, "0", "200"):
            return True, code
        if app_status is not None:
            return False, app_status
        if code is not None:
            return False, code

    compact = re.sub(r"\s", "", body or "").lower()
    explicit_error = any(k in compact for k in (
        '"success":false', '"error"', "incorrect", "invalid", "existe",
        "registrado", "ocupado", "captcha",
    ))
    explicit_success = any(k in compact for k in (
        '"success":true', '"token"', '"userid"', '"code":0', '"code":200',
    ))
    return bool(200 <= http_status < 300 and explicit_success and not explicit_error), http_status


def _solve_9amx_captcha(page):
    """截取页面当前显示的验证码图并 OCR；不重新 GET，防止服务端换题。"""
    try:
        cap = page.locator("input[placeholder*='captcha' i]").first
        if not cap.count():
            return None
        img = page.locator("input[placeholder*='captcha' i] ~ div img").first
        if not img.count():
            # DOM 换层级后的兜底：从验证码输入框父容器向下找第一张图。
            img = cap.locator("xpath=..//img").first
        img.wait_for(state="visible", timeout=10000)
        try:
            page.wait_for_function(
                "()=>{const c=document.querySelector('input[placeholder*=captcha i]');"
                "const i=c&&c.parentElement&&c.parentElement.querySelector('img');"
                "return !!(i&&i.complete&&i.naturalWidth>0);}",
                timeout=12000,
            )
        except Exception:
            pass
        raw = img.screenshot(timeout=8000)
        if not raw:
            return None
        from app.workers.geetest_solver import solve_image_captcha, eval_captcha_answer
        return eval_captcha_answer(solve_image_captcha(base64.b64encode(raw).decode()))
    except Exception as e:
        logger.warning("9AMX 验证码截图/识别失败: %s", e)
        return None


def _refresh_9amx_captcha(page):
    """点击验证码图刷新，并等待图片 URL 或像素加载完成。"""
    try:
        img = page.locator("input[placeholder*='captcha' i] ~ div img").first
        if not img.count():
            return
        old = img.get_attribute("src") or ""
        img.click(force=True, timeout=3000)
        for _ in range(15):
            page.wait_for_timeout(300)
            cur = img.get_attribute("src") or ""
            if cur and cur != old:
                break
    except Exception:
        pass
    page.wait_for_timeout(700)


def _check_all_agreements(page):
    """勾选当前可见且未选中的协议 checkbox。"""
    try:
        for cb in page.query_selector_all("input[type=checkbox]"):
            try:
                if not cb.is_checked():
                    cb.click(force=True)
            except Exception:
                continue
    except Exception:
        pass


def _storage_value(page, name, default=""):
    """读取站点以 ``sk-<md5(key)>`` 保存的 JSON localStorage 值。"""
    key = "sk-" + hashlib.md5(name.encode()).hexdigest()
    try:
        raw = page.evaluate("key=>localStorage.getItem(key)", key)
        if raw is None:
            return default
        value = json.loads(raw)
        return default if value is None else value
    except Exception:
        return default


def _9amx_signed_headers(page, path, now_ms=None):
    """复刻站点请求拦截器的 ST/STT/x-path 签名头。"""
    st = str(int(now_ms if now_ms is not None else time.time() * 1000))
    sign_src = f"#kfdjksgjdksajgkdsjkdjfkda#{path}#{st}"
    encoded_path = base64.b64encode(path.encode()).decode()
    swapped = list(encoded_path)
    for i in range(0, len(swapped) - 1, 2):
        swapped[i], swapped[i + 1] = swapped[i + 1], swapped[i]
    bfid = str(_storage_value(page, "BrowserFingerprintId", "") or "")
    if not bfid:
        bfid = secrets.token_hex(16)
    try:
        tz = page.evaluate("()=>-new Date().getTimezoneOffset()/60")
    except Exception:
        tz = -6
    try:
        user_agent = page.evaluate("()=>navigator.userAgent") or ""
    except Exception:
        user_agent = ""
    return {
        "Accept": "application/json",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Content-Type": "application/json; charset=utf-8",
        "Device": "MOBILE",
        "BFID": bfid,
        "ST": st,
        "STT": hashlib.md5(sign_src.encode()).hexdigest(),
        "TZ": str(tz),
        "LANG": str(_storage_value(page, "currentLanguage", "es") or "es"),
        "COUNTRY": str(_storage_value(page, "countryId", "MX") or "MX"),
        "x-path": "".join(swapped),
        "User-Agent": user_agent,
    }


def _render_captcha_for_ocr(page, image):
    """让 Chromium 以 3 倍尺寸重绘验证码；实测比直接 OCR 原始 200×60 PNG 稳定。"""
    raw_b64 = base64.b64encode(image).decode()
    try:
        rendered = page.evaluate(
            """async src=>{
              const img=new Image(); img.src='data:image/png;base64,'+src;
              if(img.decode) await img.decode(); else await new Promise((ok,fail)=>{img.onload=ok;img.onerror=fail});
              const c=document.createElement('canvas'); c.width=img.naturalWidth*3; c.height=img.naturalHeight*3;
              const x=c.getContext('2d'); x.imageSmoothingEnabled=true;
              x.drawImage(img,0,0,c.width,c.height);
              return c.toDataURL('image/png').split(',',2)[1];
            }""",
            raw_b64,
        )
        return rendered or raw_b64
    except Exception:
        return raw_b64


def _register_9amx_api(page, phone="", aff=""):
    """同源 API 注册兜底。

    9AMX 的 SPA 静态资源经部分住宅代理偶发不渲染，但验证码和注册 API 仍可用。
    通过页面内同源 fetch 共享 cookie、浏览器指纹与同一代理连接，并复刻站点请求签名，
    直接取当前验证码图片并提交注册；既保留落地域归属，也不依赖动态 CSS/React 抽屉。
    """
    try:
        from urllib.parse import urlparse
        parsed = urlparse(page.url or "")
        base = f"{parsed.scheme or 'https'}://{parsed.netloc}"
        host = parsed.hostname or "9amx"
    except Exception:
        return False, "9AMX API:无法确定落地域名"
    if not parsed.netloc:
        return False, "9AMX API:落地域名为空"

    local = _mx_local_number(phone)
    if not (local and len(local) == 10):
        local = str(random.choice([55, 56, 33, 81])) + "".join(
            random.choice("0123456789") for _ in range(8)
        )
    email = _gen_email()
    password = _gen_9amx_password()
    aff_seg = f"affiliateCode {aff} ┊ " if aff else ""
    creds = f"账号 +52{local} ┊ 邮箱 {email} ┊ 密码 {password} ┊ {aff_seg}9AMX @ {host}"
    last_reason = "9AMX API:注册未成功"

    from app.workers.geetest_solver import solve_image_captcha, eval_captcha_answer

    for attempt in range(3):
        try:
            captcha_url = f"{base}/api/auth/image_code?t={int(time.time() * 1000)}"
            image_result = page.evaluate(
                """async url=>{
                  const r=await fetch(url,{credentials:'include',cache:'no-store'});
                  const bytes=new Uint8Array(await r.arrayBuffer());
                  let binary=''; for(let i=0;i<bytes.length;i+=8192){
                    binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
                  }
                  return {ok:r.ok,status:r.status,body:btoa(binary)};
                }""",
                captcha_url,
            )
            if not image_result.get("ok"):
                last_reason = f"9AMX API:验证码图片 HTTP {image_result.get('status')}"
                continue
            image = base64.b64decode(image_result.get("body") or "")
            answer = eval_captcha_answer(solve_image_captcha(_render_captcha_for_ocr(page, image)))
            if not answer:
                last_reason = "9AMX API:图片验证码识别失败(CapSolver 未返回)"
                continue

            payload = {
                "phone": local,
                "email": email,
                "password": password,
                "confirmPassword": password,
                "imageCode": answer,
                "countryId": "MX",
            }
            register_path = "/api/auth/register"
            signed_headers = _9amx_signed_headers(page, register_path)
            # User-Agent/Origin/Referer 是浏览器禁改头；fetch 会按页面环境自动附带。
            fetch_headers = {
                k: v for k, v in signed_headers.items()
                if k.lower() not in ("user-agent", "origin", "referer")
            }
            reg_result = page.evaluate(
                """async arg=>{
                  const r=await fetch(arg.path,{method:'POST',credentials:'include',
                    headers:arg.headers,body:JSON.stringify(arg.payload)});
                  return {status:r.status,body:await r.text()};
                }""",
                {"path": register_path, "headers": fetch_headers, "payload": payload},
            )
            http_status = int(reg_result.get("status") or 0)
            body = reg_result.get("body") or ""
            ok, app_status = _parse_register_response(http_status, body)
            if ok:
                return True, creds
            last_reason = (
                f"9AMX API:注册接口拒绝 http={http_status} status={app_status} "
                f"{body[:160]}"
            )
            # 验证码偶发 OCR 错误时换图重试；其它业务拒绝（号码占用等）重试没有意义。
            if not re.search(r"captcha|image.?code|verification", body, re.I):
                break
        except Exception as e:
            last_reason = f"9AMX API:第{attempt + 1}次请求异常 {str(e)[:160]}"
    return False, last_reason


def _mx_local_number(phone):
    """墨西哥收信号 → 表单本地号:去掉 + 和国际区号 52(如 +5215512345678 → 5512345678)。"""
    d = re.sub(r"\D", "", phone or "")
    if d.startswith("52") and len(d) > 10:
        d = d[2:]
    # 墨西哥移动号历史上有 1 前缀(52 1 XXXXXXXXXX),去掉多余前导 1
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    return d


def register(page, country_code="", phone=""):
    """兼容 MXLUCK/9AMX：开表单、填真实收信号、提交并以注册接口为主判定。"""
    from app.workers.web_worker import _wait_through_cf, _check_register_success
    from app.workers.register_handlers import extract_affiliate

    aff = extract_affiliate(page.url)
    api_reason = ""
    if _is_9amx_site(page):
        api_ok, api_reason = _register_9amx_api(page, phone=phone, aff=aff)
        if api_ok:
            return True, api_reason
        logger.warning("9AMX 同源 API 注册未成功，回退页面表单: %s", api_reason)
    if not _reg_form_present(page) and not _open_register(page, aff):
        if api_reason:
            return False, f"{api_reason}; 页面兜底也未能打开注册表单"
        return False, "MXLUCK/9AMX:未能打开注册表单(注册入口或页面结构已变化)"
    aff = aff or extract_affiliate(page.url)

    # 只监听真正的注册接口，避免 /api/user/* 等普通页面请求被误判为注册响应。
    reg_resp = {}

    def _on_resp(resp):
        try:
            url = (resp.url or "").lower()
            is_register = bool(re.search(
                r"/api/auth/register(?:[/?]|$)|/wps/member/register(?:[/?]|$)|"
                r"/(?:register|signup)(?:[/?]|$)|/account/create(?:[/?]|$)",
                url,
            ))
            if resp.request.method not in ("POST", "PUT") or not is_register:
                return
            try:
                body = resp.text() or ""
            except Exception:
                body = ""
            ok, app_status = _parse_register_response(resp.status, body)
            reg_resp.update({
                "http_status": resp.status,
                "app_status": app_status,
                "ok": ok,
                "body": body[:500],
            })
        except Exception:
            pass

    try:
        page.on("response", _on_resp)
    except Exception:
        pass

    local = _mx_local_number(phone)
    if not (local and len(local) == 10):
        local = str(random.choice([55, 56, 33, 81])) + "".join(
            random.choice("0123456789") for _ in range(8)
        )

    try:
        from urllib.parse import urlparse
        host = urlparse(page.url).hostname or "mxluck"
    except Exception:
        host = "mxluck"
    aff_seg = f"affiliateCode {aff} ┊ " if aff else ""

    if _modern_form_present(page):
        # 新版 9AMX：手机号、邮箱、双密码、图片验证码、18 岁协议。
        password = _gen_9amx_password()
        email = _gen_email()
        _fill(page, "input[type=tel]", local)
        _fill(page, "input[type=email]", email)
        pws = page.query_selector_all("input[type=password]")
        for pw in pws[:2]:
            try:
                pw.click(); pw.fill(""); pw.type(password, delay=random.randint(40, 90))
            except Exception:
                try:
                    pw.fill(password)
                except Exception:
                    pass
        _check_all_agreements(page)
        creds = f"账号 +52{local} ┊ 邮箱 {email} ┊ 密码 {password} ┊ {aff_seg}9AMX @ {host}"

        last_reason = "9AMX:注册未成功"
        for attempt in range(3):
            if attempt:
                _refresh_9amx_captcha(page)
            answer = _solve_9amx_captcha(page)
            if not answer:
                last_reason = "9AMX:图片验证码识别失败(CapSolver 未返回)"
                continue
            if not _fill(page, "input[placeholder*=captcha i]", answer):
                return False, "9AMX:验证码输入框已丢失"
            _check_all_agreements(page)
            page.wait_for_timeout(random.randint(300, 600))

            url_before = page.url
            reg_resp.clear()
            clicked = _click_spanish_register_button(page, submit=True)
            # 点击后最多等 15 秒；导航销毁上下文时 click 可能报错，但 response 仍会到达。
            for _ in range(30):
                page.wait_for_timeout(500)
                if reg_resp.get("http_status") or not _modern_form_present(page):
                    break
            _wait_through_cf(page)

            if reg_resp.get("ok"):
                return True, creds
            if not _modern_form_present(page) or _check_register_success(page, url_before):
                return True, creds
            if reg_resp.get("http_status"):
                last_reason = (
                    "9AMX:注册接口拒绝 "
                    f"http={reg_resp.get('http_status')} status={reg_resp.get('app_status')} "
                    f"{(reg_resp.get('body') or '')[:120]}"
                )
            elif not clicked:
                last_reason = "9AMX:注册按钮仍为禁用或未找到(字段校验未通过)"
            else:
                last_reason = f"9AMX:提交后未收到注册响应(attempt {attempt + 1})"
        return False, last_reason

    # 旧版 MXLUCK：username + Celular + 双密码，无验证码。
    password = _gen_password()
    username = _gen_username()
    _fill(page, "input[name=username]", username) or _fill(
        page, "input[placeholder*=Usuario i]", username
    )
    _fill(page, "input[name=mobileNum1]", local) or _fill(
        page, "input[placeholder*=Celular i]", local
    )
    if not _fill(page, "input[name=password]", password):
        pws = page.query_selector_all("input[type=password]")
        if pws:
            try:
                pws[0].click(); pws[0].fill(""); pws[0].type(password, delay=random.randint(40, 100))
            except Exception:
                pass
    if not _fill(page, "input[name=confimpsw]", password):
        pws = page.query_selector_all("input[type=password]")
        if len(pws) >= 2:
            try:
                pws[1].click(); pws[1].fill(""); pws[1].type(password, delay=random.randint(40, 100))
            except Exception:
                pass

    def _legacy_agreed():
        try:
            return bool(page.query_selector(".sm-checkbox-item.sm-checkbox-item-select"))
        except Exception:
            return False

    for _ in range(3):
        if _legacy_agreed():
            break
        try:
            page.evaluate(
                "()=>{const e=document.querySelector('.sm-checkbox-item-bg')||"
                "document.querySelector('.sm-checkbox-item');if(e)e.click();}"
            )
        except Exception:
            _click_first_visible(page, ".sm-checkbox-item", timeout=2000, force=True)
        page.wait_for_timeout(400)
    page.wait_for_timeout(random.randint(300, 600))

    creds = f"账号 {username} / +52{local} ┊ 密码 {password} ┊ {aff_seg}MXLUCK @ {host}"
    url_before = page.url
    reg_resp.clear()
    _dismiss_bottom_modal(page)
    if not _submit_click(page):
        return False, "MXLUCK:未找到注册提交按钮(.submit-btn)"
    for _ in range(16):
        page.wait_for_timeout(400)
        if reg_resp.get("http_status"):
            break
    _wait_through_cf(page)

    if reg_resp.get("ok"):
        return True, creds
    if reg_resp.get("http_status"):
        return False, (
            "MXLUCK:注册接口拒绝 "
            f"http={reg_resp.get('http_status')} status={reg_resp.get('app_status')} "
            f"{(reg_resp.get('body') or '')[:80]}"
        )
    left_reg = "/m/register" in (url_before or "") and "/m/register" not in (page.url or "")
    if (left_reg and not _reg_form_present(page)) or _check_register_success(page, url_before):
        return True, creds
    return False, "MXLUCK:注册未确认成功(接口无响应且仍停在注册页)"
