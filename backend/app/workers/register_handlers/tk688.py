"""TK688 系孟加拉博彩注册 handler(共享模板站)。

落地页(短链 shorturl.at → www.tk688.my)是孟加拉文 Vue SPA:进注册前有多层弹窗
(cookie 同意 সম্মতি → am-modal 年龄确认 নিশ্চিত করুন → 广告关闭),点 <div class=register-btn>
客户端路由到 /m/register 出表单;字段 name 为英文(username/password/confimpsw/payeeName),
验证码 identifying=<img alt=captcha> 的 numeric/算术式 data-URI(5-6位,CapSolver ImageToText 可解)。
短链经 httpx 解不开(shorturl.at 被 CF 挡),故只能在浏览器落地后按内容识别,不走 host 前置分流。
域名会换 → WATER_TK688_DOMAINS(逗号分隔,后缀匹配)可加当前主域。

许多东南亚/南亚博彩站共用这套模板(register-btn/am-modal/算术验证码)——新站命中同结构时,
只需把域名加进 WATER_TK688_DOMAINS 即可复用,无需改代码。
"""
import os
import re
import random
import time
import logging

logger = logging.getLogger(__name__)

NAME = "tk688"

_TK688_DOMAINS = [
    d.strip().lower().strip(".")
    for d in os.getenv("WATER_TK688_DOMAINS", "tk688.my").split(",")
    if d.strip()
]


def _tk688_host(host: str) -> bool:
    host = (host or "").lower().strip(".")
    return bool(host) and any(host == d or host.endswith("." + d) for d in _TK688_DOMAINS)


def detect(page) -> bool:
    """浏览器落地后判断是否 TK688 系模板站:域名命中,或内容指纹(注册/登录按钮类 + 孟加拉注册字)。"""
    try:
        from urllib.parse import urlparse
        if _tk688_host(urlparse(page.url or "").hostname):
            return True
    except Exception:
        pass
    try:
        if "tk688" in (page.title() or "").lower():
            return True
        # 该套共享模板特征:.register-btn + .login-btn 且正文含孟加拉文"নিবন্ধন"(注册)
        if page.query_selector(".register-btn") and page.query_selector(".login-btn"):
            if "নিবন্ধন" in (page.inner_text("body") or ""):
                return True
    except Exception:
        pass
    return False


# TK688 落地/注册页拦路弹窗:cookie 同意 / am-modal 年龄确认 / 广告关闭(逐个点掉)
_TK688_POPUP_SELECTORS = (
    "button.bottom-btn--agree", ".am-modal-button", "a.am-modal-button",
    "[class*=popup] [class*=close]", ".close-btn", ".am-navbar-title.close-btn",
)


def _click_first_visible(page, sel, timeout=1500):
    try:
        loc = page.locator(sel)
        for i in range(loc.count()):
            el = loc.nth(i)
            try:
                if el.is_visible():
                    el.click(timeout=timeout)
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def _dismiss_popups(page, rounds=4):
    """连关拦路弹窗(异步出现,固定多轮不提前退出)。"""
    for _ in range(rounds):
        for sel in _TK688_POPUP_SELECTORS:
            _click_first_visible(page, sel)
        page.wait_for_timeout(600)


def _form_present(page) -> bool:
    try:
        return bool(page.query_selector("input[name=identifying]"))
    except Exception:
        return False


def _fill(page, selector, value):
    try:
        el = page.query_selector(selector)
        if not el:
            return False
        el.click()
        el.fill("")
        el.type(str(value), delay=random.randint(30, 90))
        return True
    except Exception:
        try:
            el.fill(str(value))
            return True
        except Exception:
            return False


def _captcha_src(page):
    """取当前显示的验证码图 data-URI(用于解码 + 校验提交前未被刷新)。"""
    try:
        return page.evaluate(
            "()=>{const inp=document.querySelector('input[name=identifying]');"
            "const box=inp&&inp.closest('div');"
            "const img=box&&(box.querySelector('img[alt=captcha]')||box.querySelector('img'));"
            "return img?(img.getAttribute('src')||''):''}"
        ) or ""
    except Exception:
        return ""


