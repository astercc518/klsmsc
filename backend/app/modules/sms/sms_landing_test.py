"""短信落地测试记录模型"""
from sqlalchemy import Column, Integer, BigInteger, String, Text, Enum, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class SmsLandingTest(Base):
    __tablename__ = 'sms_landing_tests'

    id = Column(Integer, primary_key=True, autoincrement=True)
    requester_tg_id = Column(BigInteger, nullable=False, index=True, comment='发起员工 TG ID')
    requester_name = Column(String(100), comment='发起员工姓名')
    supplier_id = Column(Integer, ForeignKey('suppliers.id'), nullable=False, comment='供应商ID')
    supplier_name = Column(String(100), comment='供应商名称（冗余）')
    supplier_tg_group_id = Column(String(50), nullable=False, comment='供应商 TG 群 ID（冗余）')
    country = Column(String(100), nullable=False, comment='测试国家')
    sms_content = Column(Text, nullable=False, comment='测试短信文案（不含中文）')
    status = Column(
        Enum('pending', 'forwarded', 'completed', 'cancelled', name='sms_landing_test_status_enum'),
        default='pending',
        comment='状态'
    )
    forwarded_message_id = Column(Integer, comment='转发至供应商群的 TG 消息 ID')
    forwarded_at = Column(DateTime, comment='转发时间')
    result_photo_file_ids = Column(Text, comment='供应商回传截图 file_id（JSON 数组）')
    result_note = Column(Text, comment='供应商回复备注')
    completed_at = Column(DateTime, comment='完成时间')
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')
