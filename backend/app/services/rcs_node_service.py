"""
节点(nodesms) RCS 群发任务：提交 / 轮询 / 结果回写

把「我们的逐条模型」桥接到「节点的任务模型」：

    一个分片(commit_batch) ──> 一个号码 TXT ──> 一个群发任务(sn)
                                                    │
                          beat 轮询 getTask ────────┘
                                    │ 终态
                          getFile ──┴──> 逐条回写 sms_logs

两个上游限制直接决定了这里的取舍：

  1. **整批同文案**。节点只有一个 content.text（variable 是随机替换，不是一号一文案），
     所以分片内文案不一致时必须整片拒绝 —— 否则部分客户会收到别人的文案。
  2. **没有逐条回执**。状态只能等任务终态后下载结果文件；因此提交后 sms_logs 记 sent，
     真正的成功/失败由结果文件决定。
"""
import re
from datetime import datetime
from typing import Iterable, List, Optional, Tuple

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.sms.channel import Channel
from app.modules.sms.rcs_task import RCSNumberFile, RCSSendTask
from app.modules.sms.sms_log import SMSLog
from app.services.rcs_number_file import create_number_file, public_url, purge_file
from app.utils.logger import get_logger

logger = get_logger(__name__)


class NodeBatchRejected(Exception):
    """整批无法提交（文案不一致、配置缺失等），调用方需退款并标失败。"""


def _order_id(batch_id: Optional[int], chunk_key: str) -> str:
    """商户订单号：上游要求全局唯一、≤64、字母数字下划线。

    带上 batch/分片键便于人工对账 —— 709「订单号已存在」时上游不返回原 sn，
    只能靠这个串回到我们自己的批次上查。
    """
    raw = f"KL_{batch_id or 0}_{chunk_key}"
    return re.sub(r"[^A-Za-z0-9_]", "", raw)[:64]


def _uniform_text(logs: List[SMSLog]) -> str:
    """取整批统一文案；不一致直接拒绝（节点无法一号一文案）。"""
    texts = {(l.message or "") for l in logs}
    if len(texts) > 1:
        raise NodeBatchRejected(
            f"节点 RCS 要求整批同文案，本片有 {len(texts)} 种不同文案"
            f"（模板变量/多文案批次请改用逐条通道）"
        )
    return texts.pop() if texts else ""


async def submit_task(
    db: AsyncSession,
    channel: Channel,
    logs: List[SMSLog],
    batch_id: Optional[int],
    account_id: Optional[int],
    chunk_key: str,
) -> RCSSendTask:
    """把一片消息提交成一个节点群发任务。成功返回已 accepted 的任务行。

    调用方负责：提交失败时退款 + 标记 sms_logs 失败。
    """
    from app.workers.adapters.node_rcs_adapter import NodeRCSAdapter, NodeRCSConfigError

    if not logs:
        raise NodeBatchRejected("空分片")

    text = _uniform_text(logs)
    country = (logs[0].country_code or "").strip().upper()
    order_id = _order_id(batch_id, chunk_key)

    # 号码文件必须先落库并 commit：上游可能在 createTask 返回前就来拉
    num_file: RCSNumberFile = await create_number_file(
        db,
        [l.phone_number for l in logs],
        channel_id=channel.id,
        batch_id=batch_id,
    )
    task = RCSSendTask(
        channel_id=channel.id,
        batch_id=batch_id,
        account_id=account_id,
        order_id=order_id,
        country_code=country,
        number_file_id=num_file.id,
        phone_count=num_file.phone_count,
        state=RCSSendTask.STATE_CREATED,
    )
    db.add(task)
    await db.commit()

    adapter = NodeRCSAdapter(channel)
    cfg = channel.get_rcs_config()
    thumbnail = (cfg.get("thumbnail") or "").strip() or None
    try:
        result = await adapter.create_send_task(
            order_id=order_id,
            country_code=country,
            number_url=public_url(num_file.token),
            text=text,
            thumbnail=thumbnail,
        )
    except NodeRCSConfigError as e:
        task.state = RCSSendTask.STATE_FAILED
        task.error = str(e)[:500]
        await db.commit()
        raise NodeBatchRejected(str(e))

    task.category = adapter.build_create_payload(
        order_id=order_id, country_code=country, number_url="x", text=text, thumbnail=thumbnail
    )["category"]

    if not result.success:
        task.state = RCSSendTask.STATE_FAILED
        task.error = f"code={result.code} {result.error}"[:500]
        await db.commit()
        # 号码已经没用了，别把它继续挂在公网上
        await purge_file(db, num_file.id, reason="create_failed")
        await db.commit()
        raise NodeBatchRejected(result.error or "节点任务创建失败")

    sn = (result.data or {}).get("sn") if isinstance(result.data, dict) else None
    task.sn = str(sn) if sn else None
    task.state = RCSSendTask.STATE_ACCEPTED
    await db.commit()

    if not task.sn:
        # 受理成功却没给 sn：无法轮询，只能人工去上游后台找这个 orderId
        logger.error(
            f"节点 RCS 任务受理成功但未返回 sn: order_id={order_id} batch={batch_id}，"
            f"该任务无法自动轮询，需人工核查"
        )
    return task


