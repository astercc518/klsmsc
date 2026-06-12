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
}
DEFAULT_MERCHANT = "jilievof2"


def merchant_for_host(host: str) -> Optional[str]:
    """host → 商户号:先精确匹配,再按可注册主域后缀匹配。匹配不到返回 None。"""
    host = (host or "").lower().strip(".")
    if not host:
        return None
    if host in MERCHANT_BY_DOMAIN:
        return MERCHANT_BY_DOMAIN[host]
    for dom, mc in MERCHANT_BY_DOMAIN.items():
        if host == dom or host.endswith("." + dom):
            return mc
    return None


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


def _syllables(n_syl: int) -> str:
    """拼可发音音节(辅音+元音),像真人取的名。"""
    return "".join(random.choice(_CONS) + random.choice(_VOWELS) for _ in range(n_syl))


def _gen_username() -> str:
    """生成无固定特征的用户名:6-13位,^[a-zA-Z0-9]+$,多风格混合,避免一眼识别为机器号。"""
    style = random.random()
    if style < 0.5:
        # 可发音名 + 可选数字尾(最像真人)
        u = _syllables(random.randint(2, 4))
        if random.random() < 0.7:
            u += str(random.randint(1, 9999))
    elif style < 0.8:
        # 词 + 数字穿插
        u = _syllables(random.randint(2, 3)) + str(random.randint(10, 999))
        if random.random() < 0.4:
            u += random.choice(_VOWELS) + random.choice(_CONS)
    else:
        # 纯随机字母数字(首位字母)
        ln = random.randint(7, 12)
        u = random.choice(string.ascii_lowercase) + "".join(
            random.choice(string.ascii_lowercase + string.digits) for _ in range(ln - 1))
    # 约 30% 首字母大写(真人常见)
    if random.random() < 0.3:
        u = u[0].upper() + u[1:]
    # 收敛长度到 [6,13]
    u = u[:13]
    while len(u) < 6:
        u += random.choice(string.ascii_lowercase + string.digits)
    return u


def _gen_password() -> str:
    """无固定特征密码:8-12位,纯字母数字,保证含大写/小写/数字各≥1,位置随机。"""
    ln = random.randint(8, 12)
    pool = string.ascii_letters + string.digits
    while True:
        p = "".join(random.choice(pool) for _ in range(ln))
        if any(c.islower() for c in p) and any(c.isupper() for c in p) and any(c.isdigit() for c in p):
            return p


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


def phone_to_username(phone: str) -> str:
    """点击号码 → 用户名(撞库:用真实号码建号)。去非数字;BD 国码 880 转本地 0 前缀;截断到13位。"""
    import re
    d = re.sub(r"\D", "", phone or "")
    if d.startswith("880"):
        d = "0" + d[3:]
    return d[:13]


def _verify_username_exists(cli, base, merchant, module, username) -> Optional[bool]:
    """查重核验:success:false=用户名已占用=账号确实已创建。返回 True(已建)/False(未建)/None(查不了)。"""
    try:
        vr = cli.get(f"{base}/wps/check/username?username={username}", headers={
            "Merchant": merchant, "Module-Id": module, "x-module-id": module, "Language": "EN"})
        vj = vr.json()
        if "success" in vj:
            return vj.get("success") is False
    except Exception:
        pass
    return None


def register_via_api(url: str, proxy_config: Optional[dict] = None,
                     affiliate: str = "", config: Optional[dict] = None,
                     username: Optional[str] = None, mobile: Optional[str] = None) -> dict:
    """对 in1.fun 系短链落地页直连注册。返回 {success, username, password, customer_id, base, verified, reason}。
    username 缺省随机(无固定特征);mobile=收件号则绑定为注册手机号(撞库,选填字段 mobileNum)。
    config(来自 water_register_scripts.steps,可在后台编辑):{merchant, module, register_path}。"""
    from urllib.parse import urlparse
    # 清洗:落地 URL 常被拼上点击追踪短链(如 ...register|66c.eu),取 | 与空白前的真链
    url = (url or "").split("|", 1)[0].strip()
    short_host = (urlparse(url).hostname or "").lower()
    cfg = config or {}
    merchant = cfg.get("merchant") or merchant_for_host(short_host) or DEFAULT_MERCHANT
    module = cfg.get("module") or REGISTER_MODULE
    reg_path = cfg.get("register_path") or "/wps/member/register"
    # affiliateCode:调用方未显式传则从 URL 解析(子域或 query)
    affiliate = affiliate or extract_affiliate(url, short_host)

    with _client(proxy_config) as cli:
        # 1) 解析短链 → 真实落地基址(应对站点换域)
        r0 = cli.get(url)
        base = f"{urlparse(str(r0.url)).scheme}://{urlparse(str(r0.url)).netloc}"

        # 2) 取 RSA 公钥模数
        mod = cli.get(f"{base}/wps/session/key/rsa",
                      headers={"Merchant": merchant, "Referer": base + "/"}).text.strip().strip('"')
        if len(mod) < 200:
            return {"success": False, "reason": f"取RSA公钥失败: {mod[:80]}", "base": base}

        # 3) 组装加密注册请求(用户名/密码无固定特征;手机号绑收件号撞库)
        username = username or _gen_username()
        password = _gen_password()
        payload = {
            "username": username, "password": password, "confirmPassword": password,
            "affiliateCode": affiliate, "paymentPassword": "", "merchantCode": merchant,
        }
        mobile_local = to_bd_mobile(mobile) if mobile else None
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
                    "verified": verified, "reason": "ok"}
        return {"success": False, "username": username, "base": base,
                "reason": f"{body.get('errorCode')}: {body.get('message')}"[:160]}
