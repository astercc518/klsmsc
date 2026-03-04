"""
短信发送Worker
"""
from datetime import datetime
from sqlalchemy import select
from app.workers.celery_app import celery_app
from app.modules.sms.sms_log import SMSLog
from app.modules.sms.channel import Channel
from app.database import AsyncSessionLocal
from app.utils.logger import get_logger
import asyncio

logger = get_logger(__name__)


def _run_async(coro):
    """在 Celery 同步 worker 中安全地执行异步协程"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        new_loop = asyncio.new_event_loop()
        try:
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()
    else:
        return asyncio.run(coro)


@celery_app.task(name='send_sms_task', bind=True, max_retries=3)
def send_sms_task(self, message_id: str, http_credentials: dict = None):
    """
    发送短信任务
    
    Args:
        message_id: 消息ID
        http_credentials: HTTP通道凭据（可选），包含 username 和 password
    """
    logger.info(f"开始处理短信发送任务: {message_id}")
    
    try:
        result = _run_async(_send_sms_async(message_id, http_credentials))
        return result
        
    except Exception as e:
        logger.error(f"发送短信失败: {message_id}, 错误: {str(e)}", exc_info=e)
        
        if self.request.retries < self.max_retries:
            logger.info(f"将重试发送: {message_id}, 重试次数: {self.request.retries + 1}")
            raise self.retry(exc=e, countdown=60)
        else:
            logger.error(f"达到最大重试次数，标记为失败: {message_id}")
            _run_async(_mark_failed(message_id, str(e)))
            return {"success": False, "error": str(e)}


async def _send_sms_async(message_id: str, http_credentials: dict = None) -> dict:
    """
    异步发送短信
    
    Args:
        message_id: 消息ID
        http_credentials: HTTP通道凭据（可选），包含 username 和 password
    """
    async with AsyncSessionLocal() as db:
        # 查询短信记录
        result = await db.execute(
            select(SMSLog).where(SMSLog.message_id == message_id)
        )
        sms_log = result.scalar_one_or_none()
        
        if not sms_log:
            logger.error(f"短信记录不存在: {message_id}")
            return {"success": False, "error": "Message not found"}
        
        # 查询通道
        result = await db.execute(
            select(Channel).where(Channel.id == sms_log.channel_id)
        )
        channel = result.scalar_one_or_none()
        
        if not channel:
            logger.error(f"通道不存在: {sms_log.channel_id}")
            sms_log.status = 'failed'
            sms_log.error_message = "Channel not found"
            await db.commit()
            return {"success": False, "error": "Channel not found"}
        
        logger.info(f"使用通道: {channel.channel_code} ({channel.protocol})")
        
        # 更新状态为发送中
        sms_log.status = 'sent'
        sms_log.sent_time = datetime.now()
        await db.commit()
        
        # 根据通道协议发送
        if channel.protocol == 'HTTP':
            success = await _send_via_http(sms_log, channel, http_credentials)
        elif channel.protocol == 'SMPP':
            success = await _send_via_smpp(sms_log, channel)
        else:
            logger.warning(f"不支持的协议: {channel.protocol}")
            success = False
        
        # 更新状态
        if success:
            sms_log.status = 'sent'  # 先标记为已发送，等待DLR
            sms_log.sent_time = datetime.now()
            logger.info(f"短信发送成功: {message_id}")
            
            # 触发Webhook回调（sent状态）
            try:
                from app.workers.webhook_worker import trigger_webhook
                await trigger_webhook(
                    message_id,
                    'sent',
                    {
                        'phone_number': sms_log.phone_number,
                        'country_code': sms_log.country_code,
                        'channel_id': sms_log.channel_id
                    }
                )
            except Exception as e:
                logger.warning(f"触发Webhook失败: {str(e)}")
        else:
            sms_log.status = 'failed'
            # 保留详细错误信息，只有未设置时才使用默认值
            if not sms_log.error_message:
                sms_log.error_message = "Send failed"
            logger.error(f"短信发送失败: {message_id}, 错误: {sms_log.error_message}")
            
            # 触发Webhook回调（failed状态）
            try:
                from app.workers.webhook_worker import trigger_webhook
                await trigger_webhook(
                    message_id,
                    'failed',
                    {
                        'phone_number': sms_log.phone_number,
                        'country_code': sms_log.country_code,
                        'error_message': sms_log.error_message
                    }
                )
            except Exception as e:
                logger.warning(f"触发Webhook失败: {str(e)}")
        
        await db.commit()
        
        return {"success": success, "message_id": message_id, "status": sms_log.status}


async def _send_via_http(sms_log: SMSLog, channel: Channel, http_credentials: dict = None) -> bool:
    """
    通过HTTP发送短信
    
    Args:
        sms_log: 短信记录
        channel: 通道配置
        http_credentials: HTTP凭据（可选），包含 username 和 password，优先级高于通道配置
    """
    import httpx
    
    try:
        logger.info(f"通过HTTP发送短信: {sms_log.message_id} via {channel.channel_code}")
        
        # 使用通道的默认发送方ID作为extno，如果为空则不传
        extno = channel.default_sender_id or ""
        
        # 如果没有配置 api_url，使用模拟模式
        if not channel.api_url:
            logger.info(f"HTTP通道未配置api_url，使用模拟模式: {sms_log.message_id}")
            if http_credentials:
                logger.info(f"模拟HTTP发送 (使用自定义凭据: {http_credentials.get('username', 'N/A')})")
            logger.info(f"模拟HTTP发送成功: {sms_log.message_id} -> {sms_log.phone_number}")
            return True
        
        # 确定使用哪个凭据
        # 优先级: 1. API请求传入的http_credentials  2. 通道username/password字段  3. 通道api_key字段(JSON格式)
        http_account = None
        http_password = None
        
        if http_credentials:
            http_account = http_credentials.get("username") or http_credentials.get("account")
            http_password = http_credentials.get("password")
            if http_account:
                logger.info(f"使用API请求传入的HTTP凭据: {http_account}")
        
        # 如果没有自定义凭据，使用通道的 username/password 字段
        if not http_account and channel.username:
            http_account = channel.username
            http_password = channel.password
            logger.info(f"使用通道配置的HTTP凭据: {http_account}")
        
        # 如果还是没有，从通道api_key字段解析（JSON格式，兼容旧配置）
        # 格式: {"account": "888998", "password": "xxx"}
        if not http_account and channel.api_key:
            try:
                import json
                api_config = json.loads(channel.api_key)
                http_account = api_config.get("account")
                http_password = api_config.get("password")
                if http_account:
                    logger.info(f"使用通道api_key配置的HTTP凭据: {http_account}")
            except json.JSONDecodeError:
                logger.warning(f"通道api_key不是有效的JSON格式: {channel.api_key}")
        
        # 处理手机号：去掉+号
        mobile = sms_log.phone_number
        if mobile.startswith('+'):
            mobile = mobile[1:]
        
        # 按照上游接口格式构造请求参数
        # 格式: {"action":"send","account":"123456","password":"123456","mobile":"15100000000","content":"内容","extno":"10690","atTime":"2022-12-05 18:00:00"}
        payload = {
            "action": "send",
            "account": http_account or "",
            "password": http_password or "",
            "mobile": mobile,
            "content": sms_log.message,
            "extno": extno
        }
        
        # 如果有定时发送时间，添加atTime参数
        scheduled_time = getattr(sms_log, 'scheduled_time', None)
        if scheduled_time:
            payload["atTime"] = scheduled_time.strftime("%Y-%m-%d %H:%M:%S")
        
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "SMSC-Gateway/1.0"
        }
        
        logger.info(f"HTTP请求URL: {channel.api_url}")
        logger.info(f"HTTP请求参数: {payload}")
        
        # 实际发送请求
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                channel.api_url,
                json=payload,
                headers=headers
            )
            
            response_text = response.text
            logger.info(f"HTTP响应: status={response.status_code}, body={response_text[:500]}")
            
            if response.status_code in [200, 201]:
                # 解析上游JSON响应
                # 格式: {"status":0, "balance":520, "list":[{"mid":"xxx", "mobile":"xxx", "result":0}]}
                # status: 0=成功, 2=IP错误, 3=账号密码错误, 5=其它错误
                # result: 0=成功, 10=extno错误, 15=余额不足, 100=系统错误
                try:
                    resp_data = response.json()
                    api_status = resp_data.get('status')
                    balance = resp_data.get('balance', 0)
                    result_list = resp_data.get('list', [])
                    
                    # STATUS错误代码表
                    status_errors = {
                        0: "成功",
                        2: "IP错误",
                        3: "账号密码错误",
                        5: "其它错误",
                        6: "接入点错误",
                        7: "账号状态异常(已停用)",
                        11: "系统内部错误",
                        34: "请求参数有误",
                        100: "系统内部错误"
                    }
                    
                    # RESULT错误代码表
                    result_errors = {
                        0: "提交成功",
                        10: "原发号码错误(extno错误)",
                        15: "余额不足",
                        100: "系统内部错误"
                    }
                    
                    if api_status == 0:
                        # 请求成功，检查每个号码的提交结果
                        if result_list:
                            first_result = result_list[0]
                            mid = first_result.get('mid', '')
                            result_code = first_result.get('result', -1)
                            
                            if result_code == 0:
                                logger.info(f"HTTP发送成功: {sms_log.message_id}, mid={mid}, balance={balance}")
                                # 保存上游消息ID
                                sms_log.upstream_message_id = mid
                                return True
                            else:
                                error_desc = result_errors.get(result_code, f"未知错误({result_code})")
                                logger.error(f"HTTP发送失败(提交错误): {sms_log.message_id}, result={result_code}, 错误: {error_desc}")
                                sms_log.error_message = f"上游错误: {error_desc}"
                                return False
                        else:
                            # 没有返回list，但status=0，认为成功
                            logger.info(f"HTTP发送成功(无明细): {sms_log.message_id}, balance={balance}")
                            return True
                    else:
                        # status != 0，请求失败
                        error_desc = status_errors.get(api_status, f"未知错误({api_status})")
                        logger.error(f"HTTP发送失败(API错误): {sms_log.message_id}, status={api_status}, 错误: {error_desc}")
                        sms_log.error_message = f"上游API错误: {error_desc}"
                        return False
                        
                except Exception as e:
                    # JSON解析失败，尝试解析XML响应（兼容旧接口）
                    if '<returnsms>' in response_text:
                        import re
                        status_match = re.search(r'<returnstatus>(\w+)</returnstatus>', response_text)
                        message_match = re.search(r'<message>([^<]*)</message>', response_text)
                        
                        return_status = status_match.group(1) if status_match else 'Unknown'
                        return_message = message_match.group(1) if message_match else ''
                        
                        if return_status.lower() == 'success':
                            logger.info(f"HTTP发送成功(XML): {sms_log.message_id}")
                            return True
                        else:
                            logger.error(f"HTTP发送失败(XML): {sms_log.message_id}, status={return_status}, message={return_message}")
                            sms_log.error_message = f"上游XML错误: status={return_status}, code={return_message}"
                            return False
                    else:
                        logger.error(f"HTTP响应解析失败: {sms_log.message_id}, error={e}, body={response_text[:200]}")
                        sms_log.error_message = f"响应解析失败: {str(e)}"
                        return False
            else:
                logger.error(f"HTTP发送失败: {response.status_code} {response.text}")
                return False
        
    except Exception as e:
        logger.error(f"HTTP发送异常: {str(e)}", exc_info=e)
        return False


async def _send_via_smpp(sms_log: SMSLog, channel: Channel) -> bool:
    """
    通过SMPP发送短信
    """
    from app.workers.adapters.smpp_adapter import SMPPAdapter
    
    adapter = None
    try:
        logger.info(f"通过SMPP发送短信: {sms_log.message_id} via {channel.channel_code}")
        
        # 创建SMPP适配器
        adapter = SMPPAdapter(channel)
        
        # 发送短信
        success, channel_message_id, error_message = await adapter.send(sms_log)
        
        if success:
            # 保存上游消息ID
            if channel_message_id:
                sms_log.upstream_message_id = channel_message_id
            logger.info(f"SMPP发送成功: {sms_log.message_id} -> {channel_message_id}")
            return True
        else:
            sms_log.error_message = error_message or "SMPP send failed"
            logger.error(f"SMPP发送失败: {sms_log.message_id}, 错误: {error_message}")
            return False
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"SMPP发送异常: {error_msg}", exc_info=e)
        if sms_log:
            sms_log.error_message = error_msg
        return False
    finally:
        # 断开连接（注意：实际生产环境应该使用连接池）
        if adapter:
            try:
                await adapter.disconnect()
            except Exception as e:
                logger.warning(f"关闭SMPP适配器失败: {str(e)}")


async def _mark_failed(message_id: str, error_message: str):
    """标记短信为失败状态"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SMSLog).where(SMSLog.message_id == message_id)
        )
        sms_log = result.scalar_one_or_none()
        
        if sms_log:
            sms_log.status = 'failed'
            sms_log.error_message = error_message
            await db.commit()
            logger.info(f"已标记为失败: {message_id}")


