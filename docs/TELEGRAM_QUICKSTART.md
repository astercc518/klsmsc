# Telegram Bot 快速开始指南

## 🚀 5分钟快速部署

### 第一步：创建Telegram Bot

1. 在Telegram中搜索 **@BotFather**
2. 发送 `/newbot` 创建新Bot
3. 按提示输入Bot名称和用户名：
   ```
   Bot名称: SMS Gateway Bot
   Bot用户名: your_sms_bot（必须以bot结尾）
   ```
4. 保存BotFather返回的Token：
   ```
   Token: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz
   ```

### 第二步：配置Bot命令

继续与BotFather对话：

```
/setcommands

然后复制粘贴以下命令列表：

send - 发送短信
batch - 批量发送
balance - 查询余额
records - 发送记录
status - 查询状态
recharge - 充值申请
settings - 账户设置
help - 帮助信息
```

### 第三步：配置环境变量

创建 `telegram_bot/.env` 文件：

```bash
# Telegram配置
TELEGRAM_BOT_TOKEN=你的Bot_Token
TELEGRAM_BOT_USERNAME=your_sms_bot

# 后端API
API_BASE_URL=http://localhost:8000
INTERNAL_API_KEY=生成一个随机密钥

# Redis
REDIS_URL=redis://localhost:6379/1

# 开发环境使用轮询模式
USE_WEBHOOK=false

# 新用户赠送
FREE_SMS_CREDITS=10
```

### 第四步：安装依赖

```bash
cd telegram_bot
pip install python-telegram-bot==20.7
pip install httpx
pip install redis
pip install python-dotenv
```

### 第五步：启动Bot

```bash
python -m bot.main
```

看到以下信息表示启动成功：
```
INFO - Bot started successfully
INFO - Polling for updates...
```

### 第六步：测试Bot

1. 在Telegram中搜索您的Bot（@your_sms_bot）
2. 点击 **START** 按钮
3. 看到欢迎消息，点击「注册账号」
4. 输入邮箱完成注册
5. 使用 `/send` 命令发送测试短信

---

## 📱 用户使用示例

### 场景1：新用户注册

```
用户: /start

Bot: 👋 欢迎使用 SMS Gateway Bot！
     
     通过我，您可以：
     📤 发送国际短信到200+个国家
     💰 实时查询账户余额
     📊 查看发送记录和统计
     
     首次使用？点击注册 👇
     [📝 注册账号] [❓ 帮助]

用户: 点击[注册账号]

Bot: 🎉 欢迎注册！请输入您的邮箱地址：

用户: user@example.com

Bot: ✅ 注册成功！
     
     📧 邮箱: user@example.com
     💰 余额: 10.00 CNY
     🎁 赠送: 10条免费短信
     🔑 API密钥: ak_xxxx...
     
     使用 /send 开始发送短信 📱
```

### 场景2：发送短信

```
用户: /send

Bot: 📱 请输入接收方手机号：
     格式示例: +8613800138000

用户: +8613800138000

Bot: ✅ 手机号: +8613800138000
     🌍 国家: 中国
     
     📝 请输入短信内容：

用户: 您的验证码是 123456

Bot: 📋 发送预览
     ━━━━━━━━━━━━━━━━
     📱 接收方: +8613800138000
     🌍 国家: 中国
     📝 内容: 您的验证码是 123456
     📊 条数: 1条
     💰 费用: 0.05 CNY
     ━━━━━━━━━━━━━━━━
     
     [✅ 确认发送] [❌ 取消]

用户: 点击[确认发送]

Bot: ✅ 发送成功！
     
     📨 消息ID: MSG1735577200ABC
     💰 费用: 0.05 CNY
     📊 状态: 已发送
     
     我们会在送达后通知您 🔔

（5秒后自动推送）

Bot: ✅ 短信已送达
     
     📨 消息ID: MSG1735577200ABC
     ⏰ 送达时间: 2025-12-30 15:30:05
```

### 场景3：批量发送

