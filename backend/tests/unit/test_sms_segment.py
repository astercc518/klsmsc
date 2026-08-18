from app.utils.sms_segment import (
    count_sms_parts,
    gsm7_septet_count,
    normalize_for_sms_segment_count,
    sanitize_sms_text_for_wire,
    utf16_code_unit_count,
)


def test_french_gsm7_message_is_one_standard_segment():
    message = (
        "Tradingdecryptomonnaiesquantitatifpilotéparl'IA "
        "avecdesrendementsquotidiensde3%à5%.Réservez dèsmaintenant : "
        "https://chat.whatsapp.com/Lau2wJe7EhhLAVhkQalEz1"
    )
    norm = normalize_for_sms_segment_count(message)
    assert gsm7_septet_count(norm) == 156
    assert count_sms_parts(message) == 1


def test_gsm7_extension_characters_consume_two_septets():
    assert gsm7_septet_count("{" * 80) == 160
    assert count_sms_parts("{" * 80) == 1
    assert count_sms_parts("{" * 81) == 2


def test_unicode_billing_counts_utf16_code_units():
    assert utf16_code_unit_count("中" * 70) == 70
    assert count_sms_parts("中" * 70) == 1
    assert count_sms_parts("中" * 71) == 2

    # Emoji is one Unicode code point but two UTF-16 code units.
    assert utf16_code_unit_count("😀" * 35) == 70
    assert count_sms_parts("😀" * 35) == 1
    assert count_sms_parts("😀" * 36) == 2
    assert count_sms_parts("😀" * 68) == 3


# ---------------------------------------------------------------------------
# 上行正文规范化：清洗只该在「能换回 GSM-7」时发生。
# 回归自 TS_066_zhilian(ch82) 事故：泰文文案里的 en-dash 被改写成 hyphen，
# 与上游逐字节加白的模板对不上，47631 条整批回 SMPP status=1。
# ---------------------------------------------------------------------------

_TH_WHITELISTED = "ของขวัญสำหรับสมาชิก! รับฟรี 699–6,999 วันนี้! ln.run/VUaO6"


def test_ucs2_body_keeps_en_dash_byte_for_byte():
    # 泰文本就是 UCS-2，替换 en-dash 一条也省不下来，却会顶掉上游模板匹配。
    assert sanitize_sms_text_for_wire(_TH_WHITELISTED) == _TH_WHITELISTED
    assert "–" in sanitize_sms_text_for_wire(_TH_WHITELISTED)


def test_en_dash_rewrite_still_applies_when_it_buys_gsm7():
    # 肉眼英文 + en-dash：不清洗就会计费 1 条、上游按 UCS-2 收 2 条。
    message = "Bonus 699–6,999 today! ln.run/VUaO6"
    wire = sanitize_sms_text_for_wire(message)
    assert wire == "Bonus 699-6,999 today! ln.run/VUaO6"
    assert gsm7_septet_count(wire) is not None


def test_ucs2_body_still_strips_length_changing_noise():
    # 零宽/省略号会改变 UCS-2 码元数，必须与计费口径一起清掉，否则条数错位。
    assert sanitize_sms_text_for_wire("รับฟรี\u200b\u200b 99") == "รับฟรี 99"
    assert sanitize_sms_text_for_wire("รับฟรี… 99") == "รับฟรี... 99"


def test_wire_length_always_matches_billing_normalization():
    for message in (
        _TH_WHITELISTED,
        "Bonus 699–6,999 today!",
        "รับฟรี… 99 บาท",
        "Get your “free” bonus – now",
        "中文\u200b促销 99–999",
    ):
        wire = sanitize_sms_text_for_wire(message)
        billed = normalize_for_sms_segment_count(message)
        assert utf16_code_unit_count(wire) == utf16_code_unit_count(billed)
        assert count_sms_parts(wire) == count_sms_parts(message)
        assert sanitize_sms_text_for_wire(wire) == wire  # 幂等
