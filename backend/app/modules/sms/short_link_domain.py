"""
短链域名配置表

由 super_admin 维护，前端「短链转换」对话框的下拉来源。
"""
from sqlalchemy import BigInteger, Boolean, Column, Enum, Integer, String, TIMESTAMP
from sqlalchemy.sql import func

from app.database import Base


class ShortLinkDomain(Base):
    __tablename__ = "short_link_domains"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    domain = Column(String(255), nullable=False, unique=True, comment="域名主体，如 go.kaolach.com")
    base_path = Column(String(64), nullable=False, default="/s", comment="路径前缀；空字符串=无前缀（最省字符）")
    scheme = Column(String(8), nullable=False, default="https", comment="https / http")
    omit_scheme = Column(
        Boolean, nullable=False, default=False,
        comment="短信里是否省略 https:// 前缀；True=只显示 domain[/path]/{token}",
    )
    remark = Column(String(255), nullable=True, comment="备注")
    status = Column(
        Enum("active", "disabled", name="short_link_domain_status"),
        nullable=False,
        default="active",
        comment="启停状态",
    )
    sort_order = Column(Integer, nullable=False, default=0, comment="排序权重，倒序")
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def base_url(self) -> str:
        """
        生成短链拼接前缀。注意三种形态：
          omit_scheme=False, path=/s   → "https://klsms.com/s"   （传统）
          omit_scheme=True,  path=/s   → "klsms.com/s"           （省 8 字符）
          omit_scheme=True,  path=""   → "klsms.com"             （最短，省 11 字符）
        """
        scheme = (self.scheme or "https").rstrip(":/")
        raw_path = (self.base_path or "").strip()
        path = raw_path.strip("/")  # 去掉首尾 /
        netpath = f"{self.domain}/{path}".rstrip("/") if path else self.domain
        if self.omit_scheme:
            return netpath
        return f"{scheme}://{netpath}"
