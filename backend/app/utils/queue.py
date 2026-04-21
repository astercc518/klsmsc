"""
消息队列工具
"""
import time
from typing import Optional

from app.workers.celery_app import celery_app
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
    def queue_smpp_gateway(message_id: str, http_credentials: dict = None) -> bool:
        """
        将 SMPP 发送任务直接投递到 sms_send_smpp，供 Go smpp-gateway 消费。

        与 send_sms_task 从 sms_send 重投到 sms_send_smpp 的消息体一致，但跳过 worker-sms
        对 sms_send 的消费，避免仅 api+gateway 可用而 worker-sms 未启动时测试发送卡住。
        """
        from app.workers.sms_worker import send_sms_task

        last_err: Optional[Exception] = None
        for attempt in range(_SMS_QUEUE_RETRIES):
            try:
                task = send_sms_task.apply_async(
                    args=[message_id, http_credentials],
                    queue="sms_send_smpp",
                )
                logger.info(
                    f"SMPP 已直投 sms_send_smpp: {message_id}, task_id: {task.id}"
                    + (f" (第{attempt + 1}次尝试)" if attempt else "")
                )
                return True
            except Exception as e:
                last_err = e
                logger.warning(
                    f"SMPP 直投队列失败将重试: {message_id}, 第{attempt + 1}/{_SMS_QUEUE_RETRIES}次, {e}"
                )
                if attempt < _SMS_QUEUE_RETRIES - 1:
                    time.sleep(_SMS_QUEUE_BACKOFF[attempt])

        logger.error(
            f"SMPP 直投队列最终失败: {message_id}, 错误: {str(last_err)}",
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
    def queue_sms_batch_smpp(message_ids: list, http_credentials: dict = None) -> bool:
        """
        将多条 SMPP 短信直接投递到 sms_send_smpp，由 Go 网关消费（跳过 sms_send 双跳）。

        当前实现为逐条 apply_async，与 queue_smpp_gateway 一致，保证 Celery 消息体与网关解析兼容。
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
                        queue="sms_send_smpp",
                    )
                    ok = True
                    break
                except Exception as e:
                    last_err = e
                    if attempt < _SMS_QUEUE_RETRIES - 1:
                        time.sleep(_SMS_QUEUE_BACKOFF[attempt])
            if not ok:
                logger.error(
                    f"SMPP 批量直投失败: {message_id}, 错误: {str(last_err)}",
                    exc_info=last_err,
                )
                all_ok = False

        logger.info(f"SMPP 批量直投 sms_send_smpp 完成: 共 {len(message_ids)} 条, 全部成功={all_ok}")
        return all_ok

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
