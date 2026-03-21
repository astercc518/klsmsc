# TG 验证登录开启指南

TG 验证登录允许员工通过 Telegram 接收验证码，在网页登录时无需输入密码，提升安全性与便捷性。

---

## 一、前置条件

### 1. 系统配置

| 配置项 | 说明 | 配置位置 |
|--------|------|----------|
| **TELEGRAM_BOT_TOKEN** | Telegram Bot Token | `.env` 或 系统设置 → 系统配置 |
| **Bot 服务** | 业务助手 Bot 需正常运行 | `docker compose up -d bot` |

### 2. 配置 Bot Token

**方式一：环境变量**

在项目根目录 `.env` 中配置：

```bash
TELEGRAM_BOT_TOKEN=你的Bot_Token
```

**方式二：系统配置**

1. 登录管理后台
2. 进入 **系统设置** → **系统配置**
3. 配置 `telegram_bot_token` 为你的 Bot Token

> 获取 Bot Token：在 Telegram 中与 [@BotFather](https://t.me/BotFather) 对话，创建 Bot 或使用 `/newbot` 获取 Token。

---

## 二、绑定 Telegram

### 客户账户

客户在 **业务助手 Bot** 中通过「绑定已有账户」完成绑定：
1. 网页端【账户设置】→ 生成绑定码
2. Bot 中「绑定已有账户」→ 输入 6 位绑定码

### 员工账户

员工需在 **业务助手 Bot** 中完成「员工绑定」：

1. 打开 Telegram，搜索业务助手 Bot（如 `@kaolachbot`）
2. 发送 `/start` → 选择 **「👔 员工绑定」**
3. 发送格式：`用户名 密码`（如 `KL01 mypassword`）
4. 绑定成功后，在员工管理页面可看到「已绑定」状态

---

## 三、使用 TG 验证登录

1. 打开登录页：`https://你的域名/login`

2. 选择 **「TG验证」** 标签

3. 输入 **账户标识**：
   - **客户账户**：账户名（如 `TG_6650783812_a928`）或邮箱
   - **员工账户**：员工用户名（如 `KL01`）

4. 点击 **「发送验证码到 Telegram」**

5. 在 Telegram 中查看收到的 6 位验证码

6. 在网页输入验证码，点击 **「验证并登录」**

> 系统会先尝试客户账户，若未找到则尝试员工账户。

---

## 四、常见问题

### 1. 提示「该账户未绑定 Telegram」

- **原因**：员工尚未在 Bot 中完成绑定
- **处理**：按上述「员工绑定 Telegram」步骤完成绑定

### 2. 验证码发送失败

- **原因**：Bot Token 未配置或无效，或 Bot 服务未启动
- **处理**：检查 `.env` 中 `TELEGRAM_BOT_TOKEN`，确认 Bot 服务正常：`docker compose ps bot`

### 3. 员工已删除/禁用

- **原因**：已删除或禁用的员工无法使用 TG 验证登录
- **处理**：在员工管理中恢复该员工

### 4. 验证错误次数过多

- **原因**：15 分钟内连续 5 次验证码错误
- **处理**：等待 15 分钟后重试

---

## 五、流程概览

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  1. 配置 Bot    │     │  2. 员工在 Bot   │     │  3. 网页登录    │
│  Token 并启动   │ ──► │  中完成绑定      │ ──► │  选择 TG 验证   │
│  Bot 服务      │     │  (用户名 密码)   │     │  输入验证码     │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

---

## 六、相关代码

| 功能 | 文件 |
|------|------|
| 发送验证码 | `backend/app/api/v1/admin.py` - `telegram_login_send_code` |
| 验证并登录 | `backend/app/api/v1/admin.py` - `telegram_login_verify` |
| 员工绑定 | `telegram_bot/bot/handlers/menu.py` - `staff_credentials` |
| 通知发送 | `backend/app/services/notification_service.py` |
