"""MXLUCK 系墨西哥西语博彩注册 handler。

落地(短链 mxluck.info/<token> → www.mxluck.com.mx/m/index.html)是西语 React SPA(antd-mobile `am-` 组件)。
**地域封锁**:需经 MX 住宅代理(dataimpulse cr.mx)。首屏有欢迎弹窗(👋¡Bienvenido!),开表单几秒后还会冒出
「Habilitar las notificaciones」底部弹层盖住提交键——JS .click() 提交可无视遮罩(遮罩只拦真实指针点击)。

开表单主路径:直连 /m/register?affiliateCode(表单干净、无遮罩;首页已落地故归属不丢);兜底 force 点
样式化入口 `<div class=nav-btn.register-btn>Registrarse</div>`。表单 **4 字段全必填**(实测,缺 Celular 报
"Ingrese entre 10 caracteres"):
  - input[name=username](随机用户名) + input[name=mobileNum1](Celular,10 位) + password + confimpsw。
  - **无验证码/OTP**。Celular 优先用收信号撞库(更真),取不到 10 位则随机 MX 号。
同意勾选 .sm-checkbox-item(选中态类 sm-checkbox-item-select),提交 button.submit-btn(Registrarse)。
成功信号:PUT /wps/member/register → 200 且跳转 /m/home。

域名会换 → WATER_MXLUCK_DOMAINS(逗号分隔,后缀匹配)可加当前主域;内容指纹兜底。
"""
import os
import re
import random
import string
import logging

logger = logging.getLogger(__name__)

NAME = "mxluck"

_DOMAINS = [
    d.strip().lower().strip(".")
    for d in os.getenv("WATER_MXLUCK_DOMAINS", "mxluck.com.mx,mxluck.info,mxluck.com").split(",")
    if d.strip()
]

# 拦路弹窗/确认层关闭候选(欢迎弹窗 + Aceptar 年龄条款门 + 促销角标 swiper)
_POPUP_CLOSE = (".close-btn", ".bottom-btn--agree", ".entry-close",
                "[class*=entry-close]", "[class*=close-btn]", "[class*=icon-close]")


def _host(host):
    host = (host or "").lower().strip(".")
    return bool(host) and any(host == d or host.endswith("." + d) for d in _DOMAINS)


def detect(page) -> bool:
    """落地后判断是否 MXLUCK 系:域名命中,或内容指纹(MXLUCK 品牌 + 西语注册入口类)。"""
    try:
        from urllib.parse import urlparse
        if _host(urlparse(page.url or "").hostname):
            return True
    except Exception:
        pass
    try:
        if "mxluck" in (page.title() or "").lower():
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
    """注册表单出现的判据:出现 用户名/手机 输入 + 至少一个密码框。"""
    try:
        return bool(page.evaluate(
            "()=>{const u=document.querySelector('input[name=username],input[name=mobileNum1]');"
            "const pw=document.querySelector('input[type=password],input[name=password]');"
            "return !!(u&&pw);}"))
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


