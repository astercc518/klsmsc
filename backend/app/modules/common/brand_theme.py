"""
品牌皮肤数据模型

多品牌皮肤(最小集):主色 + Logo + 品牌名 + favicon。全实例唯一激活一套,
管理员后台可增删。logo/favicon 以 data URL(base64)存库,免静态目录/卷挂载。
"""
from sqlalchemy import Column, Integer, String, Boolean, TIMESTAMP
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.sql import func
from app.database import Base


class BrandTheme(Base):
    """品牌皮肤表"""
    __tablename__ = "brand_themes"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="品牌皮肤ID")
    name = Column(String(100), nullable=False, comment="品牌名称(界面/标题显示)")
    primary_color = Column(String(16), nullable=False, server_default="#2a9d8f", comment="主色 hex")
    # base64 data URL：logo 可能数十~上百 KB,Text(64KB) 不够,用 MEDIUMTEXT(16MB)
    logo = Column(MEDIUMTEXT, nullable=True, comment="Logo,data URL(base64)")
    favicon = Column(MEDIUMTEXT, nullable=True, comment="favicon,data URL(base64)")
    is_active = Column(Boolean, nullable=False, server_default="0", comment="是否当前激活(全实例唯一)")
    is_deleted = Column(Boolean, nullable=False, server_default="0", comment="软删除标记")
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False, comment="创建时间")
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False, comment="更新时间")

    def __repr__(self):
        return f"<BrandTheme(id={self.id}, name={self.name}, active={self.is_active})>"
