"""SP111 系巴西葡语博彩注册 handler。

落地(短链 djsaa54545a.net 等 → SP111.com)是葡语 Ionic SPA。**地域封锁**:非巴西 IP 弹
"Access restricted",必须经 BR 住宅代理。首屏有促销弹窗(代理佣金)挡住注册入口,需先关掉。
点 <div class=register-btn-warper.register>Registro 开注册弹层,表单极简:
  Telefone(+55 固定前缀,填本地号) + Senha + Confirmar senha,**无验证码**,提交 .submit.register-btn-warpper。

账号=收信号码(撞库):巴西 E.164 收信号 +55DDNNNNNNNNN → 去 +55 填本地号。
域名会换 → WATER_SP111_DOMAINS(逗号分隔,后缀匹配)可加当前主域;内容指纹兜底轮换域。
"""
import os
import re
import random
import string
import logging

logger = logging.getLogger(__name__)

NAME = "sp111"

_DOMAINS = [
    d.strip().lower().strip(".")
    for d in os.getenv("WATER_SP111_DOMAINS", "sp111.com,djsaa54545a.net").split(",")
    if d.strip()
]

# 拦路弹窗(促销/cookie/活动)关闭候选
_POPUP_CLOSE = (".quick-entry-close", ".quick-entry-close-icon", "ion-icon.close", ".close",
                "[class*=close-icon]", "[class*=icon-close]", "[class*=popup] [class*=close]",
                "[class*=dialog] [class*=close]", "[class*=activity] [class*=close]")


def _host(host):
    host = (host or "").lower().strip(".")
    return bool(host) and any(host == d or host.endswith("." + d) for d in _DOMAINS)


def detect(page) -> bool:
    """浏览器落地后判断是否 SP111 系:域名命中,或内容指纹(SP111 品牌 + 葡语注册按钮类)。"""
    try:
        from urllib.parse import urlparse
        if _host(urlparse(page.url or "").hostname):
            return True
    except Exception:
        pass
    try:
        if "sp111" in (page.title() or "").lower():
            return True
        # 该模板特征:.register-btn-warper 注册入口 + 葡语正文
        if page.query_selector(".register-btn-warper"):
            body = (page.inner_text("body") or "").lower()
            if "registro" in body or "crie uma conta" in body or "cadastre" in body:
                return True
    except Exception:
        pass
    return False


def _click_first_visible(page, sel, timeout=2000):
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


def _dismiss_popups(page, rounds=3):
    """连关促销/活动弹窗(SP111 首屏必弹,挡住注册入口)。"""
    for _ in range(rounds):
        for sel in _POPUP_CLOSE:
            _click_first_visible(page, sel)
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        page.wait_for_timeout(600)


def _reg_form_present(page) -> bool:
    """注册弹层出现的判据:出现 Telefone 输入 + 至少一个密码框。"""
    try:
        return bool(page.evaluate(
            "()=>{const tel=document.querySelector('input[placeholder*=Telefone i],input[type=tel]');"
            "const pw=document.querySelector('input[type=password]');"
            "return !!(tel&&pw);}"))
    except Exception:
        return False


def _open_register(page):
    """关弹窗 → 点 .register-btn-warper.register 开注册弹层(重试 3 次),等表单出现。"""
    for _ in range(3):
        _dismiss_popups(page, rounds=2)
        _click_first_visible(page, ".register-btn-warper.register", timeout=4000) \
            or _click_first_visible(page, ".register-btn-warper", timeout=3000)
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
    """SP111 密码:6-16 位字母+数字(无特殊符号,保守),含字母与数字。"""
    chars = list("".join(random.choice(string.ascii_lowercase) for _ in range(6))
                 + "".join(random.choice(string.digits) for _ in range(3)))
    random.shuffle(chars)
    return "".join(chars)  # 9 位


def _br_local_number(phone):
    """巴西收信号 → 表单本地号:去掉 + 和国际区号 55(如 +5511987654321 → 11987654321)。"""
    d = re.sub(r"\D", "", phone or "")
    if d.startswith("55") and len(d) > 10:
        d = d[2:]
    return d


def register(page, country_code="", phone=""):
    """SP111 注册:关弹窗→开表单→填手机(撞库)/密码/确认→提交→判定。返回 (success, 凭据串/原因)。"""
    from app.workers.web_worker import _wait_through_cf, _check_register_success

    if not _reg_form_present(page) and not _open_register(page):
        return False, "SP111:未能打开注册表单(促销弹窗未关净或注册入口未命中)"

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
                # 命中真正的注册结果(排除纯埋点):有 success/token/code 字样
                if any(k in compact for k in ('"success"', '"token"', '"code"', '"data"', 'msg')):
                    reg_resp["status"] = resp.status
                    reg_resp["ok"] = ('"success":true' in compact) or ('"code":0' in compact) or \
                        ('"code":200' in compact) or (200 <= resp.status < 300 and '"success":false' not in compact
                                                      and 'error' not in compact and 'existe' not in compact)
                    reg_resp["body"] = body[:200]
        except Exception:
            pass

    try:
        page.on("response", _on_resp)
    except Exception:
        pass

    local = _br_local_number(phone)
    if not local:
        local = str(random.choice([11, 21, 31, 41, 51])) + "9" + "".join(random.choice("0123456789") for _ in range(8))
    password = _gen_password()

    _fill(page, "input[placeholder*=Telefone i]", local) or _fill(page, "input[type=tel]", local)
    # 两个密码框:第一个 Senha,第二个 Confirmar senha
    pws = page.query_selector_all("input[type=password]")
    try:
        if len(pws) >= 1:
            pws[0].click(); pws[0].fill(""); pws[0].type(password, delay=random.randint(40, 100))
        if len(pws) >= 2:
            pws[1].click(); pws[1].fill(""); pws[1].type(password, delay=random.randint(40, 100))
    except Exception:
        _fill(page, "input[placeholder*=Confirmar i]", password)
    # 勾选可能的协议
    for cb in page.query_selector_all("input[type=checkbox]"):
        try:
            if not cb.is_checked():
                cb.click(force=True)
        except Exception:
            pass
    page.wait_for_timeout(random.randint(400, 800))

    host = ""
    try:
        from urllib.parse import urlparse
        host = urlparse(page.url).hostname or "sp111"
    except Exception:
        host = "sp111"
    creds = f"账号 +55{local} ┊ 密码 {password} ┊ SP111 @ {host}"

    url_before = page.url
    reg_resp.clear()
    # 提交弹层内的注册按钮(.submit.register-btn-warpper,注意 warpper 双 p,区别于头部入口 warper)
    clicked = (_click_first_visible(page, ".submit.register-btn-warpper", timeout=4000)
               or _click_first_visible(page, "[class*='register-btn-warpper'].submit", timeout=3000)
               or _click_first_visible(page, "[class*='register-btn-warpper']", timeout=3000))
    if not clicked:
        return False, "SP111:未找到注册提交按钮"

    for _ in range(16):
        page.wait_for_timeout(400)
        if reg_resp.get("status"):
            break
    _wait_through_cf(page)

    if reg_resp.get("ok"):
        return True, creds
    if reg_resp.get("status"):
        return False, f"SP111:注册接口拒绝 status={reg_resp.get('status')} {(reg_resp.get('body') or '')[:80]}"
    # 无响应 → 回退页面信号(弹层消失/登录后特征)
    if not _reg_form_present(page) or _check_register_success(page, url_before):
        return True, creds
    return False, "SP111:注册未确认成功(需补成功判定)"
