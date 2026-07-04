"""站点注册探针 —— 给一个落地 URL,自动摸清它的注册表单,产出"配置草稿"辅助接入新站。

把之前接 TK688 时十几轮手工探测(开页→关弹窗→找表单→dump字段/验证码/提交按钮)沉淀成一个工具:
走生产同款住宅代理 + patchright 打开(自动跟随短链跳转),尽力关弹窗、打开注册表单,然后 dump:
  - 最终落地 URL / 标题 / host
  - 可见输入框(name/type/placeholder/maxlength/pattern) + 语义分类(账号/密码/手机/验证码/OTP...)
  - 验证码类型判定(图形 data-URI / 算术式 / GeeTest / reCAPTCHA / hCaptcha / 滑块 / 短信OTP)
  - 注册入口 + 提交按钮候选
  - 遇到的弹窗
并给出**接入建议档位**(标准表单→后台配脚本 / 图形验证码→CapSolver专用handler / 滑块GeeTest→专用handler /
短信OTP→无法纯自动化)与一份可塞进 water_register_scripts 的**配置草稿**。

用法(容器内):
  docker compose exec worker-web python -m app.workers.register_handlers.site_profiler \\
      "https://shorturl.at/xxxx" --country BD [--proxy-id 1] [--solve]

  --solve  额外把找到的图形验证码丢给 CapSolver 解一次,回显 OCR 文本(用来区分纯数字 vs 算术式)。

输出:JSON 报告(stdout) + 截图 /tmp/profile_<host>.png。仅只读探测,不提交注册。
"""
import re
import json
import time
import argparse
import logging

logger = logging.getLogger(__name__)

# 多语言"注册入口/提交"文案(尽量覆盖中/英/葡/西/孟加拉/印尼/泰/越/俄等注水常见落地语言)
_ENTRY_TEXTS = ["注册", "立即注册", "免费注册", "Sign up", "Sign Up", "Register", "Signup",
                "Create account", "Join", "Daftar", "ลงทะเบียน", "Đăng ký", "Регистрация",
                "নিবন্ধন", "সাইন আপ", "रजिस्टर", "Registrasi",
                # 葡萄牙语(巴西)/西班牙语博彩站常见
                "Registro", "Registrar", "Cadastrar", "Cadastre-se", "Criar conta",
                "Registrarse", "Crear cuenta", "Inscrever-se"]
_SUBMIT_HINT_TEXTS = _ENTRY_TEXTS + ["提交", "确定", "下一步", "Continue", "Next", "Submit",
                                     "জমা দিন", "নিশ্চিত করুন", "Confirm", "Done"]
# 通用拦路弹窗(cookie 同意 / 年龄确认 / 广告关闭),多语言 + 类名兜底
_POPUP_SELECTORS = (
    "button.bottom-btn--agree", ".am-modal-button", "a.am-modal-button",
    "[class*=popup] [class*=close]", ".close-btn", ".am-navbar-title.close-btn",
    "[class*=cookie] button", "[class*=consent] button", "[class*=agree]",
    "[aria-label*=close i]", "[class*=modal] [class*=close]",
    # 广告/促销弹窗的关闭 X(博彩站首屏常弹):图标/类名/svg 兜底
    "[class*=close-icon]", "[class*=icon-close]", "[class*=btn-close]", "[class*=close-btn]",
    ".van-popup__close-icon", "[class*=dialog] [class*=close]", "img[src*=close]",
)

_UA_MOBILE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
              "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")


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
    dismissed = 0
    for _ in range(rounds):
        for sel in _POPUP_SELECTORS:
            if _click_first_visible(page, sel):
                dismissed += 1
        page.wait_for_timeout(600)
    return dismissed


def _has_fillable_input(page):
    try:
        return bool(page.evaluate("""()=>{
          for(const e of document.querySelectorAll('input,textarea')){
            const s=getComputedStyle(e), b=e.getBoundingClientRect();
            if(s.display==='none'||s.visibility==='hidden'||b.width===0)continue;
            const t=(e.type||'text').toLowerCase();
            if(['hidden','submit','button','checkbox','radio','image','file','reset'].includes(t))continue;
            return true;
          } return false;}"""))
    except Exception:
        return False


