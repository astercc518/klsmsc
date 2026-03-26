# SMPP 短信状态回执（DLR）对接指南

对接 SMPP 时，**送达回执（Delivery Receipt，DLR）** 的稳定接收是开发中最容易出问题的环节之一。底层协议虽有标准，但各 SMSC/网关的实现细节常有差异。要保证回执能收到且能**精准匹配**到业务单，建议从以下四个维度设计系统。

---

## 一、协议发送层：主动索要回执

多数网关**不会默认**下发终端状态报告，必须在提交短信的 **submit_sm** PDU 中显式声明需要状态报告。

### 核心字段：`registered_delivery`

构建 submit_sm 时，将 **`registered_delivery` 设为 `1`（即 `0x01`）**，表示要求 SMSC 在短信最终成功或失败时生成并返回回执。

- 若为 **`0`**，通常**收不到**该条的最终投递状态。
- 具体位含义以 SMPP 规范及通道文档为准；若通道有额外要求（如某些 TLV），以通道说明为准。

---

## 二、链路维持层：保持接收通道可用

回执由网关**主动推送**，接收侧必须长期可用。

### 绑定模式

- **推荐 `bind_transceiver`**：同一 TCP 连接上既可发 submit，又可收 deliver_sm，运维与重连策略最简单。
- 若使用 **`bind_transmitter` + `bind_receiver` 分离**：必须保证 **Receiver 会话始终为已连接、可读**，否则回执会在网关侧堆积或丢弃。

### 心跳保活

- 周期性发送 **enquire_link**，并正确处理 **enquire_link_resp**。
- 若心跳超时，往往表示 TCP **假死**；此时网关侧推送的回执可能全部丢失。应**关闭 Socket 并触发重连**，而不是继续在旧连接上“等数据”。

---

## 三、数据处理层：解析与匹配（高频踩坑）

即使网关下发了回执，若解析或 ID 匹配错误，业务上仍表现为“没收到回执”。

### 1. 持久化 submit_sm_resp 的 Message ID

- 发送 submit_sm 后，SMSC 返回 **submit_sm_resp**，其中包含 **`message_id`**。
- 必须将**内部业务流水号**与该 **`message_id`** 绑定并**持久化**（如数据库、Redis 等），供后续 DLR 关联。

### 2. 尽快响应 deliver_sm

- 回执通过 **deliver_sm** 推送。
- 收到 **deliver_sm** 后，协议层应**尽快**回复 **deliver_sm_resp**。若业务处理过慢导致响应超时，网关可能降速推送、甚至断连，后续回执丢失。
- **建议**：在 I/O 线程中只做最小处理（解析 + 入队 + 回 resp），重逻辑放到异步 Worker。

### 3. 解析回执内容与匹配 ID

- 文本型回执多在 **deliver_sm** 的 **`short_message`** 中（固定格式的纯文本片段）。
- 部分实现也会在可选参数（TLV）如 **`receipted_message_id`** 中携带，需同时兼容。

### ⚠️ 格式转换陷阱

- **submit_sm_resp** 里的 `message_id` 可能是十进制数字字符串；
- **deliver_sm** 正文里 `id:` 等字段有时是**同一数值的十六进制表示**（或相反）。
- 若按字符串相等匹配失败，应**打印原始 PDU/原文**，确认是否需要 **十进制 ⟷ 十六进制** 归一化后再比对。

---

## 四、架构设计层：高并发与长延迟

### 异步解耦

- DLR 到达时间与发送时间**高度异步**（数秒到**最长约 72 小时**等场景均可能存在）。
- **禁止**在负责 SMPP 读写的线程里长时间查库、写复杂业务。
- 推荐流程：收到 deliver_sm → **立即 deliver_sm_resp** → 将解析结果写入消息队列（Kafka、RabbitMQ、Redis List 等）→ 由 Worker 消费后再做库表匹配与状态机更新。

### 长短信（Concatenated SMS）

- 长短信可能被拆成多条 submit；不同网关策略不同：
  - 可能**每条分片各有一条**回执；
  - 也可能**只对首条或末条**给一条汇总回执。
- 业务层需有**合并策略**（例如：所有分片均为 `DELIVRD` 才视为最终成功，或按通道文档约定），避免只更新其中一片导致状态错误。

---

## 五、与本仓库配置项对照表（环境变量 + `dlr_report_url_override`）

以下与 **本仓库**（`backend/app/config.py`、通道表、`fetch_dlr_reports_task`）一致，便于将上文通用原则落到具体配置。默认值以代码为准，生产环境请用 `.env` 或编排环境变量覆盖。

### 1. 环境变量（`Settings` / `.env`）

