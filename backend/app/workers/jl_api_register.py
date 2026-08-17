"""考拉注水:jilievobdt 系博彩落地页「直连注册 API」实现(绕过反自动化的浏览器渲染)。

逆向自 vendor.encrypt.v2.dll.js 的加密方案:
  r = 16位随机串;DES密钥 = r[:8](CryptoJS.enc.Utf8.parse 取前8字节)
  DES体  = base64( DES-ECB-Pkcs7(payloadJSON, key=r[:8]) )         → 请求体
  RSA头  = RSAUtils.encryptedString:m=小端整数(reverse(r)); c=m^65537 mod n; hex(c)  → Encryption 头
  公钥 n = GET {base}/wps/session/key/rsa 返回的模数(hex, 1024-bit)
注册   = PUT {base}/wps/member/register, 头 Encryption / Merchant / Module-Id(REG3) / Language

经实测可创建真实账号(success:true + customerId)。密码须纯字母数字(特殊字符被格式校验拒)。
"""
from __future__ import annotations
import base64
import json
import random
import string
from typing import Optional

import httpx

# 可注册主域 → 商户号。按主域后缀匹配(应对随机子域轮换:8kbd2087.rztk6mpvx.com / www.rztk6mpvx.com)。
# base 由落地 URL 实时解析,无需硬编码完整 host。
MERCHANT_BY_DOMAIN = {
    "in1.fun": "jilievof2",
    "rztk6mpvx.com": "8kbdtf4",  # 孟加拉博彩,注册开 GeeTest v4(走 CapSolver);affiliateCode 在子域/query
    # 墨西哥西语博彩(7aa.mx),注册只要 username+password,mobileNum 选填10位。
    # 真站同时挂 5 个马甲域轮换(见落地页 redirectDomains),另加 7aa88.vip 中间营销落地域——
    # 短信短链先落中间页,再由页面跳真站,故两类域都要登记(否则路由不走直连 API)。
    "7aamx.cc": "7aamxns1",
    "7aamx.vip": "7aamxns1",
    "7aamx.xyz": "7aamxns1",
    "7aamx.me": "7aamxns1",
    "7aamx.shop": "7aamxns1",
    "7aa88.vip": "7aamxns1",
}
DEFAULT_MERCHANT = "jilievof2"

# 主域 → 拟人语料/号码地区(账号密码词库与 mobileNum 本地化规则)。默认 bd(存量站)。
LOCALE_BY_DOMAIN = {
    "in1.fun": "bd",
    "rztk6mpvx.com": "bd",
    "7aamx.cc": "mx",
    "7aamx.vip": "mx",
    "7aamx.xyz": "mx",
    "7aamx.me": "mx",
    "7aamx.shop": "mx",
    "7aa88.vip": "mx",
}
_LOCALE_BY_COUNTRY = {"MX": "mx", "BD": "bd"}


def _load_env_sites() -> None:
    """WATER_API_SITES="域名=商户号[:locale],..." 追加/覆盖站点映射。

    马甲域轮换时只改环境变量即可接管新域,不必改代码重建镜像。
    例:WATER_API_SITES="7aamx2.cc=7aamxns1:mx,newdom.com=abc123"
    """
    import os
    for item in (os.getenv("WATER_API_SITES", "") or "").split(","):
        item = item.strip()
        if not item or "=" not in item:
            continue
        dom, val = item.split("=", 1)
        dom = dom.strip().lower().strip(".")
        mc, _, loc = val.strip().partition(":")
        if dom and mc.strip():
            MERCHANT_BY_DOMAIN[dom] = mc.strip()
            if loc.strip():
                LOCALE_BY_DOMAIN[dom] = loc.strip().lower()


_load_env_sites()


def _match_domain(host: str, table: dict):
    """host → 表中值:先精确匹配,再按可注册主域后缀匹配。匹配不到返回 None。"""
    host = (host or "").lower().strip(".")
    if not host:
        return None
    if host in table:
        return table[host]
    for dom, val in table.items():
        if host == dom or host.endswith("." + dom):
            return val
    return None


def merchant_for_host(host: str) -> Optional[str]:
    """host → 商户号:先精确匹配,再按可注册主域后缀匹配。匹配不到返回 None。"""
    return _match_domain(host, MERCHANT_BY_DOMAIN)


