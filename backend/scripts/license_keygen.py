#!/usr/bin/env python3
"""
生成 Ed25519 授权密钥对(一次性,厂商侧)。

- 私钥 PEM 写到 --out-private(默认 /app/.secrets/license_private_key.pem),【离线保管,严禁入库】。
- 公钥 base64 打印出来,需内嵌进 backend/app/core/license.py 的 _DEFAULT_PUBLIC_KEY_B64。

用法:
  docker compose exec -w /app api python scripts/license_keygen.py
"""
import argparse
import base64
import os

from cryptography.hazmat.primitives import serialization as ser
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-private", default="/app/.secrets/license_private_key.pem")
    args = ap.parse_args()

    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()

    os.makedirs(os.path.dirname(args.out_private), exist_ok=True)
    pem = priv.private_bytes(
        encoding=ser.Encoding.PEM,
        format=ser.PrivateFormat.PKCS8,
        encryption_algorithm=ser.NoEncryption(),
    )
    with open(args.out_private, "wb") as f:
        f.write(pem)
    os.chmod(args.out_private, 0o600)

    pub_b64 = base64.b64encode(
        pub.public_bytes(encoding=ser.Encoding.Raw, format=ser.PublicFormat.Raw)
    ).decode()

    print(f"私钥已写: {args.out_private}  (离线保管,勿入库)")
    print("公钥(base64)→ 内嵌 core/license.py 的 _DEFAULT_PUBLIC_KEY_B64:")
    print(pub_b64)


if __name__ == "__main__":
    main()
