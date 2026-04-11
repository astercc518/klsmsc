"""
账户国家限制：配置了 country_code 的短信账户仅允许购买/发送该国数据与号码。
"""
from typing import Optional

from app.modules.common.account import Account
from app.utils.country_code import normalize_country_code


class AccountCountryNotAllowedError(Exception):
    """目标国家与账户限定国家不一致"""

    def __init__(self, message: str, code: str = "COUNTRY_NOT_ALLOWED"):
        self.message = message
        self.code = code
        super().__init__(message)


def account_country_iso(account: Account) -> Optional[str]:
    """账户配置的国家，规范为 ISO2；未配置则返回 None（不限制）。"""
    raw = getattr(account, "country_code", None)
    if not raw or not str(raw).strip():
        return None
    return normalize_country_code(str(raw).strip())


def assert_sms_destination_allowed(account: Account, destination_iso: str) -> None:
    """短信目的国家须与账户 country_code 一致（未配置则不校验）。"""
    acc = account_country_iso(account)
    if not acc:
        return
    dest = normalize_country_code(destination_iso)
    if dest != acc:
        raise AccountCountryNotAllowedError(
            f"当前账户仅允许向 {acc} 国家/地区号码发送短信，目标号码归属为 {dest}",
        )