@celery_app.task(name='process_dlr_task')
def process_dlr_task(dlr_data: dict):
    """
    处理送达回执(DLR)任务
    
    Args:
        dlr_data: DLR数据
    """
    logger.info(f"处理DLR: {dlr_data}")
    
    try:
        _run_async(_process_dlr_async(dlr_data))
        return {"success": True}
        
    except Exception as e:
        logger.error(f"处理DLR失败: {str(e)}", exc_info=e)
        return {"success": False, "error": str(e)}


async def _process_dlr_async(dlr_data: dict):
    """
    异步处理DLR
    """
    async with AsyncSessionLocal() as db:
        message_id = dlr_data.get('message_id')
        status = dlr_data.get('status')
        
        result = await db.execute(
            select(SMSLog).where(SMSLog.message_id == message_id)
        )
        sms_log = result.scalar_one_or_none()
        
        if not sms_log:
            logger.warning(f"DLR对应的短信记录不存在: {message_id}")
            return
        
        # 更新状态
        sms_log.status = status
        if status == 'delivered':
            sms_log.delivery_time = datetime.now()
        elif status == 'failed':
            sms_log.error_message = dlr_data.get('error_message', 'Delivery failed')
        
        await db.commit()
        logger.info(f"DLR处理完成: {message_id}, 状态: {status}")
        
        # 触发Webhook回调
        try:
            from app.workers.webhook_worker import trigger_webhook
            await trigger_webhook(
                message_id,
                status,
                {
                    'phone_number': sms_log.phone_number,
                    'country_code': sms_log.country_code,
                    'error_message': dlr_data.get('error_message') if status == 'failed' else None
                }
            )
        except Exception as e:
            logger.warning(f"触发Webhook失败: {str(e)}")


