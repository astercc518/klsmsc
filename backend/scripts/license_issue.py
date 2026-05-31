#!/usr/bin/env python3
"""
签发授权 .lic(厂商侧,需私钥)。

签名算法/规范化必须与 app.core.license.verify_blob 完全一致:
  sig = Ed25519(私钥, json.dumps(payload, sort_keys=True, separators=(',',':'), ensure_ascii=False))
  .lic = base64( json{"payload":payload, "sig":base64(sig)} )

用法示例:
  # 私有部署买断(绑定客户机器指纹、永久):
  docker compose exec -w /app api python scripts/license_issue.py \
    --customer "广州XX科技" --edition private --expires perpetual \
    --fingerprint fp_xxxxxxxx --out /app/.secrets/xx.lic

  # OEM 白标(带品牌、年付到期、30天宽限):
  docker compose exec -w /app api python scripts/license_issue.py \
    --customer "出海通" --edition oem --expires 2027-05-31 --grace-days 30 \
    --fingerprint fp_xxxx --brand-name "出海通短信" --brand-logo "data:image/png;base64,..." \
    --out /app/.secrets/oem.lic

  # SaaS(我方托管、不绑机器):
  docker compose exec -w /app api python scripts/license_issue.py \
    --customer "自营SaaS" --edition saas --expires 2027-01-01 --unbound \
    --out /app/.secrets/saas.lic
"""
import argparse
import base64
import json
import secrets
from datetime import date, datetime

from cryptography.hazmat.primitives import serialization as ser


def canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer", required=True, help="客户名称")
    ap.add_argument("--edition", required=True, choices=["saas", "private", "oem"])
    ap.add_argument("--expires", required=True, help="到期日 YYYY-MM-DD,或 perpetual=永久")
    ap.add_argument("--fingerprint", default="", help="绑定的机器指纹(private/oem 必填)")
    ap.add_argument("--unbound", action="store_true", help="不绑定机器(SaaS 用)")
    ap.add_argument("--grace-days", type=int, default=0, help="到期后宽限天数")
    ap.add_argument("--brand-name", default=None, help="OEM 品牌名称")
    ap.add_argument("--brand-logo", default=None, help="OEM 品牌 logo(URL 或 data:image base64)")
    ap.add_argument("--private-key", default="/app/.secrets/license_private_key.pem")
    ap.add_argument("--out", required=True, help="输出 .lic 路径")
    args = ap.parse_args()

    fp = "" if args.unbound else (args.fingerprint or "").strip()
    if args.edition in ("private", "oem") and not fp:
        raise SystemExit("private/oem 必须 --fingerprint(或显式 --unbound)")

    if args.expires.lower() in ("perpetual", "none", "null", ""):
        expires_at = None
    else:
        expires_at = date.fromisoformat(args.expires).isoformat()

    brand = None
    if args.brand_name or args.brand_logo:
        brand = {"name": args.brand_name, "logo": args.brand_logo}

    payload = {
        "license_id": "lic_" + secrets.token_hex(8),
        "customer": args.customer,
        "edition": args.edition,
        "issued_at": datetime.utcnow().date().isoformat(),
        "expires_at": expires_at,
        "machine_fingerprint": fp,
        "grace_days": int(args.grace_days),
        "brand": brand,
        "limits": {},  # 预留,本期不强制
        "nonce": secrets.token_hex(8),
    }

    with open(args.private_key, "rb") as f:
        priv = ser.load_pem_private_key(f.read(), password=None)
    sig = priv.sign(canonical(payload))

    lic = base64.b64encode(json.dumps(
        {"payload": payload, "sig": base64.b64encode(sig).decode()},
        ensure_ascii=False,
    ).encode("utf-8")).decode()

    with open(args.out, "w") as f:
        f.write(lic + "\n")

    print(f"已签发: {args.out}")
    print(f"  客户={args.customer} edition={args.edition} 到期={expires_at or '永久'} "
          f"指纹={'(不绑定)' if not fp else fp} 宽限={args.grace_days}天")
    print("把该 .lic 内容交客户在后台『授权管理』上传即可。")


if __name__ == "__main__":
    main()
