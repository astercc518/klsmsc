"""
电话号码解析器单元测试
"""
import pytest
from app.core.phone_parser import PhoneNumberParser


@pytest.mark.unit
def test_parse_valid_phone_number():
    """测试解析有效电话号码"""
    result = PhoneNumberParser.parse("+8613800138000")
    
    assert result['valid'] is True
    assert result['country_code'] == "CN"
    assert result['e164_format'] == "+8613800138000"


@pytest.mark.unit
def test_parse_invalid_phone_number():
    """测试解析无效电话号码"""
    result = PhoneNumberParser.parse("123")
    
    assert result['valid'] is False
    assert 'error' in result


@pytest.mark.unit
def test_parse_us_phone():
    """测试解析美国电话号码"""
    result = PhoneNumberParser.parse("+12025551234")
    
    assert result['valid'] is True
    assert result['country_code'] == "US"
