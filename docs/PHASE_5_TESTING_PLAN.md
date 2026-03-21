# Phase 5: 全面测试与优化 - 详细开发计划

## 📋 概述

**阶段**: Phase 5  
**周期**: 2-3 周  
**目标**: 将测试覆盖率从当前水平提升至 80%+，确保系统生产就绪  
**状态**: 🚀 进行中

---

## 🎯 核心目标

| 目标项 | 当前状态 | 目标值 | 优先级 |
|--------|---------|--------|--------|
| 单元测试覆盖率 | ~40% | > 80% | 🔴 最高 |
| 集成测试用例数 | 8个 | 30+ | 🔴 最高 |
| 压力测试通过 | 未测试 | 10,000 TPS | 🟡 中 |
| 安全测试通过 | 未测试 | 无高危漏洞 | 🟡 中 |
| E2E测试覆盖 | 0% | 核心流程100% | 🟢 低 |

---

## 📅 详细开发时间表

### Week 1: 单元测试补充 (Day 1-5)

#### Day 1-2: Worker 层测试
- [ ] `test_sms_worker.py` - SMS发送Worker测试
- [ ] `test_webhook_worker.py` - Webhook回调Worker测试
- [ ] `test_celery_tasks.py` - Celery任务测试

#### Day 3-4: Adapter 层测试
- [ ] `test_smpp_adapter.py` - SMPP协议适配器测试
- [ ] `test_http_adapter.py` - HTTP协议适配器测试
- [ ] Mock外部依赖（SMPP服务器、HTTP通道）

#### Day 5: 工具类测试
- [ ] `test_cache.py` - Redis缓存测试
- [ ] `test_validator.py` - 验证器测试
- [ ] `test_logger.py` - 日志模块测试

### Week 2: 集成测试与E2E测试 (Day 6-10)

#### Day 6-7: API集成测试补充
- [ ] `test_api_admin.py` - 管理后台API测试
- [ ] `test_api_reports.py` - 报表统计API测试
- [ ] `test_api_bot_admin.py` - TG助手管理API测试
- [ ] `test_api_channels.py` - 通道管理API测试

#### Day 8-9: E2E完整流程测试
- [ ] `test_e2e_sms_flow.py` - 完整发送流程测试
- [ ] `test_e2e_recharge_flow.py` - 充值审核流程测试
- [ ] `test_e2e_batch_flow.py` - 群发审核流程测试

#### Day 10: 边界条件与异常测试
- [ ] 网络超时测试
- [ ] 数据库连接失败测试
- [ ] 消息队列故障测试
- [ ] 并发竞态条件测试

### Week 3: 性能测试与安全测试 (Day 11-15)

#### Day 11-12: 性能测试
- [ ] 创建 Locust 压测脚本
- [ ] 单接口性能基准测试
- [ ] 高并发发送场景测试
- [ ] 数据库查询性能分析

#### Day 13-14: 安全测试
- [ ] SQL注入测试
- [ ] XSS攻击测试
- [ ] CSRF防护测试
- [ ] 权限越权测试
- [ ] API认证绕过测试

#### Day 15: 测试报告与优化
- [ ] 生成测试覆盖率报告
- [ ] 识别低覆盖率模块
- [ ] 制定优化计划
- [ ] 文档更新

---

## 🗂️ 测试目录结构

