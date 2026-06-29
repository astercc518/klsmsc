# 故障复盘:回执(DLR)处理链路连环故障

- **日期**:2026-06-25
- **系统**:KLSMSC 国际短信网关
- **严重度**:高(批量发送间歇停摆 + 主机CPU打满 + 回执积压41万)
- **状态**:已止血并部署根治补丁;定时发送根治待上线

---

## 一、事件概述

由"单批次发送失败"切入,逐层揭开的**回执处理链路连环故障**。表面是几个发送任务异常,根子是一组**长期潜伏、被高峰流量引爆**的设计缺陷。全程历经两个故障窗口 + 三个潜伏 bug。

最核心的错误假设:**把"至少一次(at-least-once)"的 SMPP 回执当成"恰好一次"处理。**

---

## 二、时间线(本地时间 UTC+8)

| 时间 | 事件 |
|---|---|
| ~17:57 | 批次1254(TS泰国直连/ch82,1.2万)发送,57%送达——上游用非标准 `status=1` 限流拒收3880条 |
| 18:23-18:24 | **worker 崩溃3次**(RabbitMQ `consumer_timeout` 406) |
| 18:28-18:31 | TS上游连接超时 → 网关 **bind 风暴**(会话堆到5个)→ 提交端卡死 |
| 18:24-18:28 | 批次1257-1261 创建后全部卡住(表现为"发送暂停") |
| ~18:50 | **处置:重启网关清会话 + 重启 worker** → 1257/1259/1260 恢复 |
| 22:xx | 发送高峰 → **DLR 被上游约4倍重传** → sms_dlr 积压涨到41万,主机CPU 98%打满 |
| 00:17 | 部署 SETNX 副作用去重 + 注水入队预检 |
| 01:17 | 部署「删除账户清 webhook + 门槛排除已删除账户」 |
| 01:36 | 部署 gosmpp 发送缓冲 1→256 补丁 |

---

## 三、根因分析

### 链1:worker 崩溃 → 批量发送停摆(下午窗口)
TS上游连接超时 → 网关 bind 风暴/会话堆叠 → submit 提交端卡死 → chunk 任务跑超30分钟 → 撞 RabbitMQ `consumer_timeout=1800000ms` → 406 掐断 channel → **整个 Celery worker 崩溃** → 崩溃循环期间所有批量处理停摆。

### 链2:DLR 4倍重传 → 积压 + CPU打满(晚高峰)
gosmpp v0.2.1 的 `transmittable.input` 通道缓冲**仅为1**,且 deliver_sm_resp 由 receivable **读循环同步**经此通道发出 → 高峰出站 submit_sm 占满该1格 → ACK 的 `input<-p` 阻塞、读循环停摆(Submit 错误还被 `_=` 丢弃)→ 上游收不到 ACK 判定丢失 → 对每条 DLR 重传至上限(实测约4次)→ sms_dlr 量×4、worker CPU×4。

> 实测证据:全量日志收到 DeliverSM 60.6万条、唯一ID仅17.6万条(13.3万个ID各被收4次,stat全是DELIVRD=纯重传)。

### 链3:每条 DLR 派生空转任务 → CPU空耗
注水跟进/webhook 入队**无预检**(派发后才在任务内查配置)→ 0注水配置下仍为每条送达消息派生空任务 → ×4重传 → 主 worker 烧4核空转。

### 三个潜伏 bug
- **A. 定时发送 eta 反模式**:`apply_async(eta=)` + `acks_late`,任务挂 worker 内存 unacked;eta>30min 必撞 consumer_timeout 崩 worker;且 `scheduled_at` 不落库、无 beat 兜底,崩了无法恢复。开发者已为 webhook 重试改用 DLX 规避此反模式,定时发送却未跟上。
- **B. DLR 副作用非幂等**:重复回执照常派发 webhook/注水/SMPP转发,无按 message_id 去重。
- **C. 已删除客户 webhook 残留**:软删除不清 `webhook_url`,且门槛 `_account_has_webhook` 不过滤 `is_deleted` → 已删除客户(341/SMSCPRO)仍可能被推送回执。

> 共性:每条链/bug 单独都"看着合理",是**多个隐含假设叠加 + 高峰流量引爆**的涌现型故障。

---

## 四、已部署的修复

| 修复 | 解决 | commit |
|---|---|---|
| SETNX 按 (message_id,终态) 去重 | bug B(确定性兜底,无论重传几次副作用只一次) | `0a8b190` |
| 注水入队预检(仿 webhook) | 链3(0配置不再派生空任务) | `0a8b190` |
| 门槛排除 is_deleted/closed 账户 + 删除时清 webhook_url(2个入口)+ 历史残留清理 | bug C | `0a8b190` |
| **gosmpp 发送缓冲 1→256**(本地 fork) | 链2(从源头减重传) | `4640884` |
| 重启网关清会话 + 重启 worker | 链1(现场恢复) | — |

实测效果:主 worker 4核→0.8%,注水/webhook 空转停止,sms_dlr 积压清零。

---

## 五、处置中的失误(诚实记录)

1. **误判"共用账号"**:把回执洪水归因到"另一套系统共用上游"——其实 ch82 早已独享。错在只读了记忆的过时标题、没读它自己的更新。**教训:记忆是时间点快照,用前要看全、要核实。**
2. **夸大"点击被刷4倍"**:实际0注水配置,根本没真实点击,只是CPU空耗。**教训:下结论前先查实际配置/数据,别从机制直接推断后果。**
3. **一度建议"立刻加 worker-dlr 并发"**:没先看主机CPU(已打满),差点帮倒忙。**教训:容量决策先看资源现状。**

---

## 六、经验教训

1. **回执必须按"至少一次"设计**:所有副作用(状态/计费/注水/webhook/转发)都要幂等去重——这是 SMPP 协议常识,不是可选优化。
2. **长任务/定时任务不能裸挂 RabbitMQ**:consumer_timeout 30min 是硬线;长任务要么分片、要么改 DB+beat 调度。
3. **入队前预检 > 任务内空转**。
4. **删除要清干净副作用配置**:软删除不能只标记,关联外发配置(webhook/注水)必须一并失效。
5. **DB 时间戳≠真实速率,队列深度≠真实工作量**:队列41万其实只有~10万真实回执,靠日志/实时抓流才看清真相。

---

## 七、遗留 / 待办

- [ ] **定时发送根治(eta 反模式)**:加 `scheduled_at` 列 + beat 到点入队(本次正在做)。最高优先级。
- [ ] **网关补丁效果验证**:缓冲 1→256 待**下个高峰**抓日志验证(重传倍数应从 3.43 → ~1)。
- [ ] **ZY_kafa 绑定 EOF**:单通道上游连接问题,需单独查凭据/可达性。
- [ ] **代码推送/合并**:commit 在分支 `fix/dlr-sideeffect-idempotency`,待审后推送。
- [ ] 可选:worker-dlr 处理改批量(降每条事件循环开销)。

---

## 八、相关组件 / 关键文件

- `backend/app/workers/sms_worker.py` — `_process_smpp_dlr_async`(DLR 处理 + 副作用)、`_account_has_webhook/_account_has_water_config`(入队门槛)
- `go-smpp-gateway/third_party/gosmpp/transmittable.go` — 发送缓冲补丁
- `go-smpp-gateway/connector.go` — `handleDeliverSM`、SubmitSMResp 处理
- `backend/app/api/v1/sms.py` — 发送页/定时发送入队
- `backend/app/api/v1/admin.py` — 账户删除(`delete_account_admin` / `delete_business_account`)
