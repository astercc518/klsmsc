# 安全设计备忘（看了再改）

本文档记录系统**故意做或不做**的安全选择，避免好心改坏事。

## 鉴权与会话

### CSRF 中间件 - **故意不加**

**现状**：FastAPI 后端**没有**配置 CSRFMiddleware。

**原因**：所有客户端鉴权走 `Authorization: Bearer <jwt>` 或 `X-API-Key: <ak_xxx>` 头部。
浏览器**不会自动**附加这些头到第三方网站发起的跨域请求 → 没有经典 CSRF 攻击面。

**约束（强制）**：

> 🚫 **绝不引入基于 cookie 的鉴权**（包括 `Set-Cookie: session=...`、`SameSite=Lax`、OAuth 浏览器跳转 cookie 等）。
> 浏览器会自动在跨站请求上携带 cookie，没有 CSRF 防护就会被攻击。

如果将来必须引入 cookie 会话（比如某些 SSO 集成），**必须先加 CSRFMiddleware**（如 [`fastapi-csrf-protect`](https://pypi.org/project/fastapi-csrf-protect/)），并对所有非幂等 cookie-based 端点强制 `X-CSRF-Token` 校验。

### JWT Token

- Access token: **30 分钟**（`JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30`）
- Refresh token: **24 小时**（`JWT_REFRESH_TOKEN_EXPIRE_HOURS=24`）轮换式（每次刷新发新的，旧的失效）
- 模拟登录 (`/admin/users/{id}/impersonate`) 固定 2h 不发 refresh

### 多源鉴权（API）

`/api/v1/sms/*` 等客户端点接受多种凭证（按优先级）：
1. `X-API-Key` header
2. URL `?api_key=`
3. HTTP Basic Auth
4. JWT Bearer（管理员模拟）

**改动这里要小心**：不能让 admin token 误被路由到客户路径走 API key 校验。

## 网络

### 端口绑定

除业务必需的 80/443/2775，其余端口（MySQL/Redis/RabbitMQ/ProxySQL/API）一律绑 `127.0.0.1`。
外部访问通过 SSH 隧道。

### docker-proxy 权限

[docker-compose.yml#docker-proxy](../docker-compose.yml) 显式声明 `EXEC=0 IMAGES=0 VOLUMES=0 NETWORKS=0`。
`POST=1 + CONTAINERS=1` 是 tecnativa 现有最小组合（无更细的"仅 restart"开关）。

**已知局限**：`EXEC=0` 仅阻断 `/exec/*` 端点，**不阻断** `POST /containers/{id}/exec`
（被归到 CONTAINERS 类别）。如果 API/Bot 容器被 RCE，攻击者仍可以经 docker-proxy 在
其他业务容器内 spawn 进程。已实施的对冲：
1. 所有 backend 容器 uid=1000，spawn 出来的进程也是 1000
2. docker-proxy `read_only:true` + 仅 socket `:ro` 挂载
3. 业务容器自身无 root 提权路径

**未来收紧**：若要彻底封 exec 路径，需自写 allowlist 反代（仅放行
GET /containers/json + GET /containers/{name}/stats + POST /containers/{name}/restart）。
当前评级：可接受。

### TG Bot 内部接口

`/api/v1/internal/bot/*` 接受两种凭证（任一）：

1. `X-Internal-Token`（向后兼容旧路径）
2. `X-Bot-Sig` + `X-Bot-Ts` HMAC-SHA256 + 时间窗 ±60s（推荐）

设 `BOT_REQUIRE_HMAC=true` 强制只接受 HMAC 路径。

## 凭证

### 强密码强制

`.env` 的密码字段长度规则：
- MySQL/Redis/RabbitMQ: ≥ 24 字符随机
- ProxySQL admin/radmin: ≥ 24 字符
- JWT_SECRET_KEY: ≥ 32 字符
- TELEGRAM_STAFF_API_SECRET / INTERNAL_TOKEN: ≥ 32 字符

测试用弱密码（`rootpass123` / `admin/admin` 等）**已下线**。

### .env 文件权限

```
-rw-r----- root:1000 .env
```

非 root 容器 (uid=1000) 通过 group 读取；宿主机其他用户无权读。

### Bot Pickle 加密

`bot_data.pickle` 用 Fernet (AES-128 + HMAC) 加密，key 在 `.env` 的 `BOT_PERSISTENCE_KEY`。
旧明文文件启动时一次性自动迁移到密文。

## 容器

### 非 root 运行

所有 backend 容器（api / 5 worker / beat / bot）以 **uid=1000** 运行。

### 已知例外

- mysql / redis / rabbitmq / proxysql / smpp-gateway / frontend / docker-proxy / landing-preview 由其官方镜像决定 user，未审。

## 审计

### log_operation 覆盖

所有 mutation 端点应调 `log_operation(...)` 写入 `admin_operation_log`：
- ✅ `admin.py` 全覆盖
- ✅ `system_config.py` 通过 `ConfigService` 自动写
- ✅ `tickets.py` / `knowledge.py` / `suppliers.py` / `channel_relations.py`（用 `audited()` dependency）

### 已知缺陷

- `log_operation` 失败时仅 logger.error 不抛异常 → DB 抖动期间审计行可能丢
- 部分 system_config 写入未传 Request → 审计 IP 字段 NULL

## 加固清单（剩余）

- 🟡 X-Forwarded-For IP 信任收紧（middleware/ip_whitelist.py:92）
- 🟡 Login 加账户级失败锁定（同账号 N 次失败锁定 15 分钟）
- 🟡 SMPP 客户密码 16 字符 → 32（同时存 AES）
- 🟡 备份加密（`/root/smsc_backup_*.tar.gz`）
- 🟡 容器镜像漏洞扫描接 CI
