# 自建语音系统（产品与运维约定）

本文档固化计划中的 **产品假设** 与 **基础设施对接**，便于研发、运维与合规对齐。

## 产品假设（费率与合规）

- **预付费**：语音余额不足时拒绝 originate（由业务层校验）；CDR 后扣费与短信一致时可配置「后付费」模式（需单独审批）。
- **AI 外呼**：首期以 IVR（播报 + DTMF）为主；全双工 ASR/LLM 需单独资源与合规评估。
- **挂机短信**：营销类须用户同意；与短信模块共用频控与黑名单。
- **DNC**：外呼前校验 `voice_dnc_numbers`；与短信黑名单可后续映射。
- **时区**：外呼任务默认 `Asia/Shanghai`，任务级可覆盖。

## 自建栈（Kamailio + FreeSWITCH + Trunk）

- 部署不在本仓库；需独立维护 Kamailio/OpenSIPS、FreeSWITCH、SIP Trunk。
- **CDR Webhook**：向 `POST /api/v1/voice/webhooks/cdr` 推送 JSON，请求头 `X-Voice-Signature: hex(hmac_sha256(body, secret))`（secret 为环境变量 `VOICE_CDR_WEBHOOK_SECRET`）。

### CDR JSON 建议字段

| 字段 | 说明 |
|------|------|
| `call_id` | 全局唯一，幂等键 |
| `account_id` | 业务账户 ID（smsc `accounts.id`） |
| `voice_account_id` | 可选，`voice_accounts.id` |
| `caller` / `callee` | 主叫/被叫号码 |
| `direction` | `inbound` / `outbound` |
| `start_time` / `answer_time` / `end_time` | ISO8601 |
| `billsec` | 计费秒数 |
| `hangup_cause` | 挂断原因 |
| `campaign_id` | 可选，外呼任务 ID |
| `recording_url` | 可选 |
| `sip_extension` | 可选，分机 |
| `voice_route_id` | 可选，与 `voice_routes.id` 一致时按该路由单价批价；否则按 `country_code` 匹配路由 |
| `country_code` | 可选，缺省时用语音子账户 `VoiceAccount.country_code` |

## 外呼网关（可选）

- `VOICE_GATEWAY_BASE_URL`：若配置，Worker 将向 `{BASE}/originate` 发起 HTTP 调用（需 `VOICE_ORIGINATE_TOKEN`）。
- **请求体建议字段**：`account_id`、`callee`（E.164）、`campaign_id`、`caller_id`（外显）、`trunk_ref`、`voice_route_id`（来自主叫号码池绑定，可与 CDR 批价一致）、`ai_mode`。网关需将 `campaign_id` 写入呼叫变量，以便 CDR 回传 smsc。

## 主叫号码池（管理端 / 客户只读）

- 管理端可增删改主叫号码，并可选 **绑定 `voice_route_id`**（`voice_caller_ids.voice_route_id`），与计费路由、FS 出局 profile 对齐。
- 客户 API：`GET /api/v1/voice/caller-ids`（API Key）仅返回本账户号码池，不包含敏感运维字段。

## FreeSWITCH / 网关变量约定（与 CDR 对齐）

- 外呼 `originate` 时设置通道变量，例如：`account_id`、`campaign_id`、`voice_account_id`（若有），以便 `mod_xml_cdr` 或自定义脚本 POST 到 Webhook 时带回。
- 管理端 **语音路由** 表字段 `trunk_profile` / `dial_prefix` 与 Kamailio/FS 出局网关配置名对齐，便于运维双写与排查；CDR 可带 `voice_route_id` 锁定批价路由。
- Worker 发往 HTTP 网关的 JSON 含：`caller_id`、`trunk_ref`（来自主叫号码池 `trunk_ref`）、`ai_mode`（任务级 `ivr`/`ai`），网关应写入通道变量并回传 CDR。
- 手拨出局时：在 dialplan 中设置 `effective_caller_id_number` 与 `account_id`（或从 `sip_from_user` 映射到 `voice_accounts`）。

## Kamailio / OpenSIPS（边缘）

- 负责 REGISTER、NAT、ACL；媒体仍到 FreeSWITCH。
- 生产环境建议 TLS/SIPS，并与防火墙联动限制来源 IP。

## 客户控制台（Web）

