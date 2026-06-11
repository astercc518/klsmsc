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

# 短链域 → (商户号, 注册模块号)。base 由短链重定向实时解析,无需硬编码(应对站点换域)。
MERCHANT_BY_DOMAIN = {
    "in1.fun": "jilievof2",
}
DEFAULT_MERCHANT = "jilievof2"
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


def _gen_password() -> str:
    return "Kx" + "".join(random.choice(string.ascii_lowercase) for _ in range(4)) + str(random.randint(1000, 9999))


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
                     username: Optional[str] = None) -> dict:
    """对 in1.fun 系短链落地页直连注册。返回 {success, username, password, customer_id, base, verified, reason}。
    username 缺省随机;撞库场景由调用方传入「点击号码」派生的用户名。
    config(来自 water_register_scripts.steps,可在后台编辑):{merchant, module, register_path}。"""
    from urllib.parse import urlparse
    short_host = (urlparse(url).hostname or "").lower()
    cfg = config or {}
    merchant = cfg.get("merchant") or MERCHANT_BY_DOMAIN.get(short_host, DEFAULT_MERCHANT)
    module = cfg.get("module") or REGISTER_MODULE
    reg_path = cfg.get("register_path") or "/wps/member/register"

    with _client(proxy_config) as cli:
        # 1) 解析短链 → 真实落地基址(应对站点换域)
        r0 = cli.get(url)
        base = f"{urlparse(str(r0.url)).scheme}://{urlparse(str(r0.url)).netloc}"

        # 2) 取 RSA 公钥模数
        mod = cli.get(f"{base}/wps/session/key/rsa",
                      headers={"Merchant": merchant, "Referer": base + "/"}).text.strip().strip('"')
        if len(mod) < 200:
            return {"success": False, "reason": f"取RSA公钥失败: {mod[:80]}", "base": base}

        # 3) 组装加密注册请求(用户名:撞库用点击号码派生,缺省随机)
        username = username or ("kf" + _rnd(8).lower())
        password = _gen_password()
        r = _rnd(16)
        payload = {
            "username": username, "password": password, "confirmPassword": password,
            "affiliateCode": affiliate, "paymentPassword": "", "merchantCode": merchant,
        }
        des_b64 = _des_ecb_pkcs7_b64(json.dumps(payload, separators=(",", ":")), r[:8])
        enc_hex = _rsa_utils_encrypt(r[::-1], mod)
        headers = {
            "Content-Type": "application/json", "Encryption": enc_hex,
            "Merchant": merchant, "Module-Id": module, "x-module-id": module,
            "Language": "EN", "Origin": base, "Referer": base + "/m/register",
            "Accept": "application/json, text/plain, */*",
        }
        resp = cli.put(f"{base}{reg_path}", content=des_b64, headers=headers)

        try:
            body = resp.json()
        except Exception:
            return {"success": False, "username": username,
                    "reason": f"HTTP {resp.status_code}: {resp.text[:120]}", "base": base}
        if resp.status_code == 200 and body.get("success"):
            val = body.get("value") or {}
            # 4) 核验:登录需 GeeTest 验证码无法纯自动登录,改用查重端点确认账号已存在
            verified = _verify_username_exists(cli, base, merchant, module, username)
            return {"success": True, "username": username, "password": password,
                    "customer_id": val.get("customerId"), "base": base,
                    "verified": verified, "reason": "ok"}
        return {"success": False, "username": username, "base": base,
                "reason": f"{body.get('errorCode')}: {body.get('message')}"[:160]}
