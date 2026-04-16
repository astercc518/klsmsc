# DLR（送达回执）排查指南

## 现象

短信发送后状态一直显示「已发送」，没有更新为「已送达」或「失败」。

### Worker 提交顺序竞态（已修复）

`send_sms_task` 曾在 **`status=sent` 首次 commit 之后**才执行 SMPP/HTTP 发送，发送成功后再把 **`upstream_message_id`** 写在内存里，直到 **Webhook 之后**才第二次 `commit`。  
`deliver_sm` 与 `submit_sm_resp` 往往只差几百毫秒，DLR 处理在 **独立线程**里读库时，若第二次 commit 尚未执行，**按 `upstream_message_id` 查询会落空**，日志表现为 `SMPP DLR: 未找到 upstream_id=...`；部分短信后续不再重推同一条 DLR，则界面会长期 **「送达等待中」**。

**修复**：在 **`_send_via_smpp` / `_send_via_http` 返回成功之后、Webhook 之前**立即 **`await db.commit()`**，优先持久化上游 ID。

### 与界面文案的对应关系（易混淆点）

- **数据库 `status = sent` + 已有 `upstream_message_id`**：表示通道已受理并成功拿到上游消息 ID，**不等于**用户手机已收到。
- **时间线里的「送达」**：仅在有 **终端 DLR** 并成功解析为送达时，才会写入 `delivery_time` 并将 `status` 更新为 `delivered`。
- 因此会出现：**通道侧显示「已提交上游」类提示，但「送达」仍为等待中**——这在未收到/未匹配终端回执时是正常现象。

前端「发送记录 → 短信详情」中已用「通道回执 / 已提交上游」等文案与 Tooltip 区分上述两个阶段；排查请以 `sms_logs.status`、`delivery_time` 及日志为准。

### 发送任务列表（批次）新字段与部署

- **接口**：`GET /batches`、`GET /batches/{id}` 的响应中会多出 **`delivered_count`**（`delivered` 条数）、**`sent_awaiting_receipt_count`**（**pending + queued + sent**，含购数并发送入队后尚未下发、或已送通道待终态回执）。列表页的「通道已接受 / 已送达(回执) / 待终态回执 / 终态回执送达率」依赖上述字段。购数并发送路径**不得**用入队数覆盖 `SmsBatch.success_count`，应与 `update_batch_progress` 一致（见 `data_worker`）。
- **上线要求**：**API 与前端需同时发布**。只更前端时新列多为 0 或与真实回执脱节；只更后端时旧前端不会展示拆列。
- **发布后**：管理后台若仍像旧版，对浏览器做一次 **强制刷新（Ctrl+F5）** 或重建前端镜像。
- **「待终态回执」长期偏大**：在「发送记录」里按单条看 `status`；对照服务日志是否出现 **`DLR 状态未识别`** 或 **`DLR 找不到对应记录`**，再扩展 `dlr_handler` 解析字段或 `upstream_message_id` 匹配规则。

## 原因说明

系统在短信提交成功后先标记为 `sent`（已发送），等待上游通道的 DLR（Delivery Report）回执后才会更新为 `delivered`（已送达）或 `failed`（失败）。

DLR 获取方式有两种：

1. **推送模式**：上游在送达/失败时主动回调我们的接口
2. **拉取模式**：我们定时请求上游的 report 接口获取状态

若上游未配置回调、或拉取 URL/参数不匹配、或 `upstream_message_id` 未正确保存，则无法匹配到对应记录，状态会一直停留在「已发送」。

## 排查步骤

### 1. 确认通道类型

- **HTTP 通道**：支持拉取（每 30 秒）和推送回调
- **SMPP 通道**：仅支持推送（通过 deliver_sm PDU）

### 2. 检查 upstream_message_id

在数据库 `sms_logs` 表中查看对应记录的 `upstream_message_id` 字段：

- 若为空：上游未返回消息 ID，或返回格式未被识别，DLR 无法匹配
- 若有值：说明已保存，需确认 DLR 报告中的 message_id 与该值一致

### 3. GET 回调参数名不全在路由声明里（已修复）

历史上 `GET /dlr/callback` 仅绑定少量查询参数名（如 `mid`、`msgid`），上游若使用 `task_id`、`messageid`、`sn` 等字段，**整条请求会被当成「缺少 message_id」而丢弃**。

当前实现已改为：**将 URL 全部 query 转为小写后走 `parse_form_dlr`**，与表单回调共用一套字段别名；若仍收不到，请抓包对照 `parse_form_dlr` / `dlr_handler.py` 是否需再扩展键名。

