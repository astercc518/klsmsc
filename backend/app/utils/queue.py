"""
消息队列工具
"""
import time
from typing import Optional

from app.workers.celery_app import celery_app, SMPP_BULK_PUBLISH_SERIALIZER
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 入队短暂失败（Broker 抖动、连接竞争）时自动重试，避免库中永久 queued 却无 Celery 任务
_SMS_QUEUE_RETRIES = 3
_SMS_QUEUE_BACKOFF = (0.2, 0.6, 1.2)


class QueueManager:
    """消息队列管理器"""
    
    @staticmethod
    def queue_sms(message_id: str, http_credentials: dict = None) -> bool:
        """
        将短信加入发送队列
        
        Args:
            message_id: 消息ID
            http_credentials: HTTP通道凭据（可选），包含 username 和 password
            
        Returns:
            是否成功加入队列
        """
        from app.workers.sms_worker import send_sms_task

        last_err: Optional[Exception] = None
        for attempt in range(_SMS_QUEUE_RETRIES):
            try:
                task = send_sms_task.apply_async(
                    args=[message_id, http_credentials],
                    queue='sms_send',
                )
                logger.info(
                    f"短信已加入队列: {message_id}, task_id: {task.id}"
                    + (f" (第{attempt + 1}次尝试)" if attempt else "")
                )
                return True
            except Exception as e:
                last_err = e
                logger.warning(
                    f"加入队列失败将重试: {message_id}, 第{attempt + 1}/{_SMS_QUEUE_RETRIES}次, {e}"
                )
                if attempt < _SMS_QUEUE_RETRIES - 1:
                    time.sleep(_SMS_QUEUE_BACKOFF[attempt])

        logger.error(
            f"加入队列最终失败: {message_id}, 错误: {str(last_err)}",
            exc_info=last_err,
        )
        return False

    @staticmethod
    def queue_smpp_gateway(smpp_payload_or_message_id, http_credentials: dict = None) -> bool:
        """
        将 SMPP 发送任务直接投递到 sms_send_smpp，供 Go smpp-gateway 消费。

        smpp_payload_or_message_id 可为全量 dict（推荐）或 message_id 字符串（将同步查库组装负载）。
        """
        from app.workers.sms_worker import send_sms_task, _run_async, _load_smpp_payload_by_message_id

        payload = smpp_payload_or_message_id
        if isinstance(payload, str):
            built = _run_async(_load_smpp_payload_by_message_id(payload))
            if not built:
                logger.error(f"SMPP 直投失败：无法组装负载 message_id={payload}")
                return False
            payload = built
            mid = payload.get("message_id", "")
        else:
            mid = (payload or {}).get("message_id", "")

        last_err: Optional[Exception] = None
        for attempt in range(_SMS_QUEUE_RETRIES):
            try:
                task = send_sms_task.apply_async(
                    args=[payload, http_credentials],
                    queue="sms_send_smpp",
                )
                logger.info(
                    f"SMPP 已直投 sms_send_smpp: {mid}, task_id: {task.id}"
                    + (f" (第{attempt + 1}次尝试)" if attempt else "")
                )
                return True
            except Exception as e:
                last_err = e
                logger.warning(
                    f"SMPP 直投队列失败将重试: {mid}, 第{attempt + 1}/{_SMS_QUEUE_RETRIES}次, {e}"
                )
                if attempt < _SMS_QUEUE_RETRIES - 1:
                    time.sleep(_SMS_QUEUE_BACKOFF[attempt])

        logger.error(
            f"SMPP 直投队列最终失败: {mid}, 错误: {str(last_err)}",
            exc_info=last_err,
        )
        return False

    @staticmethod
    def queue_sms_batch(message_ids: list, http_credentials: dict = None) -> bool:
        """
        批量将多条短信加入发送队列（每条独立 Celery 任务）。
        
        Args:
            message_ids: 消息ID列表
            http_credentials: HTTP通道凭据（可选）

        Returns:
            全部成功返回 True，有任意失败则返回 False
        """
        if not message_ids:
            return True

        from app.workers.sms_worker import send_sms_task

        all_ok = True
        for message_id in message_ids:
            last_err = None
            ok = False
            for attempt in range(_SMS_QUEUE_RETRIES):
                try:
                    send_sms_task.apply_async(
                        args=[message_id, http_credentials],
                        queue='sms_send',
                    )
                    ok = True
                    break
                except Exception as e:
                    last_err = e
                    if attempt < _SMS_QUEUE_RETRIES - 1:
                        time.sleep(_SMS_QUEUE_BACKOFF[attempt])
            if not ok:
                logger.error(
                    f"批量入队失败: {message_id}, 错误: {str(last_err)}",
                    exc_info=last_err,
                )
                all_ok = False

        logger.info(f"批量入队完成: 共 {len(message_ids)} 条, 全部成功={all_ok}")
        return all_ok

    @staticmethod
    def queue_sms_batch_smpp(items: list, http_credentials: dict = None) -> bool:
        """
        将多条 SMPP 短信整包投递到 sms_send_smpp（单次 AMQP publish / 单次 apply_async）。

        Go 网关从 Celery 信封首参解析 list[dict]（见 go-smpp-gateway smsPayloadsFromFirstTaskArg）。
        禁止在内部对每条再 apply_async，否则 5 万条会产生 5 万次网络往返。

        items 元素须为全量负载 dict（与 Go SMSLogData 对齐）；若为 message_id 字符串列表则先批量查库组装。
        """
        if not items:
            return True

        from app.workers.sms_worker import send_sms_task, _run_async, _load_smpp_payloads_by_message_ids

        payloads: list = []
        if isinstance(items[0], str):
            payloads = _run_async(_load_smpp_payloads_by_message_ids(items))
            if len(payloads) != len(items):
                logger.error(
                    f"SMPP 批量直投：负载条数 {len(payloads)} 与输入 {len(items)} 不一致，放弃本批"
                )
                return False
        else:
            payloads = list(items)

        ser = SMPP_BULK_PUBLISH_SERIALIZER
        last_err: Optional[Exception] = None

        for attempt in range(_SMS_QUEUE_RETRIES):
            try:
                with celery_app.producer_pool.acquire(block=True) as producer:
                    send_sms_task.apply_async(
                        args=[payloads, http_credentials],
                        queue="sms_send_smpp",
                        producer=producer,
                        serializer=ser,
                    )
                logger.info(
                    f"SMPP 整包直投 sms_send_smpp: {len(payloads)} 条, serializer={ser}, 单次 publish"
                )
                return True
            except Exception as e:
                last_err = e
                logger.warning(
                    f"SMPP 整包直投失败将重试: 共 {len(payloads)} 条, "
                    f"第 {attempt + 1}/{_SMS_QUEUE_RETRIES} 次, {e}"
                )
                if attempt < _SMS_QUEUE_RETRIES - 1:
                    time.sleep(_SMS_QUEUE_BACKOFF[attempt])

        logger.error(
            f"SMPP 整包直投最终失败: 共 {len(payloads)} 条, 错误: {last_err}",
            exc_info=last_err,
        )
        # 降级：逐条 publish（保证尽量不丢，但性能差）
        ok = 0
        for payload in payloads:
            if QueueManager.queue_smpp_gateway(payload, http_credentials):
                ok += 1
        logger.warning(
            f"SMPP 整包失败后已降级逐条投递: 成功 {ok}/{len(payloads)}"
        )
        return ok == len(payloads)

    @staticmethod
    def queue_sms_bulk(message_ids: list, http_credentials: dict = None) -> tuple:
        """
        批量将多条短信加入 sms_send 队列，复用单个 AMQP producer 连接。

        相比逐条 apply_async（每条独占一次 producer pool 申请/释放），
        此方法一次 acquire 发布全部消息，在千条规模下可节省数秒 AMQP 开销。

        Returns:
            (ok_ids, fail_ids) — 成功/失败的 message_id 列表
        """
        if not message_ids:
            return [], []

        from app.workers.sms_worker import send_sms_task
        from app.workers.celery_app import celery_app

        ok_ids: list = []
        fail_ids: list = []

        try:
            with celery_app.producer_pool.acquire(block=True) as producer:
                for message_id in message_ids:
                    last_err = None
                    sent = False
                    for attempt in range(_SMS_QUEUE_RETRIES):
                        try:
                            send_sms_task.apply_async(
                                args=[message_id, http_credentials],
                                queue='sms_send',
                                producer=producer,
                            )
                            sent = True
                            break
                        except Exception as e:
                            last_err = e
                            if attempt < _SMS_QUEUE_RETRIES - 1:
                                time.sleep(_SMS_QUEUE_BACKOFF[attempt])
                    if sent:
                        ok_ids.append(message_id)
                    else:
                        logger.error(f"批量入队失败: {message_id}, {last_err}")
                        fail_ids.append(message_id)
        except Exception as e:
            logger.error(f"queue_sms_bulk producer 获取失败，降级逐条入队: {e}")
            # 降级：逐条 apply_async
            for message_id in message_ids:
                if QueueManager.queue_sms(message_id, http_credentials):
                    ok_ids.append(message_id)
                else:
                    fail_ids.append(message_id)

        logger.info(f"批量入队完成: 共 {len(message_ids)} 条, 成功={len(ok_ids)}, 失败={len(fail_ids)}")
        return ok_ids, fail_ids

    @staticmethod
    def queue_dlr(dlr_data: dict) -> bool:
        """
        将DLR加入处理队列
        
        Args:
            dlr_data: DLR数据
            
        Returns:
            是否成功加入队列
        """
        try:
            from app.workers.sms_worker import process_dlr_task
            task = process_dlr_task.apply_async(
                args=[dlr_data],
                queue='sms_dlr'
            )
            
            logger.info(f"DLR已加入队列, task_id: {task.id}")
            return True

        except Exception as e:
            logger.error(f"DLR加入队列失败: {str(e)}", exc_info=e)
            return False

    @staticmethod
    def queue_inbound_dlr(payload: dict) -> bool:
        """
        发布 DLR 到 sms_inbound_dlr 队列，供 Go SMPP 入站网关推送给在线的客户 RECEIVER 会话。

        payload 结构（与 Go 侧 inbound_dlr_consumer 解析对齐）:
            {
                "system_id":   str,   # 客户 SMPP system_id
                "message_id":  str,   # SMSLog.message_id（Go 网关生成的入站 msgid）
                "source_addr": str,
                "dest_addr":   str,
                "stat":        str,   # DELIVRD / UNDELIV / EXPIRED / REJECTD / ACCEPTD
                "err":         str,   # 三位错误码
                "submit_date": str,   # YYMMDDhhmm
                "done_date":   str,   # YYMMDDhhmm
                "text_preview": str,  # 短信文本前 20 字符
            }
        无 Python worker 消费此队列；Celery envelope 仅作为传输载体。
        """
        try:
            celery_app.send_task(
                "_inbound_dlr_dispatch",  # 占位任务名，Python 端无 worker 注册
                args=[payload],
                queue="sms_inbound_dlr",
                routing_key="sms_inbound_dlr",
            )
            return True
        except Exception as e:
            logger.error(
                f"queue_inbound_dlr 失败: system_id={payload.get('system_id')} "
                f"msgid={payload.get('message_id')}: {e}",
                exc_info=e,
            )
            return False
