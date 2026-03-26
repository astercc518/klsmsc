"""
FastAPI 主应用入口
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.ip_whitelist import IPWhitelistMiddleware
from app.config import settings
from app.database import (
    init_db,
    close_db,
    ensure_channel_dlr_preference_columns,
    ensure_sales_commission_total_cost_columns,
)
from app.utils.logger import setup_logging, get_logger
from app.utils.errors import SMSGatewayException, error_response
from app.utils.cache import get_redis_client, close_redis

# 初始化日志
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 放宽 multipart 单文件大小限制（Starlette 默认 1MB，大文件导入需 500MB）
    try:
        from starlette.formparsers import MultiPartParser
        if hasattr(MultiPartParser, 'max_part_size'):
            MultiPartParser.max_part_size = 500 * 1024 * 1024
            logger.info("已设置 MultiPartParser.max_part_size=500MB")
    except Exception as e:
        logger.debug(f"MultiPartParser 配置: {e}")
    # 启动
    logger.info(f"🚀 {settings.APP_NAME} 启动中...")
    logger.info(f"环境: {settings.APP_ENV}")
    logger.info(f"调试模式: {settings.APP_DEBUG}")
    
    # 初始化数据库
    await init_db()
    await ensure_channel_dlr_preference_columns()
    await ensure_sales_commission_total_cost_columns()
    logger.info("✅ 数据库初始化完成")
    
    # 初始化Redis连接
    try:
        await get_redis_client()
        logger.info("✅ Redis连接初始化完成")
    except Exception as e:
        logger.warning(f"⚠️  Redis连接失败，将使用数据库直连: {str(e)}")
    
    yield
    
    # 关闭
    logger.info("⏹️  应用正在关闭...")
    await close_db()
    await close_redis()
    logger.info("✅ 数据库和Redis连接已关闭")


# 生产环境禁用 API 文档端点
_is_dev = (settings.APP_ENV == "development")

app = FastAPI(
    title=settings.APP_NAME,
    description="考拉出海 - 企业级国际短信网关系统 | kaolach.com",
    version="1.0.0",
    docs_url="/docs" if _is_dev else None,
    redoc_url="/redoc" if _is_dev else None,
    openapi_url="/openapi.json" if _is_dev else None,
    lifespan=lifespan
)

# CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# IP白名单中间件（在限流之前）
app.add_middleware(IPWhitelistMiddleware)

# API限流中间件
app.add_middleware(
    RateLimitMiddleware,
    default_limit=settings.RATE_LIMIT_PER_MINUTE
)


# 全局异常处理
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """处理Pydantic验证错误并记录详细信息"""
    errors = exc.errors()
    # P2-FIX: 不记录请求体，防止泄露密码/Token
    logger.error(f"Pydantic验证错误: path={request.url.path}, errors={errors}")
    return JSONResponse(
        status_code=422,
        content={"detail": errors}
    )

@app.exception_handler(SMSGatewayException)
async def sms_gateway_exception_handler(request: Request, exc: SMSGatewayException):
    """处理自定义异常"""
    logger.error(f"业务异常: {exc.message}", exc_info=exc)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(exc)
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """处理未捕获的异常"""
    logger.error(f"未处理异常: {str(exc)}", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Internal server error",
                "details": {}
            }
        }
    )


# 健康检查
@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": "1.0.0",
        "environment": settings.APP_ENV
    }


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": f"Welcome to {settings.APP_NAME}",
        "docs": "/docs",
        "health": "/health"
    }


# 注册路由
from app.api.v1 import (
    sms, account, channels, admin, reports, bot_admin, system_config,
    templates, api_keys, batches, scheduled_tasks, sub_accounts, packages,
    notifications, security_logs, suppliers, tickets, settlements,
    sales_commission, knowledge,
    channel_relations, voice, account_templates, ai, admin_logs
)
from app.api.v1.data import (
    admin_numbers_router, admin_products_router, admin_orders_router,
    admin_accounts_router, admin_pricing_router, sales_router, customer_router,
)

app.include_router(sms.router, prefix="/api/v1/sms", tags=["SMS"])
app.include_router(account.router, prefix="/api/v1/account", tags=["Account"])
app.include_router(channels.router, prefix="/api/v1/channels", tags=["Channels"])
app.include_router(admin.router, prefix="/api/v1", tags=["Admin"])
app.include_router(reports.router, prefix="/api/v1", tags=["Reports"])
app.include_router(bot_admin.router, prefix="/api/v1/admin/bot", tags=["Bot Admin"])
app.include_router(system_config.router, prefix="/api/v1/admin", tags=["System Config"])
app.include_router(templates.router, prefix="/api/v1", tags=["Templates"])
app.include_router(api_keys.router, prefix="/api/v1", tags=["API Keys"])
app.include_router(batches.router, prefix="/api/v1", tags=["Batch Send"])
app.include_router(scheduled_tasks.router, prefix="/api/v1", tags=["Scheduled Tasks"])
app.include_router(sub_accounts.router, prefix="/api/v1", tags=["Sub Accounts"])
app.include_router(packages.router, prefix="/api/v1", tags=["Packages"])
app.include_router(notifications.router, prefix="/api/v1", tags=["Notifications"])
app.include_router(security_logs.router, prefix="/api/v1", tags=["Security Logs"])
# 新增模块
app.include_router(suppliers.router, prefix="/api/v1", tags=["Suppliers"])
app.include_router(tickets.router, prefix="/api/v1", tags=["Tickets"])
app.include_router(settlements.router, prefix="/api/v1", tags=["Settlements"])
app.include_router(settlements.customer_bill_router, prefix="/api/v1", tags=["客户账单"])
app.include_router(sales_commission.router, prefix="/api/v1", tags=["销售佣金"])
app.include_router(knowledge.router, prefix="/api/v1", tags=["知识库"])
# 数据业务模块
app.include_router(admin_numbers_router, prefix="/api/v1/admin/data", tags=["数据管理-号码"])
app.include_router(admin_products_router, prefix="/api/v1/admin/data", tags=["数据管理-商品"])
app.include_router(admin_orders_router, prefix="/api/v1/admin/data", tags=["数据管理-订单"])
app.include_router(admin_accounts_router, prefix="/api/v1/admin/data", tags=["数据管理-账户"])
app.include_router(admin_pricing_router, prefix="/api/v1/admin/data", tags=["数据管理-定价模板"])
app.include_router(sales_router, prefix="/api/v1/sales/data", tags=["数据业务-销售"])
app.include_router(customer_router, prefix="/api/v1/data", tags=["数据业务-客户"])
# 通道关系管理
app.include_router(channel_relations.router, prefix="/api/v1", tags=["Channel Relations"])
# 语音业务管理
app.include_router(voice.router, prefix="/api/v1", tags=["Voice"])
# 开户模板管理
app.include_router(account_templates.router, prefix="/api/v1", tags=["Account Templates"])
# AI 文案生成
app.include_router(ai.router, prefix="/api/v1/ai", tags=["AI"])
# 系统操作日志
app.include_router(admin_logs.router, prefix="/api/v1", tags=["System Logs"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.APP_DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )

