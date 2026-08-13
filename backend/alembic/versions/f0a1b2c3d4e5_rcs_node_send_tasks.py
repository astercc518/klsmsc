"""节点(nodesms) RCS 群发：号码文件表 + 群发任务表

节点是任务制：号码要以一个公网可下载的 TXT 提供给上游，提交后得到任务号 sn，
再轮询状态、终态后下载结果文件回写。两张表分别承载这两件事。

号码文件存 DB 而不是落盘：api 容器没有持久化卷，重启会丢；而上游可能在任务
排队/审核结束后才来拉取（可能隔几小时），文件必须活得够久。存 DB 顺带能审计
「上游什么时候拉的、拉了几次、从哪个 IP」。

按本仓惯例不设 DB 外键（channel_id / batch_id 只做逻辑关联 + 索引）。

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4
Create Date: 2026-08-10 15:40:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "f0a1b2c3d4e5"
down_revision: Union[str, None] = "e9f0a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NUMBER_FILES = """
CREATE TABLE IF NOT EXISTS rcs_number_files (
    id BIGINT NOT NULL AUTO_INCREMENT,
    token VARCHAR(64) NOT NULL COMMENT '下载令牌(高熵随机,URL 路径的一部分)',
    channel_id BIGINT NULL COMMENT '所属通道',
    batch_id BIGINT NULL COMMENT '所属批次',
    phone_count INT NOT NULL DEFAULT 0 COMMENT '号码条数',
    content LONGTEXT NULL COMMENT 'TXT 正文(每行一个号码);清理后置空',
    expires_at DATETIME NOT NULL COMMENT '过期时间,过期即拒绝下载',
    download_count INT NOT NULL DEFAULT 0 COMMENT '被上游拉取次数',
    first_downloaded_at DATETIME NULL,
    last_downloaded_at DATETIME NULL,
    last_downloaded_ip VARCHAR(64) NULL,
    purged_at DATETIME NULL COMMENT '内容清空时间(任务终态或过期后)',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_rcs_numfile_token (token),
    KEY idx_rcs_numfile_expires (expires_at),
    KEY idx_rcs_numfile_batch (batch_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='节点RCS群发号码文件(供上游HTTP拉取)'
"""

_SEND_TASKS = """
CREATE TABLE IF NOT EXISTS rcs_send_tasks (
    id BIGINT NOT NULL AUTO_INCREMENT,
    channel_id BIGINT NOT NULL COMMENT '通道',
    batch_id BIGINT NULL COMMENT '本系统批次',
    account_id BIGINT NULL COMMENT '客户账户',
    order_id VARCHAR(64) NOT NULL COMMENT '我们生成的商户订单号(上游要求全局唯一)',
    sn VARCHAR(64) NULL COMMENT '上游任务号;创建成功后回填',
    country_code VARCHAR(10) NULL,
    category VARCHAR(32) NULL COMMENT 'RCS_Text / RCS_ImgText',
    number_file_id BIGINT NULL COMMENT '号码文件 rcs_number_files.id',
    phone_count INT NOT NULL DEFAULT 0 COMMENT '提交号码数',
    state VARCHAR(20) NOT NULL DEFAULT 'created'
        COMMENT '本地生命周期: created/accepted/running/final/applied/failed',
    status INT NULL COMMENT '上游任务状态码(0-11)',
    sum_count INT NOT NULL DEFAULT 0 COMMENT '上游 sum 商户提交量',
    submit_num INT NOT NULL DEFAULT 0 COMMENT '上游 submitNum 计量',
    total_num INT NOT NULL DEFAULT 0 COMMENT '上游 totalNum 计费量',
    send_time BIGINT NULL COMMENT '上游发送时间戳',
    finish_time BIGINT NULL COMMENT '上游完成时间戳',
    result_url VARCHAR(500) NULL COMMENT 'getFile 返回的结果文件地址',
    result_fetched_at DATETIME NULL,
    result_applied_at DATETIME NULL COMMENT '结果已回写 sms_logs 的时间',
    result_note VARCHAR(500) NULL COMMENT '结果解析说明(如格式无法识别)',
    last_polled_at DATETIME NULL,
    poll_count INT NOT NULL DEFAULT 0,
    error VARCHAR(500) NULL COMMENT '最近一次错误(对内,可含上游原文)',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_rcs_task_order (order_id),
    KEY idx_rcs_task_poll (state, last_polled_at),
    KEY idx_rcs_task_batch (batch_id),
    KEY idx_rcs_task_sn (sn)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='节点RCS群发任务'
"""


def upgrade() -> None:
    op.execute(_NUMBER_FILES)
    op.execute(_SEND_TASKS)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS rcs_send_tasks")
    op.execute("DROP TABLE IF EXISTS rcs_number_files")
