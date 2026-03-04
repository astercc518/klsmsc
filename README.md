# 国际短信系统（SMSC） - International SMS Gateway System

## 📋 项目简介

国际短信网关系统是一个企业级的短信发送平台，支持多通道、多国家、灵活计费和自定义发送方ID。本系统旨在为企业提供稳定、高效、智能的国际短信服务。

### 核心特性

- ✅ **全球覆盖**: 支持200+国家和地区
- ✅ **智能路由**: 自动选择最优通道，降低成本
- ✅ **灵活计费**: 支持多国家、多通道、多运营商的差异化计费
- ✅ **品牌保护**: 支持自定义发送方ID
- ✅ **高可用**: 99.9%系统可用性，支持10,000+ TPS
- ✅ **多协议**: 支持SMPP、HTTP、SOAP等多种协议
- 🆕 **Telegram集成**: 通过Telegram Bot零门槛注册和发送短信

---

## 📚 项目文档

### 核心文档

1. **[项目总体规划](./docs/PROJECT_OVERVIEW.md)**
   - 项目背景和目标
   - 团队组织结构
   - 项目里程碑
   - 技术选型
   - 预算估算

2. **[业务需求文档 (PRD)](./docs/PRD.md)**
   - 产品定位和愿景
   - 功能需求详细说明
   - 用户故事和验收标准
   - 界面原型设计

3. **[技术架构设计](./docs/ARCHITECTURE.md)**
   - 系统架构图
   - 核心模块设计
   - 数据流设计
   - 缓存和安全设计
   - 监控和容灾方案

4. **[数据库设计](./docs/DATABASE_DESIGN.md)**
   - 完整的表结构设计
   - 索引优化策略
   - 分区和备份方案
   - 初始化脚本

5. **[后端开发计划](./docs/BACKEND_PLAN.md)**
   - 开发环境搭建
   - 项目结构说明
   - 分阶段开发计划（Week 1-16）
   - 核心代码示例
   - 测试和部署计划

6. **[前端开发计划](./docs/FRONTEND_PLAN.md)**
   - 前端技术栈（Vue 3 + TypeScript + Element Plus）
   - 项目结构说明
   - 分阶段开发计划（Week 1-13）
   - 页面组件示例
   - UI设计规范

7. **[Telegram Bot 集成方案](./docs/TELEGRAM_INTEGRATION.md)** 🆕
   - Telegram Bot功能设计
   - 账号自动创建流程
   - 短信发送任务提交
   - 完整代码实现
   - 安全和部署方案

8. **[Telegram Bot 快速开始](./docs/TELEGRAM_QUICKSTART.md)** 🆕
   - 5分钟快速部署指南
   - 用户使用示例
   - 高级配置和最佳实践
   - 常见问题解答
   - 生产环境部署

9. **[项目交付总结](./docs/PROJECT_SUMMARY.md)** ⭐
   - 完整的交付物清单
   - 核心功能实现方案
   - 性能指标和成本估算
   - 技术亮点和创新价值
   - 验收标准和下一步建议

---

## 🏗️ 技术架构

### 后端技术栈

| 技术 | 版本 | 说明 |
|------|------|------|
| Python | 3.10+ | 编程语言 |
| FastAPI | 0.104+ | Web框架 |
| SQLAlchemy | 2.0+ | ORM框架 |
| MySQL | 8.0 | 关系数据库 |
| Redis | 7.0 | 缓存/队列 |
| RabbitMQ | 3.12 | 消息队列 |
| Celery | 5.3 | 异步任务队列 |

### 前端技术栈

| 技术 | 版本 | 说明 |
|------|------|------|
| Vue | 3.3+ | 前端框架 |
| TypeScript | 5.0+ | 类型系统 |
| Element Plus | 2.4+ | UI组件库 |
| Vite | 5.0+ | 构建工具 |
| Pinia | 2.1+ | 状态管理 |
| ECharts | 5.4+ | 数据可视化 |

### 基础设施

| 技术 | 说明 |
|------|------|
| Docker | 容器化 |
| Nginx | 负载均衡 |
| Prometheus + Grafana | 监控告警 |
| ELK Stack | 日志分析 |
| Jaeger | 链路追踪 |

---

## 🚀 快速开始

### 环境要求

```bash
# 后端
Python 3.10+
MySQL 8.0
Redis 7.0
RabbitMQ 3.12

# 前端
Node.js 18+
npm 9+ / pnpm 8+
```

### 后端启动

```bash
# 1. 进入后端目录
cd backend

# 2. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置环境变量
cp .env.example .env
# 编辑.env文件，配置数据库连接等

# 5. 初始化数据库
python scripts/init_db.py

# 6. 启动服务
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

访问 API 文档: http://localhost:8000/docs

### 前端启动

```bash
# 1. 进入前端目录
cd frontend

# 2. 安装依赖
npm install
# 或使用 pnpm
pnpm install

# 3. 配置环境变量
cp .env.development .env.local
# 编辑.env.local文件

