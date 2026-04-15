"""
DLR (Delivery Report) 统一处理模块

支持多种上游通道的 DLR 格式：
- 推送模式 (Push): 上游主动回调通知
- 拉取模式 (Pull): 主动去上游查询报告

支持的数据格式：
- JSON
- XML
- Form (键值对)
"""
import re
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any
from enum import Enum
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.sms.sms_log import SMSLog
from app.utils.logger import get_logger

logger = get_logger(__name__)


class DLRStatus(Enum):
    """DLR 状态枚举"""
    DELIVERED = "delivered"      # 已送达
    FAILED = "failed"            # 失败
    EXPIRED = "expired"          # 过期
    REJECTED = "rejected"        # 拒绝
    UNKNOWN = "unknown"          # 未知
    PENDING = "pending"          # 等待中


# 常见的送达成功状态码/关键词（含 Kaola 等上游的 DELIVRD、DELIVRD 000 等）
DELIVERED_CODES = {
    # 数字状态码（2/11/20 等仅在下文 isdigit 分支处理，便于在含失败关键词的 error 字段时先判失败）
    '0', '1', '10', '100', '200',
    # 字符串状态
    'delivrd', 'delivered', 'success', 'ok', 'sent', 'accepted',
    'deliveredtonetwork', 'deliveredtoterminal', 'sm_deliveredtomob',
    'dlvrd', 'submitted', 'receive', 'received',
}

# 常见的失败状态码/关键词
FAILED_CODES = {
    # 字符串状态
    'undeliv', 'undelivered', 'failed', 'rejected', 'rejectd', 'error',
    'expired', 'unknown', 'absent', 'blocked', 'invalid', 'notexist',
    'blacklist', 'spam', 'denied', 'unreachable', 'busy', 'noroute',
}


def normalize_status(status_code: Any, error_code: str = '') -> DLRStatus:
    """
    标准化 DLR 状态
    
    Args:
        status_code: 状态码（数字或字符串）
        error_code: 错误码/描述
        
    Returns:
        标准化的 DLRStatus
    """
    # 转为小写字符串
    status_str = str(status_code).lower().strip() if status_code is not None else ''
    error_str = str(error_code).lower().strip() if error_code else ''

    # 失败关键词优先，避免与「数字成功码」或模糊文案冲突
    for failed_code in FAILED_CODES:
        if failed_code in status_str or failed_code in error_str:
            return DLRStatus.FAILED

    # 明确送达（SMPP 风格）
    if 'delivrd' in status_str or 'delivrd' in error_str:
        return DLRStatus.DELIVERED

    if status_str in DELIVERED_CODES or error_str in DELIVERED_CODES:
        return DLRStatus.DELIVERED

    # 纯数字状态码
    if status_str.isdigit():
        code = int(status_str)
        # 多家 HTTP report 用 2/11/20 等表示已送达或流程成功
        if code in [0, 1, 2, 10, 11, 20, 100, 200]:
            return DLRStatus.DELIVERED
        if code < 0 or code > 1000:
            return DLRStatus.FAILED

    return DLRStatus.UNKNOWN


def _dlr_upstream_id_candidates(raw: Any) -> List[str]:
    """
    生成可与 SMSLog.upstream_message_id 匹配的候选 ID（与 SMPP deliver_sm 侧逻辑对齐）。
    解决 DLR 回传大小写、十六进制/十进制变体等与入库值不完全一致时「找不到记录」的问题。
    """
    s = str(raw).strip() if raw is not None else ""
    if not s:
        return []
    candidates = [s]
    if any(c in s.upper() for c in "ABCDEF"):
        candidates.append(s.upper())
        candidates.append(s.lower())
    try:
        if s.startswith("0x") or s.startswith("0X"):
            candidates.append(str(int(s, 16)))
        elif s.isdigit():
            candidates.append(hex(int(s)))
        elif len(s) >= 2 and all(c in "0123456789abcdefABCDEF" for c in s):
            candidates.append(str(int(s, 16)))
    except (ValueError, TypeError):
        pass
    # 去重保序
    return list(dict.fromkeys(candidates))


