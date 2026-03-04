# Phase 4 部署指南

## 📋 部署清单

### 前置条件
- ✅ MySQL 8.0+ 已安装并运行
- ✅ Redis 7.0+ 已安装并运行
- ✅ Python 3.9+ 已安装
- ✅ Node.js 16+ 已安装
- ✅ 已获取Telegram Bot Token（可选，用于通知功能）

---

## 🚀 部署步骤

### 第一步：数据库迁移

执行Phase 4数据库迁移脚本：

```bash
# 进入项目目录
cd /var/smsc

# 执行迁移脚本
mysql -u smsuser -p sms_system < scripts/phase4_migration.sql
```

**迁移内容**：
- 创建 `system_config` 表（如果不存在）
- 创建 `sms_batches` 表（如果不存在）
- 创建 `sms_templates` 表（如果不存在）
- 为 `sms_batches` 表添加 `reject_reason` 字段
- 为 `invitation_codes` 表添加 `pricing_config` 字段
- 创建必要的索引
- 初始化系统配置数据

**验证迁移**：
```sql
-- 检查表是否存在
SHOW TABLES LIKE 'system_config';
SHOW TABLES LIKE 'sms_batches';
SHOW TABLES LIKE 'sms_templates';

-- 检查字段是否存在
DESC sms_batches;
DESC invitation_codes;
```

---

### 第二步：配置环境变量

#### 方式1：通过前端页面配置（推荐）

1. 启动后端服务：
```bash
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

2. 启动前端服务：
```bash
cd frontend
npm run dev
```

3. 访问系统配置页面：
   - 登录管理员账号
   - 导航到：**系统配置 / System Config**
   - 配置以下项：
     - `telegram_bot_token`: Telegram Bot Token
     - `telegram_bot_username`: Telegram Bot Username

#### 方式2：通过环境变量配置

创建或编辑 `.env` 文件：

```bash
# 后端 .env
cd backend
cat > .env << EOF
# Telegram配置
TELEGRAM_BOT_TOKEN=你的Bot_Token
TELEGRAM_BOT_USERNAME=your_bot_username

# 数据库配置
DATABASE_HOST=localhost
DATABASE_PORT=3306
DATABASE_USER=smsuser
DATABASE_PASSWORD=smspass
DATABASE_NAME=sms_system

# Redis配置
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# JWT配置
JWT_SECRET_KEY=your-secret-key-change-in-production
EOF
```

```bash
# Telegram Bot .env
cd telegram_bot
cat > .env << EOF
TELEGRAM_BOT_TOKEN=你的Bot_Token
API_BASE_URL=http://localhost:8000
REDIS_URL=redis://localhost:6379/1
EOF
```

---

### 第三步：安装依赖

#### 后端依赖

```bash
cd backend
pip install -r requirements.txt
```

#### 前端依赖

```bash
cd frontend
npm install
```

---

### 第四步：启动服务

#### 开发环境

**后端**：
```bash
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**前端**：
```bash
cd frontend
npm run dev
```

**Telegram Bot**（可选）：
```bash
cd telegram_bot
python -m bot.main
```

#### 生产环境

**使用Docker Compose**：
```bash
docker-compose up -d
```

**或使用systemd服务**：

创建 `/etc/systemd/system/smsc-backend.service`：
```ini
[Unit]
Description=SMS Gateway Backend
After=network.target mysql.service redis.service

[Service]
Type=simple
User=smsc
WorkingDirectory=/var/smsc/backend
Environment="PATH=/usr/local/bin:/usr/bin:/bin"
ExecStart=/usr/local/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

启动服务：
```bash
sudo systemctl enable smsc-backend
sudo systemctl start smsc-backend
sudo systemctl status smsc-backend
```

---

### 第五步：功能测试

运行测试脚本：

```bash
# 赋予执行权限
chmod +x scripts/test_phase4.sh