# 4. 启动开发服务器
npm run dev
```

访问前端页面: http://localhost:3000

### Telegram Bot 启动 🆕

```bash
# 1. 进入Bot目录
cd telegram_bot

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑.env，填写TELEGRAM_BOT_TOKEN等

# 4. 启动Bot服务
python -m bot.main
```

在Telegram中搜索您的Bot并发送 `/start` 开始使用！

### Docker 一键启动

```bash
# 启动所有服务（包含Telegram Bot）
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

---

## 📊 系统架构图

```
┌─────────────────────────────────────────────────────────┐
│                       客户端层                           │
│     Web API      SDK        Webhook                     │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────┼────────────────────────────────────┐
│              接入层 (Nginx)                              │
│    负载均衡 • SSL终结 • 限流 • 认证                      │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────┼────────────────────────────────────┐
│          应用服务层 (FastAPI)                            │
│  路由引擎 • 计费引擎 • SID管理 • 状态追踪                │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────┼────────────────────────────────────┐
│        消息队列层 (RabbitMQ)                             │
│  发送队列 • 回调队列 • 定时队列                          │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────┼────────────────────────────────────┐
│       通道服务层 (Celery Workers)                        │
│  SMPP Worker • HTTP Worker • SOAP Worker                │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────┴────────────────────────────────────┐
│             第三方服务商                                 │
│  Twilio • Nexmo • 阿里云 • 华为云                       │
└──────────────────────────────────────────────────────────┘
```

---

## 📦 项目结构

```
rpg/
├── backend/                # 后端代码
│   ├── app/
│   │   ├── api/           # API路由
│   │   ├── core/          # 核心业务逻辑
│   │   ├── models/        # 数据模型
│   │   ├── schemas/       # 数据模式
│   │   ├── services/      # 服务层
│   │   ├── workers/       # Celery任务
│   │   └── utils/         # 工具函数
│   ├── tests/             # 测试代码
│   └── requirements.txt   # Python依赖
│
├── frontend/              # 前端代码
│   ├── src/
│   │   ├── api/          # API接口
│   │   ├── components/   # 组件
│   │   ├── views/        # 页面
│   │   ├── router/       # 路由
│   │   ├── stores/       # 状态管理
│   │   └── utils/        # 工具函数
│   └── package.json      # npm依赖
│
├── telegram_bot/         # Telegram Bot 🆕
│   ├── bot/
│   │   ├── handlers/     # 命令处理器
│   │   ├── services/     # 业务服务
│   │   ├── keyboards/    # 按钮键盘
│   │   └── utils/        # 工具函数
│   ├── requirements.txt
│   └── Dockerfile
│
├── docs/                  # 项目文档
│   ├── PROJECT_OVERVIEW.md
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   ├── DATABASE_DESIGN.md
│   ├── BACKEND_PLAN.md
│   ├── FRONTEND_PLAN.md
│   └── TELEGRAM_INTEGRATION.md  🆕
│
├── docker/               # Docker配置
│   ├── Dockerfile
│   └── nginx.conf
│
├── scripts/              # 脚本工具
│   ├── init_db.py
│   └── backup.sh
│
├── docker-compose.yml    # Docker编排
└── README.md            # 本文件
```

---

## 🔐 核心功能

### 1. 多通道智能路由

- **优先级路由**: 按通道优先级自动选择
- **成本优先**: 选择价格最低的通道
- **质量优先**: 选择送达率最高的通道
- **负载均衡**: 按权重分配流量
- **故障转移**: 通道故障时自动切换

### 2. 多国家灵活计费

- 支持按国家设置价格
- 支持按运营商（MCC/MNC）细分价格
- 支持按通道差异化定价
- 长短信自动拆分计费
- 支持多币种（USD/CNY/EUR）

### 3. 可选发送方ID（SID）

- 支持自定义字母/数字SID
- 支持按账户、国家、通道配置
- 自动匹配最优SID
- 支持SID审核流程
- 各国SID规则适配

### 4. 状态追踪和回调

- 实时状态更新
- Webhook回调通知
- 送达报告处理
- 失败重试机制
- 状态查询API

### 5. 报表统计

- 发送量统计
- 成功率分析
- 费用统计
- 通道性能对比
- 国家分布分析
- 数据导出（Excel/CSV）

### 6. Telegram Bot集成 🆕

- **零门槛注册**: 在Telegram中直接完成账号创建
- **便捷发送**: 聊天窗口即可发送短信
- **批量发送**: 上传CSV文件批量发送
- **实时通知**: 送达状态自动推送
- **余额查询**: 随时查看账户余额
- **移动优先**: 手机即可完成所有操作

**使用流程**:
1. 在Telegram搜索Bot
2. 发送 `/start` 启动
3. 点击「注册账号」
4. 输入邮箱完成注册
5. 发送 `/send` 开始发送短信

**支持的命令**:
- `/start` - 启动Bot
- `/register` - 注册账号
- `/send` - 发送单条短信
- `/batch` - 批量发送
- `/balance` - 查询余额
- `/records` - 发送记录
- `/help` - 帮助信息

---

## 🧪 测试

### 后端测试

