"""phone_utils 通道级号码格式化"""
import pytest

from app.utils.phone_utils import format_sms_dest_phone, strip_leading_plus_enabled


@pytest.mark.unit
@pytest.mark.parametrize(
    "cfg,expected",
    [
        (None, True),
        ({}, True),
        ({"strip_leading_plus": True}, True),
        ({"strip_leading_plus": False}, False),
        ({"strip_leading_plus": 0}, False),
        ({"strip_leading_plus": "false"}, False),
        ({"strip_leading_plus": "0"}, False),
        ({"strip_leading_plus": "off"}, False),
    ],
)
def test_strip_leading_plus_enabled(cfg, expected):
    assert strip_leading_plus_enabled(cfg) is expected


@pytest.mark.unit
def test_format_sms_dest_phone_toggle():
    assert format_sms_dest_phone("+8613800138000", strip_leading_plus=True) == "8613800138000"
    assert format_sms_dest_phone("+8613800138000", strip_leading_plus=False) == "+8613800138000"
    assert format_sms_dest_phone("8613800138000", strip_leading_plus=True) == "8613800138000"
