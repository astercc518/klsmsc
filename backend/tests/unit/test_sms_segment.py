from app.utils.sms_segment import (
    count_sms_parts,
    gsm7_septet_count,
    normalize_for_sms_segment_count,
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