```
用户: /batch

Bot: 📤 批量发送短信
     
     请上传CSV文件，格式如下：
     phone_number,message
     +8613800138000,Hello
     +8613900139000,World
     
     💡 提示：
     • 文件大小不超过5MB
     • 单次最多1000条
     
     📎 点击下方按钮上传文件
     [📎 上传文件] [❌ 取消]

用户: 上传 sms_list.csv

Bot: ⏳ 正在解析文件...
     
     ✅ 解析成功！
     
     📊 总数: 250条
     💰 预计费用: 12.50 CNY
     🌍 国家分布:
        • 中国: 200条
        • 美国: 30条
        • 英国: 20条
     
     确认发送吗？
     [✅ 确认发送] [❌ 取消]

用户: 点击[确认发送]

Bot: ✅ 批量任务已创建！
     
     📦 批次ID: BATCH_20251230_001
     📊 总数: 250条
     
     发送中... 0/250
     
     可以使用其他命令，我会定期更新进度

（每30秒更新一次）

Bot: 📊 发送进度更新
     
     批次: BATCH_20251230_001
     进度: 50/250 (20%)
     成功: 49条
     失败: 1条

（完成后）

Bot: 🎉 批量发送完成！
     
     批次: BATCH_20251230_001
     ✅ 成功: 248条
     ❌ 失败: 2条
     💰 总费用: 12.40 CNY
     
     查看详情: /records BATCH_20251230_001
```

### 场景4：查询余额

```
用户: /balance

Bot: 💰 账户余额
     ━━━━━━━━━━━━━━━━
     余额: 95.50 CNY
     
     📊 今日统计:
     • 已发送: 45条
     • 成功率: 98.9%
     • 今日消费: 2.25 CNY
     
     💳 充值: /recharge
```

### 场景5：查询记录

```
用户: /records

Bot: 📊 最近发送记录（前10条）
     ━━━━━━━━━━━━━━━━
     
     1. ✅ +86138*** | 15:30 | ¥0.05
     2. ✅ +86139*** | 15:25 | ¥0.05
     3. ✅ +1202*** | 15:20 | ¥0.08
     4. ❌ +9112*** | 15:15 | ¥0.00
     5. ✅ +44207*** | 15:10 | ¥0.10
     
     📄 查看更多: 登录Web后台
     🔍 查询单条: /status 消息ID
```

---

## 🔧 高级配置

### 启用Webhook模式（生产环境推荐）

1. **准备域名和SSL证书**
   ```
   域名: bot.yourdomain.com
   SSL: Let's Encrypt免费证书
   ```

2. **配置Nginx**
   ```nginx
   server {
       listen 443 ssl;
       server_name bot.yourdomain.com;
       
       ssl_certificate /etc/ssl/cert.pem;
       ssl_certificate_key /etc/ssl/key.pem;
       
       location /telegram/webhook {
           proxy_pass http://telegram_bot:8080;
           proxy_set_header Host $host;
           
           # 只允许Telegram服务器IP
           allow 149.154.160.0/20;
           allow 91.108.4.0/22;
           deny all;
       }
   }
   ```

3. **修改Bot配置**
   ```bash
   USE_WEBHOOK=true
   WEBHOOK_URL=https://bot.yourdomain.com
   WEBHOOK_PATH=/telegram/webhook
   WEBHOOK_PORT=8080
   ```

4. **设置Webhook**
   ```bash
   curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
     -d "url=https://bot.yourdomain.com/telegram/webhook"
   ```

5. **验证Webhook**
   ```bash
   curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
   ```

### 自定义欢迎消息

编辑 `bot/handlers/start.py`:

```python
WELCOME_MESSAGE = """
👋 欢迎来到 {bot_name}！

🌟 我们的优势：
• 全球200+国家覆盖
• 秒级送达
• 价格低至 ¥0.03/条
• 7×24小时服务

🎁 新用户福利：
注册即送10条免费短信！

开始使用 → /register
"""
```

### 添加管理员命令

```python
# bot/handlers/admin.py
@admin_only
async def handle_stats(update, context):
    """管理员查看系统统计"""
    stats = await get_system_stats()
    await update.message.reply_text(
        f"📊 系统统计\n"
        f"总用户: {stats['total_users']}\n"
        f"今日新增: {stats['new_users_today']}\n"
        f"今日发送: {stats['sms_sent_today']}\n"
        f"在线用户: {stats['active_users']}"
    )
```

---

## 🛡️ 安全最佳实践

### 1. Token安全
```bash
# ❌ 不要将Token提交到Git
echo "TELEGRAM_BOT_TOKEN=*" >> .gitignore

# ✅ 使用环境变量或密钥管理服务
export TELEGRAM_BOT_TOKEN=$(aws secretsmanager get-secret-value ...)
```

### 2. 限流保护
```python
# 防止用户滥用
RATE_LIMITS = {
    "register": "1/hour",      # 每小时只能注册1次
    "send": "100/day",         # 每天最多100条
    "batch": "10/day",         # 每天最多10次批量
}
```

