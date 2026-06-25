"""brand_themes：多品牌皮肤(主色+Logo+品牌名+favicon),全实例唯一激活

Revision ID: z1a2b3c4d5e6
Revises: y0z1a2b3c4d5

新增 brand_themes 表 + 种子默认品牌(考拉出海 #2a9d8f，激活)。logo/favicon 用
MEDIUMTEXT 存 base64 data URL。幂等:表已存在则跳过,避免生产重复执行报错。
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "z1a2b3c4d5e6"
down_revision: Union[str, None] = "y0z1a2b3c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "brand_themes"


def _has_table() -> bool:
    insp = sa.inspect(op.get_bind())
    return TABLE in insp.get_table_names()


def upgrade() -> None:
    if _has_table():
        return
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True, comment="品牌皮肤ID"),
        sa.Column("name", sa.String(100), nullable=False, comment="品牌名称"),
        sa.Column("primary_color", sa.String(16), nullable=False, server_default="#2a9d8f", comment="主色 hex"),
        sa.Column("logo", mysql.MEDIUMTEXT, nullable=True, comment="Logo base64 data URL"),
        sa.Column("favicon", mysql.MEDIUMTEXT, nullable=True, comment="favicon base64 data URL"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("0"), comment="当前激活(全实例唯一)"),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default=sa.text("0"), comment="软删除"),
        sa.Column("created_at", sa.TIMESTAMP, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="创建时间"),
        sa.Column("updated_at", sa.TIMESTAMP, nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), comment="更新时间"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    # 种子:从现有 OEM 单品牌(system_config 的 brand.name/brand.logo)继承名称与 Logo,
    # 主色用当前 #2a9d8f,直接激活 —— 保证升级后界面外观不变(无品牌则回落"考拉出海")。
    op.execute(
        "INSERT INTO brand_themes (name, primary_color, logo, is_active, is_deleted) "
        "SELECT "
        "  COALESCE(NULLIF((SELECT config_value FROM system_config WHERE config_key='brand.name'), ''), '考拉出海'), "
        "  '#2a9d8f', "
        "  (SELECT config_value FROM system_config WHERE config_key='brand.logo'), "
        "  1, 0"
    )


def downgrade() -> None:
    if _has_table():
        op.drop_table(TABLE)