def parse_json_dlr(data: Dict) -> List[Dict]:
    """
    解析 JSON 格式的 DLR
    
    支持多种 JSON 格式：
    1. Kaola JSON: {"status":0, "list":[{"mid":"xxx", "mobile":"xxx", "result":0}]}
    2. 简单格式: {"mid":"xxx", "status":"delivered"}
    3. 批量格式: [{"mid":"xxx", "status":"delivered"}, ...]
    """
    reports = []
    
    try:
        # 格式1: 包含 list 字段
        if 'list' in data:
            for item in data.get('list', []):
                report = {
                    'message_id': (
                        item.get('mid') or item.get('message_id') or item.get('msgid')
                        or item.get('taskid') or item.get('smsid') or item.get('sms_id')
                        or item.get('sm_id')
                    ),
                    'mobile': item.get('mobile') or item.get('phone') or item.get('to'),
                    'status_code': item.get('result') or item.get('status') or item.get('state'),
                    'error_code': item.get('errorcode') or item.get('error') or item.get('desc'),
                    'delivery_time': item.get('recvTime') or item.get('deliverytime') or item.get('time'),
                }
                if report['message_id']:
                    reports.append(report)
        
        # 格式2: 数组格式
        elif isinstance(data, list):
            for item in data:
                report = {
                    'message_id': (
                        item.get('mid') or item.get('message_id') or item.get('msgid')
                        or item.get('taskid') or item.get('smsid') or item.get('sms_id')
                    ),
                    'mobile': item.get('mobile') or item.get('phone'),
                    'status_code': item.get('result') or item.get('status'),
                    'error_code': item.get('errorcode') or item.get('error'),
                    'delivery_time': item.get('recvTime') or item.get('deliverytime'),
                }
                if report['message_id']:
                    reports.append(report)
        
        # 格式3: 单个报告
        else:
            message_id = (
                data.get('mid') or data.get('message_id') or data.get('msgid')
                or data.get('taskid') or data.get('id') or data.get('smsid')
                or data.get('sms_id') or data.get('sm_id')
            )
            if message_id:
                reports.append({
                    'message_id': message_id,
                    'mobile': data.get('mobile') or data.get('phone') or data.get('to'),
                    'status_code': data.get('result') or data.get('status') or data.get('state'),
                    'error_code': data.get('errorcode') or data.get('error') or data.get('desc'),
                    'delivery_time': data.get('recvTime') or data.get('deliverytime') or data.get('time'),
                })
    
    except Exception as e:
        logger.warning(f"解析 JSON DLR 失败: {e}")
    
    return reports


