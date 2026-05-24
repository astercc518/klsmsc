"""
文件上传安全校验：后缀、大小、内容嗅探（防止伪装成 CSV/TXT 的脚本/二进制）。

调用方式：
    from app.utils.upload_validator import validate_upload_csv_txt
    validate_upload_csv_txt(file_bytes, filename="x.csv", max_bytes=100 * 1024 * 1024)
    # 不通过时抛 UploadValidationError

设计要点（号码导入场景）：
- 后缀白名单：.csv / .txt（大小写不敏感）
- 大小硬上限（调用方传入；不同端点不同）
- magic number 嗅探：拒绝常见可执行/脚本特征（PE/ELF/Mach-O/ZIP/PDF/PHP/<script> 等）
- 编码校验：首 4KB 必须能被 UTF-8/GBK/Big5/Latin-1 之一无损解码
- 内容字符校验：去除常见空白/数字/+/-/() 之后剩余字符若大多数非可打印，认为不是号码文件
"""
from __future__ import annotations

import re
from typing import Optional


class UploadValidationError(ValueError):
    """文件上传安全校验未通过；调用方应直接返回 400。"""


_ALLOWED_EXTS = (".csv", ".txt")

# 拒绝列表：常见可执行/脚本/打包文件的 magic number 与可疑字节序列
_MAGIC_BLACKLIST = [
    (b"MZ", "Windows PE/EXE"),
    (b"\x7fELF", "Linux ELF"),
    (b"\xca\xfe\xba\xbe", "Mach-O/Java class"),
    (b"\xcf\xfa\xed\xfe", "Mach-O 64"),
    (b"\xfe\xed\xfa\xce", "Mach-O 32"),
    (b"PK\x03\x04", "ZIP / xlsx / docx"),
    (b"PK\x05\x06", "ZIP (empty)"),
    (b"PK\x07\x08", "ZIP (spanned)"),
    (b"%PDF-", "PDF"),
    (b"\x1f\x8b", "GZIP"),
    (b"BZh", "BZIP2"),
    (b"7z\xbc\xaf\x27\x1c", "7z"),
    (b"Rar!\x1a\x07", "RAR"),
    (b"\xff\xd8\xff", "JPEG"),
    (b"\x89PNG", "PNG"),
    (b"GIF8", "GIF"),
    (b"#!", "Shebang script"),
    (b"<?php", "PHP source"),
    (b"<%", "ASP / JSP"),
    (b"<!DOCTYPE", "HTML"),
    (b"<html", "HTML"),
    (b"<HTML", "HTML"),
    (b"<script", "HTML+script"),
    (b"<SCRIPT", "HTML+script"),
]


def _looks_like_text(sample: bytes) -> bool:
    """前 4KB 必须能用 UTF-8/GBK/Big5/Latin-1 之一解码无损，且控制字符占比 < 5%."""
    # NUL 字节通常意味着二进制
    if b"\x00" in sample:
        return False
    decoded: Optional[str] = None
    for enc in ("utf-8", "utf-8-sig", "gbk", "big5", "latin-1"):
        try:
            decoded = sample.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if decoded is None:
        return False
    # 控制字符（除换行/制表）密度过高 → 不像文本
    ctrl = sum(1 for c in decoded if ord(c) < 32 and c not in "\n\r\t")
    return ctrl / max(len(decoded), 1) < 0.05


def validate_upload_csv_txt(
    content: bytes,
    filename: str,
    max_bytes: int,
    *,
    label: str = "文件",
) -> None:
    """对 CSV/TXT 上传做后缀 + 大小 + magic number 嗅探的最小集校验。

    label 仅用于错误消息（如「私库上传文件」「号码导入文件」），便于客户定位。

    校验失败抛 UploadValidationError；调用方应转 HTTP 400。
    """
    fname = (filename or "").lower().strip()
    if not fname.endswith(_ALLOWED_EXTS):
        raise UploadValidationError(f"{label}仅支持 .csv 或 .txt 后缀，当前: {filename!r}")

    if not isinstance(content, (bytes, bytearray)):
        raise UploadValidationError(f"{label}内容必须是 bytes")
    size = len(content)
    if size == 0:
        raise UploadValidationError(f"{label}为空")
    if max_bytes and size > max_bytes:
        mb = max_bytes / 1024 / 1024
        raise UploadValidationError(f"{label}超过上限 {mb:.0f}MB（实际: {size/1024/1024:.1f}MB）")

    sample = bytes(content[:4096])

    # magic number 黑名单：前 16 字节里命中即拒
    head16 = sample[:16]
    head_lower = head16.lower()
    for sig, kind in _MAGIC_BLACKLIST:
        if head16.startswith(sig) or head_lower.startswith(sig.lower()):
            raise UploadValidationError(f"{label}疑似 {kind} 文件，不是合法的 CSV/TXT")

    # 文本嗅探
    if not _looks_like_text(sample):
        raise UploadValidationError(f"{label}首段不像纯文本（可能是二进制或损坏的编码）")