```
backend/tests/
├── __init__.py
├── conftest.py                 # 共享fixtures和配置
├── fixtures/
│   ├── __init__.py
│   ├── account_fixtures.py     # 账户测试数据
│   ├── channel_fixtures.py     # 通道测试数据
│   └── sms_fixtures.py         # 短信测试数据
├── unit/
│   ├── __init__.py
│   ├── test_auth.py            # ✅ 已存在
│   ├── test_models.py          # ✅ 已存在
│   ├── test_phone_parser.py    # ✅ 已存在
│   ├── test_pricing.py         # ✅ 已存在
│   ├── test_router.py          # ✅ 已存在
│   ├── test_sender_id.py       # ✅ 已存在
│   ├── test_sms_worker.py      # 🆕 待创建
│   ├── test_webhook_worker.py  # 🆕 待创建
│   ├── test_smpp_adapter.py    # 🆕 待创建
│   ├── test_http_adapter.py    # 🆕 待创建
│   ├── test_cache.py           # 🆕 待创建
│   └── test_validator.py       # 🆕 待创建
├── integration/
│   ├── __init__.py
│   ├── test_api_account.py         # ✅ 已存在
│   ├── test_api_account_extended.py # ✅ 已存在
│   ├── test_api_sms.py             # ✅ 已存在
│   ├── test_middleware.py          # ✅ 已存在
│   ├── test_api_admin.py           # 🆕 待创建
│   ├── test_api_reports.py         # 🆕 待创建
│   ├── test_api_bot_admin.py       # 🆕 待创建
│   └── test_api_channels.py        # 🆕 待创建
├── e2e/
│   ├── __init__.py
│   ├── test_sms_flow.py        # 🆕 待创建
│   ├── test_recharge_flow.py   # 🆕 待创建
│   └── test_batch_flow.py      # 🆕 待创建
└── performance/
    ├── __init__.py
    ├── locustfile.py           # 🆕 待创建
    └── benchmark.py            # 🆕 待创建
```

---

## 📝 测试用例详细清单

### 1. SMS Worker 测试 (`test_sms_worker.py`)

| 测试用例ID | 测试名称 | 描述 | 优先级 |
|-----------|---------|------|--------|
| SW-001 | test_send_sms_task_success | 成功发送短信任务 | 高 |
| SW-002 | test_send_sms_task_channel_not_found | 通道不存在时的处理 | 高 |
| SW-003 | test_send_sms_task_retry_on_failure | 失败时自动重试 | 高 |
| SW-004 | test_send_sms_task_max_retries | 达到最大重试次数 | 中 |
| SW-005 | test_send_sms_http_channel | HTTP通道发送 | 高 |
| SW-006 | test_send_sms_smpp_channel | SMPP通道发送 | 高 |
| SW-007 | test_send_sms_status_update | 发送后状态更新 | 高 |
| SW-008 | test_send_sms_concurrent | 并发发送处理 | 中 |

### 2. Webhook Worker 测试 (`test_webhook_worker.py`)

| 测试用例ID | 测试名称 | 描述 | 优先级 |
|-----------|---------|------|--------|
| WH-001 | test_send_webhook_success | 成功发送Webhook | 高 |
| WH-002 | test_send_webhook_no_url | 无Webhook URL配置 | 高 |
| WH-003 | test_send_webhook_retry | 失败重试机制 | 高 |
| WH-004 | test_send_webhook_signature | HMAC签名验证 | 高 |
| WH-005 | test_send_webhook_timeout | 超时处理 | 中 |
| WH-006 | test_send_webhook_400_response | 4xx响应处理 | 中 |
| WH-007 | test_send_webhook_500_response | 5xx响应处理 | 中 |

### 3. SMPP Adapter 测试 (`test_smpp_adapter.py`)

| 测试用例ID | 测试名称 | 描述 | 优先级 |
|-----------|---------|------|--------|
| SMPP-001 | test_connect_success | 成功连接SMPP服务器 | 高 |
| SMPP-002 | test_connect_failure | 连接失败处理 | 高 |
| SMPP-003 | test_send_short_message | 发送短短信 | 高 |
| SMPP-004 | test_send_long_message | 发送长短信（拆分） | 高 |
| SMPP-005 | test_send_unicode_message | 发送Unicode消息 | 高 |
| SMPP-006 | test_heartbeat | 心跳保活 | 中 |
| SMPP-007 | test_reconnect | 断线重连 | 中 |
| SMPP-008 | test_handle_dlr | 处理送达报告 | 高 |
| SMPP-009 | test_gsm7_encoding | GSM-7编码 | 中 |
| SMPP-010 | test_ucs2_encoding | UCS-2编码 | 中 |

### 4. 集成测试补充