def parse_xml_dlr(xml_text: str) -> List[Dict]:
    """
    解析 XML 格式的 DLR
    
    支持多种 XML 格式：
    1. Kaola XML: <returnsms><statusbox><mobile>xxx</mobile><taskid>xxx</taskid><status>10</status><errorcode>DELIVRD</errorcode></statusbox></returnsms>
    2. 通用格式: <dlr><report mid="xxx" status="delivered"/></dlr>
    """
    reports = []
    
    try:
        # 格式1: Kaola statusbox 格式
        statusbox_pattern = r'<statusbox>(.*?)</statusbox>'
        statusboxes = re.findall(statusbox_pattern, xml_text, re.DOTALL | re.IGNORECASE)
        
        for statusbox in statusboxes:
            mobile = _extract_xml_value(statusbox, 'mobile')
            message_id = (_extract_xml_value(statusbox, 'taskid') or 
                         _extract_xml_value(statusbox, 'mid') or
                         _extract_xml_value(statusbox, 'msgid') or
                         _extract_xml_value(statusbox, 'messageid'))
            status_code = _extract_xml_value(statusbox, 'status')
            error_code = _extract_xml_value(statusbox, 'errorcode')
            recv_time = (_extract_xml_value(statusbox, 'receivetime') or 
                        _extract_xml_value(statusbox, 'recvtime') or
                        _extract_xml_value(statusbox, 'deliverytime'))
            
            if message_id:
                reports.append({
                    'message_id': message_id,
                    'mobile': mobile,
                    'status_code': status_code,
                    'error_code': error_code,
                    'delivery_time': recv_time,
                })
        
        # 格式2: report 标签格式
        if not reports:
            report_pattern = r'<report\s+([^>]+)/?>(?:</report>)?'
            report_matches = re.findall(report_pattern, xml_text, re.IGNORECASE)
            
            for attrs in report_matches:
                message_id = _extract_xml_attr(attrs, 'mid') or _extract_xml_attr(attrs, 'msgid')
                status_code = _extract_xml_attr(attrs, 'status') or _extract_xml_attr(attrs, 'state')
                mobile = _extract_xml_attr(attrs, 'mobile') or _extract_xml_attr(attrs, 'to')
                error_code = _extract_xml_attr(attrs, 'error') or _extract_xml_attr(attrs, 'desc')
                
                if message_id:
                    reports.append({
                        'message_id': message_id,
                        'mobile': mobile,
                        'status_code': status_code,
                        'error_code': error_code,
                        'delivery_time': None,
                    })
        
        # 格式3: 简单的元素列表
        if not reports:
            # 尝试提取 <message> 或 <sms> 块
            for tag in ['message', 'sms', 'dlr', 'delivery']:
                block_pattern = rf'<{tag}>(.*?)</{tag}>'
                blocks = re.findall(block_pattern, xml_text, re.DOTALL | re.IGNORECASE)
                
                for block in blocks:
                    message_id = (_extract_xml_value(block, 'mid') or 
                                 _extract_xml_value(block, 'msgid') or
                                 _extract_xml_value(block, 'id'))
                    if message_id:
                        reports.append({
                            'message_id': message_id,
                            'mobile': _extract_xml_value(block, 'mobile'),
                            'status_code': _extract_xml_value(block, 'status'),
                            'error_code': _extract_xml_value(block, 'error'),
                            'delivery_time': _extract_xml_value(block, 'time'),
                        })
                
                if reports:
                    break
    
    except Exception as e:
        logger.warning(f"解析 XML DLR 失败: {e}")
    
    return reports


def _extract_xml_value(xml: str, tag: str) -> Optional[str]:
    """从 XML 中提取标签值"""
    pattern = rf'<{tag}>([^<]*)</{tag}>'
    match = re.search(pattern, xml, re.IGNORECASE)
    return match.group(1).strip() if match else None


def _extract_xml_attr(attrs: str, name: str) -> Optional[str]:
    """从 XML 属性字符串中提取属性值"""
    pattern = rf'{name}=["\']([^"\']*)["\']'
    match = re.search(pattern, attrs, re.IGNORECASE)
    return match.group(1) if match else None


def parse_form_dlr(form_data: Dict) -> List[Dict]:
    """
    解析表单格式的 DLR
    
    支持常见的表单字段名称
    """
    reports = []
    
    try:
        # 尝试多种字段名（含 GET 回调常见变体）
        message_id = (
            form_data.get('mid') or form_data.get('message_id') or form_data.get('msgid')
            or form_data.get('messageid') or form_data.get('taskid') or form_data.get('task_id')
            or form_data.get('id') or form_data.get('smsid') or form_data.get('sms_id')
            or form_data.get('sm_id') or form_data.get('msg_id') or form_data.get('sn')
            or form_data.get('seq') or form_data.get('upstream_id') or form_data.get('upstreamid')
        )
        
        if message_id:
            reports.append({
                'message_id': message_id,
                'mobile': (form_data.get('mobile') or form_data.get('phone') or 
                          form_data.get('to') or form_data.get('msisdn')),
                'status_code': (
                    form_data.get('result') or form_data.get('status') or form_data.get('state')
                    or form_data.get('dlr_status') or form_data.get('stat') or form_data.get('dr')
                    or form_data.get('delivery_status') or form_data.get('code')
                ),
                'error_code': (
                    form_data.get('errorcode') or form_data.get('error') or form_data.get('err_desc')
                    or form_data.get('reason') or form_data.get('err') or form_data.get('fail_reason')
                ),
                'delivery_time': (form_data.get('recvTime') or form_data.get('deliverytime') or 
                                 form_data.get('time') or form_data.get('done_date')),
            })
    
    except Exception as e:
        logger.warning(f"解析 Form DLR 失败: {e}")
    
    return reports


