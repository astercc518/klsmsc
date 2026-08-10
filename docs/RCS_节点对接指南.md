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

## 4. 接入现状与待办

**已完成**：`backend/app/workers/adapters/node_rcs_adapter.py` —— 完整的任务级 API 客户端
（签名、创建/查询/取消/暂停/恢复/中断/改文案/结果文件/余量、错误码映射）。
通道「检测」可用：`get_balance()` 映射到群发余量查询，一次调用即可验证地址可达 +
account/secret + 签名算法。

**未完成**（把它接进发送链路还缺三块）：

1. **号码文件的公网 URL**。节点要求 `numberUrl` 指向一个每行一个号码的 TXT。
   我们得把批次号码落盘并暴露成公网可下载的地址 —— 这是**客户号码库外泄的风险点**，
   必须随机长 token 路径 + 短 TTL + 任务受理后即删，不能用可枚举的路径。
2. **任务轮询 worker**。beat 定时对在途任务调 `getTask`，直到落入终态。
3. **结果回写**。终态后 `getFile` 下载 TXT，逐条回写 `sms_logs`，再结算批次。

另外要定的产品问题：我们的一个批次 = 节点的一个任务，那么**客户侧单条发送**（`/sms/send`
发一条）怎么处理？一号一任务在任务制下开销极大，可能需要限制 RCS-节点通道只走批量。

## 5. 通道配置

协议选 **HTTP**，接口类型选 **RCS - 节点**（写入 `config_json.rcs.vendor='node'`）：

| 表单项 | 落库位置 | 说明 |
|---|---|---|
| 接口地址 | `channels.api_url` | 留空则用默认 `https://apip.nodesms.com` |
| 用户名 | `channels.username` | = `account` |
| 密码 | `channels.password` | = `secret`（仅签名用，不进 body） |
| — | `config_json.rcs.product_id` | **节点特有**，决定线路与单价，必填 |
