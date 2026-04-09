"""
短信内置变量占位符替换（与 Web 发送页「系统变量」、数据业务买即发一致）
每条发送应单独调用，以便 {随机码}/{code} 按条生成不同值。
"""
import random
import re
import string
from datetime import date, datetime
from typing import Optional

# 内置占位符（勿与自定义变量混淆）——用于快速判断模板是否含内置变量
SMS_TEMPLATE_VAR_TAGS = (
    "{序号}",
    "{国家}",
    "{日期}",
    "{时间}",
    "{随机码}",
    "{号码}",
    "{金额}",
    "{随机字母}",
    "{index}",
    "{country}",
    "{date}",
    "{time}",
    "{code}",
    "{phone}",
    "{amount}",
    "{letters}",
)

# 可变长度随机码正则：{随机码4}、{随机码8}、{codeN} 等
_VAR_LEN_CODE_ZH = re.compile(r"\{随机码(\d{1,2})\}")
_VAR_LEN_CODE_EN = re.compile(r"\{code(\d{1,2})\}")
# 可变长度随机字母正则：{随机字母4}、{lettersN}
_VAR_LEN_LETTERS_ZH = re.compile(r"\{随机字母(\d{1,2})\}")
_VAR_LEN_LETTERS_EN = re.compile(r"\{letters(\d{1,2})\}")


def sms_template_has_variables(template: str) -> bool:
    """是否包含任一内置变量（无则跳过替换，避免无意义 random）"""
    if not template:
        return False
    if any(tag in template for tag in SMS_TEMPLATE_VAR_TAGS):
        return True
    if _VAR_LEN_CODE_ZH.search(template) or _VAR_LEN_CODE_EN.search(template):
        return True
    if _VAR_LEN_LETTERS_ZH.search(template) or _VAR_LEN_LETTERS_EN.search(template):
        return True
    return False


def _rand_digits(n: int) -> str:
    """生成 n 位纯数字随机码"""
    n = max(1, min(n, 20))
    if n == 1:
        return str(random.randint(0, 9))
    return str(random.randint(10 ** (n - 1), 10**n - 1))


def _rand_letters(n: int) -> str:
    """生成 n 位大写随机字母"""
    n = max(1, min(n, 20))
    return "".join(random.choices(string.ascii_uppercase, k=n))


def render_sms_variables(
    template: str,
    *,
    index: int,
    phone_e164: str,
    country_code: Optional[str] = None,
    amount: Optional[str] = None,
) -> str:
    """
    将模板中的内置占位符替换为实际值。

    :param index: 批次内序号，从 1 开始
    :param phone_e164: E.164 号码（可含 +）
    :param country_code: 国家区号或地区码（与号码解析一致）
    :param amount: 金额字符串（可选，由调用方传入）
    """
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")
    rand_code = _rand_digits(6)
    rand_letter = _rand_letters(6)
    phone_digits = phone_e164.lstrip("+") if phone_e164 else ""
    cc = (country_code or "").strip()
    amt = (amount or "").strip()

    msg = template

    # 固定长度变量替换
    msg = msg.replace("{序号}", str(index))
    msg = msg.replace("{国家}", cc)
    msg = msg.replace("{日期}", today_str)
    msg = msg.replace("{时间}", time_str)
    msg = msg.replace("{随机码}", rand_code)
    msg = msg.replace("{号码}", phone_digits)
    msg = msg.replace("{金额}", amt)
    msg = msg.replace("{随机字母}", rand_letter)

    msg = msg.replace("{index}", str(index))
    msg = msg.replace("{country}", cc)
    msg = msg.replace("{date}", today_str)
    msg = msg.replace("{time}", time_str)
    msg = msg.replace("{code}", rand_code)
    msg = msg.replace("{phone}", phone_digits)
    msg = msg.replace("{amount}", amt)
    msg = msg.replace("{letters}", rand_letter)

    # 可变长度随机码：{随机码4} -> 4位数字, {code8} -> 8位数字
    def _replace_var_code_zh(m: re.Match) -> str:
        return _rand_digits(int(m.group(1)))

    def _replace_var_code_en(m: re.Match) -> str:
        return _rand_digits(int(m.group(1)))

    msg = _VAR_LEN_CODE_ZH.sub(_replace_var_code_zh, msg)
    msg = _VAR_LEN_CODE_EN.sub(_replace_var_code_en, msg)

    # 可变长度随机字母：{随机字母4} -> 4位字母, {letters8} -> 8位字母
    def _replace_var_letters_zh(m: re.Match) -> str:
        return _rand_letters(int(m.group(1)))

    def _replace_var_letters_en(m: re.Match) -> str:
        return _rand_letters(int(m.group(1)))

    msg = _VAR_LEN_LETTERS_ZH.sub(_replace_var_letters_zh, msg)
    msg = _VAR_LEN_LETTERS_EN.sub(_replace_var_letters_en, msg)

    return msg