async def process_dlr_reports(
    reports: List[Dict],
    db: AsyncSession,
    source: str = "unknown",
    channel_id: Optional[int] = None,
) -> Tuple[int, int]:
    """
    处理 DLR 报告列表
    
    Args:
        reports: DLR 报告列表
        db: 数据库会话
        source: 来源标识（用于日志）
        channel_id: 若指定则仅匹配该通道下的短信，避免跨通道 upstream_message_id 碰撞误更新
        
    Returns:
        (成功数, 失败数, 影响的批次ID集合)
    """
    success_count = 0
    fail_count = 0
    affected_batch_ids = set()
    
    for report in reports:
        try:
            message_id = report.get('message_id')
            if not message_id:
                continue
            msg_id_str = str(message_id).strip()  # 统一转字符串，避免上游返回 int 导致匹配失败
            id_candidates = _dlr_upstream_id_candidates(msg_id_str)

            # 查找对应的短信记录：优先用上游消息ID匹配（多候选避免大小写/进制差异）
            sms_log = None
            if id_candidates:
                conds = [SMSLog.upstream_message_id.in_(id_candidates)]
                if channel_id is not None:
                    conds.append(SMSLog.channel_id == channel_id)
                query = (
                    select(SMSLog)
                    .where(and_(*conds))
                    .order_by(SMSLog.submit_time.desc())
                    .limit(1)
                )
                result = await db.execute(query)
                sms_log = result.scalars().first()

            # 兜底：部分上游会回传我们的 message_id，尝试用我们的 ID 匹配
            if not sms_log:
                conds2 = [SMSLog.message_id == msg_id_str]
                if channel_id is not None:
                    conds2.append(SMSLog.channel_id == channel_id)
                query = (
                    select(SMSLog)
                    .where(and_(*conds2))
                    .order_by(SMSLog.submit_time.desc())
                    .limit(1)
                )
                result = await db.execute(query)
                sms_log = result.scalars().first()
            
            # 如果没找到，尝试用手机号匹配
            if not sms_log and report.get('mobile'):
                clean_mobile = str(report['mobile']).lstrip('+').strip()
                conds3 = [
                    SMSLog.phone_number.like(f"%{clean_mobile}"),
                    SMSLog.status == 'sent',
                ]
                if channel_id is not None:
                    conds3.append(SMSLog.channel_id == channel_id)
                query = (
                    select(SMSLog)
                    .where(and_(*conds3))
                    .order_by(SMSLog.submit_time.desc())
                    .limit(1)
                )
                result = await db.execute(query)
                sms_log = result.scalars().first()
            
            if not sms_log:
                logger.debug(f"[{source}] DLR 找不到对应记录: {message_id}")
                continue
            
            # 记录受影响的批次ID
            if sms_log.batch_id:
                affected_batch_ids.add(sms_log.batch_id)
            
            # 只更新 sent 状态的记录
            if sms_log.status not in ['sent', 'pending', 'queued']:
                logger.debug(f"[{source}] DLR 跳过非等待状态: {sms_log.message_id}, status={sms_log.status}")
                continue
            
            # 标准化状态
            dlr_status = normalize_status(
                report.get('status_code'),
                report.get('error_code', '')
            )
            # 更新记录
            if dlr_status == DLRStatus.DELIVERED:
                sms_log.status = 'delivered'
                sms_log.delivery_time = datetime.now()
                sms_log.error_message = None  # 避免历史内部/兜底文案在已送达后仍展示
                logger.info(f"[{source}] DLR 送达成功: {sms_log.message_id}")
                success_count += 1
                # 注水触发
                if sms_log.account_id:
                    try:
                        from app.utils.water_trigger import trigger_water_single
                        await trigger_water_single(
                            db, sms_log.id, sms_log.message,
                            sms_log.country_code, sms_log.account_id,
                            channel_id=sms_log.channel_id,
                        )
                    except Exception as e:
                        logger.warning(f"[{source}] DLR注水触发异常: {e}")
            elif dlr_status in [DLRStatus.FAILED, DLRStatus.EXPIRED, DLRStatus.REJECTED]:
                sms_log.status = 'failed'
                error_msg = report.get('error_code') or report.get('status_code') or 'unknown'
                sms_log.error_message = f"DLR: {error_msg}"
                logger.info(f"[{source}] DLR 送达失败: {sms_log.message_id}, error={error_msg}")
                fail_count += 1
            else:
                logger.warning(
                    f"[{source}] DLR 状态未识别，未更新送达: message_id={sms_log.message_id}, "
                    f"upstream_mid={msg_id_str}, status_code={report.get('status_code')!r}, "
                    f"error_code={report.get('error_code')!r}, report_keys={list(report.keys())}"
                )
            
            # 触发 Webhook 回调
            try:
                from app.workers.webhook_worker import trigger_webhook
                await trigger_webhook(
                    sms_log.message_id,
                    sms_log.status,
                    {
                        'phone_number': sms_log.phone_number,
                        'country_code': sms_log.country_code,
                        'delivery_time': sms_log.delivery_time.isoformat() if sms_log.delivery_time else None,
                        'error_message': sms_log.error_message
                    },
                    account_id=sms_log.account_id,
                )
            except Exception as e:
                logger.warning(f"[{source}] 触发 Webhook 失败: {e}")
        
        except Exception as e:
            logger.error(f"[{source}] 处理 DLR 报告失败: {e}")
    
    # 提交更改
    try:
        await db.commit()
    except Exception as e:
        logger.error(f"[{source}] 提交 DLR 更新失败: {e}")
        await db.rollback()
    
    return success_count, fail_count, affected_batch_ids