def locale_for(host: str = "", country_code: str = "", cfg: Optional[dict] = None) -> str:
    """决定拟人语料/号码地区:后台脚本 name_locale > 域名映射 > 短信国家 > bd(存量默认)。"""
    if cfg and (cfg.get("name_locale") or cfg.get("locale")):
        return str(cfg.get("name_locale") or cfg.get("locale")).strip().lower()
    return (_match_domain(host, LOCALE_BY_DOMAIN)
            or _LOCALE_BY_COUNTRY.get((country_code or "").strip().upper())
            or "bd")


def extract_affiliate(url: str, host: str = None) -> str:
    """从落地 URL 取 affiliateCode:优先 query ?affiliateCode=,否则取子域最左标签(<aff>.主域)。"""
    from urllib.parse import urlparse, parse_qs
    p = urlparse(url)
    q = parse_qs(p.query or "")
    for k in ("affiliateCode", "affiliatecode", "affiliate", "aff"):
        if q.get(k):
            return q[k][0]
    host = (host or p.hostname or "").lower()
    labels = host.split(".")
    if len(labels) >= 3 and labels[0] not in ("www", "m", "mobile", "h5"):
        return labels[0]
    return ""


def domain_candidates(host: str) -> list:
    """host → 由具体到主域的候选列表(≥2 段),供注册脚本表按主域后缀匹配随机子域。
    例:8kbd2087.rztk6mpvx.com → [8kbd2087.rztk6mpvx.com, rztk6mpvx.com];in1.fun → [in1.fun]。"""
    host = (host or "").lower().strip(".")
    parts = host.split(".") if host else []
    return [".".join(parts[i:]) for i in range(len(parts) - 1)]


def parse_landing_campaign(html: str) -> tuple:
    """从「中间营销落地页」提取真站信息,返回 (merchant, affiliate, [真站base...])。

    短信短链(cutt.ly)并不直接落到白标站本体,而是落到一张营销页(如 www.7aa88.vip),
    页面内嵌 campaign 配置 JSON,含权威的:
      "merchantCode":"7aamxns1"          商户号
      "agentName":"7aadx16"              推广码(= affiliateCode)
      "redirectDomains":["https://www.7aamx.xyz", ...]   真站马甲域轮换池
    真站域随时增删,读页面比硬编码域名表更跟得上;取不到时返回 (None, "", [])。
    """
    import re
    html = html or ""
    if len(html) > 400_000:      # 只在头部找,避免超大页正则开销
        html = html[:400_000]
    m = re.search(r'"merchantCode"\s*:\s*"([^"]+)"', html)
    merchant = m.group(1) if m else None
    m = re.search(r'"agentName"\s*:\s*"([^"]+)"', html)
    affiliate = m.group(1) if m else ""
    bases = []
    m = re.search(r'"redirectDomains"\s*:\s*\[([^\]]*)\]', html)
    if m:
        for d in re.findall(r'"(https?://[^"]+)"', m.group(1)):
            d = d.rstrip("/")
            if d not in bases:
                bases.append(d)
    return merchant, affiliate, bases


def looks_like_white_label(html: str) -> bool:
    """内容指纹:判断落地页是否本族白标(真站或其中间营销页),供域名未登记时自动路由到直连 API。

    两种形态各自的判据:
      真站   —— 首页骨架同时引用 /js/aboutMerchant.js 与 /js/encrypt.js(该白标的固定构建)
      中间页 —— campaign 配置里同时有 merchantCode 与 redirectDomains(真站域池)
    每个推广活动都会启用一个新的中间页域(7aa88/7aa69/7aa65/7aa13.vip ...),域名白名单穷举不过来,
    靠内容识别兜住:换域、上新活动都不必改代码。
    """
    h = html or ""
    if "aboutMerchant.js" in h and "encrypt.js" in h:
        return True
    merchant, _aff, bases = parse_landing_campaign(h)
    return bool(merchant and bases)


REGISTER_MODULE = "REG3"
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Mobile/15E148 Safari/604.1")

_RSA_EXP = 0x10001
_RND_CS = string.ascii_letters + string.digits


def _rnd(n: int = 16) -> str:
    return "".join(random.choice(_RND_CS) for _ in range(n))


def _des_ecb_pkcs7_b64(plaintext: str, key8: str) -> str:
    """单DES-ECB-Pkcs7 → base64。用 3DES 三段同密钥等价单DES(容器无 pycryptodome)。"""
    from cryptography.hazmat.primitives.ciphers import Cipher, modes
    try:
        from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
    except Exception:  # 旧版 cryptography
        from cryptography.hazmat.primitives.ciphers.algorithms import TripleDES
    key = key8.encode("latin1")[:8]
    data = plaintext.encode("utf-8")
    pad = 8 - (len(data) % 8)
    data += bytes([pad]) * pad
    enc = Cipher(TripleDES(key * 3), modes.ECB()).encryptor()
    return base64.b64encode(enc.update(data) + enc.finalize()).decode()