# ── 轮询 ────────────────────────────────────────────────────────────────────


async def poll_task(db: AsyncSession, task: RCSSendTask, channel: Channel) -> bool:
    """查一次任务状态，落库。返回 True 表示已进入上游终态。"""
    from app.workers.adapters.node_rcs_adapter import (
        TASK_STATUS,
        TASK_STATUS_FINAL,
        NodeRCSAdapter,
    )

    if not task.sn:
        return False

    result = await NodeRCSAdapter(channel).get_send_task(task.sn)
    task.last_polled_at = datetime.now()
    task.poll_count = (task.poll_count or 0) + 1

    if not result.success:
        task.error = f"poll: code={result.code} {result.error}"[:500]
        await db.commit()
        return False

    data = result.data if isinstance(result.data, dict) else {}
    status = data.get("status")
    try:
        status = int(status)
    except (TypeError, ValueError):
        status = None

    task.status = status
    task.sum_count = int(data.get("sum") or 0)
    task.submit_num = int(data.get("submitNum") or 0)
    task.total_num = int(data.get("totalNum") or 0)
    task.send_time = data.get("sendTime") or None
    task.finish_time = data.get("finishTime") or None

    is_final = status in TASK_STATUS_FINAL
    task.state = RCSSendTask.STATE_FINAL if is_final else RCSSendTask.STATE_RUNNING
    await db.commit()

    logger.info(
        f"节点 RCS 任务轮询: sn={task.sn} status={status}({TASK_STATUS.get(status, '?')}) "
        f"sum={task.sum_count} submit={task.submit_num} total={task.total_num} 终态={is_final}"
    )
    if is_final and task.number_file_id:
        # 上游已经不需要号码文件了，立刻从公网撤下
        await purge_file(db, task.number_file_id, reason="task_final")
        await db.commit()
    return is_final


# ── 结果回写 ─────────────────────────────────────────────────────────────────

# 结果 TXT 的列语义文档没写。这里做保守的自适应解析：能明确判出成功/失败语义才回写，
# 否则只存档 + 告警，绝不瞎猜 —— 猜错会把没送达的记成送达，直接污染送达率与计费口径。
_OK_WORDS = ("成功", "已送达", "送达", "delivered", "success", "ok", "read")
_FAIL_WORDS = ("失败", "未送达", "不可达", "拒绝", "过期", "failed", "fail", "undeliver", "reject", "expired")
_PHONE_RE = re.compile(r"^\+?\d{6,20}$")


def parse_result_text(text: str) -> Tuple[dict, Optional[str]]:
    """解析结果文件，返回 ({号码: True/False}, 无法解析时的说明)。

    识别得出状态列 → 回写；只有号码没有状态 → 返回空 dict + 说明（调用方不改状态）。
    """
    mapping: dict = {}
    only_phone_lines = 0
    parsed_lines = 0

    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # 分隔符含空白：结果文件用空格分列也很常见（"号码 送达"）。
        # 状态文本自身带空格不受影响 —— 下面会把 parts[1:] 重新拼回一句再匹配。
        parts = [p.strip() for p in re.split(r"[,;|\s]+", line) if p.strip()]
        if not parts:
            continue
        phone = parts[0]
        if not _PHONE_RE.match(phone):
            continue
        if len(parts) == 1:
            only_phone_lines += 1
            continue
        rest = " ".join(parts[1:]).lower()
        # 必须先判失败：失败词往往把成功词整个包住（「未送达」⊃「送达」、
        # undelivered ⊃ delivered），反过来判会把没送达的记成已送达。
        if any(w in rest for w in _FAIL_WORDS):
            mapping[phone] = False
            parsed_lines += 1
        elif any(w in rest for w in _OK_WORDS):
            mapping[phone] = True
            parsed_lines += 1

    if not mapping:
        return {}, (
            f"结果文件未能识别状态列（可解析号码行 {only_phone_lines} 条）；"
            f"已跳过回写，需人工确认格式后再启用"
        )
    return mapping, None


