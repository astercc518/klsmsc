import httpx
from typing import Optional
from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

class NotificationService:
    def __init__(self):
        self.bot_token = settings.TELEGRAM_BOT_TOKEN
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else None

    async def send_message(self, chat_id: str, text: str, parse_mode: str = "Markdown") -> bool:
        """
        发送消息到指定Telegram Chat ID
        """
        if not self.bot_token:
            logger.warning("Telegram Bot Token未配置，无法发送通知")
            return False

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": text,
                        "parse_mode": parse_mode
                    },
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    return True
                
                logger.error(f"发送Telegram消息失败: {response.status_code} {response.text}")
                return False
        except Exception as e:
            logger.error(f"发送Telegram消息异常: {str(e)}")
            return False

    async def notify_admin_group(self, text: str) -> bool:
        """
        通知管理员群组
        """
        if settings.TELEGRAM_ADMIN_GROUP_ID:
            return await self.send_message(settings.TELEGRAM_ADMIN_GROUP_ID, text)
        return False

    async def notify_user(self, tg_id: str, text: str) -> bool:
        """
        通知单个用户
        """
        if tg_id:
            return await self.send_message(tg_id, text)
        return False

# 全局实例
notification_service = NotificationService()