# 打开注册表单时高优先文案子集(全量 _ENTRY_TEXTS 太多会拖慢,这里挑各语言主词)
_ENTRY_TEXTS_PRIORITY = ["注册", "Register", "Sign up", "Registro", "Cadastrar", "Cadastre-se",
                         "নিবন্ধন", "Daftar", "ลงทะเบียน", "Đăng ký"]
# 注册按钮类名(样式化 div/a 无标准语义;register-btn-warper 等命中 [class*='register-btn'])
_REGISTER_CLASS_SELS = ("[class*='register-btn']:visible", ".register-btn:visible",
                        "[class*='btn-register']:visible", "[class*='register-button']:visible",
                        "[class*=cadastr]:visible", "[class*=signup]:visible", "a[href*=register]:visible")


def _open_register(page, budget_s=45):
    """当前无可填输入框时,尝试打开注册表单。时间受限:关弹窗→点注册入口(类优先,再高优文案)→
    再关弹窗→查表单;最多 2 轮或耗尽 budget_s 秒。"""
    if _has_fillable_input(page):
        return "already-present"
    deadline = time.time() + budget_s
    for _ in range(2):
        _dismiss_popups(page, rounds=1)  # 先清拦路弹窗(促销/cookie 挡注册按钮)
        for sel in _REGISTER_CLASS_SELS:
            if time.time() > deadline:
                return "timeout"
            if _click_first_visible(page, sel, timeout=2000):
                page.wait_for_timeout(1500)
                _dismiss_popups(page, rounds=1)
                if _has_fillable_input(page):
                    return f"clicked-class:{sel}"
        for txt in _ENTRY_TEXTS_PRIORITY:
            if time.time() > deadline:
                return "timeout"
            if _click_first_visible(page, f"a:has-text('{txt}'), button:has-text('{txt}'), "
                                          f"[role=button]:has-text('{txt}')", timeout=2000):
                page.wait_for_timeout(1500)
                _dismiss_popups(page, rounds=1)
                if _has_fillable_input(page):
                    return f"clicked-text:{txt}"
    return "not-opened"


def _dump_inputs(page):
    try:
        raw = page.evaluate("""()=>{
          const r=[];
          document.querySelectorAll('input,textarea,select').forEach(e=>{
            const s=getComputedStyle(e), b=e.getBoundingClientRect();
            if(s.display==='none'||s.visibility==='hidden'||b.width===0)return;
            r.push({tag:e.tagName,type:(e.getAttribute('type')||'text'),name:e.name||'',id:e.id||'',
                    placeholder:e.placeholder||'',autocomplete:e.getAttribute('autocomplete')||'',
                    aria:e.getAttribute('aria-label')||'',maxlength:e.getAttribute('maxlength')||'',
                    pattern:e.getAttribute('pattern')||'',inputmode:e.getAttribute('inputmode')||''});
          });
          return r;}""") or []
    except Exception:
        raw = []
    # 复用 web_worker 的语义分类
    from app.workers.web_worker import _classify_input
    out = []
    for m in raw:
        blob_meta = {"type": m["type"], "name": m["name"], "id": m["id"],
                     "placeholder": m["placeholder"], "autocomplete": m["autocomplete"],
                     "aria": m["aria"], "label": ""}
        try:
            cat = _classify_input(blob_meta)
        except Exception:
            cat = None
        m["semantic"] = cat
        m["selector"] = (f"input[name={m['name']}]" if m["name"]
                         else (f"#{m['id']}" if m["id"] else f"input[type={m['type']}]"))
        out.append(m)
    return out