def _wait_captcha_stable(page, timeout_ms=6000):
    """轮询验证码 data-URI 直到连续两次一致再返回。

    聚焦 identifying 触发的刷新是异步的(新图 ~1-2s 后才到),过早抓图会解到旧图、
    提交时已换新图而必败。等稳定后再解,src 才与提交时一致。"""
    prev = None
    waited = 0
    while waited < timeout_ms:
        page.wait_for_timeout(400)
        waited += 400
        cur = _captcha_src(page)
        if cur and cur == prev:
            return cur
        prev = cur
    return prev or ""


def _solve_captcha(page):
    """等验证码稳定 → 取 data-URI → CapSolver ImageToText → 求应填答案(含算术求值)。
    返回 (answer, src):src 供提交前校验未被刷新;失败 (None, src)。"""
    src = _wait_captcha_stable(page)
    if "base64," not in src:
        return None, src
    from app.workers.geetest_solver import solve_image_captcha, eval_captcha_answer
    ocr = solve_image_captcha(src.split("base64,", 1)[1])
    return eval_captcha_answer(ocr), src


def _refresh_captcha(page, wait_ms=1300):
    """点验证码图/刷新图标换一张新验证码(多数实现点图即刷新)。"""
    for sel in ("img[alt=captcha]", "input[name=identifying] ~ img",
                ".captcha img", "[class*=refresh]"):
        if _click_first_visible(page, sel, timeout=1500):
            break
    page.wait_for_timeout(wait_ms)


def _open_register(page):
    """连关弹窗 → 点 .register-btn 客户端路由到 /m/register(重试 4 次),等注册表单出现。"""
    for _ in range(4):
        _dismiss_popups(page, rounds=4)
        _click_first_visible(page, ".register-btn", timeout=5000)
        for _ in range(12):
            page.wait_for_timeout(800)
            if _form_present(page):
                return True
    return _form_present(page)


def _gen_password():
    """TK688 密码规则(客户端校验):6-12 位,字母+数字,无特殊符号(且需同时含字母与数字)。

    通用 _gen_identity 的密码带 `!` 等特殊符号且可能超 12 位,会被该站前端校验拦下不发注册请求。
    """
    import string as _string
    chars = list("".join(random.choice(_string.ascii_lowercase) for _ in range(6))
                 + "".join(random.choice(_string.digits) for _ in range(3)))
    random.shuffle(chars)
    return "".join(chars)  # 9 位,字母+数字,无特殊符号