def _rsa_utils_encrypt(text: str, modulus_hex: str) -> str:
    """复刻 RSAUtils.encryptedString:bytes(text) 小端打包成整数, c=m^65537 mod n, 输出 hex。"""
    n = int(modulus_hex, 16)
    m = int.from_bytes(text.encode("latin1"), "little")
    h = format(pow(m, _RSA_EXP, n), "x")
    return ("0" + h) if len(h) % 2 else h


_CONS = "bcdfghjklmnpqrstvwxyz"
_VOWELS = "aeiou"

# 真人风词库:孟加拉常见罗马化名 + 通用英文名/词,用于拼出"像真人取的"账号密码,而非随机串。
_NAMES = [
    "rakib", "sumon", "shakib", "raju", "sakib", "karim", "rahim", "jamal", "hasan",
    "akash", "rana", "bappy", "mithun", "sojib", "rabbi", "nayem", "shanto", "riad",
    "fahim", "tanvir", "sabbir", "arif", "masud", "milon", "polash", "robin", "joy",
    "tania", "nadia", "sadia", "tisha", "muna", "sumi", "mim", "rumana", "shorna",
    "jonny", "alamin", "russel", "emon", "limon", "shuvo", "tuhin", "noyon", "biplob",
    "john", "mike", "david", "alex", "sam", "leo", "ryan", "tony", "jack", "kevin",
]
_PWORDS = [
    "dhaka", "bangla", "tiger", "king", "star", "lucky", "money", "football", "cricket",
    "winner", "gold", "royal", "power", "sun", "moon", "river", "ocean", "summer",
    "dream", "magic", "happy", "smart", "super", "rocket", "panda", "eagle", "lion",
]
# 自然数字尾:出生年/吉利数/常见尾巴(真人爱用)
_NUMS = (
    [str(y) for y in range(1985, 2011)]
    + ["123", "1234", "12345", "786", "111", "007", "99", "00", "21", "23", "01", "69", "88"]
)

# 西语(墨西哥)语料:MX 站用。孟加拉名出现在墨西哥站一眼假,故按站点地区换库。
_NAMES_ES = [
    "juan", "jose", "luis", "carlos", "miguel", "jorge", "ricardo", "eduardo", "fernando",
    "alejandro", "javier", "antonio", "manuel", "pedro", "raul", "sergio", "hector", "arturo",
    "cesar", "diego", "pablo", "andres", "oscar", "ivan", "rafael", "emilio", "santiago",
    "maria", "guadalupe", "ana", "rosa", "laura", "patricia", "karla", "brenda", "alondra",
    "fernanda", "lucia", "elena", "sofia", "valeria", "daniela", "gabriela", "monica",
    "chava", "beto", "lalo", "tono", "checo", "memo", "pepe", "paco", "nacho",
]
_PWORDS_ES = [
    "mexico", "azteca", "aguila", "tigre", "leon", "toro", "sol", "luna", "oro", "rey",
    "reina", "fuego", "suerte", "dinero", "campeon", "futbol", "chivas", "america", "cancun",
    "playa", "estrella", "corazon", "amigo", "fiesta", "guerrero", "jaguar", "puma", "norte",
]
_NUMS_ES = (
    [str(y) for y in range(1985, 2011)]
    + ["123", "1234", "12345", "111", "99", "00", "07", "10", "21", "23", "77", "88", "2024"]
)


def _corpus(locale: str = "bd"):
    """按站点地区取(名库, 词库, 数字尾库)。未知地区回落存量 bd 库。"""
    if (locale or "").lower() == "mx":
        return _NAMES_ES, _PWORDS_ES, _NUMS_ES
    return _NAMES, _PWORDS, _NUMS


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def _syllables(n_syl: int) -> str:
    """拼可发音音节(辅音+元音),作为词库之外的少数派变体。"""
    return "".join(random.choice(_CONS) + random.choice(_VOWELS) for _ in range(n_syl))


