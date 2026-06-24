# 考拉出海 SMSC —— 运行态架构文档

> 本文档描述 **当前实际运行** 的系统拓扑(以 `docker-compose.yml` 为权威来源),
> 区别于 `docs/ARCHITECTURE.md`(早期设计稿)。
> 最后更新:2026-06-25。

---

## 1. 系统概述

考拉出海(Kaolach)国际短信网关。多租户 SMS 网关,含 Telegram 业务机器人、管理后台、客户门户,
对接上游 SMPP 供应商。所有 UI 文案双语(zh-CN 主、en 兜底)。

**技术栈**:FastAPI(Python)+ Vue3/Vite + MySQL8 + Redis + RabbitMQ + Celery + Go(SMPP 网关)。

**核心设计哲学**:**按任务类型把 Celery worker 拆成独立容器 + 独立队列,做故障域隔离** ——
任一类任务出问题(回执洪峰、webhook 雪崩、注水卡死),爆炸半径被限制在自己的容器内,不连累发送主链路。

---

## 2. 服务清单(18 个容器)

### 2.1 基础设施层

| 容器 | 镜像/角色 | 端口 | 作用 |
|---|---|---|---|
| `smsc-mysql` | MySQL 8 | (内网) | 主数据库。utf8mb4,时区 +08:00,buffer pool 默认 4G。**不被应用直连** |
| `smsc-proxysql` | ProxySQL | (内网 6033) | 连接池中间件。**API/worker 都连它,不直连 MySQL**,统一管理连接数 |
| `smsc-redis` | Redis 7 | (内网 6379) | 缓存 / 分布式锁 / DLR 重试缓冲 / 令牌桶 / 熔断状态。**本部署启用密码**(`--requirepass`) |
| `smsc-rabbitmq` | RabbitMQ | (内网 5672) | Celery 消息 broker。API 投递任务 → workers 消费的总线 |

### 2.2 应用层

| 容器 | 命令 | 端口 | 作用 |
|---|---|---|---|
| `smsc-api` | `uvicorn app.main:app --workers 4` | 8000(内网) | **核心业务大脑**:REST API、鉴权、计费、通道路由,向 RabbitMQ 投递异步任务 |
| `smsc-frontend` | Nginx + Vue SPA | **80 / 443** | 托管管理后台 + 客户门户,反代到 api |
| `smsc-bot` | `python -m bot.main` | — | Telegram 业务机器人(开户、查询、报价) |
| `smsc-landing-preview` | Nginx 静态 | — | 短链/落地页预览服务 |

### 2.3 Celery Workers(按队列物理隔离)

| 容器 | 队列 `-Q` | 并发(默认) | 作用 |
|---|---|---|---|
| `smsc-worker-sms` | `sms_send` | 32 | **单条短信发送**(热路径,最高并发);含虚拟通道模拟回执 |
| `smsc-worker-dlr` | `sms_dlr` | 8 | **回执(DLR)处理**:匹配 upstream_id、更新 sms_logs、入站回送 |
| `smsc-worker-result` | `sms_result_queue` | 12 | Go 网关 SubmitSM 结果异步回写 sms_logs(批量合并 UPDATE) |
| `smsc-worker-webhook` | `webhook_tasks` | 16 | **客户回调推送 + 短链点击记录**(2026-06 新增,外部 I/O 隔离) |
| `smsc-worker` | `celery,data_tasks,integrations` | 8 | 通用:批量发送分片、撞库、数据任务、OKCC 集成 |
| `smsc-worker-web` | `web_automation` | 6(prefork) | 注水点击(浏览器自动化,重资源) |
| `smsc-worker-web-register` | `web_register` | 2(prefork) | 注水注册(独立队列,防被点击 ETA 洪流饿死) |
| `smsc-beat` | (调度器) | — | Celery Beat 定时器,只调度不执行 |

### 2.4 外部网关 / 运维

| 容器 | 角色 | 端口 | 作用 |
|---|---|---|---|
| `smsc-smpp-gateway` | Go 服务 | **2775**(SMPP) | 连上游 SMPP 供应商,收发 PDU + 回执;发布 DLR 到 RabbitMQ `sms_dlr`;DLR 归属过滤 |
| `smsc-docker-proxy` | tecnativa/docker-socket-proxy | (内网) | 受限 Docker API,让后台"重启服务"功能只能重启容器,不暴露完整 Docker 权限 |

