"""
注水子系统数据模型
"""
from sqlalchemy import Column, Integer, String, DECIMAL, Enum, Boolean, TIMESTAMP, Text, BigInteger
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.sql import func

from app.database import Base


class WaterProxy(Base):
    """代理池表"""

    __tablename__ = "water_proxies"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    name = Column(String(100), nullable=False, comment="代理名称")
    proxy_type = Column(
        Enum("http", "https", "socks5", name="water_proxy_type"),
        nullable=False,
        default="http",
        comment="代理协议类型",
    )
    endpoint = Column(String(500), nullable=False, comment="代理地址")
    country_code = Column(String(5), nullable=False, default="*", comment="目标国家代码")
    country_auto = Column(Boolean, nullable=False, default=False, comment="是否支持占位符自动替换")
    max_concurrency = Column(Integer, nullable=False, default=10, comment="最大并发数")
    status = Column(
        Enum("active", "inactive", "testing", name="water_proxy_status"),
        nullable=False,
        default="active",
        comment="状态",
    )
    last_test_at = Column(TIMESTAMP, nullable=True, comment="最近检测时间")
    last_test_result = Column(String(200), nullable=True, comment="最近检测结果摘要")
    remark = Column(Text, nullable=True, comment="备注")
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), comment="创建时间")
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )


class WaterTaskConfig(Base):
    """注水任务配置表（按客户账户维度）"""

    __tablename__ = "water_task_configs"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    account_id = Column(Integer, nullable=False, unique=True, comment="关联客户账户 ID")
    enabled = Column(Boolean, nullable=False, default=False, comment="是否启用注水任务")
    click_rate_min = Column(DECIMAL(5, 2), nullable=False, default=3.00, comment="点击率下限(%)")
    click_rate_max = Column(DECIMAL(5, 2), nullable=False, default=8.00, comment="点击率上限(%)")
    click_delay_min = Column(Integer, nullable=False, default=60, comment="点击延迟下限(秒)")
    click_delay_max = Column(Integer, nullable=False, default=14400, comment="点击延迟上限(秒)")
    click_delay_curve = Column(DECIMAL(3, 1), nullable=False, default=4.0, comment="延迟分布曲线(1.0=均匀,4.0=自然先快后慢)")
    register_enabled = Column(Boolean, nullable=False, default=False, comment="是否启用注册注水")
    register_rate_min = Column(DECIMAL(5, 2), nullable=False, default=1.00, comment="注册率下限(%)")
    register_rate_max = Column(DECIMAL(5, 2), nullable=False, default=3.00, comment="注册率上限(%)")
    proxy_id = Column(Integer, nullable=True, comment="关联代理 ID")
    user_agent_type = Column(
        Enum("mobile", "desktop", "random", name="water_task_user_agent_type"),
        nullable=False,
        default="mobile",
        comment="User-Agent 类型",
    )
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), comment="创建时间")
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )


class WaterRegisterScript(Base):
    """按域名注册的脚本配置表"""

    __tablename__ = "water_register_scripts"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    name = Column(String(100), nullable=False, comment="脚本名称")
    domain = Column(String(255), nullable=False, unique=True, comment="目标域名（唯一）")
    steps = Column(Text, nullable=True, comment="步骤定义（JSON 字符串）")
    enabled = Column(Boolean, nullable=False, default=True, comment="是否启用")
    success_count = Column(Integer, nullable=False, default=0, comment="成功次数")
    fail_count = Column(Integer, nullable=False, default=0, comment="失败次数")
    last_run_at = Column(TIMESTAMP, nullable=True, comment="最近执行时间")
    remark = Column(Text, nullable=True, comment="备注")
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), comment="创建时间")
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )


class WaterInjectionLog(Base):
    """注水执行流水表"""

    __tablename__ = "water_injection_logs"

    id = Column(BIGINT(unsigned=True), primary_key=True, autoincrement=True, comment="主键")
    sms_log_id = Column(BigInteger, nullable=False, comment="关联短信记录 ID")
    account_id = Column(Integer, nullable=True, comment="客户账户 ID")
    batch_id = Column(Integer, nullable=True, comment="批次 ID")
    channel_id = Column(Integer, nullable=False, comment="通道 ID")
    task_config_id = Column(Integer, nullable=True, comment="任务配置 ID")
    url = Column(String(1000), nullable=False, comment="目标 URL")
    action = Column(
        Enum("click", "register", name="water_injection_action"),
        nullable=False,
        comment="动作类型",
    )
    status = Column(
        Enum("pending", "processing", "success", "failed", name="water_injection_log_status"),
        nullable=False,
        default="pending",
        comment="执行状态",
    )
    proxy_id = Column(Integer, nullable=True, comment="使用的代理 ID")
    proxy_ip = Column(String(50), nullable=True, comment="代理出口 IP")
    proxy_country = Column(String(5), nullable=True, comment="代理国家代码")
    duration_ms = Column(Integer, nullable=True, comment="耗时(毫秒)")
    error_message = Column(Text, nullable=True, comment="错误信息")
    screenshot_path = Column(String(500), nullable=True, comment="截图存储路径")
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), comment="创建时间")


class WaterUrlResolution(Base):
    """短链替换映射：用于绕过 Cloudflare Interactive Challenge 的短链服务"""

    __tablename__ = "water_url_resolutions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    short_url = Column(String(500), nullable=False, unique=True, comment="SMS 中出现的短链")
    resolved_url = Column(String(2000), nullable=False, comment="人工浏览器解析得到的真实落地页 URL")
    enabled = Column(Boolean, nullable=False, default=True)
    hit_count = Column(Integer, nullable=False, default=0, comment="累计命中次数")
    notes = Column(String(500), nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now())