| 测试用例ID | 测试文件 | 测试内容 | 优先级 |
|-----------|---------|---------|--------|
| INT-001 | test_api_admin.py | 管理员登录 | 高 |
| INT-002 | test_api_admin.py | 管理员权限验证 | 高 |
| INT-003 | test_api_channels.py | 通道CRUD操作 | 高 |
| INT-004 | test_api_channels.py | 通道状态切换 | 中 |
| INT-005 | test_api_reports.py | 发送统计查询 | 中 |
| INT-006 | test_api_reports.py | 数据导出 | 低 |
| INT-007 | test_api_bot_admin.py | 邀请码管理 | 高 |
| INT-008 | test_api_bot_admin.py | 充值审核 | 高 |
| INT-009 | test_api_bot_admin.py | 群发审核 | 高 |

### 5. E2E 完整流程测试

| 测试用例ID | 测试名称 | 流程描述 | 优先级 |
|-----------|---------|---------|--------|
| E2E-001 | test_complete_sms_flow | API请求→验证→路由→计费→入队→Worker发送→状态更新→Webhook | 高 |
| E2E-002 | test_batch_send_flow | 批量发送→CSV解析→验证→分批入队→并发发送 | 高 |
| E2E-003 | test_recharge_approval_flow | TG充值申请→财务审核→余额增加→TG通知 | 高 |
| E2E-004 | test_batch_audit_flow | TG群发申请→管理员审核→自动发送→状态跟踪 | 高 |

---

## 🔧 技术实现

### Mock 策略

```python
# 外部依赖Mock清单
MOCKS = {
    "redis": "app.utils.cache.get_redis_client",
    "smpp_client": "smpplib.client.Client",
    "http_client": "httpx.AsyncClient",
    "celery": "app.workers.celery_app.celery_app",
    "telegram_bot": "telegram.Bot"
}
```

### Fixtures 复用

```python
# conftest.py 中的核心fixtures
- db_session: 测试数据库会话
- test_account: 测试账户
- test_channel: 测试通道
- test_pricing: 测试价格规则
- test_routing_rule: 测试路由规则
- mock_redis: Mock Redis客户端
- mock_cache_manager: Mock缓存管理器
```

---

## 📊 验收标准

### 测试覆盖率要求

| 模块 | 最低覆盖率 | 目标覆盖率 |
|------|-----------|-----------|
| `app/core/` | 90% | 95% |
| `app/api/` | 80% | 90% |
| `app/workers/` | 75% | 85% |
| `app/utils/` | 70% | 80% |
| **总体** | **80%** | **85%** |

### 性能基准

| 指标 | 基准值 | 目标值 |
|------|-------|-------|
| API响应时间 (P95) | < 200ms | < 100ms |
| 并发TPS | 5,000 | 10,000 |
| Worker吞吐量 | 1,000/s | 2,000/s |
| 数据库查询 (P95) | < 50ms | < 30ms |

### 安全检查清单

- [ ] 无SQL注入漏洞
- [ ] 无XSS漏洞
- [ ] 无CSRF漏洞
- [ ] 无敏感信息泄露
- [ ] 权限控制严格
- [ ] API认证有效
- [ ] 密码存储安全

---

## 🚀 执行命令

### 运行全部测试
```bash
cd /var/smsc/backend
pytest -v --cov=app --cov-report=html
```

### 仅运行单元测试
```bash
pytest tests/unit -v -m unit
```

### 仅运行集成测试
```bash
pytest tests/integration -v -m integration
```

### 生成覆盖率报告
```bash
pytest --cov=app --cov-report=html --cov-report=term-missing
# 报告位置: htmlcov/index.html
```

### 运行性能测试
```bash
cd /var/smsc/backend/tests/performance
locust -f locustfile.py --host=http://localhost:8000
```

---

## 📞 问题反馈

如有测试相关问题，请参考：
- [pytest 官方文档](https://docs.pytest.org/)
- [pytest-asyncio 文档](https://pytest-asyncio.readthedocs.io/)
- [Locust 官方文档](https://locust.io/)

---

**创建时间**: 2026-01-20  
**最后更新**: 2026-01-20  
**版本**: v1.0  
**负责人**: [待分配]