def _gen_username(locale: str = "bd") -> str:
    """生成拟人用户名:6-13位,^[a-zA-Z0-9]+$。主力用真人名+自然数字尾,辅以拼名/可发音变体,避免一眼假或清一色。

    locale 决定名库(bd=孟加拉罗马化名, mx=西语名),让账号看起来像该站真实用户。"""
    _names, _, _nums = _corpus(locale)
    style = random.random()
    if style < 0.55:
        # 真人名 + 自然数字(rakib95 / Sumon2018 / carlos1998)
        u = random.choice(_names) + (random.choice(_nums) if random.random() < 0.85 else "")
    elif style < 0.78:
        # 双名拼接(rakibhasan / joseluis),偶带短数字
        u = random.choice(_names) + random.choice(_names)
        if random.random() < 0.4:
            u += random.choice(["1", "12", "7", "99", "23"])
    elif style < 0.92:
        # 名 + 短可发音尾(rakibny / carlosda),更杂避免名库被识别
        u = random.choice(_names) + _syllables(random.randint(1, 2))
        if random.random() < 0.5:
            u += str(random.randint(1, 99))
    else:
        # 少数可发音随机(防止全是词库名)
        u = _syllables(random.randint(2, 4)) + (str(random.randint(1, 999)) if random.random() < 0.6 else "")
    # 约 35% 首字母大写(真人常见)
    if random.random() < 0.35:
        u = _cap(u)
    u = u[:13]
    while len(u) < 6:
        u += random.choice(string.ascii_lowercase + string.digits)
    return u


def _gen_password(locale: str = "bd") -> str:
    """生成拟人密码:6-12位,^[a-zA-Z0-9]+$,含大小写+数字。主力为「首字母大写词/名 + 数字」(Dhaka2018 / Suerte99)。"""
    _names, _pwords, _nums = _corpus(locale)
    for _ in range(12):
        style = random.random()
        if style < 0.6:
            # 大写词 + 数字(Tiger2019 / Azteca88)
            p = _cap(random.choice(_pwords)) + random.choice(_nums)
        elif style < 0.85:
            # 大写名 + 数字(Rakib1998 / Carlos1998)
            p = _cap(random.choice(_names)) + random.choice(_nums)
        else:
            # 词 + 大写词(无数字时补一位)(tigerKing7)
            p = random.choice(_pwords) + _cap(random.choice(_pwords))
            if not any(c.isdigit() for c in p):
                p += str(random.randint(1, 99))
        p = p[:12]
        if 6 <= len(p) <= 12 and any(c.islower() for c in p) and any(c.isupper() for c in p) and any(c.isdigit() for c in p):
            return p
    # 兜底:保证一定产出合规密码
    return _cap(random.choice(_pwords)) + str(random.randint(1985, 2010))


def to_bd_mobile(phone: str) -> Optional[str]:
    """收件号 → BD 本地 11 位手机号(01XXXXXXXXX)。非合法 BD 号返回 None。"""
    import re
    d = re.sub(r"\D", "", phone or "")
    if d.startswith("880"):
        d = d[3:]
    if d.startswith("0"):
        d = d[1:]
    # BD 移动号:运营商前缀 1[3-9] + 8 位 = 10 位;补前导 0 成 11 位
    if len(d) == 10 and d[0] == "1":
        return "0" + d
    return None


def to_mx_mobile(phone: str) -> Optional[str]:
    """收件号 → MX 本地 10 位手机号(区号+号码,如 +5215512345678 → 5512345678)。非合法返回 None。

    墨西哥历史上移动号带 1 前缀(52 1 XXXXXXXXXX),要剥掉才是站点要的 10 位。"""
    import re
    d = re.sub(r"\D", "", phone or "")
    if d.startswith("00"):
        d = d[2:]
    if d.startswith("52") and len(d) > 10:
        d = d[2:]
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    # MX 区号首位 2-9(无前导 0)
    if len(d) == 10 and d[0] in "23456789":
        return d
    return None


def to_local_mobile(phone: str, locale: str = "bd") -> Optional[str]:
    """收件号 → 站点 mobileNum 要的本地号。未知地区回落 bd 规则(存量行为不变)。"""
    if (locale or "").lower() == "mx":
        return to_mx_mobile(phone)
    return to_bd_mobile(phone)


def _client(proxy_config: Optional[dict]) -> httpx.Client:
    kw = {"timeout": 30.0, "verify": False, "follow_redirects": True,
          "headers": {"User-Agent": UA}}
    if proxy_config and proxy_config.get("server"):
        srv = proxy_config["server"]
        u, p = proxy_config.get("username"), proxy_config.get("password")
        if u and p and "://" in srv:
            sch, host = srv.split("://", 1)
            srv = f"{sch}://{u}:{p}@{host}"
        kw["proxies"] = srv
    return httpx.Client(**kw)