### 4. 推送模式配置（推荐）

若上游支持 DLR 回调，需在上游后台配置回调 URL：

```
POST https://你的域名/api/v1/sms/dlr/callback
```

或按通道区分：

```
POST https://你的域名/api/v1/sms/dlr/callback/通道编码
```

**安全配置**（至少配置一项）：

- 环境变量 `DLR_CALLBACK_OPEN=true`：**允许无认证回调**（上游不支持 Token 时使用，收到回执后建议改为 Token/IP）
- 环境变量 `DLR_CALLBACK_TOKEN`：回调时需在 Header `X-DLR-Token` 或 Query `dlr_token` 中携带
- 环境变量 `DLR_CALLBACK_IP_WHITELIST`：上游服务器 IP 白名单，逗号分隔；`0.0.0.0/0` 表示允许所有 IP

**若上游已推送回执但状态未更新**：多为认证被拒（403）。请设置 `DLR_CALLBACK_OPEN=true`（上游不支持 Token 时）或配置 Token/IP 白名单后重启服务。

**Cloudflare 代理（橙色云）**：回调 URL 使用 **`https://你的域名/...`** 时，请求先到 Cloudflare 再回源到服务器，**一般不影响** POST 与 JSON/表单体转发。注意两点：（1）**IP 白名单**：回源侧看到的客户端 IP 往往是 **Cloudflare 网段**，而不是上游机房出口 IP；若启用 `DLR_CALLBACK_IP_WHITELIST`，应改为 **Token 校验**（推荐），或放行 [Cloudflare IP 段](https://www.cloudflare.com/ips/)，而不是只填「上游 IP」。（2）若在上游填写的是 **`http(s)://107.148.34.177/...` 直连公网 IP**，则**不经过** Cloudflare，与域名代理无关，需本机防火墙/安全组放行上游出口，且 HTTPS 在纯 IP 上需单独配置证书。

### 5. 拉取模式（HTTP 通道）

系统每 30 秒会拉取 Kaola 风格接口的 DLR 报告。若通道 API 非 Kaola 格式，需确认：

- 拉取 URL 是否正确（由 `api_url` 自动推断：`/smsv2`→`/sms`，或 `/send`→`/report`）
- 拉取参数 `action=report`、`account`、`password` 是否与上游要求一致
- 上游返回的 DLR 格式是否被解析（支持 JSON/XML，字段 mid/msgid/taskid 等）

**URL 覆盖**：若自动推断的 report URL 不正确，可在系统配置中新增 `dlr_report_url_override`（类型 json），例如：

```json
{"KAOLA_PH_HTTP": "https://实际report接口完整URL"}
```

或指定 POST 方法：

```json
{"KAOLA_PH_HTTP": {"url": "https://xxx/report", "method": "POST"}}
```

**SMPP 通道（如 KAOLA_TH）**：SMPP 通道默认仅通过 deliver_sm 接收 DLR。若上游提供 HTTP report 接口（与 SMPP 同账号），可在 `dlr_report_url_override` 中为该通道配置 report URL，系统会定时拉取：

```json
{"KAOLA_TH": "https://kaola的report接口完整URL"}
```

需确保 KAOLA_TH 通道已配置 username/password（与 SMPP 登录一致，report 接口通常使用相同认证）。

添加方式：管理后台 → 系统配置 → 新增配置，key 填 `dlr_report_url_override`，类型选 `json`，值填上述 JSON。

### 6. 查看日志

- 拉取：搜索 `拉取 DLR`、`解析到 N 条 DLR 报告`、`DLR 找不到对应记录`
- 推送：搜索 `收到 DLR 回调`、`DLR 回调处理完成`
- 发送：搜索 `upstream_id=` 确认是否保存了上游消息 ID

## 本次代码改进

1. **扩展 upstream_message_id 提取**：支持 `mid`、`msgid`、`taskid`、`message_id`、`id` 等字段；无 list 时从响应顶层尝试提取
2. **DLR 匹配兜底**：除 `upstream_message_id` 外，增加用 `message_id`（我们的 ID）匹配，兼容回传我们 ID 的上游
3. **GET `/dlr/callback`**：全量 query + `parse_form_dlr`，避免非标准参数名导致静默丢回执
4. **parse_form_dlr**：增加 `task_id`、`messageid`、`stat`、`dr` 等别名，减少「有回执但解析不到状态」的情况
5. **日志**：`DLR 状态未识别` 时附带 `report_keys`，便于对照上游字段；若持续出现，可在 `normalize_status` 中按通道文档增补映射

## 日志排查结论（Kaola 通道）

从运行日志可见：
- **KAOLA_PH_HTTP、KAOLA_VN、KAOLA_MO**：拉取返回 `<returnsms></returnsms>`（空），表示该账号下暂无 DLR 报告
- **KAOLA_PH_OTP**：返回 `CON_INVALID_AUTH`，report 接口认证失败，需检查通道的 username/password（或 api_key）
- **KAOLA_TH**：SMPP 通道（7099），DLR 通过 deliver_sm 推送。**必须使用 transceiver 模式**才能接收；若配置为 transmitter 则无法收到 DLR。系统已对 Kaola SMPP 自动优先尝试 transceiver；若上游不支持会降级为 transmitter（此时无 DLR）

DLR 按通道账号拉取，发送用哪个通道，回执就需用该通道的账号拉取。

## SMPP：误存 `upstream_message_id=7` 等短数字（已修复）

若 `sms_logs.upstream_message_id` 仅为 **1～3 位数字**，多为历史逻辑把 **`submit_sm` 的 PDU sequence** 误当作上游消息 ID。`deliver_sm` 报告体里的 `id:` 为长串（如 `20260324231908HY0XIBJK`），**永远对不上**，表现为一直 `sent`、无送达时间。

**修复**：不再使用 `sequence` 作 ID；若 submit 未返回 message_id 则留空；DLR 处理增加 **按 `destination_addr` / `source_addr` 与通道 ID** 在 `sent` 记录中兜底匹配，并回写真实 `upstream_message_id`。

## SMPP：message_payload / message_state TLV（已支持）

部分上游将 DLR 放在 **optional TLV** `message_payload` 中，而 **`short_message` 为空**；仅用文本正则解析会跳过，界面长期「已发送」。当前 Worker 会合并 `short_message` + `message_payload` 再解析；若无文本但存在 **`receipted_message_id` + `message_state`**，会按 TLV 映射终态（与常见 SMPP 枚举一致）。

## SMPP：连接保持时间

默认发送成功后 **延迟 300s** 再断开 TCP，以便同连接接收 `deliver_sm`。环境变量 **`SMPP_DLR_SOCKET_HOLD_SECONDS`** 可调到 **86400（24h）**；更久依赖 **HTTP report 拉取或回调**，长连一般无法一直空闲。

可在管理后台通道上配置 **`smpp_dlr_socket_hold_seconds`**（覆盖全局），便于「快通道短保持、慢通道长保持」。

## DLR 超时（expired）

定时任务将长期仍为 **`sent`** 的记录标为 **`expired`**。全局默认由 **`DLR_SENT_TIMEOUT_HOURS`** 控制（默认 **72h**，可调至 **720h**）。可在通道上配置 **`dlr_sent_timeout_hours`**，对「终态回执可晚于 12～24 小时」的线路单独加长。定时 **HTTP 拉取** 的超时可调 **`DLR_PULL_HTTP_TIMEOUT_SECONDS`**。

## SMPP DLR 排查清单

### 1. registered_delivery 是否请求了状态报告

submit_sm 的 `registered_delivery` 必须为 1 才会请求 DLR。当前实现已设置 `registered_delivery=1`。

### 2. Bind 模式

- **Transmitter**：仅发送，无法接收 deliver_sm
- **Transceiver**：收发一体，可接收 deliver_sm
- **Receiver**：仅接收

系统对 Kaola SMPP 自动优先尝试 transceiver；若上游不支持会降级为 transmitter（此时无 DLR）。

### 3. message_id 匹配

常见问题：submit_sm_resp 返回十进制 ID，deliver_sm 回传十六进制（或反之）。系统已做兼容：
- 统一转字符串匹配
- 支持 hex/decimal 互转尝试（见代码 `_update_dlr_status`）

### 4. 日志排查

- 发送：`SMPP发送成功`、`upstream_message_id`
- 接收：`收到 deliver_sm`、`DLR: id=`
- 更新：`SMPP DLR 更新成功` 或 `SMPP DLR: 未找到 upstream_id`
- 异常：`SMPP DLR 更新失败`、`处理 deliver_sm 失败`

## 通道 TS_zhikun 建议

请向通道供应商确认：

1. 是否支持 DLR？以推送还是拉取方式提供？
2. 推送：回调 URL 格式、认证方式
3. 拉取：report 接口 URL、请求参数、响应格式
4. 发送接口返回的消息 ID 字段名（mid/msgid/taskid 等）

若供应商不支持 DLR，则状态会一直保持「已发送」，可考虑在通道配置中增加「无 DLR 时默认视为已送达」等策略（需另行开发）。
