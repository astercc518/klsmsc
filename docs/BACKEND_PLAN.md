# 国际短信系统 - 后端开发计划

## 文档信息
- **文档类型**: Backend Development Plan
- **项目名称**: International SMS Gateway System - Backend
- **技术栈**: Python 3.10+ / FastAPI / MySQL / Redis / RabbitMQ
- **文档版本**: v1.0
- **创建日期**: 2025-12-30

---

## 目录
1. [开发环境搭建](#1-开发环境搭建)
2. [项目结构](#2-项目结构)
3. [开发阶段规划](#3-开发阶段规划)
4. [核心模块开发](#4-核心模块开发)
5. [测试计划](#5-测试计划)
6. [部署计划](#6-部署计划)

---

## 1. 开发环境搭建

### 1.1 本地开发环境

**必需软件**:
```bash
# Python环境
Python 3.10+
pip 23.0+
virtualenv

# 数据库
MySQL 8.0
Redis 7.0
RabbitMQ 3.12

# 开发工具
VS Code / PyCharm
Git
Postman / HTTPie
Docker Desktop
```

**环境配置**:
```bash
# 1. 克隆项目
git clone <repository_url>
cd rpg

# 2. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 3. 安装依赖
pip install -r requirements.txt
pip install -r requirements-dev.txt  # 开发依赖

# 4. 配置环境变量
cp .env.example .env
# 编辑.env文件，填写数据库连接等配置

# 5. 初始化数据库
python scripts/init_db.py

# 6. 启动开发服务器
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 1.2 Docker开发环境

```bash
# 使用Docker Compose一键启动所有服务
docker-compose -f docker-compose.dev.yml up -d

# 查看日志
docker-compose -f docker-compose.dev.yml logs -f

# 进入容器
docker-compose exec api bash
```

### 1.3 依赖管理

**requirements.txt**:
```
# Web框架
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.0
pydantic-settings==2.1.0

# 数据库
SQLAlchemy==2.0.23
PyMySQL==1.1.0
alembic==1.12.1

# 缓存和消息队列
redis==5.0.1
celery==5.3.4
kombu==5.3.4

# HTTP客户端
httpx==0.25.2
aiohttp==3.9.1

# SMPP协议
smpplib==2.2.3

# 工具库
python-dotenv==1.0.0
phonenumbers==8.13.26
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.6

# 监控和日志
prometheus-client==0.19.0
python-json-logger==2.0.7

# 测试
pytest==7.4.3
pytest-asyncio==0.21.1
pytest-cov==4.1.0
```

**requirements-dev.txt**:
```
# 代码质量
black==23.12.0
flake8==6.1.0
pylint==3.0.3
mypy==1.7.1
isort==5.13.2

# 测试工具
faker==20.1.0
factory-boy==3.3.0
pytest-mock==3.12.0
```

---

## 2. 项目结构

```
rpg/
├── app/                            # 应用主目录
│   ├── __init__.py
│   ├── main.py                     # FastAPI应用入口
│   ├── config.py                   # 配置管理
│   ├── dependencies.py             # 依赖注入
│   │
│   ├── api/                        # API路由
│   │   ├── __init__.py
│   │   └── v1/                     # API v1版本
│   │       ├── __init__.py
│   │       ├── sms.py              # 短信发送API
│   │       ├── status.py           # 状态查询API
│   │       ├── account.py          # 账户管理API
│   │       ├── channels.py         # 通道管理API
│   │       ├── pricing.py          # 计费查询API
│   │       ├── sender_ids.py       # SID管理API
│   │       ├── reports.py          # 报表API
│   │       └── admin.py            # 管理后台API
│   │
│   ├── core/                       # 核心业务逻辑
│   │   ├── __init__.py
│   │   ├── router.py               # 路由引擎
│   │   ├── pricing.py              # 计费引擎
│   │   ├── sender_id.py            # SID管理器
│   │   ├── phone_parser.py         # 号码解析
│   │   ├── status_tracker.py       # 状态追踪
│   │   ├── auth.py                 # 认证授权
│   │   └── rate_limiter.py         # 限流器
│   │
│   ├── models/                     # 数据模型（SQLAlchemy ORM）
│   │   ├── __init__.py
│   │   ├── base.py                 # 基础模型
│   │   ├── account.py              # 账户模型
│   │   ├── channel.py              # 通道模型
│   │   ├── sms_log.py              # 短信记录模型
│   │   ├── pricing.py              # 计费规则模型
│   │   ├── sender_id.py            # SID模型
│   │   ├── balance_log.py          # 余额变动模型
│   │   └── admin_user.py           # 管理员模型
│   │
│   ├── schemas/                    # Pydantic数据模式
│   │   ├── __init__.py
│   │   ├── sms.py                  # 短信相关模式
│   │   ├── account.py              # 账户相关模式
│   │   ├── channel.py              # 通道相关模式
│   │   ├── common.py               # 通用模式
│   │   └── response.py             # 响应模式
│   │
│   ├── services/                   # 服务层
│   │   ├── __init__.py
│   │   ├── sms_service.py          # 短信服务
│   │   ├── account_service.py      # 账户服务
│   │   ├── channel_service.py      # 通道服务
│   │   ├── pricing_service.py      # 计费服务
│   │   ├── report_service.py       # 报表服务
│   │   └── callback_service.py     # 回调服务
│   │
│   ├── workers/                    # Celery任务
│   │   ├── __init__.py
│   │   ├── celery_app.py           # Celery应用
│   │   ├── sms_worker.py           # 短信发送Worker
│   │   ├── smpp_worker.py          # SMPP协议Worker
│   │   ├── http_worker.py          # HTTP协议Worker
│   │   ├── callback_worker.py      # 回调Worker
│   │   └── scheduled_tasks.py      # 定时任务
│   │
│   ├── utils/                      # 工具函数
│   │   ├── __init__.py
│   │   ├── cache.py                # Redis缓存工具
│   │   ├── database.py             # 数据库工具
│   │   ├── logger.py               # 日志工具
│   │   ├── security.py             # 安全工具
│   │   ├── validators.py           # 验证器
│   │   ├── exceptions.py           # 自定义异常
│   │   └── metrics.py              # Prometheus指标
│   │
│   └── middleware/                 # 中间件
│       ├── __init__.py
│       ├── error_handler.py        # 错误处理
│       ├── logging_middleware.py   # 日志中间件
│       ├── metrics_middleware.py   # 指标中间件
│       └── cors_middleware.py      # CORS中间件
│
├── tests/                          # 测试目录
│   ├── __init__.py
│   ├── conftest.py                 # Pytest配置
│   ├── unit/                       # 单元测试
│   │   ├── test_router.py
│   │   ├── test_pricing.py
│   │   └── test_phone_parser.py
│   ├── integration/                # 集成测试
│   │   ├── test_sms_api.py
│   │   └── test_account_api.py
│   └── e2e/                        # 端到端测试
│       └── test_send_flow.py
│
├── scripts/                        # 脚本工具
│   ├── init_db.py                  # 初始化数据库
│   ├── seed_data.py                # 填充测试数据
│   ├── migrate.py                  # 数据迁移
│   └── backup.sh                   # 备份脚本
│
├── alembic/                        # 数据库迁移
│   ├── versions/                   # 迁移版本
│   ├── env.py
│   └── script.py.mako
│
├── docs/                           # 文档
│   ├── PROJECT_OVERVIEW.md
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   ├── DATABASE_DESIGN.md
│   ├── BACKEND_PLAN.md
│   ├── FRONTEND_PLAN.md
│   └── API_SPECIFICATION.md
│
├── docker/                         # Docker配置
│   ├── Dockerfile
│   ├── Dockerfile.worker
│   └── nginx.conf
│
├── .env.example                    # 环境变量示例
├── .gitignore
├── docker-compose.yml              # 生产环境Docker配置
├── docker-compose.dev.yml          # 开发环境Docker配置
├── requirements.txt                # 生产依赖
├── requirements-dev.txt            # 开发依赖
├── pytest.ini                      # Pytest配置
├── .flake8                         # Flake8配置
├── pyproject.toml                  # Black/isort配置
└── README.md                       # 项目说明
```

---

## 3. 开发阶段规划

### 阶段一：基础框架搭建（Week 1-2）

**目标**: 完成项目基础架构和开发环境

**任务清单**:
- [x] Week 1
  - [ ] 项目目录结构创建
  - [ ] FastAPI应用初始化
  - [ ] 数据库连接配置
  - [ ] Redis连接配置
  - [ ] RabbitMQ连接配置
  - [ ] 日志系统搭建
  - [ ] 配置管理（环境变量）
  - [ ] Docker开发环境
  
- [x] Week 2
  - [ ] SQLAlchemy模型定义（基础表）
  - [ ] Alembic数据库迁移配置
  - [ ] Pydantic数据模式定义
  - [ ] 统一响应格式
  - [ ] 异常处理中间件
  - [ ] API文档配置（Swagger）
  - [ ] 单元测试框架搭建

**验收标准**:
- ✅ 开发环境可正常启动
- ✅ 数据库连接成功
- ✅ API文档可访问 (http://localhost:8000/docs)
- ✅ 日志正常输出

---

### 阶段二：核心功能开发（Week 3-7）

#### Week 3: 账户和认证模块

**任务**:
- [ ] 账户模型和API
  - [ ] 账户注册
  - [ ] API密钥生成
  - [ ] API密钥验证（HMAC签名）
  - [ ] IP白名单验证
  - [ ] 请求限流（Rate Limiting）
- [ ] 单元测试
- [ ] API文档完善

**交付物**:
- `app/api/v1/account.py`
- `app/core/auth.py`
- `app/core/rate_limiter.py`
- `tests/unit/test_auth.py`

---

#### Week 4: 通道管理模块

**任务**:
- [ ] 通道CRUD API
  - [ ] 创建通道
  - [ ] 查询通道列表
  - [ ] 更新通道配置
  - [ ] 启用/禁用通道
  - [ ] 删除通道
- [ ] 通道状态监控
- [ ] 通道测试功能
- [ ] 单元测试

**交付物**:
- `app/api/v1/channels.py`
- `app/services/channel_service.py`
- `tests/unit/test_channel_service.py`

---

#### Week 5: 路由引擎和计费引擎

**任务**:
- [ ] 号码解析器
  - [ ] 解析国际号码
  - [ ] 识别国家代码
  - [ ] 识别运营商（MCC/MNC）
- [ ] 路由引擎
  - [ ] 优先级路由
  - [ ] 成本优先路由
  - [ ] 质量优先路由
  - [ ] 负载均衡路由
- [ ] 计费引擎
  - [ ] 价格查询（多级缓存）
  - [ ] 长短信条数计算
  - [ ] 费用计算
  - [ ] 余额扣减（事务）
- [ ] 单元测试

**交付物**:
- `app/core/phone_parser.py`
- `app/core/router.py`
- `app/core/pricing.py`
- `tests/unit/test_router.py`
- `tests/unit/test_pricing.py`

---

#### Week 6: SID管理和短信发送API

**任务**:
- [ ] 发送方ID管理
  - [ ] SID申请
  - [ ] SID审核
  - [ ] SID自动匹配
  - [ ] SID查询API
- [ ] 短信发送API
  - [ ] 单条发送
  - [ ] 参数验证
  - [ ] 调用路由引擎
  - [ ] 调用计费引擎
  - [ ] 消息入队
  - [ ] 返回消息ID
- [ ] 单元测试

**交付物**:
- `app/core/sender_id.py`
- `app/api/v1/sender_ids.py`
- `app/api/v1/sms.py`
- `app/services/sms_service.py`
- `tests/integration/test_sms_api.py`

---

#### Week 7: Celery Worker和通道协议

**任务**:
- [ ] Celery配置
  - [ ] Celery app初始化
  - [ ] 队列配置
  - [ ] 任务重试机制
- [ ] SMPP Worker
  - [ ] SMPP连接管理
  - [ ] 短信发送
  - [ ] 送达回执处理
- [ ] HTTP Worker
  - [ ] HTTP API调用
  - [ ] 错误处理
  - [ ] 状态映射
- [ ] 状态追踪
  - [ ] 状态更新
  - [ ] 回调触发
- [ ] 单元测试

**交付物**:
- `app/workers/celery_app.py`
- `app/workers/smpp_worker.py`
- `app/workers/http_worker.py`
- `app/core/status_tracker.py`
- `tests/unit/test_workers.py`

---

### 阶段三：高级功能开发（Week 8-10）

#### Week 8: 批量发送和定时发送

**任务**:
- [ ] 批量发送API
  - [ ] CSV文件上传
  - [ ] 模板变量替换
  - [ ] 批次管理
  - [ ] 进度查询
- [ ] 定时发送
  - [ ] 定时任务创建
  - [ ] 定时任务取消
  - [ ] 时区处理
- [ ] 单元测试

**交付物**:
- `app/api/v1/sms.py` (批量发送接口)
- `app/services/batch_service.py`
- `app/workers/scheduled_tasks.py`

---

#### Week 9: 状态查询和Webhook回调

**任务**:
- [ ] 状态查询API
  - [ ] 单条查询
  - [ ] 批量查询
  - [ ] 筛选查询
- [ ] Webhook回调
  - [ ] 回调Worker
  - [ ] 签名生成
  - [ ] 重试机制
  - [ ] 回调日志
- [ ] 单元测试

**交付物**:
- `app/api/v1/status.py`
- `app/workers/callback_worker.py`
- `app/services/callback_service.py`

---

#### Week 10: 报表统计

**任务**:
- [ ] 统计报表API
  - [ ] 发送量统计
  - [ ] 成功率统计
  - [ ] 费用统计
  - [ ] 通道性能统计
  - [ ] 国家分布统计
- [ ] 数据导出
  - [ ] Excel导出
  - [ ] CSV导出
- [ ] 缓存优化
- [ ] 单元测试

**交付物**:
- `app/api/v1/reports.py`
- `app/services/report_service.py`

---

### 阶段四：管理后台API（Week 11-12）

#### Week 11-12: 管理后台接口

**任务**:
- [ ] 管理员认证
  - [ ] 登录/登出
  - [ ] JWT Token管理
  - [ ] 权限控制（RBAC）
- [ ] 通道管理API（完整CRUD）
- [ ] 计费规则管理API
- [ ] 用户管理API
- [ ] 系统配置API
- [ ] 操作日志API
- [ ] 单元测试

**交付物**:
- `app/api/v1/admin.py`
- `app/core/auth.py` (管理员认证)
- `app/middleware/rbac.py`

---

### 阶段五：监控和优化（Week 13-14）

#### Week 13: 监控指标

**任务**:
- [ ] Prometheus指标
  - [ ] 请求计数
  - [ ] 响应时间
  - [ ] 短信发送量
  - [ ] 成功率
  - [ ] 队列长度
- [ ] 健康检查接口
- [ ] 性能监控

**交付物**:
- `app/utils/metrics.py`
- `app/middleware/metrics_middleware.py`

---

#### Week 14: 性能优化

**任务**:
- [ ] SQL查询优化
- [ ] 索引优化
- [ ] 缓存优化
- [ ] 连接池优化
- [ ] 异步处理优化
- [ ] 压力测试
- [ ] 性能调优

**交付物**:
- 性能测试报告
- 优化方案文档

---

### 阶段六：测试和文档（Week 15-16）

#### Week 15: 全面测试

**任务**:
- [ ] 单元测试补充（覆盖率>80%）
- [ ] 集成测试
- [ ] 端到端测试
- [ ] 安全测试
  - [ ] SQL注入测试
  - [ ] XSS测试
  - [ ] 认证测试
- [ ] 压力测试（10,000 TPS）
- [ ] Bug修复

**交付物**:
- 测试报告
- Bug列表和修复记录

---

#### Week 16: 文档和部署准备

**任务**:
- [ ] API文档完善
- [ ] 代码注释补充
- [ ] 部署文档编写
- [ ] 运维手册编写
- [ ] Docker镜像构建
- [ ] CI/CD配置
- [ ] 上线检查清单

**交付物**:
- 完整的API文档
- 部署文档
- 运维手册
- Docker镜像

---

## 4. 核心模块开发

### 4.1 FastAPI应用入口

```python
# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from app.api.v1 import sms, status, account, channels, pricing, sender_ids, reports, admin
from app.config import settings
from app.middleware.error_handler import error_handler_middleware
from app.middleware.logging_middleware import logging_middleware
from app.utils.logger import setup_logging

# 初始化日志
setup_logging()

# 创建FastAPI应用
app = FastAPI(
    title="International SMS Gateway API",
    description="企业级国际短信网关系统",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 自定义中间件
app.middleware("http")(error_handler_middleware)
app.middleware("http")(logging_middleware)

# 注册路由
app.include_router(sms.router, prefix="/api/v1/sms", tags=["SMS"])
app.include_router(status.router, prefix="/api/v1/status", tags=["Status"])
app.include_router(account.router, prefix="/api/v1/account", tags=["Account"])
app.include_router(channels.router, prefix="/api/v1/channels", tags=["Channels"])
app.include_router(pricing.router, prefix="/api/v1/pricing", tags=["Pricing"])
app.include_router(sender_ids.router, prefix="/api/v1/sender-ids", tags=["Sender IDs"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["Reports"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["Admin"])

# Prometheus指标
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "services": {
            "api": "up",
            "database": "up",  # 实际应检查数据库连接
            "redis": "up",     # 实际应检查Redis连接
            "rabbitmq": "up"   # 实际应检查RabbitMQ连接
        }
    }

@app.on_event("startup")
async def startup_event():
    """启动事件"""
    print("🚀 Application starting up...")
    # 初始化数据库连接池
    # 初始化Redis连接
    # 预热缓存
    print("✅ Application started successfully")

@app.on_event("shutdown")
async def shutdown_event():
    """关闭事件"""
    print("👋 Application shutting down...")
    # 关闭数据库连接
    # 关闭Redis连接
    print("✅ Application shut down successfully")
```

### 4.2 配置管理

```python
# app/config.py
from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    # 应用配置
    APP_NAME: str = "SMS Gateway"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # 数据库配置
    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10
    
    # Redis配置
    REDIS_URL: str
    REDIS_POOL_SIZE: int = 20
    
    # RabbitMQ配置
    RABBITMQ_URL: str
    
    # JWT配置
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    
    # CORS配置
    CORS_ORIGINS: List[str] = ["*"]
    
    # 限流配置
    RATE_LIMIT_PER_MINUTE: int = 1000
    
    # 日志配置
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/app.log"
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
```

### 4.3 短信发送API示例

```python
# app/api/v1/sms.py
from fastapi import APIRouter, Depends, HTTPException
from app.schemas.sms import SendSMSRequest, SendSMSResponse
from app.services.sms_service import SMSService
from app.core.auth import verify_api_key
from app.core.rate_limiter import check_rate_limit

router = APIRouter()

@router.post("/send", response_model=SendSMSResponse)
async def send_sms(
    request: SendSMSRequest,
    api_key: str = Depends(verify_api_key),
    service: SMSService = Depends()
):
    """
    发送短信
    
    - **phone_number**: 国际格式手机号（如+8613800138000）
    - **message**: 短信内容
    - **sender_id**: 发送方ID（可选）
    - **channel**: 指定通道（可选）
    """
    # 检查限流
    await check_rate_limit(api_key)
    
    # 发送短信
    result = await service.send_sms(
        account_id=request.account_id,
        phone_number=request.phone_number,
        message=request.message,
        sender_id=request.sender_id,
        preferred_channel=request.channel
    )
    
    if not result['success']:
        raise HTTPException(status_code=400, detail=result.get('error'))
    
    return SendSMSResponse(**result)
```

---

## 5. 测试计划

### 5.1 单元测试

```python
# tests/unit/test_phone_parser.py
import pytest
from app.core.phone_parser import PhoneNumberParser

def test_parse_valid_chinese_number():
    """测试解析有效的中国号码"""
    result = PhoneNumberParser.parse("+8613800138000")
    assert result['valid'] == True
    assert result['country_code'] == 'CN'
    assert result['country_name'] == '中国'

def test_parse_invalid_number():
    """测试解析无效号码"""
    result = PhoneNumberParser.parse("12345")
    assert result['valid'] == False

# tests/unit/test_pricing.py
import pytest
from decimal import Decimal
from app.core.pricing import PricingEngine

@pytest.mark.asyncio
async def test_calculate_price():
    """测试价格计算"""
    engine = PricingEngine(db_mock, redis_mock)
    result = await engine.calculate_and_charge(
        account_id=1,
        channel_id=1,
        country_code='CN',
        message='Hello World'
    )
    assert result['success'] == True
    assert result['total_cost'] > 0
```

### 5.2 集成测试

```python
# tests/integration/test_sms_api.py
import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_send_sms_api():
    """测试发送短信API"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/sms/send",
            json={
                "phone_number": "+8613800138000",
                "message": "Test message"
            },
            headers={"X-API-Key": "test_key"}
        )
        assert response.status_code == 200
        data = response.json()
        assert 'message_id' in data
```

### 5.3 性能测试

```bash
# 使用Locust进行压力测试
locust -f tests/performance/locustfile.py --host=http://localhost:8000
```

---

## 6. 部署计划

### 6.1 Docker构建

```dockerfile
# docker/Dockerfile
FROM python:3.10-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY app/ ./app/

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 6.2 CI/CD配置

```yaml
# .github/workflows/ci.yml
name: CI/CD Pipeline

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main, develop ]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.10'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
      
      - name: Run linters
        run: |
          black --check app/
          flake8 app/
          pylint app/
      
      - name: Run tests
        run: |
          pytest tests/ --cov=app --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v2
  
  build:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v2
      
      - name: Build Docker image
        run: |
          docker build -t sms-gateway:${{ github.sha }} .
      
      - name: Push to Registry
        run: |
          docker push sms-gateway:${{ github.sha }}
```

---

## 7. 开发规范

### 7.1 代码规范

- 遵循PEP 8规范
- 使用Black进行代码格式化
- 使用isort排序导入
- 使用类型注解（Type Hints）
- 每个函数必须有文档字符串

### 7.2 Git工作流

```bash
# 功能分支
git checkout -b feature/sms-api
git commit -m "feat: add SMS sending API"
git push origin feature/sms-api

# 提交规范（Conventional Commits）
feat: 新功能
fix: Bug修复
docs: 文档更新
style: 代码格式
refactor: 重构
test: 测试
chore: 构建/工具
```

### 7.3 代码审查清单

- [ ] 代码符合规范
- [ ] 有完整的单元测试
- [ ] 有文档字符串
- [ ] 无安全隐患
- [ ] 性能合理
- [ ] 错误处理完善

---

## 附录

### A. 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env

# 3. 初始化数据库
python scripts/init_db.py

# 4. 启动开发服务器
uvicorn app.main:app --reload

# 5. 访问API文档
open http://localhost:8000/docs
```

### B. 常用命令

```bash
# 运行测试
pytest

# 代码格式化
black app/
isort app/

# 代码检查
flake8 app/
pylint app/

# 生成迁移
alembic revision --autogenerate -m "message"

# 执行迁移
alembic upgrade head
```

---

**文档结束**