def phone_to_username(phone: str, locale: str = "bd") -> str:
    """点击号码 → 用户名(撞库:用真实号码建号)。优先按站点地区取本地号(BD 01XXXXXXXXX / MX 10位),
    取不到再退化为去符号截断到 13 位。"""
    import re
    local = to_local_mobile(phone, locale)
    if local:
        return local[:13]
    d = re.sub(r"\D", "", phone or "")
    if d.startswith("880"):
        d = "0" + d[3:]
    return d[:13]


def _verify_username_exists(cli, base, merchant, module, username) -> Optional[bool]:
    """查重核验:HTTP200 + success:false = 用户名已占用 = 账号确实已创建。
    返回 True(已建)/False(未建)/None(查不了)。

    必须先看状态码:用户名不合规(如超过 13 位)时站点返回 **HTTP 400 + success:false**,
    与"已占用"的响应体只差状态码。只看 success 会把参数错误误判成"账号已建",
    让失败的注册显示成核验通过。
    """
    try:
        vr = cli.get(f"{base}/wps/check/username?username={username}", headers={
            "Merchant": merchant, "Module-Id": module, "x-module-id": module, "Language": "EN"})
        if vr.status_code != 200:
            return None
        vj = vr.json()
        if "success" in vj:
            return vj.get("success") is False
    except Exception:
        pass
    return None


