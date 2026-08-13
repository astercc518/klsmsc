# RCS 群发 —— 节点(nodesms) 对接说明

源文档：`img.nodesms.com/doc/group_api.pdf`（注意：该 PDF 页树被截断成 8 页，实际有 28 页，
用能按页渲染的工具指定 9–28 页才能读到群发部分）。

## 1. 与叮咚的根本差异

| | 叮咚 BoltTel | 节点 nodesms |
|---|---|---|
| 提交粒度 | **逐条**（一次一个号码） | **整批**（号码是一个公网 TXT 文件的 URL） |
| 上游标识 | 每条一个 `messageId` | 整个任务一个 `sn` |
| 状态获取 | **Webhook 推终态**，逐条 | **轮询** `getTask`，只有聚合计数 |
| 逐条结果 | 回执里带 | 任务完成后 `getFile` 下载 TXT |
| 文案 | 纯文本 ≤160 字符、禁 emoji | 文本 + 可选图片(图文)、支持 `${var}` 随机变量 |
| 计费 | 受理预扣 → 失败退回 | 按任务结算（`sum`/`submitNum`/`totalNum`） |

**这意味着节点无法复用现有的 `send_one(sms_log)` 逐条链路。**
适配器的 `send_one` 会直接抛错 —— 故意的：若有人把 vendor=node 的通道挂到逐条发送链路上，
必须立刻炸出来，而不是把消息悄悄丢掉或误计费。

## 2. 接口一览

BASE = `https://apip.nodesms.com`

| 用途 | 方法 | URL |
|---|---|---|
| 创建群发任务 | POST | `/api/send/createTask` |
| 查任务状态 | POST | `/api/send/getTask` |
| 结果文件(TXT) | POST | `/api/send/getFile` |
| 撤销 / 暂停 / 恢复 / 中断 | POST | `/api/send/revoke` `/pause` `/recover` `/interrupt` |
| 改文案 | POST | `/api/send/updateTask` |
| 群发余量 | GET | `/api/send/getValNumByShortCode` |
| 号码筛选（数据业务，非发送） | POST | `/api/filter/createTask` `/getTask` `/cancelTask` `/getFile` |

### 鉴权

```
Header: Content-Type: application/json;charset=utf-8
        X-Signature: BASE64(HMAC_SHA256(secret, bodyJson))
```

对应文档里的 PHP：`base64_encode(hash_hmac('sha256', $dataJson, $secret, true))`。
与叮咚同一个坑：**签名的字节必须与实际发出的 body 完全一致**，先 dumps 成 bytes 再发，
不能交给 HTTP 库重新序列化。

`secret` 只参与签名、不进 body（各接口参数表里都只有 `account`；§公共请求参数那张表把
account/secret 并列是笼统写法）。**若上游回 710/711，优先复核这个判断。**

### 创建任务报文

```json
{
  "account": "c", "productId": "100000172", "orderId": "11111",
  "business": "RCS", "category": "RCS_Text",
  "countryCode": "BR",
  "numberUrl": "https://.../100078_全部有效1752649794.txt",
  "content": { "text": "1232", "isFilter": 2, "thumbnail": "https://img.../x.jpg" },
  "variable": ["https://xxx.xx", "https://yyy.yy"]
}
```

- `category`：`RCS_Text` 纯文本 / `RCS_ImgText` 图文（适配器按有无 `thumbnail` 自动选）
- `thumbnail`：**≤40KB**、jpg/png、完整地址，且**仅自研 RCS 图文支持**，用前须与供应商确认；
  格式不符会「提交成功但发送失败」
- `isFilter`：1=直接发送，2=先筛选再发送（文档参数表把它列在外层，但请求示例放在 `content`
  内部 —— 示例是实际报文，适配器按示例走）
- `variable`：随机变量，一条消息只支持一个，用 `${var}` 在 text 里占位
- `orderId`：≤64 字符，字母数字下划线，**全局唯一**

### 任务状态（`getTask.status`）

```
0 等待审核   1 待开始   2 筛选中   3 群发中   4 已取消   5 已完成
6 结算中     7 已拒绝   8 失败     9 中断     10 暂停    11 撤单
```

终态（停止轮询）：`4, 5, 7, 8, 11`。注意 **9 中断 / 10 暂停不是终态** —— 中断任务的终态是
「任务完成」，只是发送量变少。

## 3. 错误码