def _dump_buttons(page):
    try:
        return page.evaluate("""(hints)=>{
          const r=[]; const seen=new Set();
          document.querySelectorAll('button,a,[role=button],input[type=submit],div,span').forEach(e=>{
            const s=getComputedStyle(e); if(s.display==='none'||s.visibility==='hidden')return;
            const b=e.getBoundingClientRect(); if(b.width<40||b.height<18||b.height>90)return;
            const txt=(e.innerText||e.value||'').trim(); const cls=(e.className||'').toString();
            const isSubmit = e.tagName==='BUTTON'||e.getAttribute('type')==='submit'
                 ||/btn|button|submit|register|confirm|next|primary/i.test(cls)
                 ||hints.some(h=>txt.includes(h));
            if(!isSubmit||txt.length>24)return;
            const key=e.tagName+cls+txt; if(seen.has(key))return; seen.add(key);
            r.push({tag:e.tagName,cls:cls.slice(0,60),txt:txt.slice(0,24),
                    selector: cls?('.'+cls.trim().split(/\\s+/).join('.')).slice(0,80):e.tagName.toLowerCase()});
          });
          return r.slice(0,25);}""", _SUBMIT_HINT_TEXTS) or []
    except Exception:
        return []


def _detect_captcha(page, solve=False):
    """判定验证码类型。返回 {type, detail, [ocr]}。"""
    info = {"type": "none", "detail": ""}
    try:
        probe = page.evaluate("""()=>{
          const has=(sel)=>!!document.querySelector(sel);
          const body=(document.body.innerText||'').toLowerCase();
          // 图形验证码:img[alt*=captcha] 或 data-uri img 靠近短数字输入框
          let imgSrc='';
          const capImg=document.querySelector('img[alt*=captcha i]');
          if(capImg) imgSrc=(capImg.getAttribute('src')||'').slice(0,30);
          return {
            geetest: has('[class*=geetest]')||has('[id*=geetest]')||typeof window.initGeetest!=='undefined'||typeof window.initGeetest4!=='undefined',
            recaptcha: has('iframe[src*=recaptcha]')||has('.g-recaptcha'),
            hcaptcha: has('iframe[src*=hcaptcha]')||has('.h-captcha'),
            // 滑块要收紧:只认带 verify/captcha 语义的,避免误命中页面轮播(swiper/banner slider)
            slider: has('[class*=nc_]')||has('[class*=verify-slide]')||has('[class*=slide-verify]')
                   ||has('[class*=slideUnlock]')||has('[class*=drag-verify]')||has('[class*=captcha-slider]'),
            imgCaptcha: !!capImg, imgSrc,
            otpText: ['验证码','verification code','otp','code sent','短信验证'].some(k=>body.includes(k)),
          };}""") or {}
    except Exception:
        probe = {}
    # 优先级:iframe型(geetest/recaptcha/hcaptcha)与图形验证码(img[alt=captcha]强信号)先判,
    # 滑块是弱信号(易被轮播误触)放最后,OTP 文案再兜底。
    if probe.get("geetest"):
        info = {"type": "geetest", "detail": "GeeTest(滑块/点选) → 需专用handler+CapSolver GeeTaskProxyLess(见1win/8kbdtf4)"}
    elif probe.get("recaptcha"):
        info = {"type": "recaptcha", "detail": "Google reCAPTCHA → 需 CapSolver ReCaptchaV2/V3,专用handler"}
    elif probe.get("hcaptcha"):
        info = {"type": "hcaptcha", "detail": "hCaptcha → 需 CapSolver HCaptcha,专用handler"}
    elif probe.get("imgCaptcha"):
        info = {"type": "image", "detail": f"图形验证码 img[alt=captcha] (src {probe.get('imgSrc')}) → CapSolver ImageToText(参考 TK688)"}
        if solve:
            try:
                src = page.evaluate("()=>{const i=document.querySelector('img[alt*=captcha i]');return i?(i.getAttribute('src')||''):''}") or ""
                if "base64," in src:
                    from app.workers.geetest_solver import solve_image_captcha
                    ocr = solve_image_captcha(src.split("base64,", 1)[1])
                    info["ocr"] = ocr
                    info["detail"] += f";CapSolver解得 '{ocr}'" + ("(疑似算术式,需求值)" if ocr and re.search(r'[+\-*/]', ocr) else "(纯数字)")
            except Exception as e:
                info["ocr_err"] = str(e)[:100]
    elif probe.get("slider"):
        info = {"type": "slider", "detail": "滑块验证 → 需专用handler(轨迹/CapSolver)"}
    elif probe.get("otpText"):
        info = {"type": "otp", "detail": "疑似短信/邮箱 OTP → 注水方收不到验证码,无法纯自动化"}
    return info


