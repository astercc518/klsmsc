# BoltTel RCS OpenAPI 对接指南

面向客户开发。开通后可获得 `appKey` / `appSecret`，并配置发件人（`sendCode`）、目标国家单价与回执 Webhook。

---

## 1. 地址与鉴权

```
BASE = https://user.fcuncloud.com/service/api
```

| 接口 | 方法 | URL |
| ---- | ---- | --- |
| 发送 | POST | `{BASE}/openApi/rcs/send` |
| 批次报告 | GET | `{BASE}/openApi/rcs/report?batchId=...&withMessages=false` |
| 余额 | GET | `{BASE}/openApi/rcs/balance` |

### 请求头（所有 OpenAPI 必带）

| Header | 说明 |
| ------ | ---- |
| `X-App-Key` | appKey |
| `X-Timestamp` | 毫秒时间戳（与服务器偏差 ≤ 5 分钟） |
| `X-Nonce` | 随机串（建议 UUID；同一 appKey 下 5 分钟内勿重复） |
| `X-Signature` | 下方签名 |
| `Content-Type` | `application/json`（仅 POST 需要） |

### 签名

```
bodySha256   = HEX_LOWER(SHA256(请求体字节))   # GET 无 body 时对空字节做 SHA256
stringToSign = METHOD + "\n" + PATH + "\n" + X-Timestamp + "\n" + X-Nonce + "\n" + bodySha256
X-Signature  = HEX_LOWER(HMAC_SHA256(appSecret, stringToSign))
```

| 项 | 值 |
| -- | -- |
| METHOD | 大写，如 `POST` / `GET` |
| PATH（签名用） | `/api/openApi/rcs/send`（**含** `/api`，**不含** `/service`） |
| 实际 URL | `{BASE}/openApi/rcs/send`（BASE 已含 `/service/api`） |

报告 / 余额签名 PATH 分别为：`/api/openApi/rcs/report`、`/api/openApi/rcs/balance`。  
Query 参数（如 `batchId`）**不参与**签名。

> 注意：响应体里的 `request` 字段是 `POST /openApi/rcs/send`（不含 `/api`），与签名 PATH 不同，请勿混用。

### 请求伪代码

```text
METHOD = "POST"
URL_PATH = "/openApi/rcs/send"              # 拼到 BASE 后面
SIGN_PATH = "/api/openApi/rcs/send"         # 仅用于签名
bodyBytes = UTF8(jsonBody)                  # 与最终 HTTP body 字节完全一致
timestamp = nowMillis()
nonce = uuid()
bodySha256 = hexLower(sha256(bodyBytes))
stringToSign = METHOD + "\n" + SIGN_PATH + "\n" + timestamp + "\n" + nonce + "\n" + bodySha256
signature = hexLower(hmacSha256(appSecret, stringToSign))

HTTP POST BASE + URL_PATH
  Header X-App-Key    = appKey
  Header X-Timestamp  = timestamp
  Header X-Nonce      = nonce
  Header X-Signature  = signature
  Header Content-Type = application/json
  Body = bodyBytes
```

GET 报告 / 余额：`bodyBytes` 为空；`SIGN_PATH` 改为对应路径；URL 带 query。

### Java 鉴权示例