| code | 含义 | 可重投 |
|---|---|---|
| 200 | 成功 | — |
| 400 | 无权操作 | 否 |
| 402 | 参数值不对 | 否 |
| 404 | 目标不存在或已删除 | 否 |
| 405 / 601 | 系统错误 / 请稍后再试 | **是** |
| 701 | 余额不足 | 否 |
| 702 / 703 / 704 / 707 | 产品未配价 / 产品不存在 / 通道不存在 / 通道已关闭 | 否 |
| 705 | 文件错误 | 否 |
| 706 | 国家错误 | 否 |
| 708 | 扣费失败 | 否 |
| **709** | **订单号已存在** | **绝对不能重试** |
| 710 / 711 | 认证失败 / 验签失败 | 否 |
| 799 | 未知错误 | 否 |

> **709 是最需要小心的一个**：它说明上游已经受理过这个 orderId，但响应里**不返回原 sn**，
> 而节点又没有「按 orderId 反查任务」的接口 —— 也就是说这单发没发、发了多少，接口层面查不到，
> 只能人工核查。所以 709 必须停下来告警，绝不能自动重试。

## 4. 接入实现

```
批量发送分片 ──> 号码 TXT(带高熵 token 的临时 URL) ──> createTask ──> sn
                                                                  │
                       beat 每 2 分钟 poll_rcs_node_tasks_task ────┘
                                     │ 落终态
                       getFile ──────┴──> 解析 ──> 回写 sms_logs ──> 批次进度
```

| 组件 | 位置 |
|---|---|
| API 客户端 | `workers/adapters/node_rcs_adapter.py` |
| 任务服务（提交/轮询/回写） | `services/rcs_node_service.py` |
| 号码文件服务 | `services/rcs_number_file.py` |
| 号码下载端点 | `GET /api/v1/rcs/numbers/{token}.txt` |
| 轮询任务 | `workers/rcs_node_worker.py`（beat 2 分钟；清理任务 1 小时） |
| 发送接入点 | `batch_worker._queue_commit_batch_node_rcs` |
| 两张表 | `rcs_number_files` / `rcs_send_tasks` |

### 号码文件的安全处理

号码要放到公网供上游拉取，这是整个接入最大的风险点，所以：

- token 用 `secrets.token_urlsafe(32)`（≈256 bit），路径本身即凭据，不可枚举
- 默认 48 小时过期（上游可能排队/审核后才拉，太短会导致整批发不出去）
- **任务一进终态立刻清空内容**，不等过期；另有每小时兜底清理过期件
- 过期/已清空一律 410，不存在 404；每次下载记录次数/时间/来源 IP，可事后审计
- 不做 IP 白名单：上游拉取源 IP 未知且可能变动，误拦会让整批任务静默发不出去

### 两条硬限制（都在入口拦截）

1. **只支持批量**。单条发送（`/sms/send`）在提交入口就返回 `CHANNEL_BATCH_ONLY`，
   不会走到适配器才失败。
2. **整批同文案**。节点一个任务只有一份 `content.text`（`variable` 是随机替换，不是
   一号一文案），分片内文案不一致会整片拒绝 + 退款，否则部分客户会收到别人的文案。

### 结果文件解析

文档没有写结果 TXT 的列格式，所以做的是**保守自适应**：识别得出「号码 + 状态」两列才回写，
只有号码没有状态时**只存档告警、不改任何状态** —— 猜错会把没送达的记成送达，直接污染送达率
和计费口径。

已覆盖的格式：`,` `;` `|` 制表符 空格 分隔；中英文状态词。
**判失败在判成功之前** —— 失败词往往把成功词整个包住（「未送达」⊃「送达」、
`undelivered` ⊃ `delivered`），反过来判会把未达记成已达。

首次真实跑通后，务必人工核对一次 `rcs_send_tasks.result_note`：若显示「未能识别状态列」，
把实际文件格式补进 `parse_result_text` 再启用回写。

### 尚未处理

- **709「订单号已存在」**：上游不返回原 sn 且无法按 orderId 反查，目前只记 error 不自动重试，
  需人工核查。orderId 形如 `KL_{batch_id}_{分片键}`，可据此回到我们的批次。
- 受理成功但未返回 sn 的任务无法轮询，只能人工去上游后台按 orderId 找。
- 暂停/恢复/中断/改文案等运维接口适配器已实现，但还没接后台按钮。

## 5. 通道配置

协议选 **HTTP**，接口类型选 **RCS - 节点**（写入 `config_json.rcs.vendor='node'`）：

| 表单项 | 落库位置 | 说明 |
|---|---|---|
| 接口地址 | `channels.api_url` | 留空则用默认 `https://apip.nodesms.com` |
| 用户名 | `channels.username` | = `account` |
| 密码 | `channels.password` | = `secret`（仅签名用，不进 body） |
| — | `config_json.rcs.product_id` | **节点特有**，决定线路与单价，必填 |
