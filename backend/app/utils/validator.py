"""
业务验证工具类
"""
import phonenumbers
from typing import Dict, Tuple, Optional, List
from app.utils.logger import get_logger
from app.utils.sms_segment import count_sms_parts, is_gsm7_message
from app.utils.country_code import normalize_country_code

logger = get_logger(__name__)

class Validator:
    """验证工具"""
    
    # 后端不再拦截敏感词，违禁词检测已移至前端实时提醒
    BLACKLIST_KEYWORDS: list = []

    @staticmethod
    def validate_phone_number(phone: str) -> Tuple[bool, str, Optional[Dict]]:
        """
        验证手机号码
        
        Returns:
            (is_valid, error_msg, info_dict)
        """
        try:
            # 必须以 + 开头
            if not phone.startswith('+'):
                # 尝试自动修复：如果是纯数字，假设是国际格式但没加+
                if phone.isdigit():
                    phone = '+' + phone
                else:
                    return False, "号码必须以 + 开头 (E.164格式)", None

            parsed = phonenumbers.parse(phone, None)
            
            if not phonenumbers.is_valid_number(parsed):
                return False, "无效的手机号码", None
                
            region_code = phonenumbers.region_code_for_number(parsed)
            dial_code = str(parsed.country_code)
            # 统一使用 ISO2 作为 country_code，区号保留在 dial_code
            iso_code = normalize_country_code(region_code) or normalize_country_code(dial_code) or region_code or dial_code
            
            num_type = phonenumbers.number_type(parsed)
            
            return True, "", {
                "e164_format": phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164),
                "e164": phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164),
                "region": region_code,
                "dial_code": dial_code,
                "country_code": iso_code
            }
            
        except phonenumbers.NumberParseException:
            return False, "号码解析失败", None
        except Exception as e:
            logger.error(f"号码验证异常: {str(e)}")
            return False, "系统验证错误", None

    @staticmethod
    def validate_content(content: str) -> Tuple[bool, str, Dict]:
        """
        验证短信内容
        
        Returns:
            (is_valid, error_msg, info_dict)
        """
        if not content:
            return False, "内容不能为空", {}
            
        # 长度检查
        length = len(content)
        if length > 1000:
            return False, "内容过长（最大1000字符）", {"length": length}
            
        # 敏感词检查
        for keyword in Validator.BLACKLIST_KEYWORDS:
            if keyword in content:
                return False, f"包含敏感词: {keyword}", {"length": length}
        
        # 拆分条数与计费引擎一致（含规范化）
        is_gsm7 = is_gsm7_message(content)
        parts = count_sms_parts(content)

        return True, "", {
            "length": length,
            "parts": parts,
            "encoding": "GSM-7" if is_gsm7 else "UCS-2",
        }
