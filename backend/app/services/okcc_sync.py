"""
OKCC 客户余额与资费同步（管理端 API 与 Celery 定时任务共用）
"""
import re
from datetime import datetime as dt

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.modules.common.account import Account
from app.modules.common.admin_user import AdminUser
from app.utils.logger import get_logger

logger = get_logger(__name__)

# OKCC 服务器配置：key = 前缀标识
OKCC_SERVERS = {
    "lcchcc": {
        "url": "https://www.lcchcc.com/smsc_api.php",
        "key": "smsc_okcc_sync_8f3a2d1e",
        "sip_domain": "107.149.129.185:5893",
        "label": "OKCC-1 (lcchcc)",
    },
    "klchcc": {
        "url": "https://www.klchcc.com/smsc_api.php",
        "key": "smsc_okcc_sync_8f3a2d1e",
        "sip_domain": "107.148.228.97:5893",
        "label": "OKCC-2 (klchcc)",
    },
}


async def fetch_okcc_customers(server_id: str) -> list:
    """从指定 OKCC 拉取全部客户数据"""
    cfg = OKCC_SERVERS.get(server_id)
    if not cfg:
        return []
    try:
        async with httpx.AsyncClient(verify=False, timeout=15) as client:
            resp = await client.get(cfg["url"], params={"key": cfg["key"], "action": "customers"})
            data = resp.json()
            if data.get("ok"):
                return data.get("data", [])
    except Exception as e:
        logger.error("OKCC(%s) 拉取失败: %s", server_id, e)
    return []


async def fetch_okcc_customer_detail(server_id: str, name: str) -> dict:
    """从 OKCC 获取单个客户详情（含 sip_password）"""
    cfg = OKCC_SERVERS.get(server_id)
    if not cfg:
        return {}
    try:
        async with httpx.AsyncClient(verify=False, timeout=10) as client:
            resp = await client.get(
                cfg["url"],
                params={"key": cfg["key"], "action": "customer_detail", "name": name},
            )
            data = resp.json()
            if data.get("ok") and data.get("data"):
                return data["data"]
    except Exception:
        pass
    return {}


def extract_staff_code(parent_name: str) -> str:
    """从 OKCC 代理商名（LC01, KL03 等）提取员工编号 → KL01, KL03"""
    m = re.match(r"^[A-Z]{2}(\d{2})", parent_name)
    if m:
        return f"KL{m.group(1)}"
    return ""


def parse_billing_package(pkg_name: str) -> dict:
    """
    从资费套餐名解析单价信息
    例: 'KL07孟加拉0.09/0.06' → {'name': ..., 'prices': [0.09, 0.06], 'unit_price': 0.09}
    """
    result = {"name": pkg_name, "prices": [], "unit_price": None}
    if not pkg_name:
        return result
    cleaned = re.sub(r"^[A-Z]{2}\d{2}", "", pkg_name)
    prices = re.findall(r"(\d+\.\d+)", cleaned)
    float_prices = [float(p) for p in prices]
    if not float_prices:
        nums = re.findall(r"(?<![A-Z])(\d+)(?!\d)", cleaned)
        for n in nums:
            val = float(n)
            if val < 100:
                float_prices.append(val)
    result["prices"] = float_prices
    if float_prices:
        result["unit_price"] = float_prices[0]
    return result


async def resolve_sales_id(db: AsyncSession, parent_name: str) -> int | None:
    """将 OKCC 代理商名映射到 SMSC 的 sales_id"""
    staff_code = extract_staff_code(parent_name)
    if not staff_code:
        return None
    result = await db.execute(select(AdminUser.id).where(AdminUser.username == staff_code))
    row = result.scalar_one_or_none()
    return row


LOW_BALANCE_THRESHOLD = 100  # 余额低于此值通知员工


async def _notify_low_balance(db: AsyncSession, account: Account, old_balance: float, new_balance: float):
    """余额跌破阈值时通知负责员工（通过 Telegram Bot）"""
    if new_balance >= LOW_BALANCE_THRESHOLD:
        return
    # 上次余额已经低于阈值则不重复通知（仅在从 >=100 跌到 <100 时触发）
    if old_balance < LOW_BALANCE_THRESHOLD:
        return
    if not account.sales_id:
        return
    try:
        result = await db.execute(
            select(AdminUser).where(AdminUser.id == account.sales_id)
        )
        sales = result.scalar_one_or_none()
        if not sales or not sales.tg_id:
            return
        from app.services.notification_service import notification_service
        text = (
            f"⚠️ 语音客户余额预警\n\n"
            f"客户: {account.account_name}\n"
            f"OKCC余额: ¥{new_balance:.2f}\n"
            f"（低于 ¥{LOW_BALANCE_THRESHOLD}）\n\n"
            f"请及时联系客户充值。"
        )
        await notification_service.send_message(str(sales.tg_id), text, parse_mode="")
    except Exception as e:
        logger.warning("低余额通知失败 account=%s: %s", account.account_name, e)