### 3. IP白名单（Webhook模式）
```nginx
# 只允许Telegram服务器IP
allow 149.154.160.0/20;
allow 91.108.4.0/22;
deny all;
```

### 4. 验证回调来源
```python
# 验证Webhook请求签名
def verify_telegram_signature(token, request):
    secret_key = hashlib.sha256(token.encode()).digest()
    # 验证逻辑...
```

---

## 🐛 常见问题

### Q1: Bot无响应怎么办？

**检查清单**:
```bash
# 1. 检查Bot进程
ps aux | grep "bot.main"

# 2. 查看日志
tail -f logs/bot.log

# 3. 测试Token
curl "https://api.telegram.org/bot<TOKEN>/getMe"

# 4. 检查网络
ping api.telegram.org
```

### Q2: Webhook无法接收消息？

```bash
# 1. 检查Webhook状态
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"

# 2. 查看错误信息
# 返回中的 last_error_message 字段

# 3. 测试Webhook URL可访问性
curl https://bot.yourdomain.com/telegram/webhook

# 4. 检查SSL证书
openssl s_client -connect bot.yourdomain.com:443
```

### Q3: 如何处理消息延迟？

**优化方案**:
```python
# 1. 使用异步处理
async def handle_message(update, context):
    # 异步处理逻辑
    await process_async()

# 2. 后台任务
context.application.create_task(long_running_task())

# 3. 队列处理
await redis.lpush("task_queue", message)
```

### Q4: 批量发送如何避免被限流？

```python
# Telegram API限制: 30条消息/秒
import asyncio

async def send_batch_with_rate_limit(messages):
    for i, msg in enumerate(messages):
        await bot.send_message(msg)
        
        # 每30条休息1秒
        if (i + 1) % 30 == 0:
            await asyncio.sleep(1)
```

---

## 📈 监控和运维

### 查看Bot状态

```bash
# 实时日志
tail -f logs/bot.log | grep ERROR

# 统计今日发送量
grep "send_sms" logs/bot.log | grep $(date +%Y-%m-%d) | wc -l

# 查看错误率
grep "ERROR" logs/bot.log | tail -100
```

### 性能监控

```python
# Prometheus指标
from prometheus_client import Counter, Histogram

telegram_commands = Counter('telegram_commands_total', 'Total commands', ['command'])
telegram_response_time = Histogram('telegram_response_seconds', 'Response time')

@telegram_response_time.time()
async def handle_send(update, context):
    telegram_commands.labels(command='send').inc()
    # 处理逻辑...
```

### 自动重启

```bash
# supervisor配置
[program:telegram_bot]
command=/usr/bin/python -m bot.main
directory=/app/telegram_bot
autostart=true
autorestart=true
stderr_logfile=/var/log/telegram_bot.err.log
stdout_logfile=/var/log/telegram_bot.out.log
```

---

## 🚀 部署到生产环境

### Docker部署

```bash
# 1. 构建镜像
docker build -t sms-telegram-bot:latest ./telegram_bot

# 2. 运行容器
docker run -d \
  --name telegram_bot \
  --env-file .env \
  --restart always \
  sms-telegram-bot:latest

# 3. 查看日志
docker logs -f telegram_bot
```

### Docker Compose

```yaml
version: '3.8'
services:
  telegram_bot:
    build: ./telegram_bot
    environment:
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - API_BASE_URL=http://api:8000
      - REDIS_URL=redis://redis:6379/1
    depends_on:
      - api
      - redis
    restart: always
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### Kubernetes部署

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: telegram-bot
spec:
  replicas: 2
  template:
    spec:
      containers:
      - name: bot
        image: sms-telegram-bot:latest
        env:
        - name: TELEGRAM_BOT_TOKEN
          valueFrom:
            secretKeyRef:
              name: telegram-secret
              key: bot-token
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
```

---

## 📚 更多资源

- **完整文档**: [TELEGRAM_INTEGRATION.md](./TELEGRAM_INTEGRATION.md)
- **python-telegram-bot文档**: https://docs.python-telegram-bot.org/
- **Telegram Bot API**: https://core.telegram.org/bots/api
- **最佳实践**: https://core.telegram.org/bots/best-practices

---

## ✨ 下一步

1. ✅ 完成基础配置
2. ✅ 测试所有命令
3. 🔄 启用Webhook（生产环境）
4. 🔄 添加监控和告警
5. 🔄 优化用户体验

**祝您使用愉快！** 🎉

有问题？加入我们的Telegram群组：@sms_gateway_support