---

## 3. 架构分层图

```
       客户/管理员 ─HTTP→ smsc-frontend(Nginx+Vue, 80/443)
       Telegram   ──────→ smsc-bot
                                │ 反代/调用
                                ▼
                        smsc-api (FastAPI :8000) ── 业务大脑
                    ┌───────────┼────────────┬──────────────┐
                  SQL│        缓存/锁│       投递任务│
                    ▼            ▼              ▼
              ProxySQL→MySQL   Redis        RabbitMQ(broker)
                                               │ 按队列分发
        ┌──────────────────────────────────────┴───────────────────────┐
        ▼          ▼          ▼            ▼          ▼          ▼        ▼
   worker-sms  worker    worker-dlr  worker-result worker-   worker-  worker-
   [sms_send] [celery,   [sms_dlr]   [sms_result] webhook    web      web-register
              data_tasks,                         [webhook_  [web_    [web_register]
              integrations]                        tasks]    auto]
        │                     ▲          ▲
        │ SMPP 发送            │ 回执      │ 结果回写
        ▼                     │          │
   smsc-smpp-gateway(Go, 2775)┘──────────┘
        │
        ▼  上游 SMPP 供应商
```

---

## 4. Celery 队列与 worker 隔离

任务通过 `celery_app.conf.task_routes` 路由到队列,worker 容器各自 `-Q` 只消费指定队列。

| 队列 | 消费容器 | 典型任务 |
|---|---|---|
| `sms_send` | worker-sms | `send_sms_task`、虚拟通道模拟 |
| `sms_dlr` | worker-dlr | `process_dlr_task`、`process_smpp_dlr_task`、`flush_dlr_retry_buffer_task` |
| `sms_result_queue` | worker-result | `process_sms_result_task` |
| `webhook_tasks` | worker-webhook | `send_webhook`、`record_link_click_task` |
| `celery` | worker | `process_batch`、`process_batch_chunk`、批次巡检 |
| `data_tasks` | worker | 撞库发送、库存刷新、私库导入、`dlr_water_followup_task` |
| `integrations` | worker | `okcc_sync_balances_task` |
| `web_automation` | worker-web | `web_click_task` |
| `web_register` | worker-web-register | `web_register_task` |
| `webhook.retry.{1m,5m,30m,2h,6h}` / `webhook.throttle` / `webhook.dlq` | (无消费者) | webhook DLX 延迟重试暂存 |

### Webhook 韧性架构(2026-06)

webhook 推送是唯一"去敲外部客户服务器、延迟不可控"的任务,做了多层防护:

```
DLR → gate(账户没配 webhook_url 不入队) → webhook_tasks → worker-webhook
  ├─ 令牌桶限流(per-account + 全局) ──超速→ webhook.throttle(10s)回投
  ├─ 熔断器(per-endpoint,失败≥20 open 300s) ──open→ 快速失败
  ├─ 在途信号量(单账户≤8) ──满→ 背压
  ├─ 三段硬超时 httpx(connect3/read5/write3)
  └─ 失败→ DLX 阶梯重试 webhook.retry.1m→5m→30m→2h→6h → 穷尽 webhook.dlq(7天可重放)
全程 fail-open:Redis 故障只降级,绝不阻断真实回执
```

---

## 5. 核心数据流

**① 发送短信**
```
前端/API → 计费&通道路由(api) → RabbitMQ[sms_send] → worker-sms
        → smpp-gateway(SMPP) → 上游供应商
```

**② 收回执(DLR)**
```
上游 → smpp-gateway → RabbitMQ[sms_dlr] → worker-dlr → 匹配并更新 sms_logs
     ├─(配了 webhook 的客户)→ RabbitMQ[webhook_tasks] → worker-webhook → POST 客户服务器
     └─(SMPP 绑定的代理商)→ 入站 DLR 回送
未匹配(DLR 先于 SubmitResp 到达)→ Redis 重试缓冲 → flush 任务接力
```

