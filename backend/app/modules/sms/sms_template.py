"""
短信模板模型
"""
from sqlalchemy import Column, Integer, String, Text, Enum, TIMESTAMP, Boolean, ForeignKey
from sqlalchemy.sql import func
from app.database import Base
import enum


class TemplateCategory(str, enum.Enum):
    """模板分类"""
    VERIFICATION = "verification"  # 验证码
    NOTIFICATION = "notification"  # 通知
    MARKETING = "marketing"        # 营销


class TemplateStatus(str, enum.Enum):
    """模板状态"""
    PENDING = "pending"      # 待审核
    APPROVED = "approved"    # 已通过
    REJECTED = "rejected"    # 已拒绝
    DISABLED = "disabled"    # 已禁用


def _enum_values(obj):
    return [e.value for e in obj]


class SmsTemplate(Base):
    """短信模板表"""
    __tablename__ = "sms_templates"

    id = Column(Integer, primary_key=True, index=True, comment="模板ID")
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True, comment="账户ID")
    name = Column(String(100), nullable=False, default="Template", comment="模板名称")
    category = Column(Enum(TemplateCategory, values_callable=_enum_values), nullable=True, default="notification", comment="模板分类")
    content = Column(Text, comment="模板内容（支持变量）")
    variables = Column(Text, comment="变量列表（JSON数组）")
    content_hash = Column(String(64), nullable=False, default="", comment="内容哈希")
    content_text = Column(Text, comment="白名单文案原文")
    status = Column(Enum(TemplateStatus, values_callable=_enum_values), nullable=True, default="pending", comment="审核状态")
    reject_reason = Column(Text, comment="拒绝原因")
    usage_count = Column(Integer, default=0, comment="使用次数")

    # 审核相关
    approved_by = Column(Integer, comment="审核人ID")
    approved_at = Column(TIMESTAMP, comment="审核时间")

    # 时间戳
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False, comment="创建时间")
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False, comment="更新时间")
    is_deleted = Column(Boolean, default=False, nullable=False, comment="软删除标记")
    
    def __repr__(self):
        return f"<SmsTemplate(id={self.id}, name='{self.name}', category='{self.category}', status='{self.status}')>"