def _best_submit(cands):
    """从提交候选里挑最像"注册提交键"的:优先 .submit-btn / 含 submit·register 类 / BUTTON / 提交文案,
    惩罚明显的容器(header/nav/group/container/social 等)。"""
    def score(c):
        s = 0
        cls = (c.get("cls") or "").lower()
        txt = c.get("txt") or ""
        if "submit-btn" in cls:
            s += 5
        if re.search(r'submit|register|signup|reg-btn|confirm', cls):
            s += 3
        if c.get("tag") == "BUTTON":
            s += 2
        if any(h in txt for h in _SUBMIT_HINT_TEXTS):
            s += 2
        if re.search(r'header|nav|container|group|social|footer|menu|title|list', cls):
            s -= 3
        return s
    if not cands:
        return ""
    return max(cands, key=score)["selector"]


def _suggest_tier(inputs, captcha):
    fields = [i for i in inputs if i.get("semantic") in ("email", "username", "phone", "password", "name")]
    ct = captcha["type"]
    if not fields:
        return "未找到可填注册表单 —— 可能是纯引流页/未打开表单/需先过弹窗;人工看截图确认"
    if ct == "otp":
        return "档4-:含短信OTP,无法纯自动化(尽力而为或放弃)"
    if ct in ("geetest", "recaptcha", "hcaptcha", "slider"):
        return f"档4:{ct} → 写专用handler(仿1win/TK688)+接CapSolver对应task"
    if ct == "image":
        return "档4:图形验证码 → 写专用handler(仿TK688)+CapSolver ImageToText"
    if ct == "none":
        return "档2:标准表单无验证码 → 后台 Scripts.vue 配脚本即可,或先试通用引擎;无需改代码"
    return "需人工判断"


