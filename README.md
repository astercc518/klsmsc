# 考拉出海 Gateway（SMS / 语音 / 数据）

国际短信与多业务网关平台：提供客户门户、管理后台、HTTP API、SMPP 上游对接、Telegram 业务助手、语音（OKCC 等）与数据业务扩展能力。

## 功能概览

- **短信**：单发/批量、任务与记录、发送统计、审批、充值与通道、路由与计价、DLR 与 Webhook
- **客户接入**：HTTP API（`X-API-Key` / `Authorization: Bearer`）、HTTP Basic Auth（账户名 + 6 位接口密码 `api_secret`）、SMPP 客户协议配置
- **管理端**：客户与通道、员工与销售、定价、报表、知识库与运维相关能力
- **异步任务**：Celery + RabbitMQ + Redis（发送、DLR、批量、语音同步等）
- **可观测性**：Prometheus + Grafana（可选）

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 API | Python 3、FastAPI、SQLAlchemy 2（异步）、Pydantic v2 |
| 数据库 | MySQL 8 |
| 缓存 / 队列 | Redis、RabbitMQ、Celery |
| 前端 | Vue 3、Vite、TypeScript、Element Plus、ECharts、vue-i18n |
| 部署 | Docker Compose、Nginx（前端镜像） |

## 目录结构（简要）

```
├── backend/                 # FastAPI 应用与 Celery Worker
│   ├── app/                 # 业务代码（api、core、modules、workers）
│   └── scripts/             # 工具脚本（如 md2pdf、截图、知识库发布）
├── frontend/                # Vue 3 管理端与客户端
├── telegram_bot/            # Telegram 业务机器人
├── docs/                    # 文档与操作指南
│   ├── SMS_API_接口文档.md  # 客户 HTTP / SMPP 对接说明
│   └── guides/              # 客户/员工/管理员指南（Markdown + 截图）
├── scripts/                 # 数据库初始化等
├── docker-compose.yml
├── .env                     # 本地/生产环境变量（勿提交密钥）
└── .env.example             # 环境变量示例与注释
```

## 快速开始（Docker Compose）

### 1. 准备环境变量

```bash
cp .env.example .env
# 编辑 .env：至少配置 MYSQL_*、JWT_SECRET_KEY、CORS_ORIGINS、TELEGRAM_* 等
```

### 2. 启动全部服务

```bash
docker compose up -d
```

### 3. 常用端口

| 服务 | 默认端口 |
|------|----------|
| 前端（Nginx） | 80 / 443 |
| API（直连调试） | 8000 |
| MySQL | 3306 |
| Redis | 6379 |
| RabbitMQ AMQP | 5672 |
| RabbitMQ 管理台 | 15672 |
| Prometheus | 9090 |
| Grafana | 3000 |

健康检查示例：

```bash
curl -s http://127.0.0.1:8000/health
```

### 4. 首次数据库

`docker-compose` 中 MySQL 会挂载 `scripts/init_db.sql` 做初始化；后续表结构变更请按团队约定使用 Alembic 或既定迁移流程。

## 环境变量说明

完整示例与注释见根目录 **`.env.example`**。常见项包括：

- **应用**：`APP_ENV`、`APP_DEBUG`、`JWT_SECRET_KEY`、`CORS_ORIGINS`
- **数据库**：`MYSQL_*`（与 compose 中一致）
- **对外站点**：`PUBLIC_WEB_BASE_URL`（账号摘要、模拟登录等拼接 URL）
- **Telegram**：`TELEGRAM_BOT_TOKEN`、`TELEGRAM_STAFF_API_SECRET` 等
- **DLR 回调**：`DLR_CALLBACK_TOKEN`、`DLR_CALLBACK_OPEN`、`DLR_CALLBACK_IP_WHITELIST`
- **SMPP 行为**：`SMPP_SUBMIT_RESP_WAIT_SECONDS`、`SMPP_DLR_SOCKET_HOLD_SECONDS`（见 compose 与 `.env.example`）
- **对外 SMPP 展示**（管理端账号摘要）：`SMPP_SERVER_HOST`、`SMPP_SERVER_PORT`（在 `backend/app/config.py` 中可配置）

**切勿**将含真实密钥的 `.env` 提交到 Git。

## 本地开发（可选）

### 后端

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# 配置数据库与 Redis 等环境变量后
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

生产构建：`npm run build`，静态资源由 Nginx 镜像提供（见 `frontend/Dockerfile`）。

## 客户对接文档

- **HTTP / SMPP 接口说明**：[docs/SMS_API_接口文档.md](docs/SMS_API_接口文档.md)
- **操作指南维护与发布**：[docs/guides/README.md](docs/guides/README.md)（含 Markdown 转 PDF、Playwright 截图脚本说明）

## 管理端「账号摘要」

在 **客户管理** 操作栏「更多」中可打开 **账号摘要**，按协议展示：

- HTTP：API Key、Basic Auth（用户名 + 接口密码）、接口地址与限速/白名单
- SMPP：服务器地址、端口、System ID、密码等

接口密码为账户的 **`api_secret`**（创建客户或重置 API Key 时生成，当前策略为 **6 位随机字符**）。

## 许可证与贡献

内部/商业项目请遵循团队规范。若需对外开源，请补充 LICENSE 与贡献指南。

---

如有部署或对接问题，优先查阅 `docs/` 下接口文档与指南；生产环境请务必轮换密钥并限制数据库与队列端口暴露范围。
