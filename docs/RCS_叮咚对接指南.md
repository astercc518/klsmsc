# RCS 短信发送 —— 叮咚 (BoltTel) 对接说明

上游接口规范见仓库根目录 `BoltTel-RCS-OpenAPI对接指南.md`。本文说明本系统侧的落地方式与开通步骤。

## 1. 设计要点

RCS 走的就是 HTTP API，**不占 protocol 枚举**（否则每接一家 RCS 供应商都要动一次
DB 枚举）。通道配置为：

    protocol = 'HTTP'  +  config_json.rcs.vendor = 'bolttel' | ...

判别统一走 `Channel.is_rcs()` / `Channel.rcs_vendor()`，适配器在
`workers/adapters/rcs_adapter.py:_RCS_ADAPTERS` 按 vendor 分发（未知 vendor 直接报错，
不回落——静默回落会用错误的签名算法把号码发给另一家上游）。

这样完全复用现有的路由、计费、批量发送、批次进度、退款、报表、客户 webhook 链路，
不新增业务表。

| 环节 | 走向 |
|---|---|
| 提交 | `/api/v1/sms/send`、批量发送、TG 发送 —— 与短信同一入口 |
| 路由 | `RoutingEngine`（按国家/账户绑定），与短信一致 |
| 发送 | `sms_send` 队列 → `sms_worker._send_via_rcs`（HTTP 分支内按 `is_rcs()` 分流） → `workers/adapters/rcs_adapter.py` |
| 回执 | 叮咚平台 Webhook → `POST /api/v1/rcs/dlr/{channel_code}` → `core/dlr_handler.process_dlr_reports` |
| 对账 | 管理端 `/api/v1/admin/rcs/channels/{id}/report`、`/balance` |

**逐条提交**：每条消息一次 `send` 调用，`sendMode=broadcast` + 单个号码，
`clientRef` 用我们的 `message_id`。超时/5xx/限流重投时携带同一个 `clientRef`，
上游按幂等返回原批次（`duplicated=true`）且不重复扣费，因此不会双发。

## 2. 与普通短信的行为差异

| 项 | 说明 |
|---|---|
| **计费单位** | 按「条」，一个号码一条，与文案长度/编码无关（普通短信按 GSM-7/UCS-2 分段计费）。见 `PricingEngine.billable_units` |
| **文案限制** | ≤ **160 个 Unicode 字符**、**禁止 emoji**。上游是「整批拒绝」，所以在**提交入口就拦截**（单发 / 批量 / 批次分片预检三处），不会等发到上游才失败 |
| **号码格式** | 一律 E.164 带 `+`，不走通道的 `strip_leading_plus` 配置 |
| **国家** | `isoCode` 取 `sms_logs.country_code`（ISO2）。单批仅一个国家 —— 我们逐条提交，天然满足 |
| **回执** | 只走 Webhook 推送，不参与 `fetch_dlr_reports_task` 的 HTTP 拉取 |
| **READED** | 与 `DELIVERED` 同样映射为 `delivered`。同一条消息可能先后收到两者，第二次因终态保护被跳过 |
| **REPLY** | 不计费、不改投递状态，当前仅落日志（无入站消息表） |

## 3. 开通步骤

### 3.1 后台建通道

管理后台 → 通道管理 → 新增通道，协议选 **HTTP**，再把「接口类型」选成
**RCS - 叮咚 BoltTel**（该选择写入 `config_json.rcs.vendor`，是后端判别 RCS 通道的唯一依据）：

| 表单项 | 填什么 | 落库位置 |
|---|---|---|
| 接口地址 | `https://<生产域名>/service/api`（BASE，含 `/service/api`） | `channels.api_url` |
| appKey | 平台下发的 appKey | `channels.username` |
| appSecret | 平台下发的 appSecret | `channels.password` |
| 默认 SID | 平台开通的发件人 `sendCode` | `channels.default_sender_id` |
| 回执 secret | 平台「回执推送」里配的 secret | `channels.config_json → rcs.webhook_secret` |
| 下发总速度 | 合同约定的 QPS（超了上游返回 429，系统会退避重投） | `channels.max_tps` |

也可以在 `config_json.rcs` 里用 `base_url` / `app_key` / `app_secret` / `send_code` 显式覆盖上述回落。

> **密钥脱敏**：`appSecret` 与回执 `secret` 不会被列表/详情接口回吐明文，
> 前端看到的是 `******`。保存时原样提交掩码 = 保持原值；编辑时把 appSecret 留空同样表示不修改。

### 3.2 叮咚平台侧配置回执

在平台「API 接入 / 回执推送」填：

- `callbackUrl`：`https://<本系统域名>/api/v1/rcs/dlr/<通道编码>`（后台表单里可一键复制）
- `secret`：与后台「回执 secret」**填同一个值**
- `events`：`DELIVERED,READED,UNDELIVERABLE,REJECTED,EXPIRED,SEND_FAILED,REPLY`
- `enabled=1`

**未配置 secret 时系统会以 403 拒收回执** —— 无法验签就无法防止任何人伪造回执把未达改成已达。

同时需要让平台把本系统出口公网 IP 加入白名单，否则发送会收到 `AUTH_IP_FORBIDDEN`。

### 3.3 配国家路由 + 配价

与短信通道完全一样，两步都要做，缺一条发不出去：

1. 通道列表 →「国家」→ 添加目标国家。这写的是 `routing_rules`，**没有这条记录通道不会进入
   路由候选**（表现为「无可用通道」，与协议无关，新建 SMPP/HTTP 通道也一样）。
