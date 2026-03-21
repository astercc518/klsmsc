"""
业务验证工具类
"""
import phonenumbers
from typing import Dict, Tuple, Optional, List
from app.utils.logger import get_logger

logger = get_logger(__name__)

class Validator:
    """验证工具"""
    
    # 简单的敏感词列表（实际应从配置或数据库加载）
    BLACKLIST_KEYWORDS = [
        "博彩", "赌博", "杀猪盘", "casino", "gamble", 
        "诈骗", "fraud", "发票", "invoice"
    ]

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
            country_code = str(parsed.country_code)
            
            # 简单的类型检查（拦截固定电话等，非完全准确）
            num_type = phonenumbers.number_type(parsed)
            # 0: FIXED_LINE, 1: MOBILE, 2: FIXED_LINE_OR_MOBILE ...
            # 这里我们放宽一点，只要不是明确的特殊服务号即可
            
            return True, "", {
                "e164_format": phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164),
                "e164": phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164),
                "region": region_code,
                "country_code": country_code
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
        
        # 计算拆分条数
        # GSM-7: 160, UCS-2: 70
        is_gsm7 = Validator._is_gsm7(content)
        if is_gsm7:
            parts = 1 if length <= 160 else (length + 152) // 153
        else:
            parts = 1 if length <= 70 else (length + 66) // 67
            
        return True, "", {
            "length": length,
            "parts": parts,
            "encoding": "GSM-7" if is_gsm7 else "UCS-2"
        }

    @staticmethod
    def _is_gsm7(message: str) -> bool:
        """判断是否为GSM-7编码"""
        gsm7_chars = set(
            "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
            "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
        )
        return all(c in gsm7_chars for c in message)
