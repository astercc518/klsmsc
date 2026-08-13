"""节点(nodesms) RCS 群发的两张表：号码文件 与 群发任务。"""
from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


class RCSNumberFile(Base):
    """供上游 HTTP 拉取的号码 TXT。

    存 DB 不落盘：api 容器无持久化卷,重启会丢;而上游可能在任务排队/审核后
    才来拉(可能隔几小时),文件必须活得够久。顺带能审计谁在什么时候拉的。
    """

    __tablename__ = "rcs_number_files"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    token = Column(String(64), nullable=False, unique=True, comment="下载令牌(高熵随机)")
    channel_id = Column(BigInteger, comment="所属通道")
    batch_id = Column(BigInteger, comment="所属批次")
    phone_count = Column(Integer, nullable=False, default=0)
    content = Column(Text().with_variant(Text(length=4294967295), "mysql"), comment="TXT 正文")
    expires_at = Column(DateTime, nullable=False, comment="过期后拒绝下载")
    download_count = Column(Integer, nullable=False, default=0)
    first_downloaded_at = Column(DateTime)
    last_downloaded_at = Column(DateTime)
    last_downloaded_ip = Column(String(64))
    purged_at = Column(DateTime, comment="内容清空时间")
    created_at = Column(DateTime, server_default=func.now())


class RCSSendTask(Base):
    """一个节点群发任务 = 我们的一个批次（或一次提交）。"""

    __tablename__ = "rcs_send_tasks"

    # 本地生命周期
    STATE_CREATED = "created"     # 已建行,尚未提交上游
    STATE_ACCEPTED = "accepted"   # 上游已受理,拿到 sn
    STATE_RUNNING = "running"     # 轮询中(上游在途)
    STATE_FINAL = "final"         # 上游终态,待取结果
    STATE_APPLIED = "applied"     # 结果已处理完
    STATE_FAILED = "failed"       # 创建失败/不可恢复

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    channel_id = Column(BigInteger, nullable=False)
    batch_id = Column(BigInteger)
    account_id = Column(BigInteger)
    order_id = Column(String(64), nullable=False, unique=True, comment="我们生成,上游要求全局唯一")
    sn = Column(String(64), comment="上游任务号")
    country_code = Column(String(10))
    category = Column(String(32))
    number_file_id = Column(BigInteger)
    phone_count = Column(Integer, nullable=False, default=0)
    state = Column(String(20), nullable=False, default=STATE_CREATED)
    status = Column(Integer, comment="上游任务状态码 0-11")
    sum_count = Column(Integer, nullable=False, default=0)
    submit_num = Column(Integer, nullable=False, default=0)
    total_num = Column(Integer, nullable=False, default=0)
    send_time = Column(BigInteger)
    finish_time = Column(BigInteger)
    result_url = Column(String(500))
    result_fetched_at = Column(DateTime)
    result_applied_at = Column(DateTime)
    result_note = Column(String(500))
    last_polled_at = Column(DateTime)
    poll_count = Column(Integer, nullable=False, default=0)
    error = Column(String(500))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
