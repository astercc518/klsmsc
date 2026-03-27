"""外呼名单导入工具单元测试。"""
from app.utils.voice_contact_import import (
    MAX_VOICE_CONTACTS_PER_IMPORT,
    normalize_e164_phone,
    parse_phones_from_csv_bytes,
)


def test_normalize_e164_adds_plus():
    assert normalize_e164_phone("8613800138000") == "+8613800138000"
    assert normalize_e164_phone("+8613800138000") == "+8613800138000"


def test_normalize_empty():
    assert normalize_e164_phone("") == ""
    assert normalize_e164_phone("   ") == ""


def test_parse_csv_skips_header():
    raw = b"phone\n+8613800138000\n+8613800138001\n"
    assert parse_phones_from_csv_bytes(raw) == ["+8613800138000", "+8613800138001"]


def test_parse_csv_no_header():
    raw = b"+861\n+862\n"
    assert parse_phones_from_csv_bytes(raw) == ["+861", "+862"]


def test_max_rows_cap():
    lines = "\n".join([f"+8613800{i:05d}" for i in range(MAX_VOICE_CONTACTS_PER_IMPORT + 50)])
    out = parse_phones_from_csv_bytes(lines.encode("utf-8"))
    assert len(out) == MAX_VOICE_CONTACTS_PER_IMPORT