def profile(url, country_code="", proxy_id=None, solve=False):
    # 复用 worker 的共享 Chromium 单例(_get_browser):worker 进程里注册任务已 start 了 sync playwright,
    # 再自开一个 sync_playwright 会撞"Sync API inside asyncio loop"。单例模式与 _do_register_sync 一致。
    from app.workers.web_worker import _make_session, _db_sync, _wait_through_cf, _get_browser, _apply_stealth
    from app.utils.proxy_manager import get_proxy_for_country

    report = {"input_url": url, "country": country_code}
    # 生产同款代理
    proxy_config = None
    try:
        eng, factory = _make_session()

        async def _get():
            async with factory() as db:
                return await get_proxy_for_country(db, country_code, proxy_id)
        proxy_config = _db_sync(_get())
        _db_sync(eng.dispose())
    except Exception as e:
        report["proxy_error"] = str(e)[:120]
    # 空国家会让 DataImpulse 的 {country} 占位符残留 → 隧道必失败;此时改直连(geo受限站需填国家)
    if proxy_config and "{country}" in json.dumps(proxy_config):
        proxy_config = None
        report["proxy_note"] = "country 未指定或代理含未解析{country},改直连;若站点地域受限请填国家"
    report["proxy_used"] = bool(proxy_config)

    browser = _get_browser()
    ctx_kwargs = dict(user_agent=_UA_MOBILE, viewport={"width": 390, "height": 844},
                      is_mobile=True, has_touch=True, device_scale_factor=3, locale="en-US")
    if proxy_config:
        ctx_kwargs["proxy"] = proxy_config
    ctx = browser.new_context(**ctx_kwargs)
    page = ctx.new_page()
    if True:
        try:
            _apply_stealth(page)
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            _wait_through_cf(page)
            page.wait_for_timeout(4000)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            report["landing_url"] = page.url
            try:
                report["title"] = page.title()
            except Exception:
                report["title"] = ""
            from urllib.parse import urlparse
            host = urlparse(page.url).hostname or "site"
            report["host"] = host

            report["popups_dismissed"] = _dismiss_popups(page)
            report["open_register"] = _open_register(page)
            _dismiss_popups(page, rounds=2)

            report["inputs"] = _dump_inputs(page)
            report["captcha"] = _detect_captcha(page, solve=solve)
            report["submit_candidates"] = _dump_buttons(page)
            report["suggested_tier"] = _suggest_tier(report["inputs"], report["captcha"])

            # 配置草稿(可塞进 water_register_scripts.steps 的雏形)
            fields = [{"selector": i["selector"], "semantic": i.get("semantic")}
                      for i in report["inputs"] if i.get("semantic") in
                      ("email", "username", "phone", "password", "name", "otp")]
            submit_sel = _best_submit(report["submit_candidates"])
            report["config_draft"] = {
                "name": f"{host} 注册", "domain": host,
                "steps": {"entry_selector": "", "fields": fields, "submit_selector": submit_sel,
                          "captcha_handler": report["captcha"]["type"], "success_indicator": ""},
            }

            shot = f"/tmp/profile_{host}.png"
            try:
                page.screenshot(path=shot, full_page=True)
                report["screenshot"] = shot
            except Exception:
                pass
        except Exception as e:
            import traceback
            report["error"] = str(e)[:200]
            report["tb"] = traceback.format_exc()[-500:]
        finally:
            try:
                ctx.close()  # 只关 context;browser 是共享单例,不关
            except Exception:
                pass
    return report


# ========== 脚本自动生成 ==========

def _build_config_script(rep):
    """把画像转成 water_register_scripts 配置脚本(供 _execute_script_steps 执行)。

    无验证码站直接可跑;图形验证码站靠引擎里的 type=captcha 字段(CapSolver)也能跑。
    """
    host = rep.get("host", "site")
    ct = rep.get("captcha", {}).get("type", "none")
    fields = []
    for i in rep.get("inputs", []):
        sem = i.get("semantic")
        if sem in ("email", "username", "phone", "password", "name"):
            fields.append({"selector": i["selector"], "type": sem})
        elif sem in ("otp", "captcha") and ct == "image":
            fields.append({"selector": i["selector"], "type": "captcha"})
    return {
        "name": f"{host} 注册(自动生成)",
        "domain": host,
        "steps": {
            "entry_selector": "",  # 若首屏无表单需先点注册入口,人工补
            "fields": fields,
            "submit_selector": _best_submit(rep.get("submit_candidates", [])),
            "success_indicator": "",  # 建议补:注册成功后的URL片段或元素,如 /home,my-account
            "captcha_handler": ct,
        },
    }


def _save_config_script(script):
    """upsert 到 water_register_scripts(domain 唯一)。返回 script id。"""
    from app.workers.web_worker import _make_session, _db_sync
    from sqlalchemy import select
    from app.modules.water.models import WaterRegisterScript

    async def _do():
        eng, factory = _make_session()
        async with factory() as db:
            row = (await db.execute(
                select(WaterRegisterScript).where(WaterRegisterScript.domain == script["domain"])
            )).scalar_one_or_none()
            steps_json = json.dumps(script["steps"], ensure_ascii=False)
            if row:
                row.steps = steps_json
                row.name = script["name"]
                row.remark = "site_profiler 自动生成/更新"
            else:
                row = WaterRegisterScript(name=script["name"], domain=script["domain"],
                                          steps=steps_json, enabled=True,
                                          remark="site_profiler 自动生成")
                db.add(row)
            await db.commit()
            await db.refresh(row)
            rid = row.id
        await eng.dispose()
        return rid
    return _db_sync(_do())