```bash
# 运行所有测试
pytest

# 运行单元测试
pytest tests/unit

# 运行集成测试
pytest tests/integration

# 生成覆盖率报告
pytest --cov=app --cov-report=html
```

### 前端测试

```bash
# 单元测试
npm run test:unit

# E2E测试
npm run test:e2e

# 覆盖率
npm run test:coverage
```

---

## 📈 性能指标

| 指标 | 目标 | 说明 |
|------|------|------|
| API响应时间 | P95 < 200ms | 95%的请求响应时间 |
| 系统可用性 | 99.9% | 年宕机时间 < 8.76小时 |
| 并发处理能力 | 10,000 TPS | 每秒事务数 |
| 短信送达率 | > 95% | 成功送达比例 |
| 数据可靠性 | 99.99% | 消息不丢失 |

---

## 🔒 安全特性

- ✅ API密钥认证（HMAC-SHA256签名）
- ✅ HTTPS强制加密
- ✅ IP白名单限制
- ✅ 请求频率限制（Rate Limiting）
- ✅ SQL注入防护
- ✅ XSS防护
- ✅ 敏感信息加密存储
- ✅ 审计日志记录

---

## 📖 API文档

启动后端服务后，访问以下地址查看API文档：

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

### API示例

```bash
# 发送短信
curl -X POST "http://localhost:8000/api/v1/sms/send" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "phone_number": "+8613800138000",
    "message": "Your verification code is 123456",
    "sender_id": "MyApp"
  }'

# 查询状态
curl -X GET "http://localhost:8000/api/v1/sms/status/{message_id}" \
  -H "X-API-Key: your_api_key"
```

---

## 🤝 开发规范

### 代码规范

- **后端**: 遵循PEP 8规范，使用Black格式化
- **前端**: 遵循Vue 3风格指南，使用ESLint + Prettier

### Git提交规范

```bash
feat: 新功能
fix: Bug修复
docs: 文档更新
style: 代码格式调整
refactor: 代码重构
test: 测试相关
chore: 构建/工具变更
```

### 分支管理

- `main`: 生产环境分支
- `develop`: 开发分支
- `feature/*`: 功能分支
- `hotfix/*`: 紧急修复分支

---

## 📅 开发进度

| 阶段 | 周期 | 状态 | 说明 |
|------|------|------|------|
| 需求和设计 | Week 1-2 | ✅ 完成 | 需求文档、架构设计 |
| 基础框架 | Week 3-5 | ✅ 完成 | 项目搭建、数据库设计 |
| 核心功能 | Week 6-10 | ✅ 完成 | 路由、计费、发送、SMPP、Webhook |
| 管理后台 | Week 11-14 | ✅ 完成 | 管理员登录、通道/费率管理 |
| 报表与导出 | Week 15-17 | ✅ 完成 | 发送统计、图表展示、Excel导出 |
| Telegram集成 | Week 18-19 | ✅ 完成 | Bot开发、账号注册、便捷发送 |
| 测试优化 | Week 20-22 | 🚧 进行中 | 测试覆盖率提升、性能压测 |
| 上线部署 | Week 23 | ⏳ 待开始 | 生产环境部署 |

---

## 🚀 项目当前状态

**总体进度**: **90%**
- ✅ **核心引擎**: 100% (路由、计费、发送)
- ✅ **管理后台**: 100% (JWT认证、CRUD)
- ✅ **数据分析**: 100% (统计、图表、导出)
- ✅ **Telegram**: 100% (Bot集成)
- 🚧 **质量保证**: 60%+ 测试覆盖率 (目标 >80%)

---

## 🏁 下一步计划 (Next Steps)

1. **质量加固 (Week 1)**
   - 提升测试覆盖率至 80% 以上
   - 完善 Worker 和 Webhook 的故障恢复测试

2. **性能压测 (Week 1-2)**
   - 执行 10,000 TPS 压力测试
   - 优化数据库查询索引和 Redis 缓存策略

3. **安全审计 (Week 2)**
   - 进行漏洞扫描和渗透测试
   - 完善管理员 RBAC 细粒度权限控制

4. **生产部署 (Week 3)**
   - 配置生产环境 CI/CD 流水线
   - 编写完整的生产环境运维手册和用户手册

---

## 🐛 问题反馈

如有问题或建议，请通过以下方式反馈：

- **Issue**: 在GitHub上提交Issue
- **Email**: support@example.com
- **文档**: 查看 `docs/` 目录下的详细文档

---

## 📄 许可证

本项目采用 MIT 许可证。详见 [LICENSE](./LICENSE) 文件。

---

## 👥 贡献者

感谢所有为本项目做出贡献的开发者！

---

## 🔗 相关链接

- [FastAPI官方文档](https://fastapi.tiangolo.com/)
- [Vue 3官方文档](https://vuejs.org/)
- [Element Plus官方文档](https://element-plus.org/)
- [SMPP 3.4协议规范](http://www.smsforum.net/)

---

**最后更新**: 2026-01-26

**版本**: v1.5.0

**状态**: 测试优化中 🚧