```java
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.UUID;

public class BoltTelRcsSigner {

    private final String base;       // https://<域名>/service/api
    private final String appKey;
    private final String appSecret;

    public BoltTelRcsSigner(String base, String appKey, String appSecret) {
        this.base = base.endsWith("/") ? base.substring(0, base.length() - 1) : base;
        this.appKey = appKey;
        this.appSecret = appSecret;
    }

    /** 发送：signPath=/api/openApi/rcs/send，urlPath=/openApi/rcs/send */
    public String postSend(String jsonBody) throws Exception {
        return request("POST", "/api/openApi/rcs/send", "/openApi/rcs/send",
                jsonBody.getBytes(StandardCharsets.UTF_8), null);
    }

    public String getReport(String batchId, boolean withMessages) throws Exception {
        String qs = "batchId=" + batchId + "&withMessages=" + withMessages;
        return request("GET", "/api/openApi/rcs/report", "/openApi/rcs/report",
                new byte[0], qs);
    }

    public String getBalance() throws Exception {
        return request("GET", "/api/openApi/rcs/balance", "/openApi/rcs/balance",
                new byte[0], null);
    }

    private String request(String method, String signPath, String urlPath,
                           byte[] body, String query) throws Exception {
        String timestamp = String.valueOf(System.currentTimeMillis());
        String nonce = UUID.randomUUID().toString();
        String bodySha = sha256Hex(body);
        String stringToSign = method + "\n" + signPath + "\n" + timestamp + "\n" + nonce + "\n" + bodySha;
        String signature = hmacSha256Hex(appSecret, stringToSign);

        String url = base + urlPath + (query == null || query.isEmpty() ? "" : "?" + query);
        HttpRequest.Builder b = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .header("X-App-Key", appKey)
                .header("X-Timestamp", timestamp)
                .header("X-Nonce", nonce)
                .header("X-Signature", signature);
        if ("POST".equals(method)) {
            b.header("Content-Type", "application/json; charset=UTF-8")
             .POST(HttpRequest.BodyPublishers.ofByteArray(body));
        } else {
            b.GET();
        }
        HttpResponse<String> resp = HttpClient.newHttpClient()
                .send(b.build(), HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        return resp.body();
    }

    private static String sha256Hex(byte[] data) throws Exception {
        return toHex(MessageDigest.getInstance("SHA-256").digest(data == null ? new byte[0] : data));
    }

    private static String hmacSha256Hex(String secret, String data) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
        return toHex(mac.doFinal(data.getBytes(StandardCharsets.UTF_8)));
    }

    private static String toHex(byte[] bytes) {
        StringBuilder sb = new StringBuilder(bytes.length * 2);
        for (byte b : bytes) sb.append(String.format("%02x", b));
        return sb.toString();
    }
}
```

调用示例：

```java
BoltTelRcsSigner client = new BoltTelRcsSigner(
        "https://<生产域名>/service/api", "yourAppKey", "yourAppSecret");

String body = "{"
        + "\"sendCode\":\"YourSenderId\","
        + "\"isoCode\":\"BR\","
        + "\"sendMode\":\"broadcast\","
        + "\"content\":\"Hello RCS\","
        + "\"phones\":[\"+5511987654321\"],"
        + "\"clientRef\":\"order-001\""
        + "}";
String resp = client.postSend(body);
```

> 参与签名的 `body` 字节必须与 HTTP 实际发出的完全一致（勿签名后再被框架改写 JSON）。

---

## 2. 计费规则（重点）

| 规则 | 说明 |
| ---- | ---- |
| 计价口径 | 按目标国家（`isoCode`）单价计费；单价由平台为您的账户配置。**未配置则整批拒收、不扣费** |
| 预扣 | 发送受理成功（`code=0` 且 `duplicated=false`）后，按「条数 × 单价」从余额**预扣** |
| 成功计费 | 消息终态为 `DELIVERED`（已送达）或 `READED`（已读）→ 计入消费 |
| 失败退回 | 消息终态为 `UNDELIVERABLE` / `REJECTED` / `EXPIRED` / `SEND_FAILED` → 该条预扣在批次完成后**退回** |
| 在途 | `PENDING` 表示处理中，费用仍在预扣中 |
| 回复 | `REPLY`（用户回复）不计费 |
| 校验失败 | 参数不合规整批拒绝，**不扣费** |
| 幂等 | 相同 `clientRef` 重复提交返回原批次，`duplicated=true`，**不重复扣费** |

金额字段对应关系：

1. 发送成功返回：`deductAmount` = 本批预扣总额（字符串）  
2. 批次完成后查报告：`refundAmount`（失败退回）、`actualAmount`（实扣 = 预扣 − 退回）  
3. 具体单价以商务合同 / 平台配置为准；对账以报告金额与 Webhook 终态为准。

---

## 3. 发送 `POST /openApi/rcs/send`

### 限制（任一不满足 → 整批拒绝、不扣费）

- 单次最多 **1000** 条  
- 每条文案最多 **160** 个 Unicode 字符，**禁止 emoji**  
- 单批只能一个 `isoCode`；号码须为国际格式（建议 E.164，如 `+5511987654321`），且须属于该国家  
- `sendCode` 须为平台已为您开通的发件人  