- 前端路由（需账户开通语音业务 `customerServices` 含 `voice`）：`/voice/call`（SIP 与策略）、`/voice/records`（话单分页）、`/voice/caller-ids`（外显号码只读）。
- 对应 API（`X-API-Key` / 客户登录态）：`GET /api/v1/voice/me`、`GET /api/v1/voice/calls`（`start_date`/`end_date`，`YYYY-MM-DD`；`date_basis=created_at|start_time`；可选 `status`、`direction=inbound|outbound`、`outbound_campaign_id`（须为本账户外呼任务，否则 400））、`GET /api/v1/voice/calls/export`（同上筛选，最多 10000 条）、`GET /api/v1/voice/caller-ids`。
- **话单列表与导出 CSV** 均包含：`direction`（`inbound`/`outbound`）、`outbound_campaign_id`、`outbound_campaign_name`（本账户任务名称，任务已删或越权则无）、`voice_route_id`（批价所用路由，可与管理端路由表对账）、`hangup_cause`、`created_at`（入库时间）、`recording_url` 等；便于客户对账与区分任务外呼。
- 管理端话单 `GET /api/v1/admin/voice/calls` 与导出 `GET /api/v1/admin/voice/calls/export`：含 **`outbound_campaign_id` / `outbound_campaign_name`**（按任务 ID 解析名称）、账户、状态、日期范围，以及 **`date_basis`**（默认 `created_at`；`start_time` 时排除无开始时间的记录）。

## 管理端：SIP 密码重置

- `POST /api/v1/admin/voice/accounts/{voice_account_id}/reset-sip-password`（管理员鉴权）：生成新密码写入 `voice_accounts.okcc_password`，**响应中一次性返回** `sip_username` / `sip_password`；操作写入审计日志（不含明文密码）。
- **网关同步**：若 Kamailio/FreeSWITCH 等使用独立用户库，须在运维流程中把新密码同步到边缘/媒体层，否则软电话仍用旧密码无法注册。

## 运维探活

- `GET /health/voice`：检查 MySQL 与 Redis 是否可用（与 FS 无关，仅业务层就绪）。
- `GET /api/v1/admin/voice/ops-metrics`（管理员鉴权）：近 **24 小时** 运营快照，供自建告警或 Grafana HTTP 数据源对接；管理端 **语音运营指标** 页（`/admin/voice/ops`）为只读展示。字段包括：
  - `cdr_webhook_processed` / `cdr_webhook_failed`：CDR Webhook 处理成功/失败条数；
  - `campaigns_running`：状态为 `running` 的外呼任务数；
  - `voice_calls_total_24h` / `voice_calls_connected_24h`：话单入库总数与状态为 `answered` 或 `completed` 的条数；
  - `voice_answer_rate_24h`：上两者之比（无入库时为 `null`）；
  - `outbound_contacts_pending`：全库待拨打名单条数（`voice_outbound_contacts.status=pending`，用于观察积压）。

## smsc 环境变量补充

| 变量 | 说明 |
|------|------|
| `VOICE_CDR_MAX_RETRIES` | CDR 处理失败后 Celery 定时重放 `raw_payload` 的最大次数 |
| `VOICE_HANGUP_SMS_MAX_PER_CALLEE_PER_DAY` | 挂机短信：同一被叫每日上限（Redis 计数） |
| `VOICE_MIN_BALANCE_FOR_ORIGINATE` | 外呼 Worker 跳过拨打的余额下限（0=不校验） |
| `VOICE_CDR_WEBHOOK_IP_RATE_PER_MINUTE` | CDR Webhook 按源 IP 每分钟最大请求数（0=不单独限制） |

## 账户配额（smsc）

- `VoiceAccount.max_concurrent_calls`：账户下「正在拨号」名单数（`dialing`）上限；与任务级 `max_concurrent` 同时生效。
- `VoiceAccount.daily_outbound_limit`：当日已成功发起外呼尝试次数（`dialing`/`completed`/`failed`）上限，UTC 日切分。

## AI 外呼（任务级）

- 表字段 `voice_outbound_campaigns.ai_mode`：`ivr`（默认，语音菜单/播报）或 `ai`（需网关注入 RTP→ASR/LLM 流水线，不在本仓库实现媒体侧）。

## 上线发布检查

1. **数据库**：在部署环境执行 `alembic upgrade head`（含 `005`～`008` 等语音相关迁移），确认无报错。
2. **环境变量**：项目根目录 `.env` 可参考 `.env.example` 中语音段落；`docker-compose` 已将 `VOICE_*` 注入 **api**、**worker**（须消费 **`voice_tasks`** 队列）等。
3. **Celery**：Worker 必须订阅 **`voice_tasks`**；Beat 下发 `voice_campaign_scan_task`（每 30 秒）与 `voice_cdr_retry_failed_task`（每 2 分钟）。
4. **进程**：示例：`docker compose build --no-cache frontend && docker compose up -d --force-recreate api worker beat frontend`。
5. **验证**：`GET /health/voice` 中 `database`/`redis` 为 true；CDR Webhook 为 `POST /api/v1/voice/webhooks/cdr`。
6. **网关侧**：自建 Kamailio/FreeSWITCH 按本文档对接 CDR Webhook 与（可选）HTTP originate；与运维确认 Trunk、`trunk_profile` 双写。
