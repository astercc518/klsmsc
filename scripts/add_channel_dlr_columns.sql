-- 通道级 DLR / SMPP 保持时间（与 backend/app/modules/sms/channel.py 一致）
-- 执行：mysql ... sms_system < scripts/add_channel_dlr_columns.sql
-- 若提示列已存在，可忽略或先检查 DESCRIBE channels;

ALTER TABLE channels
  ADD COLUMN smpp_dlr_socket_hold_seconds INT NULL DEFAULT NULL
    COMMENT 'SMPP发送成功后保持TCP秒数以接收deliver_sm，NULL=用全局SMPP_DLR_SOCKET_HOLD_SECONDS',
  ADD COLUMN dlr_sent_timeout_hours INT NULL DEFAULT NULL
    COMMENT 'sent状态最长等待终态DLR小时数，NULL=用全局DLR_SENT_TIMEOUT_HOURS';