**③ 批量发送**
```
API 上传 CSV → RabbitMQ[celery] → worker(分片)
            → 每片 RabbitMQ[sms_send] → worker-sms → ...
进度由 beat 的 sync_processing_batch_progress_task 每 30s 汇总
```

**④ 注水(点击/注册)**
```
送达回执 → dlr_water_followup_task(data_tasks)
点击 → web_click_task(web_automation) → worker-web(浏览器)
注册 → web_register_task(web_register) → worker-web-register
```

---

## 6. 定时任务(Celery Beat)

| 任务 | 周期 | 作用 |
|---|---|---|
| `fetch_dlr_reports_task` | 30s | 拉取上游 DLR 报告 |
| `flush_dlr_retry_buffer_task` | 5s | 重试未匹配 DLR(防丢) |
| `sync_processing_batch_progress_task` | 30s | 汇总批次进度 |
| `dlr_timeout_check_task` | 10min | 检查 DLR 超时记录 |
| `inspect_batches_task` | 5min | 巡检卡死批次 |
| `data_refresh_all_product_stock` | 10min | 刷新商品库存 |
| `data_refresh_carriers_cache` | 10min | 预热运营商聚合缓存 |
| `data_expire_pending_orders` | 30min | 清理过期 pending 订单 |
| `data_recycle_expired_numbers` | 每日 03:00 | 回收过期私库号码 |
| `refresh_staff_commission_cache` | 25min | 刷新员工佣金缓存 |
| `refresh_business_report_cache` | 1h | 刷新经营报表缓存 |
| `smpp_pending_dlr_cleanup` | 每日 | 清理 SMPP 待发 DLR |

---

## 7. 关键技术约束(踩坑要点)

- **Celery worker 用 NullPool**:`_run_async` 每任务新建并关闭 event loop;DB 引擎必须 NullPool,不能复用 API 的 async 引擎。
- **Redis 单例不可跨 loop**:`get_redis_client()` 单例绑定首个 loop,worker 内须**每 loop 新建短命 client**(webhook_worker / record_link_click / dlr_buffer 均如此)。违反即 `Future attached to a different loop`。
- **改 worker 代码必 restart**:volume 挂载下容器内文件变新但 Celery 进程跑旧模块,不重启不生效。
- **schema 只走 Alembic**:无 `create_all`,entrypoint `alembic upgrade head`(40 次重试)。
- **前端构建用 docker build**:`docker compose restart frontend` 不切换新镜像,须 `docker compose build frontend && up -d frontend`。
- **定时 eta 时区**:`celery_app.send_task` 全局兜底把 naive eta 标成 Asia/Shanghai,防被当 UTC 延后 8h。

---

## 8. 故障域隔离(设计精髓)

每类任务独占容器+队列 = 一类任务故障的**爆炸半径**被限制:

| 历史事故 | 隔离如何救场 |
|---|---|
| webhook 队列被无配置账户的回执打爆 13 万 | 拆 `worker-webhook` 独立容器 + 源头 gate,不再连累批量/数据任务 |
| worker-dlr 因 DLR 重试缓冲 loop 冲突高频崩溃 | 它独立,发送(worker-sms)完全无感 |
| 注水点击 ETA 洪流占满 prefetch | 注册单列 `web_register` + 专用 worker,永不被饿死 |
| 大批量 send 占满 worker | `sms_send` 独立 worker-sms,DLR/结算不受影响 |

---

## 9. 运维速查

```bash
# 看所有容器状态
docker compose ps

# 看某 worker 日志
docker compose logs worker-dlr -f --tail=100

# 改后端代码后(volume 挂载,须 restart 让 Celery 重载)
docker compose restart api worker worker-dlr worker-sms worker-webhook

# 改前端(必须 build 再 up,restart 不换镜像)
docker compose build frontend && docker compose up -d frontend

# requirements/Dockerfile 变更:重建镜像
docker compose build api && docker compose up -d api

# 队列深度
docker compose exec rabbitmq rabbitmqctl list_queues name messages consumers

# Alembic 迁移
docker compose exec api alembic upgrade head
docker compose exec api alembic revision --autogenerate -m "describe_change"
```