### 广播（同文案）

```json
{
  "sendCode": "YourSenderId",
  "isoCode": "BR",
  "sendMode": "broadcast",
  "content": "Hello, this is an RCS message.",
  "phones": ["+5511987654321", "+5521912345678"],
  "clientRef": "order-20260717-001"
}
```

### 个性化（一号一文案）

```json
{
  "sendCode": "YourSenderId",
  "isoCode": "BR",
  "sendMode": "personalized",
  "messages": [
    { "phone": "+5511987654321", "content": "Olá João, seu pedido foi enviado." },
    { "phone": "+5521912345678", "content": "Olá Maria, seu pedido foi enviado." }
  ],
  "clientRef": "order-20260717-002"
}
```

| 字段 | 必填 | 说明 |
| ---- | ---- | ---- |
| sendCode | 是 | 发件人 ID（平台开通） |
| isoCode | 是 | 目标国家，如 `BR` / `CN`（单批仅一国） |
| sendMode | 是 | `broadcast` 或 `personalized` |
| content | 广播必填 | 全员同文案 |
| phones | 广播必填 | 号码列表 |
| messages | 个性化必填 | `{phone, content}[]` |
| clientRef | 强烈建议 | 业务侧唯一幂等键；超时重试请沿用同一值 |

### 成功返回（HTTP 200，`code=0`，业务数据在 `message`）

```json
{
  "code": 0,
  "message": {
    "batchId": "468295533663481856",
    "acceptedCount": 2,
    "deductAmount": "0.100000",
    "duplicated": false,
    "messageIds": [
      "msg:468295533663481856-0",
      "msg:468295533663481856-1"
    ],
    "messages": [
      { "messageId": "msg:468295533663481856-0", "phone": "+5511987654321" },
      { "messageId": "msg:468295533663481856-1", "phone": "+5521912345678" }
    ]
  },
  "request": "POST /openApi/rcs/send"
}
```

| 字段 | 类型 | 说明 |
| ---- | ---- | ---- |
| batchId | string | 批次 ID（**按字符串处理**，防 JS 精度丢失） |
| acceptedCount | number | 受理条数 |
| deductAmount | string | 本批预扣金额（明文小数，如 `"0.100000"`） |
| duplicated | boolean | `true` = 幂等命中，未再次扣费 |
| messageIds | string[] | 平台消息 ID，顺序与请求号码一致；格式 `msg:{batchId}-{index}` |
| messages | object[] | **推荐使用**：`{messageId, phone}` 显式映射，便于回执关联 |

**幂等命中（`duplicated=true`）说明：**

- 仍返回原 `batchId` / `acceptedCount` / `deductAmount`  
- **`messageIds` / `messages` 可能为 `null` 或不存在**  
- 请在首次成功受理时保存 `messages` 映射；后续重复提交不要依赖这两字段  

### 失败返回（业务校验 / 受理失败）

HTTP **200**，`code=10030`：

```json
{
  "code": 10030,
  "message": {
    "errorCode": "CONTENT_TOO_LONG",
    "errorMsg": "文案超过 160 字符的条目：+5511987654321"
  },
  "request": "POST /openApi/rcs/send"
}
```

此类失败整批拒绝。完整错误码见 **§7.2**。  
鉴权失败见 **§7.1**（HTTP 401 / 403 / 429，结构不同）。

---

## 4. 报告与余额

### 报告 `GET {BASE}/openApi/rcs/report?batchId=468295533663481856&withMessages=false`

用于对账兜底；日常状态以 Webhook 为准。建议轮询间隔 ≥ 60 秒。

```json
{
  "code": 0,
  "message": {
    "batchId": "468295533663481856",
    "status": "SETTLED",
    "sendMode": "broadcast",
    "totalCount": 2,
    "deliveredCount": 1,
    "failedCount": 1,
    "deductAmount": 0.1,
    "refundAmount": 0.05,
    "actualAmount": 0.05,
    "clientRef": "order-20260717-001",
    "createdAt": "2026-07-17T10:00:00",
    "settledAt": "2026-07-17T10:05:00"
  },
  "request": "GET /openApi/rcs/report"
}
```

