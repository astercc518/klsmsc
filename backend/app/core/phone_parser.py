"""
电话号码解析模块
"""
import phonenumbers
from phonenumbers import geocoder, carrier
from typing import Dict, Optional
from app.utils.errors import InvalidPhoneNumberError
from app.utils.logger import get_logger

logger = get_logger(__name__)


class PhoneNumberParser:
    """电话号码解析器"""
    
    @staticmethod
    def parse(phone_number: str, default_region: Optional[str] = None) -> Dict:
        """
        解析电话号码
        
        Args:
            phone_number: 电话号码
            default_region: 默认国家代码 (如果号码不包含国际前缀)
            
        Returns:
            {
                'valid': bool,
                'country_code': str,
                'country_name': str,
                'operator': str,
                'e164_format': str,
                'national_format': str,
                'international_format': str
            }
            
        Raises:
            InvalidPhoneNumberError: 号码无效
        """
        try:
            # 解析号码
            parsed = phonenumbers.parse(phone_number, default_region)
            
            # 验证有效性
            is_valid = phonenumbers.is_valid_number(parsed)
            
            if not is_valid:
                logger.warning(f"无效的电话号码: {phone_number}")
                raise InvalidPhoneNumberError(phone_number)
            
            # 获取国家代码
            country_code = phonenumbers.region_code_for_number(parsed)
            
            # 获取国家名称
            country_name = geocoder.description_for_number(parsed, "zh")
            
            # 获取运营商（可能为空）
            operator = carrier.name_for_number(parsed, "en")
            
            # E.164格式（国际标准格式）
            e164_format = phonenumbers.format_number(
                parsed, 
                phonenumbers.PhoneNumberFormat.E164
            )
            
            # 本地格式
            national_format = phonenumbers.format_number(
                parsed,
                phonenumbers.PhoneNumberFormat.NATIONAL
            )
            
            # 国际格式
            international_format = phonenumbers.format_number(
                parsed,
                phonenumbers.PhoneNumberFormat.INTERNATIONAL
            )
            
            result = {
                'valid': True,
                'country_code': country_code,
                'country_name': country_name,
                'operator': operator or 'Unknown',
                'e164_format': e164_format,
                'national_format': national_format,
                'international_format': international_format
            }
            
            logger.debug(f"号码解析成功: {phone_number} -> {result}")
            return result
            
        except phonenumbers.phonenumberutil.NumberParseException as e:
            logger.error(f"号码解析失败: {phone_number}, 错误: {str(e)}")
            raise InvalidPhoneNumberError(phone_number)
    
    @staticmethod
    def is_valid(phone_number: str, default_region: Optional[str] = None) -> bool:
        """
        检查电话号码是否有效
        
        Args:
            phone_number: 电话号码
            default_region: 默认国家代码
            
        Returns:
            是否有效
        """
        try:
            parsed = phonenumbers.parse(phone_number, default_region)
            return phonenumbers.is_valid_number(parsed)
        except:
            return False

