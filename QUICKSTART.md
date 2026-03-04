# 快速启动指南

## 前提条件

- Docker 和 Docker Compose
- Node.js 18+ (仅用于前端开发)
- Python 3.10+ (仅用于本地开发)

## 一键启动 (Docker Compose)

### 1. 启动所有服务

```bash
cd /var/smsc
docker-compose up -d
```

这将启动以下服务:
- MySQL (端口 3306)
- Redis (端口 6379)
- RabbitMQ (端口 5672, 管理界面 15672)
- API服务 (端口 8000)
- Celery Worker
- Prometheus (端口 9090)
- Grafana (端口 3000)

### 2. 查看服务状态

```bash
docker-compose ps
```

### 3. 查看日志

```bash
# 查看所有服务日志
docker-compose logs -f

# 查看特定服务日志
docker-compose logs -f api
docker-compose logs -f worker
```

### 4. 访问服务

- **API文档**: http://localhost:8000/docs
- **RabbitMQ管理界面**: http://localhost:15672 (用户名: guest, 密码: guest)
- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (用户名: admin, 密码: admin)

## 前端启动

### 1. 安装依赖

```bash
cd frontend
npm install
# 或
pnpm install
```

### 2. 启动开发服务器

```bash
npm run dev
```

### 3. 访问前端

http://localhost:3000

### 4. 构建生产版本

```bash
npm run build
```

## Telegram Bot 启动

### 1. 配置环境变量

```bash
cd telegram_bot
cp .env.example .env
```

编辑 `.env` 文件:
```
TELEGRAM_BOT_TOKEN=your_bot_token_here
API_BASE_URL=http://api:8000
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 启动Bot

```bash
python -m bot.main
```

或使用Docker:
```bash
docker build -t smsc-telegram-bot .
docker run -d --name telegram-bot --env-file .env smsc-telegram-bot
```

## 使用说明

### 1. 注册账户

#### 方式一: 通过API

```bash
curl -X POST "http://localhost:8000/api/v1/account/register" \
  -H "Content-Type: application/json" \
  -d '{
    "account_name": "测试账户",
    "email": "test@example.com",
    "password": "password123",
    "company_name": "测试公司"
  }'
```

#### 方式二: 通过Telegram Bot

1. 在Telegram搜索你的Bot
2. 发送 `/start`
3. 点击"注册账户"按钮
4. 按提示完成注册

### 2. 登录管理后台

1. 访问 http://localhost:3000
2. 使用注册的邮箱和密码登录
3. 或使用API Key直接访问

### 3. 发送短信

#### 方式一: 通过API

```bash
curl -X POST "http://localhost:8000/api/v1/sms/send" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key_here" \
  -d '{
    "phone_number": "+8613800138000",
    "message": "测试短信内容",
    "sender_id": "TestApp"
  }'
```

#### 方式二: 通过管理后台

1. 登录管理后台
2. 点击"发送短信"
3. 填写号码和内容
4. 点击发送

#### 方式三: 通过Telegram Bot

1. 在Bot中发送 `/send`
2. 输入目标号码
3. 输入短信内容
4. 确认发送

### 4. 查询余额

```bash
curl -X GET "http://localhost:8000/api/v1/account/balance" \
  -H "X-API-Key: your_api_key_here"
```

或在管理后台查看，或使用Bot的 `/balance` 命令。

## 停止服务

```bash
docker-compose down
```

保留数据:
```bash
docker-compose down
```

删除所有数据:
```bash
docker-compose down -v
```

## 数据库管理

### 连接数据库

```bash
docker-compose exec mysql mysql -u smsuser -psmspass123 sms_system
```

### 查看表

```sql
SHOW TABLES;
SELECT * FROM accounts;
SELECT * FROM channels;
SELECT * FROM sms_logs LIMIT 10;
```

### 备份数据库

```bash
docker-compose exec mysql mysqldump -u smsuser -psmspass123 sms_system > backup.sql
```

### 恢复数据库

```bash
docker-compose exec -T mysql mysql -u smsuser -psmspass123 sms_system < backup.sql
```

## 故障排查

### 服务无法启动

1. 检查端口占用:
```bash
netstat -tulpn | grep -E '3306|6379|5672|8000'
```

2. 查看容器日志:
```bash
docker-compose logs service_name
```

### API 502错误

检查API服务是否正常启动:
```bash
docker-compose logs api
docker-compose restart api
```

### Worker不处理消息

检查RabbitMQ连接:
```bash
docker-compose logs worker
docker-compose exec rabbitmq rabbitmqctl list_queues
```

### 数据库连接失败

检查MySQL是否就绪:
```bash
docker-compose exec mysql mysqladmin ping -h localhost -u root -prootpass123
```

## 性能优化

### 1. 增加Worker数量

编辑 `docker-compose.yml`:
```yaml
worker:
  deploy:
    replicas: 5
```

### 2. 调整数据库连接池

编辑 `backend/app/config.py`:
```python
DATABASE_POOL_SIZE = 50
DATABASE_MAX_OVERFLOW = 20
```

### 3. 配置Redis缓存

编辑 `docker-compose.yml` 的Redis部分:
```yaml
command: redis-server --maxmemory 2gb --maxmemory-policy allkeys-lru
```

## 生产部署建议

1. **使用独立的数据库服务器**
2. **配置SSL/TLS证书**
3. **启用Redis持久化**
4. **配置日志轮转**
5. **设置监控告警**
6. **定期备份数据库**
7. **使用负载均衡器**

## 更多文档

- [项目总览](./README.md)
- [业务需求文档](./docs/PRD.md)
- [技术架构设计](./docs/ARCHITECTURE.md)
- [数据库设计](./docs/DATABASE_DESIGN.md)
- [后端开发计划](./docs/BACKEND_PLAN.md)
- [前端开发计划](./docs/FRONTEND_PLAN.md)
- [Telegram Bot集成](./docs/TELEGRAM_INTEGRATION.md)

## 技术支持

如有问题，请查看文档或联系开发团队。

