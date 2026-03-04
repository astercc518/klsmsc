"""Telegram消息记录模型"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Enum
from sqlalchemy.sql import func
from app.database import Base


class TelegramMessage(Base):
    """Telegram消息记录表"""
    __tablename__ = 'telegram_messages'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tg_user_id = Column(String(50), nullable=False, comment='Telegram用户ID')
    tg_username = Column(String(100), comment='Telegram用户名')
    tg_chat_id = Column(String(50), comment='Telegram聊天ID')
    
    direction = Column(Enum('incoming', 'outgoing', name='message_direction_enum'), 
                      nullable=False, comment='消息方向')
    message_type = Column(String(50), default='text', comment='消息类型: text/command/callback/photo等')
    content = Column(Text, comment='消息内容')
    
    # 关联账户(可选)
    account_id = Column(Integer, comment='关联账户ID')
    account_name = Column(String(100), comment='账户名称')
    
    # 元数据
    message_id = Column(String(50), comment='Telegram消息ID')
    reply_to_message_id = Column(String(50), comment='回复的消息ID')
    extra_data = Column(Text, comment='额外数据JSON')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now())