| 字段 | 说明 |
| ---- | ---- |
| batchId | 批次 ID（字符串） |
| status | `SENDING`=处理中；`SETTLED`=批次已完成（金额已结清） |
| sendMode | `broadcast` / `personalized` |
| totalCount | 总条数 |
| deliveredCount | 成功条数（送达 / 已读） |
| failedCount | 失败条数 |
| deductAmount / refundAmount / actualAmount | 预扣 / 退回 / 实扣（JSON **数字**；与发送接口字符串形式不同） |
| clientRef | 发送时携带则回传 |
| createdAt / settledAt | 创建时间 / 完成时间（本地时间 ISO，无时区后缀） |

`withMessages=true` 时，`message` 中额外带 `messages` 数组（最多 1000 条），常用字段：

| 字段 | 说明 |
| ---- | ---- |
| messageId | 与发送返回一致 |
| phoneNumber | 号码 |
| status | 消息状态（见 §5.5） |
| content | 文案 |
| isoCode | 国家 |

批次不存在或不属于当前账户时：`code=10020`，`message` 为文案字符串（如 `"批次不存在"`）。

### 余额 `GET {BASE}/openApi/rcs/balance`

```json
{
  "code": 0,
  "message": {
    "userId": 10086,
    "balance": 998.50
  },
  "request": "GET /openApi/rcs/balance"
}
```

---

## 5. 回执 Webhook（重点）

在平台「API 接入 / 回执推送」配置回调 URL 与 `secret` 后，平台主动 `POST` 状态变更。

### 5.1 推送请求

| 项 | 说明 |
| -- | ---- |
| Method | `POST` |
| Content-Type | `application/json` |
| `X-Rcs-Signature` | `HEX_LOWER(HMAC_SHA256(secret, 请求体原文))` |
| `X-Rcs-Timestamp` | 推送毫秒时间戳 |
| `X-Rcs-Delivery` | 推送唯一 ID（批量时多个 ID 逗号分隔） |
| `X-Rcs-Delivery-Count` | 仅批量时有，本包条数 |

控制台常用配置：`callbackUrl`、`secret`、`pushQps`（HTTP 次/秒）、`pushBatchSize`（1~100，默认 1）、`timeoutMs`（默认 3000）、`retryMax`（默认 6）、`events`、`enabled=1`。

建议订阅：  
`DELIVERED,READED,UNDELIVERABLE,REJECTED,EXPIRED,SEND_FAILED,REPLY`

> `PENDING` 为在途状态，一般**不会**通过 Webhook 推送；请以终态事件为准。

### 5.2 单条推送体（`pushBatchSize=1`）

```json
{
  "deliveryId": "1943220000000000001",
  "batchId": "468295533663481856",
  "messageId": "msg:468295533663481856-0",
  "clientRef": "order-20260717-001",
  "phone": "+5511987654321",
  "iso": "BR",
  "status": "DELIVERED",
  "eventTime": "2026-07-17T02:05:00.000Z",
  "errorCode": null,
  "errorMsg": null,
  "reply": null,
  "version": "1.0"
}
```

### 5.3 批量推送体（`pushBatchSize>1`）

Body 为 **数组**，元素结构同上；对**完整数组原文**验签。整包非 2xx 则整包重试。

```json
[
  {
    "deliveryId": "1943220000000000001",
    "batchId": "468295533663481856",
    "messageId": "msg:468295533663481856-0",
    "clientRef": "order-20260717-001",
    "phone": "+5511987654321",
    "iso": "BR",
    "status": "DELIVERED",
    "eventTime": "2026-07-17T02:05:00.000Z",
    "version": "1.0"
  },
  {
    "deliveryId": "1943220000000000002",
    "batchId": "468295533663481856",
    "messageId": "msg:468295533663481856-1",
    "clientRef": "order-20260717-001",
    "phone": "+5521912345678",
    "iso": "BR",
    "status": "UNDELIVERABLE",
    "eventTime": "2026-07-17T02:05:01.000Z",
    "errorCode": "RCS_UNDELIVERABLE",
    "errorMsg": "...",
    "version": "1.0"
  }
]
```