_SCAFFOLD_TEMPLATE = '''"""%%HOST%% 注册 handler(site_profiler 自动生成脚手架,需人工微调后启用)。

验证码类型:%%CAPTCHA%%。字段/提交选择器来自探针,可能需按实测校正。
接线:web_worker._do_register_sync 落地后加 `if %%MODULE%%.detect(page): ... %%MODULE%%.register(...)`。
"""
import os
import re
import random
import time

NAME = "%%MODULE%%"
_DOMAINS = [d.strip().lower() for d in os.getenv("WATER_%%UMODULE%%_DOMAINS", "%%HOST%%").split(",") if d.strip()]


def detect(page) -> bool:
    try:
        from urllib.parse import urlparse
        h = (urlparse(page.url or "").hostname or "").lower()
        return any(h == d or h.endswith("." + d) for d in _DOMAINS)
    except Exception:
        return False


def register(page, country_code="", phone=""):
    """返回 (success, reason/凭据串)。TODO:按实测补弹窗关闭/成功判定/验证码细节。"""
    from app.workers.web_worker import _gen_identity, _click_submit, _check_register_success, _wait_through_cf
    from app.workers.geetest_solver import solve_image_captcha, eval_captcha_answer

    ident = _gen_identity("", country_code)
    username = re.sub(r"\\D", "", phone or "") or re.sub(r"[^a-z0-9]", "", ident["username"].lower())[:12]
    password = ident["password"]  # TODO:若站点有密码格式规则(如6-12位纯字母数字),改这里
    values = {"username": username, "password": password, "email": ident["email"],
              "phone": username, "name": ident.get("name", "")}

    # TODO:若首屏无表单,先关弹窗+点注册入口打开
%%FILLS%%

    # 验证码
%%CAPTCHA_BLOCK%%

    url_before = page.url
    if not (%%SUBMIT%% or _click_submit(page)):
        return False, "%%HOST%%:未找到提交按钮"
    page.wait_for_timeout(3000)
    _wait_through_cf(page)
    if _check_register_success(page, url_before):
        return True, f"账号 {username} ┊ 密码 {password} ┊ %%HOST%%"
    return False, "%%HOST%%:注册未确认成功(需补成功判定)"
'''


def _handler_scaffold_code(rep):
    host = rep.get("host", "site")
    module = re.sub(r"[^a-z0-9]", "", host.split(".")[0].lower()) or "site"
    ct = rep.get("captcha", {}).get("type", "none")
    # 填字段行
    fill_lines = []
    for i in rep.get("inputs", []):
        sem = i.get("semantic")
        if sem in ("email", "username", "phone", "password", "name"):
            fill_lines.append(f'    _fill(page, "{i["selector"]}", values.get("{sem}", username))')
    fills = "\n".join(fill_lines) or "    pass  # TODO:探针未识别到标准字段,手工补"
    # 验证码块(统一 4 空格缩进,占位符在行首)
    cap_field = next((i["selector"] for i in rep.get("inputs", []) if i.get("semantic") in ("otp", "captcha")), "input[name=captcha]")
    if ct == "image":
        cap_block = (
            '    src = page.evaluate("()=>{const i=document.querySelector(\'img[alt*=captcha i]\');return i?(i.getAttribute(\'src\')||\'\'):\'\'}") or ""\n'
            '    if "base64," in src:\n'
            '        ans = eval_captcha_answer(solve_image_captcha(src.split("base64,", 1)[1]))\n'
            f'        _fill(page, "{cap_field}", ans or "")')
    elif ct in ("geetest", "recaptcha", "hcaptcha", "slider"):
        cap_block = f'    pass  # TODO:{ct} 验证码,接 CapSolver 对应 task(参考 geetest_solver/1win handler)'
    else:
        cap_block = "    pass  # 无验证码"
    submit = _best_submit(rep.get("submit_candidates", []))
    submit_expr = f'page.query_selector("{submit}") and page.query_selector("{submit}").click()' if submit else "False"
    # 内嵌一个简易 _fill(避免依赖)
    fill_helper = ('\ndef _fill(page, sel, val):\n'
                   '    try:\n'
                   '        el = page.query_selector(sel)\n'
                   '        if el:\n'
                   '            el.fill(str(val)); return True\n'
                   '    except Exception:\n'
                   '        pass\n'
                   '    return False\n')
    code = (_SCAFFOLD_TEMPLATE
            .replace("%%HOST%%", host).replace("%%MODULE%%", module)
            .replace("%%UMODULE%%", module.upper()).replace("%%CAPTCHA%%", ct)
            .replace("%%FILLS%%", fills).replace("%%CAPTCHA_BLOCK%%", cap_block)
            .replace("%%SUBMIT%%", submit_expr))
    return code + fill_helper