# 运行测试
./scripts/test_phase4.sh
```

**测试内容**：
- ✅ 系统配置管理API
- ✅ 邀请码管理API
- ✅ 充值审核API
- ✅ 群发审核API
- ✅ 白名单管理API
- ✅ Telegram配置检查

**手动测试**：

1. **邀请码管理**：
   - 访问：`/admin/bot/invites`
   - 创建邀请码
   - 查看邀请码列表
   - 测试筛选功能

2. **充值审核**：
   - 访问：`/admin/bot/recharge`
   - 查看待审核工单
   - 测试审核通过/拒绝
   - 验证Telegram通知（如果已配置）

3. **群发审核**：
   - 访问：`/admin/bot/batches`
   - 查看待审核批次
   - 测试审核通过/拒绝
   - 验证Telegram通知（如果已配置）

4. **白名单管理**：
   - 访问：`/admin/bot/templates`
   - 创建白名单
   - 编辑白名单
   - 删除白名单

5. **系统配置**：
   - 访问：`/admin/system/config`
   - 配置Telegram Bot Token
   - 配置其他系统参数

---

## 🔧 常见问题

### 1. 数据库迁移失败

**问题**：执行迁移脚本时报错

**解决**：
```bash
# 检查MySQL连接
mysql -u smsuser -p -e "USE sms_system; SHOW TABLES;"

# 检查表是否已存在
mysql -u smsuser -p sms_system -e "SHOW TABLES LIKE 'system_config';"

# 如果表已存在，可以手动执行缺失的字段添加
mysql -u smsuser -p sms_system << EOF
ALTER TABLE sms_batches ADD COLUMN IF NOT EXISTS reject_reason VARCHAR(500);
ALTER TABLE invitation_codes ADD COLUMN IF NOT EXISTS pricing_config JSON;
EOF
```

### 2. Telegram通知不工作

**问题**：审核后用户未收到Telegram通知

**检查清单**：
1. ✅ Telegram Bot Token 已配置（系统配置页面或环境变量）
2. ✅ 用户账户已绑定Telegram（telegram_bindings表）
3. ✅ Telegram Bot服务正在运行
4. ✅ 检查后端日志：`tail -f backend/logs/app.log`

**调试**：
```python
# 在Python中测试Telegram API
import httpx
import os

bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
chat_id = "你的Telegram用户ID"

url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
payload = {
    "chat_id": chat_id,
    "text": "测试消息"
}

async with httpx.AsyncClient() as client:
    response = await client.post(url, json=payload)
    print(response.json())
```

### 3. 前端页面无法访问

**问题**：访问系统配置页面404

**解决**：
1. 检查路由配置：`frontend/src/router/index.ts`
2. 检查菜单配置：`frontend/src/layouts/MainLayout.vue`
3. 清除浏览器缓存
4. 重新构建前端：
```bash
cd frontend
npm run build
```

### 4. 权限不足

**问题**：提示"需要管理员权限"

**解决**：
1. 确认当前登录账号角色为 `super_admin` 或 `admin`
2. 检查JWT Token是否有效
3. 重新登录获取新Token

---

## 📊 性能优化建议

### 数据库优化

```sql
-- 分析表统计信息
ANALYZE TABLE sms_batches;
ANALYZE TABLE sms_templates;
ANALYZE TABLE invitation_codes;

-- 优化表
OPTIMIZE TABLE sms_batches;
OPTIMIZE TABLE sms_templates;
```

### 缓存配置

在Redis中缓存常用配置：
```python
# 在系统配置读取时添加Redis缓存
import redis
r = redis.Redis(host='localhost', port=6379, db=0)

def get_config(key):
    cache_key = f"config:{key}"
    cached = r.get(cache_key)
    if cached:
        return cached.decode()
    # 从数据库读取并缓存
    value = db.get_config(key)
    r.setex(cache_key, 3600, value)  # 缓存1小时
    return value
```

---

## 🔐 安全建议

1. **环境变量安全**：
   - 不要将 `.env` 文件提交到Git
   - 使用密钥管理服务（如AWS Secrets Manager）
   - 定期轮换密钥

2. **数据库安全**：
   - 使用强密码
   - 限制数据库访问IP
   - 定期备份数据库

3. **API安全**：
   - 启用HTTPS
   - 配置CORS白名单
   - 实施API限流

4. **Telegram安全**：
   - 保护Bot Token
   - 验证消息来源
   - 实施消息签名验证

---

## 📝 部署检查清单

- [ ] 数据库迁移已执行
- [ ] 系统配置已设置（Telegram Token等）
- [ ] 后端服务已启动
- [ ] 前端服务已启动
- [ ] 功能测试已通过
- [ ] Telegram通知已测试
- [ ] 日志记录正常
- [ ] 监控告警已配置
- [ ] 备份策略已制定

---

## 📞 技术支持

如有问题，请参考：
- [Phase 4实施总结](./PHASE_4_IMPLEMENTATION_SUMMARY.md)
- [开发计划文档](./DEVELOPMENT_PLAN_AND_ACCEPTANCE.md)
- [API接口文档](./API_SPECIFICATION.md)

---

**部署完成！** ✅