# ============ 定时拉取 DLR 报告 ============

@celery_app.task(name='fetch_dlr_reports_task')
def fetch_dlr_reports_task():
    """
    定时拉取上游 DLR 报告
    
    从 Kaola SMS 的 report 接口拉取送达报告
    """
    logger.info("开始拉取 DLR 报告...")
    
    try:
        result = _run_async(_fetch_dlr_reports_async())
        return result
        
    except Exception as e:
        logger.error(f"拉取 DLR 报告失败: {str(e)}", exc_info=e)
        return {"success": False, "error": str(e)}


async def _fetch_dlr_reports_async():
    """
    异步拉取 DLR 报告
    
    支持多种上游格式（JSON/XML），使用统一的 DLR 处理模块
    """
    import httpx
    from app.core.dlr_handler import detect_and_parse_dlr, process_dlr_reports
    
    async with AsyncSessionLocal() as db:
        # 获取所有活跃的 HTTP 通道
        result = await db.execute(
            select(Channel).where(
                Channel.protocol == 'HTTP',
                Channel.status == 'active',
                Channel.is_deleted == False
            )
        )
        channels = result.scalars().all()
        
        total_success = 0
        total_fail = 0
        
        for channel in channels:
            if not channel.api_url:
                continue
            
            # 获取凭据
            http_account = channel.username or ''
            http_password = channel.password or ''
            
            if not http_account:
                logger.debug(f"通道 {channel.channel_code} 没有配置凭据，跳过")
                continue
            
            try:
                # 构造报告查询 URL
                report_url = _build_dlr_pull_url(channel)
                
                params = {
                    "action": "report",
                    "account": http_account,
                    "password": http_password
                }
                
                logger.info(f"拉取 DLR: {channel.channel_code}, URL: {report_url}")
                
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(report_url, params=params)
                    
                    if response.status_code == 200:
                        resp_text = response.text
                        content_type = response.headers.get('content-type', '')
                        
                        logger.debug(f"[{channel.channel_code}] DLR 响应: {resp_text[:500]}")
                        
                        # 检查是否为空响应
                        if _is_empty_dlr_response(resp_text):
                            logger.debug(f"[{channel.channel_code}] DLR 响应为空，无新报告")
                            continue
                        
                        # 检查是否有错误
                        if _is_error_dlr_response(resp_text):
                            logger.warning(f"[{channel.channel_code}] DLR 响应错误: {resp_text[:200]}")
                            continue
                        
                        # 使用统一的解析器
                        reports = detect_and_parse_dlr(resp_text, content_type)
                        
                        if reports:
                            logger.info(f"[{channel.channel_code}] 解析到 {len(reports)} 条 DLR 报告")
                            success, fail = await process_dlr_reports(
                                reports, db, 
                                source=f"pull-{channel.channel_code}"
                            )
                            total_success += success
                            total_fail += fail
                        else:
                            logger.debug(f"[{channel.channel_code}] 无有效 DLR 报告")
                    else:
                        logger.warning(f"[{channel.channel_code}] 拉取 DLR 失败: HTTP {response.status_code}")
                        
            except Exception as e:
                logger.error(f"拉取通道 {channel.channel_code} DLR 失败: {str(e)}")
        
        total = total_success + total_fail
        logger.info(f"DLR 拉取完成: 成功={total_success}, 失败={total_fail}, 总计={total}")
        return {"success": True, "updated": total, "delivered": total_success, "failed": total_fail}


