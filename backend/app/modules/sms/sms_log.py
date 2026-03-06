"""
短信记录数据模型
"""
from sqlalchemy import Column, Integer, String, DECIMAL, Enum, TIMESTAMP, Text, BigInteger, Computed
from sqlalchemy.sql import func
from app.database import Base


class SMSLog(Base):
    """短信记录表"""
    __tablename__ = "sms_logs"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="记录ID")
    message_id = Column(String(64), nullable=False, unique=True, comment="消息ID")
    upstream_message_id = Column(String(64), comment="上游消息ID(用于状态报告匹配)")
    account_id = Column(Integer, nullable=False, comment="账户ID")
    channel_id = Column(Integer, comment="通道ID")
    batch_id = Column(Integer, comment="关联批次ID")
    phone_number = Column(String(20), nullable=False, comment="目标号码")
    country_code = Column(String(3), comment="国家代码")
    message = Column(Text, comment="短信内容")
    message_count = Column(Integer, default=1, comment="短信条数")
    status = Column(
        Enum("pending", "queued", "sent", "delivered", "failed", "expired", name="sms_status"),
        nullable=False,
        default="pending",
        comment="状态"
    )
    
    # 结算字段
    cost_price = Column(DECIMAL(10, 4), default=0.0000, comment="通道成本")
    selling_price = Column(DECIMAL(10, 4), default=0.0000, comment="销售价格")
    # profit 是生成列（computed column），使用 Computed 标记为只读
    profit = Column(DECIMAL(10, 4), Computed("selling_price - cost_price"), comment="毛利")
    
    currency = Column(String(10), default="USD", comment="币种")
    
    submit_time = Column(TIMESTAMP, nullable=False, server_default=func.now(), comment="提交时间")
    sent_time = Column(TIMESTAMP, comment="发送时间")
    delivery_time = Column(TIMESTAMP, comment="送达时间")
    error_message = Column(Text, comment="错误信息")
    
    def __repr__(self):
        return f"<SMSLog(id={self.id}, phone={self.phone_number}, status={self.status})>"
