"""
管理端按角色限制查询作用域 —— 把 19+ 处 inline 检查抽出来。

设计目标：
  - 把"sales 只能看自己名下账户"等规则集中到一处
  - 调用方读起来意图明确：apply_account_scope(query, admin) / assert_account_in_scope(account, admin)
  - 不破坏现有 inline 检查的语义（先并存，逐步替换）

未来拓展：
  - 可加 apply_batch_scope / apply_sms_log_scope 等
  - 角色升级时改这一个文件而非 grep 19 处
"""
from typing import Any

from fastapi import HTTPException

from app.modules.common.account import Account
from app.modules.common.admin_user import AdminUser


def apply_account_scope(query, admin: AdminUser):
    """对 SELECT Account 的查询追加角色作用域 WHERE。

    sales 角色：限制为 sales_id == admin.id
    其它角色（super_admin/admin/staff/tech/finance）：不限制
    """
    if admin.role == "sales":
        return query.where(Account.sales_id == admin.id)
    return query


def assert_account_in_scope(account: Account, admin: AdminUser):
    """单条 Account 的访问检查（POST/PUT/DELETE 用）。

    sales 角色访问别人名下账户时抛 403。
    其它角色无限制。
    """
    if account is None:
        return  # 让调用方处理 404
    if admin.role == "sales" and account.sales_id != admin.id:
        raise HTTPException(status_code=403, detail="只能操作自己名下的客户")


def is_sales_scoped(admin: AdminUser) -> bool:
    """判断当前管理员是否处于 sales 作用域（便于自定义查询补充 WHERE）。"""
    return admin.role == "sales"


def sales_id_filter(admin: AdminUser) -> Any:
    """返回 sales_id 过滤值；非 sales 返回 None 表示不限制。

    用于已有 sales_id 局部变量的查询点：
        if admin.role == 'sales': sales_id = admin.id
    可改为：
        sales_id = sales_id_filter(admin) or sales_id
    """
    return admin.id if admin.role == "sales" else None
