import sys
import os
from typing import Any, Optional, Tuple, Dict

# 将 backend 目录添加到 path，以便可以直接引用 app 模块
from loguru import logger

# 不需要再添加 backend 到 sys.path，所有交互应通过 APIClient 进行
# logger 使用 loguru 直接初始化

async def log_outgoing_message(user_id: int, content: str, chat_id: Optional[int] = None):
    """记录发出消息异步助手"""
    from bot.services.message_service import MessageService
    await MessageService.log_outgoing(user_id, content, chat_id)

async def send_and_log(context: Any, chat_id: int, text: str, **kwargs):
    """发送并记录消息"""
    message = await context.bot.send_message(chat_id=chat_id, text=text, **kwargs)
    # 异步记录，不阻塞发送
    import asyncio
    asyncio.create_task(log_outgoing_message(chat_id, text, chat_id))
    return message

async def edit_and_log(query: Any, text: str, **kwargs):
    """编辑并记录消息"""
    message = await query.edit_message_text(text=text, **kwargs)
    # 异步记录
    import asyncio
    chat_id = query.message.chat_id if query.message else None
    user_id = query.from_user.id
    asyncio.create_task(log_outgoing_message(user_id, text, chat_id))
    return message

def dedupe_country_codes_from_templates(raw_codes: list) -> list[str]:
    """
    开户模板国家列表去重：同一国家码只保留一条（避免 distinct(country_code, country_name) 产生重复按钮），
    并合并大小写差异（如 id / ID），统一使用大写 ISO 码。
    """
    by_upper: dict[str, str] = {}
    for c in raw_codes:
        if c is None:
            continue
        s = str(c).strip()
        if not s:
            continue
        u = s.upper()
        by_upper.setdefault(u, u)
    return sorted(by_upper.keys())


async def get_group_ids() -> dict:
    """
    从后端 API 读取各 TG 群组 ID（回退环境变量）
    返回 {'tech_group_id': '...', 'billing_group_id': '...', 'admin_group_id': '...'}
    """
    from bot.services.api_client import APIClient
    
    # 基础环境变量回退
    ids = {
        'admin_group_id': os.getenv('TELEGRAM_ADMIN_GROUP_ID', ''),
        'tech_group_id': os.getenv('STAFF_GROUP_ID', ''),
        'billing_group_id': '',
    }
    
    try:
        api = APIClient()
        settings = await api.get_internal_settings()
        if settings:
            if settings.get('admin_group_id'):
                ids['admin_group_id'] = settings['admin_group_id']
            if settings.get('tech_group_id'):
                ids['tech_group_id'] = settings['tech_group_id']
            if settings.get('billing_group_id'):
                ids['billing_group_id'] = settings['billing_group_id']
    except Exception as e:
        logger.warning(f"从 API 读取群组 ID 配置失败，使用环境变量: {e}")
        
    return ids

async def get_user_binding_internal(tg_id: int) -> Optional[Dict]:
    """通过 API 获取用户绑定信息"""
    from bot.services.api_client import APIClient
    api = APIClient()
    user_info = await api.verify_user(tg_id)
    if user_info and user_info.get("role") == "customer":
        return user_info
    return None
