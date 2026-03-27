"""外呼名单导入：号码规范化与 CSV 首列解析。"""
from __future__ import annotations

import csv
import io
from typing import List

# 与单次 JSON 导入、CSV 行数上限一致
MAX_VOICE_CONTACTS_PER_IMPORT = 10000


def normalize_e164_phone(s: str) -> str:
    """将一行文本规范为带 + 的 E.164 形式（宽松）。"""
    phone = (s or "").strip()
    if not phone:
        return ""
    if not phone.startswith("+"):
        phone = "+" + phone.lstrip("+")
    return phone


def parse_phones_from_csv_bytes(raw: bytes) -> List[str]:
    """
    解析 CSV：默认取每行第一列为号码；首行若为表头（phone/mobile 等）则跳过。
    最多返回 MAX_VOICE_CONTACTS_PER_IMPORT 条。
    """
    text = raw.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    out: List[str] = []
    for i, row in enumerate(reader):
        if not row:
            continue
        cell = (row[0] or "").strip()
        if not cell:
            continue
        low = cell.lower()
        if i == 0 and low in ("phone", "mobile", "e164", "号码", "电话", "手机号"):
            continue
        out.append(cell)
        if len(out) >= MAX_VOICE_CONTACTS_PER_IMPORT:
            break
    return out
