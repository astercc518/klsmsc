"""
通道数据模型
"""
from sqlalchemy import Column, Integer, String, DECIMAL, Enum, Boolean, TIMESTAMP, Text
from sqlalchemy.sql import func
from app.database import Base


class Channel(Base):
    """通道表"""
    __tablename__ = "channels"
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment="通道ID")
    channel_code = Column(String(50), unique=True, nullable=False, comment="通道编码")
    channel_name = Column(String(100), nullable=False, comment="通道名称")
    protocol = Column(
        Enum("SMPP", "HTTP", "VIRTUAL", name="channel_protocol"),
        nullable=False,
        comment="协议类型"
    )
    host = Column(String(255), comment="主机地址")
    port = Column(Integer, comment="端口号")
    username = Column(String(100), comment="用户名")
    password = Column(String(255), comment="密码（加密存储）")
    smpp_bind_mode = Column(String(20), default="transceiver", comment="SMPP绑定模式: transceiver/transmitter/receiver")
    smpp_system_type = Column(String(13), default="", comment="SMPP system_type参数")
    smpp_interface_version = Column(Integer, default=52, comment="SMPP接口版本(0x34=52=v3.4)")
    smpp_dlr_socket_hold_seconds = Column(
        Integer,
        nullable=True,
        comment="SMPP发送成功后保持TCP秒数以接收deliver_sm，空则用全局SMPP_DLR_SOCKET_HOLD_SECONDS",
    )
    dlr_sent_timeout_hours = Column(
        Integer,
        nullable=True,
        comment="仍为sent时最长等待终态回执的小时数，空则用全局DLR_SENT_TIMEOUT_HOURS",
    )
    api_url = Column(String(500), comment="HTTP API地址")
    api_key = Column(String(255), comment="HTTP API密钥")
    
    default_sender_id = Column(String(20), nullable=False, comment="默认发送方ID(必填)")
    cost_rate = Column(DECIMAL(10, 4), default=0.0000, comment="通道基础成本价")
    
    max_tps = Column(Integer, default=100, comment="下发总速度(条/秒)")
    concurrency = Column(Integer, default=1, comment="并发数")
    rate_control_window = Column(Integer, default=1000, comment="速率控制窗口(毫秒)")
    
    priority = Column(Integer, nullable=False, default=0, comment="优先级")
    weight = Column(Integer, nullable=False, default=100, comment="权重")
    
    status = Column(
        Enum("active", "inactive", "maintenance", name="channel_status"),
        nullable=False,
        default="active",
        comment="配置状态：是否启用通道"
    )
    
    connection_status = Column(
        String(20),
        nullable=True,
        default="unknown",
        comment="连接状态：online=正常 offline=异常 unknown=未检测"
    )
    connection_checked_at = Column(TIMESTAMP, nullable=True, comment="最后检测时间")
    
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), comment="创建时间")
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间"
    )
    banned_words = Column(Text, nullable=True, comment="违禁词列表，逗号分隔")
    is_deleted = Column(Boolean, nullable=False, default=False, comment="软删除标记")

    virtual_config = Column(
        Text,
        nullable=True,
        comment="虚拟通道配置 JSON: {delivery_rate, fail_rate, pending_rate, dlr_delay_min, dlr_delay_max, fail_codes}",
    )
    config_json = Column(
        Text,
        nullable=True,
        comment="HTTP/SMPP 扩展 JSON：如 strip_leading_plus、payload_template、auth_type",
    )

    def get_gateway_config(self) -> dict:
        """解析 config_json，供网关/适配器读取 strip_leading_plus 等扩展项。"""
        import json
        raw = self.config_json
        if not raw:
            return {}
        try:
            if isinstance(raw, dict):
                return dict(raw)
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            return {}

    def strip_leading_plus_for_submit(self) -> bool:
        """提交到上游前是否去掉号码前导 +（默认 True）。"""
        from app.utils.phone_utils import strip_leading_plus_enabled

        return strip_leading_plus_enabled(self.get_gateway_config())

    def get_virtual_config(self) -> dict:
        """解析虚拟通道配置，返回带默认值的 dict（比例支持区间）"""
        import json
        defaults = {
            "delivery_rate_min": 80,
            "delivery_rate_max": 90,
            "fail_rate_min": 5,
            "fail_rate_max": 15,
            "dlr_delay_min": 3,
            "dlr_delay_max": 30,
            "fail_codes": ["UNDELIV"],
        }
        if not self.virtual_config:
            return defaults
        try:
            cfg = json.loads(self.virtual_config)
            # 兼容旧的单值配置：自动转换为区间
            if "delivery_rate" in cfg and "delivery_rate_min" not in cfg:
                v = cfg.pop("delivery_rate")
                cfg["delivery_rate_min"] = v
                cfg["delivery_rate_max"] = v
            if "fail_rate" in cfg and "fail_rate_min" not in cfg:
                v = cfg.pop("fail_rate")
                cfg["fail_rate_min"] = v
                cfg["fail_rate_max"] = v
            defaults.update(cfg)
        except (json.JSONDecodeError, TypeError):
            pass
        return defaults
    
    def __repr__(self):
        return f"<Channel(id={self.id}, code={self.channel_code}, status={self.status})>"
