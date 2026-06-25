"""
短信记录数据模型
"""
from sqlalchemy import Column, Integer, String, DECIMAL, Enum, TIMESTAMP, Text, BigInteger, Computed, Index
from sqlalchemy.sql import func
from app.database import Base


class SMSLog(Base):
    """短信记录表"""
    __tablename__ = "sms_logs"

    # 性能索引：与 KLSMSC 生产库对齐。全新 create_all 部署若缺这些索引，批次进度统计
    # (WHERE batch_id GROUP BY status) 会全表扫描，并发发送时拖垮 MySQL。务必随表创建。
    __table_args__ = (
        Index("idx_sms_logs_batch_status", "batch_id", "status"),
        # idx_sms_logs_batch_id(单列 batch_id) 已删——被 idx_sms_logs_batch_status 左前缀
        # 完全覆盖(EXPLAIN 实测同 ref/key_len、仍 Using index),见迁移 e5f6a7b8c9d0。
        Index("idx_status", "status"),
        Index("idx_account_time", "account_id", "submit_time"),
        Index("idx_channel_id_submit", "channel_id", "submit_time"),
        Index("idx_country_code_submit", "country_code", "submit_time"),
        # 全局批次按通道筛选：DISTINCT batch_id WHERE channel_id=X 需要 batch_id 进索引，
        # 否则要回表读 3M+ 行再用临时表去重（实测 ~12s）。覆盖索引使其变松散索引扫描，子秒返回。
        Index("idx_channel_id_batch", "channel_id", "batch_id"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="记录ID")
    message_id = Column(String(64), nullable=False, unique=True, comment="消息ID")
    upstream_message_id = Column(String(64), index=True, comment="上游消息ID(用于状态报告匹配)")
    account_id = Column(Integer, nullable=False, comment="账户ID")
    channel_id = Column(Integer, comment="通道ID")
    batch_id = Column(Integer, comment="关联批次ID")
    phone_number = Column(String(20), nullable=False, comment="目标号码")
    country_code = Column(String(3), comment="国家代码")
    sender_id = Column(String(32), comment="本条实际使用的发送方ID(SID);空则用通道默认")
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

    # 退款追踪（管理员手动审核退款；NULL 表示未退款）
    refunded_at = Column(TIMESTAMP, comment="退款时间")
    refunded_by = Column(String(100), comment="执行退款的管理员用户名")
    refunded_amount = Column(DECIMAL(18, 6), comment="实际退款金额")

    def __repr__(self):
        return f"<SMSLog(id={self.id}, phone={self.phone_number}, status={self.status})>"