async def apply_result(db: AsyncSession, task: RCSSendTask, channel: Channel) -> int:
    """下载结果文件并回写 sms_logs。返回被改写的条数。"""
    from app.workers.adapters.node_rcs_adapter import NodeRCSAdapter

    adapter = NodeRCSAdapter(channel)
    if not task.result_url:
        res = await adapter.get_send_file(task.sn)
        if not res.success:
            task.error = f"getFile: code={res.code} {res.error}"[:500]
            await db.commit()
            return 0
        url = (res.data or {}).get("url") if isinstance(res.data, dict) else None
        if not url:
            task.result_note = "getFile 未返回 url"
            await db.commit()
            return 0
        task.result_url = str(url)[:500]
        task.result_fetched_at = datetime.now()
        await db.commit()

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(task.result_url)
        if resp.status_code != 200:
            task.error = f"结果文件下载 HTTP {resp.status_code}"[:500]
            await db.commit()
            return 0
        text = resp.text
    except Exception as e:
        task.error = f"结果文件下载失败: {e}"[:500]
        await db.commit()
        return 0

    mapping, note = parse_result_text(text)
    if note:
        logger.error(
            f"节点 RCS 结果文件无法识别状态: sn={task.sn} batch={task.batch_id} "
            f"url={task.result_url} 前200字符={text[:200]!r}"
        )
        task.result_note = note[:500]
        task.state = RCSSendTask.STATE_APPLIED
        task.result_applied_at = datetime.now()
        await db.commit()
        return 0

    changed = 0
    for phone, ok in mapping.items():
        variants = {phone, phone.lstrip("+"), "+" + phone.lstrip("+")}
        conds = [
            SMSLog.channel_id == task.channel_id,
            SMSLog.phone_number.in_(list(variants)),
            SMSLog.status.in_(["sent", "queued", "pending"]),
        ]
        if task.batch_id:
            conds.append(SMSLog.batch_id == task.batch_id)
        values = (
            {"status": "delivered", "delivery_time": datetime.now()}
            if ok
            else {"status": "failed", "error_message": "上游结果文件标记为失败"}
        )
        r = await db.execute(update(SMSLog).where(*conds).values(**values))
        changed += r.rowcount or 0
    await db.commit()

    task.state = RCSSendTask.STATE_APPLIED
    task.result_applied_at = datetime.now()
    task.result_note = f"回写 {changed} 条（结果文件 {len(mapping)} 行）"[:500]
    await db.commit()

    if task.batch_id:
        try:
            from app.modules.sms.batch_utils import update_batch_progress

            await update_batch_progress(db, task.batch_id)
        except Exception as e:
            logger.warning(f"节点 RCS 回写后更新批次进度失败: batch={task.batch_id}, {e}")

    logger.info(
        f"节点 RCS 结果已回写: sn={task.sn} batch={task.batch_id} "
        f"结果行={len(mapping)} 实际改写={changed}"
    )
    return changed


async def pending_tasks(db: AsyncSession, limit: int = 100) -> List[RCSSendTask]:
    """待轮询/待取结果的任务。"""
    res = await db.execute(
        select(RCSSendTask)
        .where(
            RCSSendTask.state.in_(
                [
                    RCSSendTask.STATE_ACCEPTED,
                    RCSSendTask.STATE_RUNNING,
                    RCSSendTask.STATE_FINAL,
                ]
            ),
            RCSSendTask.sn.isnot(None),
        )
        # MySQL 不支持 NULLS FIRST，但它的 ASC 本就把 NULL 排在最前 ——
        # 正好是我们要的：从没轮询过的任务优先。
        .order_by(RCSSendTask.last_polled_at.asc())
        .limit(limit)
    )
    return list(res.scalars().all())
