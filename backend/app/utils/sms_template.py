"""
短信内置变量占位符替换（与 Web 发送页「系统变量」、数据业务买即发一致）
每条发送应单独调用，以便 {随机码}/{code} 按条生成不同值。
"""
import random
from datetime import date
from typing import Optional

# 内置占位符（勿与自定义变量混淆）
SMS_TEMPLATE_VAR_TAGS = (
    "{序号}",
    "{国家}",
    "{日期}",
    "{随机码}",
    "{号码}",
    "{index}",
    "{country}",
    "{date}",
    "{code}",
    "{phone}",
)


def sms_template_has_variables(template: str) -> bool:
    """是否包含任一内置变量（无则跳过替换，避免无意义 random）"""
    if not template:
        return False
    return any(tag in template for tag in SMS_TEMPLATE_VAR_TAGS)


def render_sms_variables(
    template: str,
    *,
    index: int,
    phone_e164: str,
    country_code: Optional[str] = None,
) -> str:
    """
    将模板中的内置占位符替换为实际值。

    :param index: 批次内序号，从 1 开始
    :param phone_e164: E.164 号码（可含 +）
    :param country_code: 国家区号或地区码（与号码解析一致，用于 {国家}/{country}）
    """
    today_str = date.today().strftime("%Y-%m-%d")
    rand_code = str(random.randint(100000, 999999))
    phone_digits = phone_e164.lstrip("+") if phone_e164 else ""
    cc = (country_code or "").strip()

    msg = template
    msg = msg.replace("{序号}", str(index))
    msg = msg.replace("{国家}", cc)
    msg = msg.replace("{日期}", today_str)
    msg = msg.replace("{随机码}", rand_code)
    msg = msg.replace("{号码}", phone_digits)
    msg = msg.replace("{index}", str(index))
    msg = msg.replace("{country}", cc)
    msg = msg.replace("{date}", today_str)
    msg = msg.replace("{code}", rand_code)
    msg = msg.replace("{phone}", phone_digits)
    return msg
