"""
SMPP Go 网关入队负载：携带全量发送字段，避免网关在发送路径读库。
"""


def smpp_payload_public_dict_from_row(
    log_id: int,
    message_id: str,
    phone_number: str,
    message: str,
    channel_id: int,
    record_status: str,
    batch_status: str = "",
) -> dict:
    """
    将 Core 查询行 / 原生字段转为投递 sms_send_smpp 的 JSON（与 Go 侧 SMSLogData 对齐）。
    避免 Worker 侧构造 SMSLog ORM 仅用于组负载。
    """
    bs = getattr(batch_status, "value", batch_status) if batch_status is not None else ""
    st = getattr(record_status, "value", record_status) or ""
    return {
        "log_id": int(log_id),
        "message_id": message_id or "",
        "phone_number": phone_number or "",
        "message": message or "",
        "channel_id": int(channel_id or 0),
        "batch_status": str(bs or ""),
        "record_status": str(st),
    }


def smpp_payload_public_dict(sms_log, batch_status: str = "") -> dict:
    """
    将 ORM 行转为投递 sms_send_smpp 的 JSON 对象（与 Go 侧 SMSLogData 对齐）。

    Args:
        sms_log: SMSLog 实例（须已 flush 得到 id）
        batch_status: 关联批次状态快照（取消时网关不写库，仅回报失败）
    """
    st = getattr(sms_log.status, "value", sms_log.status) or ""
    bs = getattr(batch_status, "value", batch_status) if batch_status is not None else ""
    return smpp_payload_public_dict_from_row(
        int(sms_log.id),
        sms_log.message_id,
        sms_log.phone_number or "",
        sms_log.message or "",
        int(sms_log.channel_id or 0),
        st,
        bs,
    )