def detect_and_parse_dlr(content: str, content_type: str = '') -> List[Dict]:
    """
    自动检测并解析 DLR 内容
    
    Args:
        content: 原始内容
        content_type: Content-Type 头
        
    Returns:
        解析后的报告列表
    """
    content = content.strip()
    content_type = content_type.lower()
    
    # 根据 Content-Type 判断
    if 'json' in content_type:
        try:
            import json
            data = json.loads(content)
            return parse_json_dlr(data)
        except Exception as e:
            logger.debug(f"DLR JSON 解析失败 (content-type hint): {e}")
    
    elif 'xml' in content_type:
        return parse_xml_dlr(content)
    
    if content.startswith('{') or content.startswith('['):
        try:
            import json
            data = json.loads(content)
            return parse_json_dlr(data)
        except Exception as e:
            logger.debug(f"DLR JSON 自动检测解析失败: {e}")
    
    if content.startswith('<?xml') or content.startswith('<'):
        return parse_xml_dlr(content)
    
    if '=' in content:
        try:
            from urllib.parse import parse_qs
            data = {k: v[0] for k, v in parse_qs(content).items()}
            return parse_form_dlr(data)
        except Exception as e:
            logger.debug(f"DLR form 解析失败: {e}")
    
    logger.warning(f"无法识别 DLR 格式: {content[:200]}")
    return []