def register_via_api(url: str, proxy_config: Optional[dict] = None,
                     affiliate: str = "", config: Optional[dict] = None,
                     username: Optional[str] = None, mobile: Optional[str] = None,
                     country_code: str = "") -> dict:
    """对 in1.fun / 7aamx 等同族白标落地页直连注册。
    返回 {success, username, password, customer_id, base, verified, reason}。
    username 缺省随机(无固定特征);mobile=收件号则绑定为注册手机号(撞库,选填字段 mobileNum)。
    country_code 参与拟人语料/号码本地化选择(MX→西语名+10位号)。
    config(来自 water_register_scripts.steps,可在后台编辑):{merchant, module, register_path, name_locale}。"""
    from urllib.parse import urlparse
    # 清洗:落地 URL 常被拼上点击追踪短链(如 ...register|66c.eu),取 | 与空白前的真链
    url = (url or "").split("|", 1)[0].strip()
    short_host = (urlparse(url).hostname or "").lower()
    cfg = config or {}
    merchant = cfg.get("merchant") or merchant_for_host(short_host)
    module = cfg.get("module") or REGISTER_MODULE
    reg_path = cfg.get("register_path") or "/wps/member/register"
    # affiliateCode:调用方未显式传则从 URL 解析(子域或 query)
    affiliate = affiliate or extract_affiliate(url, short_host)

    with _client(proxy_config) as cli:
        # 1) 解析短链 → 真实落地基址(应对站点换域)
        r0 = cli.get(url)
        final_host = (urlparse(str(r0.url)).hostname or "").lower()
        base = f"{urlparse(str(r0.url)).scheme}://{urlparse(str(r0.url)).netloc}"
        # 2) 落地页自省:短链多半落在中间营销页(无 /wps 接口),据页面配置切到真站马甲域。
        #    页面里的 merchantCode/agentName 比域名表权威,域轮换时无需改代码。
        land_merchant, land_aff, land_bases = parse_landing_campaign(r0.text)
        #    (redirectDomains 只出现在营销页配置里,真站 SPA 骨架没有,故它本身就是判据)
        if land_bases:
            # 优先已登记的马甲域,否则按落地页给出的顺序
            base = next((b for b in land_bases if merchant_for_host(urlparse(b).hostname)), land_bases[0])
            final_host = (urlparse(base).hostname or "").lower()
        # 短链 host 匹配不到时用跳转后的真实落地域再匹配一次,避免错落 DEFAULT_MERCHANT 建到别家站
        merchant = merchant or merchant_for_host(final_host) or land_merchant or DEFAULT_MERCHANT
        # affiliateCode 决定这个号算不算客户业绩,必须取到。优先级:
        # 调用方显式 > 入参URL(?affiliateCode=/子域) > 短链跳转后的最终URL > 中间页 agentName。
        # 短链入参本身不带码,码在跳转后的 URL 或落地页配置里,少一层就丢归属。
        affiliate = affiliate or extract_affiliate(str(r0.url), final_host) or land_aff
        locale = locale_for(short_host, country_code, cfg)
        if not (cfg.get("name_locale") or cfg.get("locale")) and not _match_domain(short_host, LOCALE_BY_DOMAIN):
            locale = locale_for(final_host, country_code, cfg)

        # 3) 取 RSA 公钥模数(个别马甲域会下线/被墙,逐个候选域试)
        mod = ""
        for cand in [base] + [b for b in land_bases if b != base]:
            mod = cli.get(f"{cand}/wps/session/key/rsa",
                          headers={"Merchant": merchant, "Referer": cand + "/"}).text.strip().strip('"')
            if len(mod) >= 200:
                base = cand
                break
        if len(mod) < 200:
            return {"success": False, "reason": f"取RSA公钥失败: {mod[:80]}", "base": base}

        # 3) 组装加密注册请求(用户名/密码拟人;手机号绑收件号撞库)
        # 拟人用户名易与站点已有真实用户撞名 → 提交前用只读 check/username 预检,被占就换,
        # 避免把已解的 GeeTest 浪费在注定"用户名已占用"的提交上。
        if not username:
            username = _gen_username(locale)
            for _ in range(6):
                taken = _verify_username_exists(cli, base, merchant, module, username)
                if taken is not True:   # False=可用 / None=查不了 → 放行
                    break
                username = _gen_username(locale)
        password = _gen_password(locale)
        payload = {
            "username": username, "password": password, "confirmPassword": password,
            "affiliateCode": affiliate, "paymentPassword": "", "merchantCode": merchant,
        }
        mobile_local = to_local_mobile(mobile, locale) if mobile else None
        if mobile_local:
            payload["mobileNum"] = mobile_local
        headers = {
            "Content-Type": "application/json",
            "Merchant": merchant, "Module-Id": module, "x-module-id": module,
            "Language": "EN", "Origin": base, "Referer": base + "/m/register",
            "Accept": "application/json, text/plain, */*",
        }

        def _submit(pl):
            """每次提交用全新随机 r(DES密钥/RSA头),站点对重放敏感。"""
            rr = _rnd(16)
            des_b64 = _des_ecb_pkcs7_b64(json.dumps(pl, separators=(",", ":")), rr[:8])
            h = dict(headers, Encryption=_rsa_utils_encrypt(rr[::-1], mod))
            rsp = cli.put(f"{base}{reg_path}", content=des_b64, headers=h)
            try:
                return rsp, rsp.json()
            except Exception:
                return rsp, None

        resp, body = _submit(payload)

        # 4) GeeTest v4 拦截(errorCode 含 geetest / #1066):此时未建号,解出凭证后带 geetestValidateV4 重提交一次。
        #    不需要验证码的商户(如 in1.fun jilievof2)首提交即成功,不会触发求解,不产生打码成本。
        if body and not body.get("success") and "geetest" in str(body.get("errorCode", "")).lower():
            from app.workers.geetest_solver import solve_geetest_v4
            try:
                gt = cli.get(f"{base}/wps/captcha/geetest?product=register",
                             headers={"Merchant": merchant}).json().get("value", {}).get("gt")
            except Exception:
                gt = None
            gt = gt or cfg.get("captcha_id")
            val4 = solve_geetest_v4(gt, base) if gt else None
            if val4:
                payload["geetestValidateV4"] = val4
                resp, body = _submit(payload)
            elif not gt:
                return {"success": False, "username": username, "base": base,
                        "reason": "geetest: 无法获取 captcha_id"}
            else:
                return {"success": False, "username": username, "base": base,
                        "reason": "geetest: 验证码求解失败(检查 CAPSOLVER_API_KEY/余额)"}

        if body is None:
            return {"success": False, "username": username,
                    "reason": f"HTTP {resp.status_code}: {resp.text[:120]}", "base": base}
        if resp.status_code == 200 and body.get("success"):
            val = body.get("value") or {}
            # 核验:登录需 GeeTest 验证码无法纯自动登录,改用查重端点确认账号已存在
            verified = _verify_username_exists(cli, base, merchant, module, username)
            return {"success": True, "username": username, "password": password,
                    "customer_id": val.get("customerId"), "base": base, "mobile": mobile_local,
                    "verified": verified, "affiliate": affiliate, "merchant": merchant,
                    "reason": "ok"}
        return {"success": False, "username": username, "base": base, "affiliate": affiliate,
                "merchant": merchant,
                "reason": f"{body.get('errorCode')}: {body.get('message')}"[:160]}
