"""
业务知识库数据模型
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum
from sqlalchemy.dialects.mysql import INTEGER
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class KnowledgeArticle(Base):
    """知识库文章表"""
    __tablename__ = "knowledge_articles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False, comment="标题")
    content = Column(Text, comment="正文内容")
    category = Column(String(50), default="general", comment="分类：sms/voice/data/general")
    summary = Column(String(500), comment="摘要")
    created_by = Column(INTEGER(unsigned=True), ForeignKey("admin_users.id"), comment="创建者")
    status = Column(
        Enum("draft", "published", name="knowledge_status_enum"),
        default="published",
        comment="状态"
    )
    view_count = Column(Integer, default=0, comment="浏览次数")
    is_pinned = Column(Integer, default=0, comment="是否置顶：0否 1是")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    attachments = relationship("KnowledgeAttachment", back_populates="article", cascade="all, delete-orphan")


class KnowledgeAttachment(Base):
    """知识库附件表"""
    __tablename__ = "knowledge_attachments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    article_id = Column(Integer, ForeignKey("knowledge_articles.id"), nullable=False)
    file_type = Column(String(20), nullable=False, comment="类型：doc/image/video")
    file_name = Column(String(255), nullable=False, comment="原始文件名")
    file_path = Column(String(500), nullable=False, comment="存储路径")
    file_size = Column(Integer, default=0, comment="文件大小(字节)")
    created_at = Column(DateTime, server_default=func.now())

    article = relationship("KnowledgeArticle", back_populates="attachments")
