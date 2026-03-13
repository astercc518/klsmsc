"""工单系统模型"""
from sqlalchemy import Column, Integer, String, Enum, Text, DateTime, Boolean, ForeignKey, JSON, BigInteger
from sqlalchemy.dialects.mysql import INTEGER
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Ticket(Base):
    """工单表"""
    __tablename__ = 'tickets'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_no = Column(String(50), unique=True, nullable=False, comment='工单号')
    
    # 关联
    account_id = Column(INTEGER(unsigned=True), ForeignKey('accounts.id'), comment='账户ID(可为空，系统工单)')
    tg_user_id = Column(String(50), comment='Telegram用户ID(来自TG的工单)')
    
    # 工单类型
    ticket_type = Column(Enum('test', 'registration', 'recharge', 'technical', 'billing', 'feedback', 'other', 
                              name='ticket_type_enum'), 
                        default='other', comment='工单类型：test-测试申请,registration-开户,recharge-充值,technical-技术,billing-账务,feedback-反馈,other-其他')
    
    # 优先级
    priority = Column(Enum('low', 'normal', 'high', 'urgent', name='ticket_priority_enum'), 
                     default='normal', comment='优先级')
    
    # 分类
    category = Column(String(50), comment='分类标签')
    
    # 内容
    title = Column(String(200), nullable=False, comment='工单标题')
    description = Column(Text, comment='工单描述')
    
    # 附件
    attachments = Column(JSON, comment='附件列表(JSON数组)')
    
    # 状态
    status = Column(Enum('open', 'assigned', 'in_progress', 'pending_user', 'resolved', 'closed', 'cancelled',
                        name='ticket_status_enum'), 
                   default='open', comment='状态')
    
    # 分配
    assigned_to = Column(INTEGER(unsigned=True), ForeignKey('admin_users.id'), comment='分配给(管理员ID)')
    assigned_at = Column(DateTime, comment='分配时间')
    
    # 创建信息（created_by_id 可为 Telegram 用户 ID，需 BIGINT）
    created_by_type = Column(Enum('account', 'admin', 'telegram', 'system', name='created_by_type_enum'), 
                            default='account', comment='创建人类型')
    created_by_id = Column(BigInteger, comment='创建人ID(账户/管理员/Telegram用户ID)')
    
    # 解决信息
    resolved_at = Column(DateTime, comment='解决时间')
    resolved_by = Column(INTEGER(unsigned=True), ForeignKey('admin_users.id'), comment='解决人ID')
    resolution = Column(Text, comment='解决方案/备注')
    
    # 关闭信息
    closed_at = Column(DateTime, comment='关闭时间')
    closed_by = Column(BigInteger, comment='关闭人ID')
    close_reason = Column(String(255), comment='关闭原因')
    
    # 评价
    satisfaction_rating = Column(Integer, comment='满意度评分(1-5)')
    satisfaction_comment = Column(Text, comment='满意度评价')
    
    # 额外数据
    extra_data = Column(JSON, comment='额外数据(JSON)')
    
    # === 测试工单扩展字段 ===
    template_id = Column(Integer, ForeignKey('account_templates.id'), comment='关联开户模板ID')
    test_content = Column(Text, comment='测试文案内容')
    test_phone = Column(String(50), comment='测试号码')
    test_sender_id = Column(String(50), comment='测试SenderID')
    
    # 审核相关
    review_status = Column(
        Enum('pending', 'forwarded', 'approved', 'rejected', name='review_status_enum'),
        default='pending',
        comment='审核状态：pending-待审核,forwarded-已转发,approved-通过,rejected-拒绝'
    )
    reviewed_by = Column(INTEGER(unsigned=True), ForeignKey('admin_users.id'), comment='审核人ID')
    reviewed_at = Column(DateTime, comment='审核时间')
    review_note = Column(Text, comment='审核备注')
    
    # 转发消息追踪
    forwarded_to_group = Column(String(50), comment='转发到的TG群组ID')
    forwarded_message_id = Column(Integer, comment='转发消息的Message ID')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # 关系
    account = relationship("Account", backref="tickets")
    assignee = relationship("AdminUser", foreign_keys=[assigned_to], backref="assigned_tickets")
    resolver = relationship("AdminUser", foreign_keys=[resolved_by], backref="resolved_tickets")
    reviewer = relationship("AdminUser", foreign_keys=[reviewed_by], backref="reviewed_tickets")
    template = relationship("AccountTemplate", backref="tickets")
    replies = relationship("TicketReply", back_populates="ticket", order_by="TicketReply.created_at")


class TicketReply(Base):
    """工单回复表"""
    __tablename__ = 'ticket_replies'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_id = Column(Integer, ForeignKey('tickets.id'), nullable=False, comment='工单ID')
    
    # 回复人
    reply_by_type = Column(Enum('account', 'admin', 'telegram', 'system', name='reply_by_type_enum'), 
                          default='account', comment='回复人类型')
    reply_by_id = Column(Integer, comment='回复人ID')
    reply_by_name = Column(String(100), comment='回复人名称')
    
    # 内容
    content = Column(Text, nullable=False, comment='回复内容')
    
    # 附件
    attachments = Column(JSON, comment='附件列表(JSON数组)')
    
    # 标记
    is_internal = Column(Boolean, default=False, comment='是否为内部备注(客户不可见)')
    is_solution = Column(Boolean, default=False, comment='是否为解决方案')
    
    # 来源
    source = Column(Enum('web', 'telegram', 'api', 'system', name='reply_source_enum'), 
                   default='web', comment='来源')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now())
    
    # 关系
    ticket = relationship("Ticket", back_populates="replies")


class TicketTemplate(Base):
    """工单模板 - 用于快速回复"""
    __tablename__ = 'ticket_templates'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    template_name = Column(String(100), nullable=False, comment='模板名称')
    template_type = Column(String(50), comment='模板类型/分类')
    
    # 内容
    title_template = Column(String(200), comment='标题模板')
    content_template = Column(Text, nullable=False, comment='内容模板')
    
    # 使用统计
    usage_count = Column(Integer, default=0, comment='使用次数')
    
    # 状态
    status = Column(Enum('active', 'inactive', name='template_status_enum'), 
                   default='active', comment='状态')
    
    # 创建人
    created_by = Column(INTEGER(unsigned=True), ForeignKey('admin_users.id'), comment='创建人ID')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    is_deleted = Column(Boolean, default=False)
