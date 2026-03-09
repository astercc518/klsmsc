# DLR（送达回执）排查指南

## 现象

短信发送后状态一直显示「已发送」，没有更新为「已送达」或「失败」。

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

### 3. 推送模式配置（推荐）

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

### 4. 拉取模式（HTTP 通道）

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

### 5. 查看日志

- 拉取：搜索 `拉取 DLR`、`解析到 N 条 DLR 报告`、`DLR 找不到对应记录`
- 推送：搜索 `收到 DLR 回调`、`DLR 回调处理完成`
- 发送：搜索 `upstream_id=` 确认是否保存了上游消息 ID

## 本次代码改进

1. **扩展 upstream_message_id 提取**：支持 `mid`、`msgid`、`taskid`、`message_id`、`id` 等字段；无 list 时从响应顶层尝试提取
2. **DLR 匹配兜底**：除 `upstream_message_id` 外，增加用 `message_id`（我们的 ID）匹配，兼容回传我们 ID 的上游

## 日志排查结论（Kaola 通道）

从运行日志可见：
- **KAOLA_PH_HTTP、KAOLA_VN、KAOLA_MO**：拉取返回 `<returnsms></returnsms>`（空），表示该账号下暂无 DLR 报告
- **KAOLA_PH_OTP**：返回 `CON_INVALID_AUTH`，report 接口认证失败，需检查通道的 username/password（或 api_key）
- **KAOLA_TH**：SMPP 通道（7099），DLR 通过 deliver_sm 推送。**必须使用 transceiver 模式**才能接收；若配置为 transmitter 则无法收到 DLR。系统已对 Kaola SMPP 自动优先尝试 transceiver；若上游不支持会降级为 transmitter（此时无 DLR）

DLR 按通道账号拉取，发送用哪个通道，回执就需用该通道的账号拉取。

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
