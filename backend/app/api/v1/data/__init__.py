"""数据业务模块路由汇总"""
from app.api.v1.data.admin_numbers import router as admin_numbers_router
from app.api.v1.data.admin_products import router as admin_products_router
from app.api.v1.data.admin_orders import router as admin_orders_router
from app.api.v1.data.admin_accounts import router as admin_accounts_router
from app.api.v1.data.admin_pricing import router as admin_pricing_router
from app.api.v1.data.sales import router as sales_router
from app.api.v1.data.customer import router as customer_router

__all__ = [
    "admin_numbers_router",
    "admin_products_router",
    "admin_orders_router",
    "admin_accounts_router",
    "admin_pricing_router",
    "sales_router",
    "customer_router",
]