### 5.4 字段说明

| 字段 | 说明 |
| ---- | ---- |
| deliveryId | **推送去重键**（重试会重复送达，务必按此幂等） |
| batchId / messageId | 与发送返回一致（按字符串处理） |
| clientRef | 发送时携带则回传 |
| phone / iso | 号码与国家 |
| status | 见 §5.5 |
| eventTime | UTC ISO-8601（带 `Z`） |
| errorCode / errorMsg | 失败时可能有值 |
| reply | 仅 `REPLY` 时有用户回复内容 |
| version | 固定 `1.0` |

> 推送体可能含其它内部字段，对接时请忽略未知字段，只依赖上表。

### 5.5 状态与计费关系

| status | 含义 | 计费 |
| ------ | ---- | ---- |
| PENDING | 在途 | 预扣中（通常不推 Webhook） |
| DELIVERED | 已送达 | 计费 |
| READED | 已读 | 计费 |
| UNDELIVERABLE | 不可达 | 退回 |
| REJECTED | 被拒绝 | 退回 |
| EXPIRED | 过期 | 退回 |
| SEND_FAILED | 发送失败 | 退回 |
| REPLY | 用户回复 | 不计费 |

同一消息可能先后收到 `DELIVERED` 与 `READED`，属正常；请按 `deliveryId` 去重，按 `messageId` 更新业务状态。

### 5.6 接收要求

1. **HTTP 2xx 视为成功**；建议 3 秒内返回（先落库再异步处理）。  
2. 按 `deliveryId` 幂等去重。  
3. 失败会自动重试（间隔递增，默认最多约 6 次）；仍失败可联系平台人工重推。  
4. 验签：`HEX_LOWER(HMAC_SHA256(secret, rawBody))` 与 `X-Rcs-Signature` 比对（对原始 body，勿先 parse 再序列化）。

---

## 6. 对接注意

- 每次请求换新 `X-Nonce`；网络超时重试发送时使用**同一** `clientRef`。  
- `batchId` / `deliveryId` / `messageId` 一律当**字符串**。  
- 首次受理成功后务必持久化 `messages`（`messageId ↔ phone`）；幂等重放时这两字段可能为空。  
- 回执以 Webhook 为主；`/report` 仅作对账兜底（轮询间隔建议 ≥ 60s）。  
- 保管好 `appSecret` 与 Webhook `secret`，勿写入代码库或客户端。  
- 签名 PATH 含 `/api`；响应 `request` 字段不含 `/api`——两者用途不同。

---

## 7. 错误码说明

判断顺序：先看 **HTTP 状态码**，再看 Body 的 `errorCode` / `code`。

### 7.1 鉴权错误（请求未进入业务）

响应**没有**统一包装里的 `request` 字段：

```json
{
  "code": 10000,
  "errorCode": "AUTH_BAD_SIGNATURE",
  "message": "签名校验失败"
}
```

（`AUTH_QPS_EXCEEDED` 时 `code` 为 `10140`。）

| errorCode | HTTP | 含义 | 处理建议 |
| --------- | ---- | ---- | -------- |
| AUTH_MISSING_HEADER | 401 | 缺少四个鉴权 Header 之一 | 补全 `X-App-Key` / `X-Timestamp` / `X-Nonce` / `X-Signature` |
| AUTH_INVALID_APP_KEY | 401 | appKey 不存在 | 核对密钥；联系平台确认已开通 |
| AUTH_DISABLED | 401 | 凭证已停用 | 联系平台重新启用或换新凭证 |
| AUTH_BAD_TIMESTAMP | 401 | `X-Timestamp` 非合法数字 | 传毫秒时间戳字符串 |
| AUTH_TIMESTAMP_EXPIRED | 401 | 与服务器时间差超过 5 分钟 | 校准 NTP；勿复用旧 timestamp |
| AUTH_NONCE_REPLAY | 401 | 同一 appKey 下 5 分钟内 nonce 重复 | 每次请求换新 UUID |
| AUTH_BAD_SIGNATURE | 401 | HMAC 验签失败 | 核对：① SIGN_PATH 含 `/api`、不含 `/service`；② body 字节与签名一致；③ appSecret 无多余空格；④ METHOD 大写 |
| AUTH_IP_FORBIDDEN | 403 | 来源 IP 不在白名单 | 将出口公网 IP 加入平台白名单 |
| AUTH_QPS_EXCEEDED | 429 | 超过账户发送 QPS | 降并发 + 指数退避；需更高配额联系商务 |

