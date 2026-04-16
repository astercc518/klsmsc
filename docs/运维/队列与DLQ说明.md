# Celery 队列与死信队列（DLQ）说明

## 1. 当前队列划分（与代码同步）

除 [`服务与队列矩阵.md`](./服务与队列矩阵.md) 所列外，以下队列用于**隔离负载**：

| 队列 | 任务 | 消费方 |
|------|------|--------|
| webhook_tasks | `send_webhook` | worker（与 celery 等并列 `-Q`） |
| integrations | `okcc_sync_balances_task` | worker |

批量 `process_batch` / `process_batch_chunk`、虚拟 DLR 等仍使用 **`celery`** 队列，避免一次迁移面过大。

## 2. 为何尚未在 Broker 层强制 DLQ

RabbitMQ **死信交换（DLX）** 需在队列声明时带上 `x-dead-letter-exchange` 等参数。Celery/Kombu 多数队列由 Worker **启动时自动声明**，要在全队列统一 DLQ 需满足其一：

- 在 `celery_app` 中为每个 `task_queues` 配置 `queue_arguments`（需与现有 Broker 声明兼容，变更队列属性可能需删队重建）；或  
- 使用 **rabbitmqadmin / definitions.json** 在运维侧预定义队列与策略。

上述属于**有停机或迁移窗口**的变更，故本仓库先完成**逻辑队列拆分**；Broker 级 DLQ 建议在低峰期单独评审后上线。

## 3. 建议的后续步骤（运维）

1. 在 RabbitMQ 管理台观察 **`webhook_tasks`**、**`integrations`** 深度，分别对 Webhook 与 OKCC 设告警阈值。  
2. 对 poison message（无限重试）场景，在应用层已依赖 `max_retries`；Broker DLQ 作为**二次兜底**再引入。  
3. 若使用 Shovel/Federation 做多机房，队列名变更需同步到 Shovel 配置。

---

文档随 `backend/app/workers/celery_app.py` 与 `docker-compose.yml` 中 worker 的 `-Q` 列表维护。
