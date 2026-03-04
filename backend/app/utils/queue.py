"""
消息队列工具
"""
from app.workers.celery_app import celery_app
from app.utils.logger import get_logger

logger = get_logger(__name__)


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
        try:
            # 发送异步任务到Celery
            from app.workers.sms_worker import send_sms_task
            task = send_sms_task.apply_async(
                args=[message_id, http_credentials],
                queue='sms_send',
                retry=True
            )
            
            logger.info(f"短信已加入队列: {message_id}, task_id: {task.id}")
            return True
            
        except Exception as e:
            logger.error(f"加入队列失败: {message_id}, 错误: {str(e)}", exc_info=e)
            return False
    
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