### 7.2 业务错误（发送校验 / 受理失败）

HTTP **200**，`code=10030`，错误详情在 `message`：

```json
{
  "code": 10030,
  "message": {
    "errorCode": "PRICE_MISSING",
    "errorMsg": "该客户未配置 BR 的 RCS 单价（请联系平台配置）"
  },
  "request": "POST /openApi/rcs/send"
}
```

| errorCode | 含义 | 是否扣费 | 处理建议 |
| --------- | ---- | -------- | -------- |
| SENDCODE_MISSING | 未传 `sendCode` | 否 | 补传平台开通的发件人 ID |
| ISO_MISSING | 未传 `isoCode` | 否 | 补传目标国家，如 `BR` |
| SENDCODE_INVALID | 发件人不可用（不存在 / 停用 / 不属于本账户） | 否 | 核对发件人；联系平台开通 |
| ROUTE_INVALID | 发件人当前不可用 | 否 | 联系平台检查发件人配置 |
| ROUTE_UNSUPPORTED | 发件人当前不可用 | 否 | 联系平台更换可用发件人 |
| REQ_EMPTY | 号码列表为空 | 否 | 检查 `phones` / `messages` |
| REQ_TOO_MANY | 超过单次 1000 条 | 否 | 拆批发送 |
| REQ_BAD_MODE | `sendMode` 与 body 不匹配 | 否 | `broadcast` 须带 `phones`+`content`；`personalized` 须带 `messages` |
| CONTENT_EMPTY | 某条文案为空 | 否 | 补全文案 |
| CONTENT_TOO_LONG | 文案超过 160 字符（按 Unicode 字符计，非字节） | 否 | 缩短文案 |
| CONTENT_EMOJI_FORBIDDEN | 文案含 emoji | 否 | 去掉表情符号 |
| PHONE_INVALID | 号码非法，或不属于所传 `isoCode` | 否 | 使用国际格式（建议 E.164）；单批仅一个国家，按国家拆批 |
| PRICE_MISSING | 账户未配置该国家 RCS 单价 | 否 | 联系平台开通单价 |
| BALANCE_INSUFFICIENT | 余额不足，无法完成本批预扣 | 否 | 充值后重试；可先调 `/balance` |
| SYSTEM_BUSY | 系统繁忙 | 否（若曾预扣会回退） | 稍后用同一 `clientRef` 重试 |
| INTERNAL_ERROR | 内部处理失败 | 否（预扣已回退） | 用同一 `clientRef` 重试；持续出现联系技术支持 |

### 7.3 其它业务 code

| code | 场景 | 说明 |
| ---- | ---- | ---- |
| `0` | 成功 | 业务数据在 `message` |
| `10020` | 报告查询 | 批次不存在或不属于当前账户（`message` 为文案字符串） |
| `10030` | 发送业务错误 | 见 §7.2 |
| `10000` / `10140` | 鉴权 | 见 §7.1 |

### 7.4 判读伪代码

```text
if httpStatus in (401, 403, 429):
    // 鉴权 / 限流：读 body.errorCode（无 request 字段）
    handleAuthError(body.errorCode)
else if httpStatus == 200:
    if body.code == 0:
        // 成功：读 body.message
        // 若 duplicated=true，messageIds/messages 可能为空
        onSuccess(body.message)
    else if body.code == 10030:
        // 业务拒绝：读 body.message.errorCode / errorMsg
        handleBizError(body.message.errorCode, body.message.errorMsg)
    else if body.code == 10020:
        // 资源不存在（如 report）
        handleNotFound(body.message)
    else:
        handleUnknown(body)
else:
    // 5xx / 网络：用同一 clientRef 重试发送
    retryLater()
```

---

*BoltTel RCS OpenAPI*
