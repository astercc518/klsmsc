"""
通道长信编码风险巡检 (Channel Encoding Inspector)

排查"长短信走 message_payload TLV、被 TLV-blind 上游静默丢内容 → 上游/手机收到空白"的隐患。

背景：message_payload(0x0424 TLV) 被不读 TLV 的上游忽略时，上游仍回 status=0、DLR 仍
delivered——从我们这侧的发送状态**完全看不出空白**。唯一被动可观测信号是「该通道正在用
message_payload 发长信」。本任务定期扫描活跃通道，把这类通道列出来告警，防止新开/改回的
通道再次踩 TLV 坑（如 TS_zhilian/BAXI_TEST 已实证）。

注意：本任务只做**风险筛查**，不能确认空白；确认须金丝雀实测(发短+长对照看收件)。
确认 TLV-blind 后，把该通道 config_json 设 {"long_message_mode":"udh_segmentation"} 修复
(UCS-2 UDH 分段，esm_class 已修)。阈值/窗口可用环境变量覆盖。
"""
import os
from sqlalchemy import text
from app.workers.celery_app import celery_app
from app.workers.sms_worker import _make_session, _run_async
from app.services.notification_service import notification_service
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 近 N 小时窗口内，单活跃通道走 message_payload 的长信(>127 UCS-2 字符)数 ≥ 阈值即告警。
# 窗口默认 72h：通道发送多为突发(如 KL_888_GJ 单波数万、随后数日沉寂)，窗口须显著宽于每日
# 巡检周期才不漏突发；修复(切 udh_segmentation)后该通道自然从告警消失。
_WINDOW_HOURS = int(os.environ.get("CHAN_ENC_INSPECT_WINDOW_HOURS", "72"))
_ALERT_THRESHOLD = int(os.environ.get("CHAN_ENC_INSPECT_THRESHOLD", "50"))


@celery_app.task(name='inspect_channel_encoding_risk_task')
def inspect_channel_encoding_risk_task():
    """每日扫描：走 message_payload 发长信的活跃通道(空白隐患)，超阈值告警管理员群。"""
    return _run_async(_do_inspect())


async def _do_inspect():
    eng, Session = _make_session()
    try:
        async with Session() as db:
            rows = (await db.execute(
                text(
                    """
                    SELECT c.channel_code AS code, COUNT(*) AS long_cnt
                      FROM sms_logs l JOIN channels c ON c.id = l.channel_id
                     WHERE l.submit_time > NOW() - INTERVAL :hrs HOUR
                       AND CHAR_LENGTH(l.message) > 127
                       AND c.status = 'active'
                       AND (c.config_json IS NULL
                            OR (c.config_json NOT LIKE '%udh_segmentation%'
                                AND c.config_json NOT LIKE '%latin1_single%'
                                AND c.config_json NOT LIKE '%"gsm7_enabled": true%'))
                     GROUP BY c.channel_code
                    HAVING long_cnt >= :thr
                     ORDER BY long_cnt DESC
                    """
                ),
                {"hrs": _WINDOW_HOURS, "thr": _ALERT_THRESHOLD},
            )).all()

        if not rows:
            logger.info("通道编码巡检：近 %dh 无 message_payload 长信风险通道", _WINDOW_HOURS)
            return {"risk_channels": 0}

        detail = [(r.code, int(r.long_cnt)) for r in rows]
        lines = "\n".join(f"• `{code}`: {cnt} 条" for code, cnt in detail)
        msg = (
            "⚠️ *长信编码风险巡检*\n"
            f"近 {_WINDOW_HOURS}h 内，以下活跃通道用 message_payload 发长信(>127字)，"
            "若上游不读 TLV 会收到*空白*：\n\n"
            f"{lines}\n\n"
            "确认：对每条通道发短+长对照金丝雀；确认空白后切 "
            "`long_message_mode=udh_segmentation`。"
        )
        logger.warning("通道编码巡检风险通道: %s", detail)
        try:
            await notification_service.notify_admin_group(msg)
        except Exception as e:  # 告警失败不影响巡检本身
            logger.error("通道编码巡检告警发送失败: %s", e)
        return {"risk_channels": len(detail), "detail": detail}
    finally:
        await eng.dispose()