def register(page, country_code="", phone=""):
    """TK688 系注册:开表单 → 填字段 → CapSolver 解数字/算术验证码 → 提交 → 判定。返回 (success, reason)。

    phone: 该条短信的收信号码(撞库) → 用作注册账号(去掉 + 取纯数字);缺失时回退随机用户名。
    验证码可能被判错/提交前刷新 → 最多 3 轮(每轮聚焦触发刷新→解稳定后的图→键盘输入→提交)。
    """
    # 共享工具懒导入,避免与 web_worker 循环引用
    from app.workers.web_worker import (
        _gen_identity, _click_submit, _check_register_success, _wait_through_cf,
    )

    if not _form_present(page) and not _open_register(page):
        return False, "TK688:未能打开注册表单(弹窗未关净或注册入口未命中)"

    # 抓注册接口响应作为主判定信号(比"表单消失"稳):PUT/POST /wps/member/register → {"success":true,...}
    reg_resp = {}

    def _on_reg_resp(resp):
        try:
            if resp.request.method in ("POST", "PUT") and re.search(r'/member/register|/register\b', resp.url, re.I):
                body = ""
                try:
                    body = resp.text() or ""
                except Exception:
                    body = ""
                compact = re.sub(r'\s', '', body)
                reg_resp["status"] = resp.status
                reg_resp["ok"] = ('"success":true' in compact) or (
                    200 <= resp.status < 300 and '"success":false' not in compact)
                reg_resp["body"] = body[:200]
        except Exception:
            pass

    try:
        page.on("response", _on_reg_resp)
    except Exception:
        pass

    ident = _gen_identity("", country_code)
    # 账号=收信号码(撞库):去掉 + 取纯数字(如 +8801300015360 → 8801300015360)。缺失时回退随机。
    phone_digits = re.sub(r"\D", "", phone or "")
    if phone_digits:
        username = phone_digits
    else:
        username = re.sub(r"[^a-z0-9]", "", ident["username"].lower())[:12] or f"u{random.randint(100000,999999)}"
        if len(username) < 6:
            username += str(random.randint(1000, 9999))
    password = _gen_password()
    payee = (ident.get("name") or "Rahim Uddin")[:20]
    from urllib.parse import urlparse as _urlparse
    _host = ""
    try:
        _host = _urlparse(page.url).hostname or "tk688.my"
    except Exception:
        _host = "tk688.my"
    creds = f"账号 {username} ┊ 密码 {password} ┊ TK688 @ {_host}"

    # 账号/密码/姓名只填一次;验证码每轮重解
    _fill(page, "input[name=username]", username)
    _fill(page, "input[name=password]", password)
    _fill(page, "input[name=confimpsw]", password)
    _fill(page, "input[name=payeeName]", payee)
    # 勾选"已阅读并同意条款"(默认多为已勾,兜底强制勾)
    for cb in page.query_selector_all("input[type=checkbox]"):
        try:
            if not cb.is_checked():
                cb.click(force=True)
        except Exception:
            pass

    # 关键:该站在"首次聚焦 identifying 输入框"时会刷新一次验证码(实测:等待/填其它字段不刷,
    # 一点验证码框就刷;而聚焦后再键盘输入不会再刷)。故每轮:先点框触发刷新→解"刷新后"的图→
    # 只用键盘敲答案(不再 click/清空,避免二次刷新)→校验未变→提交。
    last_reason = "TK688:注册未成功"
    for attempt in range(3):
        ident_el = page.query_selector("input[name=identifying]")
        if not ident_el:
            return False, "TK688:注册表单验证码输入框丢失"
        # 记录点击前验证码;聚焦触发刷新是异步的,先等它"相对点击前变了"(刷新落地)再解,
        # 否则 wait_stable 可能在刷新尚未开始时把旧图当稳定返回→解旧图、提交时已换新图而必败。
        before_src = _captcha_src(page)
        try:
            ident_el.click()
        except Exception:
            pass
        _chg_deadline = time.time() + 3.0
        while time.time() < _chg_deadline and _captcha_src(page) == before_src:
            page.wait_for_timeout(300)
        answer, src = _solve_captcha(page)
        if not answer:
            last_reason = "TK688:图形验证码求解失败(CapSolver 未返回)"
            _refresh_captcha(page)
            continue
        try:
            ident_el.press("Control+a")
            ident_el.type(answer, delay=random.randint(60, 130))
        except Exception:
            _fill(page, "input[name=identifying]", answer)
        page.wait_for_timeout(random.randint(200, 400))
        # 提交前校验验证码未被刷新(键盘输入正常不会刷;若因意外变了→本次答案作废,重解)
        if _captcha_src(page) != src:
            last_reason = "TK688:验证码提交前被刷新,重解"
            continue

        url_before = page.url
        reg_resp.clear()
        # 提交按钮唯一特征是 .submit-btn 类(头部注册入口是 .register-btn 无 submit-btn);
        # 并发共用浏览器时偶发定位失手 → 多选择器 + 重试,找不到重试整轮而非直接判失败。
        clicked = False
        for _ in range(3):
            if (_click_first_visible(page, "button.submit-btn.register-btn", timeout=4000)
                    or _click_first_visible(page, "button.submit-btn", timeout=3000)
                    or _click_first_visible(page, ".submit-btn", timeout=3000)):
                clicked = True
                break
            page.wait_for_timeout(700)
        if not clicked:
            clicked = _click_submit(page)  # 兜底:通用提交(已含孟加拉文 নিবন্ধন)
        if not clicked:
            last_reason = "TK688:未找到注册提交按钮"
            _refresh_captcha(page)
            continue

        # 等注册接口响应(最多 ~6s)
        for _ in range(15):
            page.wait_for_timeout(400)
            if reg_resp.get("status"):
                break
        _wait_through_cf(page)

        if reg_resp.get("ok"):
            return True, creds
        if reg_resp.get("status"):
            # 收到响应但被拒(验证码判错/账号占用等)→ 刷新验证码重试
            last_reason = (f"TK688:注册接口拒绝 status={reg_resp.get('status')} "
                           f"{(reg_resp.get('body') or '')[:80]}")
            _refresh_captcha(page)
            continue
        # 未截到响应 → 回退页面信号(弹层消失/登录后特征)
        if not _form_present(page) or _check_register_success(page, url_before):
            return True, creds
        last_reason = f"TK688:注册未成功(attempt {attempt + 1})"
        _refresh_captcha(page)

    return False, last_reason