2. 通道 →「国家报价」配置 `country_pricing`（成本价），以及账户侧售价。

**上游未给你配某国家单价时会返回 `PRICE_MISSING` 整批拒绝**，需要联系叮咚商务开通。

保存通道价格时会自动联动开户模板底价与资源报价，**RCS 通道联动的是 `business_type='rcs'`
的模板/报价行**（不会串到短信的底价上）。

### 3.5 业务助手（TG）RCS 开户

RCS 是与短信/语音/数据并列的独立业务类型，销售在 TG 里的流程与短信开户一致：

```
主菜单 → 🎯 创建开户邀请 → 💬 RCS → 选国家 → 选模板 → 设单价 → 生成授权码
                                                        ↓
                              客户点开户链接 → 自动建号(business_type=rcs)
                                             + 按模板 channel_ids 绑定 RCS 通道
                                             + 写账户报价(business_type=rcs)
                                             + 赠送 1 USD 试用金
```

前提：管理后台先建好 **RCS 开户模板**（开户模板管理 → 业务类型选 RCS → 关联通道选 RCS 通道）。
模板底价由通道价格自动联动；销售报价受 **≥ 底价×1.1** 约束（bot 与后端 activate 双重校验，
绕过 bot 直接调接口也拦得住）。

开完的 RCS 客户在「我的客户 → 💬 RCS客户」下单独分类，业务工单也有独立的「💬 RCS工单」入口。

### 3.4 验证

1. 通道列表点「检测」：RCS 走真实 `/balance` 调用，同时验证 base_url 可达 + appKey/appSecret + 签名路径。
   显示 online 才说明鉴权真的通了（不是 TCP 通就算数）。
2. 通道「测试发送」发一条到真机。
3. 观察 `sms_logs`：受理后 `status=sent` 且 `upstream_message_id` 形如 `msg:{batchId}-0`；
   收到回执后变 `delivered`。

## 4. 排查

| 现象 | 多半是 |
|---|---|
| 通道存了但发送走了普通 HTTP 短信逻辑 | 「接口类型」没选，`config_json.rcs.vendor` 为空 —— 判别全靠它，不看 protocol |
| 日志 `RCS 上游 vendor=... 尚未实现` | vendor 值不在 `_RCS_ADAPTERS` 里（如节点 `node` 尚未接入） |
| `RCS 通道鉴权异常` + 日志 `AUTH_BAD_SIGNATURE` | 签名路径写错。签名用 `/api/openApi/rcs/send`（含 `/api`、**不含** `/service`），实际 URL 是 `{BASE}/openApi/rcs/send` |
| `AUTH_TIMESTAMP_EXPIRED` | 本机时间漂移 > 5 分钟，校准 NTP |
| `AUTH_IP_FORBIDDEN` | 出口 IP 未加白 |
| 一直 `sent` 收不到回执 | 平台 callbackUrl / secret 没配或配错；看 api 日志 `RCS 回执验签失败` |
| 回执 403 且日志说 `未配置 webhook_secret` | 后台通道没填「回执 secret」 |
| 发送报 `RCS 文案超过 160 个字符` / `不支持 emoji` | 本系统入口拦截（不是上游拒的），改文案即可 |
| 大量 `发送过于频繁` | `max_tps` 高于合同 QPS，调低通道下发总速度 |

关键日志关键字：`RCS 发送受理` / `RCS 业务拒绝` / `RCS 鉴权失败` / `RCS 回执处理完成`。

## 5. 涉及文件

通道与发送：

```
backend/app/workers/adapters/rcs_adapter.py   叮咚 OpenAPI 客户端（签名/发送/报告/余额/回执验签）
backend/app/utils/rcs_content.py              文案校验（160 字符 / emoji）与 E.164 归一
backend/app/api/v1/rcs.py                     回执 Webhook + 管理端余额/报告/回执URL
backend/app/workers/sms_worker.py             _send_via_rcs 与协议分发
backend/app/core/pricing.py                   billable_units：RCS 按条计费
backend/app/modules/sms/channel.py            protocol 枚举 + get_rcs_config()
backend/alembic/versions/c7d8e9f0a1b2_*.py    channels.protocol 增加 RCS（已被 e9f0a1b2c3d4 收回）
backend/alembic/versions/e9f0a1b2c3d4_*.py    protocol 收回 RCS，改用 config_json.rcs.vendor
frontend/src/views/admin/Channels.vue         RCS 通道表单
```

RCS 业务与开户：

```
backend/alembic/versions/d8e9f0a1b2c3_*.py    account_templates / accounts 的 business_type 增加 rcs
backend/app/api/v1/account_templates.py       模板业务类型放行 rcs
backend/app/api/v1/admin.py                   通道价格→模板底价/资源报价 按通道协议分流到 rcs
backend/app/core/invitation.py                RCS 开户的 services 与试用金
telegram_bot/bot/utils.py                     BIZ_NAMES / biz_label 业务名单一数据源
telegram_bot/bot/handlers/menu.py             开户邀请业务选择、我的客户 RCS 分类、RCS 工单
telegram_bot/bot/handlers/sales.py            /invite 业务类型加 RCS
telegram_bot/bot/handlers/biz_ticket.py       RCS 业务工单
frontend/src/views/admin/AccountTemplates.vue RCS 模板（关联通道方式与短信一致）
frontend/src/views/admin/Accounts.vue         RCS 客户 Tab 与接入/计费表单
```

改动后需要 `docker compose restart api worker worker-sms bot`
（worker/bot 在 volume 挂载下不重启不生效）。
