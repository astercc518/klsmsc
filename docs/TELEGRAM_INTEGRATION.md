# 国际短信系统 - Telegram Bot 集成方案

## 文档信息
- **文档类型**: Telegram Integration Design
- **功能**: 账号自动创建 + 短信发送任务提交
- **文档版本**: v1.0
- **创建日期**: 2025-12-30

---

## 目录
1. [功能概述](#1-功能概述)
2. [用户流程](#2-用户流程)
3. [技术架构](#3-技术架构)
4. [功能设计](#4-功能设计)
5. [实现方案](#5-实现方案)
6. [安全设计](#6-安全设计)
7. [部署方案](#7-部署方案)

---

## 1. 功能概述

### 1.1 核心价值

通过Telegram Bot提供：
- ✅ **零门槛注册**: 无需访问网站，在Telegram中即可完成账号创建
- ✅ **便捷发送**: 直接在聊天窗口发送短信，无需登录Web后台
- ✅ **实时通知**: 短信状态变化实时推送到Telegram
- ✅ **余额查询**: 随时查看账户余额和消费情况
- ✅ **移动优先**: 随时随地通过手机管理短信

### 1.2 目标用户

- 个人开发者（快速测试）
- 小微企业（简单场景）
- 移动办公用户
- 非技术人员

### 1.3 功能范围

**✅ 支持的功能**:
- 账号自动注册
- 发送单条短信
- 发送批量短信（文件上传）
- 查询发送记录
- 查询账户余额
- 充值申请
- 状态通知（Webhook推送）

**❌ 不支持的功能**:
- 复杂的通道管理
- 计费规则配置
- 报表统计（推荐使用Web后台）

---

## 2. 用户流程

### 2.1 首次使用流程

```
用户在Telegram搜索Bot
    ↓
点击 /start
    ↓
Bot欢迎消息 + 介绍功能
    ↓
用户点击「注册账号」按钮
    ↓
Bot请求输入邮箱
    ↓
用户输入邮箱
    ↓
系统自动创建账号
    ↓
生成API密钥
    ↓
Bot返回账号信息和使用指南
    ↓
赠送测试余额（如10条免费短信）
    ↓
用户可以开始发送短信
```

### 2.2 发送短信流程

```
用户输入命令：/send
    ↓
Bot提示输入手机号
    ↓
用户输入：+8613800138000
    ↓
Bot提示输入短信内容
    ↓
用户输入：Your code is 123456
    ↓
Bot显示预览和费用预估
    ↓
用户点击「确认发送」按钮
    ↓
Bot调用后端API发送
    ↓
返回消息ID和状态
    ↓
（异步）送达后推送通知
```

### 2.3 批量发送流程

```
用户输入命令：/batch
    ↓
Bot提示上传CSV文件
    ↓
用户上传文件（格式：phone,message）
    ↓
Bot解析文件并预览
    ↓
显示：共X条，预计费用Y元
    ↓
用户点击「确认发送」
    ↓
Bot创建批次任务
    ↓
返回批次ID
    ↓
定期推送进度（已发X/共Y）
```

---

## 3. 技术架构

### 3.1 整体架构图

```
┌─────────────────────────────────────────────────────┐
│              Telegram 客户端                         │
│        (用户通过手机/电脑与Bot交互)                   │
└────────────────────┬────────────────────────────────┘
                     │ Webhook / Long Polling
                     ↓
┌─────────────────────────────────────────────────────┐
│           Telegram Bot Service                      │
│  ┌──────────────────────────────────────────────┐  │
│  │  python-telegram-bot / aiogram               │  │
│  │  • 消息处理                                   │  │
│  │  • 命令路由                                   │  │
│  │  • 会话管理                                   │  │
│  │  • 文件处理                                   │  │
│  └────────────┬─────────────────────────────────┘  │
└───────────────┼─────────────────────────────────────┘
                │
                ↓
┌─────────────────────────────────────────────────────┐
│          SMS Gateway Backend API                    │
│  ┌──────────────────────────────────────────────┐  │
│  │  /api/v1/telegram/register   (注册账号)      │  │
│  │  /api/v1/telegram/send       (发送短信)      │  │
│  │  /api/v1/telegram/batch      (批量发送)      │  │
│  │  /api/v1/telegram/balance    (查询余额)      │  │
│  │  /api/v1/telegram/records    (查询记录)      │  │
│  └──────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
                │
                ↓
┌─────────────────────────────────────────────────────┐
│              数据库 (MySQL + Redis)                  │
│  • telegram_users (Telegram用户映射)               │
│  • accounts (账户表)                                │
│  • sms_logs (短信记录)                              │
└─────────────────────────────────────────────────────┘
```

### 3.2 技术选型

| 组件 | 技术选择 | 说明 |
|------|---------|------|
| Bot框架 | python-telegram-bot 20+ | 官方推荐，功能完善 |
| 异步处理 | asyncio | 高性能异步处理 |
| 会话管理 | Redis | 存储用户会话状态 |
| 文件存储 | 本地/OSS | 临时存储上传的CSV文件 |
| 部署方式 | Docker容器 | 独立部署Bot服务 |
| Webhook | Nginx反向代理 | 接收Telegram推送 |

---

## 4. 功能设计

### 4.1 命令列表

| 命令 | 功能 | 示例 |
|------|------|------|
| `/start` | 启动Bot，显示欢迎信息 | `/start` |
| `/register` | 注册新账号 | `/register` |
| `/send` | 发送单条短信 | `/send` |
| `/batch` | 批量发送短信 | `/batch` |
| `/balance` | 查询账户余额 | `/balance` |
| `/records` | 查询发送记录 | `/records` |
| `/status` | 查询短信状态 | `/status MSG123...` |
| `/recharge` | 充值申请 | `/recharge` |
| `/settings` | 账户设置 | `/settings` |
| `/help` | 帮助信息 | `/help` |
| `/cancel` | 取消当前操作 | `/cancel` |

### 4.2 按钮交互设计

**主菜单**:
```
┌────────────────────────────────────┐
│  📱 SMS Gateway Bot                │
├────────────────────────────────────┤
│  [📤 发送短信]  [📊 查询记录]      │
│  [💰 账户余额]  [⚙️ 设置]          │
│  [❓ 帮助]      [🔄 刷新]          │
└────────────────────────────────────┘
```

**发送短信确认**:
```
┌────────────────────────────────────┐
│  📋 发送预览                        │
├────────────────────────────────────┤
│  收件人: +8613800138000            │
│  内容: Your code is 123456         │
│  条数: 1条                         │
│  费用: ¥0.05                       │
├────────────────────────────────────┤
│  [✅ 确认发送]  [❌ 取消]          │
└────────────────────────────────────┘
```

### 4.3 会话状态管理

```python
# 会话状态枚举
class BotState:
    IDLE = "idle"                    # 空闲
    WAITING_EMAIL = "waiting_email"  # 等待输入邮箱
    WAITING_PHONE = "waiting_phone"  # 等待输入手机号
    WAITING_MESSAGE = "waiting_msg"  # 等待输入短信内容
    WAITING_FILE = "waiting_file"    # 等待上传文件
    CONFIRMING = "confirming"        # 等待确认

# Redis存储格式
telegram_session:{telegram_id} → {
    "state": "waiting_phone",
    "data": {
        "account_id": 1001,
        "temp_phone": "+8613800138000"
    },
    "expire": 300  # 5分钟过期
}
```

---

## 5. 实现方案

### 5.1 Bot服务实现

**项目结构**:
```
telegram_bot/
├── bot/
│   ├── __init__.py
│   ├── main.py              # Bot启动入口
│   ├── config.py            # 配置
│   ├── handlers/            # 命令处理器
│   │   ├── __init__.py
│   │   ├── start.py         # /start命令
│   │   ├── register.py      # /register命令
│   │   ├── send.py          # /send命令
│   │   ├── batch.py         # /batch命令
│   │   ├── balance.py       # /balance命令
│   │   └── records.py       # /records命令
│   ├── keyboards/           # 按钮键盘
│   │   ├── main_menu.py
│   │   └── confirm.py
│   ├── services/            # 业务服务
│   │   ├── account_service.py
│   │   ├── sms_service.py
│   │   └── file_service.py
│   ├── utils/               # 工具函数
│   │   ├── session.py       # 会话管理
│   │   ├── validator.py     # 验证器
│   │   └── formatter.py     # 格式化
│   └── middlewares/         # 中间件
│       ├── auth.py          # 认证中间件
│       └── logger.py        # 日志中间件
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

### 5.2 核心代码实现

#### 5.2.1 Bot主入口

```python
# bot/main.py
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from bot.config import settings
from bot.handlers import (
    start,
    register,
    send,
    batch,
    balance,
    records,
)
from bot.middlewares.auth import auth_middleware
from bot.middlewares.logger import logger_middleware

# 配置日志
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def main():
    """启动Bot"""
    # 创建Application
    application = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()
    
    # 注册命令处理器
    application.add_handler(CommandHandler("start", start.handle_start))
    application.add_handler(CommandHandler("register", register.handle_register))
    application.add_handler(CommandHandler("send", send.handle_send))
    application.add_handler(CommandHandler("batch", batch.handle_batch))
    application.add_handler(CommandHandler("balance", balance.handle_balance))
    application.add_handler(CommandHandler("records", records.handle_records))
    application.add_handler(CommandHandler("help", start.handle_help))
    application.add_handler(CommandHandler("cancel", start.handle_cancel))
    
    # 注册回调查询处理器（按钮点击）
    application.add_handler(CallbackQueryHandler(handle_callback))
    
    # 注册消息处理器（文本、文件）
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    # 添加中间件
    application.add_handler(auth_middleware)
    application.add_handler(logger_middleware)
    
    # 启动Bot
    if settings.USE_WEBHOOK:
        # Webhook模式（生产环境推荐）
        application.run_webhook(
            listen="0.0.0.0",
            port=settings.WEBHOOK_PORT,
            url_path=settings.WEBHOOK_PATH,
            webhook_url=f"{settings.WEBHOOK_URL}{settings.WEBHOOK_PATH}"
        )
    else:
        # 轮询模式（开发环境）
        application.run_polling()


async def handle_callback(update: Update, context):
    """处理按钮回调"""
    query = update.callback_query
    await query.answer()
    
    # 根据callback_data路由到不同处理器
    data = query.data
    
    if data.startswith("confirm_send:"):
        await send.handle_confirm_send(update, context)
    elif data.startswith("cancel_send"):
        await send.handle_cancel_send(update, context)
    elif data.startswith("main_menu"):
        await start.handle_main_menu(update, context)
    # ... 其他回调处理


async def handle_message(update: Update, context):
    """处理文本消息"""
    from bot.utils.session import get_user_state
    
    user_id = update.effective_user.id
    state = await get_user_state(user_id)
    
    # 根据用户当前状态路由到相应处理器
    if state == "waiting_email":
        await register.handle_email_input(update, context)
    elif state == "waiting_phone":
        await send.handle_phone_input(update, context)
    elif state == "waiting_message":
        await send.handle_message_input(update, context)
    else:
        await update.message.reply_text(
            "请使用命令或按钮操作。输入 /help 查看帮助。"
        )


async def handle_document(update: Update, context):
    """处理文件上传"""
    from bot.utils.session import get_user_state
    
    user_id = update.effective_user.id
    state = await get_user_state(user_id)
    
    if state == "waiting_file":
        await batch.handle_file_upload(update, context)
    else:
        await update.message.reply_text("请先使用 /batch 命令开始批量发送。")


if __name__ == '__main__':
    main()
```

#### 5.2.2 注册命令处理

```python
# bot/handlers/register.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.services.account_service import AccountService
from bot.utils.session import set_user_state, get_user_data, set_user_data
from bot.utils.validator import validate_email
import logging

logger = logging.getLogger(__name__)


async def handle_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理注册命令"""
    user = update.effective_user
    telegram_id = user.id
    
    # 检查用户是否已注册
    account_service = AccountService()
    existing_account = await account_service.get_account_by_telegram_id(telegram_id)
    
    if existing_account:
        await update.message.reply_text(
            f"✅ 您已经注册过了！\n\n"
            f"📧 邮箱: {existing_account['email']}\n"
            f"💰 余额: {existing_account['balance']} {existing_account['currency']}\n"
            f"🔑 API密钥: `{existing_account['api_key']}`\n\n"
            f"使用 /send 发送短信",
            parse_mode='Markdown'
        )
        return
    
    # 开始注册流程
    await set_user_state(telegram_id, "waiting_email")
    
    await update.message.reply_text(
        "🎉 欢迎注册 SMS Gateway！\n\n"
        "请输入您的邮箱地址：\n"
        "（用于接收重要通知）\n\n"
        "输入 /cancel 取消注册"
    )


async def handle_email_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理邮箱输入"""
    user = update.effective_user
    telegram_id = user.id
    email = update.message.text.strip()
    
    # 验证邮箱格式
    if not validate_email(email):
        await update.message.reply_text(
            "❌ 邮箱格式不正确，请重新输入：\n\n"
            "输入 /cancel 取消注册"
        )
        return
    
    # 创建账号
    account_service = AccountService()
    try:
        result = await account_service.create_account_from_telegram(
            telegram_id=telegram_id,
            telegram_username=user.username,
            telegram_first_name=user.first_name,
            telegram_last_name=user.last_name,
            email=email
        )
        
        if result['success']:
            # 清除会话状态
            await set_user_state(telegram_id, "idle")
            
            # 发送成功消息
            await update.message.reply_text(
                f"🎉 注册成功！\n\n"
                f"📧 邮箱: {email}\n"
                f"💰 余额: {result['balance']} {result['currency']}\n"
                f"🎁 赠送: {result['free_credits']} 条免费短信\n"
                f"🔑 API密钥: `{result['api_key']}`\n\n"
                f"⚠️ 请妥善保管API密钥！\n\n"
                f"使用 /send 开始发送短信 📱",
                parse_mode='Markdown'
            )
            
            # 显示主菜单
            keyboard = [
                [
                    InlineKeyboardButton("📤 发送短信", callback_data="send"),
                    InlineKeyboardButton("💰 查余额", callback_data="balance")
                ],
                [
                    InlineKeyboardButton("📊 发送记录", callback_data="records"),
                    InlineKeyboardButton("❓ 帮助", callback_data="help")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("请选择操作：", reply_markup=reply_markup)
            
        else:
            await update.message.reply_text(
                f"❌ 注册失败: {result.get('error', '未知错误')}\n\n"
                f"请稍后重试或联系客服"
            )
    
    except Exception as e:
        logger.error(f"Registration error: {e}")
        await update.message.reply_text(
            "❌ 注册时发生错误，请稍后重试"
        )
```

#### 5.2.3 发送命令处理

```python
# bot/handlers/send.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.services.sms_service import SMSService
from bot.utils.session import set_user_state, get_user_data, set_user_data
from bot.utils.validator import validate_phone_number
import logging

logger = logging.getLogger(__name__)


async def handle_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理发送命令"""
    telegram_id = update.effective_user.id
    
    # 检查用户是否已注册
    sms_service = SMSService()
    account = await sms_service.get_account_by_telegram_id(telegram_id)
    
    if not account:
        await update.message.reply_text(
            "❌ 您还没有注册账号。\n\n"
            "请先使用 /register 注册"
        )
        return
    
    # 检查余额
    if account['balance'] <= 0:
        await update.message.reply_text(
            "❌ 账户余额不足。\n\n"
            f"当前余额: {account['balance']} {account['currency']}\n\n"
            "请使用 /recharge 充值"
        )
        return
    
    # 设置状态为等待输入手机号
    await set_user_state(telegram_id, "waiting_phone")
    await set_user_data(telegram_id, {"account_id": account['id']})
    
    await update.message.reply_text(
        "📱 请输入接收方手机号：\n\n"
        "格式: +8613800138000\n"
        "（必须包含国际区号）\n\n"
        "输入 /cancel 取消发送"
    )


async def handle_phone_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理手机号输入"""
    telegram_id = update.effective_user.id
    phone_number = update.message.text.strip()
    
    # 验证手机号格式
    validation = validate_phone_number(phone_number)
    if not validation['valid']:
        await update.message.reply_text(
            f"❌ 手机号格式不正确\n\n"
            f"错误: {validation['error']}\n\n"
            f"请重新输入（格式：+8613800138000）"
        )
        return
    
    # 保存手机号，等待输入短信内容
    await set_user_data(telegram_id, {
        "phone_number": validation['e164_format'],
        "country_code": validation['country_code'],
        "country_name": validation['country_name']
    })
    await set_user_state(telegram_id, "waiting_message")
    
    await update.message.reply_text(
        f"✅ 手机号: {validation['e164_format']}\n"
        f"🌍 国家: {validation['country_name']}\n\n"
        f"📝 请输入短信内容："
    )


async def handle_message_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理短信内容输入"""
    telegram_id = update.effective_user.id
    message_content = update.message.text.strip()
    
    # 验证内容长度
    if len(message_content) == 0:
        await update.message.reply_text("❌ 短信内容不能为空，请重新输入：")
        return
    
    if len(message_content) > 1000:
        await update.message.reply_text(
            "❌ 短信内容过长（超过1000字符）\n\n"
            "请缩短内容后重新输入："
        )
        return
    
    # 获取之前保存的数据
    user_data = await get_user_data(telegram_id)
    phone_number = user_data.get('phone_number')
    country_name = user_data.get('country_name')
    
    # 计算费用
    sms_service = SMSService()
    pricing = await sms_service.calculate_price(
        account_id=user_data['account_id'],
        phone_number=phone_number,
        message=message_content
    )
    
    if not pricing['success']:
        await update.message.reply_text(
            f"❌ 计算费用失败: {pricing.get('error')}\n\n"
            "请重试或联系客服"
        )
        return
    
    # 保存短信内容
    await set_user_data(telegram_id, {"message_content": message_content})
    await set_user_state(telegram_id, "confirming")
    
    # 显示预览和确认按钮
    message_parts = pricing['message_count']
    total_cost = pricing['total_cost']
    currency = pricing['currency']
    
    preview_text = (
        "📋 发送预览\n"
        "━━━━━━━━━━━━━━━━\n"
        f"📱 接收方: {phone_number}\n"
        f"🌍 国家: {country_name}\n"
        f"📝 内容: {message_content[:50]}{'...' if len(message_content) > 50 else ''}\n"
        f"📊 条数: {message_parts} 条\n"
        f"💰 费用: {total_cost} {currency}\n"
        "━━━━━━━━━━━━━━━━\n"
        "确认发送吗？"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("✅ 确认发送", callback_data="confirm_send"),
            InlineKeyboardButton("❌ 取消", callback_data="cancel_send")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(preview_text, reply_markup=reply_markup)


async def handle_confirm_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理确认发送"""
    query = update.callback_query
    telegram_id = update.effective_user.id
    
    # 获取用户数据
    user_data = await get_user_data(telegram_id)
    
    # 调用后端API发送短信
    sms_service = SMSService()
    try:
        result = await sms_service.send_sms(
            account_id=user_data['account_id'],
            phone_number=user_data['phone_number'],
            message=user_data['message_content']
        )
        
        if result['success']:
            # 清除会话状态
            await set_user_state(telegram_id, "idle")
            
            await query.edit_message_text(
                f"✅ 发送成功！\n\n"
                f"📨 消息ID: `{result['message_id']}`\n"
                f"📱 接收方: {user_data['phone_number']}\n"
                f"💰 费用: {result['pricing']['total_cost']} {result['pricing']['currency']}\n"
                f"📊 状态: {result['status']}\n\n"
                f"我们会在短信送达后通知您。\n\n"
                f"使用 /status {result['message_id']} 查询状态",
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(
                f"❌ 发送失败\n\n"
                f"错误: {result.get('error', '未知错误')}\n\n"
                f"请重试或联系客服"
            )
    
    except Exception as e:
        logger.error(f"Send SMS error: {e}")
        await query.edit_message_text(
            "❌ 发送时发生错误，请稍后重试"
        )


async def handle_cancel_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理取消发送"""
    query = update.callback_query
    telegram_id = update.effective_user.id
    
    await set_user_state(telegram_id, "idle")
    await query.edit_message_text(
        "❌ 已取消发送\n\n"
        "使用 /send 重新发送"
    )
```

#### 5.2.4 账户服务

```python
# bot/services/account_service.py
import httpx
from bot.config import settings
import logging

logger = logging.getLogger(__name__)


class AccountService:
    """账户服务"""
    
    def __init__(self):
        self.base_url = settings.API_BASE_URL
        self.api_key = settings.INTERNAL_API_KEY
    
    async def get_account_by_telegram_id(self, telegram_id: int):
        """通过Telegram ID获取账户"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.base_url}/api/v1/telegram/account/{telegram_id}",
                    headers={"X-Internal-Key": self.api_key}
                )
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    return None
                else:
                    logger.error(f"API error: {response.status_code}")
                    return None
            except Exception as e:
                logger.error(f"Request error: {e}")
                return None
    
    async def create_account_from_telegram(
        self,
        telegram_id: int,
        telegram_username: str,
        telegram_first_name: str,
        telegram_last_name: str,
        email: str
    ):
        """通过Telegram创建账户"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/api/v1/telegram/register",
                    headers={"X-Internal-Key": self.api_key},
                    json={
                        "telegram_id": telegram_id,
                        "telegram_username": telegram_username,
                        "telegram_first_name": telegram_first_name,
                        "telegram_last_name": telegram_last_name,
                        "email": email
                    }
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    return {
                        "success": False,
                        "error": response.json().get("detail", "注册失败")
                    }
            
            except Exception as e:
                logger.error(f"Registration error: {e}")
                return {
                    "success": False,
                    "error": str(e)
                }
```

### 5.3 后端API扩展

需要在后端添加Telegram专用的API接口：

```python
# backend/app/api/v1/telegram.py
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, EmailStr
from app.services.telegram_service import TelegramService
from app.config import settings

router = APIRouter()


class TelegramRegisterRequest(BaseModel):
    telegram_id: int
    telegram_username: str | None
    telegram_first_name: str
    telegram_last_name: str | None
    email: EmailStr


class TelegramSendSMSRequest(BaseModel):
    telegram_id: int
    phone_number: str
    message: str


async def verify_internal_key(x_internal_key: str = Header(...)):
    """验证内部API密钥"""
    if x_internal_key != settings.INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid internal key")
    return True


@router.post("/register")
async def register_from_telegram(
    request: TelegramRegisterRequest,
    _: bool = Depends(verify_internal_key)
):
    """
    Telegram用户注册
    
    自动创建账号并返回API密钥
    """
    service = TelegramService()
    result = await service.register_user(
        telegram_id=request.telegram_id,
        telegram_username=request.telegram_username,
        telegram_first_name=request.telegram_first_name,
        telegram_last_name=request.telegram_last_name,
        email=request.email
    )
    return result


@router.get("/account/{telegram_id}")
async def get_account_by_telegram(
    telegram_id: int,
    _: bool = Depends(verify_internal_key)
):
    """获取Telegram用户的账户信息"""
    service = TelegramService()
    account = await service.get_account(telegram_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.post("/send")
async def send_sms_from_telegram(
    request: TelegramSendSMSRequest,
    _: bool = Depends(verify_internal_key)
):
    """通过Telegram发送短信"""
    service = TelegramService()
    result = await service.send_sms(
        telegram_id=request.telegram_id,
        phone_number=request.phone_number,
        message=request.message
    )
    return result


@router.get("/balance/{telegram_id}")
async def get_balance(
    telegram_id: int,
    _: bool = Depends(verify_internal_key)
):
    """查询账户余额"""
    service = TelegramService()
    balance = await service.get_balance(telegram_id)
    if balance is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return balance
```

### 5.4 数据库扩展

需要添加Telegram用户映射表：

```sql
-- telegram_users表
CREATE TABLE `telegram_users` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `telegram_id` BIGINT NOT NULL COMMENT 'Telegram用户ID',
  `telegram_username` VARCHAR(100) COMMENT 'Telegram用户名',
  `telegram_first_name` VARCHAR(100) COMMENT '名字',
  `telegram_last_name` VARCHAR(100) COMMENT '姓氏',
  `account_id` INT UNSIGNED NOT NULL COMMENT '关联账户ID',
  `is_active` BOOLEAN NOT NULL DEFAULT TRUE COMMENT '是否激活',
  `notification_enabled` BOOLEAN NOT NULL DEFAULT TRUE COMMENT '是否启用通知',
  `language` VARCHAR(10) DEFAULT 'zh' COMMENT '语言偏好',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_telegram_id` (`telegram_id`),
  KEY `idx_account_id` (`account_id`),
  FOREIGN KEY (`account_id`) REFERENCES `accounts`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Telegram用户映射表';
```

---

## 6. 安全设计

### 6.1 认证机制

**Bot Token保护**:
- Bot Token存储在环境变量中
- 使用Webhook时验证来源IP
- 定期轮换Bot Token

**内部API保护**:
- Bot服务与后端API之间使用内部密钥
- 不暴露用户API密钥给Telegram
- 所有请求走HTTPS

### 6.2 防滥用机制

```python
# 限流策略
RATE_LIMITS = {
    "register": "1/hour",      # 1小时只能注册1次
    "send": "100/day",         # 每天最多发送100条
    "batch": "10/day",         # 每天最多批量发送10次
    "balance": "100/hour",     # 每小时最多查询100次
}

# Redis存储
telegram_ratelimit:{telegram_id}:{action}:{hour} → count
```

### 6.3 数据安全

- 短信内容不永久存储在Bot服务器
- 敏感信息（API密钥）用反引号包裹（防止转发时可见）
- 会话数据5分钟自动过期
- 上传的CSV文件处理后立即删除

---

## 7. 部署方案

### 7.1 Docker部署

```yaml
# docker-compose.yml（添加telegram_bot服务）
services:
  telegram_bot:
    build: ./telegram_bot
    environment:
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - API_BASE_URL=http://api:8000
      - INTERNAL_API_KEY=${INTERNAL_API_KEY}
      - REDIS_URL=redis://redis:6379/1
      - USE_WEBHOOK=true
      - WEBHOOK_URL=https://yourdomain.com
      - WEBHOOK_PATH=/telegram/webhook
    depends_on:
      - redis
      - api
    restart: always
    networks:
      - sms-network

networks:
  sms-network:
    driver: bridge
```

```dockerfile
# telegram_bot/Dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-m", "bot.main"]
```

### 7.2 Nginx配置（Webhook）

```nginx
# Webhook接收端点
location /telegram/webhook {
    proxy_pass http://telegram_bot:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    
    # 只允许Telegram服务器IP
    allow 149.154.160.0/20;
    allow 91.108.4.0/22;
    deny all;
}
```

### 7.3 创建Bot步骤

1. **与BotFather对话**:
```
/newbot
Bot名称: SMS Gateway Bot
Bot用户名: sms_gateway_bot
```

2. **获取Token**:
```
Bot Token: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz
```

3. **设置命令菜单**:
```
/setcommands

send - 发送短信
batch - 批量发送
balance - 查询余额
records - 发送记录
help - 帮助信息
```

4. **设置Webhook**:
```bash
curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \
  -d "url=https://yourdomain.com/telegram/webhook"
```

---

## 8. 用户体验优化

### 8.1 多语言支持

```python
# bot/i18n.py
MESSAGES = {
    "zh": {
        "welcome": "欢迎使用 SMS Gateway Bot！",
        "register_success": "注册成功！",
        # ...
    },
    "en": {
        "welcome": "Welcome to SMS Gateway Bot!",
        "register_success": "Registration successful!",
        # ...
    }
}
```

### 8.2 快捷回复

用户可以直接发送格式化文本快速发送：

```
格式: 手机号|短信内容

示例:
+8613800138000|Your code is 123456
```

### 8.3 状态通知

当短信送达时，自动推送通知：

```
✅ 短信已送达

📨 消息ID: MSG123...
📱 接收方: +8613800138000
⏰ 送达时间: 2025-12-30 15:30:05
```

---

## 9. 监控和运维

### 9.1 关键指标

- Bot在线状态
- 消息处理延迟
- API调用成功率
- 用户活跃度
- 注册转化率

### 9.2 日志收集

```python
# 结构化日志
logger.info("telegram_event", extra={
    "telegram_id": user_id,
    "command": "send",
    "status": "success",
    "duration_ms": 150
})
```

---

## 10. 路线图

### Phase 1（MVP）- 2周
- [x] 基础命令（start, register, send）
- [x] 单条发送
- [x] 余额查询

### Phase 2 - 2周
- [ ] 批量发送
- [ ] 发送记录查询
- [ ] 状态通知

### Phase 3 - 2周
- [ ] 充值申请
- [ ] 多语言支持
- [ ] 快捷发送

### Phase 4 - 后续
- [ ] 定时发送
- [ ] 模板管理
- [ ] 群组支持

---

## 附录

### A. 示例对话流程

```
用户: /start
Bot: 👋 欢迎使用 SMS Gateway Bot！
    
    通过我，您可以：
    📤 发送国际短信
    💰 查询账户余额
    📊 查看发送记录
    
    首次使用？点击下方注册 👇
    [注册账号] [帮助]

用户: 点击[注册账号]
Bot: 🎉 欢迎注册！请输入您的邮箱：

用户: user@example.com
Bot: ✅ 注册成功！
    
    📧 邮箱: user@example.com
    💰 余额: 10.00 CNY
    🎁 赠送: 10条免费短信
    🔑 API密钥: `ak_1234...`
    
    使用 /send 开始发送短信 📱
    [发送短信] [查余额] [帮助]

用户: /send
Bot: 📱 请输入接收方手机号：
    格式: +8613800138000

用户: +8613800138000
Bot: ✅ 手机号: +8613800138000
    🌍 国家: 中国
    
    📝 请输入短信内容：

用户: Your verification code is 123456
Bot: 📋 发送预览
    ━━━━━━━━━━━━━━━━
    📱 接收方: +8613800138000
    🌍 国家: 中国
    📝 内容: Your verification code is 123456
    📊 条数: 1条
    💰 费用: 0.05 CNY
    ━━━━━━━━━━━━━━━━
    确认发送吗？
    [✅ 确认发送] [❌ 取消]

用户: 点击[确认发送]
Bot: ✅ 发送成功！
    
    📨 消息ID: `MSG1735577200ABC`
    📱 接收方: +8613800138000
    💰 费用: 0.05 CNY
    📊 状态: sent
    
    我们会在短信送达后通知您。

（5秒后）
Bot: ✅ 短信已送达
    
    📨 消息ID: MSG1735577200ABC
    📱 接收方: +8613800138000
    ⏰ 送达时间: 2025-12-30 15:30:05
```

### B. FAQ

**Q: Bot会保存我的短信内容吗？**
A: 不会。短信内容仅在发送时临时存储（5分钟），发送后立即删除。

**Q: 如何充值？**
A: 使用 /recharge 命令提交充值申请，客服会联系您完成充值。

**Q: 支持哪些国家？**
A: 支持200+个国家和地区，覆盖全球主要市场。

**Q: 发送失败会扣费吗？**
A: 不会。只有成功送达才会扣费。

---

**文档结束**