| 变量名 | 作用简述 | 与 DLR / SMPP 的关系 |
|--------|----------|----------------------|
| `SMPP_REDIS_CLUSTER_LOCK` | 是否用 Redis 锁串行化多进程下的同一 SMPP 通道 bind | 为 `true` 时，发送成功后会**立即断开 TCP**，**无法在同一连接上收 `deliver_sm`**；需依赖 HTTP 拉取/回调或 `worker-sms --concurrency=1` 且本项为 `false` |
| `SMPP_SUBMIT_RESP_WAIT_SECONDS` | 等待 `submit_sm_resp` 的最长秒数 | 过短可能拿不到 `message_id`；入站可被 `deliver_sm` 插队，实现上已 drain 至同 sequence 应答 |
| `SMPP_DLR_SOCKET_HOLD_SECONDS` | **非集群锁**模式下，发送后保持 SMPP 连接的最长秒数（上限 86400） | 超时且无新发送/新 DLR 刷新则断连，**晚到的 `deliver_sm` 可能丢失**；慢回执通道应加大或配 HTTP 补拉 |
| `DLR_SENT_TIMEOUT_HOURS` | `sent` 状态超过该小时数仍未收到终态 DLR 则标记为 `expired`（4～720） | 与「上游 72 小时内回执」类 SLA 对齐；可按通道再覆盖（见下表 `channels.dlr_sent_timeout_hours`） |
| `DLR_PULL_HTTP_TIMEOUT_SECONDS` | 定时任务拉取上游 report 的 HTTP 超时（10～300 秒） | 拉取过慢会拖住 `sms_dlr` 队列，过短可能误判失败 |
| `DLR_CALLBACK_TOKEN` | 推送回调 Header `X-DLR-Token` 或 Query `dlr_token` | 上游 HTTP 推送 DLR 时的鉴权；与 SMPP 并行存在时各自独立 |
| `DLR_CALLBACK_IP_WHITELIST` | 回调来源 IP 白名单（逗号分隔） | 代理/CDN 场景需注意真实客户端 IP，见 [DLR 排查指南](./DLR_TROUBLESHOOTING.md) |
| `DLR_CALLBACK_OPEN` | 为 `true` 时允许无 Token/IP 的回调 | 仅建议联调；生产应关闭并改用 Token 或白名单 |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_DB` / `REDIS_PASSWORD` | Redis 连接 | 仅在 `SMPP_REDIS_CLUSTER_LOCK=true` 时参与 SMPP 跨进程锁 |

**Docker Compose 提示**：`worker-sms` 服务通常注入 `SMPP_DLR_SOCKET_HOLD_SECONDS`、`DLR_SENT_TIMEOUT_HOURS` 等；`beat` 负责每 30 秒触发 `fetch_dlr_reports_task`，若 Beat 未运行则**不会**自动 HTTP 拉取 DLR。

### 2. 数据库表 `channels`（SMPP / DLR 相关列）

| 字段 | 说明 |
|------|------|
| `smpp_bind_mode` | `transceiver` / `transmitter` / `receiver`；仅 `transceiver` 或 `receiver` 会注册 `deliver_sm` 回调（纯 `transmitter` 时同连接**收不到** SMPP 推送 DLR） |
| `smpp_system_type` | SMPP `bind` 的 `system_type` |
| `smpp_interface_version` | 接口版本（如 `0x34`） |
| `smpp_dlr_socket_hold_seconds` | 覆盖全局 `SMPP_DLR_SOCKET_HOLD_SECONDS`；为空则用环境变量全局值 |
| `dlr_sent_timeout_hours` | 覆盖全局 `DLR_SENT_TIMEOUT_HOURS`；为空则用环境变量全局值 |

### 3. 系统配置 `dlr_report_url_override`（表 `system_config`）

- **存储位置**：表 **`system_config`**，键名 **`dlr_report_url_override`**（`config_key`），值为 **JSON 字符串**（`config_value`）。
- **作用**：为指定 **`channel_code`** 配置 HTTP 报告地址后，**SMPP 通道**也会参与定时拉取（`fetch_dlr_reports_task`），作为「长延迟 / 断线后」补 DLR 的第二路径；纯 SMPP且**未配置**该项时，仅依赖 TCP 上的 `deliver_sm`（外加你们对上游开放的 HTTP 推送回调，若有）。

**JSON 示例**（键为通道编码，与后台通道 `channel_code` 一致）：

```json
{
  "KAOLA_PH_HTTP": "https://example.com/sms/report",
  "OTHER_SMPP": {
    "url": "https://example.com/api/dlr",
    "method": "POST"
  }
}
```

- 值为**字符串**：该 URL 为报告地址；拉取时默认 `GET`，若上游返回 `405` 会再尝试 `POST`（与实现一致）。
- 值为**对象**：使用 `url` 必填，`method` 可选 `GET`/`POST`（默认 `GET`）。

拉取请求会携带 `action=report` 及通道的 `username`/`password`（与 Kaola 风格 report 兼容）；SMPP 通道参与拉取的前提是：**在 override 中为该 `channel_code` 配置了 URL**，且通道已配置可用的账号密码。

---

## 与本项目排查文档的关系

若回执已到达但界面/数据库状态仍不更新，除上述通用 SMPP 要点外，还可结合仓库内 **[DLR 排查指南](./DLR_TROUBLESHOOTING.md)**，核对 `upstream_message_id` 持久化时机、HTTP 回调参数名、认证与白名单等项目侧已知的踩坑点。