def _open_register(page, aff=""):
    """开注册表单。主路径:直连 /m/register?affiliateCode(表单干净、无底部遮罩,首页已落地故归属不丢)。
    兜底:force 点 .register-btn 样式化入口 + 关底部确认层。"""
    from urllib.parse import urlparse
    p = urlparse(page.url)
    base = f"{p.scheme}://{p.netloc}"
    # 主路径:直连注册路由
    try:
        target = base + "/m/register" + (f"?affiliateCode={aff}" if aff else "")
        page.goto(target, wait_until="domcontentloaded", timeout=25000)
        _dismiss_popups(page, rounds=1)
        for _ in range(10):
            page.wait_for_timeout(600)
            if _reg_form_present(page):
                return True
    except Exception:
        pass
    # 兜底:回首页点样式化注册入口
    for _ in range(2):
        _dismiss_popups(page, rounds=2)
        _click_first_visible(page, ".nav-btn.register-btn", timeout=4000, force=True) \
            or _click_first_visible(page, ".register-btn", timeout=3000, force=True)
        _dismiss_bottom_modal(page)
        for _ in range(8):
            page.wait_for_timeout(700)
            if _reg_form_present(page):
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
    """MXLUCK 注册:关弹窗→开表单→填4字段(用户名/Celular撞库/双密码)→勾同意→JS提交→判定。返回 (success, 凭据串/原因)。"""
    from app.workers.web_worker import _wait_through_cf, _check_register_success
    from app.workers.register_handlers import extract_affiliate

    aff = extract_affiliate(page.url)
    if not _reg_form_present(page) and not _open_register(page, aff):
        return False, "MXLUCK:未能打开注册表单(欢迎/Aceptar 遮罩未关净或注册入口未命中)"
    aff = aff or extract_affiliate(page.url)

    # 抓注册接口响应作主判定
    reg_resp = {}

    def _on_resp(resp):
        try:
            if resp.request.method in ("POST", "PUT") and re.search(
                    r'regist|signup|member|user|account|create', resp.url, re.I):
                body = ""
                try:
                    body = resp.text() or ""
                except Exception:
                    body = ""
                compact = re.sub(r'\s', '', body).lower()
                if any(k in compact for k in ('"success"', '"token"', '"code"', '"data"', 'msg')):
                    reg_resp["status"] = resp.status
                    reg_resp["ok"] = ('"success":true' in compact) or ('"code":0' in compact) or \
                        ('"code":200' in compact) or (200 <= resp.status < 300 and '"success":false' not in compact
                                                      and '"error"' not in compact and 'existe' not in compact
                                                      and 'registrado' not in compact and 'ocupado' not in compact)
                    reg_resp["body"] = body[:200]
        except Exception:
            pass

    try:
        page.on("response", _on_resp)
    except Exception:
        pass

    # 该模板 4 个字段全必填:username + Celular(10 位) + password + confirm。
    # username 随机;Celular 优先用收信号撞库(更真,affiliate 看到被短信触达的号在注册),取不到 10 位则随机。
    password = _gen_password()
    username = _gen_username()
    local = _mx_local_number(phone)
    if not (local and len(local) == 10):  # 撞库号无效/缺失 → 随机 MX 手机号
        local = str(random.choice([55, 56, 33, 81])) + "".join(random.choice("0123456789") for _ in range(8))

    _fill(page, "input[name=username]", username) or _fill(page, "input[placeholder*=Usuario i]", username)
    _fill(page, "input[name=mobileNum1]", local) or _fill(page, "input[placeholder*=Celular i]", local)
    # 两个密码框:password + confimpsw(确认)
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
    account_disp = f"{username} / +52{local}"

    # 勾选 18 岁+条款(.sm-checkbox-item,React 组件 JS click;选中态=类 sm-checkbox-item-select),必勾否则报错
    def _agreed():
        try:
            return bool(page.query_selector(".sm-checkbox-item.sm-checkbox-item-select"))
        except Exception:
            return False
    for _ in range(3):
        if _agreed():
            break
        try:
            page.evaluate("()=>{const e=document.querySelector('.sm-checkbox-item-bg')||document.querySelector('.sm-checkbox-item');if(e)e.click();}")
        except Exception:
            _click_first_visible(page, ".sm-checkbox-item", timeout=2000, force=True)
        page.wait_for_timeout(400)
    page.wait_for_timeout(random.randint(300, 600))

    host = ""
    try:
        from urllib.parse import urlparse
        host = urlparse(page.url).hostname or "mxluck"
    except Exception:
        host = "mxluck"
    _aff_seg = f"affiliateCode {aff} ┊ " if aff else ""
    creds = f"账号 {account_disp} ┊ 密码 {password} ┊ {_aff_seg}MXLUCK @ {host}"

    url_before = page.url
    reg_resp.clear()
    _dismiss_bottom_modal(page)  # 提交前尽力关通知弹窗(JS click 已能无视遮罩,这步保持状态干净)
    if not _submit_click(page):
        return False, "MXLUCK:未找到注册提交按钮(.submit-btn)"

    for _ in range(16):
        page.wait_for_timeout(400)
        if reg_resp.get("status"):
            break
    _wait_through_cf(page)

    if reg_resp.get("ok"):
        return True, creds
    if reg_resp.get("status"):
        return False, f"MXLUCK:注册接口拒绝 status={reg_resp.get('status')} {(reg_resp.get('body') or '')[:80]}"
    # 无接口响应 → 回退页面信号(离开 /m/register / 表单消失 / 登录后特征)
    left_reg = "/m/register" not in (page.url or "")
    if (left_reg and not _reg_form_present(page)) or _check_register_success(page, url_before):
        return True, creds
    return False, "MXLUCK:注册未确认成功(接口无响应且仍停在注册页)"
