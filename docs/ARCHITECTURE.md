# 国际短信系统 - 技术架构设计文档

## 文档信息
- **文档类型**: Architecture Design Document
- **系统名称**: International SMS Gateway System
- **文档版本**: v1.0
- **创建日期**: 2025-12-30
- **架构师**: [待填写]
- **审核状态**: 待审核

---

## 目录
1. [架构概述](#1-架构概述)
2. [系统架构](#2-系统架构)
3. [核心模块设计](#3-核心模块设计)
4. [数据流设计](#4-数据流设计)
5. [缓存设计](#5-缓存设计)
6. [安全设计](#6-安全设计)
7. [监控告警](#7-监控告警)
8. [容灾方案](#8-容灾方案)
9. [性能优化](#9-性能优化)
10. [部署架构](#10-部署架构)

---

## 1. 架构概述

### 1.1 设计目标
- **高性能**: 支持10,000+ TPS，API响应P95 < 200ms
- **高可用**: 99.9%系统可用性，无单点故障
- **可扩展**: 支持水平扩展，模块化设计
- **易维护**: 清晰的模块职责，完善的监控
- **安全性**: 多层安全防护，数据加密

### 1.2 架构原则
1. **单一职责**: 每个服务负责单一功能
2. **松耦合**: 服务间通过API/消息队列通信
3. **无状态**: 应用层无状态，便于水平扩展
4. **数据一致性**: 采用事务或最终一致性保证
5. **故障隔离**: 单个服务故障不影响整体
6. **可观测性**: 完善的日志、监控、追踪

### 1.3 技术选型概览
| 层次 | 技术选型 | 说明 |
|------|---------|------|
| 接入层 | Nginx | 负载均衡、SSL终结 |
| 应用层 | FastAPI (Python) | 高性能异步Web框架 |
| 任务队列 | Celery + RabbitMQ | 异步任务处理 |
| 数据库 | MySQL 8.0 | 关系数据存储 |
| 缓存 | Redis 7.0 | 缓存、会话、队列 |
| 消息队列 | RabbitMQ | 消息解耦 |
| 监控 | Prometheus + Grafana | 指标监控和可视化 |
| 日志 | ELK Stack | 日志收集和分析 |
| 容器化 | Docker + Docker Compose | 容器化部署 |

---

## 2. 系统架构

### 2.1 总体架构图

```
┌───────────────────────────────────────────────────────────────────┐
│                          客户端层                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │   Web API    │  │     SDK      │  │   Webhook    │           │
│  │  (REST/JSON) │  │ (多语言支持)  │  │   (回调)     │           │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘           │
└─────────┼──────────────────┼──────────────────┼───────────────────┘
          │                  │                  │
          └──────────────────┴──────────────────┘
                             │
┌────────────────────────────┼──────────────────────────────────────┐
│                      接入层 (API Gateway)                          │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                    Nginx / Kong                            │  │
│  │  • 负载均衡    • SSL/TLS终结   • 请求限流                   │  │
│  │  • IP白名单    • 健康检查      • 访问日志                   │  │
│  └────────────────────────────────────────────────────────────┘  │
└────────────────────────────┬──────────────────────────────────────┘
                             │
┌────────────────────────────┼──────────────────────────────────────┐
│                    应用服务层 (Backend Services)                   │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │                   API 服务 (FastAPI)                     │    │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐           │    │
│  │  │ 发送API   │  │ 查询API   │  │ 管理API   │           │    │
│  │  └───────────┘  └───────────┘  └───────────┘           │    │
│  └────────────┬─────────────────────────────────────────────┘    │
│               │                                                   │
│  ┌────────────┴──────────────────────────────────────────┐      │
│  │              业务逻辑层 (Business Logic)               │      │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐            │      │
│  │  │路由引擎  │  │计费引擎  │  │SID管理器 │            │      │
│  │  └──────────┘  └──────────┘  └──────────┘            │      │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐            │      │
│  │  │号码解析  │  │状态追踪  │  │权限控制  │            │      │
│  │  └──────────┘  └──────────┘  └──────────┘            │      │
│  └──────────────────────────┬──────────────────────────┘        │
└─────────────────────────────┼───────────────────────────────────┘
                              │
┌─────────────────────────────┼───────────────────────────────────┐
│                     消息队列层 (Message Queue)                    │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                   RabbitMQ Cluster                       │  │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐        │  │
│  │  │ 发送队列   │  │ 回调队列   │  │ 定时队列   │        │  │
│  │  │sms.send    │  │sms.callback│  │sms.schedule│        │  │
│  │  └────────────┘  └────────────┘  └────────────┘        │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────┬───────────────────────────────────┘
                              │
┌─────────────────────────────┼───────────────────────────────────┐
│                   通道服务层 (Channel Workers)                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │            Celery Worker Pool (多进程)                  │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │   │
│  │  │ SMPP Worker  │  │ HTTP Worker  │  │ SOAP Worker  │ │   │
│  │  │  (smpplib)   │  │  (aiohttp)   │  │   (zeep)     │ │   │
│  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘ │   │
│  │         │                 │                 │          │   │
│  └─────────┼─────────────────┼─────────────────┼──────────┘   │
└────────────┼─────────────────┼─────────────────┼──────────────┘
             │                 │                 │
             └─────────────────┴─────────────────┘
                             │
┌────────────────────────────┼──────────────────────────────────┐
│                   第三方服务商层 (Providers)                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │   Twilio     │  │    Nexmo     │  │   阿里云     │       │
│  │  (HTTP API)  │  │  (HTTP API)  │  │  (HTTP API)  │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
│  ┌──────────────┐  ┌──────────────┐                         │
│  │ 华为云(SMPP) │  │  中国移动    │                         │
│  └──────────────┘  └──────────────┘                         │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                       数据存储层 (Data Layer)                 │
│  ┌───────────────┐  ┌───────────────┐  ┌──────────────┐    │
│  │  MySQL 8.0    │  │   Redis 7.0   │  │  InfluxDB    │    │
│  │  (主从复制)    │  │   (集群模式)   │  │ (时序数据)   │    │
│  │               │  │               │  │              │    │
│  │• 业务数据      │  │• 缓存         │  │• 监控指标    │    │
│  │• 账户信息      │  │• 会话         │  │• 性能统计    │    │
│  │• 短信记录      │  │• 队列         │  │              │    │
│  │• 配置信息      │  │• 限流计数      │  │              │    │
│  └───────────────┘  └───────────────┘  └──────────────┘    │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                  监控运维层 (Observability)                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Prometheus   │  │   Grafana    │  │     ELK      │      │
│  │ (指标采集)    │  │  (可视化)    │  │  (日志分析)   │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Jaeger     │  │AlertManager  │  │   Nginx      │      │
│  │ (链路追踪)    │  │   (告警)     │  │  (日志)      │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 服务分层说明

#### 2.2.1 接入层
**职责**:
- 流量分发和负载均衡
- SSL/TLS加密终结
- 请求限流和防护
- IP白名单验证
- 健康检查

**技术**: Nginx + Lua脚本

#### 2.2.2 应用服务层
**职责**:
- API接口提供
- 业务逻辑处理
- 数据验证
- 权限认证

**技术**: FastAPI + Pydantic + SQLAlchemy

#### 2.2.3 消息队列层
**职责**:
- 异步任务队列
- 消息持久化
- 流量削峰
- 服务解耦

**技术**: RabbitMQ + Celery

#### 2.2.4 通道服务层
**职责**:
- 短信实际发送
- 协议转换（SMPP/HTTP/SOAP）
- 送达回执处理
- 错误重试

**技术**: Celery Worker + 协议库

#### 2.2.5 数据存储层
**职责**:
- 持久化存储
- 缓存加速
- 时序数据存储

**技术**: MySQL + Redis + InfluxDB

---

## 3. 核心模块设计

### 3.1 API服务模块

**技术栈**: FastAPI + Pydantic + SQLAlchemy

**目录结构**:
```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI应用入口
│   ├── config.py               # 配置管理
│   ├── dependencies.py         # 依赖注入
│   │
│   ├── api/                    # API路由
│   │   ├── __init__.py
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── sms.py          # 短信发送API
│   │   │   ├── status.py       # 状态查询API
│   │   │   ├── account.py      # 账户管理API
│   │   │   ├── channels.py     # 通道管理API
│   │   │   ├── pricing.py      # 计费查询API
│   │   │   └── sender_ids.py   # SID管理API
│   │
│   ├── core/                   # 核心业务逻辑
│   │   ├── __init__.py
│   │   ├── router.py           # 路由引擎
│   │   ├── pricing.py          # 计费引擎
│   │   ├── sender_id.py        # SID管理器
│   │   ├── phone_parser.py     # 号码解析
│   │   ├── status_tracker.py   # 状态追踪
│   │   └── auth.py             # 认证授权
│   │
│   ├── models/                 # 数据模型
│   │   ├── __init__.py
│   │   ├── account.py
│   │   ├── channel.py
│   │   ├── sms_log.py
│   │   ├── pricing.py
│   │   └── sender_id.py
│   │
│   ├── schemas/                # Pydantic模式
│   │   ├── __init__.py
│   │   ├── sms.py
│   │   ├── account.py
│   │   ├── channel.py
│   │   └── common.py
│   │
│   ├── services/               # 服务层
│   │   ├── __init__.py
│   │   ├── sms_service.py
│   │   ├── account_service.py
│   │   ├── channel_service.py
│   │   └── report_service.py
│   │
│   ├── workers/                # Celery任务
│   │   ├── __init__.py
│   │   ├── sms_worker.py
│   │   ├── smpp_worker.py
│   │   ├── http_worker.py
│   │   └── callback_worker.py
│   │
│   └── utils/                  # 工具函数
│       ├── __init__.py
│       ├── cache.py
│       ├── logger.py
│       ├── security.py
│       └── validators.py
```

**核心代码结构**:

```python
# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1 import sms, status, account, channels

app = FastAPI(
    title="International SMS Gateway API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(sms.router, prefix="/api/v1/sms", tags=["SMS"])
app.include_router(status.router, prefix="/api/v1/status", tags=["Status"])
app.include_router(account.router, prefix="/api/v1/account", tags=["Account"])
app.include_router(channels.router, prefix="/api/v1/channels", tags=["Channels"])

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
```

### 3.2 路由引擎模块

**职责**: 智能选择最优通道

**核心算法**:

```python
# app/core/router.py
from typing import Optional, List
from app.models.channel import Channel
from app.models.routing_rule import RoutingRule
from app.utils.cache import get_redis_client
import random

class RoutingEngine:
    def __init__(self, db_session, redis_client):
        self.db = db_session
        self.redis = redis_client
        
    async def select_channel(
        self, 
        country_code: str, 
        preferred_channel: Optional[str] = None,
        strategy: str = 'priority'
    ) -> Optional[Channel]:
        """
        选择最优通道
        
        Args:
            country_code: 国家代码
            preferred_channel: 指定通道（可选）
            strategy: 路由策略 (priority/cost/quality/load_balance)
            
        Returns:
            Channel对象或None
        """
        # 1. 如果指定了通道，验证并返回
        if preferred_channel:
            channel = await self._get_channel_by_code(preferred_channel, country_code)
            if channel and channel.status == 'active':
                return channel
            return None
        
        # 2. 获取可用通道列表
        channels = await self._get_available_channels(country_code)
        if not channels:
            return None
        
        # 3. 根据策略选择通道
        if strategy == 'priority':
            return self._select_by_priority(channels)
        elif strategy == 'cost':
            return await self._select_by_cost(channels, country_code)
        elif strategy == 'quality':
            return self._select_by_quality(channels)
        elif strategy == 'load_balance':
            return self._select_by_weight(channels)
        
        return None
    
    async def _get_available_channels(self, country_code: str) -> List[Channel]:
        """获取支持该国家的可用通道列表"""
        # 先从缓存获取
        cache_key = f"route:{country_code}"
        cached = await self.redis.get(cache_key)
        
        if cached:
            channel_ids = json.loads(cached)
            channels = []
            for cid in channel_ids:
                ch = await self.db.get(Channel, cid)
                if ch:
                    channels.append(ch)
            return channels
        
        # 从数据库查询
        query = """
            SELECT c.* FROM channels c
            JOIN routing_rules r ON c.id = r.channel_id
            WHERE r.country_code = :country_code
            AND c.status = 'active'
            AND r.is_active = TRUE
            ORDER BY r.priority DESC
        """
        result = await self.db.execute(query, {"country_code": country_code})
        channels = result.fetchall()
        
        # 缓存5分钟
        channel_ids = [ch.id for ch in channels]
        await self.redis.setex(cache_key, 300, json.dumps(channel_ids))
        
        return channels
    
    def _select_by_priority(self, channels: List[Channel]) -> Channel:
        """按优先级选择（优先级最高的）"""
        return max(channels, key=lambda x: x.priority)
    
    async def _select_by_cost(self, channels: List[Channel], country_code: str) -> Channel:
        """按成本选择（价格最低的）"""
        from app.core.pricing import PricingEngine
        pricing = PricingEngine(self.db, self.redis)
        
        min_price = float('inf')
        best_channel = None
        
        for channel in channels:
            price_info = await pricing.get_price(channel.id, country_code)
            if price_info and price_info['price'] < min_price:
                min_price = price_info['price']
                best_channel = channel
        
        return best_channel
    
    def _select_by_quality(self, channels: List[Channel]) -> Channel:
        """按质量选择（成功率最高的）"""
        return max(channels, key=lambda x: x.success_rate or 0)
    
    def _select_by_weight(self, channels: List[Channel]) -> Channel:
        """按权重负载均衡"""
        weights = [ch.weight or 100 for ch in channels]
        return random.choices(channels, weights=weights)[0]
```

### 3.3 计费引擎模块

**职责**: 计算费用和扣减余额

```python
# app/core/pricing.py
from decimal import Decimal
from typing import Dict, Optional
from app.models.country_pricing import CountryPricing
from app.models.account import Account

class PricingEngine:
    def __init__(self, db_session, redis_client):
        self.db = db_session
        self.redis = redis_client
    
    async def calculate_and_charge(
        self,
        account_id: int,
        channel_id: int,
        country_code: str,
        message: str
    ) -> Dict:
        """
        计算费用并扣款
        
        Returns:
            {
                'success': bool,
                'total_cost': Decimal,
                'message_count': int,
                'price_per_sms': Decimal,
                'currency': str
            }
        """
        # 1. 计算短信条数
        message_count = self._count_sms_parts(message)
        
        # 2. 查询价格
        price_info = await self.get_price(channel_id, country_code)
        if not price_info:
            return {'success': False, 'error': 'No pricing found'}
        
        price_per_sms = Decimal(str(price_info['price']))
        currency = price_info['currency']
        
        # 3. 计算总费用
        total_cost = price_per_sms * message_count
        
        # 4. 检查余额
        account = await self.db.get(Account, account_id)
        if not account or account.balance < total_cost:
            return {
                'success': False,
                'error': 'Insufficient balance',
                'required': float(total_cost),
                'available': float(account.balance) if account else 0
            }
        
        # 5. 扣减余额（使用数据库事务）
        try:
            async with self.db.begin():
                account.balance -= total_cost
                
                # 记录余额变动
                from app.models.balance_log import BalanceLog
                balance_log = BalanceLog(
                    account_id=account_id,
                    change_type='charge',
                    amount=-total_cost,
                    balance_before=account.balance + total_cost,
                    balance_after=account.balance,
                    currency=currency,
                    description=f"SMS charge: {message_count} parts"
                )
                self.db.add(balance_log)
                
            # 更新缓存
            await self.redis.setex(
                f"account:{account_id}:balance",
                60,
                str(account.balance)
            )
            
            return {
                'success': True,
                'total_cost': float(total_cost),
                'message_count': message_count,
                'price_per_sms': float(price_per_sms),
                'currency': currency
            }
            
        except Exception as e:
            await self.db.rollback()
            return {'success': False, 'error': str(e)}
    
    async def get_price(
        self,
        channel_id: int,
        country_code: str,
        mnc: Optional[str] = None
    ) -> Optional[Dict]:
        """
        查询价格（带缓存）
        
        优先级：通道+国家+运营商 > 通道+国家 > 通道默认
        """
        cache_key = f"price:{channel_id}:{country_code}:{mnc or 'default'}"
        
        # 先从缓存获取
        cached = await self.redis.get(cache_key)
        if cached:
            return json.loads(cached)
        
        # 从数据库查询
        # 1. 尝试匹配运营商级价格
        if mnc:
            query = """
                SELECT price_per_sms, currency, operator_name
                FROM country_pricing
                WHERE channel_id = :channel_id
                AND country_code = :country_code
                AND mnc = :mnc
                AND (effective_date <= CURDATE())
                AND (expiry_date IS NULL OR expiry_date >= CURDATE())
                ORDER BY effective_date DESC
                LIMIT 1
            """
            result = await self.db.execute(query, {
                'channel_id': channel_id,
                'country_code': country_code,
                'mnc': mnc
            })
            pricing = result.fetchone()
            if pricing:
                price_info = {
                    'price': float(pricing[0]),
                    'currency': pricing[1],
                    'operator': pricing[2]
                }
                await self.redis.setex(cache_key, 3600, json.dumps(price_info))
                return price_info
        
        # 2. 尝试匹配国家级价格
        query = """
            SELECT price_per_sms, currency, country_name
            FROM country_pricing
            WHERE channel_id = :channel_id
            AND country_code = :country_code
            AND mnc IS NULL
            AND (effective_date <= CURDATE())
            AND (expiry_date IS NULL OR expiry_date >= CURDATE())
            ORDER BY effective_date DESC
            LIMIT 1
        """
        result = await self.db.execute(query, {
            'channel_id': channel_id,
            'country_code': country_code
        })
        pricing = result.fetchone()
        
        if pricing:
            price_info = {
                'price': float(pricing[0]),
                'currency': pricing[1],
                'country': pricing[2]
            }
            await self.redis.setex(cache_key, 3600, json.dumps(price_info))
            return price_info
        
        return None
    
    def _count_sms_parts(self, message: str) -> int:
        """
        计算短信条数
        
        GSM-7编码: 160字符/条，超出按153字符/条拆分
        UCS-2编码: 70字符/条，超出按67字符/条拆分
        """
        if self._is_gsm7(message):
            # GSM-7编码
            if len(message) <= 160:
                return 1
            else:
                return (len(message) + 152) // 153
        else:
            # UCS-2编码（Unicode）
            if len(message) <= 70:
                return 1
            else:
                return (len(message) + 66) // 67
    
    def _is_gsm7(self, message: str) -> bool:
        """判断是否为GSM-7编码"""
        gsm7_chars = set(
            "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
            "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
        )
        return all(c in gsm7_chars for c in message)
```

### 3.4 SID管理器模块

```python
# app/core/sender_id.py
from typing import Optional
from app.models.sender_id import SenderID

class SenderIDManager:
    def __init__(self, db_session, redis_client):
        self.db = db_session
        self.redis = redis_client
    
    async def get_sender_id(
        self,
        account_id: int,
        country_code: str,
        channel_id: int,
        preferred_sid: Optional[str] = None
    ) -> Optional[str]:
        """
        获取发送方ID
        
        优先级:
        1. 用户指定的SID（需验证权限）
        2. 账户+国家+通道专属SID
        3. 账户+通道通用SID
        4. 通道默认SID
        """
        # 1. 如果指定了SID，验证权限和可用性
        if preferred_sid:
            sid = await self._validate_sid(
                preferred_sid, account_id, country_code, channel_id
            )
            if sid:
                return sid
        
        # 2. 查询账户+国家+通道专属SID
        query = """
            SELECT sid FROM sender_ids
            WHERE account_id = :account_id
            AND country_code = :country_code
            AND channel_id = :channel_id
            AND status = 'active'
            ORDER BY is_default DESC
            LIMIT 1
        """
        result = await self.db.execute(query, {
            'account_id': account_id,
            'country_code': country_code,
            'channel_id': channel_id
        })
        row = result.fetchone()
        if row:
            return row[0]
        
        # 3. 查询账户+通道通用SID（不限国家）
        query = """
            SELECT sid FROM sender_ids
            WHERE account_id = :account_id
            AND country_code IS NULL
            AND channel_id = :channel_id
            AND status = 'active'
            ORDER BY is_default DESC
            LIMIT 1
        """
        result = await self.db.execute(query, {
            'account_id': account_id,
            'channel_id': channel_id
        })
        row = result.fetchone()
        if row:
            return row[0]
        
        # 4. 获取通道默认SID
        from app.models.channel import Channel
        channel = await self.db.get(Channel, channel_id)
        if channel and channel.default_sender_id:
            return channel.default_sender_id
        
        return None
    
    async def _validate_sid(
        self,
        sid: str,
        account_id: int,
        country_code: str,
        channel_id: int
    ) -> Optional[str]:
        """验证SID是否可用"""
        query = """
            SELECT sid FROM sender_ids
            WHERE sid = :sid
            AND channel_id = :channel_id
            AND (country_code = :country_code OR country_code IS NULL)
            AND (account_id = :account_id OR account_id IS NULL)
            AND status = 'active'
            LIMIT 1
        """
        result = await self.db.execute(query, {
            'sid': sid,
            'channel_id': channel_id,
            'country_code': country_code,
            'account_id': account_id
        })
        row = result.fetchone()
        return row[0] if row else None
```

### 3.5 号码解析模块

```python
# app/core/phone_parser.py
import phonenumbers
from phonenumbers import geocoder, carrier
from typing import Dict

class PhoneNumberParser:
    """电话号码解析器"""
    
    @staticmethod
    def parse(phone_number: str) -> Dict:
        """
        解析电话号码
        
        Returns:
            {
                'valid': bool,
                'country_code': str,
                'country_name': str,
                'operator': str,
                'e164_format': str,
                'national_format': str
            }
        """
        try:
            # 解析号码
            parsed = phonenumbers.parse(phone_number, None)
            
            # 验证有效性
            is_valid = phonenumbers.is_valid_number(parsed)
            
            if not is_valid:
                return {'valid': False, 'error': 'Invalid phone number'}
            
            # 获取国家代码
            country_code = phonenumbers.region_code_for_number(parsed)
            
            # 获取国家名称
            country_name = geocoder.description_for_number(parsed, "zh")
            
            # 获取运营商（可能为空）
            operator = carrier.name_for_number(parsed, "en")
            
            # E.164格式（国际标准格式）
            e164_format = phonenumbers.format_number(
                parsed, 
                phonenumbers.PhoneNumberFormat.E164
            )
            
            # 本地格式
            national_format = phonenumbers.format_number(
                parsed,
                phonenumbers.PhoneNumberFormat.NATIONAL
            )
            
            return {
                'valid': True,
                'country_code': country_code,
                'country_name': country_name,
                'operator': operator or 'Unknown',
                'e164_format': e164_format,
                'national_format': national_format
            }
            
        except phonenumbers.phonenumberutil.NumberParseException as e:
            return {
                'valid': False,
                'error': str(e)
            }
```

---

## 4. 数据流设计

### 4.1 发送短信数据流

```
┌────────┐
│ Client │ 发送请求
└───┬────┘
    │ POST /api/v1/sms/send
    │ {phone, message, sender_id}
    ↓
┌────────────┐
│  Nginx     │ 1. 负载均衡
└─────┬──────┘ 2. SSL终结
      │
      ↓
┌────────────────┐
│  FastAPI       │ 3. 验证API密钥
│  (API Service) │ 4. 参数验证
└─────┬──────────┘
      │
      ↓
┌────────────────┐
│ PhoneParser    │ 5. 解析号码
└─────┬──────────┘    → +86138... → CN (中国)
      │
      ↓
┌────────────────┐
│ RoutingEngine  │ 6. 选择通道
└─────┬──────────┘    → Channel-CN-01
      │
      ↓
┌────────────────┐
│ SenderIDMgr    │ 7. 匹配SID
└─────┬──────────┘    → "MyApp"
      │
      ↓
┌────────────────┐
│ PricingEngine  │ 8. 计算费用
└─────┬──────────┘    → ¥0.05 × 1条 = ¥0.05
      │             9. 检查余额
      │             10. 扣款
      ↓
┌────────────────┐
│ MySQL          │ 11. 插入sms_logs
│ (sms_logs)     │     status='pending'
└─────┬──────────┘
      │
      ↓
┌────────────────┐
│ RabbitMQ       │ 12. 发送到队列
│ (sms.send)     │     消息持久化
└─────┬──────────┘
      │
      │ 13. 返回消息ID给客户端
      │     {"message_id": "MSG123..."}
      ↓
┌────────────────┐
│ Celery Worker  │ 14. 消费队列
│ (SMPP/HTTP)    │ 15. 调用通道API
└─────┬──────────┘ 16. 更新status='sent'
      │
      ↓
┌────────────────┐
│ 第三方通道      │ 17. 发送短信
│ (Twilio/Nexmo) │ 18. 返回送达回执
└─────┬──────────┘
      │
      ↓
┌────────────────┐
│ StatusTracker  │ 19. 更新status='delivered'
└─────┬──────────┘ 20. 触发Webhook
      │
      ↓
┌────────────────┐
│ CallbackWorker │ 21. HTTP POST到callback_url
│                │     {message_id, status, time}
└────────────────┘
```

---

## 5. 缓存设计

### 5.1 Redis数据结构

```
# 1. 路由缓存（Hash）
route:{country_code}
  - channel_id: 5
  - channel_name: "Channel-CN-01"
  - priority: 100
TTL: 5分钟

# 2. 价格缓存（String）
price:{channel_id}:{country_code}:{mnc}
  → "0.0500"
TTL: 1小时

# 3. 账户余额缓存（String）
account:{account_id}:balance
  → "1250.5000"
TTL: 1分钟

# 4. 短信状态缓存（Hash）
sms:{message_id}
  - status: "delivered"
  - submit_time: "2025-12-30 15:30:00"
  - delivery_time: "2025-12-30 15:30:05"
TTL: 24小时

# 5. 通道性能缓存（Hash）
channel:{channel_id}:stats
  - success_rate: "98.5"
  - avg_latency: "150"
  - current_tps: "850"
TTL: 1分钟

# 6. API限流计数器（Counter）
ratelimit:{api_key}:{minute}
  → 235 (当前分钟请求数)
TTL: 1分钟

# 7. SID缓存（Hash）
sid:{account_id}:{country_code}:{channel_id}
  - sid: "MyApp"
  - is_default: "true"
TTL: 10分钟

# 8. 会话缓存（String）
session:{token}
  → user_id, expires_at
TTL: 2小时
```

### 5.2 缓存更新策略

| 场景 | 策略 | 说明 |
|------|------|------|
| 读取路由 | Cache Aside | 先查缓存，未命中查DB |
| 更新价格 | Write Through | 写DB同时更新缓存 |
| 余额扣减 | Write Behind | 先扣DB，异步更新缓存 |
| 通道状态 | Cache Invalidation | 状态变更时删除缓存 |

---

## 6. 安全设计

### 6.1 认证机制

**API密钥 + HMAC签名**:

```python
# app/core/auth.py
import hmac
import hashlib
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")

async def verify_request(
    api_key: str = Security(api_key_header),
    timestamp: str = Header(..., alias="X-Timestamp"),
    signature: str = Header(..., alias="X-Signature"),
    body: bytes = Body(...)
):
    """验证API请求"""
    
    # 1. 查询API密钥对应的secret
    secret = await get_api_secret(api_key)
    if not secret:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    # 2. 验证时间戳（防重放攻击）
    current_time = int(time.time())
    request_time = int(timestamp)
    if abs(current_time - request_time) > 300:  # 5分钟有效期
        raise HTTPException(status_code=401, detail="Request expired")
    
    # 3. 计算签名
    message = f"{api_key}{timestamp}{body.decode()}"
    expected_signature = hmac.new(
        secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    
    # 4. 比较签名
    if not hmac.compare_digest(expected_signature, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    return api_key
```

**请求示例**:
```http
POST /api/v1/sms/send HTTP/1.1
Host: api.sms-gateway.com
Content-Type: application/json
X-API-Key: abc123def456...
X-Timestamp: 1735577200
X-Signature: a8f3c2e1b4d6...

{
  "phone_number": "+8613800138000",
  "message": "Your code is 123456"
}
```

### 6.2 限流策略

**基于令牌桶算法**:

```python
# app/utils/rate_limiter.py
from fastapi import HTTPException
from app.utils.cache import get_redis_client
from datetime import datetime

class RateLimiter:
    def __init__(self, redis_client):
        self.redis = redis_client
    
    async def check_limit(
        self,
        api_key: str,
        limit_per_minute: int = 1000
    ) -> bool:
        """
        检查是否超过限流
        
        Args:
            api_key: API密钥
            limit_per_minute: 每分钟限制次数
            
        Returns:
            True if allowed, raises HTTPException if rate limited
        """
        # 生成当前分钟的key
        current_minute = datetime.now().strftime("%Y%m%d%H%M")
        key = f"ratelimit:{api_key}:{current_minute}"
        
        # 增加计数
        current = await self.redis.incr(key)
        
        # 第一次设置过期时间
        if current == 1:
            await self.redis.expire(key, 60)
        
        # 检查是否超限
        if current > limit_per_minute:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {limit_per_minute} requests per minute"
            )
        
        return True
```

### 6.3 数据加密

```python
# app/utils/security.py
import bcrypt
from cryptography.fernet import Fernet

class SecurityUtils:
    @staticmethod
    def hash_password(password: str) -> str:
        """密码哈希"""
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    
    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        """验证密码"""
        return bcrypt.checkpw(password.encode(), hashed.encode())
    
    @staticmethod
    def encrypt_data(data: str, key: str) -> str:
        """数据加密（用于敏感信息）"""
        f = Fernet(key.encode())
        return f.encrypt(data.encode()).decode()
    
    @staticmethod
    def decrypt_data(encrypted: str, key: str) -> str:
        """数据解密"""
        f = Fernet(key.encode())
        return f.decrypt(encrypted.encode()).decode()
    
    @staticmethod
    def mask_phone(phone: str) -> str:
        """手机号脱敏"""
        if len(phone) < 7:
            return phone
        return phone[:3] + "****" + phone[-4:]
```

---

## 7. 监控告警

### 7.1 监控指标

**系统指标**:
- CPU使用率
- 内存使用率
- 磁盘I/O
- 网络流量

**应用指标**:
```python
# app/utils/metrics.py
from prometheus_client import Counter, Histogram, Gauge

# 请求计数器
request_counter = Counter(
    'api_requests_total',
    'Total API requests',
    ['method', 'endpoint', 'status']
)

# 响应时间直方图
response_time = Histogram(
    'api_response_time_seconds',
    'API response time',
    ['endpoint']
)

# 短信发送量
sms_sent = Counter(
    'sms_sent_total',
    'Total SMS sent',
    ['country', 'channel', 'status']
)

# 账户余额（实时）
account_balance = Gauge(
    'account_balance',
    'Account balance',
    ['account_id', 'currency']
)

# 通道TPS
channel_tps = Gauge(
    'channel_tps',
    'Channel transactions per second',
    ['channel_id', 'channel_name']
)
```

### 7.2 Prometheus告警规则

```yaml
# prometheus/alerts.yml
groups:
  - name: sms_alerts
    rules:
      # API响应时间告警
      - alert: HighAPILatency
        expr: histogram_quantile(0.95, rate(api_response_time_seconds_bucket[5m])) > 0.2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "API响应时间过高"
          description: "API P95延迟超过200ms，当前值: {{ $value }}s"
      
      # 短信成功率告警
      - alert: LowSMSSuccessRate
        expr: |
          rate(sms_sent_total{status="delivered"}[10m]) /
          rate(sms_sent_total[10m]) < 0.95
        for: 10m
        labels:
          severity: critical
        annotations:
          summary: "短信成功率低于95%"
          description: "当前成功率: {{ $value | humanizePercentage }}"
      
      # 通道故障告警
      - alert: ChannelDown
        expr: channel_tps == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "通道{{ $labels.channel_name }}不可用"
          description: "通道TPS为0，可能已故障"
      
      # 账户余额低告警
      - alert: LowAccountBalance
        expr: account_balance < 100
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "账户{{ $labels.account_id }}余额不足"
          description: "当前余额: {{ $value }} {{ $labels.currency }}"
      
      # 队列堆积告警
      - alert: QueueBacklog
        expr: rabbitmq_queue_messages{queue="sms.send"} > 10000
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "发送队列堆积"
          description: "当前队列长度: {{ $value }}"
```

---

## 8. 容灾方案

### 8.1 高可用架构

```
┌─────────────── 可用区 A ───────────────┐
│                                        │
│  ┌──────────┐      ┌──────────┐      │
│  │  Nginx1  │      │  Nginx2  │      │
│  │  (主)    │      │  (备)    │      │
│  └────┬─────┘      └────┬─────┘      │
│       │                 │             │
│  ┌────┴─────────────────┴────┐       │
│  │   API Service (x3)         │       │
│  │   (负载均衡)                │       │
│  └─────────────┬──────────────┘       │
│                │                       │
│  ┌─────────────┴──────────────┐       │
│  │   Celery Workers (x5)      │       │
│  └────────────────────────────┘       │
│                                        │
│  ┌──────────┐      ┌──────────┐      │
│  │  MySQL   │◄────►│  MySQL   │      │
│  │  Master  │      │  Slave1  │      │
│  └──────────┘      └──────────┘      │
│                                        │
│  ┌──────────┐      ┌──────────┐      │
│  │  Redis   │◄────►│  Redis   │      │
│  │  Master  │      │  Slave1  │      │
│  └──────────┘      └──────────┘      │
└────────────────────────────────────────┘
                     ║
           同步复制  ║  主从切换
                     ║
┌─────────────── 可用区 B ───────────────┐
│                                        │
│  ┌──────────┐      ┌──────────┐      │
│  │  Nginx3  │      │  Nginx4  │      │
│  │  (备)    │      │  (备)    │      │
│  └────┬─────┘      └────┬─────┘      │
│       │                 │             │
│  ┌────┴─────────────────┴────┐       │
│  │   API Service (x3)         │       │
│  └─────────────┬──────────────┘       │
│                │                       │
│  ┌─────────────┴──────────────┐       │
│  │   Celery Workers (x5)      │       │
│  └────────────────────────────┘       │
│                                        │
│  ┌──────────┐                         │
│  │  MySQL   │                         │
│  │  Slave2  │                         │
│  └──────────┘                         │
│                                        │
│  ┌──────────┐                         │
│  │  Redis   │                         │
│  │  Slave2  │                         │
│  └──────────┘                         │
└────────────────────────────────────────┘
```

### 8.2 数据备份策略

**MySQL备份**:
```bash
# 全量备份（每天凌晨2点）
0 2 * * * /usr/bin/mysqldump -u backup -p --all-databases \
  --single-transaction --master-data=2 \
  | gzip > /backup/mysql/full_$(date +\%Y\%m\%d).sql.gz

# 增量备份（每小时）
0 * * * * /usr/bin/mysqlbinlog --read-from-remote-server \
  --stop-never --raw mysql-bin > /backup/mysql/binlog/

# 备份保留策略
- 全量备份保留30天
- 增量备份保留7天
- 异地备份（同步到OSS）
```

**Redis备份**:
```bash
# RDB持久化（每6小时）
save 21600 1

# AOF持久化（实时）
appendonly yes
appendfsync everysec
```

### 8.3 故障恢复流程

**数据库故障恢复**:
```
1. 检测主库故障
   ↓
2. 提升从库为主库
   ↓
3. 修改应用配置指向新主库
   ↓
4. 验证数据一致性
   ↓
5. 恢复故障主库为从库
```

**RTO/RPO**:
- RTO (恢复时间目标): < 15分钟
- RPO (恢复点目标): < 5分钟

---

## 9. 性能优化

### 9.1 数据库优化

**索引优化**:
```sql
-- 短信记录表常用查询索引
CREATE INDEX idx_message_id ON sms_logs(message_id);
CREATE INDEX idx_account_time ON sms_logs(account_id, submit_time DESC);
CREATE INDEX idx_status_time ON sms_logs(status, submit_time DESC);
CREATE INDEX idx_phone ON sms_logs(phone_number);

-- 复合索引（覆盖索引）
CREATE INDEX idx_account_status_time 
ON sms_logs(account_id, status, submit_time DESC);

-- 计费规则表
CREATE INDEX idx_channel_country 
ON country_pricing(channel_id, country_code, mnc);
```

**查询优化**:
```sql
-- 避免全表扫描
EXPLAIN SELECT * FROM sms_logs 
WHERE account_id = 1001 AND submit_time >= '2025-12-01'
ORDER BY submit_time DESC LIMIT 100;

-- 使用覆盖索引
SELECT message_id, status, submit_time
FROM sms_logs
WHERE account_id = 1001 AND status = 'delivered';
```

**分区表**:
```sql
-- 按月分区
ALTER TABLE sms_logs PARTITION BY RANGE (UNIX_TIMESTAMP(submit_time)) (
    PARTITION p202512 VALUES LESS THAN (UNIX_TIMESTAMP('2026-01-01')),
    PARTITION p202601 VALUES LESS THAN (UNIX_TIMESTAMP('2026-02-01')),
    PARTITION p202602 VALUES LESS THAN (UNIX_TIMESTAMP('2026-03-01'))
);
```

### 9.2 应用层优化

**连接池配置**:
```python
# config.py
DATABASE_CONFIG = {
    'pool_size': 20,          # 连接池大小
    'max_overflow': 10,       # 最大溢出连接数
    'pool_timeout': 30,       # 获取连接超时时间
    'pool_recycle': 3600,     # 连接回收时间
    'pool_pre_ping': True     # 连接前ping测试
}
```

**批量操作**:
```python
# 批量插入
async def batch_insert_sms_logs(sms_logs: List[SMSLog]):
    """批量插入短信记录（性能优化）"""
    async with db.begin():
        db.bulk_insert_mappings(SMSLog, [log.dict() for log in sms_logs])
```

**异步处理**:
```python
# 使用asyncio并发处理
async def send_batch_sms(phone_numbers: List[str], message: str):
    tasks = [send_single_sms(phone, message) for phone in phone_numbers]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results
```

---

## 10. 部署架构

### 10.1 Docker Compose部署

```yaml
# docker-compose.yml
version: '3.8'

services:
  # Nginx负载均衡
  nginx:
    image: nginx:latest
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf
      - ./nginx/ssl:/etc/nginx/ssl
    depends_on:
      - api1
      - api2
    restart: always
  
  # API服务（多实例）
  api1:
    build: ./backend
    environment:
      - DATABASE_URL=mysql://user:pass@mysql:3306/sms_system
      - REDIS_URL=redis://redis:6379/0
      - RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/
    depends_on:
      - mysql
      - redis
      - rabbitmq
    restart: always
  
  api2:
    build: ./backend
    environment:
      - DATABASE_URL=mysql://user:pass@mysql:3306/sms_system
      - REDIS_URL=redis://redis:6379/0
      - RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/
    depends_on:
      - mysql
      - redis
      - rabbitmq
    restart: always
  
  # Celery Worker
  worker:
    build: ./backend
    command: celery -A app.workers worker --loglevel=info --concurrency=4
    environment:
      - DATABASE_URL=mysql://user:pass@mysql:3306/sms_system
      - REDIS_URL=redis://redis:6379/0
      - RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/
    depends_on:
      - mysql
      - redis
      - rabbitmq
    restart: always
    deploy:
      replicas: 3
  
  # MySQL数据库
  mysql:
    image: mysql:8.0
    environment:
      - MYSQL_ROOT_PASSWORD=rootpass
      - MYSQL_DATABASE=sms_system
      - MYSQL_USER=smsuser
      - MYSQL_PASSWORD=smspass
    volumes:
      - mysql_data:/var/lib/mysql
      - ./mysql/init.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "3306:3306"
    restart: always
  
  # Redis缓存
  redis:
    image: redis:7.0-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
    restart: always
  
  # RabbitMQ消息队列
  rabbitmq:
    image: rabbitmq:3-management-alpine
    environment:
      - RABBITMQ_DEFAULT_USER=guest
      - RABBITMQ_DEFAULT_PASS=guest
    ports:
      - "5672:5672"
      - "15672:15672"
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq
    restart: always
  
  # Prometheus监控
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"
    restart: always
  
  # Grafana可视化
  grafana:
    image: grafana/grafana:latest
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana_data:/var/lib/grafana
    ports:
      - "3000:3000"
    depends_on:
      - prometheus
    restart: always
  
  # 前端管理后台
  frontend:
    build: ./frontend
    ports:
      - "8080:80"
    depends_on:
      - api1
    restart: always

volumes:
  mysql_data:
  redis_data:
  rabbitmq_data:
  prometheus_data:
  grafana_data:
```

### 10.2 Kubernetes部署（可选）

```yaml
# k8s/deployment.yml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sms-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: sms-api
  template:
    metadata:
      labels:
        app: sms-api
    spec:
      containers:
      - name: api
        image: sms-gateway/api:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: db-secret
              key: url
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
---
apiVersion: v1
kind: Service
metadata:
  name: sms-api-service
spec:
  selector:
    app: sms-api
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8000
  type: LoadBalancer
```

---

## 附录

### A. 技术选型对比

| 需求 | 方案A | 方案B | 最终选择 | 理由 |
|------|-------|-------|---------|------|
| Web框架 | FastAPI | Flask | FastAPI | 高性能、异步、自动文档 |
| 数据库 | MySQL | PostgreSQL | MySQL | 团队熟悉度高、生态成熟 |
| 消息队列 | RabbitMQ | Kafka | RabbitMQ | 更轻量、易维护、满足需求 |
| 缓存 | Redis | Memcached | Redis | 功能更丰富（支持多种数据结构） |
| 任务队列 | Celery | RQ | Celery | 功能完整、文档丰富 |

### B. 参考资料

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SMPP 3.4 Specification](http://www.smsforum.net/)
- [Redis Best Practices](https://redis.io/topics/best-practices)
- [RabbitMQ Tutorials](https://www.rabbitmq.com/tutorials/tutorial-one-python.html)
- [Prometheus Documentation](https://prometheus.io/docs/)

### C. 变更历史

| 版本 | 日期 | 修改人 | 变更内容 |
|------|------|--------|---------|
| v1.0 | 2025-12-30 | System | 初始版本，完整架构设计 |

---

**文档结束**

