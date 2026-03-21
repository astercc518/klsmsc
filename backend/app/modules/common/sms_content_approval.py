"""短信内容审核表 - 客户通过业务助手提交的短信需供应商群审核通过后才发送"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Enum
from sqlalchemy.sql import func
from app.database import Base


class SmsContentApproval(Base):
    """短信内容审核表"""
    __tablename__ = 'sms_content_approvals'

    id = Column(Integer, primary_key=True, autoincrement=True)
    approval_no = Column(String(50), unique=True, nullable=False, comment='审核单号')

    # 关联
    account_id = Column(Integer, nullable=False, comment='账户ID')
    tg_user_id = Column(String(50), nullable=False, comment='Telegram用户ID')

    # 发送内容（只审核文案时 phone_number 可为空，发送时再填写）
    phone_number = Column(String(50), nullable=True, comment='目标号码，只审核文案时为空')
    content = Column(Text, nullable=False, comment='短信内容')

    # 状态
    status = Column(
        Enum('pending', 'approved', 'rejected', name='sms_approval_status_enum'),
        default='pending',
        comment='状态：pending-待审核,approved-已通过,rejected-已拒绝'
    )

    # 转发信息
    forwarded_to_group = Column(String(50), comment='转发到的TG群组ID')
    forwarded_message_id = Column(Integer, comment='转发消息的Message ID')

    # 审核信息
    reviewed_at = Column(DateTime, comment='审核时间')
    reviewed_by_name = Column(String(100), comment='审核人名称')
    review_note = Column(String(500), comment='审核备注/拒绝原因')

    # 发送结果（审核通过后）
    message_id = Column(String(100), comment='发送成功后的消息ID')
    send_error = Column(Text, comment='发送失败时的错误信息')

    # 时间戳
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