async def sync_okcc_to_accounts(db: AsyncSession) -> dict:
    """将 OKCC 客户数据同步到本地 accounts 表（更新已有 + 自动导入新客户）"""
    stats = {"synced": 0, "created": 0, "errors": [], "servers": {}}

    for server_id, cfg in OKCC_SERVERS.items():
        try:
            customers = await fetch_okcc_customers(server_id)
            stats["servers"][server_id] = {"total": len(customers), "synced": 0, "created": 0}

            for cust in customers:
                okcc_name = cust.get("name", "").strip()
                if not okcc_name:
                    continue

                balance_yuan = float(cust.get("balance_yuan", 0))
                sip_min = cust.get("sip_min") or ""
                sip_max = cust.get("sip_max") or ""
                sip_count = int(cust.get("sip_count", 0))
                parent_name = cust.get("parent_name", "")
                billing_pkg = cust.get("billing_package", "")

                pkg_info = parse_billing_package(billing_pkg)

                cc_match = re.search(r"[A-Z]{2}\d{2}(\d{3})", okcc_name)
                country_code = cc_match.group(1) if cc_match else ""

                result = await db.execute(
                    select(Account).where(
                        Account.account_name == okcc_name,
                    ).limit(1)
                )
                account = result.scalar_one_or_none()
                # 已删除的账户不更新也不重建
                if account and account.is_deleted:
                    continue

                now_str = dt.now().strftime("%Y-%m-%d %H:%M:%S")
                sync_data = {
                    "okcc_balance": balance_yuan,
                    "okcc_id": cust.get("id"),
                    "okcc_server": server_id,
                    "okcc_parent": parent_name,
                    "okcc_synced_at": now_str,
                    "billing_package": billing_pkg,
                }
                if pkg_info["prices"]:
                    sync_data["billing_prices"] = pkg_info["prices"]
                if sip_min and sip_max:
                    sync_data["sip_range"] = f"{sip_min}-{sip_max}"
                    sync_data["sip_count"] = sip_count
                    sync_data["sip_domain"] = cfg["sip_domain"]

                unit_price_val = pkg_info.get("unit_price")

                existing_creds = (account.supplier_credentials if account else None) or {}
                if not existing_creds.get("sip_password"):
                    detail = await fetch_okcc_customer_detail(server_id, okcc_name)
                    if detail.get("sip_password"):
                        sync_data["sip_password"] = detail["sip_password"]

                if account:
                    old_balance = float(account.balance or 0)
                    account.balance = balance_yuan
                    if unit_price_val is not None:
                        account.unit_price = unit_price_val
                    creds = account.supplier_credentials or {}
                    creds.update(sync_data)
                    creds.setdefault("client_name", okcc_name)
                    creds.setdefault("username", "admin")
                    if not account.supplier_url:
                        account.supplier_url = f"https://www.{server_id}.com"
                    account.supplier_credentials = creds
                    flag_modified(account, "supplier_credentials")
                    stats["synced"] += 1
                    stats["servers"][server_id]["synced"] += 1
                    # 余额跌破阈值时通知员工
                    await _notify_low_balance(db, account, old_balance, balance_yuan)
                else:
                    sales_id = await resolve_sales_id(db, parent_name)
                    new_creds = sync_data.copy()
                    new_creds["client_name"] = okcc_name
                    new_creds["username"] = "admin"

                    new_account = Account(
                        account_name=okcc_name,
                        business_type="voice",
                        country_code=country_code,
                        balance=balance_yuan,
                        currency="CNY",
                        unit_price=unit_price_val or 0,
                        supplier_url=f"https://www.{server_id}.com",
                        supplier_credentials=new_creds,
                        sales_id=sales_id,
                        status="active",
                        payment_type="prepaid",
                    )
                    db.add(new_account)
                    stats["created"] += 1
                    stats["servers"][server_id]["created"] = stats["servers"][server_id].get("created", 0) + 1

            await db.commit()
        except Exception as e:
            logger.error("OKCC(%s) 同步出错: %s", server_id, e)
            stats["errors"].append(f"{server_id}: {str(e)}")
            await db.rollback()

    return stats
