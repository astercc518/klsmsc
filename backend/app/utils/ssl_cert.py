"""
SSL 证书校验工具

用于「短链域名」UI 上传 Cloudflare Origin Cert 时的预校验：
- PEM / KEY 格式合法性
- 公钥指纹一致（key 与 cert 配对）
- 证书未过期
- 提取 SAN（用于前端展示「这张证书覆盖了哪些域名」）
"""
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import load_pem_private_key


class CertValidationError(Exception):
    pass


def parse_cert(pem: str) -> x509.Certificate:
    if not pem or "BEGIN CERTIFICATE" not in pem:
        raise CertValidationError("证书内容不是合法的 PEM 格式（缺少 -----BEGIN CERTIFICATE----- 头）")
    try:
        return x509.load_pem_x509_certificate(pem.encode("utf-8"))
    except Exception as e:
        raise CertValidationError(f"证书解析失败: {e}")


def parse_key(pem: str):
    if not pem or "PRIVATE KEY" not in pem:
        raise CertValidationError("私钥内容不是合法的 PEM 格式（缺少 -----BEGIN PRIVATE KEY----- 头）")
    try:
        return load_pem_private_key(pem.encode("utf-8"), password=None)
    except Exception as e:
        raise CertValidationError(f"私钥解析失败: {e}")


def public_key_fingerprint(key_or_cert) -> str:
    """SHA256 of DER-encoded public key (sufficient for matching cert <-> key)."""
    if hasattr(key_or_cert, "public_key"):
        pub = key_or_cert.public_key()
    else:
        pub = key_or_cert
    der = pub.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    digest = hashes.Hash(hashes.SHA256())
    digest.update(der)
    return digest.finalize().hex()


def extract_sans(cert: x509.Certificate) -> List[str]:
    try:
        ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        sans = ext.value.get_values_for_type(x509.DNSName)
        return list(sans)
    except x509.ExtensionNotFound:
        return []


def cert_summary(cert: x509.Certificate) -> Dict:
    sans = extract_sans(cert)
    not_before = cert.not_valid_before_utc if hasattr(cert, "not_valid_before_utc") else cert.not_valid_before.replace(tzinfo=timezone.utc)
    not_after = cert.not_valid_after_utc if hasattr(cert, "not_valid_after_utc") else cert.not_valid_after.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    days_until_expiry = (not_after - now).days

    issuer_cn = ""
    try:
        for attr in cert.issuer:
            if attr.oid == x509.NameOID.COMMON_NAME:
                issuer_cn = attr.value
                break
    except Exception:
        pass

    return {
        "sans": sans,
        "issuer": issuer_cn,
        "not_before": not_before.isoformat(),
        "not_after": not_after.isoformat(),
        "days_until_expiry": days_until_expiry,
        "expired": days_until_expiry < 0,
        "fingerprint_sha256": cert.fingerprint(hashes.SHA256()).hex(),
    }


def validate_cert_and_key(cert_pem: str, key_pem: str) -> Tuple[x509.Certificate, Dict]:
    """
    校验证书与私钥配对有效。

    Returns:
        (cert, summary_dict)

    Raises:
        CertValidationError: 任何一步校验失败
    """
    cert = parse_cert(cert_pem)
    key = parse_key(key_pem)

    # 公钥指纹比对
    cert_fp = public_key_fingerprint(cert)
    key_fp = public_key_fingerprint(key)
    if cert_fp != key_fp:
        raise CertValidationError("私钥与证书不匹配（公钥指纹不一致）")

    summary = cert_summary(cert)
    if summary["expired"]:
        raise CertValidationError(
            f"证书已过期（not_after={summary['not_after']}）"
        )
    if not summary["sans"]:
        raise CertValidationError("证书没有 SAN 扩展，无法用于多域名 SNI 路由")

    return cert, summary