def generate(url, country_code="", proxy_id=None, save=False, out_dir="/tmp"):
    """画像 → 自动生成注册脚本。配置化档出配置脚本(可--save入库),复杂档出代码脚手架文件。"""
    rep = profile(url, country_code, proxy_id, solve=True)
    ct = rep.get("captcha", {}).get("type", "none")
    result = {"suggested_tier": rep.get("suggested_tier"),
              "profile": {k: rep.get(k) for k in ("landing_url", "host", "inputs", "captcha", "screenshot")}}
    if rep.get("error") or not rep.get("inputs"):
        result["kind"] = "failed"
        result["note"] = rep.get("error") or "未识别到注册表单(可能需先关弹窗/点注册入口,看截图)"
        return result
    if ct in ("none", "image"):
        script = _build_config_script(rep)
        result["kind"] = "config_script"
        result["script"] = script
        result["note"] = ("标准表单" if ct == "none" else "图形验证码(引擎已支持)") + \
            " → 配置脚本可跑;若有聚焦刷新/多层弹窗等怪癖(如TK688),需改专用handler"
        if save:
            try:
                result["saved_script_id"] = _save_config_script(script)
                result["saved"] = True
            except Exception as e:
                result["save_error"] = str(e)[:150]
    elif ct in ("geetest", "recaptcha", "hcaptcha", "slider"):
        code = _handler_scaffold_code(rep)
        path = f"{out_dir}/{rep.get('host', 'site').split('.')[0]}_scaffold.py"
        try:
            with open(path, "w") as f:
                f.write(code)
            result["kind"] = "handler_scaffold"
            result["scaffold_path"] = path
        except Exception as e:
            result["kind"] = "handler_scaffold"
            result["scaffold_code"] = code
            result["write_error"] = str(e)[:120]
        result["note"] = f"{ct} 需专用handler;已生成脚手架,需人工补验证码接入/成功判定/弹窗后启用"
    elif ct == "otp":
        result["kind"] = "cannot_automate"
        result["note"] = "短信/邮箱OTP:注水方收不到验证码,无法纯自动化"
    else:
        result["kind"] = "unknown"
    return result


def main():
    ap = argparse.ArgumentParser(description="注册站点探针 / 脚本自动生成")
    ap.add_argument("url")
    ap.add_argument("--country", default="", help="ISO2 国家码(决定代理出口地),如 BD")
    ap.add_argument("--proxy-id", type=int, default=None, help="指定 water_proxies.id")
    ap.add_argument("--solve", action="store_true", help="额外用 CapSolver 解一次图形验证码回显文本")
    ap.add_argument("--generate", action="store_true", help="生成注册脚本(配置脚本或代码脚手架)")
    ap.add_argument("--save", action="store_true", help="配合 --generate:把配置脚本 upsert 入库")
    a = ap.parse_args()
    if a.generate:
        out = generate(a.url, a.country, a.proxy_id, a.save)
    else:
        out = profile(a.url, a.country, a.proxy_id, a.solve)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