def _build_dlr_pull_url(channel: Channel) -> str:
    """
    构建 DLR 拉取 URL
    
    根据不同的通道类型构建对应的报告查询 URL
    """
    base_url = channel.api_url or ''
    
    # Kaola 格式: /smsv2 -> /sms?action=report
    if 'kaolasms' in base_url.lower():
        base_url = base_url.replace('/smsv2', '/sms').replace('?action=send', '')
        if '?' in base_url:
            base_url = base_url.split('?')[0]
        return base_url
    
    # 通用格式: 尝试替换或添加 /report 路径
    if base_url.endswith('/send'):
        return base_url.replace('/send', '/report')
    
    if base_url.endswith('/sms'):
        return base_url + '/report'
    
    # 默认直接使用
    return base_url


def _is_empty_dlr_response(resp_text: str) -> bool:
    """
    检查 DLR 响应是否为空
    """
    resp_text = resp_text.strip()
    
    # XML 空响应
    if '<returnsms></returnsms>' in resp_text:
        return True
    if '<returnsms/>' in resp_text:
        return True
    if '<reports></reports>' in resp_text:
        return True
    
    # JSON 空响应
    if resp_text in ['{}', '[]', '{"list":[]}', '{"reports":[]}', '{"data":[]}']:
        return True
    
    # 纯空
    if not resp_text:
        return True
    
    return False


def _is_error_dlr_response(resp_text: str) -> bool:
    """
    检查 DLR 响应是否为错误
    """
    resp_text = resp_text.lower()
    
    # 常见错误标识
    error_patterns = [
        '<errorstatus>',
        '<error>',
        '"error":',
        'invalid_auth',
        'authentication failed',
        'access denied',
        'unauthorized',
    ]
    
    return any(pattern in resp_text for pattern in error_patterns)
